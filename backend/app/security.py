from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from app.config import settings


def hash_clave(clave: str) -> str:
    return bcrypt.hashpw(clave.encode(), bcrypt.gensalt()).decode()


def verificar_clave(clave: str, clave_hash: str) -> bool:
    return bcrypt.checkpw(clave.encode(), clave_hash.encode())


def crear_token(id_usuario: int, rol: str, minutos: int) -> str:
    expira = datetime.now(timezone.utc) + timedelta(minutes=minutos)
    datos = {"sub": str(id_usuario), "rol": rol, "exp": expira}
    return jwt.encode(datos, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decodificar_token(token: str) -> dict:
    return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])