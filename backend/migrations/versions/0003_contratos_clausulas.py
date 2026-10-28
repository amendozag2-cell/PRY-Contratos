"""Avance 2: cláusulas del contrato con coordenadas y catálogo del semáforo de riesgo.

cat_nivel_riesgo se crea ahora porque con_clausula la referencia; sus valores
se usarán en el Avance 4 (motor de diagnóstico).

Revision ID: 0003_contratos_clausulas
Revises: 0002_corpus_rag
Create Date: 2026-10-22
"""

from alembic import op

revision = "0003_contratos_clausulas"
down_revision = "0002_corpus_rag"
branch_labels = None
depends_on = None

DIMENSION_EMBEDDING = 1536


def control(tabla: str) -> str:
    """Columnas de control estándar del modelo v2.0."""
    return f"""
    estado               char(1)      NOT NULL DEFAULT 'A',
    usuario_creacion     integer,
    fecha_creacion       timestamptz  NOT NULL DEFAULT now(),
    usuario_modificacion integer,
    fecha_modificacion   timestamptz,
    CONSTRAINT ck_{tabla}_estado CHECK (estado IN ('A', 'I'))"""


NIVELES = [
    # codigo, nombre, color, peso, orden, descripcion
    ("ALTO", "Riesgo alto", "#DC2626", 100, 1,
     "Cláusula desequilibrada o abusiva que puede causar un perjuicio grave"),
    ("MEDIO", "Advertencia", "#F59E0B", 50, 2,
     "Cláusula ambigua o incompleta que conviene negociar o aclarar"),
    ("BAJO", "Cláusula segura", "#16A34A", 0, 3,
     "Cláusula equilibrada según la legislación y las buenas prácticas"),
]


def upgrade() -> None:
    op.execute(f"""
    CREATE TABLE cat_nivel_riesgo (
        id_nivel_riesgo  smallserial  NOT NULL,
        codigo           varchar(10)  NOT NULL,
        nombre           varchar(40)  NOT NULL,
        color_hex        char(7)      NOT NULL,
        peso             smallint     NOT NULL,
        orden            smallint     NOT NULL,
        descripcion      varchar(255),
        {control("cat_nivel_riesgo")},
        CONSTRAINT pk_cat_nivel_riesgo PRIMARY KEY (id_nivel_riesgo),
        CONSTRAINT uk_cat_nivel_riesgo_codigo UNIQUE (codigo),
        CONSTRAINT ck_cat_nivel_riesgo_peso CHECK (peso BETWEEN 0 AND 100),
        CONSTRAINT ck_cat_nivel_riesgo_color_hex CHECK (color_hex ~ '^#[0-9A-Fa-f]{{6}}$')
    )""")

    for codigo, nombre, color, peso, orden, descripcion in NIVELES:
        op.execute(
            "INSERT INTO cat_nivel_riesgo (codigo, nombre, color_hex, peso, orden, descripcion) "
            f"VALUES ('{codigo}', '{nombre}', '{color}', {peso}, {orden}, '{descripcion}')"
        )

    op.execute(f"""
    CREATE TABLE con_clausula (
        id_clausula          serial        NOT NULL,
        id_contrato          integer       NOT NULL,
        id_nivel_riesgo      smallint,
        id_categoria_riesgo  integer,
        numero_orden         integer       NOT NULL,
        titulo               varchar(255),
        contenido            text          NOT NULL,
        numero_pagina        smallint      NOT NULL,
        coordenadas          jsonb         NOT NULL,
        embedding            vector({DIMENSION_EMBEDDING}),
        explicacion          text,
        {control("con_clausula")},
        CONSTRAINT pk_con_clausula PRIMARY KEY (id_clausula),
        CONSTRAINT fk_con_clausula_id_contrato
            FOREIGN KEY (id_contrato) REFERENCES con_contrato (id_contrato) ON DELETE CASCADE,
        CONSTRAINT fk_con_clausula_id_nivel_riesgo
            FOREIGN KEY (id_nivel_riesgo) REFERENCES cat_nivel_riesgo (id_nivel_riesgo),
        CONSTRAINT fk_con_clausula_id_categoria_riesgo
            FOREIGN KEY (id_categoria_riesgo) REFERENCES cat_catalogo_detalle (id_catalogo_detalle),
        CONSTRAINT uk_con_clausula_id_contrato_numero_orden UNIQUE (id_contrato, numero_orden),
        CONSTRAINT ck_con_clausula_numero_orden CHECK (numero_orden > 0),
        CONSTRAINT ck_con_clausula_numero_pagina CHECK (numero_pagina > 0),
        CONSTRAINT ck_con_clausula_coordenadas CHECK (jsonb_typeof(coordenadas) = 'array')
    )""")

    op.execute("CREATE INDEX ix_con_clausula_id_contrato ON con_clausula (id_contrato)")
    op.execute(
        "CREATE INDEX ix_con_clausula_embedding ON con_clausula "
        "USING hnsw (embedding vector_cosine_ops)"
    )
    op.execute("CREATE INDEX ix_con_contrato_hash_archivo ON con_contrato (hash_archivo)")

    for tabla in ("cat_nivel_riesgo", "con_clausula"):
        for columna in ("usuario_creacion", "usuario_modificacion"):
            op.execute(
                f"ALTER TABLE {tabla} ADD CONSTRAINT fk_{tabla}_{columna} "
                f"FOREIGN KEY ({columna}) REFERENCES seg_usuario (id_usuario)"
            )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_con_contrato_hash_archivo")
    op.execute("DROP TABLE IF EXISTS con_clausula")
    op.execute("DROP TABLE IF EXISTS cat_nivel_riesgo")