"""Configuración común de las pruebas automáticas.

- Usa una base de datos SEPARADA (<base>_test en el mismo servidor PostgreSQL). Se borra y se
  vuelve a crear en cada ejecución, y se le aplican todas las migraciones de Alembic.
- Cada prueba corre dentro de una transacción que se revierte al terminar: las pruebas no se
  afectan entre sí y la base real (contratos_db) nunca se toca.
- OpenAI NUNCA se llama: los embeddings y las respuestas del LLM se reemplazan por funciones
  deterministas (fixture `llm_falso`), así las pruebas no gastan saldo ni dependen de internet.

Para usar otra base de pruebas, defina la variable de entorno TEST_DATABASE_URL.
"""

import hashlib
import math
import os
import re
import shutil
import uuid
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.config import settings

RAIZ = Path(__file__).resolve().parents[1]  # carpeta backend/

# ----------------------------------------------------------- base de pruebas
_url_principal = make_url(settings.database_url)
URL_PRUEBAS = make_url(
    os.environ.get("TEST_DATABASE_URL")
    or _url_principal.set(database=f"{_url_principal.database}_test").render_as_string(hide_password=False)
)
if not URL_PRUEBAS.database.endswith("_test"):
    raise RuntimeError("Por seguridad, la base de pruebas debe terminar en _test")

# La aplicación y Alembic leen `settings`: se apuntan a la base y carpetas de prueba ANTES de
# importar app.db (que crea el engine al importarse).
settings.database_url = URL_PRUEBAS.render_as_string(hide_password=False)
settings.openai_api_key = ""
_temporal = RAIZ / ".pruebas_tmp"
settings.directorio_archivos = str(_temporal / "storage")
settings.directorio_confianza = str(_temporal / "confianza")

from fastapi.testclient import TestClient  # noqa: E402

from app.constantes import CAT_ESTADO_ANALISIS, EST_ANALIZADO, EST_CARGADO, ROL_ADMINISTRADOR  # noqa: E402
from app.db import engine, get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Clausula, Contrato, NivelRiesgo, Rol, Usuario  # noqa: E402
from app.security import hash_clave  # noqa: E402
from app.services.catalogos import obtener_id_detalle  # noqa: E402
from app.services.llm import (  # noqa: E402
    CondicionesExtraidas,
    ContrapropuestaGenerada,
    CorreoGenerado,
    DiagnosticoClausula,
    VerificacionCondicion,
)

CLAVE = "ClaveSegura123"


def _recrear_base() -> None:
    admin = create_engine(_url_principal, isolation_level="AUTOCOMMIT")
    with admin.connect() as conexion:
        conexion.execute(text(f'DROP DATABASE IF EXISTS "{URL_PRUEBAS.database}" WITH (FORCE)'))
        conexion.execute(text(f'CREATE DATABASE "{URL_PRUEBAS.database}" ENCODING \'UTF8\' TEMPLATE template0'))
    admin.dispose()


def aplicar_migraciones(destino: str = "head") -> None:
    from alembic import command
    from alembic.config import Config

    configuracion = Config(str(RAIZ / "alembic.ini"))
    configuracion.set_main_option("script_location", str(RAIZ / "migrations"))
    command.upgrade(configuracion, destino)


def revertir_migraciones(destino: str = "base") -> None:
    from alembic import command
    from alembic.config import Config

    configuracion = Config(str(RAIZ / "alembic.ini"))
    configuracion.set_main_option("script_location", str(RAIZ / "migrations"))
    command.downgrade(configuracion, destino)


@pytest.fixture(scope="session", autouse=True)
def base_de_pruebas():
    shutil.rmtree(_temporal, ignore_errors=True)
    _recrear_base()
    aplicar_migraciones()
    yield
    engine.dispose()
    shutil.rmtree(_temporal, ignore_errors=True)


@pytest.fixture
def db():
    """Sesión dentro de una transacción que se revierte al final de cada prueba.

    Los commit() del código se convierten en SAVEPOINT, así que nada queda guardado.
    """
    conexion = engine.connect()
    transaccion = conexion.begin()
    sesion = Session(bind=conexion, join_transaction_mode="create_savepoint",
                     autoflush=False, expire_on_commit=False)
    try:
        yield sesion
    finally:
        sesion.close()
        transaccion.rollback()
        conexion.close()


@pytest.fixture
def cliente(db):
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


