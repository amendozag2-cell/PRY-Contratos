from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator

from app.models import ContractStatus, UserRole


class UserCreate(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=2, max_length=150)
    password: str = Field(min_length=8, max_length=64)
    role: Literal["freelancer", "pyme"] = "freelancer"
    company_name: str | None = Field(default=None, max_length=150)

    @model_validator(mode="after")
    def pyme_requires_company(self):
        if self.role == "pyme" and not self.company_name:
            raise ValueError("Las PYMEs deben indicar el nombre de la empresa")
        return self


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: EmailStr
    full_name: str
    role: UserRole
    company_name: str | None
    created_at: datetime


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class ContractOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    original_filename: str
    page_count: int | None
    status: ContractStatus
    global_risk_score: float | None
    created_at: datetime