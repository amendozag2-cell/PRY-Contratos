import re
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator


# --------------------------------------------------------------- seguridad
class UsuarioCrear(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    correo: EmailStr
    nombres: str = Field(min_length=2, max_length=80)
    apellidos: str = Field(min_length=2, max_length=80)
    clave: str = Field(min_length=8, max_length=64)
    rol: Literal["FREELANCER", "PYME"] = "FREELANCER"
    nombre_empresa: str | None = Field(default=None, max_length=150)
    ruc_empresa: str | None = None

    @field_validator("nombre_empresa", "ruc_empresa", mode="before")
    @classmethod
    def vacio_a_nulo(cls, valor):
        return None if isinstance(valor, str) and not valor.strip() else valor

    @field_validator("ruc_empresa")
    @classmethod
    def validar_ruc(cls, valor):
        if valor is not None and not re.fullmatch(r"\d{13}", valor):
            raise ValueError("El RUC debe tener 13 dígitos")
        return valor

    @model_validator(mode="after")
    def validar_empresa(self):
        if self.rol == "PYME":
            if not self.nombre_empresa:
                raise ValueError("Las PYMEs deben indicar el nombre de la empresa")
        else:
            self.nombre_empresa = None
            self.ruc_empresa = None
        return self


class UsuarioSalida(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id_usuario: int
    correo: str
    nombres: str
    apellidos: str
    rol: str = Field(validation_alias="codigo_rol")
    nombre_empresa: str | None
    ruc_empresa: str | None
    fecha_creacion: datetime


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


# --------------------------------------------------------------- contratos
class ContratoSalida(BaseModel):
    id_contrato: int
    nombre_archivo: str
    numero_paginas: int | None
    estado_analisis: str
    puntaje_riesgo_global: Decimal | None
    fecha_creacion: datetime


# ----------------------------------------------------------- administración
class OpcionCatalogo(BaseModel):
    codigo: str
    nombre: str


class AuditoriaSalida(BaseModel):
    id_auditoria: int
    correo_usuario: str | None
    accion: str
    accion_nombre: str
    tabla_afectada: str | None
    id_registro: int | None
    resultado: Literal["EXITO", "FALLO"]
    datos_anteriores: dict | None
    datos_nuevos: dict | None
    observacion: str | None
    direccion_ip: str | None
    fecha_evento: datetime


class AuditoriaPagina(BaseModel):
    elementos: list[AuditoriaSalida]
    total: int
    pagina: int
    tamanio: int


class ResumenAdministracion(BaseModel):
    usuarios_activos: int
    contratos: int
    eventos_hoy: int
    accesos_fallidos_hoy: int


# ------------------------------------------------- corpus legal (RAG)
class DocumentoRagSalida(BaseModel):
    id_documento: int
    titulo: str
    tipo_fuente: str
    tipo_fuente_nombre: str
    referencia: str | None
    numero_fragmentos: int
    estado: str
    fecha_creacion: datetime


class FragmentoSalida(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id_fragmento: int
    numero_orden: int
    articulo_referencia: str | None
    contenido: str


class FragmentoPagina(BaseModel):
    elementos: list[FragmentoSalida]
    total: int
    pagina: int
    tamanio: int


class BusquedaEntrada(BaseModel):
    consulta: str = Field(min_length=5, max_length=2000)
    top_k: int | None = Field(default=None, ge=1, le=20)


class FragmentoEncontrado(BaseModel):
    id_fragmento: int
    id_documento: int
    titulo_documento: str
    articulo_referencia: str | None
    contenido: str
    similitud: float


class BusquedaSalida(BaseModel):
    consulta: str
    modelo: str
    tiempo_ms: int
    resultados: list[FragmentoEncontrado]