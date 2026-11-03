"""Avance 7: firma electrónica (PAdES) de la versión final negociada del contrato.

- seg_certificado: datos públicos de cada certificado usado (el .p12 y su clave NUNCA se guardan).
- con_documento_firma: versión final del contrato que se firma (PDF vigente con las firmas acumuladas).
- con_firma: cada firma del PDF, hecha en la plataforma o fuera de ella (FirmaEC u otra).
- vw_documento_firma_estado: PENDIENTE, FIRMADO_PARCIAL, FIRMADO_COMPLETO o INVALIDO.
- Acciones de auditoría de la firma.

Revision ID: 0008_firma_electronica
Revises: 0007_negociacion
Create Date: 2026-11-02
"""

from alembic import op

revision = "0008_firma_electronica"
down_revision = "0007_negociacion"
branch_labels = None
depends_on = None

ACCIONES = [
    ("CARGA_VERSION_FINAL", "Carga de la versión final del contrato"),
    ("FIRMA_DOCUMENTO", "Firma electrónica en la plataforma"),
    ("REGISTRO_FIRMA_EXTERNA", "Registro de firma hecha fuera de la plataforma"),
    ("VERIFICACION_FIRMA", "Verificación de firmas electrónicas"),
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
    for codigo, nombre in ACCIONES:
        op.execute(
            "INSERT INTO cat_catalogo_detalle (id_catalogo, codigo, nombre, orden) "
            f"SELECT c.id_catalogo, {_texto(codigo)}, {_texto(nombre)}, "
            "(SELECT coalesce(max(d.orden), 0) + 1 FROM cat_catalogo_detalle d WHERE d.id_catalogo = c.id_catalogo) "
            "FROM cat_catalogo c WHERE c.codigo = 'ACCION_AUDITORIA' "
            "ON CONFLICT (id_catalogo, codigo) DO UPDATE SET estado = 'A'"
        )

    op.execute(f"""
    CREATE TABLE seg_certificado (
        id_certificado          serial        NOT NULL,
        emisor                  varchar(255)  NOT NULL,
        numero_serie            varchar(100)  NOT NULL,
        huella_sha256           char(64)      NOT NULL,
        nombre_titular          varchar(200)  NOT NULL,
        identificacion_titular  varchar(20),
        fecha_inicio_vigencia   timestamptz   NOT NULL,
        fecha_fin_vigencia      timestamptz   NOT NULL,
        {control("seg_certificado")},
        CONSTRAINT pk_seg_certificado PRIMARY KEY (id_certificado),
        CONSTRAINT uk_seg_certificado_huella_sha256 UNIQUE (huella_sha256),
        CONSTRAINT uk_seg_certificado_emisor_numero_serie UNIQUE (emisor, numero_serie),
        CONSTRAINT ck_seg_certificado_vigencia CHECK (fecha_fin_vigencia > fecha_inicio_vigencia)
    )""")

    op.execute(f"""
    CREATE TABLE con_documento_firma (
        id_documento_firma        serial        NOT NULL,
        id_contrato               integer       NOT NULL,
        numero_version            smallint      NOT NULL,
        nombre_archivo            varchar(255)  NOT NULL,
        ruta_archivo              varchar(500)  NOT NULL,
        hash_archivo              char(64)      NOT NULL,
        numero_firmas_requeridas  smallint      NOT NULL DEFAULT 2,
        {control("con_documento_firma")},
        CONSTRAINT pk_con_documento_firma PRIMARY KEY (id_documento_firma),
        CONSTRAINT uk_con_documento_firma_id_contrato_numero_version UNIQUE (id_contrato, numero_version),
        CONSTRAINT ck_con_documento_firma_numero_version CHECK (numero_version > 0),
        CONSTRAINT ck_con_documento_firma_numero_firmas_requeridas CHECK (numero_firmas_requeridas > 0),
        CONSTRAINT fk_con_documento_firma_id_contrato
            FOREIGN KEY (id_contrato) REFERENCES con_contrato (id_contrato) ON DELETE CASCADE
    )""")

    op.execute(f"""
    CREATE TABLE con_firma (
        id_firma            serial        NOT NULL,
        id_documento_firma  integer       NOT NULL,
        id_certificado      integer       NOT NULL,
        id_usuario          integer,
        numero_orden        smallint      NOT NULL,
        fecha_firma         timestamptz   NOT NULL,
        hash_documento      char(64)      NOT NULL,
        motivo              varchar(255),
        es_integra          boolean       NOT NULL,
        es_confiable        boolean       NOT NULL DEFAULT false,
        fecha_verificacion  timestamptz   NOT NULL DEFAULT now(),
        {control("con_firma")},
        CONSTRAINT pk_con_firma PRIMARY KEY (id_firma),
        CONSTRAINT uk_con_firma_id_documento_firma_numero_orden UNIQUE (id_documento_firma, numero_orden),
        CONSTRAINT ck_con_firma_numero_orden CHECK (numero_orden > 0),
        CONSTRAINT fk_con_firma_id_documento_firma
            FOREIGN KEY (id_documento_firma) REFERENCES con_documento_firma (id_documento_firma) ON DELETE CASCADE,
        CONSTRAINT fk_con_firma_id_certificado
            FOREIGN KEY (id_certificado) REFERENCES seg_certificado (id_certificado),
        CONSTRAINT fk_con_firma_id_usuario
            FOREIGN KEY (id_usuario) REFERENCES seg_usuario (id_usuario)
    )""")
    op.execute("CREATE INDEX ix_con_firma_id_certificado ON con_firma (id_certificado)")

    # Estado de firma calculado: no se guarda para que nunca contradiga a con_firma
    op.execute("""
    CREATE VIEW vw_documento_firma_estado AS
    SELECT d.id_documento_firma,
           d.id_contrato,
           count(f.id_firma)::int AS numero_firmas,
           CASE
               WHEN bool_or(NOT f.es_integra) THEN 'INVALIDO'
               WHEN count(f.id_firma) = 0 THEN 'PENDIENTE'
               WHEN count(f.id_firma) < d.numero_firmas_requeridas THEN 'FIRMADO_PARCIAL'
               ELSE 'FIRMADO_COMPLETO'
           END AS estado_firma,
           coalesce((array_agg(f.hash_documento ORDER BY f.numero_orden DESC))[1], d.hash_archivo) AS hash_vigente
    FROM con_documento_firma d
    LEFT JOIN con_firma f ON f.id_documento_firma = d.id_documento_firma AND f.estado = 'A'
    GROUP BY d.id_documento_firma""")


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS vw_documento_firma_estado")
    op.execute("DROP TABLE IF EXISTS con_firma")
    op.execute("DROP TABLE IF EXISTS con_documento_firma")
    op.execute("DROP TABLE IF EXISTS seg_certificado")
    # La auditoría es inmutable y puede referenciar las acciones: solo se inactivan
    op.execute(
        "UPDATE cat_catalogo_detalle d SET estado = 'I' FROM cat_catalogo c "
        "WHERE c.id_catalogo = d.id_catalogo AND c.codigo = 'ACCION_AUDITORIA' "
        "AND d.codigo IN ('CARGA_VERSION_FINAL', 'FIRMA_DOCUMENTO', 'REGISTRO_FIRMA_EXTERNA', 'VERIFICACION_FIRMA')"
    )