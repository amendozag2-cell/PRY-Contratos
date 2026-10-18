from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.api.deps import CurrentUser, SessionDep
from app.core.security import DUMMY_HASH, create_access_token, hash_password, verify_password
from app.models import User
from app.schemas import Token, UserCreate, UserRead

router = APIRouter(prefix="/auth", tags=["Autenticación"])


@router.post("/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def register(data: UserCreate, db: SessionDep) -> User:
    user = User(
        email=data.email,
        full_name=data.full_name,
        hashed_password=hash_password(data.password),
        role=data.role,
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError:  # índice único ix_users_email
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "El email ya está registrado")
    db.refresh(user)
    return user


@router.post("/login", response_model=Token)
def login(form: Annotated[OAuth2PasswordRequestForm, Depends()], db: SessionDep) -> Token:
    user = db.scalar(select(User).where(User.email == form.username.strip().lower()))
    if user is None:
        verify_password(form.password, DUMMY_HASH)  # mismo tiempo de respuesta
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Email o contraseña incorrectos")
    if not verify_password(form.password, user.hashed_password):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Email o contraseña incorrectos")
    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Cuenta desactivada")
    return Token(access_token=create_access_token(str(user.id)))


@router.get("/me", response_model=UserRead)
def me(current_user: CurrentUser) -> User:
    return current_user
