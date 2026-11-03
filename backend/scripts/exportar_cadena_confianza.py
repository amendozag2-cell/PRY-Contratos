"""Copia a certificados_confianza/ los certificados PÚBLICOS de la entidad de certificación
(raíz e intermedios) que vienen dentro de un .p12. No exporta la clave privada.

Úselo con un certificado real emitido por una entidad acreditada (Banco Central, Security Data,
Uanataca, etc.) para que el sistema reconozca a esa entidad al verificar firmas.

Uso (desde backend/):
    uv run python scripts/exportar_cadena_confianza.py "C:/ruta/mi_firma.p12" "MiClave"
"""

import sys
from pathlib import Path

from cryptography.hazmat.primitives.serialization import Encoding, pkcs12
from cryptography.x509.oid import NameOID

DESTINO = Path(__file__).resolve().parents[1] / "certificados_confianza"


def main(ruta_p12: str, clave: str) -> None:
    _, _, cadena = pkcs12.load_key_and_certificates(Path(ruta_p12).read_bytes(), clave.encode("utf-8"))
    if not cadena:
        print("El .p12 no trae los certificados de la entidad. Descárguelos de la página oficial de la entidad.")
        return
    DESTINO.mkdir(exist_ok=True)
    for certificado in cadena:
        nombres = certificado.subject.get_attributes_for_oid(NameOID.COMMON_NAME)
        nombre = str(nombres[0].value) if nombres else f"entidad_{certificado.serial_number:x}"
        archivo = DESTINO / ("".join(c if c.isalnum() else "_" for c in nombre)[:80] + ".crt")
        archivo.write_bytes(certificado.public_bytes(Encoding.PEM))
        print(f"Guardado: {archivo.name}  ({nombre})")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(1)
    main(sys.argv[1], sys.argv[2])