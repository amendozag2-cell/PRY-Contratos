"""Motor de diagnóstico: semáforo de riesgo de las cláusulas con RAG y LLM.

Para cada cláusula del contrato:
1. Se genera su embedding (text-embedding-3-small).
2. Se recuperan del corpus legal los fragmentos más parecidos (pgvector, coseno) y se
   descartan los que no llegan a la similitud mínima (parámetro RAG_SIMILITUD_MINIMA).
3. El LLM clasifica la cláusula en ALTO / MEDIO / BAJO desde el papel del usuario
   (presta o contrata el servicio) y lo que dice que acordaron, indica la categoría de
   riesgo, la explica y cita los fragmentos usados. Sin citas, la cláusula queda
   evaluada "por criterio general".
Además, si el usuario describió lo acordado, se verifica cada condición contra el
contrato (services/condiciones.py). Las llamadas al LLM se hacen en paralelo.
"""

import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone

from fastapi import Request
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.constantes import (
    ACC_ANALISIS_CONTRATO,
    CAT_CATEGORIA_RIESGO,
    CAT_COBERTURA_CONDICION,
    CAT_ESTADO_ANALISIS,
    EST_ANALIZADO,
    EST_ERROR,
    EST_PROCESANDO,
    FALLO,
    PAR_LLM_MODELO,
    PAR_PLAZO_PAGO,
    PAR_SIMILITUD_MINIMA,
    PAR_TIEMPO_MAX,
    PARTE_CONTRATANTE,
    PARTE_PRESTADOR,
    ROL_PYME,
)
from app.models import (
    ESTADO_ACTIVO,
    CatalogoDetalle,
    Clausula,
    ClausulaFundamento,
    Condicion,
    Contrato,
    DocumentoRag,
    FragmentoRag,
    NivelRiesgo,
    Usuario,
)
from app.services.auditoria import registrar_evento
from app.services.catalogos import listar_detalles, obtener_id_detalle
from app.services.condiciones import (
    INSTRUCCIONES_EXTRACCION,
    INSTRUCCIONES_VERIFICACION,
    MAX_CONDICIONES,
    clausulas_candidatas,
    mensaje_extraccion,
    mensaje_verificacion,
)
from app.services.corpus import leer_configuracion
from app.services.embeddings import generar_embeddings
from app.services.llm import (
    CondicionesExtraidas,
    VerificacionCondicion,
    clasificar_clausula,
    generar_estructurado,
)
from app.services.parametros import obtener_decimal, obtener_entero, obtener_parametro

MAX_HILOS = 8
MAX_CARACTERES_CLAUSULA = 6000
MAX_CARACTERES_FRAGMENTO = 1200
MAX_CARACTERES_CONTEXTO = 4000

INSTRUCCIONES = """Eres un analista jurídico que revisa contratos de servicios para freelancers y pequeñas y medianas empresas (PYMEs) de Ecuador. Evalúa UNA cláusula y clasifica su nivel de riesgo para el usuario que la está revisando.

Niveles:
- ALTO: la cláusula es desequilibrada o abusiva y puede causar un perjuicio grave al usuario. Ejemplos: cesión total o gratuita de la propiedad intelectual, multas sin límite, terminación unilateral sin pago de lo ejecutado, no competencia desproporcionada, plazos de pago excesivos o que dependen solo de la voluntad de la otra parte.
- MEDIO: la cláusula es ambigua, incompleta o algo desfavorable; conviene aclararla o negociarla.
- BAJO: la cláusula es equilibrada o meramente formal (identificación de las partes, jurisdicción, firmas, constancias).

Categorías permitidas (usa el código exacto):
{categorias}
- NINGUNA: la cláusula es de riesgo bajo o no encaja en las anteriores.

Reglas:
1. Evalúa SIEMPRE desde el papel del usuario en el contrato (presta o contrata el servicio): lo que favorece a una parte puede ser un riesgo para la otra.
2. Básate principalmente en las normas y buenas prácticas del CONTEXTO. En "fundamentos" pon los números de los fragmentos que realmente sustentan tu decisión y, si un fragmento corresponde a un artículo, menciónalo en la explicación.
3. No inventes leyes ni artículos que no aparezcan en el contexto. Si el contexto no es pertinente, decide con criterios generales de equidad contractual y deja "fundamentos" vacío.
4. Si el usuario describió lo que acordaron, señala cuando la cláusula se aparta de ello.
5. Si la relación tiene horario fijo, subordinación a órdenes, lugar de trabajo fijo y pago periódico, advierte que podría tratarse de una relación laboral encubierta bajo la forma de un contrato civil y usa la categoría RELACION_LABORAL en la cláusula que lo evidencie.
6. Un plazo de pago mayor a {plazo_pago} días, o sin fecha determinada, es un riesgo.
7. Escribe la explicación en español sencillo, para una persona sin formación jurídica, en máximo tres oraciones. Di qué problema tiene la cláusula y qué conviene negociar.
8. Esta evaluación es una ayuda y no constituye asesoría legal."""


