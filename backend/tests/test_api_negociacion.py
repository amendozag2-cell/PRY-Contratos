"""Contrapropuestas, correo de negociación e informe PDF (OpenAI simulado)."""

from .conftest import crear_contrato, id_usuario


def _clausula(detalle: dict, palabra: str) -> dict:
    return next(c for c in detalle["clausulas"] if palabra in (c["titulo"] or ""))


def test_negociacion_requiere_contrato_analizado(cliente, db, freelancer, llm_falso):
    contrato = crear_contrato(db, id_usuario(cliente, freelancer), analizado=False)
    r = cliente.post(f"/contratos/{contrato.id_contrato}/contrapropuestas", headers=freelancer, json={})
    assert r.status_code == 422
    assert cliente.get(f"/contratos/{contrato.id_contrato}/reporte", headers=freelancer).status_code == 422


def test_flujo_de_contrapropuestas(cliente, db, freelancer, llm_falso):
    contrato = crear_contrato(db, id_usuario(cliente, freelancer), analizado=True)
    base = f"/contratos/{contrato.id_contrato}"

    detalle = cliente.post(f"{base}/contrapropuestas", headers=freelancer, json={}).json()
    con_propuesta = [c for c in detalle["clausulas"] if c["contrapropuesta"]]
    # Solo las cláusulas ALTO y MEDIO reciben contrapropuesta
    assert {c["nivel_riesgo"]["codigo"] for c in con_propuesta} == {"ALTO", "MEDIO"}
    penalidad = _clausula(detalle, "PENALIDAD")
    assert penalidad["contrapropuesta"]["estado"]["codigo"] == "GENERADA"
    assert "10 %" in penalidad["contrapropuesta"]["texto_propuesto"]

    # "Aceptó con cambios" exige el texto acordado
    ruta = f"{base}/clausulas/{penalidad['id_clausula']}/contrapropuesta"
    assert cliente.patch(ruta, headers=freelancer, json={"estado": "MODIFICADA"}).status_code == 422
    r = cliente.patch(ruta, headers=freelancer, json={"estado": "MODIFICADA", "texto_acordado": "Tope del 15 %."})
    assert _clausula(r.json(), "PENALIDAD")["contrapropuesta"]["texto_acordado"] == "Tope del 15 %."

    # Una cláusula sin riesgo no tiene contrapropuesta que responder
    jurisdiccion = _clausula(detalle, "JURISDICCIÓN")
    r = cliente.patch(f"{base}/clausulas/{jurisdiccion['id_clausula']}/contrapropuesta",
                      headers=freelancer, json={"estado": "ACEPTADA"})
    assert r.status_code == 404


def test_correo_no_pide_lo_que_ya_se_rechazo(cliente, db, freelancer, llm_falso):
    contrato = crear_contrato(db, id_usuario(cliente, freelancer), analizado=True)
    base = f"/contratos/{contrato.id_contrato}"
    detalle = cliente.post(f"{base}/contrapropuestas", headers=freelancer, json={}).json()
    pago = _clausula(detalle, "PAGO")
    cliente.patch(f"{base}/clausulas/{pago['id_clausula']}/contrapropuesta", headers=freelancer,
                  json={"estado": "RECHAZADA"})

    r = cliente.post(f"{base}/correos", headers=freelancer,
                     json={"tono": "CORDIAL", "destinatario": "Ing. Carlos", "incluir_advertencias": True})
    assert r.status_code == 201, r.text
    assert r.json()["asunto"] == "Revisión del contrato de servicios"
    mensaje = llm_falso.mensajes[-1]
    assert "PENALIDAD" in mensaje
    assert "FORMA DE PAGO" not in mensaje  # rechazada: no se vuelve a pedir
    assert "Ing. Carlos" in mensaje

    historial = cliente.get(f"{base}/correos", headers=freelancer).json()
    assert len(historial) == 1 and historial[0]["tono"]["codigo"] == "CORDIAL"


def test_informe_pdf(cliente, db, freelancer, llm_falso):
    contrato = crear_contrato(db, id_usuario(cliente, freelancer), analizado=True)
    cliente.post(f"/contratos/{contrato.id_contrato}/contrapropuestas", headers=freelancer, json={})
    r = cliente.get(f"/contratos/{contrato.id_contrato}/reporte", headers=freelancer)
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert r.content.startswith(b"%PDF")

    import pymupdf

    with pymupdf.open(stream=r.content, filetype="pdf") as documento:
        texto = "".join(p.get_text() for p in documento)
    assert "Informe de riesgos del contrato" in texto
    assert "PENALIDAD" in texto
    assert "gina 1 de" in texto  # pie: "Página 1 de N"