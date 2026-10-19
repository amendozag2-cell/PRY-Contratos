from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ESTADO_ACTIVO, Catalogo, CatalogoDetalle


def obtener_id_detalle(db: Session, catalogo: str, codigo: str) -> int:
    """Devuelve el id de un valor activo de catálogo a partir de sus códigos."""
    id_detalle = db.scalar(
        select(CatalogoDetalle.id_catalogo_detalle)
        .join(Catalogo, Catalogo.id_catalogo == CatalogoDetalle.id_catalogo)
        .where(
            Catalogo.codigo == catalogo,
            CatalogoDetalle.codigo == codigo,
            CatalogoDetalle.estado == ESTADO_ACTIVO,
        )
    )
    if id_detalle is None:
        raise ValueError(f"No existe el valor activo '{codigo}' en el catálogo '{catalogo}'")
    return id_detalle


def listar_detalles(db: Session, catalogo: str) -> list[CatalogoDetalle]:
    """Valores activos de un catálogo, en su orden de presentación."""
    return list(
        db.scalars(
            select(CatalogoDetalle)
            .join(Catalogo, Catalogo.id_catalogo == CatalogoDetalle.id_catalogo)
            .where(Catalogo.codigo == catalogo, CatalogoDetalle.estado == ESTADO_ACTIVO)
            .order_by(CatalogoDetalle.orden)
        )
    )