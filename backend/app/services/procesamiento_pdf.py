"""Lectura de contratos PDF: texto por línea con coordenadas y OCR en páginas escaneadas."""

import os
from dataclasses import dataclass, field
from pathlib import Path

import pymupdf

from app.config import settings
from app.services.extraccion import ErrorExtraccion
from app.services.segmentacion import Linea

CARACTERES_MINIMOS_PAGINA = 25  # menos texto que esto: la página se trata como escaneada
RUTA_TESSDATA_WINDOWS = r"C:\Program Files\Tesseract-OCR\tessdata"


@dataclass
class ResultadoLectura:
    numero_paginas: int
    lineas: list[Linea] = field(default_factory=list)
    paginas_ocr: list[int] = field(default_factory=list)

    @property
    def es_escaneado(self) -> bool:
        return bool(self.paginas_ocr)


def _carpeta_tessdata() -> str | None:
    for ruta in (settings.tessdata_prefix, os.environ.get("TESSDATA_PREFIX"), RUTA_TESSDATA_WINDOWS):
        if ruta and Path(ruta).is_dir():
            return ruta
    return None


def _contar_caracteres(datos: dict) -> int:
    return sum(
        len(span["text"].strip())
        for bloque in datos["blocks"] if bloque.get("type") == 0
        for linea in bloque["lines"]
        for span in linea["spans"]
    )


def _texto_ocr(pagina: pymupdf.Page) -> dict:
    tessdata = _carpeta_tessdata()
    if tessdata is None:
        raise ErrorExtraccion(
            "El contrato está escaneado y no se encontró Tesseract. Instálelo con el idioma "
            "español y configure TESSDATA_PREFIX en el archivo .env"
        )
    os.environ["TESSDATA_PREFIX"] = tessdata
    try:
        textpage = pagina.get_textpage_ocr(
            language=settings.idioma_ocr, dpi=settings.dpi_ocr, full=True, tessdata=tessdata
        )
    except Exception as error:
        raise ErrorExtraccion(
            f"No se pudo aplicar OCR a la página {pagina.number + 1}. Verifique que Tesseract "
            f"tenga instalado el idioma '{settings.idioma_ocr}'"
        ) from error
    return pagina.get_text("dict", textpage=textpage, sort=True)


def _limitar(valor: float) -> float:
    return min(max(valor, 0.0), 1.0)


def leer_contrato(contenido: bytes, max_paginas: int) -> ResultadoLectura:
    try:
        documento = pymupdf.open(stream=contenido, filetype="pdf")
    except Exception as error:
        raise ErrorExtraccion("No se pudo abrir el archivo. Verifique que sea un PDF válido") from error

    with documento:
        if documento.needs_pass:
            raise ErrorExtraccion("El PDF está protegido con contraseña")
        total = documento.page_count
        if total == 0:
            raise ErrorExtraccion("El PDF no tiene páginas")
        if total > max_paginas:
            raise ErrorExtraccion(
                f"El contrato tiene {total} páginas y el máximo permitido es {max_paginas}"
            )

        resultado = ResultadoLectura(numero_paginas=total)
        for numero, pagina in enumerate(documento, start=1):
            datos = pagina.get_text("dict", sort=True)
            if _contar_caracteres(datos) < CARACTERES_MINIMOS_PAGINA:
                if not pagina.get_images():
                    continue  # página en blanco
                datos = _texto_ocr(pagina)
                resultado.paginas_ocr.append(numero)

            ancho, alto = pagina.rect.width, pagina.rect.height
            for indice, bloque in enumerate(datos["blocks"]):
                if bloque.get("type") != 0:
                    continue
                for linea in bloque["lines"]:
                    texto = "".join(span["text"] for span in linea["spans"]).strip()
                    if not texto:
                        continue
                    x0, y0, x1, y1 = linea["bbox"]
                    resultado.lineas.append(
                        Linea(
                            pagina=numero,
                            bloque=indice,
                            texto=texto,
                            x0=_limitar(x0 / ancho),
                            y0=_limitar(y0 / alto),
                            x1=_limitar(x1 / ancho),
                            y1=_limitar(y1 / alto),
                        )
                    )
    return resultado


def renderizar_pagina(ruta: str, numero_pagina: int, ancho: int) -> bytes:
    """Imagen PNG de una página, para la vista previa con coordenadas."""
    with pymupdf.open(ruta) as documento:
        if not 1 <= numero_pagina <= documento.page_count:
            raise ErrorExtraccion("La página solicitada no existe")
        pagina = documento[numero_pagina - 1]
        zoom = ancho / pagina.rect.width
        return pagina.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=False).tobytes("png")