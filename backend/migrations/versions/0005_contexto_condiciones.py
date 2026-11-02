"""Avance 4.1: contexto del usuario y verificación de las condiciones acordadas.

- con_contrato guarda el papel del usuario en el contrato y lo que dice que acordaron.
- con_condicion guarda cada condición acordada y si el contrato la cubre.
- Nuevos catálogos ROL_PARTE y COBERTURA_CONDICION (el color va en "valor"),
  la categoría de riesgo RELACION_LABORAL, la acción ACTUALIZACION_CONTEXTO y el
  parámetro RAG_SIMILITUD_MINIMA.

Revision ID: 0005_contexto_condiciones
Revises: 0004_analisis_riesgo
Create Date: 2026-10-31
"""

from alembic import op

revision = "0005_contexto_condiciones"
down_revision = "0004_analisis_riesgo"
branch_labels = None
depends_on = None

MAX_CONTEXTO = 4000

CATALOGOS_NUEVOS = {
    ("ROL_PARTE", "Papel del usuario en el contrato"): [
        # codigo, nombre, descripcion, valor
        ("PRESTADOR", "Presto el servicio", "Ejecuto el trabajo y recibo el pago", None),
        ("CONTRATANTE", "Contrato el servicio", "Recibo el trabajo y pago por él", None),
    ],
    ("COBERTURA_CONDICION", "Cobertura de una condición acordada en el contrato"): [
        ("CUBIERTA", "Cubierta", "El contrato la recoge de forma clara y completa", "#16A34A"),
        ("PARCIAL", "Parcial", "El contrato la recoge de forma incompleta o con excepciones", "#F59E0B"),
        ("CONTRADICHA", "Contradicha", "El contrato establece lo contrario", "#DC2626"),
        ("AUSENTE", "Ausente", "El contrato no la menciona", "#64748B"),
    ],
}

# Valores que se agregan a catálogos existentes: catálogo, codigo, nombre, descripcion
DETALLES_NUEVOS = [
    ("CATEGORIA_RIESGO", "RELACION_LABORAL", "Relación laboral encubierta",
     "Horario fijo, subordinación o pago periódico bajo la forma de un contrato civil"),
    ("ACCION_AUDITORIA", "ACTUALIZACION_CONTEXTO", "Actualización del contexto de un contrato", None),
]


def _texto(v):
    return "NULL" if v is None else "'" + v.replace("'", "''") + "'"


def _insertar_detalle(catalogo, codigo, nombre, descripcion, valor=None, orden=None):
    orden_sql = str(orden) if orden is not None else (
        "(SELECT coalesce(max(d.orden), 0) + 1 FROM cat_catalogo_detalle d "
        "WHERE d.id_catalogo = c.id_catalogo)"
    )
    op.execute(
        "INSERT INTO cat_catalogo_detalle (id_catalogo, codigo, nombre, descripcion, valor, orden) "
        f"SELECT c.id_catalogo, {_texto(codigo)}, {_texto(nombre)}, {_texto(descripcion)}, "
        f"{_texto(valor)}, {orden_sql} FROM cat_catalogo c WHERE c.codigo = {_texto(catalogo)} "
        "ON CONFLICT (id_catalogo, codigo) DO UPDATE SET estado = 'A'"
    )