# ----------------------------------------------------------------- usuarios
def registrar(cliente: TestClient, correo: str | None = None, rol: str = "FREELANCER", **extra) -> dict:
    """Registra un usuario por la API, inicia sesión y devuelve los encabezados con el token."""
    correo = correo or f"usuario_{uuid.uuid4().hex[:8]}@prueba.ec"
    datos = {"correo": correo, "nombres": "Ana", "apellidos": "Pérez", "clave": CLAVE, "rol": rol, **extra}
    r = cliente.post("/auth/registro", json=datos)
    assert r.status_code == 201, r.text
    return iniciar_sesion(cliente, correo)


def iniciar_sesion(cliente: TestClient, correo: str, clave: str = CLAVE) -> dict:
    r = cliente.post("/auth/login", data={"username": correo, "password": clave})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture
def freelancer(cliente) -> dict:
    return registrar(cliente)


@pytest.fixture
def administrador(cliente, db) -> dict:
    correo = f"admin_{uuid.uuid4().hex[:8]}@prueba.ec"
    rol = db.query(Rol).filter(Rol.codigo == ROL_ADMINISTRADOR).one()
    db.add(Usuario(rol=rol, correo=correo, nombres="Admin", apellidos="Sistema", clave_hash=hash_clave(CLAVE)))
    db.commit()
    return iniciar_sesion(cliente, correo)


def id_usuario(cliente: TestClient, encabezados: dict) -> int:
    return cliente.get("/auth/perfil", headers=encabezados).json()["id_usuario"]


# ---------------------------------------------------------------- contratos
CLAUSULAS_EJEMPLO = [
    ("PRIMERA.- OBJETO", "EL PRESTADOR se obliga a desarrollar el sitio web de EL CONTRATANTE."),
    ("SEGUNDA.- FORMA DE PAGO", "EL CONTRATANTE pagará el valor acordado en un plazo de 120 días "
                                "contados desde la entrega final."),
    ("TERCERA.- PENALIDAD", "Por cada día de retraso EL PRESTADOR pagará una penalidad del 5 % del valor "
                            "total, sin límite máximo."),
    ("CUARTA.- JURISDICCIÓN", "Las partes se someten a los jueces de la ciudad de Guayaquil."),
]


def crear_contrato(db, id_usuario: int, *, analizado: bool = False, contexto: str | None = None) -> Contrato:
    """Contrato con cláusulas creado directamente en la base (sin pasar por el PDF ni OCR).

    Con analizado=True la cláusula de penalidad queda en ALTO, la de pago en MEDIO y el resto en BAJO.
    """
    estado = EST_ANALIZADO if analizado else EST_CARGADO
    contrato = Contrato(
        id_usuario=id_usuario,
        id_estado_analisis=obtener_id_detalle(db, CAT_ESTADO_ANALISIS, estado),
        nombre_archivo="contrato_prueba.pdf",
        ruta_archivo=str(Path(settings.directorio_archivos) / "no_existe.pdf"),
        hash_archivo=uuid.uuid4().hex * 2,
        numero_paginas=1,
        contexto_usuario=contexto,
        puntaje_riesgo_global=50 if analizado else None,
        usuario_creacion=id_usuario,
    )
    db.add(contrato)
    db.flush()
    niveles = {n.codigo: n.id_nivel_riesgo for n in db.query(NivelRiesgo)}
    for orden, (titulo, contenido) in enumerate(CLAUSULAS_EJEMPLO, start=1):
        nivel = None
        if analizado:
            nivel = niveles["ALTO"] if "PENALIDAD" in titulo else niveles["MEDIO"] if "PAGO" in titulo else niveles["BAJO"]
        db.add(Clausula(
            id_contrato=contrato.id_contrato, numero_orden=orden, titulo=titulo, contenido=contenido,
            numero_pagina=1, coordenadas=[{"pagina": 1, "x0": 0.1, "y0": 0.1 * orden, "x1": 0.9, "y1": 0.1 * orden + 0.05}],
            id_nivel_riesgo=nivel, explicacion="Explicación de prueba" if analizado else None,
            usuario_creacion=id_usuario,
        ))
    db.commit()
    return contrato


def pdf_con_texto(lineas: list[str]) -> bytes:
    """PDF de una página con el texto indicado (generado con PyMuPDF)."""
    import pymupdf

    documento = pymupdf.open()
    pagina = documento.new_page()
    for i, linea in enumerate(lineas):
        pagina.insert_text((60, 70 + i * 16), linea, fontsize=10)
    datos = documento.tobytes()
    documento.close()
    return datos


