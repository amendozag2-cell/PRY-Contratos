"""Recorta una ley en PDF a los artículos que se cargarán en el corpus legal.

Uso (desde la carpeta backend):
    uv run python recortar_ley.py <ley.pdf> <salida.txt> --rango 1453-1590 [--rango 1937-1950]

- Extrae el texto exacto del PDF oficial (no reescribe nada).
- Quita encabezados y pies de página que se repiten en casi todas las páginas.
- Conserva solo los artículos de los rangos pedidos, con su formato "Art. N.-",
  que es el que usa el fragmentador para llenar articulo_referencia.
- Sin --rango, guarda el texto completo limpio (útil para ver la numeración).
"""

import argparse
import re
import sys
from collections import Counter
from pathlib import Path

# "Art. 8.-", "Art. 8.- ", "Artículo 8.-", "Art. 1561.-", "ART. 47.-"
INICIO_ARTICULO = re.compile(r"^\s*Art(?:[íi]culo|\.)\s*(\d+)\s*\.?\s*[-–—]", re.IGNORECASE)
DIGITOS = re.compile(r"\d+")
SOLO_NUMERO = re.compile(r"^\s*(P[áa]g(ina)?\.?\s*)?\d+(\s*(de|/)\s*\d+)?\s*$", re.IGNORECASE)


def leer_paginas(pdf: Path) -> list[list[str]]:
    import fitz  # PyMuPDF, ya instalado en el backend como "pymupdf"

    with fitz.open(pdf) as documento:
        return [pagina.get_text("text").splitlines() for pagina in documento]


def limpiar(paginas: list[list[str]]) -> list[str]:
    """Une las páginas quitando números de página y líneas repetidas en la mayoría de páginas."""
    def clave(linea: str) -> str:
        # "CÓDIGO CIVIL - Página 12" y "CÓDIGO CIVIL - Página 13" cuentan como la misma línea
        return DIGITOS.sub("#", linea.strip())

    conteo = Counter(
        c for lineas in paginas for c in {clave(linea) for linea in lineas if linea.strip()}
    )
    umbral = max(3, int(len(paginas) * 0.5))
    repetidas = {texto for texto, veces in conteo.items() if veces >= umbral}

    resultado: list[str] = []
    for lineas in paginas:
        for linea in lineas:
            texto = linea.rstrip()
            if not texto.strip() or clave(texto) in repetidas or SOLO_NUMERO.match(texto):
                continue
            resultado.append(texto)
    return resultado


def recortar(lineas: list[str], rangos: list[tuple[int, int]]) -> list[str]:
    """Devuelve solo las líneas de los artículos cuyos números caen en algún rango.

    Un artículo empieza en una línea "Art. N.-" y termina donde empieza el siguiente.
    Solo se acepta un inicio si su número no es menor que el del artículo anterior,
    para no confundir con referencias como "Art. 8.- del Código Civil" al inicio de línea.
    """
    salida: list[str] = []
    incluir = False
    ultimo = 0
    for linea in lineas:
        coincidencia = INICIO_ARTICULO.match(linea)
        if coincidencia:
            numero = int(coincidencia.group(1))
            if numero >= ultimo:
                ultimo = numero
                incluir = any(desde <= numero <= hasta for desde, hasta in rangos)
                if incluir and salida:
                    salida.append("")  # línea en blanco entre artículos
        if incluir:
            salida.append(linea)
    return salida


def leer_rango(texto: str) -> tuple[int, int]:
    partes = texto.split("-")
    if len(partes) == 1:
        numero = int(partes[0])
        return numero, numero
    desde, hasta = int(partes[0]), int(partes[1])
    if desde > hasta:
        raise argparse.ArgumentTypeError(f"Rango inválido: {texto}")
    return desde, hasta


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("pdf", type=Path)
    parser.add_argument("salida", type=Path)
    parser.add_argument("--rango", type=leer_rango, action="append", default=[],
                        help="Artículos a conservar, ej. 1453-1590 o 8. Se puede repetir.")
    args = parser.parse_args()

    if not args.pdf.exists():
        sys.exit(f"No existe el archivo {args.pdf}")
    lineas = limpiar(leer_paginas(args.pdf))
    if args.rango:
        lineas = recortar(lineas, args.rango)
        if not lineas:
            sys.exit("No se encontró ningún artículo en esos rangos. Revise la numeración "
                     "ejecutando el script sin --rango y abriendo el .txt completo.")

    args.salida.write_text("\n".join(lineas) + "\n", encoding="utf-8")
    articulos = sum(1 for linea in lineas if INICIO_ARTICULO.match(linea))
    print(f"Guardado {args.salida} — {articulos} artículos, {len(lineas)} líneas")


if __name__ == "__main__":
    main()