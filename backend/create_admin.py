"""Crea el usuario administrador. Uso: uv run python create_admin.py"""

from getpass import getpass

from sqlalchemy import select

from app.constantes import ROL_ADMINISTRADOR
from app.db import SessionLocal
from app.models import Rol, Usuario
from app.security import hash_clave

correo = input("Correo del administrador: ").strip().lower()
nombres = input("Nombres: ").strip()
apellidos = input("Apellidos: ").strip()
clave = getpass("Contraseña (mín. 8 caracteres, no se muestra al escribir): ")

if len(clave) < 8:
    raise SystemExit("La contraseña debe tener al menos 8 caracteres.")

with SessionLocal() as db:
    if db.scalar(select(Usuario.id_usuario).where(Usuario.correo == correo)):
        raise SystemExit("Ese correo ya está registrado.")
    rol = db.scalar(select(Rol).where(Rol.codigo == ROL_ADMINISTRADOR))
    if rol is None:
        raise SystemExit("No existe el rol ADMINISTRADOR. Ejecute primero: uv run alembic upgrade head")
    db.add(Usuario(rol=rol, correo=correo, nombres=nombres, apellidos=apellidos,
                   clave_hash=hash_clave(clave)))
    db.commit()
    print("Administrador creado.")