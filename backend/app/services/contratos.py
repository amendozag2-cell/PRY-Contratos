"""Carga de contratos: lectura, OCR, segmentación en cláusulas y registro."""

import hashlib
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
    ACC_CARGA_CONTRATO,
    CAT_ESTADO_ANALISIS,
    EST_CARGADO,
    PAR_MAX_PAGINAS,
)
from app.models import ESTADO_ACTIVO, Clausula, Contrato, Usuario
from app.services.auditoria import registrar_evento
from app.services.catalogos import obtener_id_detalle
from app.services.extraccion import ErrorExtraccion
from app.services.parametros import obtener_entero
from app.services.procesamiento_pdf import leer_contrato
from app.services.segmentacion import segmentar


class ContratoDuplicado(Exception):
    def __init__(self, id_contrato: int):
        super().__init__("Ya cargaste este mismo archivo anteriormente")
        self.id_contrato = id_contrato


@dataclass
class ResultadoCargaContrato:
    contrato: Contrato
    clausulas: int
    paginas_ocr: list[int]
    milisegundos: int


def cargar_contrato(
    db: Session,
    request: Request,
    usuario: Usuario,
    *,
    contenido: bytes,
    nombre_archivo: str,
    id_tipo_contrato: int | None,
) -> ResultadoCargaContrato:
    inicio = time.perf_counter()
    hash_archivo = hashlib.sha256(contenido).hexdigest()

    existente = db.scalar(
        select(Contrato.id_contrato).where(
            Contrato.id_usuario == usuario.id_usuario,
            Contrato.hash_archivo == hash_archivo,
            Contrato.estado == ESTADO_ACTIVO,
        )
    )
    if existente:
        raise ContratoDuplicado(existente)

    max_paginas = obtener_entero(db, PAR_MAX_PAGINAS, 15)
    lectura = leer_contrato(contenido, max_paginas)
    clausulas = segmentar(lectura.lineas)
    if not clausulas:
        raise ErrorExtraccion("No se encontró texto legible en el contrato")

    carpeta = Path(settings.directorio_archivos) / "contratos"
    carpeta.mkdir(parents=True, exist_ok=True)
    ruta = carpeta / f"{uuid.uuid4().hex}.pdf"
    ruta.write_bytes(contenido)

    try:
        contrato = Contrato(
            id_usuario=usuario.id_usuario,
            id_tipo_contrato=id_tipo_contrato,
            id_estado_analisis=obtener_id_detalle(db, CAT_ESTADO_ANALISIS, EST_CARGADO),
            nombre_archivo=nombre_archivo[:255],
            ruta_archivo=ruta.as_posix(),
            hash_archivo=hash_archivo,
            numero_paginas=lectura.numero_paginas,
            es_escaneado=lectura.es_escaneado,
            usuario_creacion=usuario.id_usuario,
        )
        db.add(contrato)
        db.flush()

        db.add_all(
            Clausula(
                id_contrato=contrato.id_contrato,
                numero_orden=c.numero_orden,
                titulo=c.titulo,
                contenido=c.contenido,
                numero_pagina=c.numero_pagina,
                coordenadas=c.coordenadas,
                usuario_creacion=usuario.id_usuario,
            )
            for c in clausulas
        )

        milisegundos = round((time.perf_counter() - inicio) * 1000)
        registrar_evento(
            db, request, ACC_CARGA_CONTRATO,
            usuario=usuario,
            tabla_afectada="con_contrato",
            id_registro=contrato.id_contrato,
            datos_nuevos={
                "archivo": nombre_archivo,
                "paginas": lectura.numero_paginas,
                "paginas_ocr": len(lectura.paginas_ocr),
                "clausulas": len(clausulas),
                "tiempo_ms": milisegundos,
            },
        )
        db.commit()
    except Exception:
        db.rollback()
        ruta.unlink(missing_ok=True)
        raise

    db.refresh(contrato)
    return ResultadoCargaContrato(
        contrato=contrato,
        clausulas=len(clausulas),
        paginas_ocr=lectura.paginas_ocr,
        milisegundos=milisegundos,
    )


def inactivar_contrato(contrato: Contrato, usuario: Usuario) -> None:
    contrato.estado = "I"
    contrato.usuario_modificacion = usuario.id_usuario
    contrato.fecha_modificacion = datetime.now(timezone.utc)