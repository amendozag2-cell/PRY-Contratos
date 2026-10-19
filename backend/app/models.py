from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    CHAR,
    BigInteger,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

ESTADO_ACTIVO = "A"
ESTADO_INACTIVO = "I"


class ColumnasControl:
    """Columnas estándar de todas las tablas excepto aud_auditoria."""

    estado: Mapped[str] = mapped_column(
        CHAR(1), default=ESTADO_ACTIVO, server_default=text("'A'")
    )
    usuario_creacion: Mapped[int | None] = mapped_column(
        ForeignKey("seg_usuario.id_usuario", use_alter=True)
    )
    fecha_creacion: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    usuario_modificacion: Mapped[int | None] = mapped_column(
        ForeignKey("seg_usuario.id_usuario", use_alter=True)
    )
    fecha_modificacion: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


# ------------------------------------------------------------ parametrización
class Catalogo(ColumnasControl, Base):
    __tablename__ = "cat_catalogo"

    id_catalogo: Mapped[int] = mapped_column(Integer, primary_key=True)
    codigo: Mapped[str] = mapped_column(String(40), unique=True)
    nombre: Mapped[str] = mapped_column(String(100))
    descripcion: Mapped[str | None] = mapped_column(String(255))


class CatalogoDetalle(ColumnasControl, Base):
    __tablename__ = "cat_catalogo_detalle"
    __table_args__ = (UniqueConstraint("id_catalogo", "codigo"),)

    id_catalogo_detalle: Mapped[int] = mapped_column(Integer, primary_key=True)
    id_catalogo: Mapped[int] = mapped_column(ForeignKey("cat_catalogo.id_catalogo"))
    codigo: Mapped[str] = mapped_column(String(40))
    nombre: Mapped[str] = mapped_column(String(100))
    descripcion: Mapped[str | None] = mapped_column(String(255))
    valor: Mapped[str | None] = mapped_column(String(100))
    orden: Mapped[int] = mapped_column(SmallInteger, default=1, server_default=text("1"))


class Parametro(ColumnasControl, Base):
    __tablename__ = "cat_parametro"

    id_parametro: Mapped[int] = mapped_column(Integer, primary_key=True)
    codigo: Mapped[str] = mapped_column(String(60), unique=True)
    nombre: Mapped[str] = mapped_column(String(120))
    valor: Mapped[str] = mapped_column(String(255))
    tipo_dato: Mapped[str] = mapped_column(String(10))
    descripcion: Mapped[str | None] = mapped_column(String(255))


# ------------------------------------------------------------------ seguridad
class Rol(ColumnasControl, Base):
    __tablename__ = "seg_rol"

    id_rol: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    codigo: Mapped[str] = mapped_column(String(20), unique=True)
    nombre: Mapped[str] = mapped_column(String(50))
    descripcion: Mapped[str | None] = mapped_column(String(255))


class Usuario(ColumnasControl, Base):
    __tablename__ = "seg_usuario"

    id_usuario: Mapped[int] = mapped_column(Integer, primary_key=True)
    id_rol: Mapped[int] = mapped_column(ForeignKey("seg_rol.id_rol"))
    correo: Mapped[str] = mapped_column(String(255), unique=True)
    nombres: Mapped[str] = mapped_column(String(80))
    apellidos: Mapped[str] = mapped_column(String(80))
    clave_hash: Mapped[str] = mapped_column(String(255))
    nombre_empresa: Mapped[str | None] = mapped_column(String(150))
    ruc_empresa: Mapped[str | None] = mapped_column(CHAR(13))
    fecha_ultimo_acceso: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    rol: Mapped[Rol] = relationship(foreign_keys="Usuario.id_rol", lazy="joined")

    @property
    def codigo_rol(self) -> str:
        return self.rol.codigo


# ------------------------------------------------------------------ contratos
class Contrato(ColumnasControl, Base):
    __tablename__ = "con_contrato"

    id_contrato: Mapped[int] = mapped_column(Integer, primary_key=True)
    id_usuario: Mapped[int] = mapped_column(ForeignKey("seg_usuario.id_usuario"), index=True)
    id_tipo_contrato: Mapped[int | None] = mapped_column(
        ForeignKey("cat_catalogo_detalle.id_catalogo_detalle")
    )
    id_estado_analisis: Mapped[int] = mapped_column(
        ForeignKey("cat_catalogo_detalle.id_catalogo_detalle")
    )
    nombre_archivo: Mapped[str] = mapped_column(String(255))
    ruta_archivo: Mapped[str] = mapped_column(String(500))
    hash_archivo: Mapped[str | None] = mapped_column(CHAR(64))
    numero_paginas: Mapped[int | None] = mapped_column(SmallInteger)
    es_escaneado: Mapped[bool] = mapped_column(default=False, server_default=text("false"))
    puntaje_riesgo_global: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    resumen: Mapped[str | None] = mapped_column(Text)
    tiempo_procesamiento_ms: Mapped[int | None] = mapped_column(Integer)
    fecha_analisis: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


# ------------------------------------------------------------------ auditoría
class Auditoria(Base):
    """Bitácora inmutable: un trigger en la base de datos impide UPDATE y DELETE."""

    __tablename__ = "aud_auditoria"

    id_auditoria: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    id_usuario: Mapped[int | None] = mapped_column(
        ForeignKey("seg_usuario.id_usuario"), index=True
    )
    id_accion: Mapped[int] = mapped_column(
        ForeignKey("cat_catalogo_detalle.id_catalogo_detalle"), index=True
    )
    correo_usuario: Mapped[str | None] = mapped_column(String(255))
    tabla_afectada: Mapped[str | None] = mapped_column(String(60))
    id_registro: Mapped[int | None] = mapped_column(BigInteger)
    resultado: Mapped[str] = mapped_column(String(10))
    datos_anteriores: Mapped[dict | None] = mapped_column(JSONB)
    datos_nuevos: Mapped[dict | None] = mapped_column(JSONB)
    observacion: Mapped[str | None] = mapped_column(String(255))
    direccion_ip: Mapped[str | None] = mapped_column(String(45))
    agente_usuario: Mapped[str | None] = mapped_column(String(300))
    fecha_evento: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )