from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ESTADO_ACTIVO, Parametro


def obtener_parametro(db: Session, codigo: str, por_defecto: str | None = None) -> str | None:
    valor = db.scalar(
        select(Parametro.valor).where(Parametro.codigo == codigo, Parametro.estado == ESTADO_ACTIVO)
    )
    return valor if valor is not None else por_defecto


def obtener_entero(db: Session, codigo: str, por_defecto: int) -> int:
    try:
        return int(obtener_parametro(db, codigo))
    except (TypeError, ValueError):
        return por_defecto