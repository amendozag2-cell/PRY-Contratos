"""Operaciones criptográficas y de PDF de la firma electrónica (sin base de datos).

- Lectura del certificado .p12/.pfx en memoria: el archivo y su clave nunca se escriben
  en disco ni en la base de datos.
- Firma PAdES (ETSI.CAdES.detached) con pyHanko, como actualización incremental del PDF:
  las firmas anteriores siguen siendo válidas.
- Verificación de todas las firmas del PDF: integridad (el documento no cambió después de
  firmar) y confianza (el certificado proviene de una entidad de certificación cargada en
  la carpeta de certificados de confianza).
"""

import hashlib
import logging
import re
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher
from datetime import datetime, timezone
from functools import lru_cache
from io import BytesIO
from pathlib import Path

import pymupdf
from asn1crypto import keys as asn1_keys
from asn1crypto import pem
from asn1crypto import x509 as asn1_x509
from cryptography.hazmat.primitives.serialization import Encoding, NoEncryption, PrivateFormat, pkcs12
from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
from pyhanko.pdf_utils.reader import PdfFileReader
from pyhanko.sign import fields, signers
from pyhanko.sign.diff_analysis import ModificationLevel
from pyhanko.sign.validation import validate_pdf_signature
from pyhanko.stamp import TextStampStyle
from pyhanko_certvalidator import ValidationContext
from pyhanko_certvalidator.registry import SimpleCertificateStore

# pyHanko registra con traza completa cada certificado que no encadena con una raíz de
# confianza; ese caso ya se informa como "no confiable", así que se silencia el aviso.
logging.getLogger("pyhanko.sign.validation.generic_cms").setLevel(logging.ERROR)

TITULO_HOJA = "HOJA DE FIRMAS ELECTRÓNICAS"
EXTENSIONES_CONFIANZA = {".cer", ".crt", ".pem", ".der"}

# Hoja de firmas A4 (puntos). Las cajas se ubican en dos columnas debajo del encabezado.
ANCHO_A4, ALTO_A4 = 595, 842
CAJA_ANCHO, CAJA_ALTO = 240, 70
MAX_CAJAS = 12

ESTILO_SELLO = TextStampStyle(
    stamp_text="Firmado electrónicamente por:\n%(signer)s\nFecha: %(ts)s",
    timestamp_format="%d/%m/%Y %H:%M:%S %Z",
    border_width=1,
)


class ErrorFirma(Exception):
    """No se pudo leer el certificado, firmar o verificar el documento."""


@dataclass
class DatosCertificado:
    emisor: str
    numero_serie: str
    huella_sha256: str
    nombre_titular: str
    identificacion_titular: str | None
    fecha_inicio_vigencia: datetime
    fecha_fin_vigencia: datetime


@dataclass
class CertificadoCargado:
    firmante: signers.SimpleSigner
    datos: DatosCertificado


@dataclass
class FirmaVerificada:
    numero_orden: int
    nombre_campo: str
    certificado: DatosCertificado
    fecha_firma: datetime
    motivo: str | None
    hash_documento: str  # SHA-256 del PDF tal como quedó después de esta firma
    es_integra: bool
    es_confiable: bool


# ------------------------------------------------------------ certificados
def _nombre(nombre: asn1_x509.Name) -> str:
    datos = nombre.native
    return str(datos.get("common_name") or datos.get("organization_name") or nombre.human_friendly)


def _identificacion(certificado: asn1_x509.Certificate) -> str | None:
    """Cédula o RUC del titular, si el certificado lo trae en el sujeto."""
    sujeto = certificado.subject.native
    serie = str(sujeto.get("serial_number") or "")
    encontrado = re.search(r"\d{13}|\d{10}", serie) or re.search(r"\b(\d{13}|\d{10})\b", certificado.subject.human_friendly)
    return encontrado.group(0) if encontrado else None


def datos_certificado(certificado: asn1_x509.Certificate) -> DatosCertificado:
    vigencia = certificado["tbs_certificate"]["validity"]
    return DatosCertificado(
        emisor=_nombre(certificado.issuer)[:255],
        numero_serie=format(certificado.serial_number, "X")[:100],
        huella_sha256=hashlib.sha256(certificado.dump()).hexdigest(),
        nombre_titular=_nombre(certificado.subject)[:200],
        identificacion_titular=_identificacion(certificado),
        fecha_inicio_vigencia=vigencia["not_before"].native,
        fecha_fin_vigencia=vigencia["not_after"].native,
    )


