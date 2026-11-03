"""Firma electrónica de la versión final negociada (Avance 7)."""

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import FileResponse

from app.config import settings
from app.deps import DbSession, UsuarioActual
from app.models import Contrato, DocumentoFirma, Usuario
from app.routers.contratos import FIRMA_PDF, _obtener_propio
from app.schemas import CambioAcordadoSalida, DocumentoFirmaSalida, FirmaSalida
from app.services.firma import (
    cambios_acordados,
    cargar_version_final,
    estado_documento,
    firmar_documento,
    listar_firmas,
    obtener_documento,
    registrar_firma_externa,
    verificar_documento,
)
from app.services.firma_pdf import ErrorFirma, cargar_raices
from app.services.negociacion import ErrorNegociacion

router = APIRouter(prefix="/contratos", tags=["Firma electrónica"])

MAX_FIRMAS_REQUERIDAS = 10


def _resultado(cobertura: float) -> str:
    if cobertura >= 0.9:
        return "INCLUIDA"
    if cobertura >= 0.5:
        return "PARCIAL"
    return "NO_ENCONTRADA"


def _salida(db, usuario: Usuario, contrato: Contrato, documento: DocumentoFirma) -> DocumentoFirmaSalida:
    estado = estado_documento(db, documento)
    firmas = listar_firmas(db, documento)
    cambios = cambios_acordados(db, contrato, documento)
    return DocumentoFirmaSalida(
        id_documento_firma=documento.id_documento_firma,
        numero_version=documento.numero_version,
        nombre_archivo=documento.nombre_archivo,
        hash_archivo=documento.hash_archivo,
        hash_vigente=estado.hash_vigente,
        numero_firmas=estado.numero_firmas,
        numero_firmas_requeridas=documento.numero_firmas_requeridas,
        estado_firma=estado.estado_firma,
        fecha_creacion=documento.fecha_creacion,
        ya_firme=any(f.id_usuario == usuario.id_usuario for f, _, _ in firmas),
        raices_confianza=len(cargar_raices(settings.directorio_confianza)),
        firmas=[
            FirmaSalida(
                numero_orden=f.numero_orden,
                titular=c.nombre_titular,
                identificacion=c.identificacion_titular,
                emisor=c.emisor,
                numero_serie=c.numero_serie,
                vigencia_hasta=c.fecha_fin_vigencia,
                fecha_firma=f.fecha_firma,
                motivo=f.motivo,
                en_plataforma=f.id_usuario is not None,
                firmante=f"{u.nombres} {u.apellidos}" if u else None,
                es_integra=f.es_integra,
                es_confiable=f.es_confiable,
                fecha_verificacion=f.fecha_verificacion,
            )
            for f, c, u in firmas
        ],
        cambios=None if cambios is None else [
            CambioAcordadoSalida(
                id_clausula=k.clausula.id_clausula,
                numero_clausula=k.clausula.numero_orden,
                titulo_clausula=k.clausula.titulo,
                estado=k.estado_codigo,
                estado_nombre=k.estado_nombre,
                porcentaje=round(k.cobertura * 100),
                resultado=_resultado(k.cobertura),
            )
            for k in cambios
        ],
    )


def _leer_pdf(archivo: UploadFile) -> bytes:
    limite = settings.max_mb_contrato * 1024 * 1024
    contenido = archivo.file.read(limite + 1)
    if len(contenido) > limite:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE,
                            f"El archivo supera el máximo de {settings.max_mb_contrato} MB")
    if not contenido.startswith(FIRMA_PDF):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "El archivo debe ser un PDF")
    return contenido


def _documento_o_404(db, contrato: Contrato) -> DocumentoFirma:
    documento = obtener_documento(db, contrato)
    if documento is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Aún no se cargó la versión final del contrato")
    return documento


@router.get("/{id_contrato}/firma", response_model=DocumentoFirmaSalida | None)
def ver_firma(id_contrato: int, db: DbSession, usuario: UsuarioActual):
    """Versión final vigente con sus firmas, o null si todavía no se cargó."""
    contrato = _obtener_propio(db, id_contrato, usuario)[0]
    documento = obtener_documento(db, contrato)
    return _salida(db, usuario, contrato, documento) if documento else None


