"""Crea un certificado .p12 de PRUEBA para probar la firma electrónica sin un certificado real.

El certificado es emitido por una "CA de prueba" que no está acreditada: las firmas hechas con él
serán íntegras pero NO confiables (salvo que copie ca_prueba.crt a certificados_confianza/).

Uso (desde backend/):
    uv run python scripts/crear_certificado_prueba.py "NOMBRE APELLIDO" 0912345678 MiClave123

Genera en la carpeta indicada (por defecto ../../certificados_prueba, FUERA del repositorio):
    <cedula>.p12   certificado del firmante con su clave privada
    ca_prueba.crt  certificado de la CA de prueba (público)
Nunca suba archivos .p12 a GitHub.
"""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.x509.oid import NameOID


def _nombre(cn: str, serie: str | None = None) -> x509.Name:
    atributos = [
        x509.NameAttribute(NameOID.COUNTRY_NAME, "EC"),
        x509.NameAttribute(NameOID.COMMON_NAME, cn),
    ]
    if serie:
        atributos.append(x509.NameAttribute(NameOID.SERIAL_NUMBER, serie))
    return x509.Name(atributos)


def crear(nombre: str, cedula: str, clave: str, carpeta: Path) -> Path:
    carpeta.mkdir(parents=True, exist_ok=True)
    ahora = datetime.now(timezone.utc)

    # CA de prueba (se reutiliza si ya existe)
    ruta_ca, ruta_llave_ca = carpeta / "ca_prueba.crt", carpeta / "ca_prueba.key"
    if ruta_ca.exists() and ruta_llave_ca.exists():
        ca = x509.load_pem_x509_certificate(ruta_ca.read_bytes())
        llave_ca = serialization.load_pem_private_key(ruta_llave_ca.read_bytes(), None)
    else:
        llave_ca = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        nombre_ca = _nombre("CA DE PRUEBA - PRY CONTRATOS")
        ca = (
            x509.CertificateBuilder()
            .subject_name(nombre_ca).issuer_name(nombre_ca)
            .public_key(llave_ca.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(ahora - timedelta(days=1))
            .not_valid_after(ahora + timedelta(days=3650))
            .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
            .add_extension(x509.KeyUsage(False, False, False, False, False, True, True, False, False), critical=True)
            .sign(llave_ca, hashes.SHA256())
        )
        ruta_ca.write_bytes(ca.public_bytes(serialization.Encoding.PEM))
        ruta_llave_ca.write_bytes(llave_ca.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))

    # Certificado del firmante, uso: firma digital y no repudio
    llave = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    certificado = (
        x509.CertificateBuilder()
        .subject_name(_nombre(nombre.upper(), cedula)).issuer_name(ca.subject)
        .public_key(llave.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(ahora - timedelta(days=1))
        .not_valid_after(ahora + timedelta(days=730))
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(x509.KeyUsage(True, True, False, False, False, False, False, False, False), critical=True)
        .sign(llave_ca, hashes.SHA256())
    )
    p12 = pkcs12.serialize_key_and_certificates(
        name=nombre.encode(), key=llave, cert=certificado, cas=[ca],
        encryption_algorithm=serialization.BestAvailableEncryption(clave.encode()),
    )
    ruta = carpeta / f"{cedula}.p12"
    ruta.write_bytes(p12)
    return ruta


if __name__ == "__main__":
    if len(sys.argv) < 4:
        print(__doc__)
        sys.exit(1)
    destino = Path(sys.argv[4]) if len(sys.argv) > 4 else Path(__file__).resolve().parents[2].parent / "certificados_prueba"
    archivo = crear(sys.argv[1], sys.argv[2], sys.argv[3], destino)
    print(f"Certificado de prueba creado: {archivo}")
    print(f"CA de prueba: {destino / 'ca_prueba.crt'}")