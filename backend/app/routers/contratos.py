from fastapi import APIRouter
from sqlalchemy import select

from app.deps import DbSession, UsuarioActual
from app.models import ESTADO_ACTIVO, CatalogoDetalle, Contrato
from app.schemas import ContratoSalida

router = APIRouter(prefix="/contratos", tags=["Contratos"])


@router.get("", response_model=list[ContratoSalida])
def listar_mis_contratos(usuario: UsuarioActual, db: DbSession):
    consulta = (
        select(Contrato, CatalogoDetalle.codigo)
        .join(CatalogoDetalle, CatalogoDetalle.id_catalogo_detalle == Contrato.id_estado_analisis)
        .where(Contrato.id_usuario == usuario.id_usuario, Contrato.estado == ESTADO_ACTIVO)
        .order_by(Contrato.fecha_creacion.desc())
    )
    return [
        ContratoSalida(
            id_contrato=c.id_contrato,
            nombre_archivo=c.nombre_archivo,
            numero_paginas=c.numero_paginas,
            estado_analisis=estado,
            puntaje_riesgo_global=c.puntaje_riesgo_global,
            fecha_creacion=c.fecha_creacion,
        )
        for c, estado in db.execute(consulta).all()
    ]