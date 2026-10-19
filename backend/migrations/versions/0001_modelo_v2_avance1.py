"""Modelo v2.0 - Avance 1: parametrización, seguridad, contratos y auditoría.

Crea las 7 tablas del Avance 1 siguiendo el estándar de nomenclatura del
modelo entidad-relación (prefijo de módulo, id_<entidad>, columnas de control
y nombres de restricciones pk_/fk_/uk_/ck_/ix_) y carga los datos semilla de
roles, catálogos y parámetros del sistema.

Revision ID: 0001_avance1
Revises:
Create Date: 2026-10-19
"""

from alembic import op

revision = "0001_avance1"
down_revision = None
branch_labels = None
depends_on = None


# Columnas de control estándar (todas las tablas excepto aud_auditoria)
def control(tabla: str) -> str:
    return f"""
    estado               char(1)      NOT NULL DEFAULT 'A',
    usuario_creacion     integer,
    fecha_creacion       timestamptz  NOT NULL DEFAULT now(),
    usuario_modificacion integer,
    fecha_modificacion   timestamptz,
    CONSTRAINT ck_{tabla}_estado CHECK (estado IN ('A', 'I'))"""


TABLAS_CON_CONTROL = [
    "cat_catalogo",
    "cat_catalogo_detalle",
    "cat_parametro",
    "seg_rol",
    "seg_usuario",
    "con_contrato",
]

