"""Informe PDF del análisis de un contrato.

Se arma un HTML sencillo y PyMuPDF (Story) lo distribuye en páginas A4. Al final se
agrega a cada página el pie "Informe generado el … · Página i de n". El archivo se
guarda en storage/reportes con su hash SHA-256 y se registra en con_reporte.
"""

import hashlib
import uuid
from datetime import datetime, timedelta, timezone
from html import escape
from io import BytesIO
from pathlib import Path

import pymupdf
from fastapi import Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.constantes import ACC_DESCARGA_REPORTE, CAT_COBERTURA_CONDICION, CAT_ESTADO_CONTRAPROPUESTA
from app.models import (
    ESTADO_ACTIVO,
    CatalogoDetalle,
    Clausula,
    Condicion,
    Contrapropuesta,
    Contrato,
    NivelRiesgo,
    Reporte,
    Usuario,
)
from app.services.auditoria import registrar_evento
from app.services.catalogos import listar_detalles
from app.services.negociacion import _exigir_analizado, _normas, _tipo_y_rol

ZONA = timezone(timedelta(hours=-5), "ECT")  # Ecuador continental, sin horario de verano
MARGEN = 50  # puntos (1 pt = 1/72 pulgada)
ALTO_PIE = 24

CSS = """
body { font-family: sans-serif; font-size: 10pt; color: #1e293b; line-height: 1.35; }
h1 { font-size: 18pt; color: #0f172a; margin: 0 0 4pt 0; }
h2 { font-size: 13pt; color: #0f172a; margin: 14pt 0 6pt 0; }
h3 { font-size: 11pt; margin: 10pt 0 2pt 0; }
p { margin: 0 0 5pt 0; }
.gris { color: #64748b; font-size: 9pt; }
.cita { color: #334155; font-size: 9pt; margin-left: 10pt; }
.propuesta { margin-left: 10pt; }
.aviso { font-size: 8.5pt; color: #64748b; margin-top: 14pt; }
table { border-collapse: collapse; width: 100%; }
td, th { border: 1px solid #cbd5e1; padding: 3pt 5pt; font-size: 9.5pt; text-align: left; }
th { background-color: #f1f5f9; }
"""

AVISO_LEGAL = (
    "Este informe fue generado automáticamente a partir del contrato cargado y de un corpus de "
    "normas ecuatorianas. Es una herramienta de apoyo para revisar y negociar el contrato y no "
    "constituye asesoría legal. Ante dudas importantes, consulte con un abogado."
)


def _e(texto: str | None) -> str:
    """Escapa el texto para el HTML y respeta los saltos de línea."""
    return escape(texto or "").replace("\n", "<br/>")


def _color(texto: str, color: str) -> str:
    return f'<b style="color:{escape(color)}">{_e(texto)}</b>'


