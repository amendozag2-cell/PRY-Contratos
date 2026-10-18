from sqlalchemy import update

from app.models import User
from tests.conftest import TestingSession

USUARIO = {
    "email": "joel_21@outlook.com",
    "full_name": "Joel Barrionuevo",
    "password": "Clave1234",
    "role": "freelancer",
}


def registrar(client, **cambios):
    return client.post("/auth/register", json={**USUARIO, **cambios})


def login(client, email=USUARIO["email"], password=USUARIO["password"]):
    return client.post("/auth/login", data={"username": email, "password": password})


def headers(token):
    return {"Authorization": f"Bearer {token}"}


# --- Registro ---

def test_registro_exitoso(client):
    r = registrar(client)
    assert r.status_code == 201
    body = r.json()
    assert body["email"] == USUARIO["email"]
    assert body["role"] == "freelancer"
    assert "hashed_password" not in body and "password" not in body


def test_registro_email_duplicado(client):
    registrar(client)
    r = registrar(client, email=USUARIO["email"].upper())
    assert r.status_code == 409


def test_registro_como_admin_rechazado(client):
    assert registrar(client, role="admin").status_code == 422


def test_registro_password_debil(client):
    assert registrar(client, password="sololetras").status_code == 422


# --- Login ---

def test_login_exitoso_ignora_mayusculas(client):
    registrar(client)
    r = login(client, email=USUARIO["email"].upper())
    assert r.status_code == 200
    assert r.json()["token_type"] == "bearer"
    assert r.json()["access_token"]


def test_login_password_incorrecta(client):
    registrar(client)
    r = login(client, password="Mala1234")
    assert r.status_code == 401
    assert r.json()["detail"] == "Email o contraseña incorrectos"


def test_login_usuario_inexistente(client):
    r = login(client, email="nadie@test.com")
    assert r.status_code == 401
    assert r.json()["detail"] == "Email o contraseña incorrectos"


def test_login_password_mayor_72_bytes_no_rompe(client):
    registrar(client)
    assert login(client, password="a" * 100).status_code == 401


def test_login_cuenta_desactivada(client):
    registrar(client)
    with TestingSession() as db:
        db.execute(update(User).values(is_active=False))
        db.commit()
    assert login(client).status_code == 403


# --- Perfil (/auth/me) ---

def test_me_sin_token(client):
    assert client.get("/auth/me").status_code == 401


def test_me_token_invalido(client):
    assert client.get("/auth/me", headers=headers("token-falso")).status_code == 401


def test_me_con_token(client):
    registrar(client)
    token = login(client).json()["access_token"]
    r = client.get("/auth/me", headers=headers(token))
    assert r.status_code == 200
    assert r.json()["email"] == USUARIO["email"]
