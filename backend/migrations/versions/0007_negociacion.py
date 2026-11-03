"""Avance 6: contrapropuestas por cláusula, correos de negociación e informes PDF.

- con_contrapropuesta: redacción alternativa de una cláusula riesgosa y su resultado.
- con_correo_negociacion: cada correo redactado para pedir cambios a la otra parte.
- con_reporte: cada informe PDF generado, con su hash para verificar integridad.
- Catálogos ESTADO_CONTRAPROPUESTA (color en "valor") y TONO_CORREO.
- Acciones de auditoría de negociación y descarga del informe.

Revision ID: 0007_negociacion
Revises: 0006_reactivacion_corpus
Create Date: 2026-11-02
"""

from alembic import op

revision = "0007_negociacion"
down_revision = "0006_reactivacion_corpus"
branch_labels = None
depends_on = None

CATALOGOS_NUEVOS = {
    ("ESTADO_CONTRAPROPUESTA", "Estado de la negociación de una cláusula"): [
        # codigo, nombre, descripcion, valor (color)
        ("GENERADA", "Propuesta", "Redacción sugerida por el sistema, aún sin respuesta", "#2563EB"),
        ("ACEPTADA", "Aceptada", "La otra parte aceptó la redacción propuesta", "#16A34A"),
        ("MODIFICADA", "Aceptada con cambios", "Se acordó una redacción distinta (texto acordado)", "#0D9488"),
        ("RECHAZADA", "Rechazada", "La otra parte no aceptó el cambio", "#DC2626"),
    ],
    ("TONO_CORREO", "Tono del correo de negociación"): [
        ("FORMAL", "Formal", "Respetuoso, trato de usted", None),
        ("CORDIAL", "Cordial", "Cercano pero profesional", None),
    ],
}

ACCIONES = [
    ("GENERACION_CONTRAPROPUESTA", "Generación de contrapropuesta"),
    ("RESPUESTA_CONTRAPROPUESTA", "Respuesta a contrapropuesta"),
    ("GENERACION_CORREO", "Generación de correo de negociación"),
    ("DESCARGA_REPORTE", "Descarga de reporte"),
]


def _texto(v):
    return "NULL" if v is None else "'" + v.replace("'", "''") + "'"


def control(tabla: str) -> str:
    return f"""
        estado               char(1)      NOT NULL DEFAULT 'A',
        usuario_creacion     integer,
        fecha_creacion       timestamptz  NOT NULL DEFAULT now(),
        usuario_modificacion integer,
        fecha_modificacion   timestamptz,
        CONSTRAINT ck_{tabla}_estado CHECK (estado IN ('A', 'I')),
        CONSTRAINT fk_{tabla}_usuario_creacion
            FOREIGN KEY (usuario_creacion) REFERENCES seg_usuario (id_usuario),
        CONSTRAINT fk_{tabla}_usuario_modificacion
            FOREIGN KEY (usuario_modificacion) REFERENCES seg_usuario (id_usuario)"""


