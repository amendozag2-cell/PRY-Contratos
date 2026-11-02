from pathlib import Path
from typing import Annotated
from typing import Annotated
from fastapi import APIRouter, File, Form, HTTPException, Query, Request, Response, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.orm import aliased

from app.config import settings
from app.constantes import (
    ACC_ACTUALIZACION_CONTEXTO,
    ACC_CARGA_CONTRATO,
    ACC_INACTIVACION_CONTRATO,
    CAT_ROL_PARTE,
    CAT_TIPO_CONTRATO,
    FALLO,
)
from app.deps import DbSession, UsuarioActual
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
from app.schemas import (
    MAX_CONTEXTO,
    CargaContratoSalida,
    ClausulaSalida,
    CoberturaSalida,
    CondicionSalida,
    ContextoEntrada,
    ContratoDetalle,
    ContratoSalida,
    FundamentoSalida,
    NivelRiesgoSalida,
    OpcionCatalogo,
)
from app.services.analisis import ErrorAnalisis, analizar_contrato
from app.services.auditoria import registrar_evento
from app.services.catalogos import listar_detalles, obtener_id_detalle
from app.services.contratos import (
    ContratoDuplicado,
    actualizar_contexto,
    cargar_contrato,
    inactivar_contrato,
)
from app.services.corpus import ErrorCorpus
from app.services.embeddings import ErrorEmbeddings
from app.services.extraccion import ErrorExtraccion
from app.services.llm import ErrorLLM
from app.services.procesamiento_pdf import renderizar_pagina

router = APIRouter(prefix="/contratos", tags=["Contratos"])

FIRMA_PDF = b"%PDF"


def _consulta_contratos():
    """Contratos con su estado de análisis, tipo y número de cláusulas."""
    estado = aliased(CatalogoDetalle)
    tipo = aliased(CatalogoDetalle)
    clausulas = (
        select(Clausula.id_contrato, func.count().label("total"))
        .where(Clausula.estado == ESTADO_ACTIVO)
        .group_by(Clausula.id_contrato)
        .subquery()
    )
    return select(
        Contrato, estado.codigo, tipo.nombre, func.coalesce(clausulas.c.total, 0)
    ).join(
        estado, estado.id_catalogo_detalle == Contrato.id_estado_analisis
    ).outerjoin(
        tipo, tipo.id_catalogo_detalle == Contrato.id_tipo_contrato
    ).outerjoin(
        clausulas, clausulas.c.id_contrato == Contrato.id_contrato
    )


def _salida(fila) -> ContratoSalida:
    c, estado, tipo, total = fila
    return ContratoSalida(
        id_contrato=c.id_contrato,
        nombre_archivo=c.nombre_archivo,
        tipo_contrato=tipo,
        numero_paginas=c.numero_paginas,
        numero_clausulas=total,
        es_escaneado=c.es_escaneado,
        estado_analisis=estado,
        puntaje_riesgo_global=c.puntaje_riesgo_global,
        fecha_creacion=c.fecha_creacion,
    )


def _obtener_propio(db, id_contrato: int, usuario: Usuario):
    fila = db.execute(
        _consulta_contratos().where(
            Contrato.id_contrato == id_contrato,
            Contrato.id_usuario == usuario.id_usuario,
            Contrato.estado == ESTADO_ACTIVO,
        )
    ).first()
    if fila is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Contrato no encontrado")
    return fila


@router.get("/tipos", response_model=list[OpcionCatalogo])
def tipos_de_contrato(db: DbSession, _: UsuarioActual):
    return [OpcionCatalogo(codigo=d.codigo, nombre=d.nombre) for d in listar_detalles(db, CAT_TIPO_CONTRATO)]


@router.get("/roles-parte", response_model=list[OpcionCatalogo])
def roles_en_el_contrato(db: DbSession, _: UsuarioActual):
    """Papeles que el usuario puede tener en el contrato (presta o contrata el servicio)."""
    return [OpcionCatalogo(codigo=d.codigo, nombre=d.nombre) for d in listar_detalles(db, CAT_ROL_PARTE)]


def _id_rol_parte(db, codigo: str | None) -> int | None:
    if not codigo:
        return None
    try:
        return obtener_id_detalle(db, CAT_ROL_PARTE, codigo)
    except ValueError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "El papel en el contrato no es válido")


@router.get("", response_model=list[ContratoSalida])
def listar_mis_contratos(usuario: UsuarioActual, db: DbSession):
    filas = db.execute(
        _consulta_contratos()
        .where(Contrato.id_usuario == usuario.id_usuario, Contrato.estado == ESTADO_ACTIVO)
        .order_by(Contrato.fecha_creacion.desc())
    ).all()
    return [_salida(f) for f in filas]


