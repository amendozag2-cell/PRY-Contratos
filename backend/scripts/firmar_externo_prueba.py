"""Simula que la otra parte firma el contrato FUERA de la plataforma (como haría con FirmaEC).

Toma el PDF descargado con "Descargar PDF", lo firma con un certificado .p12 de prueba y guarda
una copia firmada, que luego se sube con "Subir PDF firmado con FirmaEC".

Uso (desde backend/):
    uv run python scripts/firmar_externo_prueba.py "PDF_DESCARGADO.pdf" "CERTIFICADO.p12" "CLAVE"

Genera, junto al PDF original, el archivo "<nombre> - firmado externo.pdf".
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.firma_pdf import (  # noqa: E402
    ErrorFirma,
    caja_firma,
    firmar_pdf,
    leer_certificado_p12,
    nombres_campos,
    numero_firmas,
    tiene_hoja_firmas,
)


def main(ruta_pdf: str, ruta_p12: str, clave: str) -> None:
    pdf = Path(ruta_pdf)
    contenido = pdf.read_bytes()
    try:
        cargado = leer_certificado_p12(Path(ruta_p12).read_bytes(), clave)
        numero = numero_firmas(contenido) + 1
        campo = f"FirmaExterna{numero}"
        while campo in nombres_campos(contenido):
            campo += "_"
        firmado = firmar_pdf(
            contenido, cargado,
            motivo="Firmado fuera de la plataforma (simulación de FirmaEC)",
            nombre_campo=campo,
            caja=caja_firma(numero) if tiene_hoja_firmas(contenido) else None,
        )
    except ErrorFirma as error:
        print(f"Error: {error}")
        sys.exit(1)
    destino = pdf.with_name(f"{pdf.stem} - firmado externo.pdf")
    destino.write_bytes(firmado)
    print(f"Firmado por {cargado.datos.nombre_titular}: {destino}")


if __name__ == "__main__":
    if len(sys.argv) != 4:
        print(__doc__)
        sys.exit(1)
    main(sys.argv[1], sys.argv[2], sys.argv[3])