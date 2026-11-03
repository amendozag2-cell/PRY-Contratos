"""Negociación del contrato: contrapropuestas por cláusula y correo para la otra parte.

1. Para cada cláusula de riesgo ALTO o MEDIO el LLM redacta una versión alternativa
   que conserva el propósito legítimo de la cláusula pero corrige el desequilibrio,
   apoyándose en el diagnóstico y en las normas citadas en el análisis.
2. El usuario registra qué pasó con cada propuesta: aceptada, aceptada con cambios
   (texto acordado) o rechazada.
3. El LLM redacta un correo con los cambios que se piden; el usuario lo copia y lo envía.
"""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.constantes import (
    ACC_GENERACION_CONTRAPROPUESTA,
    ACC_GENERACION_CORREO,
    ACC_RESPUESTA_CONTRAPROPUESTA,
    CAT_COBERTURA_CONDICION,
    CAT_ESTADO_ANALISIS,
    CAT_ESTADO_CONTRAPROPUESTA,
    CAT_TONO_CORREO,
    CP_GENERADA,
    CP_MODIFICADA,
    CP_RECHAZADA,
    EST_ANALIZADO,
    PAR_LLM_MODELO,
)
from app.models import (
    ESTADO_ACTIVO,
    CatalogoDetalle,
    Clausula,
    ClausulaFundamento,
    Condicion,
    Contrapropuesta,
    Contrato,
    CorreoNegociacion,
    DocumentoRag,
    FragmentoRag,
    NivelRiesgo,
    Usuario,
)
from app.services.analisis import MAX_CARACTERES_CONTEXTO, MAX_CARACTERES_FRAGMENTO, _perfil, _texto_clausula
from app.services.auditoria import registrar_evento
from app.services.catalogos import listar_detalles, obtener_id_detalle
from app.services.llm import ContrapropuestaGenerada, CorreoGenerado, generar_estructurado
from app.services.parametros import obtener_parametro

MAX_HILOS = 8
NIVELES_NEGOCIABLES = ("ALTO", "MEDIO")

INSTRUCCIONES_CONTRAPROPUESTA = """Eres un abogado que ayuda a freelancers y pequeñas y medianas empresas (PYMEs) de Ecuador a negociar contratos de servicios. Recibes UNA cláusula que el análisis marcó como riesgosa para el usuario y debes redactar una versión alternativa que el usuario pueda proponer a la otra parte.

Reglas:
1. Conserva el propósito legítimo de la cláusula (lo que la otra parte razonablemente necesita) y corrige solo lo que perjudica al usuario según el diagnóstico.
2. Redacta "texto_propuesto" con el estilo de un contrato: tercera persona, mismas denominaciones de las partes que usa el contrato (por ejemplo "EL CONTRATANTE", "EL PRESTADOR"), sin explicaciones ni comentarios dentro del texto. Debe poder reemplazar a la cláusula original tal cual.
3. Si la cláusula tiene título, no lo repitas en "texto_propuesto".
4. Propón soluciones concretas y equilibradas: plazos y montos determinados, límites a multas, preaviso, pago de lo ejecutado, licencias en lugar de cesiones totales, etc.
5. Si el usuario describió lo que acordaron, haz que la cláusula lo refleje.
6. Puedes apoyarte en las normas indicadas, pero no inventes leyes ni artículos que no aparezcan en el mensaje.
7. En "justificacion" explica en español sencillo, en máximo tres oraciones, qué cambia y por qué es más justo, de modo que el usuario pueda defenderlo ante la otra parte.
8. Esta propuesta es una ayuda para negociar y no constituye asesoría legal."""

