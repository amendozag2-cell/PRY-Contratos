"""Fragmentación (chunking) de documentos legales para el pipeline RAG.

Estrategia:
1. Si el texto tiene estructura de articulado (al menos 3 encabezados del tipo
   "Art. 1561.-" o "Artículo 12."), cada artículo es un fragmento. Así cada
   fragmento recuperado se puede citar con su número de artículo.
2. Los artículos más largos que el tamaño configurado, el preámbulo y los
   documentos sin articulado (guías de buenas prácticas) se dividen con el
   RecursiveCharacterTextSplitter de LangChain, que corta preferentemente por
   párrafos, luego por líneas y luego por oraciones.
"""

import re
from dataclasses import dataclass

from langchain_text_splitters import RecursiveCharacterTextSplitter

_NUMERO = r"\d+(?:\.\d+)?(?:[ \t]*(?:bis|ter|quater|BIS|TER|QUATER))?"

# Encabezado de artículo al inicio de una línea. Dos formas:
#  - "Art. 1561.-", "ART. 8:", "Artículo 12." -> número seguido de puntuación o fin de línea
#  - "Artículo 8 Contrato individual"         -> palabra completa con mayúscula inicial
# Una cita como "...conforme al Art. 1561 de este Código" no se toma como encabezado.
PATRON_ARTICULO = re.compile(
    rf"^[ \t]*(?:"
    rf"(?:Art|ART)(?:[íi]culo|ÍCULO|ICULO|\.)?[ \t]*(?P<n1>{_NUMERO})(?=[ \t]*(?:\.-|\.–|[.:\-–]|$))"
    rf"|(?:Art[íi]culo|ART[ÍI]CULO)[ \t]+(?P<n2>{_NUMERO})\b"
    rf")",
    re.MULTILINE,
)
MINIMO_ARTICULOS = 3
LONGITUD_MINIMA_FRAGMENTO = 30


@dataclass
class Fragmento:
    numero_orden: int
    articulo_referencia: str | None
    contenido: str


def _crear_divisor(tamanio: int, solapamiento: int) -> RecursiveCharacterTextSplitter:
    return RecursiveCharacterTextSplitter(
        chunk_size=tamanio,
        chunk_overlap=min(solapamiento, tamanio // 2),
        separators=["\n\n", "\n", ". ", "; ", ", ", " ", ""],
    )


def _referencia(numero: str) -> str:
    return "Art. " + re.sub(r"\s+", " ", numero).strip().lower()


def contar_articulos(texto: str) -> int:
    return len(PATRON_ARTICULO.findall(texto))


def fragmentar(texto: str, tamanio: int, solapamiento: int) -> list[Fragmento]:
    divisor = _crear_divisor(tamanio, solapamiento)
    coincidencias = list(PATRON_ARTICULO.finditer(texto))
    piezas: list[tuple[str | None, str]] = []

    if len(coincidencias) >= MINIMO_ARTICULOS:
        preambulo = texto[: coincidencias[0].start()]
        piezas.extend((None, parte) for parte in divisor.split_text(preambulo))

        for i, coincidencia in enumerate(coincidencias):
            fin = coincidencias[i + 1].start() if i + 1 < len(coincidencias) else len(texto)
            bloque = texto[coincidencia.start():fin].strip()
            referencia = _referencia(coincidencia.group("n1") or coincidencia.group("n2"))
            partes = divisor.split_text(bloque) if len(bloque) > tamanio else [bloque]
            piezas.extend((referencia, parte) for parte in partes)
    else:
        piezas.extend((None, parte) for parte in divisor.split_text(texto))

    utiles = [(ref, c.strip()) for ref, c in piezas if len(c.strip()) >= LONGITUD_MINIMA_FRAGMENTO]
    return [
        Fragmento(numero_orden=i, articulo_referencia=ref, contenido=contenido)
        for i, (ref, contenido) in enumerate(utiles, start=1)
    ]