@router.post("", response_model=CargaContratoSalida, status_code=status.HTTP_201_CREATED)
def cargar(
    request: Request,
    db: DbSession,
    usuario: UsuarioActual,
    archivo: Annotated[UploadFile, File(description="Contrato en PDF (digital o escaneado)")],
    tipo_contrato: Annotated[str | None, Form(description="Código del catálogo TIPO_CONTRATO")] = None,
    rol_parte: Annotated[str | None, Form(description="Código del catálogo ROL_PARTE")] = None,
    contexto: Annotated[str | None, Form(description="Lo que el usuario dice que acordaron")] = None,
):
    nombre_archivo = archivo.filename or "contrato.pdf"
    limite = settings.max_mb_contrato * 1024 * 1024
    contenido = archivo.file.read(limite + 1)
    if len(contenido) > limite:
        raise HTTPException(
            status.HTTP_413_CONTENT_TOO_LARGE,
            f"El archivo supera el máximo de {settings.max_mb_contrato} MB",
        )
    if not contenido.startswith(FIRMA_PDF):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "El archivo debe ser un PDF")

    contexto = (contexto or "").strip() or None
    if contexto and len(contexto) > MAX_CONTEXTO:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"La descripción de lo acordado admite hasta {MAX_CONTEXTO} caracteres",
        )
    id_rol = _id_rol_parte(db, rol_parte)

    id_tipo = None
    if tipo_contrato:
        try:
            id_tipo = obtener_id_detalle(db, CAT_TIPO_CONTRATO, tipo_contrato)
        except ValueError:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "El tipo de contrato no es válido")

    try:
        resultado = cargar_contrato(
            db, request, usuario,
            contenido=contenido,
            nombre_archivo=nombre_archivo,
            id_tipo_contrato=id_tipo,
            id_rol_parte=id_rol,
            contexto_usuario=contexto,
        )
    except ContratoDuplicado as error:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            {"mensaje": str(error), "id_contrato": error.id_contrato},
        )
    except ErrorExtraccion as error:
        db.rollback()
        registrar_evento(
            db, request, ACC_CARGA_CONTRATO,
            usuario=usuario, resultado=FALLO, observacion=str(error)[:255],
            datos_nuevos={"archivo": nombre_archivo},
        )
        db.commit()
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error))

    fila = _obtener_propio(db, resultado.contrato.id_contrato, usuario)
    return CargaContratoSalida(
        contrato=_salida(fila),
        paginas_ocr=resultado.paginas_ocr,
        tiempo_ms=resultado.milisegundos,
    )


def _detalle(db, fila) -> ContratoDetalle:
    """Contrato con sus cláusulas, el diagnóstico de cada una y las normas citadas."""
    contrato = fila[0]
    categoria = aliased(CatalogoDetalle)
    filas = db.execute(
        select(Clausula, NivelRiesgo, categoria)
        .outerjoin(NivelRiesgo, NivelRiesgo.id_nivel_riesgo == Clausula.id_nivel_riesgo)
        .outerjoin(categoria, categoria.id_catalogo_detalle == Clausula.id_categoria_riesgo)
        .where(Clausula.id_contrato == contrato.id_contrato, Clausula.estado == ESTADO_ACTIVO)
        .order_by(Clausula.numero_orden)
    ).all()

    fundamentos: dict[int, list[FundamentoSalida]] = {}
    ids = [c.id_clausula for c, _, _ in filas]
    if ids:
        for cf, fragmento, titulo in db.execute(
            select(ClausulaFundamento, FragmentoRag, DocumentoRag.titulo)
            .join(FragmentoRag, FragmentoRag.id_fragmento == ClausulaFundamento.id_fragmento)
            .join(DocumentoRag, DocumentoRag.id_documento == FragmentoRag.id_documento)
            .where(ClausulaFundamento.id_clausula.in_(ids), ClausulaFundamento.estado == ESTADO_ACTIVO)
            .order_by(ClausulaFundamento.similitud.desc())
        ).all():
            fundamentos.setdefault(cf.id_clausula, []).append(FundamentoSalida(
                id_fragmento=fragmento.id_fragmento,
                titulo_documento=titulo,
                articulo_referencia=fragmento.articulo_referencia,
                contenido=fragmento.contenido,
                similitud=float(cf.similitud),
            ))

    clausulas = []
    for c, nivel, cat in filas:
        salida = ClausulaSalida.model_validate(c)
        salida.nivel_riesgo = NivelRiesgoSalida.model_validate(nivel) if nivel else None
        salida.categoria_riesgo = OpcionCatalogo(codigo=cat.codigo, nombre=cat.nombre) if cat else None
        salida.explicacion = c.explicacion
        salida.fundamentos = fundamentos.get(c.id_clausula, [])
        clausulas.append(salida)

    cobertura = aliased(CatalogoDetalle)
    condiciones = [
        CondicionSalida(
            numero_orden=cond.numero_orden,
            descripcion=cond.descripcion,
            cobertura=CoberturaSalida(codigo=cob.codigo, nombre=cob.nombre, color_hex=cob.valor or "#64748B"),
            explicacion=cond.explicacion,
            id_clausula=cond.id_clausula,
            numero_clausula=numero,
            titulo_clausula=titulo,
        )
        for cond, cob, numero, titulo in db.execute(
            select(Condicion, cobertura, Clausula.numero_orden, Clausula.titulo)
            .join(cobertura, cobertura.id_catalogo_detalle == Condicion.id_cobertura)
            .outerjoin(Clausula, Clausula.id_clausula == Condicion.id_clausula)
            .where(Condicion.id_contrato == contrato.id_contrato, Condicion.estado == ESTADO_ACTIVO)
            .order_by(Condicion.numero_orden)
        ).all()
    ]

    rol = db.get(CatalogoDetalle, contrato.id_rol_parte) if contrato.id_rol_parte else None
    niveles = db.scalars(
        select(NivelRiesgo).where(NivelRiesgo.estado == ESTADO_ACTIVO).order_by(NivelRiesgo.orden)
    ).all()
    return ContratoDetalle(
        **_salida(fila).model_dump(),
        resumen=contrato.resumen,
        tiempo_procesamiento_ms=contrato.tiempo_procesamiento_ms,
        fecha_analisis=contrato.fecha_analisis,
        rol_parte=OpcionCatalogo(codigo=rol.codigo, nombre=rol.nombre) if rol else None,
        contexto_usuario=contrato.contexto_usuario,
        niveles=[NivelRiesgoSalida.model_validate(n) for n in niveles],
        clausulas=clausulas,
        condiciones=condiciones,
    )