DDL = [
    # ---------------------------------------------------------------- cat_
    f"""
    CREATE TABLE cat_catalogo (
        id_catalogo  serial        NOT NULL,
        codigo       varchar(40)   NOT NULL,
        nombre       varchar(100)  NOT NULL,
        descripcion  varchar(255),
        {control("cat_catalogo")},
        CONSTRAINT pk_cat_catalogo PRIMARY KEY (id_catalogo),
        CONSTRAINT uk_cat_catalogo_codigo UNIQUE (codigo)
    )""",
    f"""
    CREATE TABLE cat_catalogo_detalle (
        id_catalogo_detalle  serial        NOT NULL,
        id_catalogo          integer       NOT NULL,
        codigo               varchar(40)   NOT NULL,
        nombre               varchar(100)  NOT NULL,
        descripcion          varchar(255),
        valor                varchar(100),
        orden                smallint      NOT NULL DEFAULT 1,
        {control("cat_catalogo_detalle")},
        CONSTRAINT pk_cat_catalogo_detalle PRIMARY KEY (id_catalogo_detalle),
        CONSTRAINT fk_cat_catalogo_detalle_id_catalogo
            FOREIGN KEY (id_catalogo) REFERENCES cat_catalogo (id_catalogo),
        CONSTRAINT uk_cat_catalogo_detalle_id_catalogo_codigo UNIQUE (id_catalogo, codigo)
    )""",
    f"""
    CREATE TABLE cat_parametro (
        id_parametro  serial        NOT NULL,
        codigo        varchar(60)   NOT NULL,
        nombre        varchar(120)  NOT NULL,
        valor         varchar(255)  NOT NULL,
        tipo_dato     varchar(10)   NOT NULL,
        descripcion   varchar(255),
        {control("cat_parametro")},
        CONSTRAINT pk_cat_parametro PRIMARY KEY (id_parametro),
        CONSTRAINT uk_cat_parametro_codigo UNIQUE (codigo),
        CONSTRAINT ck_cat_parametro_tipo_dato
            CHECK (tipo_dato IN ('TEXTO', 'ENTERO', 'DECIMAL', 'BOOLEANO'))
    )""",
    # ---------------------------------------------------------------- seg_
    f"""
    CREATE TABLE seg_rol (
        id_rol       smallserial   NOT NULL,
        codigo       varchar(20)   NOT NULL,
        nombre       varchar(50)   NOT NULL,
        descripcion  varchar(255),
        {control("seg_rol")},
        CONSTRAINT pk_seg_rol PRIMARY KEY (id_rol),
        CONSTRAINT uk_seg_rol_codigo UNIQUE (codigo)
    )""",
    f"""
    CREATE TABLE seg_usuario (
        id_usuario           serial        NOT NULL,
        id_rol               smallint      NOT NULL,
        correo               varchar(255)  NOT NULL,
        nombres              varchar(80)   NOT NULL,
        apellidos            varchar(80)   NOT NULL,
        clave_hash           varchar(255)  NOT NULL,
        nombre_empresa       varchar(150),
        ruc_empresa          char(13),
        fecha_ultimo_acceso  timestamptz,
        {control("seg_usuario")},
        CONSTRAINT pk_seg_usuario PRIMARY KEY (id_usuario),
        CONSTRAINT fk_seg_usuario_id_rol FOREIGN KEY (id_rol) REFERENCES seg_rol (id_rol),
        CONSTRAINT uk_seg_usuario_correo UNIQUE (correo),
        CONSTRAINT ck_seg_usuario_ruc_empresa CHECK (ruc_empresa ~ '^[0-9]{{13}}$')
    )""",
    # ---------------------------------------------------------------- con_
    f"""
    CREATE TABLE con_contrato (
        id_contrato              serial        NOT NULL,
        id_usuario               integer       NOT NULL,
        id_tipo_contrato         integer,
        id_estado_analisis       integer       NOT NULL,
        nombre_archivo           varchar(255)  NOT NULL,
        ruta_archivo             varchar(500)  NOT NULL,
        hash_archivo             char(64),
        numero_paginas           smallint,
        es_escaneado             boolean       NOT NULL DEFAULT false,
        puntaje_riesgo_global    numeric(5,2),
        resumen                  text,
        tiempo_procesamiento_ms  integer,
        fecha_analisis           timestamptz,
        {control("con_contrato")},
        CONSTRAINT pk_con_contrato PRIMARY KEY (id_contrato),
        CONSTRAINT fk_con_contrato_id_usuario
            FOREIGN KEY (id_usuario) REFERENCES seg_usuario (id_usuario),
        CONSTRAINT fk_con_contrato_id_tipo_contrato
            FOREIGN KEY (id_tipo_contrato) REFERENCES cat_catalogo_detalle (id_catalogo_detalle),
        CONSTRAINT fk_con_contrato_id_estado_analisis
            FOREIGN KEY (id_estado_analisis) REFERENCES cat_catalogo_detalle (id_catalogo_detalle),
        CONSTRAINT ck_con_contrato_numero_paginas CHECK (numero_paginas > 0),
        CONSTRAINT ck_con_contrato_puntaje_riesgo_global
            CHECK (puntaje_riesgo_global BETWEEN 0 AND 100)
    )""",
    "CREATE INDEX ix_con_contrato_id_usuario ON con_contrato (id_usuario)",
    # ---------------------------------------------------------------- aud_
    """
    CREATE TABLE aud_auditoria (
        id_auditoria      bigserial     NOT NULL,
        id_usuario        integer,
        id_accion         integer       NOT NULL,
        correo_usuario    varchar(255),
        tabla_afectada    varchar(60),
        id_registro       bigint,
        resultado         varchar(10)   NOT NULL,
        datos_anteriores  jsonb,
        datos_nuevos      jsonb,
        observacion       varchar(255),
        direccion_ip      varchar(45),
        agente_usuario    varchar(300),
        fecha_evento      timestamptz   NOT NULL DEFAULT now(),
        CONSTRAINT pk_aud_auditoria PRIMARY KEY (id_auditoria),
        CONSTRAINT fk_aud_auditoria_id_usuario
            FOREIGN KEY (id_usuario) REFERENCES seg_usuario (id_usuario),
        CONSTRAINT fk_aud_auditoria_id_accion
            FOREIGN KEY (id_accion) REFERENCES cat_catalogo_detalle (id_catalogo_detalle),
        CONSTRAINT ck_aud_auditoria_resultado CHECK (resultado IN ('EXITO', 'FALLO'))
    )""",
    "CREATE INDEX ix_aud_auditoria_fecha_evento ON aud_auditoria (fecha_evento)",
    "CREATE INDEX ix_aud_auditoria_id_accion ON aud_auditoria (id_accion)",
    "CREATE INDEX ix_aud_auditoria_id_usuario ON aud_auditoria (id_usuario)",
    # La auditoría es inmutable: la propia base de datos impide editarla o borrarla
    """
    CREATE FUNCTION fn_aud_auditoria_inmutable() RETURNS trigger AS $$
    BEGIN
        RAISE EXCEPTION 'aud_auditoria es de solo escritura: no se permite % sobre sus registros', TG_OP;
    END;
    $$ LANGUAGE plpgsql""",
    """
    CREATE TRIGGER tg_aud_auditoria_inmutable
        BEFORE UPDATE OR DELETE ON aud_auditoria
        FOR EACH ROW EXECUTE FUNCTION fn_aud_auditoria_inmutable()""",
]

