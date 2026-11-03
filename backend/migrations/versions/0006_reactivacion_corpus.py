"""Acción de auditoría para reactivar un documento del corpus legal.

Revision ID: 0006_reactivacion_corpus
Revises: 0005_contexto_condiciones
Create Date: 2026-11-01
"""

from alembic import op

revision = "0006_reactivacion_corpus"
down_revision = "0005_contexto_condiciones"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "INSERT INTO cat_catalogo_detalle (id_catalogo, codigo, nombre, orden) "
        "SELECT c.id_catalogo, 'REACTIVACION_DOCUMENTO_RAG', 'Reactivación de documento del corpus', "
        "(SELECT coalesce(max(d.orden), 0) + 1 FROM cat_catalogo_detalle d WHERE d.id_catalogo = c.id_catalogo) "
        "FROM cat_catalogo c WHERE c.codigo = 'ACCION_AUDITORIA' "
        "ON CONFLICT (id_catalogo, codigo) DO UPDATE SET estado = 'A'"
    )


def downgrade() -> None:
    # La auditoría es inmutable y puede referenciar la acción: solo se inactiva
    op.execute(
        "UPDATE cat_catalogo_detalle d SET estado = 'I' FROM cat_catalogo c "
        "WHERE c.id_catalogo = d.id_catalogo AND c.codigo = 'ACCION_AUDITORIA' "
        "AND d.codigo = 'REACTIVACION_DOCUMENTO_RAG'"
    )