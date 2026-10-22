"""Segmentación de un contrato en cláusulas con sus coordenadas en el PDF.

Recibe las líneas de texto extraídas (con página, bloque y rectángulo) y las
agrupa en cláusulas. Una cláusula empieza en una línea de encabezado como
"PRIMERA.- OBJETO", "CLÁUSULA SEGUNDA", "3. FORMA DE PAGO" o "Artículo 4".
Si el contrato no tiene encabezados reconocibles, se agrupan los párrafos.

Las coordenadas se guardan normalizadas entre 0 y 1 respecto al tamaño de la
página, un rectángulo por párrafo, para dibujar el resaltado en el visor.
"""

import re
from dataclasses import dataclass, field

_ORDINAL = (
    r"primera|segunda|tercera|cuarta|quinta|sexta|s[ée]ptima|octava|novena"
    r"|und[ée]cima|duod[ée]cima"
    r"|(?:d[ée]cima|vig[ée]sima)(?:[ \t]*(?:primera|segunda|tercera|cuarta|quinta|sexta"
    r"|s[ée]ptima|octava|novena))?"
)
_MAYUSCULA = "A-ZÁÉÍÓÚÑÜ"

PATRON_ENCABEZADO = re.compile(
    rf"^\s*(?:"
    rf"(?i:cl[áa]usula)\s+(?:(?i:{_ORDINAL})|\d{{1,2}}|[IVXLC]{{1,6}})\b"  # CLÁUSULA PRIMERA / 1 / I
    rf"|(?i:{_ORDINAL})\s*(?:\.-|\.–|[.:\-–])"                            # PRIMERA.- / Segunda:
    rf"|\d{{1,2}}(?:\.\d{{1,2}})?\s*(?:\.-|[.)\-–])\s*[{_MAYUSCULA}]{{2}}[{_MAYUSCULA} ,]+"  # 3. FORMA DE PAGO
    rf"|(?i:art[íi]culo)\s+\d+"                                           # Artículo 4
    rf")"
)
PATRON_RUIDO = re.compile(r"^(?i:p[áa]g(?:ina)?\.?\s*)?\d{1,3}(?:\s*(?:de|/)\s*\d{1,3})?$")

MINIMO_ENCABEZADOS = 2
LONGITUD_MINIMA = 20
LONGITUD_PARRAFOS = 500  # agrupación de párrafos cuando no hay encabezados


@dataclass
class Linea:
    pagina: int
    bloque: int
    texto: str
    x0: float
    y0: float
    x1: float
    y1: float


@dataclass
class Clausula:
    numero_orden: int
    titulo: str | None
    contenido: str
    numero_pagina: int
    coordenadas: list[dict] = field(default_factory=list)


def es_encabezado(texto: str) -> bool:
    return bool(PATRON_ENCABEZADO.match(texto))


def _unir_texto(lineas: list[Linea]) -> str:
    """Une líneas: espacio dentro de un párrafo, salto de línea entre párrafos."""
    partes: list[str] = []
    anterior: tuple[int, int] | None = None
    for linea in lineas:
        clave = (linea.pagina, linea.bloque)
        texto = linea.texto.strip()
        if not partes:
            partes.append(texto)
        elif clave != anterior:
            partes.append("\n" + texto)
        elif partes[-1].endswith("-") and texto[:1].islower():
            partes[-1] = partes[-1][:-1]  # palabra cortada al final de la línea
            partes.append(texto)
        else:
            partes.append(" " + texto)
        anterior = clave
    return re.sub(r"[ \t]+", " ", "".join(partes)).strip()


def _coordenadas(lineas: list[Linea]) -> list[dict]:
    """Un rectángulo por párrafo (bloque), unión de las líneas que lo forman."""
    rectangulos: dict[tuple[int, int], list[float]] = {}
    for l in lineas:
        clave = (l.pagina, l.bloque)
        if clave not in rectangulos:
            rectangulos[clave] = [l.x0, l.y0, l.x1, l.y1]
        else:
            r = rectangulos[clave]
            r[0], r[1] = min(r[0], l.x0), min(r[1], l.y0)
            r[2], r[3] = max(r[2], l.x1), max(r[3], l.y1)
    return [
        {"pagina": p, "x0": round(r[0], 4), "y0": round(r[1], 4), "x1": round(r[2], 4), "y1": round(r[3], 4)}
        for (p, _), r in rectangulos.items()
    ]


def _crear(grupos: list[tuple[str | None, list[Linea]]]) -> list[Clausula]:
    clausulas: list[Clausula] = []
    for titulo, lineas in grupos:
        contenido = _unir_texto(lineas)
        if len(contenido) < LONGITUD_MINIMA:
            continue
        clausulas.append(
            Clausula(
                numero_orden=len(clausulas) + 1,
                titulo=titulo[:255] if titulo else None,
                contenido=contenido,
                numero_pagina=lineas[0].pagina,
                coordenadas=_coordenadas(lineas),
            )
        )
    return clausulas


def segmentar(lineas: list[Linea]) -> list[Clausula]:
    utiles = [l for l in lineas if l.texto.strip() and not PATRON_RUIDO.match(l.texto.strip())]
    encabezados = sum(1 for l in utiles if es_encabezado(l.texto))

    grupos: list[tuple[str | None, list[Linea]]] = []
    if encabezados >= MINIMO_ENCABEZADOS:
        for linea in utiles:
            if es_encabezado(linea.texto) or not grupos:
                titulo = linea.texto.strip() if es_encabezado(linea.texto) else None
                grupos.append((titulo, [linea]))
            else:
                grupos[-1][1].append(linea)
    else:
        # Sin encabezados: se agrupan párrafos completos hasta ~LONGITUD_PARRAFOS caracteres
        actual: list[Linea] = []
        for linea in utiles:
            cambia_parrafo = actual and (linea.pagina, linea.bloque) != (actual[-1].pagina, actual[-1].bloque)
            if cambia_parrafo and len(_unir_texto(actual)) >= LONGITUD_PARRAFOS:
                grupos.append((None, actual))
                actual = []
            actual.append(linea)
        if actual:
            grupos.append((None, actual))

    return _crear(grupos)