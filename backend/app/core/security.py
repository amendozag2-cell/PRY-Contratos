from datetime import UTC, datetime, timedelta

import jwt
from pwdlib import PasswordHash
from pwdlib.hashers.bcrypt import BcryptHasher

from app.config import settings

password_hash = PasswordHash((BcryptHasher(),))

# Hash usado cuando el usuario no existe, para que el login tarde lo mismo
DUMMY_HASH = password_hash.hash("dummy-password")


def hash_password(password: str) -> str:
    return password_hash.hash(password)


def verify_password(password: str, hashed_password: str) -> bool:
    if len(password.encode("utf-8")) > 72:  # bcrypt lanza ValueError con más de 72 bytes
        return False
    return password_hash.verify(password, hashed_password)



def create_access_token(subject: str, expires_delta: timedelta | None = None) -> str:
    now = datetime.now(UTC)
    expire = now + (expires_delta or timedelta(minutes=settings.access_token_expire_minutes))
    payload = {"sub": subject, "iat": now, "exp": expire}
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> str | None:
    """Devuelve el `sub` (id del usuario) si el token es válido; None si no."""
    try:
        payload = jwt.decode(
            token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm]
        )
    except jwt.InvalidTokenError:  # firma inválida, expirado o mal formado
        return None
    return payload.get("sub")