def leer_certificado_p12(contenido: bytes, clave: str) -> CertificadoCargado:
    """Abre el .p12 en memoria y prepara el firmante. Rechaza certificados vencidos."""
    try:
        llave, certificado, adicionales = pkcs12.load_key_and_certificates(contenido, clave.encode("utf-8"))
    except ValueError:
        raise ErrorFirma("La contraseña es incorrecta o el archivo no es un certificado .p12 válido") from None
    except Exception:
        raise ErrorFirma("No se pudo abrir el certificado. Verifique que sea un archivo .p12 o .pfx") from None
    if llave is None or certificado is None:
        raise ErrorFirma("El archivo no contiene la clave privada y el certificado del firmante")

    cert = asn1_x509.Certificate.load(certificado.public_bytes(Encoding.DER))
    datos = datos_certificado(cert)
    ahora = datetime.now(timezone.utc)
    if datos.fecha_fin_vigencia < ahora:
        raise ErrorFirma(f"El certificado venció el {datos.fecha_fin_vigencia:%d/%m/%Y}")
    if datos.fecha_inicio_vigencia > ahora:
        raise ErrorFirma("El certificado todavía no está vigente")

    cadena = [asn1_x509.Certificate.load(c.public_bytes(Encoding.DER)) for c in adicionales or []]
    firmante = signers.SimpleSigner(
        signing_cert=cert,
        signing_key=asn1_keys.PrivateKeyInfo.load(
            llave.private_bytes(Encoding.DER, PrivateFormat.PKCS8, NoEncryption())
        ),
        cert_registry=SimpleCertificateStore.from_certs(cadena),
    )
    return CertificadoCargado(firmante=firmante, datos=datos)


@lru_cache(maxsize=4)
def _raices(directorio: str, marca: float) -> tuple[asn1_x509.Certificate, ...]:
    certificados = []
    for archivo in sorted(Path(directorio).glob("*")):
        if archivo.suffix.lower() not in EXTENSIONES_CONFIANZA:
            continue
        datos = archivo.read_bytes()
        if b"-----BEGIN" in datos:
            bloques = re.findall(rb"-----BEGIN CERTIFICATE-----.+?-----END CERTIFICATE-----", datos, re.S)
            certificados += [asn1_x509.Certificate.load(pem.unarmor(b)[2]) for b in bloques]
        else:
            certificados.append(asn1_x509.Certificate.load(datos))
    return tuple(certificados)


def cargar_raices(directorio: str) -> tuple[asn1_x509.Certificate, ...]:
    """Certificados raíz de confianza (entidades de certificación acreditadas en Ecuador)."""
    carpeta = Path(directorio)
    if not carpeta.is_dir():
        return ()
    marca = max((a.stat().st_mtime for a in carpeta.iterdir()), default=0.0)
    return _raices(str(carpeta.resolve()), marca)


# -------------------------------------------------------------------- PDF
def _abrir_lector(contenido: bytes) -> PdfFileReader:
    try:
        return PdfFileReader(BytesIO(contenido), strict=False)
    except Exception:
        raise ErrorFirma("El archivo no es un PDF válido") from None


def numero_firmas(contenido: bytes) -> int:
    return len(_abrir_lector(contenido).embedded_signatures)


def nombres_campos(contenido: bytes) -> set[str]:
    return {f.field_name for f in _abrir_lector(contenido).embedded_signatures}


def tiene_hoja_firmas(contenido: bytes) -> bool:
    with pymupdf.open("pdf", contenido) as documento:
        return TITULO_HOJA in documento[-1].get_text()


def extraer_texto(contenido: bytes) -> str:
    with pymupdf.open("pdf", contenido) as documento:
        return "\n".join(pagina.get_text() for pagina in documento)


def preparar_documento(contenido: bytes, nombre_contrato: str) -> bytes:
    """Agrega al final la hoja donde se estampan las firmas (solo si el PDF no tiene firmas)."""
    try:
        documento = pymupdf.open("pdf", contenido)
    except Exception:
        raise ErrorFirma("El archivo no es un PDF válido") from None
    with documento:
        if documento.needs_pass or documento.is_encrypted:
            raise ErrorFirma("El PDF está protegido con contraseña. Súbalo sin protección")
        pagina = documento.new_page(width=ANCHO_A4, height=ALTO_A4)
        pagina.insert_text((50, 70), TITULO_HOJA, fontsize=14, fontname="hebo")
        pagina.insert_textbox(
            pymupdf.Rect(50, 85, ANCHO_A4 - 50, 170),
            f"Contrato: {nombre_contrato}\n"
            "Las firmas de esta hoja son firmas electrónicas avanzadas en formato PAdES, "
            "embebidas en el archivo. Su validez se comprueba abriendo el PDF en un lector "
            "de firmas (FirmaEC, Adobe Acrobat) y no por la imagen del sello.",
            fontsize=9, fontname="helv",
        )
        return documento.tobytes(garbage=3, deflate=True)


