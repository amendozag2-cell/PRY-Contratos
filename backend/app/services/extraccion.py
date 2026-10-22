"""Extracción de texto de los documentos del corpus legal (PDF con texto o TXT)."""

import re

import pymupdf

LONGITUD_MINIMA = 200


class ErrorExtraccion(Exception):
    """El archivo no se pudo leer o no contiene texto utilizable."""


def normalizar(texto: str) -> str:
    texto = texto.replace("\r\n", "\n").replace("\r", "\n").replace("\u00a0", " ")
    texto = re.sub(r"(\w)-\n(\w)", r"\1\2", texto)  # palabras cortadas al final de línea
    texto = re.sub(r"[ \t]+", " ", texto)
    texto = re.sub(r" *\n *", "\n", texto)
    texto = re.sub(r"\n{3,}", "\n\n", texto)
    return texto.strip()


def extraer_texto(contenido: bytes, extension: str) -> str:
    if extension == ".pdf":
        try:
            with pymupdf.open(stream=contenido, filetype="pdf") as documento:
                if documento.needs_pass:
                    raise ErrorExtraccion("El PDF está protegido con contraseña")
                texto = "\n".join(pagina.get_text("text", sort=True) for pagina in documento)
        except ErrorExtraccion:
            raise
        except Exception as error:
            raise ErrorExtraccion("No se pudo leer el PDF. Verifique que el archivo no esté dañado") from error
    else:
        try:
            texto = contenido.decode("utf-8")
        except UnicodeDecodeError:
            texto = contenido.decode("latin-1")

    texto = normalizar(texto)
    if len(texto) < LONGITUD_MINIMA:
        raise ErrorExtraccion(
            "El documento no contiene texto suficiente. Si es un PDF escaneado, "
            "use una versión con texto seleccionable"
        )
    return texto