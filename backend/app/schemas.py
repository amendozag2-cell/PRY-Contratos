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


# --------------------------------------------------------------- catálogos
class OpcionCatalogo(BaseModel):
    codigo: str
    nombre: str


# --------------------------------------------------------------- contratos
class ContratoSalida(BaseModel):
    id_contrato: int
    nombre_archivo: str
    tipo_contrato: str | None
    numero_paginas: int | None
    numero_clausulas: int
    es_escaneado: bool
    estado_analisis: str
    puntaje_riesgo_global: Decimal | None
    fecha_creacion: datetime


class Coordenada(BaseModel):
    """Rectángulo de un párrafo, normalizado entre 0 y 1 respecto a la página."""

    pagina: int
    x0: float
    y0: float
    x1: float
    y1: float


class NivelRiesgoSalida(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    codigo: str
    nombre: str
    color_hex: str
    peso: int


class FundamentoSalida(BaseModel):
    """Norma del corpus citada para justificar el diagnóstico."""

    id_fragmento: int
    titulo_documento: str
    articulo_referencia: str | None
    contenido: str
    similitud: float


class ClausulaSalida(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id_clausula: int
    numero_orden: int
    titulo: str | None
    contenido: str
    numero_pagina: int
    coordenadas: list[Coordenada]
    nivel_riesgo: NivelRiesgoSalida | None = None
    categoria_riesgo: OpcionCatalogo | None = None
    explicacion: str | None = None
    fundamentos: list[FundamentoSalida] = []


class CoberturaSalida(BaseModel):
    codigo: str
    nombre: str
    color_hex: str


class CondicionSalida(BaseModel):
    """Condición que el usuario indicó y si el contrato la recoge."""

    numero_orden: int
    descripcion: str
    cobertura: CoberturaSalida
    explicacion: str | None
    id_clausula: int | None
    numero_clausula: int | None
    titulo_clausula: str | None


class ContratoDetalle(ContratoSalida):
    resumen: str | None
    tiempo_procesamiento_ms: int | None
    fecha_analisis: datetime | None
    rol_parte: OpcionCatalogo | None
    contexto_usuario: str | None
    niveles: list[NivelRiesgoSalida]
    clausulas: list[ClausulaSalida]
    condiciones: list[CondicionSalida]


MAX_CONTEXTO = 4000


class ContextoEntrada(BaseModel):
    """Papel del usuario en el contrato y lo que dice que acordaron."""

    model_config = ConfigDict(str_strip_whitespace=True)

    rol_parte: str | None = None
    contexto_usuario: str | None = Field(default=None, max_length=MAX_CONTEXTO)

    @field_validator("rol_parte", "contexto_usuario", mode="before")
    @classmethod
    def vacio_a_nulo(cls, valor):
        return None if isinstance(valor, str) and not valor.strip() else valor

class CargaContratoSalida(BaseModel):
    contrato: ContratoSalida
    paginas_ocr: list[int]
    tiempo_ms: int


# ----------------------------------------------------------- administración
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