class ErrorAnalisis(Exception):
    """El contrato no se puede analizar."""


@dataclass
class Recuperado:
    fragmento: FragmentoRag
    titulo_documento: str
    similitud: float


def _recuperar(db: Session, vector: list[float], limite: int, minima: float) -> list[Recuperado]:
    """Normas más parecidas a la cláusula que superan la similitud mínima."""
    distancia = FragmentoRag.embedding.cosine_distance(vector).label("distancia")
    filas = db.execute(
        select(FragmentoRag, DocumentoRag.titulo, distancia)
        .join(DocumentoRag, DocumentoRag.id_documento == FragmentoRag.id_documento)
        .where(FragmentoRag.estado == ESTADO_ACTIVO, DocumentoRag.estado == ESTADO_ACTIVO)
        .order_by(distancia)
        .limit(limite)
    ).all()
    recuperados = [Recuperado(f, t, round(1 - float(d), 4)) for f, t, d in filas]
    return [r for r in recuperados if r.similitud >= minima]


def _texto_clausula(clausula: Clausula) -> str:
    titulo = f"{clausula.titulo}\n" if clausula.titulo else ""
    return (titulo + clausula.contenido)[:MAX_CARACTERES_CLAUSULA]


def _mensaje(perfil: str, tipo: str, acordado: str, clausula: Clausula, contexto: list[Recuperado]) -> str:
    partes = [
        f"Perfil del usuario: {perfil}",
        f"Tipo de contrato: {tipo}",
    ]
    if acordado:
        partes += ["", "LO QUE EL USUARIO DICE QUE ACORDARON:", acordado]
    partes += [
        "",
        "CLÁUSULA A EVALUAR:",
        _texto_clausula(clausula),
        "",
        "CONTEXTO (normas y buenas prácticas recuperadas del corpus):",
    ]
    if not contexto:
        partes.append("(no hay normas del corpus relacionadas con esta cláusula)")
    for i, r in enumerate(contexto, start=1):
        fuente = r.titulo_documento
        if r.fragmento.articulo_referencia:
            fuente += f", {r.fragmento.articulo_referencia}"
        partes.append(f"[{i}] {fuente}")
        partes.append(r.fragmento.contenido[:MAX_CARACTERES_FRAGMENTO])
    return "\n".join(partes)


def _perfil(usuario: Usuario, rol_parte: str | None) -> str:
    if usuario.codigo_rol == ROL_PYME:
        empresa = f" ({usuario.nombre_empresa})" if usuario.nombre_empresa else ""
        quien = f"representante de una PYME{empresa}"
    else:
        quien = "freelancer o profesional independiente"
    if rol_parte == PARTE_PRESTADOR:
        return f"{quien}; en este contrato PRESTA el servicio: ejecuta el trabajo y recibe el pago"
    if rol_parte == PARTE_CONTRATANTE:
        return f"{quien}; en este contrato CONTRATA el servicio: recibe el trabajo y paga por él"
    if usuario.codigo_rol == ROL_PYME:
        return f"{quien} que revisa el contrato antes de firmarlo"
    return f"{quien}, normalmente quien presta el servicio"