def upgrade() -> None:
    # ----------------------------------------------------------- catálogos
    for (cat_codigo, cat_nombre), detalles in CATALOGOS_NUEVOS.items():
        op.execute(
            f"INSERT INTO cat_catalogo (codigo, nombre) VALUES ({_texto(cat_codigo)}, {_texto(cat_nombre)}) "
            "ON CONFLICT (codigo) DO UPDATE SET estado = 'A'"
        )
        for orden, (codigo, nombre, descripcion, valor) in enumerate(detalles, start=1):
            op.execute(
                "INSERT INTO cat_catalogo_detalle (id_catalogo, codigo, nombre, descripcion, valor, orden) "
                f"SELECT id_catalogo, {_texto(codigo)}, {_texto(nombre)}, {_texto(descripcion)}, {_texto(valor)}, {orden} "
                f"FROM cat_catalogo WHERE codigo = {_texto(cat_codigo)} "
                "ON CONFLICT (id_catalogo, codigo) DO UPDATE SET estado = 'A'"
            )

    for codigo, nombre in ACCIONES:
        op.execute(
            "INSERT INTO cat_catalogo_detalle (id_catalogo, codigo, nombre, orden) "
            f"SELECT c.id_catalogo, {_texto(codigo)}, {_texto(nombre)}, "
            "(SELECT coalesce(max(d.orden), 0) + 1 FROM cat_catalogo_detalle d WHERE d.id_catalogo = c.id_catalogo) "
            "FROM cat_catalogo c WHERE c.codigo = 'ACCION_AUDITORIA' "
            "ON CONFLICT (id_catalogo, codigo) DO UPDATE SET estado = 'A'"
        )

    # -------------------------------------------------------------- tablas
    op.execute(f"""
    CREATE TABLE con_contrapropuesta (
        id_contrapropuesta         serial       NOT NULL,
        id_clausula                integer      NOT NULL,
        id_estado_contrapropuesta  integer      NOT NULL,
        texto_propuesto            text         NOT NULL,
        texto_acordado             text,
        justificacion              text,
        modelo_llm                 varchar(60)  NOT NULL,
        {control("con_contrapropuesta")},
        CONSTRAINT pk_con_contrapropuesta PRIMARY KEY (id_contrapropuesta),
        CONSTRAINT uk_con_contrapropuesta_id_clausula UNIQUE (id_clausula),
        CONSTRAINT fk_con_contrapropuesta_id_clausula
            FOREIGN KEY (id_clausula) REFERENCES con_clausula (id_clausula) ON DELETE CASCADE,
        CONSTRAINT fk_con_contrapropuesta_id_estado_contrapropuesta
            FOREIGN KEY (id_estado_contrapropuesta) REFERENCES cat_catalogo_detalle (id_catalogo_detalle)
    )""")

    op.execute(f"""
    CREATE TABLE con_correo_negociacion (
        id_correo     serial        NOT NULL,
        id_contrato   integer       NOT NULL,
        id_tono       integer       NOT NULL,
        destinatario  varchar(150),
        asunto        varchar(255)  NOT NULL,
        cuerpo        text          NOT NULL,
        modelo_llm    varchar(60)   NOT NULL,
        {control("con_correo_negociacion")},
        CONSTRAINT pk_con_correo_negociacion PRIMARY KEY (id_correo),
        CONSTRAINT fk_con_correo_negociacion_id_contrato
            FOREIGN KEY (id_contrato) REFERENCES con_contrato (id_contrato) ON DELETE CASCADE,
        CONSTRAINT fk_con_correo_negociacion_id_tono
            FOREIGN KEY (id_tono) REFERENCES cat_catalogo_detalle (id_catalogo_detalle)
    )""")
    op.execute("CREATE INDEX ix_con_correo_negociacion_id_contrato ON con_correo_negociacion (id_contrato)")

    op.execute(f"""
    CREATE TABLE con_reporte (
        id_reporte      serial        NOT NULL,
        id_contrato     integer       NOT NULL,
        nombre_archivo  varchar(255)  NOT NULL,
        ruta_archivo    varchar(500)  NOT NULL,
        hash_archivo    char(64)      NOT NULL,
        {control("con_reporte")},
        CONSTRAINT pk_con_reporte PRIMARY KEY (id_reporte),
        CONSTRAINT fk_con_reporte_id_contrato
            FOREIGN KEY (id_contrato) REFERENCES con_contrato (id_contrato) ON DELETE CASCADE
    )""")
    op.execute("CREATE INDEX ix_con_reporte_id_contrato ON con_reporte (id_contrato)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS con_reporte")
    op.execute("DROP TABLE IF EXISTS con_correo_negociacion")
    op.execute("DROP TABLE IF EXISTS con_contrapropuesta")
    # La auditoría es inmutable y puede referenciar las acciones: solo se inactivan
    op.execute(
        "UPDATE cat_catalogo_detalle d SET estado = 'I' FROM cat_catalogo c "
        "WHERE c.id_catalogo = d.id_catalogo AND c.codigo = 'ACCION_AUDITORIA' "
        "AND d.codigo IN ('RESPUESTA_CONTRAPROPUESTA', 'GENERACION_CORREO')"
    )
    for cat_codigo, _ in CATALOGOS_NUEVOS:
        op.execute(
            "DELETE FROM cat_catalogo_detalle WHERE id_catalogo = "
            f"(SELECT id_catalogo FROM cat_catalogo WHERE codigo = {_texto(cat_codigo)})"
        )
        op.execute(f"DELETE FROM cat_catalogo WHERE codigo = {_texto(cat_codigo)}")