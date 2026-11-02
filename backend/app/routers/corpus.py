from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, Query, Request, UploadFile, status
from sqlalchemy import func, select

from app.config import settings
from app.constantes import (
    ACC_CREACION_DOCUMENTO_RAG,
    ACC_INACTIVACION_DOCUMENTO_RAG,
    ACC_REACTIVACION_DOCUMENTO_RAG,
    CAT_TIPO_FUENTE,
    FALLO,
)
from app.deps import Administrador, DbSession
from app.models import ESTADO_ACTIVO, CatalogoDetalle, DocumentoRag, FragmentoRag
from app.schemas import (
    BusquedaEntrada,
    BusquedaSalida,
    DocumentoRagSalida,
    FragmentoEncontrado,
    FragmentoPagina,
    FragmentoSalida,
    OpcionCatalogo,
)
from app.services.auditoria import registrar_evento
from app.services.catalogos import listar_detalles, obtener_id_detalle
from app.services.corpus import (
    ErrorCorpus,
    buscar_fragmentos,
    inactivar_documento,
    reactivar_documento,
    registrar_documento,
)
from app.services.embeddings import ErrorEmbeddings
from app.services.extraccion import ErrorExtraccion

router = APIRouter(prefix="/admin/corpus", tags=["Corpus legal (RAG)"])

EXTENSIONES_PERMITIDAS = {".pdf", ".txt"}


def _conteo_fragmentos():
    return (
        select(FragmentoRag.id_documento, func.count().label("total"))
        .where(FragmentoRag.estado == ESTADO_ACTIVO)
        .group_by(FragmentoRag.id_documento)
        .subquery()
    )


def _salida(documento: DocumentoRag, tipo: CatalogoDetalle, fragmentos: int) -> DocumentoRagSalida:
    return DocumentoRagSalida(
        id_documento=documento.id_documento,
        titulo=documento.titulo,
        tipo_fuente=tipo.codigo,
        tipo_fuente_nombre=tipo.nombre,
        referencia=documento.referencia,
        numero_fragmentos=fragmentos,
        estado=documento.estado,
        fecha_creacion=documento.fecha_creacion,
    )


@router.get("/tipos-fuente", response_model=list[OpcionCatalogo])
def tipos_de_fuente(db: DbSession, _: Administrador):
    return [OpcionCatalogo(codigo=d.codigo, nombre=d.nombre) for d in listar_detalles(db, CAT_TIPO_FUENTE)]


@router.get("", response_model=list[DocumentoRagSalida])
def listar_documentos(db: DbSession, _: Administrador):
    conteo = _conteo_fragmentos()
    filas = db.execute(
        select(DocumentoRag, CatalogoDetalle, func.coalesce(conteo.c.total, 0))
        .join(CatalogoDetalle, CatalogoDetalle.id_catalogo_detalle == DocumentoRag.id_tipo_fuente)
        .outerjoin(conteo, conteo.c.id_documento == DocumentoRag.id_documento)
        .order_by(DocumentoRag.estado, DocumentoRag.fecha_creacion.desc())
    ).all()
    return [_salida(d, t, n) for d, t, n in filas]


@router.post("", response_model=DocumentoRagSalida, status_code=status.HTTP_201_CREATED)
def cargar_documento(
    request: Request,
    db: DbSession,
    administrador: Administrador,
    archivo: Annotated[UploadFile, File(description="PDF con texto seleccionable o archivo TXT")],
    titulo: Annotated[str, Form(min_length=3, max_length=255)],
    tipo_fuente: Annotated[str, Form(description="Código del catálogo TIPO_FUENTE")],
    referencia: Annotated[str | None, Form(max_length=255)] = None,
):
    titulo = titulo.strip()
    referencia = (referencia or "").strip() or None
    nombre_archivo = archivo.filename or "documento"
    extension = Path(nombre_archivo).suffix.lower()
    if extension not in EXTENSIONES_PERMITIDAS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Solo se aceptan archivos PDF o TXT")

    limite = settings.max_mb_corpus * 1024 * 1024
    contenido = archivo.file.read(limite + 1)
    if len(contenido) > limite:
        raise HTTPException(
            status.HTTP_413_CONTENT_TOO_LARGE,
            f"El archivo supera el máximo de {settings.max_mb_corpus} MB",
        )

    try:
        id_tipo = obtener_id_detalle(db, CAT_TIPO_FUENTE, tipo_fuente)
    except ValueError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "El tipo de fuente no es válido")

    try:
        resultado = registrar_documento(
            db, request, administrador,
            contenido=contenido,
            extension=extension,
            nombre_archivo=nombre_archivo,
            titulo=titulo,
            id_tipo_fuente=id_tipo,
            codigo_tipo_fuente=tipo_fuente,
            referencia=referencia,
        )
    except (ErrorExtraccion, ErrorCorpus, ErrorEmbeddings) as error:
        db.rollback()
        registrar_evento(
            db, request, ACC_CREACION_DOCUMENTO_RAG,
            usuario=administrador,
            resultado=FALLO,
            observacion=str(error)[:255],
            datos_nuevos={"titulo": titulo, "archivo": nombre_archivo},
        )
        db.commit()
        codigo = (
            status.HTTP_502_BAD_GATEWAY
            if isinstance(error, ErrorEmbeddings)
            else status.HTTP_422_UNPROCESSABLE_CONTENT
        )
        raise HTTPException(codigo, str(error))

    tipo = db.get(CatalogoDetalle, id_tipo)
    return _salida(resultado.documento, tipo, resultado.fragmentos)