def _html(db: Session, usuario: Usuario, contrato: Contrato) -> str:
    tipo, _ = _tipo_y_rol(db, contrato)
    rol = db.get(CatalogoDetalle, contrato.id_rol_parte) if contrato.id_rol_parte else None
    niveles = list(db.scalars(
        select(NivelRiesgo).where(NivelRiesgo.estado == ESTADO_ACTIVO).order_by(NivelRiesgo.orden)))
    nivel_por_id = {n.id_nivel_riesgo: n for n in niveles}
    categorias = {d.id_catalogo_detalle: d.nombre for d in db.scalars(select(CatalogoDetalle))}
    estados_cp = {d.id_catalogo_detalle: d for d in listar_detalles(db, CAT_ESTADO_CONTRAPROPUESTA)}

    clausulas = list(db.scalars(
        select(Clausula)
        .where(Clausula.id_contrato == contrato.id_contrato, Clausula.estado == ESTADO_ACTIVO)
        .order_by(Clausula.numero_orden)))
    ids = [c.id_clausula for c in clausulas]
    normas = _normas(db, ids)
    contrapropuestas = {
        cp.id_clausula: cp for cp in db.scalars(
            select(Contrapropuesta).where(Contrapropuesta.id_clausula.in_(ids),
                                          Contrapropuesta.estado == ESTADO_ACTIVO))
    } if ids else {}

    h: list[str] = []
    # -------------------------------------------------------- encabezado
    h.append("<h1>Informe de riesgos del contrato</h1>")
    h.append(f'<p class="gris">{_e(contrato.nombre_archivo)}</p>')
    datos = [
        ("Tipo de contrato", tipo),
        ("Papel del usuario", rol.nombre if rol else "No indicado"),
        ("Revisado por", f"{usuario.nombres} {usuario.apellidos}"
         + (f" ({usuario.nombre_empresa})" if usuario.nombre_empresa else "")),
        ("Páginas / cláusulas", f"{contrato.numero_paginas} / {len(clausulas)}"),
        ("Fecha del análisis", contrato.fecha_analisis.astimezone(ZONA).strftime("%d/%m/%Y %H:%M")
         if contrato.fecha_analisis else "—"),
    ]
    h.append("<table>" + "".join(f"<tr><th>{_e(k)}</th><td>{_e(v)}</td></tr>" for k, v in datos) + "</table>")

    # ------------------------------------------------------ puntaje y conteo
    puntaje = float(contrato.puntaje_riesgo_global or 0)
    h.append("<h2>Resultado</h2>")
    conteo = {n.id_nivel_riesgo: 0 for n in niveles}
    for c in clausulas:
        if c.id_nivel_riesgo in conteo:
            conteo[c.id_nivel_riesgo] += 1
    h.append(f"<p>Puntaje de riesgo global: <b>{puntaje:.0f} / 100</b> (0 = sin riesgo, 100 = máximo riesgo).</p>")
    h.append("<table><tr>" + "".join(f"<th>{_color(n.nombre, n.color_hex)}</th>" for n in niveles) + "</tr><tr>"
             + "".join(f"<td>{conteo[n.id_nivel_riesgo]}</td>" for n in niveles) + "</tr></table>")
    if contrato.resumen:
        h.append(f"<p>{_e(contrato.resumen)}</p>")

    # ----------------------------------------------------------- condiciones
    cobertura = {d.id_catalogo_detalle: d for d in listar_detalles(db, CAT_COBERTURA_CONDICION)}
    condiciones = list(db.scalars(
        select(Condicion)
        .where(Condicion.id_contrato == contrato.id_contrato, Condicion.estado == ESTADO_ACTIVO)
        .order_by(Condicion.numero_orden)))
    if condiciones:
        h.append("<h2>Lo que indicaste que acordaron</h2>")
        filas = []
        for cond in condiciones:
            cob = cobertura.get(cond.id_cobertura)
            estado = _color(cob.nombre, cob.valor or "#64748B") if cob else "—"
            filas.append(f"<tr><td>{_e(cond.descripcion)}</td><td>{estado}</td><td>{_e(cond.explicacion)}</td></tr>")
        h.append("<table><tr><th>Condición</th><th>En el contrato</th><th>Detalle</th></tr>"
                 + "".join(filas) + "</table>")

    # ------------------------------------------------------ cláusulas riesgosas
    riesgosas = [c for c in clausulas if c.id_nivel_riesgo in nivel_por_id
                 and nivel_por_id[c.id_nivel_riesgo].codigo != "BAJO"]
    riesgosas.sort(key=lambda c: (-nivel_por_id[c.id_nivel_riesgo].peso, c.numero_orden))
    h.append("<h2>Cláusulas que conviene negociar</h2>")
    if not riesgosas:
        h.append("<p>No se detectaron cláusulas de riesgo alto ni con advertencia.</p>")
    for c in riesgosas:
        nivel = nivel_por_id[c.id_nivel_riesgo]
        nombre = f"Cláusula {c.numero_orden}" + (f": {c.titulo}" if c.titulo else "")
        categoria = categorias.get(c.id_categoria_riesgo) if c.id_categoria_riesgo else None
        h.append(f"<h3>{_e(nombre)}</h3>")
        h.append(f"<p>{_color(nivel.nombre, nivel.color_hex)}"
                 + (f" · {_e(categoria)}" if categoria else "")
                 + f' <span class="gris">(página {c.numero_pagina})</span></p>')
        h.append(f'<p class="cita">{_e(c.contenido[:1500])}{"…" if len(c.contenido) > 1500 else ""}</p>')
        if c.explicacion:
            h.append(f"<p><b>Por qué:</b> {_e(c.explicacion)}</p>")
        citadas = normas.get(c.id_clausula, [])
        if citadas:
            fuentes = "; ".join(n.titulo_documento + (f", {n.articulo_referencia}" if n.articulo_referencia else "")
                                for n in citadas)
            h.append(f'<p class="gris"><b>Normas consideradas:</b> {_e(fuentes)}</p>')
        else:
            h.append('<p class="gris">Evaluada con criterios generales de equidad contractual.</p>')
        cp = contrapropuestas.get(c.id_clausula)
        if cp:
            estado = estados_cp.get(cp.id_estado_contrapropuesta)
            etiqueta = _color(estado.nombre, estado.valor or "#2563EB") if estado else ""
            h.append(f"<p><b>Contrapropuesta</b> {etiqueta}</p>")
            h.append(f'<p class="propuesta">{_e(cp.texto_acordado or cp.texto_propuesto)}</p>')
            if cp.justificacion:
                h.append(f'<p class="gris propuesta">{_e(cp.justificacion)}</p>')

    # ------------------------------------------------------- cláusulas seguras
    seguras = [c for c in clausulas if c not in riesgosas]
    if seguras:
        h.append("<h2>Cláusulas sin observaciones</h2><ul>")
        h.extend(f"<li>Cláusula {c.numero_orden}" + (f": {_e(c.titulo)}" if c.titulo else "") + "</li>"
                 for c in seguras)
        h.append("</ul>")

    h.append(f'<p class="aviso">{_e(AVISO_LEGAL)}</p>')
    return "<body>" + "".join(h) + "</body>"


