"""Modelos ORM del Avance 1 (modelo entidad-relación v2.0).

La estructura física la crea la migración 0001_avance1; estas clases la
reflejan para que el código pueda consultarla.
"""

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
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects.postgresql import JSONB
from pgvector.sqlalchemy import Vector
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

ESTADO_ACTIVO = "A"
ESTADO_INACTIVO = "I"
DIMENSION_EMBEDDING = 1536  # text-embedding-3-small


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
    id_rol_parte: Mapped[int | None] = mapped_column(
        ForeignKey("cat_catalogo_detalle.id_catalogo_detalle")
    )
    contexto_usuario: Mapped[str | None] = mapped_column(Text)


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


# ------------------------------------------------------- base de conocimiento
class DocumentoRag(ColumnasControl, Base):
    """Ley, reglamento o guía de buenas prácticas del corpus legal."""

    __tablename__ = "rag_documento"

    id_documento: Mapped[int] = mapped_column(Integer, primary_key=True)
    id_tipo_fuente: Mapped[int] = mapped_column(
        ForeignKey("cat_catalogo_detalle.id_catalogo_detalle")
    )
    titulo: Mapped[str] = mapped_column(String(255))
    referencia: Mapped[str | None] = mapped_column(String(255))
    ruta_archivo: Mapped[str] = mapped_column(String(500))


class FragmentoRag(ColumnasControl, Base):
    """Fragmento vectorizado de un documento del corpus."""

    __tablename__ = "rag_fragmento"
    __table_args__ = (UniqueConstraint("id_documento", "numero_orden"),)

    id_fragmento: Mapped[int] = mapped_column(Integer, primary_key=True)
    id_documento: Mapped[int] = mapped_column(
        ForeignKey("rag_documento.id_documento", ondelete="CASCADE"), index=True
    )
    numero_orden: Mapped[int] = mapped_column(Integer)
    articulo_referencia: Mapped[str | None] = mapped_column(String(60))
    contenido: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list[float]] = mapped_column(Vector(DIMENSION_EMBEDDING))


# ----------------------------------------------- semáforo y cláusulas
class NivelRiesgo(ColumnasControl, Base):
    """Catálogo del semáforo de riesgo (ALTO, MEDIO, BAJO)."""

    __tablename__ = "cat_nivel_riesgo"

    id_nivel_riesgo: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    codigo: Mapped[str] = mapped_column(String(10), unique=True)
    nombre: Mapped[str] = mapped_column(String(40))
    color_hex: Mapped[str] = mapped_column(CHAR(7))
    peso: Mapped[int] = mapped_column(SmallInteger)
    orden: Mapped[int] = mapped_column(SmallInteger)
    descripcion: Mapped[str | None] = mapped_column(String(255))


class Clausula(ColumnasControl, Base):
    """Cláusula del contrato con su ubicación en el PDF y, desde el Avance 4, su diagnóstico."""

    __tablename__ = "con_clausula"
    __table_args__ = (UniqueConstraint("id_contrato", "numero_orden"),)

    id_clausula: Mapped[int] = mapped_column(Integer, primary_key=True)
    id_contrato: Mapped[int] = mapped_column(
        ForeignKey("con_contrato.id_contrato", ondelete="CASCADE"), index=True
    )
    id_nivel_riesgo: Mapped[int | None] = mapped_column(
        ForeignKey("cat_nivel_riesgo.id_nivel_riesgo")
    )
    id_categoria_riesgo: Mapped[int | None] = mapped_column(
        ForeignKey("cat_catalogo_detalle.id_catalogo_detalle")
    )
    numero_orden: Mapped[int] = mapped_column(Integer)
    titulo: Mapped[str | None] = mapped_column(String(255))
    contenido: Mapped[str] = mapped_column(Text)
    numero_pagina: Mapped[int] = mapped_column(SmallInteger)
    coordenadas: Mapped[list[dict]] = mapped_column(JSONB)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(DIMENSION_EMBEDDING))
    explicacion: Mapped[str | None] = mapped_column(Text)

class ClausulaFundamento(ColumnasControl, Base):
    """Norma del corpus que el LLM citó para justificar el diagnóstico de una cláusula."""

    __tablename__ = "con_clausula_fundamento"

    id_clausula: Mapped[int] = mapped_column(
        ForeignKey("con_clausula.id_clausula", ondelete="CASCADE"), primary_key=True
    )
    id_fragmento: Mapped[int] = mapped_column(
        ForeignKey("rag_fragmento.id_fragmento", ondelete="CASCADE"), primary_key=True
    )
    similitud: Mapped[Decimal] = mapped_column(Numeric(5, 4))


class Condicion(ColumnasControl, Base):
    """Condición que el usuario dice haber acordado y si el contrato la recoge."""

    __tablename__ = "con_condicion"
    __table_args__ = (UniqueConstraint("id_contrato", "numero_orden"),)

    id_condicion: Mapped[int] = mapped_column(Integer, primary_key=True)
    id_contrato: Mapped[int] = mapped_column(
        ForeignKey("con_contrato.id_contrato", ondelete="CASCADE")
    )
    id_cobertura: Mapped[int] = mapped_column(
        ForeignKey("cat_catalogo_detalle.id_catalogo_detalle")
    )
    id_clausula: Mapped[int | None] = mapped_column(
        ForeignKey("con_clausula.id_clausula", ondelete="SET NULL"), index=True
    )
    numero_orden: Mapped[int] = mapped_column(SmallInteger)
    descripcion: Mapped[str] = mapped_column(String(500))
    explicacion: Mapped[str | None] = mapped_column(Text)

    