# Claves foráneas de las columnas de control hacia seg_usuario
for _t in TABLAS_CON_CONTROL:
    for _col in ("usuario_creacion", "usuario_modificacion"):
        DDL.append(
            f"ALTER TABLE {_t} ADD CONSTRAINT fk_{_t}_{_col} "
            f"FOREIGN KEY ({_col}) REFERENCES seg_usuario (id_usuario)"
        )


# ------------------------------------------------------------ datos semilla
ROLES = [
    ("FREELANCER", "Freelancer", "Profesional independiente que analiza sus contratos"),
    ("PYME", "Representante de PYME", "Gestiona los contratos de una pequeña o mediana empresa"),
    ("ADMINISTRADOR", "Administrador", "Gestiona usuarios, corpus legal, parámetros y auditoría"),
]

CATALOGOS = {
    ("ESTADO_ANALISIS", "Estados del análisis de un contrato"): [
        ("CARGADO", "Cargado", "PDF recibido"),
        ("PROCESANDO", "Procesando", "Extracción y análisis en curso"),
        ("ANALIZADO", "Analizado", "Diagnóstico disponible"),
        ("ERROR", "Error", "El análisis no pudo completarse"),
    ],
    ("TIPO_CONTRATO", "Tipos de contrato"): [
        ("SERVICIOS", "Prestación de servicios", None),
        ("NDA", "Acuerdo de confidencialidad", None),
        ("ARRENDAMIENTO", "Arrendamiento comercial", None),
        ("OTRO", "Otro", None),
    ],
    ("CATEGORIA_RIESGO", "Categorías de riesgo contractual"): [
        ("PROPIEDAD_INTELECTUAL", "Propiedad intelectual", "Cesión exclusiva o no equitativa"),
        ("PLAZO_PAGO", "Plazo de pago", "Plazos de pago excesivos o ausentes"),
        ("PENALIDAD", "Penalidad", "Penalizaciones económicas abusivas"),
        ("RESCISION", "Rescisión", "Terminación unilateral"),
        ("NO_COMPETENCIA", "No competencia", "No competencia desproporcionada"),
        ("EXCLUSIVIDAD", "Exclusividad", "Exclusividad desproporcionada"),
        ("CONFIDENCIALIDAD", "Confidencialidad", "Obligaciones de confidencialidad"),
        ("RESPONSABILIDAD", "Responsabilidad", "Distribución de responsabilidades"),
    ],
    ("TIPO_HITO", "Tipos de hito contractual"): [
        ("PAGO", "Pago", None),
        ("ENTREGA", "Entrega", None),
        ("VENCIMIENTO", "Vencimiento", None),
        ("RENOVACION", "Renovación", None),
    ],
    ("TIPO_FUENTE", "Tipos de fuente del corpus legal"): [
        ("LEY", "Ley o código", None),
        ("REGLAMENTO", "Reglamento", None),
        ("BUENA_PRACTICA", "Buena práctica comercial", None),
    ],
    ("ACCION_AUDITORIA", "Acciones registradas en la auditoría"): [
        ("REGISTRO_USUARIO", "Registro de usuario", None),
        ("INICIO_SESION", "Inicio de sesión", None),
        ("INICIO_SESION_FALLIDO", "Inicio de sesión fallido", None),
        ("CARGA_CONTRATO", "Carga de contrato", None),
        ("INACTIVACION_CONTRATO", "Inactivación de contrato", None),
        ("ANALISIS_CONTRATO", "Análisis de contrato", None),
        ("CREACION_DOCUMENTO_RAG", "Creación de documento del corpus", None),
        ("INACTIVACION_DOCUMENTO_RAG", "Inactivación de documento del corpus", None),
        ("CAMBIO_ESTADO_USUARIO", "Cambio de estado de usuario", None),
        ("MODIFICACION_PARAMETRO", "Modificación de parámetro", None),
        ("GENERACION_CONTRAPROPUESTA", "Generación de contrapropuesta", None),
        ("DESCARGA_REPORTE", "Descarga de reporte", None),
    ],
}