def _pdf(html: str, pie: str) -> bytes:
    """Distribuye el HTML en páginas A4 y agrega el pie con el número de página."""
    pagina = pymupdf.paper_rect("a4")
    area = pagina + (MARGEN, MARGEN, -MARGEN, -MARGEN - ALTO_PIE)
    story = pymupdf.Story(html=html, user_css=CSS)
    salida = BytesIO()
    escritor = pymupdf.DocumentWriter(salida)
    hay_mas = True
    while hay_mas:
        dispositivo = escritor.begin_page(pagina)
        hay_mas, _ = story.place(area)
        story.draw(dispositivo)
        escritor.end_page()
    escritor.close()

    documento = pymupdf.open("pdf", salida.getvalue())
    total = documento.page_count
    for i, hoja in enumerate(documento, start=1):
        hoja.insert_text(
            (MARGEN, hoja.rect.height - MARGEN + 10),
            f"{pie} - Página {i} de {total}",
            fontsize=8, fontname="helv", color=(0.39, 0.45, 0.55),
        )
    documento.set_metadata({"title": "Informe de riesgos del contrato", "creator": "PRY-Contratos"})
    datos = documento.tobytes(garbage=3, deflate=True)
    documento.close()
    return datos


def generar_reporte(db: Session, request: Request, usuario: Usuario, contrato: Contrato) -> Reporte:
    """Genera el informe PDF, lo guarda y lo registra. Devuelve la fila de con_reporte."""
    _exigir_analizado(db, contrato)
    ahora = datetime.now(timezone.utc)
    pie = f"Informe generado el {ahora.astimezone(ZONA).strftime('%d/%m/%Y %H:%M')}"
    contenido = _pdf(_html(db, usuario, contrato), pie)

    carpeta = Path(settings.directorio_archivos) / "reportes"
    carpeta.mkdir(parents=True, exist_ok=True)
    ruta = carpeta / f"{uuid.uuid4().hex}.pdf"
    ruta.write_bytes(contenido)

    base = Path(contrato.nombre_archivo).stem[:200] or "contrato"
    try:
        reporte = Reporte(
            id_contrato=contrato.id_contrato,
            nombre_archivo=f"Informe - {base}.pdf",
            ruta_archivo=ruta.as_posix(),
            hash_archivo=hashlib.sha256(contenido).hexdigest(),
            usuario_creacion=usuario.id_usuario,
        )
        db.add(reporte)
        db.flush()
        registrar_evento(
            db, request, ACC_DESCARGA_REPORTE,
            usuario=usuario,
            tabla_afectada="con_reporte",
            id_registro=reporte.id_reporte,
            datos_nuevos={"contrato": contrato.id_contrato, "bytes": len(contenido),
                          "hash": reporte.hash_archivo},
        )
        db.commit()
    except Exception:
        db.rollback()
        ruta.unlink(missing_ok=True)
        raise
    db.refresh(reporte)
    return reporte