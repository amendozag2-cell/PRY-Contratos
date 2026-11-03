"""Carga de contratos, análisis de riesgo con RAG (OpenAI simulado) y aislamiento entre usuarios."""

from app.models import DocumentoRag, FragmentoRag
from app.services.catalogos import obtener_id_detalle

from .conftest import crear_contrato, id_usuario, pdf_con_texto, registrar, vector_falso

LINEAS_CONTRATO = [
    "CONTRATO DE PRESTACION DE SERVICIOS PROFESIONALES",
    "PRIMERA.- OBJETO: El prestador desarrollara un sitio web para el contratante.",
    "SEGUNDA.- FORMA DE PAGO: El contratante pagara el valor en un plazo de 120 dias.",
    "TERCERA.- PENALIDAD: Por cada dia de retraso se cobrara el 5 % sin limite maximo.",
    "CUARTA.- JURISDICCION: Las partes se someten a los jueces de Guayaquil.",
]


def _agregar_norma(db, texto: str, articulo: str = "Art. 1561") -> None:
    """Agrega al corpus un fragmento legal con su embedding (simulado)."""
    documento = DocumentoRag(
        id_tipo_fuente=obtener_id_detalle(db, "TIPO_FUENTE", "LEY"),
        titulo="Código Civil de prueba", ruta_archivo="corpus_prueba.txt",
    )
    db.add(documento)
    db.flush()
    db.add(FragmentoRag(id_documento=documento.id_documento, numero_orden=1, articulo_referencia=articulo,
                        contenido=texto, embedding=vector_falso(texto)))
    db.commit()


# ------------------------------------------------------------------- carga
def test_cargar_pdf_lo_divide_en_clausulas(cliente, freelancer):
    pdf = pdf_con_texto(LINEAS_CONTRATO)
    r = cliente.post("/contratos", headers=freelancer, files={"archivo": ("servicios.pdf", pdf, "application/pdf")},
                     data={"rol_parte": "PRESTADOR", "contexto": "Me pagarán a los 30 días."})
    assert r.status_code == 201, r.text
    contrato = r.json()["contrato"]
    assert contrato["estado_analisis"] == "CARGADO"
    assert contrato["numero_clausulas"] >= 4

    # El mismo archivo otra vez se detecta como duplicado
    otra = cliente.post("/contratos", headers=freelancer, files={"archivo": ("copia.pdf", pdf, "application/pdf")})
    assert otra.status_code == 409
    assert otra.json()["detail"]["id_contrato"] == contrato["id_contrato"]


def test_solo_se_aceptan_pdf(cliente, freelancer):
    r = cliente.post("/contratos", headers=freelancer, files={"archivo": ("virus.exe", b"MZ\x90\x00", "application/pdf")})
    assert r.status_code == 400


def test_un_usuario_no_ve_contratos_de_otro(cliente, db, freelancer):
    contrato = crear_contrato(db, id_usuario(cliente, freelancer))
    intruso = registrar(cliente)
    assert cliente.get(f"/contratos/{contrato.id_contrato}", headers=intruso).status_code == 404
    assert cliente.post(f"/contratos/{contrato.id_contrato}/analizar", headers=intruso).status_code == 404
    assert cliente.get("/contratos", headers=intruso).json() == []
    assert len(cliente.get("/contratos", headers=freelancer).json()) == 1