def _calcular_puntaje(pesos: list[int]) -> float:
    """Puntaje global de 0 a 100: promedio de los pesos del semáforo de cada cláusula."""
    return round(sum(pesos) / len(pesos), 2) if pesos else 0.0


def _resumen(clausulas: list[Clausula], niveles: dict[int, NivelRiesgo], categorias: dict[int, str],
             sin_corpus: bool, respaldadas: int, coberturas: dict[str, int]) -> str:
    conteo = {n.codigo: 0 for n in niveles.values()}
    altos: list[str] = []
    for c in clausulas:
        nivel = niveles[c.id_nivel_riesgo]
        conteo[nivel.codigo] += 1
        if nivel.codigo == "ALTO":
            nombre = c.titulo or f"Cláusula {c.numero_orden}"
            categoria = categorias.get(c.id_categoria_riesgo)
            altos.append(f"{nombre} ({categoria})" if categoria else nombre)

    total = len(clausulas)
    seguras = conteo.get("BAJO", 0)
    texto = (
        f"Se {'analizó' if total == 1 else 'analizaron'} {total} {'cláusula' if total == 1 else 'cláusulas'}: "
        f"{conteo.get('ALTO', 0)} de riesgo alto, {conteo.get('MEDIO', 0)} con advertencia y "
        f"{seguras} {'segura' if seguras == 1 else 'seguras'}."
    )
    if altos:
        texto += " Revise antes de firmar: " + "; ".join(altos) + "."
    else:
        texto += " No se detectaron cláusulas de riesgo alto."

    if sin_corpus:
        texto += " Advertencia: el corpus legal está vacío, por lo que el análisis no cita normas."
    elif respaldadas == total:
        texto += " Respaldo legal: todas las cláusulas se evaluaron con normas del corpus."
    else:
        texto += (
            f" Respaldo legal: {respaldadas} de {total} se evaluaron con normas del corpus;"
            " las demás, con criterios generales de equidad."
        )

    if coberturas:
        total_condiciones = sum(coberturas.values())
        texto += (
            f" Condiciones que indicaste: {total_condiciones}; cubiertas {coberturas.get('CUBIERTA', 0)},"
            f" parciales {coberturas.get('PARCIAL', 0)}, contradichas {coberturas.get('CONTRADICHA', 0)}"
            f" y ausentes {coberturas.get('AUSENTE', 0)}."
        )
    return texto