PARAMETROS = [
    ("MAX_PAGINAS_CONTRATO", "Máximo de páginas por contrato", "15", "ENTERO", "Límite del alcance de la propuesta"),
    ("TIEMPO_MAX_ANALISIS_SEG", "Tiempo máximo de análisis (s)", "20", "ENTERO", "Meta de desempeño por contrato"),
    ("PLAZO_PAGO_MAX_DIAS", "Plazo de pago máximo (días)", "90", "ENTERO", "Plazos mayores se consideran riesgo"),
    ("LLM_MODELO", "Modelo de lenguaje", "gpt-5.4-mini", "TEXTO", "Modelo de OpenAI usado para el análisis"),
    ("EMBEDDING_MODELO", "Modelo de embeddings", "text-embedding-3-small", "TEXTO", "Modelo de vectorización"),
    ("EMBEDDING_DIMENSION", "Dimensión de embeddings", "1536", "ENTERO", "Tamaño de los vectores"),
    ("CHUNK_TAMANIO", "Tamaño de fragmento (caracteres)", "1000", "ENTERO", "Fragmentación del texto"),
    ("CHUNK_SOLAPAMIENTO", "Solapamiento de fragmentos", "150", "ENTERO", "Caracteres compartidos entre fragmentos"),
    ("RAG_TOP_K", "Fragmentos recuperados", "5", "ENTERO", "Normas consultadas por cláusula"),
    ("SESION_MINUTOS_EXPIRACION", "Duración de la sesión (min)", "60", "ENTERO", "Vigencia del token de acceso"),
]


def _texto(v):
    return "NULL" if v is None else "'" + v.replace("'", "''") + "'"


def upgrade() -> None:
    for sentencia in DDL:
        op.execute(sentencia)

    for codigo, nombre, descripcion in ROLES:
        op.execute(
            f"INSERT INTO seg_rol (codigo, nombre, descripcion) "
            f"VALUES ({_texto(codigo)}, {_texto(nombre)}, {_texto(descripcion)})"
        )

    for (cat_codigo, cat_nombre), detalles in CATALOGOS.items():
        op.execute(
            f"INSERT INTO cat_catalogo (codigo, nombre) "
            f"VALUES ({_texto(cat_codigo)}, {_texto(cat_nombre)})"
        )
        for orden, (codigo, nombre, descripcion) in enumerate(detalles, start=1):
            op.execute(
                "INSERT INTO cat_catalogo_detalle (id_catalogo, codigo, nombre, descripcion, orden) "
                f"SELECT id_catalogo, {_texto(codigo)}, {_texto(nombre)}, {_texto(descripcion)}, {orden} "
                f"FROM cat_catalogo WHERE codigo = {_texto(cat_codigo)}"
            )

    for codigo, nombre, valor, tipo, descripcion in PARAMETROS:
        op.execute(
            "INSERT INTO cat_parametro (codigo, nombre, valor, tipo_dato, descripcion) "
            f"VALUES ({_texto(codigo)}, {_texto(nombre)}, {_texto(valor)}, "
            f"{_texto(tipo)}, {_texto(descripcion)})"
        )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS aud_auditoria CASCADE")
    op.execute("DROP FUNCTION IF EXISTS fn_aud_auditoria_inmutable()")
    for tabla in ("con_contrato", "seg_usuario", "seg_rol", "cat_parametro",
                  "cat_catalogo_detalle", "cat_catalogo"):
        op.execute(f"DROP TABLE IF EXISTS {tabla} CASCADE")