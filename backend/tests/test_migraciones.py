"""Las migraciones de Alembic se pueden revertir por completo y volver a aplicar."""

from sqlalchemy import inspect, text

from app.db import engine

from .conftest import aplicar_migraciones, revertir_migraciones


def _tablas() -> set[str]:
    return set(inspect(engine).get_table_names())


def test_revertir_y_volver_a_aplicar_todas_las_migraciones():
    tablas = _tablas()
    assert {"seg_usuario", "con_contrato", "rag_fragmento", "con_contrapropuesta", "con_firma"} <= tablas

    revertir_migraciones("base")
    assert _tablas() <= {"alembic_version"}

    aplicar_migraciones("head")
    assert _tablas() == tablas
    with engine.connect() as conexion:
        version = conexion.execute(text("SELECT version_num FROM alembic_version")).scalar()
        roles = conexion.execute(text("SELECT count(*) FROM seg_rol")).scalar()
    assert version.startswith("0008")
    assert roles >= 3