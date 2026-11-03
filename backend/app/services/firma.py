"""Firma electrónica de la versión final negociada del contrato.

Flujo:
1. El usuario carga la versión final (PDF con los cambios acordados). Si el PDF aún no tiene
   firmas, se le agrega una "Hoja de firmas electrónicas" donde se estampan los sellos.
2. Cada parte firma: en la plataforma con su certificado .p12 (que se usa solo en memoria) o
   fuera de ella con FirmaEC, sobre el PDF descargado; en ese caso el usuario sube el PDF
   firmado y la plataforma verifica que sea continuación exacta del documento vigente.
3. Cada firma se verifica criptográficamente (integridad y confianza) y queda registrada en
   con_firma. El estado del documento se calcula en la vista vw_documento_firma_estado.
"""

import hashlib
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from fastapi import Request
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.config import settings
from app.constantes import (
    ACC_CARGA_VERSION_FINAL,
    ACC_FIRMA_DOCUMENTO,
    ACC_REGISTRO_FIRMA_EXTERNA,
    ACC_VERIFICACION_FIRMA,
    CAT_ESTADO_CONTRAPROPUESTA,
    CP_ACEPTADA,
    CP_MODIFICADA,
    FALLO,
)
from app.models import (
    ESTADO_ACTIVO,
    Certificado,
    Clausula,
    Contrapropuesta,
    Contrato,
    DocumentoFirma,
    Firma,
    Usuario,
)
from app.services.auditoria import registrar_evento
from app.services.catalogos import listar_detalles
from app.services.firma_pdf import (
    DatosCertificado,
    ErrorFirma,
    FirmaVerificada,
    caja_firma,
    cargar_raices,
    cobertura_texto,
    extraer_texto,
    firmar_pdf,
    leer_certificado_p12,
    nombres_campos,
    numero_firmas,
    preparar_documento,
    tiene_hoja_firmas,
    verificar_firmas,
)
from app.services.negociacion import _exigir_analizado

MOTIVO_POR_DEFECTO = "Acepto los términos del contrato"
MIN_CARACTERES_TEXTO = 200  # menos texto: PDF escaneado, no se pueden comprobar los cambios


@dataclass
class EstadoDocumento:
    numero_firmas: int
    estado_firma: str
    hash_vigente: str


@dataclass
class CambioAcordado:
    clausula: Clausula
    estado_codigo: str
    estado_nombre: str
    cobertura: float


# ---------------------------------------------------------------- consultas
def obtener_documento(db: Session, contrato: Contrato) -> DocumentoFirma | None:
    """Versión final vigente (activa) del contrato."""
    return db.scalar(
        select(DocumentoFirma)
        .where(DocumentoFirma.id_contrato == contrato.id_contrato, DocumentoFirma.estado == ESTADO_ACTIVO)
        .order_by(DocumentoFirma.numero_version.desc())
        .limit(1)
    )


def estado_documento(db: Session, documento: DocumentoFirma) -> EstadoDocumento:
    fila = db.execute(
        text("SELECT numero_firmas, estado_firma, hash_vigente FROM vw_documento_firma_estado "
             "WHERE id_documento_firma = :id"),
        {"id": documento.id_documento_firma},
    ).one()
    return EstadoDocumento(fila.numero_firmas, fila.estado_firma, fila.hash_vigente)


def listar_firmas(db: Session, documento: DocumentoFirma) -> list[tuple[Firma, Certificado, Usuario | None]]:
    return [
        (f, c, u) for f, c, u in db.execute(
            select(Firma, Certificado, Usuario)
            .join(Certificado, Certificado.id_certificado == Firma.id_certificado)
            .outerjoin(Usuario, Usuario.id_usuario == Firma.id_usuario)
            .where(Firma.id_documento_firma == documento.id_documento_firma, Firma.estado == ESTADO_ACTIVO)
            .order_by(Firma.numero_orden)
        ).all()
    ]


def cambios_acordados(db: Session, contrato: Contrato, documento: DocumentoFirma) -> list[CambioAcordado] | None:
    """Comprueba si cada redacción aceptada en la negociación aparece en la versión final.

    Devuelve None si el PDF no tiene texto (escaneado) y no se puede comprobar.
    """
    estados = {d.id_catalogo_detalle: d for d in listar_detalles(db, CAT_ESTADO_CONTRAPROPUESTA)}
    aceptadas = [
        (c, cp) for c, cp in db.execute(
            select(Clausula, Contrapropuesta)
            .join(Contrapropuesta, Contrapropuesta.id_clausula == Clausula.id_clausula)
            .where(Clausula.id_contrato == contrato.id_contrato, Clausula.estado == ESTADO_ACTIVO,
                   Contrapropuesta.estado == ESTADO_ACTIVO)
            .order_by(Clausula.numero_orden)
        ).all()
        if estados.get(cp.id_estado_contrapropuesta) and
        estados[cp.id_estado_contrapropuesta].codigo in (CP_ACEPTADA, CP_MODIFICADA)
    ]
    if not aceptadas:
        return []
    try:
        texto = extraer_texto(Path(documento.ruta_archivo).read_bytes())
    except Exception:  # PDF ilegible: no se puede comprobar
        return None
    if len(texto.strip()) < MIN_CARACTERES_TEXTO:
        return None
    return [
        CambioAcordado(
            clausula=c,
            estado_codigo=estados[cp.id_estado_contrapropuesta].codigo,
            estado_nombre=estados[cp.id_estado_contrapropuesta].nombre,
            cobertura=round(cobertura_texto(cp.texto_acordado or cp.texto_propuesto, texto), 3),
        )
        for c, cp in aceptadas
    ]


