"""Registro, inicio de sesión, permisos por rol y auditoría."""

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from app.models import Auditoria, CatalogoDetalle

from .conftest import CLAVE, registrar


def _acciones(db, correo: str) -> list[tuple[str, str]]:
    return [
        (codigo, resultado) for codigo, resultado in db.execute(
            select(CatalogoDetalle.codigo, Auditoria.resultado)
            .join(CatalogoDetalle, CatalogoDetalle.id_catalogo_detalle == Auditoria.id_accion)
            .where(Auditoria.correo_usuario == correo)
            .order_by(Auditoria.id_auditoria)
        ).all()
    ]


def test_registro_y_perfil(cliente):
    encabezados = registrar(cliente, "freelancer@prueba.ec")
    perfil = cliente.get("/auth/perfil", headers=encabezados)
    assert perfil.status_code == 200
    assert perfil.json()["correo"] == "freelancer@prueba.ec"
    assert perfil.json()["rol"] == "FREELANCER"


def test_correo_duplicado_se_rechaza(cliente):
    registrar(cliente, "repetido@prueba.ec")
    r = cliente.post("/auth/registro", json={
        "correo": "REPETIDO@prueba.ec", "nombres": "Ana", "apellidos": "Pérez", "clave": CLAVE})
    assert r.status_code == 409


def test_pyme_debe_indicar_empresa_y_ruc_valido(cliente):
    base = {"correo": "pyme@prueba.ec", "nombres": "Ana", "apellidos": "Pérez", "clave": CLAVE, "rol": "PYME"}
    assert cliente.post("/auth/registro", json=base).status_code == 422
    assert cliente.post("/auth/registro", json={**base, "nombre_empresa": "ACME", "ruc_empresa": "123"}).status_code == 422
    r = cliente.post("/auth/registro", json={**base, "nombre_empresa": "ACME", "ruc_empresa": "0912345678001"})
    assert r.status_code == 201


def test_clave_corta_se_rechaza(cliente):
    r = cliente.post("/auth/registro", json={
        "correo": "corta@prueba.ec", "nombres": "Ana", "apellidos": "Pérez", "clave": "123"})
    assert r.status_code == 422


def test_login_incorrecto_no_revela_el_motivo_y_queda_auditado(cliente, db):
    registrar(cliente, "auditado@prueba.ec")
    r1 = cliente.post("/auth/login", data={"username": "auditado@prueba.ec", "password": "equivocada"})
    r2 = cliente.post("/auth/login", data={"username": "noexiste@prueba.ec", "password": "equivocada"})
    assert r1.status_code == r2.status_code == 401
    assert r1.json()["detail"] == r2.json()["detail"]
    acciones = _acciones(db, "auditado@prueba.ec")
    assert ("REGISTRO_USUARIO", "EXITO") in acciones
    assert ("INICIO_SESION", "EXITO") in acciones
    assert ("INICIO_SESION_FALLIDO", "FALLO") in acciones


def test_sin_token_o_token_falso_no_hay_acceso(cliente):
    assert cliente.get("/contratos").status_code == 401
    assert cliente.get("/contratos", headers={"Authorization": "Bearer falso"}).status_code == 401


def test_solo_el_administrador_entra_al_panel(cliente, freelancer, administrador):
    assert cliente.get("/admin/resumen", headers=freelancer).status_code == 403
    assert cliente.get("/admin/corpus", headers=freelancer).status_code == 403
    assert cliente.get("/admin/resumen", headers=administrador).status_code == 200


@pytest.mark.parametrize("sentencia", ["UPDATE aud_auditoria SET observacion = 'x'", "DELETE FROM aud_auditoria"])
def test_la_auditoria_no_se_puede_modificar(cliente, db, sentencia):
    """El trigger de aud_auditoria impide UPDATE y DELETE (bitácora inmutable)."""
    registrar(cliente)  # garantiza que haya al menos un evento
    with pytest.raises(DBAPIError):
        with db.begin_nested():
            db.execute(text(sentencia))


def test_administrador_consulta_la_auditoria(cliente, administrador):
    r = cliente.get("/admin/auditoria", headers=administrador)
    assert r.status_code == 200
    assert r.json()["total"] >= 1