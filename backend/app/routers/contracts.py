from fastapi import APIRouter
from sqlalchemy import select

from app.deps import CurrentUser, DbSession
from app.models import Contract
from app.schemas import ContractOut

router = APIRouter(prefix="/contracts", tags=["Contratos"])


@router.get("", response_model=list[ContractOut])
def list_my_contracts(user: CurrentUser, db: DbSession):
    stmt = (
        select(Contract)
        .where(Contract.user_id == user.id)
        .order_by(Contract.created_at.desc())
    )
    return db.scalars(stmt).all()