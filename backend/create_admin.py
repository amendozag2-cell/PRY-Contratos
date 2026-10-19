from getpass import getpass

from sqlalchemy import select

from app.db import SessionLocal
from app.models import User, UserRole
from app.security import hash_password

email = input("Correo del administrador: ").strip().lower()
full_name = input("Nombre completo: ").strip()
password = getpass("Contraseña (mín. 8 caracteres): ")

with SessionLocal() as db:
    if db.scalar(select(User).where(User.email == email)):
        print("Ese correo ya existe.")
    else:
        db.add(User(email=email, full_name=full_name,
                    hashed_password=hash_password(password), role=UserRole.admin))
        db.commit()
        print("Administrador creado.")