# ------------------------------------------------------------------ apoyo
def _hash(contenido: bytes) -> str:
    return hashlib.sha256(contenido).hexdigest()


def _guardar(contenido: bytes) -> Path:
    carpeta = Path(settings.directorio_archivos) / "firmas"
    carpeta.mkdir(parents=True, exist_ok=True)
    ruta = carpeta / f"{uuid.uuid4().hex}.pdf"
    ruta.write_bytes(contenido)
    return ruta


def _leer_vigente(db: Session, documento: DocumentoFirma) -> bytes:
    """PDF vigente; falla si el archivo guardado no coincide con el último hash registrado."""
    ruta = Path(documento.ruta_archivo)
    if not ruta.is_file():
        raise ErrorFirma("No se encontró el archivo del documento")
    contenido = ruta.read_bytes()
    if _hash(contenido) != estado_documento(db, documento).hash_vigente:
        raise ErrorFirma("El archivo guardado fue modificado fuera de la plataforma. Cargue de nuevo la versión final")
    return contenido


def _certificado(db: Session, datos: DatosCertificado, usuario: Usuario) -> Certificado:
    certificado = db.scalar(select(Certificado).where(Certificado.huella_sha256 == datos.huella_sha256))
    if certificado is None:
        certificado = Certificado(
            emisor=datos.emisor,
            numero_serie=datos.numero_serie,
            huella_sha256=datos.huella_sha256,
            nombre_titular=datos.nombre_titular,
            identificacion_titular=datos.identificacion_titular,
            fecha_inicio_vigencia=datos.fecha_inicio_vigencia,
            fecha_fin_vigencia=datos.fecha_fin_vigencia,
            usuario_creacion=usuario.id_usuario,
        )
        db.add(certificado)
        db.flush()
    return certificado


def _sincronizar(db: Session, documento: DocumentoFirma, contenido: bytes, usuario: Usuario,
                 firmante: int | None = None) -> list[FirmaVerificada]:
    """Verifica todas las firmas del PDF y actualiza con_firma.

    `firmante` es el usuario de la plataforma que acaba de agregar la ÚLTIMA firma (o None).
    """
    verificadas = verificar_firmas(contenido, cargar_raices(settings.directorio_confianza))
    existentes = {
        f.numero_orden: f for f in db.scalars(
            select(Firma).where(Firma.id_documento_firma == documento.id_documento_firma,
                                Firma.estado == ESTADO_ACTIVO))
    }
    ahora = datetime.now(timezone.utc)
    for v in verificadas:
        firma = existentes.pop(v.numero_orden, None)
        if firma is not None:
            # Si la revisión firmada ya no es la misma, la firma registrada dejó de ser válida
            firma.es_integra = v.es_integra and firma.hash_documento == v.hash_documento
            firma.es_confiable = v.es_confiable and firma.es_integra
            firma.fecha_verificacion = ahora
            firma.usuario_modificacion = usuario.id_usuario
            firma.fecha_modificacion = ahora
            continue
        db.add(Firma(
            id_documento_firma=documento.id_documento_firma,
            id_certificado=_certificado(db, v.certificado, usuario).id_certificado,
            id_usuario=firmante if v.numero_orden == len(verificadas) else None,
            numero_orden=v.numero_orden,
            fecha_firma=v.fecha_firma,
            hash_documento=v.hash_documento,
            motivo=v.motivo,
            es_integra=v.es_integra,
            es_confiable=v.es_confiable,
            fecha_verificacion=ahora,
            usuario_creacion=usuario.id_usuario,
        ))
    for firma in existentes.values():  # registradas pero ausentes en el PDF
        firma.es_integra = False
        firma.es_confiable = False
        firma.fecha_verificacion = ahora
    db.flush()
    return verificadas


