"""Avance 3: base de conocimiento del RAG (rag_documento y rag_fragmento).

Revision ID: 0002_corpus_rag
Revises: 0001_avance1
Create Date: 2026-10-22
"""

from alembic import op

revision = "0002_corpus_rag"
down_revision = "0001_avance1"
branch_labels = None
depends_on = None

DIMENSION_EMBEDDING = 1536  # text-embedding-3-small


def control(tabla: str) -> str:
    """Columnas de control estándar del modelo v2.0."""
    return f"""
    estado               char(1)      NOT NULL DEFAULT 'A',
    usuario_creacion     integer,
    fecha_creacion       timestamptz  NOT NULL DEFAULT now(),
    usuario_modificacion integer,
    fecha_modificacion   timestamptz,
    CONSTRAINT ck_{tabla}_estado CHECK (estado IN ('A', 'I'))"""


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.execute(f"""
    CREATE TABLE rag_documento (
        id_documento    serial        NOT NULL,
        id_tipo_fuente  integer       NOT NULL,
        titulo          varchar(255)  NOT NULL,
        referencia      varchar(255),
        ruta_archivo    varchar(500)  NOT NULL,
        {control("rag_documento")},
        CONSTRAINT pk_rag_documento PRIMARY KEY (id_documento),
        CONSTRAINT fk_rag_documento_id_tipo_fuente
            FOREIGN KEY (id_tipo_fuente) REFERENCES cat_catalogo_detalle (id_catalogo_detalle)
    )""")

    op.execute(f"""
    CREATE TABLE rag_fragmento (
        id_fragmento         serial        NOT NULL,
        id_documento         integer       NOT NULL,
        numero_orden         integer       NOT NULL,
        articulo_referencia  varchar(60),
        contenido            text          NOT NULL,
        embedding            vector({DIMENSION_EMBEDDING}) NOT NULL,
        {control("rag_fragmento")},
        CONSTRAINT pk_rag_fragmento PRIMARY KEY (id_fragmento),
        CONSTRAINT fk_rag_fragmento_id_documento
            FOREIGN KEY (id_documento) REFERENCES rag_documento (id_documento) ON DELETE CASCADE,
        CONSTRAINT uk_rag_fragmento_id_documento_numero_orden UNIQUE (id_documento, numero_orden),
        CONSTRAINT ck_rag_fragmento_numero_orden CHECK (numero_orden > 0)
    )""")

    op.execute("CREATE INDEX ix_rag_fragmento_id_documento ON rag_fragmento (id_documento)")
    # Índice HNSW para búsqueda aproximada por similitud coseno
    op.execute(
        "CREATE INDEX ix_rag_fragmento_embedding ON rag_fragmento "
        "USING hnsw (embedding vector_cosine_ops)"
    )

    for tabla in ("rag_documento", "rag_fragmento"):
        for columna in ("usuario_creacion", "usuario_modificacion"):
            op.execute(
                f"ALTER TABLE {tabla} ADD CONSTRAINT fk_{tabla}_{columna} "
                f"FOREIGN KEY ({columna}) REFERENCES seg_usuario (id_usuario)"
            )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS rag_fragmento")
    op.execute("DROP TABLE IF EXISTS rag_documento")