def caja_firma(numero: int) -> tuple[int, int, int, int] | None:
    """Rectángulo (x1, y1, x2, y2 desde abajo a la izquierda) de la firma número `numero`."""
    if numero < 1 or numero > MAX_CAJAS:
        return None
    columna, fila = (numero - 1) % 2, (numero - 1) // 2
    x1 = 50 + columna * (CAJA_ANCHO + 15)
    y2 = ALTO_A4 - 180 - fila * (CAJA_ALTO + 15)
    return (x1, y2 - CAJA_ALTO, x1 + CAJA_ANCHO, y2)


def firmar_pdf(contenido: bytes, cargado: CertificadoCargado, *, motivo: str, nombre_campo: str,
               caja: tuple[int, int, int, int] | None) -> bytes:
    """Firma el PDF (PAdES) como actualización incremental y devuelve el PDF firmado."""
    metadatos = signers.PdfSignatureMetadata(
        field_name=nombre_campo,
        reason=motivo,
        location="Ecuador",
        md_algorithm="sha256",
        subfilter=fields.SigSeedSubFilter.PADES,
    )
    campo = fields.SigFieldSpec(sig_field_name=nombre_campo, on_page=-1, box=caja) if caja else None
    firmador = signers.PdfSigner(
        metadatos, signer=cargado.firmante,
        stamp_style=ESTILO_SELLO if caja else None,
        new_field_spec=campo,
    )
    try:
        escritor = IncrementalPdfFileWriter(BytesIO(contenido), strict=False)
        salida = BytesIO()
        firmador.sign_pdf(escritor, output=salida)
    except ErrorFirma:
        raise
    except Exception as error:
        raise ErrorFirma(f"No se pudo firmar el PDF: {type(error).__name__}") from None
    return salida.getvalue()


def verificar_firmas(contenido: bytes, raices: tuple[asn1_x509.Certificate, ...]) -> list[FirmaVerificada]:
    """Verifica criptográficamente cada firma del PDF, en el orden en que se aplicaron."""
    lector = _abrir_lector(contenido)
    firmas = sorted(lector.embedded_signatures, key=lambda f: int(f.byte_range[-2]) + int(f.byte_range[-1]))
    resultado = []
    for orden, firma in enumerate(firmas, start=1):
        rango = [int(x) for x in firma.byte_range]
        fin_revision = rango[2] + rango[3]
        contexto = ValidationContext(trust_roots=list(raices), allow_fetching=False)
        try:
            estado = validate_pdf_signature(firma, contexto)
            integra = bool(estado.intact and estado.valid
                           and estado.modification_level != ModificationLevel.OTHER)
            confiable = bool(raices) and integra and estado.trusted
            fecha = estado.signer_reported_dt
        except Exception:
            integra = confiable = False
            fecha = None
        motivo = firma.sig_object.get("/Reason")
        resultado.append(FirmaVerificada(
            numero_orden=orden,
            nombre_campo=str(firma.field_name),
            certificado=datos_certificado(firma.signer_cert),
            fecha_firma=fecha or firma.self_reported_timestamp or datetime.now(timezone.utc),
            motivo=str(motivo)[:255] if motivo else None,
            hash_documento=hashlib.sha256(contenido[:fin_revision]).hexdigest(),
            es_integra=integra,
            es_confiable=confiable,
        ))
    return resultado


# ------------------------------------------------- cambios acordados en el PDF
def _palabras(texto: str) -> list[str]:
    """Palabras en minúsculas y sin tildes; los saltos de línea y guiones del PDF no importan."""
    sin_tildes = unicodedata.normalize("NFKD", texto.lower()).encode("ascii", "ignore").decode()
    return re.findall(r"[a-z0-9]+", sin_tildes)


def cobertura_texto(acordado: str, documento: str) -> float:
    """Fracción del texto acordado que aparece en el documento, en el mismo orden (0 a 1)."""
    buscadas = _palabras(acordado)
    if not buscadas:
        return 1.0
    comparador = SequenceMatcher(None, _palabras(documento), buscadas, autojunk=False)
    coincidentes = sum(b.size for b in comparador.get_matching_blocks() if b.size >= 3)
    return coincidentes / len(buscadas)