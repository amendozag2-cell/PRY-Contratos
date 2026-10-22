from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, Query, Request, Response, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.orm import aliased

from app.config import settings
from app.constantes import ACC_CARGA_CONTRATO, ACC_INACTIVACION_CONTRATO, CAT_TIPO_CONTRATO, FALLO
from app.deps import DbSession, UsuarioActual
from app.models import ESTADO_ACTIVO, CatalogoDetalle, Clausula, Contrato, Usuario
from app.schemas import (
    CargaContratoSalida,
    ClausulaSalida,
    ContratoDetalle,
    ContratoSalida,
    OpcionCatalogo,
)
from app.services.auditoria import registrar_evento
from app.services.catalogos import listar_detalles, obtener_id_detalle
from app.services.contratos import ContratoDuplicado, cargar_contrato, inactivar_contrato
from app.services.extraccion import ErrorExtraccion
from app.services.procesamiento_pdf import renderizar_pagina

router = APIRouter(prefix="/contratos", tags=["Contratos"])

FIRMA_PDF = b"%PDF"


def _consulta_contratos():
    """Contratos con su estado de análisis, tipo y número de cláusulas."""
    estado = aliased(CatalogoDetalle)
    tipo = aliased(CatalogoDetalle)
    clausulas = (
        select(Clausula.id_contrato, func.count().label("total"))
        .where(Clausula.estado == ESTADO_ACTIVO)
        .group_by(Clausula.id_contrato)
        .subquery()
    )
    return select(
        Contrato, estado.codigo, tipo.nombre, func.coalesce(clausulas.c.total, 0)
    ).join(
        estado, estado.id_catalogo_detalle == Contrato.id_estado_analisis
    ).outerjoin(
        tipo, tipo.id_catalogo_detalle == Contrato.id_tipo_contrato
    ).outerjoin(
        clausulas, clausulas.c.id_contrato == Contrato.id_contrato
    )


def _salida(fila) -> ContratoSalida:
    c, estado, tipo, total = fila
    return ContratoSalida(
        id_contrato=c.id_contrato,
        nombre_archivo=c.nombre_archivo,
        tipo_contrato=tipo,
        numero_paginas=c.numero_paginas,
        numero_clausulas=total,
        es_escaneado=c.es_escaneado,
        estado_analisis=estado,
        puntaje_riesgo_global=c.puntaje_riesgo_global,
        fecha_creacion=c.fecha_creacion,
    )


def _obtener_propio(db, id_contrato: int, usuario: Usuario):
    fila = db.execute(
        _consulta_contratos().where(
            Contrato.id_contrato == id_contrato,
            Contrato.id_usuario == usuario.id_usuario,
            Contrato.estado == ESTADO_ACTIVO,
        )
    ).first()
    if fila is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Contrato no encontrado")
    return fila


@router.get("/tipos", response_model=list[OpcionCatalogo])
def tipos_de_contrato(db: DbSession, _: UsuarioActual):
    return [OpcionCatalogo(codigo=d.codigo, nombre=d.nombre) for d in listar_detalles(db, CAT_TIPO_CONTRATO)]


@router.get("", response_model=list[ContratoSalida])
def listar_mis_contratos(usuario: UsuarioActual, db: DbSession):
    filas = db.execute(
        _consulta_contratos()
        .where(Contrato.id_usuario == usuario.id_usuario, Contrato.estado == ESTADO_ACTIVO)
        .order_by(Contrato.fecha_creacion.desc())
    ).all()
    return [_salida(f) for f in filas]


@router.post("", response_model=CargaContratoSalida, status_code=status.HTTP_201_CREATED)
def cargar(
    request: Request,
    db: DbSession,
    usuario: UsuarioActual,
    archivo: Annotated[UploadFile, File(description="Contrato en PDF (digital o escaneado)")],
    tipo_contrato: Annotated[str | None, Form(description="Código del catálogo TIPO_CONTRATO")] = None,
):
    nombre_archivo = archivo.filename or "contrato.pdf"
    limite = settings.max_mb_contrato * 1024 * 1024
    contenido = archivo.file.read(limite + 1)
    if len(contenido) > limite:
        raise HTTPException(
            status.HTTP_413_CONTENT_TOO_LARGE,
            f"El archivo supera el máximo de {settings.max_mb_contrato} MB",
        )
    if not contenido.startswith(FIRMA_PDF):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "El archivo debe ser un PDF")

    id_tipo = None
    if tipo_contrato:
        try:
            id_tipo = obtener_id_detalle(db, CAT_TIPO_CONTRATO, tipo_contrato)
        except ValueError:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "El tipo de contrato no es válido")

    try:
        resultado = cargar_contrato(
            db, request, usuario,
            contenido=contenido,
            nombre_archivo=nombre_archivo,
            id_tipo_contrato=id_tipo,
        )
    except ContratoDuplicado as error:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            {"mensaje": str(error), "id_contrato": error.id_contrato},
        )
    except ErrorExtraccion as error:
        db.rollback()
        registrar_evento(
            db, request, ACC_CARGA_CONTRATO,
            usuario=usuario, resultado=FALLO, observacion=str(error)[:255],
            datos_nuevos={"archivo": nombre_archivo},
        )
        db.commit()
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error))

    fila = _obtener_propio(db, resultado.contrato.id_contrato, usuario)
    return CargaContratoSalida(
        contrato=_salida(fila),
        paginas_ocr=resultado.paginas_ocr,
        tiempo_ms=resultado.milisegundos,
    )


@router.get("/{id_contrato}", response_model=ContratoDetalle)
def detalle(id_contrato: int, db: DbSession, usuario: UsuarioActual):
    fila = _obtener_propio(db, id_contrato, usuario)
    clausulas = db.scalars(
        select(Clausula)
        .where(Clausula.id_contrato == id_contrato, Clausula.estado == ESTADO_ACTIVO)
        .order_by(Clausula.numero_orden)
    ).all()
    return ContratoDetalle(
        **_salida(fila).model_dump(),
        clausulas=[ClausulaSalida.model_validate(c) for c in clausulas],
    )


@router.get("/{id_contrato}/paginas/{numero_pagina}/imagen")
def imagen_de_pagina(
    id_contrato: int,
    numero_pagina: int,
    db: DbSession,
    usuario: UsuarioActual,
    ancho: int = Query(900, ge=200, le=2000),
):
    contrato = _obtener_propio(db, id_contrato, usuario)[0]
    try:
        png = renderizar_pagina(contrato.ruta_archivo, numero_pagina, ancho)
    except ErrorExtraccion as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(error))
    except FileNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No se encontró el archivo del contrato")
    return Response(content=png, media_type="image/png", headers={"Cache-Control": "private, max-age=3600"})


@router.patch("/{id_contrato}/inactivar", status_code=status.HTTP_204_NO_CONTENT)
def inactivar(id_contrato: int, request: Request, db: DbSession, usuario: UsuarioActual):
    contrato = _obtener_propio(db, id_contrato, usuario)[0]
    inactivar_contrato(contrato, usuario)
    registrar_evento(
        db, request, ACC_INACTIVACION_CONTRATO,
        usuario=usuario,
        tabla_afectada="con_contrato",
        id_registro=contrato.id_contrato,
        datos_anteriores={"estado": "A"},
        datos_nuevos={"estado": "I", "archivo": contrato.nombre_archivo},
    )
    db.commit()