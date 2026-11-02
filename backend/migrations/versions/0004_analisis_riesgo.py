"""Avance 4: normas que fundamentan el diagnóstico de cada cláusula.

Revision ID: 0004_analisis_riesgo
Revises: 0003_contratos_clausulas
Create Date: 2026-10-28
"""

from alembic import op

revision = "0004_analisis_riesgo"
down_revision = "0003_contratos_clausulas"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    CREATE TABLE con_clausula_fundamento (
        id_clausula          integer       NOT NULL,
        id_fragmento         integer       NOT NULL,
        similitud            numeric(5,4)  NOT NULL,
        estado               char(1)       NOT NULL DEFAULT 'A',
        usuario_creacion     integer,
        fecha_creacion       timestamptz   NOT NULL DEFAULT now(),
        usuario_modificacion integer,
        fecha_modificacion   timestamptz,
        CONSTRAINT pk_con_clausula_fundamento PRIMARY KEY (id_clausula, id_fragmento),
        CONSTRAINT fk_con_clausula_fundamento_id_clausula
            FOREIGN KEY (id_clausula) REFERENCES con_clausula (id_clausula) ON DELETE CASCADE,
        CONSTRAINT fk_con_clausula_fundamento_id_fragmento
            FOREIGN KEY (id_fragmento) REFERENCES rag_fragmento (id_fragmento) ON DELETE CASCADE,
        CONSTRAINT fk_con_clausula_fundamento_usuario_creacion
            FOREIGN KEY (usuario_creacion) REFERENCES seg_usuario (id_usuario),
        CONSTRAINT fk_con_clausula_fundamento_usuario_modificacion
            FOREIGN KEY (usuario_modificacion) REFERENCES seg_usuario (id_usuario),
        CONSTRAINT ck_con_clausula_fundamento_estado CHECK (estado IN ('A', 'I')),
        CONSTRAINT ck_con_clausula_fundamento_similitud CHECK (similitud BETWEEN -1 AND 1)
    )""")
    op.execute(
        "CREATE INDEX ix_con_clausula_fundamento_id_fragmento "
        "ON con_clausula_fundamento (id_fragmento)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS con_clausula_fundamento")