INSTRUCCIONES_CORREO = """Redactas correos de negociación de contratos en nombre de un freelancer o de una pequeña o mediana empresa (PYME) de Ecuador. El usuario copiará el correo y lo enviará él mismo a la otra parte.

Reglas:
1. Escribe en español, con tono {tono}.
2. Agradece la propuesta de contrato y expresa interés en trabajar juntos.
3. Explica que, al revisar el contrato, el usuario quisiera ajustar algunos puntos antes de firmarlo.
4. Presenta los cambios como una lista numerada: para cada uno, la cláusula a la que se refiere, qué se pide cambiar y la razón en una oración. Si hay redacción propuesta, inclúyela entre comillas.
5. Si se incluyen condiciones acordadas que no aparecen en el contrato, pide que se incorporen.
6. Cierra ofreciendo conversar los cambios y firma con el nombre del usuario.
7. No menciones inteligencia artificial, sistemas automáticos ni análisis de riesgo. No amenaces ni uses lenguaje agresivo. No uses markdown (ni asteriscos, ni almohadillas).
8. El asunto debe ser breve y referirse a la revisión del contrato."""

TONOS = {
    "FORMAL": "formal y respetuoso, tratando de usted",
    "CORDIAL": "cordial y cercano, pero profesional",
}


class ErrorNegociacion(Exception):
    """La negociación no se puede realizar en el estado actual del contrato."""


@dataclass
class Norma:
    titulo_documento: str
    articulo_referencia: str | None
    contenido: str


def _modelo(db: Session) -> str:
    return obtener_parametro(db, PAR_LLM_MODELO, "gpt-5.4-mini")


def _exigir_analizado(db: Session, contrato: Contrato) -> None:
    if contrato.id_estado_analisis != obtener_id_detalle(db, CAT_ESTADO_ANALISIS, EST_ANALIZADO):
        raise ErrorNegociacion("Primero debe analizar el contrato")


def _tipo_y_rol(db: Session, contrato: Contrato) -> tuple[str, str | None]:
    tipo = db.scalar(select(CatalogoDetalle.nombre).where(
        CatalogoDetalle.id_catalogo_detalle == contrato.id_tipo_contrato)) or "no indicado"
    rol = db.scalar(select(CatalogoDetalle.codigo).where(
        CatalogoDetalle.id_catalogo_detalle == contrato.id_rol_parte)) if contrato.id_rol_parte else None
    return tipo, rol


def _clausulas_riesgosas(db: Session, contrato: Contrato) -> list[tuple[Clausula, NivelRiesgo, str | None]]:
    """Cláusulas ALTO y MEDIO con su nivel y el nombre de su categoría."""
    filas = db.execute(
        select(Clausula, NivelRiesgo, CatalogoDetalle.nombre)
        .join(NivelRiesgo, NivelRiesgo.id_nivel_riesgo == Clausula.id_nivel_riesgo)
        .outerjoin(CatalogoDetalle, CatalogoDetalle.id_catalogo_detalle == Clausula.id_categoria_riesgo)
        .where(
            Clausula.id_contrato == contrato.id_contrato,
            Clausula.estado == ESTADO_ACTIVO,
            NivelRiesgo.codigo.in_(NIVELES_NEGOCIABLES),
        )
        .order_by(Clausula.numero_orden)
    ).all()
    return [(c, n, cat) for c, n, cat in filas]


def _normas(db: Session, ids: list[int]) -> dict[int, list[Norma]]:
    """Normas que el análisis citó para cada cláusula."""
    normas: dict[int, list[Norma]] = {}
    if not ids:
        return normas
    for id_clausula, titulo, articulo, contenido in db.execute(
        select(ClausulaFundamento.id_clausula, DocumentoRag.titulo,
               FragmentoRag.articulo_referencia, FragmentoRag.contenido)
        .join(FragmentoRag, FragmentoRag.id_fragmento == ClausulaFundamento.id_fragmento)
        .join(DocumentoRag, DocumentoRag.id_documento == FragmentoRag.id_documento)
        .where(ClausulaFundamento.id_clausula.in_(ids), ClausulaFundamento.estado == ESTADO_ACTIVO)
        .order_by(ClausulaFundamento.similitud.desc())
    ).all():
        normas.setdefault(id_clausula, []).append(Norma(titulo, articulo, contenido))
    return normas