@router.post("/{id_contrato}/firma", response_model=DocumentoFirmaSalida, status_code=status.HTTP_201_CREATED)
def cargar_final(
    id_contrato: int,
    request: Request,
    db: DbSession,
    usuario: UsuarioActual,
    archivo: Annotated[UploadFile, File(description="Versión final negociada del contrato, en PDF")],
    firmas_requeridas: Annotated[int, Form(ge=1, le=MAX_FIRMAS_REQUERIDAS)] = 2,
):
    """Carga la versión final del contrato que se va a firmar (reemplaza a la anterior)."""
    contrato = _obtener_propio(db, id_contrato, usuario)[0]
    contenido = _leer_pdf(archivo)
    try:
        documento = cargar_version_final(
            db, request, usuario, contrato,
            contenido=contenido,
            nombre_archivo=archivo.filename or "contrato_final.pdf",
            firmas_requeridas=firmas_requeridas,
        )
    except (ErrorFirma, ErrorNegociacion) as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error))
    return _salida(db, usuario, contrato, documento)


@router.post("/{id_contrato}/firma/firmar", response_model=DocumentoFirmaSalida)
def firmar(
    id_contrato: int,
    request: Request,
    db: DbSession,
    usuario: UsuarioActual,
    certificado: Annotated[UploadFile, File(description="Certificado de firma electrónica (.p12 o .pfx)")],
    clave: Annotated[str, Form(min_length=1, max_length=200, description="Contraseña del certificado")],
    motivo: Annotated[str | None, Form(max_length=255)] = None,
):
    """Firma la versión final con el certificado del usuario.

    El certificado y su contraseña se usan solo en memoria durante esta solicitud:
    no se guardan en disco, en la base de datos ni en la auditoría.
    """
    contrato = _obtener_propio(db, id_contrato, usuario)[0]
    limite = settings.max_kb_certificado * 1024
    contenido = certificado.file.read(limite + 1)
    if len(contenido) > limite:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "El archivo no parece un certificado .p12")
    try:
        firmar_documento(db, request, usuario, contrato, certificado_p12=contenido, clave=clave, motivo=motivo)
    except ErrorFirma as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error))
    finally:
        del contenido, clave
    return _salida(db, usuario, contrato, _documento_o_404(db, contrato))


@router.post("/{id_contrato}/firma/externa", response_model=DocumentoFirmaSalida)
def firma_externa(
    id_contrato: int,
    request: Request,
    db: DbSession,
    usuario: UsuarioActual,
    archivo: Annotated[UploadFile, File(description="PDF firmado fuera de la plataforma (FirmaEC u otro)")],
):
    """Registra las firmas hechas fuera de la plataforma sobre el PDF descargado de ella."""
    contrato = _obtener_propio(db, id_contrato, usuario)[0]
    contenido = _leer_pdf(archivo)
    try:
        registrar_firma_externa(db, request, usuario, contrato, contenido)
    except ErrorFirma as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error))
    return _salida(db, usuario, contrato, _documento_o_404(db, contrato))


@router.post("/{id_contrato}/firma/verificar", response_model=DocumentoFirmaSalida)
def verificar(id_contrato: int, request: Request, db: DbSession, usuario: UsuarioActual):
    """Vuelve a verificar criptográficamente todas las firmas del documento."""
    contrato = _obtener_propio(db, id_contrato, usuario)[0]
    try:
        verificar_documento(db, request, usuario, contrato)
    except ErrorFirma as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error))
    return _salida(db, usuario, contrato, _documento_o_404(db, contrato))


@router.get("/{id_contrato}/firma/archivo")
def descargar_firmado(id_contrato: int, db: DbSession, usuario: UsuarioActual):
    """PDF vigente con todas las firmas. Es el archivo que la otra parte debe firmar con FirmaEC."""
    contrato = _obtener_propio(db, id_contrato, usuario)[0]
    documento = _documento_o_404(db, contrato)
    ruta = Path(documento.ruta_archivo)
    if not ruta.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No se encontró el archivo del documento")
    nombre = Path(documento.nombre_archivo).stem[:200] or "contrato"
    return FileResponse(ruta, media_type="application/pdf", filename=f"{nombre} - firmado v{documento.numero_version}.pdf")