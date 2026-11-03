"""Gestión del corpus legal y búsqueda semántica (recuperación del pipeline RAG)."""

import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.constantes import (
    ACC_CREACION_DOCUMENTO_RAG,
    PAR_CHUNK_SOLAPAMIENTO,
    PAR_CHUNK_TAMANIO,
    PAR_EMBEDDING_DIMENSION,
    PAR_EMBEDDING_MODELO,
    PAR_RAG_TOP_K,
)
from app.models import (
    DIMENSION_EMBEDDING,
    ESTADO_ACTIVO,
    DocumentoRag,
    FragmentoRag,
    Usuario,
)
from app.services.auditoria import registrar_evento
from app.services.embeddings import generar_embeddings
from app.services.extraccion import extraer_texto
from app.services.fragmentacion import Fragmento, contar_articulos, fragmentar
from app.services.parametros import obtener_entero, obtener_parametro


class ErrorCorpus(Exception):
    """Error de validación o configuración del corpus."""


@dataclass
class ConfiguracionRag:
    modelo: str
    dimension: int
    tamanio: int
    solapamiento: int
    top_k: int


@dataclass
class ResultadoCarga:
    documento: DocumentoRag
    fragmentos: int
    articulos: int


def leer_configuracion(db: Session) -> ConfiguracionRag:
    """Lee los parámetros del RAG desde cat_parametro."""
    dimension = obtener_entero(db, PAR_EMBEDDING_DIMENSION, DIMENSION_EMBEDDING)
    if dimension != DIMENSION_EMBEDDING:
        raise ErrorCorpus(
            f"El parámetro EMBEDDING_DIMENSION ({dimension}) debe ser {DIMENSION_EMBEDDING}, "
            "igual al tamaño de la columna rag_fragmento.embedding"
        )
    return ConfiguracionRag(
        modelo=obtener_parametro(db, PAR_EMBEDDING_MODELO, "text-embedding-3-small"),
        dimension=dimension,
        tamanio=obtener_entero(db, PAR_CHUNK_TAMANIO, 1000),
        solapamiento=obtener_entero(db, PAR_CHUNK_SOLAPAMIENTO, 150),
        top_k=obtener_entero(db, PAR_RAG_TOP_K, 5),
    )


def texto_para_embedding(titulo: str, fragmento: Fragmento) -> str:
    """Antepone la fuente al fragmento para que el vector conserve su contexto."""
    fuente = f"{titulo}, {fragmento.articulo_referencia}" if fragmento.articulo_referencia else titulo
    return f"{fuente}\n{fragmento.contenido}"


def registrar_documento(
    db: Session,
    request: Request,
    administrador: Usuario,
    *,
    contenido: bytes,
    extension: str,
    nombre_archivo: str,
    titulo: str,
    id_tipo_fuente: int,
    codigo_tipo_fuente: str,
    referencia: str | None,
) -> ResultadoCarga:
    """Extrae, fragmenta, vectoriza y guarda un documento del corpus."""
    configuracion = leer_configuracion(db)

    texto = extraer_texto(contenido, extension)
    fragmentos = fragmentar(texto, configuracion.tamanio, configuracion.solapamiento)
    if not fragmentos:
        raise ErrorCorpus("No se obtuvieron fragmentos del documento")

    vectores = generar_embeddings(
        [texto_para_embedding(titulo, f) for f in fragmentos],
        configuracion.modelo,
        configuracion.dimension,
    )

    carpeta = Path(settings.directorio_archivos) / "corpus"
    carpeta.mkdir(parents=True, exist_ok=True)
    ruta = carpeta / f"{uuid.uuid4().hex}{extension}"
    ruta.write_bytes(contenido)

    try:
        documento = DocumentoRag(
            id_tipo_fuente=id_tipo_fuente,
            titulo=titulo,
            referencia=referencia,
            ruta_archivo=ruta.as_posix(),
            usuario_creacion=administrador.id_usuario,
        )
        db.add(documento)
        db.flush()

        db.add_all(
            FragmentoRag(
                id_documento=documento.id_documento,
                numero_orden=f.numero_orden,
                articulo_referencia=f.articulo_referencia,
                contenido=f.contenido,
                embedding=vector,
                usuario_creacion=administrador.id_usuario,
            )
            for f, vector in zip(fragmentos, vectores, strict=True)
        )

        articulos = contar_articulos(texto)
        registrar_evento(
            db, request, ACC_CREACION_DOCUMENTO_RAG,
            usuario=administrador,
            tabla_afectada="rag_documento",
            id_registro=documento.id_documento,
            datos_nuevos={
                "titulo": titulo,
                "tipo_fuente": codigo_tipo_fuente,
                "archivo": nombre_archivo,
                "fragmentos": len(fragmentos),
                "articulos_detectados": articulos,
            },
        )
        db.commit()
    except Exception:
        db.rollback()
        ruta.unlink(missing_ok=True)
        raise

    db.refresh(documento)
    return ResultadoCarga(documento=documento, fragmentos=len(fragmentos), articulos=articulos)


def inactivar_documento(db: Session, documento: DocumentoRag, administrador: Usuario) -> None:
    documento.estado = "I"
    documento.usuario_modificacion = administrador.id_usuario
    documento.fecha_modificacion = datetime.now(timezone.utc)

def reactivar_documento(db: Session, documento: DocumentoRag, administrador: Usuario) -> None:
    documento.estado = ESTADO_ACTIVO
    documento.usuario_modificacion = administrador.id_usuario
    documento.fecha_modificacion = datetime.now(timezone.utc)

@dataclass
class ResultadoBusqueda:
    fragmento: FragmentoRag
    titulo_documento: str
    similitud: float


def buscar_fragmentos(
    db: Session, consulta: str, top_k: int | None = None
) -> tuple[list[ResultadoBusqueda], ConfiguracionRag, int]:
    """Recupera los fragmentos del corpus más parecidos a la consulta.

    Es el paso de recuperación del RAG: en el Avance 4 se usará para buscar
    las normas relacionadas con cada cláusula del contrato.
    Devuelve los resultados, la configuración usada y el tiempo en milisegundos.
    """
    configuracion = leer_configuracion(db)
    limite = top_k or configuracion.top_k
    inicio = time.perf_counter()

    vector = generar_embeddings([consulta], configuracion.modelo, configuracion.dimension)[0]
    distancia = FragmentoRag.embedding.cosine_distance(vector).label("distancia")
    filas = db.execute(
        select(FragmentoRag, DocumentoRag.titulo, distancia)
        .join(DocumentoRag, DocumentoRag.id_documento == FragmentoRag.id_documento)
        .where(FragmentoRag.estado == ESTADO_ACTIVO, DocumentoRag.estado == ESTADO_ACTIVO)
        .order_by(distancia)
        .limit(limite)
    ).all()

    resultados = [
        ResultadoBusqueda(fragmento=f, titulo_documento=titulo, similitud=round(1 - float(d), 4))
        for f, titulo, d in filas
    ]
    milisegundos = round((time.perf_counter() - inicio) * 1000)
    return resultados, configuracion, milisegundos