# ---------------------------------------------------------------- análisis
def test_analisis_clasifica_cita_normas_y_verifica_lo_acordado(cliente, db, freelancer, llm_falso):
    _agregar_norma(db, "Las partes pueden pactar una penalidad por retraso; la penalidad excesiva puede reducirse.")
    contrato = crear_contrato(db, id_usuario(cliente, freelancer),
                              contexto="El pago es a los 30 días. Trabajo remoto.")

    r = cliente.post(f"/contratos/{contrato.id_contrato}/analizar", headers=freelancer)
    assert r.status_code == 200, r.text
    detalle = r.json()
    assert detalle["estado_analisis"] == "ANALIZADO"

    por_titulo = {c["titulo"]: c for c in detalle["clausulas"]}
    penalidad = por_titulo["TERCERA.- PENALIDAD"]
    assert penalidad["nivel_riesgo"]["codigo"] == "ALTO"
    assert penalidad["categoria_riesgo"]["codigo"] == "PENALIDAD"
    assert penalidad["fundamentos"], "la cláusula de penalidad debe citar la norma del corpus"
    assert penalidad["fundamentos"][0]["articulo_referencia"] == "Art. 1561"
    assert por_titulo["SEGUNDA.- FORMA DE PAGO"]["nivel_riesgo"]["codigo"] == "MEDIO"
    assert por_titulo["CUARTA.- JURISDICCIÓN"]["nivel_riesgo"]["codigo"] == "BAJO"

    # Puntaje = promedio de pesos (ALTO 100, MEDIO 50, BAJO 0, BAJO 0) = 37.5
    assert float(detalle["puntaje_riesgo_global"]) == 37.5
    assert "Conviene negociar" in detalle["resumen"]

    coberturas = {k["descripcion"]: k["cobertura"]["codigo"] for k in detalle["condiciones"]}
    assert coberturas == {"El pago se hace a los 30 días": "CONTRADICHA", "Se trabaja de forma remota": "AUSENTE"}

    # El papel del usuario y lo acordado llegaron al modelo
    assert any("LO QUE EL USUARIO DICE QUE ACORDARON" in m for m in llm_falso.mensajes)


def test_sin_corpus_el_analisis_usa_criterio_general(cliente, db, freelancer, llm_falso):
    db.query(FragmentoRag).update({FragmentoRag.estado: "I"})
    db.commit()
    contrato = crear_contrato(db, id_usuario(cliente, freelancer))
    detalle = cliente.post(f"/contratos/{contrato.id_contrato}/analizar", headers=freelancer).json()
    assert all(c["fundamentos"] == [] for c in detalle["clausulas"])
    assert "corpus legal está vacío" in detalle["resumen"]


def test_cambiar_contexto_queda_auditado(cliente, db, freelancer):
    contrato = crear_contrato(db, id_usuario(cliente, freelancer))
    r = cliente.patch(f"/contratos/{contrato.id_contrato}/contexto", headers=freelancer,
                      json={"rol_parte": "CONTRATANTE", "contexto_usuario": "Entrega en 2 semanas"})
    assert r.status_code == 200
    assert r.json()["rol_parte"]["codigo"] == "CONTRATANTE"
    assert r.json()["contexto_usuario"] == "Entrega en 2 semanas"


def test_quitar_del_historial(cliente, db, freelancer):
    contrato = crear_contrato(db, id_usuario(cliente, freelancer))
    assert cliente.patch(f"/contratos/{contrato.id_contrato}/inactivar", headers=freelancer).status_code == 204
    assert cliente.get(f"/contratos/{contrato.id_contrato}", headers=freelancer).status_code == 404


# ------------------------------------------------------------------ corpus
def test_administrador_carga_una_ley_al_corpus(cliente, administrador, llm_falso):
    ley = ("LEY DE PRUEBA\nArt. 1.- Primer artículo de la ley de prueba con texto suficiente.\n"
           "Art. 2.- Segundo artículo de la ley de prueba con texto suficiente.\n"
           "Art. 3.- Tercer artículo de la ley de prueba con texto suficiente.\n").encode()
    r = cliente.post("/admin/corpus", headers=administrador, files={"archivo": ("ley.txt", ley, "text/plain")},
                     data={"titulo": "Ley de prueba", "tipo_fuente": "LEY"})
    assert r.status_code == 201, r.text
    documento = r.json()
    assert documento["numero_fragmentos"] == 3

    fragmentos = cliente.get(f"/admin/corpus/{documento['id_documento']}/fragmentos", headers=administrador).json()
    assert [f["articulo_referencia"] for f in fragmentos["elementos"]] == ["Art. 1", "Art. 2", "Art. 3"]

    assert cliente.patch(f"/admin/corpus/{documento['id_documento']}/inactivar", headers=administrador).status_code == 200
    reactivado = cliente.patch(f"/admin/corpus/{documento['id_documento']}/reactivar", headers=administrador)
    assert reactivado.status_code == 200
    assert reactivado.json()["estado"] == "A"