def _mensaje_contrapropuesta(perfil: str, tipo: str, acordado: str, clausula: Clausula,
                             nivel: str, categoria: str | None, normas: list[Norma]) -> str:
    partes = [f"Perfil del usuario: {perfil}", f"Tipo de contrato: {tipo}"]
    if acordado:
        partes += ["", "LO QUE EL USUARIO DICE QUE ACORDARON:", acordado]
    partes += [
        "",
        "CLÁUSULA ORIGINAL:",
        _texto_clausula(clausula),
        "",
        f"DIAGNÓSTICO: riesgo {nivel}" + (f" ({categoria})" if categoria else ""),
        clausula.explicacion or "(sin explicación)",
        "",
        "NORMAS CITADAS EN EL ANÁLISIS:",
    ]
    if not normas:
        partes.append("(ninguna; usa criterios generales de equidad contractual)")
    for i, n in enumerate(normas, start=1):
        fuente = n.titulo_documento + (f", {n.articulo_referencia}" if n.articulo_referencia else "")
        partes.append(f"[{i}] {fuente}")
        partes.append(n.contenido[:MAX_CARACTERES_FRAGMENTO])
    return "\n".join(partes)


def generar_contrapropuestas(db: Session, request: Request, usuario: Usuario, contrato: Contrato,
                             ids: list[int] | None = None) -> int:
    """Redacta contrapropuestas para las cláusulas riesgosas (o solo para `ids`).

    Si una cláusula ya tenía contrapropuesta, se reemplaza y vuelve al estado "Propuesta".
    Devuelve cuántas se generaron.
    """
    _exigir_analizado(db, contrato)
    riesgosas = _clausulas_riesgosas(db, contrato)
    if ids is not None:
        pedidas = set(ids)
        riesgosas = [r for r in riesgosas if r[0].id_clausula in pedidas]
    if not riesgosas:
        raise ErrorNegociacion("No hay cláusulas de riesgo alto o medio para negociar")

    modelo = _modelo(db)
    tipo, rol = _tipo_y_rol(db, contrato)
    perfil = _perfil(usuario, rol)
    acordado = (contrato.contexto_usuario or "").strip()[:MAX_CARACTERES_CONTEXTO]
    normas = _normas(db, [c.id_clausula for c, _, _ in riesgosas])
    mensajes = [
        _mensaje_contrapropuesta(perfil, tipo, acordado, c, n.nombre, cat, normas.get(c.id_clausula, []))
        for c, n, cat in riesgosas
    ]

    with ThreadPoolExecutor(max_workers=MAX_HILOS) as ejecutor:
        futuros = [
            ejecutor.submit(generar_estructurado, modelo, INSTRUCCIONES_CONTRAPROPUESTA, m, ContrapropuestaGenerada)
            for m in mensajes
        ]
        generadas = [f.result() for f in futuros]

    id_generada = obtener_id_detalle(db, CAT_ESTADO_CONTRAPROPUESTA, CP_GENERADA)
    existentes = {
        cp.id_clausula: cp for cp in db.scalars(
            select(Contrapropuesta).where(Contrapropuesta.id_clausula.in_([c.id_clausula for c, _, _ in riesgosas]))
        )
    }
    ahora = datetime.now(timezone.utc)
    for (clausula, _, _), generada in zip(riesgosas, generadas, strict=True):
        cp = existentes.get(clausula.id_clausula)
        if cp is None:
            db.add(Contrapropuesta(
                id_clausula=clausula.id_clausula,
                id_estado_contrapropuesta=id_generada,
                texto_propuesto=generada.texto_propuesto.strip(),
                justificacion=generada.justificacion.strip(),
                modelo_llm=modelo,
                usuario_creacion=usuario.id_usuario,
            ))
        else:
            cp.id_estado_contrapropuesta = id_generada
            cp.texto_propuesto = generada.texto_propuesto.strip()
            cp.texto_acordado = None
            cp.justificacion = generada.justificacion.strip()
            cp.modelo_llm = modelo
            cp.estado = ESTADO_ACTIVO
            cp.usuario_modificacion = usuario.id_usuario
            cp.fecha_modificacion = ahora

    registrar_evento(
        db, request, ACC_GENERACION_CONTRAPROPUESTA,
        usuario=usuario,
        tabla_afectada="con_contrapropuesta",
        id_registro=contrato.id_contrato,
        datos_nuevos={
            "contrato": contrato.id_contrato,
            "clausulas": [c.numero_orden for c, _, _ in riesgosas],
            "reemplazadas": len(existentes),
            "modelo": modelo,
        },
    )
    db.commit()
    return len(riesgosas)