def upgrade() -> None:
    # ----------------------------------------------------------- catálogos
    for (cat_codigo, cat_nombre), detalles in CATALOGOS_NUEVOS.items():
        op.execute(
            f"INSERT INTO cat_catalogo (codigo, nombre) VALUES ({_texto(cat_codigo)}, {_texto(cat_nombre)}) "
            "ON CONFLICT (codigo) DO UPDATE SET estado = 'A'"
        )
        for orden, (codigo, nombre, descripcion, valor) in enumerate(detalles, start=1):
            _insertar_detalle(cat_codigo, codigo, nombre, descripcion, valor, orden)

    for catalogo, codigo, nombre, descripcion in DETALLES_NUEVOS:
        _insertar_detalle(catalogo, codigo, nombre, descripcion)

    op.execute(
        "INSERT INTO cat_parametro (codigo, nombre, valor, tipo_dato, descripcion) VALUES "
        "('RAG_SIMILITUD_MINIMA', 'Similitud mínima de normas', '0.30', 'DECIMAL', "
        "'Las normas menos parecidas a la cláusula no se envían al modelo') "
        "ON CONFLICT (codigo) DO UPDATE SET estado = 'A'"
    )

    # ------------------------------------------------------ con_contrato
    op.execute(f"""
    ALTER TABLE con_contrato
        ADD COLUMN id_rol_parte     integer,
        ADD COLUMN contexto_usuario text,
        ADD CONSTRAINT fk_con_contrato_id_rol_parte
            FOREIGN KEY (id_rol_parte) REFERENCES cat_catalogo_detalle (id_catalogo_detalle),
        ADD CONSTRAINT ck_con_contrato_contexto_usuario
            CHECK (char_length(contexto_usuario) <= {MAX_CONTEXTO})
    """)

    # ------------------------------------------------------ con_condicion
    op.execute("""
    CREATE TABLE con_condicion (
        id_condicion         serial        NOT NULL,
        id_contrato          integer       NOT NULL,
        id_cobertura         integer       NOT NULL,
        id_clausula          integer,
        numero_orden         smallint      NOT NULL,
        descripcion          varchar(500)  NOT NULL,
        explicacion          text,
        estado               char(1)       NOT NULL DEFAULT 'A',
        usuario_creacion     integer,
        fecha_creacion       timestamptz   NOT NULL DEFAULT now(),
        usuario_modificacion integer,
        fecha_modificacion   timestamptz,
        CONSTRAINT pk_con_condicion PRIMARY KEY (id_condicion),
        CONSTRAINT fk_con_condicion_id_contrato
            FOREIGN KEY (id_contrato) REFERENCES con_contrato (id_contrato) ON DELETE CASCADE,
        CONSTRAINT fk_con_condicion_id_cobertura
            FOREIGN KEY (id_cobertura) REFERENCES cat_catalogo_detalle (id_catalogo_detalle),
        CONSTRAINT fk_con_condicion_id_clausula
            FOREIGN KEY (id_clausula) REFERENCES con_clausula (id_clausula) ON DELETE SET NULL,
        CONSTRAINT fk_con_condicion_usuario_creacion
            FOREIGN KEY (usuario_creacion) REFERENCES seg_usuario (id_usuario),
        CONSTRAINT fk_con_condicion_usuario_modificacion
            FOREIGN KEY (usuario_modificacion) REFERENCES seg_usuario (id_usuario),
        CONSTRAINT uk_con_condicion_id_contrato_numero_orden UNIQUE (id_contrato, numero_orden),
        CONSTRAINT ck_con_condicion_estado CHECK (estado IN ('A', 'I')),
        CONSTRAINT ck_con_condicion_numero_orden CHECK (numero_orden > 0)
    )""")
    op.execute("CREATE INDEX ix_con_condicion_id_clausula ON con_condicion (id_clausula)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS con_condicion")
    op.execute("""
    ALTER TABLE con_contrato
        DROP CONSTRAINT IF EXISTS ck_con_contrato_contexto_usuario,
        DROP CONSTRAINT IF EXISTS fk_con_contrato_id_rol_parte,
        DROP COLUMN IF EXISTS contexto_usuario,
        DROP COLUMN IF EXISTS id_rol_parte
    """)
    op.execute("DELETE FROM cat_parametro WHERE codigo = 'RAG_SIMILITUD_MINIMA'")

    # Las cláusulas clasificadas como relación laboral pierden la categoría
    op.execute("""
    UPDATE con_clausula SET id_categoria_riesgo = NULL
    WHERE id_categoria_riesgo IN (
        SELECT d.id_catalogo_detalle FROM cat_catalogo_detalle d
        JOIN cat_catalogo c ON c.id_catalogo = d.id_catalogo
        WHERE c.codigo = 'CATEGORIA_RIESGO' AND d.codigo = 'RELACION_LABORAL')
    """)
    op.execute("""
    DELETE FROM cat_catalogo_detalle d USING cat_catalogo c
    WHERE c.id_catalogo = d.id_catalogo AND c.codigo = 'CATEGORIA_RIESGO' AND d.codigo = 'RELACION_LABORAL'
    """)
    # La auditoría es inmutable y puede referenciar la acción: solo se inactiva
    op.execute("""
    UPDATE cat_catalogo_detalle d SET estado = 'I' FROM cat_catalogo c
    WHERE c.id_catalogo = d.id_catalogo AND c.codigo = 'ACCION_AUDITORIA'
      AND d.codigo = 'ACTUALIZACION_CONTEXTO'
    """)
    for cat_codigo, _ in CATALOGOS_NUEVOS:
        op.execute(
            "DELETE FROM cat_catalogo_detalle WHERE id_catalogo = "
            f"(SELECT id_catalogo FROM cat_catalogo WHERE codigo = {_texto(cat_codigo)})"
        )
        op.execute(f"DELETE FROM cat_catalogo WHERE codigo = {_texto(cat_codigo)}")