class Contrapropuesta(ColumnasControl, Base):
    """Redacción alternativa de una cláusula riesgosa y su resultado en la negociación."""

    __tablename__ = "con_contrapropuesta"

    id_contrapropuesta: Mapped[int] = mapped_column(Integer, primary_key=True)
    id_clausula: Mapped[int] = mapped_column(
        ForeignKey("con_clausula.id_clausula", ondelete="CASCADE"), unique=True
    )
    id_estado_contrapropuesta: Mapped[int] = mapped_column(
        ForeignKey("cat_catalogo_detalle.id_catalogo_detalle")
    )
    texto_propuesto: Mapped[str] = mapped_column(Text)
    texto_acordado: Mapped[str | None] = mapped_column(Text)
    justificacion: Mapped[str | None] = mapped_column(Text)
    modelo_llm: Mapped[str] = mapped_column(String(60))


class CorreoNegociacion(ColumnasControl, Base):
    """Correo redactado para pedir a la otra parte los cambios del contrato."""

    __tablename__ = "con_correo_negociacion"

    id_correo: Mapped[int] = mapped_column(Integer, primary_key=True)
    id_contrato: Mapped[int] = mapped_column(
        ForeignKey("con_contrato.id_contrato", ondelete="CASCADE"), index=True
    )
    id_tono: Mapped[int] = mapped_column(ForeignKey("cat_catalogo_detalle.id_catalogo_detalle"))
    destinatario: Mapped[str | None] = mapped_column(String(150))
    asunto: Mapped[str] = mapped_column(String(255))
    cuerpo: Mapped[str] = mapped_column(Text)
    modelo_llm: Mapped[str] = mapped_column(String(60))


class Reporte(ColumnasControl, Base):
    """Informe PDF generado de un contrato."""

    __tablename__ = "con_reporte"

    id_reporte: Mapped[int] = mapped_column(Integer, primary_key=True)
    id_contrato: Mapped[int] = mapped_column(
        ForeignKey("con_contrato.id_contrato", ondelete="CASCADE"), index=True
    )
    nombre_archivo: Mapped[str] = mapped_column(String(255))
    ruta_archivo: Mapped[str] = mapped_column(String(500))
    hash_archivo: Mapped[str] = mapped_column(CHAR(64))



class Certificado(ColumnasControl, Base):
    """Datos públicos de un certificado de firma. El .p12 y su clave nunca se guardan."""

    __tablename__ = "seg_certificado"

    id_certificado: Mapped[int] = mapped_column(Integer, primary_key=True)
    emisor: Mapped[str] = mapped_column(String(255))
    numero_serie: Mapped[str] = mapped_column(String(100))
    huella_sha256: Mapped[str] = mapped_column(CHAR(64), unique=True)
    nombre_titular: Mapped[str] = mapped_column(String(200))
    identificacion_titular: Mapped[str | None] = mapped_column(String(20))
    fecha_inicio_vigencia: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    fecha_fin_vigencia: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class DocumentoFirma(ColumnasControl, Base):
    """Versión final negociada del contrato que se firma electrónicamente."""

    __tablename__ = "con_documento_firma"

    id_documento_firma: Mapped[int] = mapped_column(Integer, primary_key=True)
    id_contrato: Mapped[int] = mapped_column(ForeignKey("con_contrato.id_contrato", ondelete="CASCADE"))
    numero_version: Mapped[int] = mapped_column(SmallInteger)
    nombre_archivo: Mapped[str] = mapped_column(String(255))
    ruta_archivo: Mapped[str] = mapped_column(String(500))
    hash_archivo: Mapped[str] = mapped_column(CHAR(64))
    numero_firmas_requeridas: Mapped[int] = mapped_column(SmallInteger, server_default=text("2"))


class Firma(ColumnasControl, Base):
    """Firma PAdES contenida en el documento (hecha en la plataforma o con FirmaEC)."""

    __tablename__ = "con_firma"

    id_firma: Mapped[int] = mapped_column(Integer, primary_key=True)
    id_documento_firma: Mapped[int] = mapped_column(
        ForeignKey("con_documento_firma.id_documento_firma", ondelete="CASCADE")
    )
    id_certificado: Mapped[int] = mapped_column(ForeignKey("seg_certificado.id_certificado"), index=True)
    id_usuario: Mapped[int | None] = mapped_column(ForeignKey("seg_usuario.id_usuario"))
    numero_orden: Mapped[int] = mapped_column(SmallInteger)
    fecha_firma: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    hash_documento: Mapped[str] = mapped_column(CHAR(64))
    motivo: Mapped[str | None] = mapped_column(String(255))
    es_integra: Mapped[bool] = mapped_column()
    es_confiable: Mapped[bool] = mapped_column(server_default=text("false"))
    fecha_verificacion: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())