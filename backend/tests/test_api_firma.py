"""Firma electrónica PAdES: versión final, firma en la plataforma, firma externa y verificación."""

import shutil
from pathlib import Path

from sqlalchemy import Text, cast, func, select

from app.config import settings
from app.models import Auditoria, DocumentoFirma
from app.services.firma_pdf import caja_firma, firmar_pdf, leer_certificado_p12

from .conftest import crear_contrato, id_usuario, pdf_con_texto

TEXTO_FINAL = [
    "CONTRATO DE PRESTACION DE SERVICIOS - VERSION FINAL",
    "PRIMERA.- OBJETO: El prestador desarrollara un sitio web.",
    "TERCERA.- PENALIDAD: La penalidad sera del 1 % diario y no excedera el 10 % del valor total.",
    "CUARTA.- JURISDICCION: Las partes se someten a los jueces de Guayaquil.",
    "Texto adicional para que el documento tenga contenido suficiente para la comparacion.",
    "Texto adicional para que el documento tenga contenido suficiente para la comparacion.",
]


def _preparar(cliente, db, encabezados, llm_falso, firmas_requeridas: int = 2) -> tuple[str, dict]:
    contrato = crear_contrato(db, id_usuario(cliente, encabezados), analizado=True)
    base = f"/contratos/{contrato.id_contrato}"
    detalle = cliente.post(f"{base}/contrapropuestas", headers=encabezados, json={}).json()
    penalidad = next(c for c in detalle["clausulas"] if "PENALIDAD" in c["titulo"])
    cliente.patch(f"{base}/clausulas/{penalidad['id_clausula']}/contrapropuesta", headers=encabezados,
                  json={"estado": "ACEPTADA"})
    r = cliente.post(f"{base}/firma", headers=encabezados,
                     files={"archivo": ("final.pdf", pdf_con_texto(TEXTO_FINAL), "application/pdf")},
                     data={"firmas_requeridas": str(firmas_requeridas)})
    assert r.status_code == 201, r.text
    return base, r.json()


def _firmar(cliente, base, encabezados, certificado, clave=None):
    contenido, clave_correcta = certificado
    return cliente.post(f"{base}/firma/firmar", headers=encabezados,
                        files={"certificado": ("firma.p12", contenido, "application/x-pkcs12")},
                        data={"clave": clave or clave_correcta})


def test_version_final_y_cambios_acordados(cliente, db, freelancer, llm_falso):
    base, documento = _preparar(cliente, db, freelancer, llm_falso)
    assert documento["estado_firma"] == "PENDIENTE"
    assert documento["numero_version"] == 1
    assert documento["hash_vigente"] == documento["hash_archivo"]
    cambio = documento["cambios"][0]
    assert cambio["estado"] == "ACEPTADA" and cambio["resultado"] == "INCLUIDA"


def test_firma_en_la_plataforma(cliente, db, freelancer, llm_falso, certificados):
    base, _ = _preparar(cliente, db, freelancer, llm_falso)

    mala = _firmar(cliente, base, freelancer, certificados["ana"], clave="incorrecta")
    assert mala.status_code == 422
    assert "contraseña" in mala.json()["detail"]

    r = _firmar(cliente, base, freelancer, certificados["ana"])
    assert r.status_code == 200, r.text
    documento = r.json()
    assert documento["estado_firma"] == "FIRMADO_PARCIAL"
    assert documento["ya_firme"] is True
    firma = documento["firmas"][0]
    assert firma["titular"] == "ANA PÉREZ ÑÁÑEZ"
    assert firma["identificacion"] == "0912345678"
    assert firma["en_plataforma"] and firma["es_integra"]
    assert firma["es_confiable"] is False  # la CA de prueba no está en la carpeta de confianza
    assert documento["hash_vigente"] != documento["hash_archivo"]

    # El mismo usuario no puede firmar dos veces
    assert _firmar(cliente, base, freelancer, certificados["luis"]).status_code == 422


def test_la_clave_del_certificado_no_queda_registrada(cliente, db, freelancer, llm_falso, certificados):
    base, _ = _preparar(cliente, db, freelancer, llm_falso)
    _firmar(cliente, base, freelancer, certificados["ana"], clave="ClaveSecretaErronea")
    _firmar(cliente, base, freelancer, certificados["ana"])
    filtrados = db.scalar(select(func.count()).select_from(Auditoria).where(
        func.coalesce(cast(Auditoria.datos_nuevos, Text), "").ilike("%ClaveAna1%")
        | func.coalesce(Auditoria.observacion, "").ilike("%ClaveSecretaErronea%")
    ))
    assert filtrados == 0


