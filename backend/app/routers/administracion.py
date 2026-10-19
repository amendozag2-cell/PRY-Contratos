from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select

from app.config import settings
from app.constantes import ACC_INICIO_SESION_FALLIDO, CAT_ACCION_AUDITORIA
from app.deps import DbSession, requiere_administrador
from app.models import ESTADO_ACTIVO, Auditoria, CatalogoDetalle, Contrato, Usuario
from app.schemas import (
    AuditoriaPagina,
    AuditoriaSalida,
    OpcionCatalogo,
    ResumenAdministracion,
)
from app.services.catalogos import listar_detalles, obtener_id_detalle

router = APIRouter(
    prefix="/admin",
    tags=["Administración"],
    dependencies=[Depends(requiere_administrador)],
)


def inicio_del_dia():
    """Medianoche de hoy en la zona horaria configurada (por defecto, Ecuador).

    Equivale a: date_trunc('day', now() AT TIME ZONE zona) AT TIME ZONE zona
    """
    zona = settings.zona_horaria
    return func.timezone(zona, func.date_trunc("day", func.timezone(zona, func.now())))


@router.get("/resumen", response_model=ResumenAdministracion)
def resumen(db: DbSession):
    desde = inicio_del_dia()
    id_fallido = obtener_id_detalle(db, CAT_ACCION_AUDITORIA, ACC_INICIO_SESION_FALLIDO)
    return ResumenAdministracion(
        usuarios_activos=db.scalar(
            select(func.count(Usuario.id_usuario)).where(Usuario.estado == ESTADO_ACTIVO)
        ),
        contratos=db.scalar(
            select(func.count(Contrato.id_contrato)).where(Contrato.estado == ESTADO_ACTIVO)
        ),
        eventos_hoy=db.scalar(
            select(func.count(Auditoria.id_auditoria)).where(Auditoria.fecha_evento >= desde)
        ),
        accesos_fallidos_hoy=db.scalar(
            select(func.count(Auditoria.id_auditoria)).where(
                Auditoria.id_accion == id_fallido, Auditoria.fecha_evento >= desde
            )
        ),
    )


@router.get("/acciones", response_model=list[OpcionCatalogo])
def acciones_de_auditoria(db: DbSession):
    """Opciones del filtro de acciones, leídas del catálogo ACCION_AUDITORIA."""
    return [
        OpcionCatalogo(codigo=d.codigo, nombre=d.nombre)
        for d in listar_detalles(db, CAT_ACCION_AUDITORIA)
    ]


@router.get("/auditoria", response_model=AuditoriaPagina)
def consultar_auditoria(
    db: DbSession,
    accion: str | None = None,
    correo: str | None = None,
    resultado: Literal["EXITO", "FALLO"] | None = None,
    pagina: int = Query(1, ge=1),
    tamanio: int = Query(20, ge=1, le=100),
):
    consulta = select(Auditoria, CatalogoDetalle.codigo, CatalogoDetalle.nombre).join(
        CatalogoDetalle, CatalogoDetalle.id_catalogo_detalle == Auditoria.id_accion
    )
    if accion:
        consulta = consulta.where(CatalogoDetalle.codigo == accion)
    if correo:
        consulta = consulta.where(Auditoria.correo_usuario.ilike(f"%{correo}%"))
    if resultado:
        consulta = consulta.where(Auditoria.resultado == resultado)

    total = db.scalar(select(func.count()).select_from(consulta.subquery()))
    filas = db.execute(
        consulta.order_by(Auditoria.fecha_evento.desc(), Auditoria.id_auditoria.desc())
        .offset((pagina - 1) * tamanio)
        .limit(tamanio)
    ).all()

    elementos = [
        AuditoriaSalida(
            id_auditoria=a.id_auditoria,
            correo_usuario=a.correo_usuario,
            accion=codigo,
            accion_nombre=nombre,
            tabla_afectada=a.tabla_afectada,
            id_registro=a.id_registro,
            resultado=a.resultado,
            datos_anteriores=a.datos_anteriores,
            datos_nuevos=a.datos_nuevos,
            observacion=a.observacion,
            direccion_ip=a.direccion_ip,
            fecha_evento=a.fecha_evento,
        )
        for a, codigo, nombre in filas
    ]
    return AuditoriaPagina(elementos=elementos, total=total, pagina=pagina, tamanio=tamanio)