@router.get("/{id_documento}/fragmentos", response_model=FragmentoPagina)
def ver_fragmentos(
    id_documento: int,
    db: DbSession,
    _: Administrador,
    pagina: int = Query(1, ge=1),
    tamanio: int = Query(10, ge=1, le=50),
):
    if db.get(DocumentoRag, id_documento) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Documento no encontrado")

    filtro = (FragmentoRag.id_documento == id_documento, FragmentoRag.estado == ESTADO_ACTIVO)
    total = db.scalar(select(func.count(FragmentoRag.id_fragmento)).where(*filtro))
    fragmentos = db.scalars(
        select(FragmentoRag)
        .where(*filtro)
        .order_by(FragmentoRag.numero_orden)
        .offset((pagina - 1) * tamanio)
        .limit(tamanio)
    ).all()
    return FragmentoPagina(
        elementos=[FragmentoSalida.model_validate(f) for f in fragmentos],
        total=total,
        pagina=pagina,
        tamanio=tamanio,
    )


@router.patch("/{id_documento}/inactivar", response_model=DocumentoRagSalida)
def inactivar(id_documento: int, request: Request, db: DbSession, administrador: Administrador):
    documento = db.get(DocumentoRag, id_documento)
    if documento is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Documento no encontrado")
    if documento.estado != ESTADO_ACTIVO:
        raise HTTPException(status.HTTP_409_CONFLICT, "El documento ya está inactivo")

    inactivar_documento(db, documento, administrador)
    registrar_evento(
        db, request, ACC_INACTIVACION_DOCUMENTO_RAG,
        usuario=administrador,
        tabla_afectada="rag_documento",
        id_registro=documento.id_documento,
        datos_anteriores={"estado": "A"},
        datos_nuevos={"estado": "I", "titulo": documento.titulo},
    )
    db.commit()

    conteo = _conteo_fragmentos()
    fragmentos = db.scalar(select(conteo.c.total).where(conteo.c.id_documento == id_documento)) or 0
    return _salida(documento, db.get(CatalogoDetalle, documento.id_tipo_fuente), fragmentos)

@router.patch("/{id_documento}/reactivar", response_model=DocumentoRagSalida)
def reactivar(id_documento: int, request: Request, db: DbSession, administrador: Administrador):
    documento = db.get(DocumentoRag, id_documento)
    if documento is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Documento no encontrado")
    if documento.estado == ESTADO_ACTIVO:
        raise HTTPException(status.HTTP_409_CONFLICT, "El documento ya está activo")

    reactivar_documento(db, documento, administrador)
    registrar_evento(
        db, request, ACC_REACTIVACION_DOCUMENTO_RAG,
        usuario=administrador,
        tabla_afectada="rag_documento",
        id_registro=documento.id_documento,
        datos_anteriores={"estado": "I"},
        datos_nuevos={"estado": "A", "titulo": documento.titulo},
    )
    db.commit()

    conteo = _conteo_fragmentos()
    fragmentos = db.scalar(select(conteo.c.total).where(conteo.c.id_documento == id_documento)) or 0
    return _salida(documento, db.get(CatalogoDetalle, documento.id_tipo_fuente), fragmentos)
@router.post("/buscar", response_model=BusquedaSalida)
def buscar(datos: BusquedaEntrada, db: DbSession, _: Administrador):
    """Prueba de recuperación semántica: devuelve las normas más parecidas al texto."""
    try:
        resultados, configuracion, milisegundos = buscar_fragmentos(db, datos.consulta, datos.top_k)
    except (ErrorCorpus, ErrorEmbeddings) as error:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(error))

    return BusquedaSalida(
        consulta=datos.consulta,
        modelo=configuracion.modelo,
        tiempo_ms=milisegundos,
        resultados=[
            FragmentoEncontrado(
                id_fragmento=r.fragmento.id_fragmento,
                id_documento=r.fragmento.id_documento,
                titulo_documento=r.titulo_documento,
                articulo_referencia=r.fragmento.articulo_referencia,
                contenido=r.fragmento.contenido,
                similitud=r.similitud,
            )
            for r in resultados
        ],
    )