def test_firma_externa_completa_el_documento(cliente, db, freelancer, llm_falso, certificados):
    base, _ = _preparar(cliente, db, freelancer, llm_falso)
    _firmar(cliente, base, freelancer, certificados["ana"])
    vigente = cliente.get(f"{base}/firma/archivo", headers=freelancer).content

    luis = leer_certificado_p12(*certificados["luis"])

    # Un PDF distinto se rechaza aunque venga firmado
    otro = firmar_pdf(pdf_con_texto(["Otro documento"]), luis, motivo="x", nombre_campo="Otra", caja=None)
    r = cliente.post(f"{base}/firma/externa", headers=freelancer, files={"archivo": ("otro.pdf", otro, "application/pdf")})
    assert r.status_code == 422
    assert "no corresponde" in r.json()["detail"]

    # El PDF vigente sin firmas nuevas también se rechaza
    r = cliente.post(f"{base}/firma/externa", headers=freelancer, files={"archivo": ("mismo.pdf", vigente, "application/pdf")})
    assert r.status_code == 422
    assert "no tiene firmas nuevas" in r.json()["detail"]

    # La otra parte firma el PDF descargado (como lo haría FirmaEC: actualización incremental)
    firmado = firmar_pdf(vigente, luis, motivo="Firmado con FirmaEC", nombre_campo="FirmaEC", caja=caja_firma(2))
    r = cliente.post(f"{base}/firma/externa", headers=freelancer,
                     files={"archivo": ("firmado.pdf", firmado, "application/pdf")})
    assert r.status_code == 200, r.text
    documento = r.json()
    assert documento["estado_firma"] == "FIRMADO_COMPLETO"
    externa = documento["firmas"][1]
    assert externa["titular"] == "LUIS TORRES" and not externa["en_plataforma"] and externa["es_integra"]


def test_confianza_con_la_raiz_cargada(cliente, db, freelancer, llm_falso, certificados):
    base, _ = _preparar(cliente, db, freelancer, llm_falso)
    _firmar(cliente, base, freelancer, certificados["ana"])
    carpeta = Path(settings.directorio_confianza)
    carpeta.mkdir(parents=True, exist_ok=True)
    shutil.copy(certificados["carpeta"] / "ca_prueba.crt", carpeta / "ca_prueba.crt")
    try:
        documento = cliente.post(f"{base}/firma/verificar", headers=freelancer).json()
        assert documento["raices_confianza"] == 1
        assert documento["firmas"][0]["es_confiable"] is True
    finally:
        shutil.rmtree(carpeta)


def test_manipular_el_pdf_invalida_las_firmas(cliente, db, freelancer, llm_falso, certificados):
    base, _ = _preparar(cliente, db, freelancer, llm_falso)
    _firmar(cliente, base, freelancer, certificados["ana"])
    documento = db.scalar(select(DocumentoFirma).where(DocumentoFirma.estado == "A")
                          .order_by(DocumentoFirma.id_documento_firma.desc()))
    ruta = Path(documento.ruta_archivo)
    datos = bytearray(ruta.read_bytes())
    datos[len(datos) // 4] ^= 0x01
    ruta.write_bytes(bytes(datos))

    verificado = cliente.post(f"{base}/firma/verificar", headers=freelancer).json()
    assert verificado["estado_firma"] == "INVALIDO"
    assert not verificado["firmas"][0]["es_integra"]
    assert _firmar(cliente, base, freelancer, certificados["luis"]).status_code == 422


def test_nueva_version_reemplaza_a_la_anterior(cliente, db, freelancer, llm_falso):
    base, primera = _preparar(cliente, db, freelancer, llm_falso)
    r = cliente.post(f"{base}/firma", headers=freelancer,
                     files={"archivo": ("final_v2.pdf", pdf_con_texto(TEXTO_FINAL + ["Cambio"]), "application/pdf")})
    assert r.status_code == 201
    assert r.json()["numero_version"] == primera["numero_version"] + 1
    assert cliente.get(f"{base}/firma", headers=freelancer).json()["nombre_archivo"] == "final_v2.pdf"