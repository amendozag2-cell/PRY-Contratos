from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.constantes import ROL_ADMINISTRADOR
from app.db import get_db
from app.models import ESTADO_ACTIVO, Usuario
from app.security import decodificar_token

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

DbSession = Annotated[Session, Depends(get_db)]


def obtener_usuario_actual(
    token: Annotated[str, Depends(oauth2_scheme)], db: DbSession
) -> Usuario:
    error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Credenciales inválidas o sesión expirada",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        datos = decodificar_token(token)
        id_usuario = int(datos["sub"])
    except (jwt.InvalidTokenError, KeyError, ValueError):
        raise error

    usuario = db.get(Usuario, id_usuario)
    if usuario is None or usuario.estado != ESTADO_ACTIVO:
        raise error
    return usuario


UsuarioActual = Annotated[Usuario, Depends(obtener_usuario_actual)]


def requiere_administrador(usuario: UsuarioActual) -> Usuario:
    if usuario.codigo_rol != ROL_ADMINISTRADOR:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Requiere rol de administrador")
    return usuario


Administrador = Annotated[Usuario, Depends(requiere_administrador)]