# ---------------------------------------------------------- OpenAI simulado
def vector_falso(texto: str, dimension: int = 1536) -> list[float]:
    """Embedding determinista: bolsa de palabras con hashing. Textos con palabras en común se parecen."""
    vector = [0.0] * dimension
    for palabra in re.findall(r"[a-záéíóúñ]{4,}", texto.lower()):
        vector[int(hashlib.md5(palabra.encode()).hexdigest(), 16) % dimension] += 1.0
    norma = math.sqrt(sum(v * v for v in vector)) or 1.0
    return [v / norma for v in vector]


class LlmFalso:
    """Reemplaza las llamadas a OpenAI y guarda los mensajes enviados para revisarlos."""

    def __init__(self):
        self.mensajes: list[str] = []

    def embeddings(self, textos, modelo, dimension):
        return [vector_falso(t, dimension) for t in textos]

    def clasificar(self, modelo, instrucciones, mensaje):
        self.mensajes.append(mensaje)
        clausula = mensaje.split("CLÁUSULA A EVALUAR:", 1)[1].split("CONTEXTO", 1)[0].lower()
        con_normas = "[1]" in mensaje
        if "penalidad" in clausula:
            return DiagnosticoClausula(nivel="ALTO", categoria="PENALIDAD", fundamentos=[1] if con_normas else [],
                                       explicacion="La penalidad no tiene límite.")
        if "pagará" in clausula and "días" in clausula:
            return DiagnosticoClausula(nivel="MEDIO", categoria="PLAZO_PAGO", fundamentos=[1] if con_normas else [],
                                       explicacion="El plazo de pago es largo.")
        return DiagnosticoClausula(nivel="BAJO", categoria="NINGUNA", fundamentos=[], explicacion="Cláusula formal.")

    def estructurado(self, modelo, instrucciones, mensaje, formato):
        self.mensajes.append(mensaje)
        if formato is CondicionesExtraidas:
            return CondicionesExtraidas(condiciones=["El pago se hace a los 30 días", "Se trabaja de forma remota"])
        if formato is VerificacionCondicion:
            if "30 días" in mensaje.split("CLÁUSULAS")[0]:
                return VerificacionCondicion(cobertura="CONTRADICHA", clausula=2, explicacion="El contrato dice 120 días.")
            return VerificacionCondicion(cobertura="AUSENTE", clausula=None, explicacion="No se menciona.")
        if formato is ContrapropuestaGenerada:
            return ContrapropuestaGenerada(
                texto_propuesto="La penalidad será del 1 % diario y no excederá el 10 % del valor total.",
                justificacion="Se fija un tope razonable a la multa.")
        if formato is CorreoGenerado:
            return CorreoGenerado(asunto="Revisión del contrato de servicios",
                                  cuerpo="Estimado cliente:\n1. Cláusula de penalidad: proponemos un tope.\nSaludos.")
        raise AssertionError(f"Formato no esperado: {formato}")


@pytest.fixture
def llm_falso(monkeypatch) -> LlmFalso:
    falso = LlmFalso()
    monkeypatch.setattr("app.services.analisis.generar_embeddings", falso.embeddings)
    monkeypatch.setattr("app.services.corpus.generar_embeddings", falso.embeddings)
    monkeypatch.setattr("app.services.analisis.clasificar_clausula", falso.clasificar)
    monkeypatch.setattr("app.services.analisis.generar_estructurado", falso.estructurado)
    monkeypatch.setattr("app.services.negociacion.generar_estructurado", falso.estructurado)
    return falso


# -------------------------------------------------------------- certificados
@pytest.fixture(scope="session")
def certificados(tmp_path_factory) -> dict:
    """Dos certificados .p12 de prueba firmados por una CA de prueba."""
    from scripts.crear_certificado_prueba import crear

    carpeta = tmp_path_factory.mktemp("certificados")
    return {
        "carpeta": carpeta,
        "ana": (crear("Ana Pérez Ñáñez", "0912345678", "ClaveAna1", carpeta).read_bytes(), "ClaveAna1"),
        "luis": (crear("Luis Torres", "0923456789", "ClaveLuis1", carpeta).read_bytes(), "ClaveLuis1"),
    }