def analizar_contrato(db: Session, request: Request, usuario: Usuario, contrato: Contrato) -> None:
    inicio = time.perf_counter()
    contrato.id_estado_analisis = obtener_id_detalle(db, CAT_ESTADO_ANALISIS, EST_PROCESANDO)
    db.commit()

    try:
        clausulas = list(db.scalars(
            select(Clausula)
            .where(Clausula.id_contrato == contrato.id_contrato, Clausula.estado == ESTADO_ACTIVO)
            .order_by(Clausula.numero_orden)
        ))
        if not clausulas:
            raise ErrorAnalisis("El contrato no tiene cláusulas para analizar")

        configuracion = leer_configuracion(db)
        modelo_llm = obtener_parametro(db, PAR_LLM_MODELO, "gpt-5.4-mini")
        plazo_pago = obtener_entero(db, PAR_PLAZO_PAGO, 90)
        meta_segundos = obtener_entero(db, PAR_TIEMPO_MAX, 20)
        similitud_minima = obtener_decimal(db, PAR_SIMILITUD_MINIMA, 0.30)

        niveles_por_codigo = {
            n.codigo: n for n in db.scalars(select(NivelRiesgo).where(NivelRiesgo.estado == ESTADO_ACTIVO))
        }
        categorias = {d.codigo: d for d in listar_detalles(db, CAT_CATEGORIA_RIESGO)}
        coberturas = {d.codigo: d for d in listar_detalles(db, CAT_COBERTURA_CONDICION)}
        lista_categorias = "\n".join(f"- {d.codigo}: {d.nombre}. {d.descripcion or ''}".strip()
                                     for d in categorias.values())
        instrucciones = INSTRUCCIONES.format(categorias=lista_categorias, plazo_pago=plazo_pago)
        tipo = db.scalar(select(CatalogoDetalle.nombre).where(
            CatalogoDetalle.id_catalogo_detalle == contrato.id_tipo_contrato)) or "no indicado"
        rol_parte = db.scalar(select(CatalogoDetalle.codigo).where(
            CatalogoDetalle.id_catalogo_detalle == contrato.id_rol_parte)) if contrato.id_rol_parte else None
        perfil = _perfil(usuario, rol_parte)
        acordado = (contrato.contexto_usuario or "").strip()[:MAX_CARACTERES_CONTEXTO]

        # 1. Embeddings de las cláusulas (una sola solicitud por lote)
        vectores = generar_embeddings(
            [_texto_clausula(c) for c in clausulas], configuracion.modelo, configuracion.dimension
        )

        # 2. Recuperación de normas (en el hilo principal: la sesión no se comparte entre hilos)
        sin_corpus = not db.scalar(select(func.count(FragmentoRag.id_fragmento))
                                   .where(FragmentoRag.estado == ESTADO_ACTIVO))
        contextos: list[list[Recuperado]] = []
        for clausula, vector in zip(clausulas, vectores, strict=True):
            clausula.embedding = vector
            contextos.append([] if sin_corpus else
                             _recuperar(db, vector, configuracion.top_k, similitud_minima))

        # 3. LLM en paralelo: semáforo de cada cláusula y, si hay contexto, verificación de condiciones
        mensajes = [_mensaje(perfil, tipo, acordado, c, ctx) for c, ctx in zip(clausulas, contextos)]
        condiciones: list[str] = []
        verificaciones: list[VerificacionCondicion] = []
        with ThreadPoolExecutor(max_workers=MAX_HILOS) as ejecutor:
            futuro_extraccion = ejecutor.submit(
                generar_estructurado, modelo_llm,
                INSTRUCCIONES_EXTRACCION.format(maximo=MAX_CONDICIONES),
                mensaje_extraccion(perfil, acordado), CondicionesExtraidas,
            ) if acordado else None
            futuros = [ejecutor.submit(clasificar_clausula, modelo_llm, instrucciones, m) for m in mensajes]

            if futuro_extraccion:
                condiciones = [
                    c.strip()[:500] for c in futuro_extraccion.result().condiciones if c.strip()
                ][:MAX_CONDICIONES]
            if condiciones:
                vectores_condicion = generar_embeddings(condiciones, configuracion.modelo, configuracion.dimension)
                futuros_verificacion = [
                    ejecutor.submit(
                        generar_estructurado, modelo_llm, INSTRUCCIONES_VERIFICACION,
                        mensaje_verificacion(perfil, texto, clausulas_candidatas(v, clausulas, vectores)),
                        VerificacionCondicion,
                    )
                    for texto, v in zip(condiciones, vectores_condicion, strict=True)
                ]
                verificaciones = [f.result() for f in futuros_verificacion]
            diagnosticos = [f.result() for f in futuros]

        # 4. Guardar el semáforo y las normas citadas
        ids = [c.id_clausula for c in clausulas]
        db.execute(delete(ClausulaFundamento).where(ClausulaFundamento.id_clausula.in_(ids)))
        ahora = datetime.now(timezone.utc)
        pesos: list[int] = []
        respaldadas = 0
        temas_sin_respaldo: set[str] = set()
        for clausula, diagnostico, contexto in zip(clausulas, diagnosticos, contextos):
            nivel = niveles_por_codigo[diagnostico.nivel]
            categoria = categorias.get(diagnostico.categoria.strip().upper())
            clausula.id_nivel_riesgo = nivel.id_nivel_riesgo
            clausula.id_categoria_riesgo = categoria.id_catalogo_detalle if categoria else None
            clausula.explicacion = diagnostico.explicacion.strip()
            clausula.usuario_modificacion = usuario.id_usuario
            clausula.fecha_modificacion = ahora
            pesos.append(nivel.peso)

            citados = sorted({i for i in diagnostico.fundamentos if 1 <= i <= len(contexto)})
            if citados:
                respaldadas += 1
            elif categoria and nivel.codigo != "BAJO":
                temas_sin_respaldo.add(categoria.nombre)
            for i in citados:
                recuperado = contexto[i - 1]
                db.add(ClausulaFundamento(
                    id_clausula=clausula.id_clausula,
                    id_fragmento=recuperado.fragmento.id_fragmento,
                    similitud=recuperado.similitud,
                    usuario_creacion=usuario.id_usuario,
                ))

        # 5. Guardar la verificación de condiciones
        db.execute(delete(Condicion).where(Condicion.id_contrato == contrato.id_contrato))
        por_numero = {c.numero_orden: c for c in clausulas}
        conteo_coberturas: dict[str, int] = {}
        for orden, (texto, verificacion) in enumerate(zip(condiciones, verificaciones), start=1):
            clausula = None
            if verificacion.cobertura != "AUSENTE" and verificacion.clausula is not None:
                clausula = por_numero.get(verificacion.clausula)
            conteo_coberturas[verificacion.cobertura] = conteo_coberturas.get(verificacion.cobertura, 0) + 1
            db.add(Condicion(
                id_contrato=contrato.id_contrato,
                id_cobertura=coberturas[verificacion.cobertura].id_catalogo_detalle,
                id_clausula=clausula.id_clausula if clausula else None,
                numero_orden=orden,
                descripcion=texto,
                explicacion=verificacion.explicacion.strip(),
                usuario_creacion=usuario.id_usuario,
            ))

        niveles_por_id = {n.id_nivel_riesgo: n for n in niveles_por_codigo.values()}
        nombres_categoria = {d.id_catalogo_detalle: d.nombre for d in categorias.values()}
        milisegundos = round((time.perf_counter() - inicio) * 1000)

        contrato.id_estado_analisis = obtener_id_detalle(db, CAT_ESTADO_ANALISIS, EST_ANALIZADO)
        contrato.puntaje_riesgo_global = _calcular_puntaje(pesos)
        contrato.resumen = _resumen(clausulas, niveles_por_id, nombres_categoria,
                                    sin_corpus, respaldadas, conteo_coberturas)
        contrato.tiempo_procesamiento_ms = milisegundos
        contrato.fecha_analisis = ahora
        contrato.usuario_modificacion = usuario.id_usuario
        contrato.fecha_modificacion = ahora

        conteo = {codigo: 0 for codigo in niveles_por_codigo}
        for d in diagnosticos:
            conteo[d.nivel] += 1
        registrar_evento(
            db, request, ACC_ANALISIS_CONTRATO,
            usuario=usuario,
            tabla_afectada="con_contrato",
            id_registro=contrato.id_contrato,
            datos_nuevos={
                "clausulas": len(clausulas),
                **{f"riesgo_{k.lower()}": v for k, v in conteo.items()},
                "clausulas_con_respaldo": respaldadas,
                "temas_sin_respaldo": sorted(temas_sin_respaldo),
                "condiciones": {k.lower(): v for k, v in conteo_coberturas.items()},
                "papel": rol_parte,
                "puntaje": float(contrato.puntaje_riesgo_global),
                "modelo": modelo_llm,
                "tiempo_ms": milisegundos,
                "dentro_de_meta": milisegundos <= meta_segundos * 1000,
            },
        )
        db.commit()
    except Exception as error:
        db.rollback()
        contrato.id_estado_analisis = obtener_id_detalle(db, CAT_ESTADO_ANALISIS, EST_ERROR)
        registrar_evento(
            db, request, ACC_ANALISIS_CONTRATO,
            usuario=usuario, tabla_afectada="con_contrato", id_registro=contrato.id_contrato,
            resultado=FALLO, observacion=str(error)[:255] or type(error).__name__,
        )
        db.commit()
        raise