def responder_contrapropuesta(db: Session, request: Request, usuario: Usuario, contrato: Contrato,
                              id_clausula: int, estado: str, texto_acordado: str | None) -> None:
    """Registra qué respondió la otra parte a la contrapropuesta de una cláusula."""
    cp = db.scalar(
        select(Contrapropuesta)
        .join(Clausula, Clausula.id_clausula == Contrapropuesta.id_clausula)
        .where(
            Contrapropuesta.id_clausula == id_clausula,
            Contrapropuesta.estado == ESTADO_ACTIVO,
            Clausula.id_contrato == contrato.id_contrato,
        )
    )
    if cp is None:
        raise LookupError("La cláusula no tiene contrapropuesta")
    texto_acordado = (texto_acordado or "").strip() or None
    if estado == CP_MODIFICADA and not texto_acordado:
        raise ErrorNegociacion("Escriba el texto que finalmente acordaron")

    anterior = db.scalar(select(CatalogoDetalle.codigo).where(
        CatalogoDetalle.id_catalogo_detalle == cp.id_estado_contrapropuesta))
    cp.id_estado_contrapropuesta = obtener_id_detalle(db, CAT_ESTADO_CONTRAPROPUESTA, estado)
    cp.texto_acordado = texto_acordado if estado == CP_MODIFICADA else None
    cp.usuario_modificacion = usuario.id_usuario
    cp.fecha_modificacion = datetime.now(timezone.utc)
    registrar_evento(
        db, request, ACC_RESPUESTA_CONTRAPROPUESTA,
        usuario=usuario,
        tabla_afectada="con_contrapropuesta",
        id_registro=cp.id_contrapropuesta,
        datos_anteriores={"estado": anterior},
        datos_nuevos={"estado": estado, "con_texto_acordado": cp.texto_acordado is not None},
    )
    db.commit()


# ---------------------------------------------------------------- correo
def _nombre_clausula(c: Clausula) -> str:
    return f"Cláusula {c.numero_orden}" + (f" ({c.titulo})" if c.titulo else "")


def _mensaje_correo(usuario: Usuario, perfil: str, contrato: Contrato, tipo: str, destinatario: str | None,
                    puntos: list[str], condiciones: list[str]) -> str:
    firma = f"{usuario.nombres} {usuario.apellidos}".strip()
    if usuario.nombre_empresa:
        firma += f", {usuario.nombre_empresa}"
    partes = [
        f"Remitente: {firma}",
        f"Perfil del remitente: {perfil}",
        f"Destinatario: {destinatario or 'la otra parte del contrato (sin nombre)'}",
        f"Contrato: {contrato.nombre_archivo} ({tipo})",
        "",
        "CAMBIOS QUE SE PIDEN:",
        *puntos,
    ]
    if condiciones:
        partes += ["", "CONDICIONES ACORDADAS QUE EL CONTRATO NO RECOGE BIEN:", *condiciones]
    return "\n".join(partes)