def _resumen_firmas(verificadas: list[FirmaVerificada]) -> list[dict]:
    """Datos de auditoría: nunca incluye la clave ni el archivo del certificado."""
    return [
        {"orden": v.numero_orden, "titular": v.certificado.nombre_titular, "huella": v.certificado.huella_sha256,
         "integra": v.es_integra, "confiable": v.es_confiable}
        for v in verificadas
    ]


def _registrar_fallo(db: Session, request: Request, usuario: Usuario, accion: str,
                     documento: DocumentoFirma | None, error: Exception) -> None:
    db.rollback()
    registrar_evento(
        db, request, accion,
        usuario=usuario, tabla_afectada="con_documento_firma",
        id_registro=documento.id_documento_firma if documento else None,
        resultado=FALLO, observacion=str(error)[:255],
    )
    db.commit()


# ------------------------------------------------------------- operaciones
def cargar_version_final(db: Session, request: Request, usuario: Usuario, contrato: Contrato, *,
                         contenido: bytes, nombre_archivo: str, firmas_requeridas: int) -> DocumentoFirma:
    """Registra la versión final negociada. Una carga nueva reemplaza a la anterior."""
    _exigir_analizado(db, contrato)
    previas = numero_firmas(contenido)
    preparado = contenido if previas else preparar_documento(contenido, contrato.nombre_archivo)

    anterior = obtener_documento(db, contrato)
    version = (db.scalar(select(func.max(DocumentoFirma.numero_version))
                         .where(DocumentoFirma.id_contrato == contrato.id_contrato)) or 0) + 1
    ruta = _guardar(preparado)
    try:
        ahora = datetime.now(timezone.utc)
        if anterior is not None:
            anterior.estado = "I"
            anterior.usuario_modificacion = usuario.id_usuario
            anterior.fecha_modificacion = ahora
        documento = DocumentoFirma(
            id_contrato=contrato.id_contrato,
            numero_version=version,
            nombre_archivo=nombre_archivo[:255],
            ruta_archivo=ruta.as_posix(),
            hash_archivo=_hash(preparado),
            numero_firmas_requeridas=firmas_requeridas,
            usuario_creacion=usuario.id_usuario,
        )
        db.add(documento)
        db.flush()
        verificadas = _sincronizar(db, documento, preparado, usuario) if previas else []
        registrar_evento(
            db, request, ACC_CARGA_VERSION_FINAL,
            usuario=usuario,
            tabla_afectada="con_documento_firma",
            id_registro=documento.id_documento_firma,
            datos_anteriores={"version": anterior.numero_version} if anterior else None,
            datos_nuevos={
                "contrato": contrato.id_contrato,
                "version": version,
                "archivo": nombre_archivo,
                "hash": documento.hash_archivo,
                "firmas_requeridas": firmas_requeridas,
                "firmas_previas": _resumen_firmas(verificadas),
                "hoja_de_firmas": not previas,
            },
        )
        db.commit()
    except Exception:
        db.rollback()
        ruta.unlink(missing_ok=True)
        raise
    db.refresh(documento)
    return documento


def firmar_documento(db: Session, request: Request, usuario: Usuario, contrato: Contrato, *,
                     certificado_p12: bytes, clave: str, motivo: str | None) -> None:
    """Firma la versión final con el certificado del usuario. El .p12 y la clave solo viven en memoria."""
    documento = obtener_documento(db, contrato)
    if documento is None:
        raise ErrorFirma("Primero cargue la versión final del contrato")
    ruta_nueva: Path | None = None
    try:
        estado = estado_documento(db, documento)
        if estado.estado_firma == "INVALIDO":
            raise ErrorFirma("El documento tiene firmas no válidas. Cargue de nuevo la versión final")
        if estado.estado_firma == "FIRMADO_COMPLETO":
            raise ErrorFirma("El documento ya tiene todas las firmas requeridas")
        firmas = listar_firmas(db, documento)
        if any(f.id_usuario == usuario.id_usuario for f, _, _ in firmas):
            raise ErrorFirma("Ya firmaste este documento")

        cargado = leer_certificado_p12(certificado_p12, clave)
        if any(c.huella_sha256 == cargado.datos.huella_sha256 for _, c, _ in firmas):
            raise ErrorFirma("Este certificado ya firmó el documento")

        actual = _leer_vigente(db, documento)
        numero = numero_firmas(actual) + 1
        campos = nombres_campos(actual)
        nombre_campo = f"Firma{numero}"
        while nombre_campo in campos:
            nombre_campo += "_"
        firmado = firmar_pdf(
            actual, cargado,
            motivo=(motivo or "").strip()[:255] or MOTIVO_POR_DEFECTO,
            nombre_campo=nombre_campo,
            caja=caja_firma(numero) if tiene_hoja_firmas(actual) else None,
        )
        ruta_nueva = _guardar(firmado)
        ruta_anterior = Path(documento.ruta_archivo)
        documento.ruta_archivo = ruta_nueva.as_posix()
        documento.usuario_modificacion = usuario.id_usuario
        documento.fecha_modificacion = datetime.now(timezone.utc)
        verificadas = _sincronizar(db, documento, firmado, usuario, firmante=usuario.id_usuario)
        nueva = verificadas[-1]
        if not nueva.es_integra:
            raise ErrorFirma("La firma generada no pasó la verificación")
        registrar_evento(
            db, request, ACC_FIRMA_DOCUMENTO,
            usuario=usuario,
            tabla_afectada="con_documento_firma",
            id_registro=documento.id_documento_firma,
            datos_nuevos={
                "orden": nueva.numero_orden,
                "titular": cargado.datos.nombre_titular,
                "emisor": cargado.datos.emisor,
                "huella": cargado.datos.huella_sha256,
                "confiable": nueva.es_confiable,
                "hash_documento": nueva.hash_documento,
            },
        )
        db.commit()
    except ErrorFirma as error:
        if ruta_nueva:
            ruta_nueva.unlink(missing_ok=True)
        _registrar_fallo(db, request, usuario, ACC_FIRMA_DOCUMENTO, documento, error)
        raise
    except Exception:
        db.rollback()
        if ruta_nueva:
            ruta_nueva.unlink(missing_ok=True)
        raise
    ruta_anterior.unlink(missing_ok=True)  # el PDF nuevo contiene íntegra la versión anterior