@router.get("/{id_contrato}", response_model=ContratoDetalle)
def detalle(id_contrato: int, db: DbSession, usuario: UsuarioActual):
    return _detalle(db, _obtener_propio(db, id_contrato, usuario))


@router.patch("/{id_contrato}/contexto", response_model=ContratoDetalle)
def cambiar_contexto(id_contrato: int, datos: ContextoEntrada, request: Request,
                     db: DbSession, usuario: UsuarioActual):
    """Cambia el papel del usuario y lo acordado. Se aplica en el siguiente análisis."""
    contrato = _obtener_propio(db, id_contrato, usuario)[0]
    anterior = {"rol_parte": contrato.id_rol_parte, "caracteres_contexto": len(contrato.contexto_usuario or "")}
    actualizar_contexto(contrato, usuario, _id_rol_parte(db, datos.rol_parte), datos.contexto_usuario)
    registrar_evento(
        db, request, ACC_ACTUALIZACION_CONTEXTO,
        usuario=usuario,
        tabla_afectada="con_contrato",
        id_registro=contrato.id_contrato,
        datos_anteriores=anterior,
        datos_nuevos={"rol_parte": contrato.id_rol_parte, "caracteres_contexto": len(datos.contexto_usuario or "")},
    )
    db.commit()
    return _detalle(db, _obtener_propio(db, id_contrato, usuario))


@router.post("/{id_contrato}/analizar", response_model=ContratoDetalle)
def analizar(id_contrato: int, request: Request, db: DbSession, usuario: UsuarioActual):
    """Clasifica cada cláusula en el semáforo de riesgo usando el corpus legal (RAG) y el LLM."""
    contrato = _obtener_propio(db, id_contrato, usuario)[0]
    try:
        analizar_contrato(db, request, usuario, contrato)
    except ErrorAnalisis as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error))
    except (ErrorLLM, ErrorEmbeddings, ErrorCorpus) as error:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(error))
    return _detalle(db, _obtener_propio(db, id_contrato, usuario))


@router.get("/{id_contrato}/paginas/{numero_pagina}/imagen")
def imagen_de_pagina(
    id_contrato: int,
    numero_pagina: int,
    db: DbSession,
    usuario: UsuarioActual,
    ancho: int = Query(900, ge=200, le=2000),
):
    contrato = _obtener_propio(db, id_contrato, usuario)[0]
    try:
        png = renderizar_pagina(contrato.ruta_archivo, numero_pagina, ancho)
    except ErrorExtraccion as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(error))
    except FileNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No se encontró el archivo del contrato")
    return Response(content=png, media_type="image/png", headers={"Cache-Control": "private, max-age=3600"})

@router.get("/{id_contrato}/archivo")
def descargar_archivo(id_contrato: int, db: DbSession, usuario: UsuarioActual):
    """PDF original del contrato, para descargarlo desde el visor."""
    contrato = _obtener_propio(db, id_contrato, usuario)[0]
    ruta = Path(contrato.ruta_archivo)
    if not ruta.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No se encontró el archivo del contrato")
    return FileResponse(ruta, media_type="application/pdf", filename=contrato.nombre_archivo)

@router.patch("/{id_contrato}/inactivar", status_code=status.HTTP_204_NO_CONTENT)
def inactivar(id_contrato: int, request: Request, db: DbSession, usuario: UsuarioActual):
    contrato = _obtener_propio(db, id_contrato, usuario)[0]
    inactivar_contrato(contrato, usuario)
    registrar_evento(
        db, request, ACC_INACTIVACION_CONTRATO,
        usuario=usuario,
        tabla_afectada="con_contrato",
        id_registro=contrato.id_contrato,
        datos_anteriores={"estado": "A"},
        datos_nuevos={"estado": "I", "archivo": contrato.nombre_archivo},
    )
    db.commit()