def generar_correo(db: Session, request: Request, usuario: Usuario, contrato: Contrato, *,
                   destinatario: str | None, tono: str, incluir_advertencias: bool,
                   incluir_condiciones: bool) -> CorreoNegociacion:
    """Redacta el correo con los cambios pedidos y lo guarda en el historial."""
    _exigir_analizado(db, contrato)
    if tono not in TONOS:
        raise ErrorNegociacion("El tono del correo no es válido")

    niveles = ("ALTO", "MEDIO") if incluir_advertencias else ("ALTO",)
    riesgosas = [r for r in _clausulas_riesgosas(db, contrato) if r[1].codigo in niveles]
    estados = {d.id_catalogo_detalle: d.codigo for d in listar_detalles(db, CAT_ESTADO_CONTRAPROPUESTA)}
    contrapropuestas = {
        cp.id_clausula: cp for cp in db.scalars(
            select(Contrapropuesta).where(
                Contrapropuesta.id_clausula.in_([c.id_clausula for c, _, _ in riesgosas]),
                Contrapropuesta.estado == ESTADO_ACTIVO,
            )
        )
    } if riesgosas else {}

    puntos: list[str] = []
    for clausula, _, categoria in riesgosas:
        cp = contrapropuestas.get(clausula.id_clausula)
        if cp and estados.get(cp.id_estado_contrapropuesta) == CP_RECHAZADA:
            continue  # la otra parte ya dijo que no: no se vuelve a pedir
        punto = f"- {_nombre_clausula(clausula)}"
        if categoria:
            punto += f" — tema: {categoria}"
        punto += f"\n  Problema: {clausula.explicacion or 'cláusula desfavorable'}"
        if cp:
            punto += f"\n  Redacción propuesta: {cp.texto_acordado or cp.texto_propuesto}"
            if cp.justificacion:
                punto += f"\n  Razón: {cp.justificacion}"
        puntos.append(punto)

    condiciones: list[str] = []
    if incluir_condiciones:
        cobertura = {d.id_catalogo_detalle: d for d in listar_detalles(db, CAT_COBERTURA_CONDICION)}
        for cond in db.scalars(
            select(Condicion)
            .where(Condicion.id_contrato == contrato.id_contrato, Condicion.estado == ESTADO_ACTIVO)
            .order_by(Condicion.numero_orden)
        ):
            cob = cobertura.get(cond.id_cobertura)
            if cob and cob.codigo != "CUBIERTA":
                linea = f"- {cond.descripcion} ({cob.nombre.lower()})"
                if cond.explicacion:
                    linea += f": {cond.explicacion}"
                condiciones.append(linea)

    if not puntos and not condiciones:
        raise ErrorNegociacion("No hay cambios que pedir: no quedan cláusulas riesgosas ni condiciones pendientes")

    modelo = _modelo(db)
    tipo, rol = _tipo_y_rol(db, contrato)
    destinatario = (destinatario or "").strip()[:150] or None
    generado = generar_estructurado(
        modelo,
        INSTRUCCIONES_CORREO.format(tono=TONOS[tono]),
        _mensaje_correo(usuario, _perfil(usuario, rol), contrato, tipo, destinatario, puntos, condiciones),
        CorreoGenerado,
    )

    correo = CorreoNegociacion(
        id_contrato=contrato.id_contrato,
        id_tono=obtener_id_detalle(db, CAT_TONO_CORREO, tono),
        destinatario=destinatario,
        asunto=generado.asunto.strip()[:255],
        cuerpo=generado.cuerpo.strip(),
        modelo_llm=modelo,
        usuario_creacion=usuario.id_usuario,
    )
    db.add(correo)
    db.flush()
    # Solo conteos: el texto del correo ya queda en con_correo_negociacion
    registrar_evento(
        db, request, ACC_GENERACION_CORREO,
        usuario=usuario,
        tabla_afectada="con_correo_negociacion",
        id_registro=correo.id_correo,
        datos_nuevos={
            "contrato": contrato.id_contrato,
            "tono": tono,
            "puntos": len(puntos),
            "condiciones": len(condiciones),
            "modelo": modelo,
        },
    )
    db.commit()
    db.refresh(correo)
    return correo


def listar_correos(db: Session, contrato: Contrato) -> list[tuple[CorreoNegociacion, CatalogoDetalle]]:
    return [
        (c, t) for c, t in db.execute(
            select(CorreoNegociacion, CatalogoDetalle)
            .join(CatalogoDetalle, CatalogoDetalle.id_catalogo_detalle == CorreoNegociacion.id_tono)
            .where(CorreoNegociacion.id_contrato == contrato.id_contrato,
                   CorreoNegociacion.estado == ESTADO_ACTIVO)
            .order_by(CorreoNegociacion.fecha_creacion.desc())
        ).all()
    ]