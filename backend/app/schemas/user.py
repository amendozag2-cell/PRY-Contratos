import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, EmailStr, Field, StringConstraints, field_validator

from app.models import UserRole

FullName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=150)]


class UserCreate(BaseModel):
    email: EmailStr
    full_name: FullName
    password: str = Field(min_length=8)
    role: UserRole = UserRole.FREELANCER

    @field_validator("email")
    @classmethod
    def normalizar_email(cls, v: str) -> str:
        return v.lower()

    @field_validator("password")
    @classmethod
    def validar_password(cls, v: str) -> str:
        if len(v.encode("utf-8")) > 72:
            raise ValueError("La contraseña no puede superar 72 bytes")
        if not any(c.isalpha() for c in v) or not any(c.isdigit() for c in v):
            raise ValueError("La contraseña debe contener al menos una letra y un número")
        return v

    @field_validator("role")
    @classmethod
    def impedir_admin(cls, v: UserRole) -> UserRole:
        if v == UserRole.ADMIN:
            raise ValueError("No está permitido registrarse como administrador")
        return v


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: EmailStr
    full_name: str
    role: UserRole
    is_active: bool
    created_at: datetime