def registrar_firma_externa(db: Session, request: Request, usuario: Usuario, contrato: Contrato,
                            contenido: bytes) -> None:
    """Registra las firmas hechas fuera de la plataforma (por ejemplo, con FirmaEC)."""
    documento = obtener_documento(db, contrato)
    if documento is None:
        raise ErrorFirma("Primero cargue la versión final del contrato")
    ruta_nueva: Path | None = None
    try:
        actual = _leer_vigente(db, documento)
        if not contenido.startswith(actual):
            raise ErrorFirma(
                "El PDF no corresponde al documento vigente. Debe firmarse el archivo descargado "
                "de la plataforma, sin modificarlo ni volver a guardarlo"
            )
        antes = numero_firmas(actual)
        if numero_firmas(contenido) <= antes:
            raise ErrorFirma("El PDF no tiene firmas nuevas")
        verificadas = verificar_firmas(contenido, cargar_raices(settings.directorio_confianza))
        invalidas = [v for v in verificadas[antes:] if not v.es_integra]
        if invalidas:
            raise ErrorFirma(f"La firma de {invalidas[0].certificado.nombre_titular} no es válida")

        ruta_nueva = _guardar(contenido)
        ruta_anterior = Path(documento.ruta_archivo)
        documento.ruta_archivo = ruta_nueva.as_posix()
        documento.usuario_modificacion = usuario.id_usuario
        documento.fecha_modificacion = datetime.now(timezone.utc)
        verificadas = _sincronizar(db, documento, contenido, usuario)
        registrar_evento(
            db, request, ACC_REGISTRO_FIRMA_EXTERNA,
            usuario=usuario,
            tabla_afectada="con_documento_firma",
            id_registro=documento.id_documento_firma,
            datos_nuevos={"firmas_nuevas": _resumen_firmas(verificadas[antes:])},
        )
        db.commit()
    except ErrorFirma as error:
        if ruta_nueva:
            ruta_nueva.unlink(missing_ok=True)
        _registrar_fallo(db, request, usuario, ACC_REGISTRO_FIRMA_EXTERNA, documento, error)
        raise
    except Exception:
        db.rollback()
        if ruta_nueva:
            ruta_nueva.unlink(missing_ok=True)
        raise
    ruta_anterior.unlink(missing_ok=True)


def verificar_documento(db: Session, request: Request, usuario: Usuario, contrato: Contrato) -> None:
    """Vuelve a verificar criptográficamente todas las firmas del documento vigente."""
    documento = obtener_documento(db, contrato)
    if documento is None:
        raise ErrorFirma("Primero cargue la versión final del contrato")
    ruta = Path(documento.ruta_archivo)
    if not ruta.is_file():
        raise ErrorFirma("No se encontró el archivo del documento")
    contenido = ruta.read_bytes()
    archivo_intacto = _hash(contenido) == estado_documento(db, documento).hash_vigente
    # Cada firma se compara con la revisión que firmó: si el archivo fue reemplazado, deja de ser íntegra
    verificadas = _sincronizar(db, documento, contenido, usuario)
    registrar_evento(
        db, request, ACC_VERIFICACION_FIRMA,
        usuario=usuario,
        tabla_afectada="con_documento_firma",
        id_registro=documento.id_documento_firma,
        datos_nuevos={"archivo_intacto": archivo_intacto, "firmas": _resumen_firmas(verificadas)},
    )
    db.commit()