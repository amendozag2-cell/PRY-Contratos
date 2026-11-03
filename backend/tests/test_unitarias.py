"""Pruebas unitarias: funciones puras, sin base de datos ni API."""

from datetime import datetime, timezone

import pytest

from app.security import crear_token, decodificar_token, hash_clave, verificar_clave
from app.services.analisis import _calcular_puntaje
from app.services.firma_pdf import caja_firma, cobertura_texto
from app.services.fragmentacion import contar_articulos, fragmentar
from app.services.segmentacion import Linea, es_encabezado, segmentar


# --------------------------------------------------------------- seguridad
def test_clave_se_guarda_cifrada_y_se_verifica():
    cifrada = hash_clave("MiClave2026")
    assert cifrada != "MiClave2026"
    assert verificar_clave("MiClave2026", cifrada)
    assert not verificar_clave("otra", cifrada)


def test_token_jwt_contiene_usuario_y_rol():
    datos = decodificar_token(crear_token(7, "FREELANCER", 5))
    assert str(datos["sub"]) == "7"
    assert datos["rol"] == "FREELANCER"


# ----------------------------------------------------------- segmentación
@pytest.mark.parametrize("texto", [
    "PRIMERA.- OBJETO", "CLÁUSULA SEGUNDA: PAGO", "Cláusula 3", "3. FORMA DE PAGO", "Artículo 4", "DÉCIMA PRIMERA.- PLAZO",
])
def test_reconoce_encabezados_de_clausula(texto):
    assert es_encabezado(texto)


@pytest.mark.parametrize("texto", [
    "El contratante pagará la primera cuota.", "Página 2 de 5", "conforme al artículo anterior",
])
def test_no_confunde_texto_comun_con_encabezado(texto):
    assert not es_encabezado(texto)


def _lineas(textos: list[str]) -> list[Linea]:
    return [Linea(pagina=1, bloque=i, texto=t, x0=50, y0=50 + i * 20, x1=500, y1=65 + i * 20)
            for i, t in enumerate(textos)]


def test_segmenta_por_clausulas_y_descarta_numeros_de_pagina():
    clausulas = segmentar(_lineas([
        "CONTRATO DE PRESTACIÓN DE SERVICIOS PROFESIONALES",
        "PRIMERA.- OBJETO: El prestador desarrollará un sitio web.",
        "El sitio tendrá cinco secciones.",
        "SEGUNDA.- PAGO: El contratante pagará 500 dólares.",
        "1",
        "TERCERA.- PLAZO: El trabajo se entregará en 30 días.",
    ]))
    assert [c.titulo for c in clausulas] == [
        None,
        "PRIMERA.- OBJETO: El prestador desarrollará un sitio web.",
        "SEGUNDA.- PAGO: El contratante pagará 500 dólares.",
        "TERCERA.- PLAZO: El trabajo se entregará en 30 días.",
    ]
    assert "cinco secciones" in clausulas[1].contenido
    assert all(c.numero_orden == i for i, c in enumerate(clausulas, start=1))
    assert all(0 <= r["x0"] <= r["x1"] for c in clausulas for r in c.coordenadas)


# ----------------------------------------------------------- fragmentación
LEY = """CÓDIGO CIVIL - LIBRO IV
Art. 1561.- Todo contrato legalmente celebrado es ley para los contratantes.
Art. 1562.- Los contratos deben ejecutarse de buena fe.
Art. 1563.- Conocida claramente la intención de los contratantes, debe estarse a ella más que a lo literal de las palabras.
"""


def test_fragmenta_por_articulo_y_conserva_la_referencia():
    assert contar_articulos(LEY) == 3
    fragmentos = fragmentar(LEY, tamanio=1000, solapamiento=100)
    referencias = [f.articulo_referencia for f in fragmentos]
    assert referencias == ["Art. 1561", "Art. 1562", "Art. 1563"]
    assert fragmentos[1].contenido.startswith("Art. 1562")


def test_una_cita_dentro_del_texto_no_es_un_articulo_nuevo():
    texto = "Art. 1.- Primero.\nArt. 2.- Segundo, conforme al Art. 1 de este código.\nArt. 3.- Tercero."
    assert contar_articulos(texto) == 3


# ---------------------------------------------------------------- análisis
def test_puntaje_global_es_el_promedio_de_los_pesos():
    assert _calcular_puntaje([100, 50, 0, 0]) == 37.5
    assert _calcular_puntaje([]) == 0.0


# ------------------------------------------------------------------- firma
def test_cajas_de_firma_no_se_superponen():
    cajas = [caja_firma(n) for n in range(1, 13)]
    for i, a in enumerate(cajas):
        for b in cajas[i + 1:]:
            separadas = a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1]
            assert separadas, (a, b)
    assert caja_firma(13) is None


def test_cobertura_del_texto_acordado():
    documento = "QUINTA.- PAGO. El contratante pagará al prestador dentro de los\n30 días siguientes a la entrega."
    assert cobertura_texto("El CONTRATANTE pagará al PRESTADOR dentro de los 30 días siguientes a la entrega.", documento) == 1.0
    assert cobertura_texto("El contratante podrá terminar el contrato sin preaviso alguno.", documento) < 0.5


def test_fechas_de_certificado_se_leen_en_utc(certificados):
    from app.services.firma_pdf import leer_certificado_p12

    contenido, clave = certificados["ana"]
    cargado = leer_certificado_p12(contenido, clave)
    assert cargado.datos.nombre_titular == "ANA PÉREZ ÑÁÑEZ"
    assert cargado.datos.identificacion_titular == "0912345678"
    assert cargado.datos.fecha_fin_vigencia > datetime.now(timezone.utc)
    