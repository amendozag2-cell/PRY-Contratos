from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select

from app.config import settings
from app.constantes import (
    ACC_INICIO_SESION,
    ACC_INICIO_SESION_FALLIDO,
    ACC_REGISTRO_USUARIO,
    FALLO,
    PAR_SESION_MINUTOS,
)
from app.deps import DbSession, UsuarioActual
from app.models import ESTADO_ACTIVO, Rol, Usuario
from app.schemas import Token, UsuarioCrear, UsuarioSalida
from app.security import crear_token, hash_clave, verificar_clave
from app.services.auditoria import registrar_evento
from app.services.parametros import obtener_entero

router = APIRouter(prefix="/auth", tags=["Autenticación"])


@router.post("/registro", response_model=UsuarioSalida, status_code=status.HTTP_201_CREATED)
def registrar(datos: UsuarioCrear, request: Request, db: DbSession):
    correo = datos.correo.lower()
    if db.scalar(select(Usuario.id_usuario).where(Usuario.correo == correo)):
        raise HTTPException(status.HTTP_409_CONFLICT, "El correo ya está registrado")

    rol = db.scalar(select(Rol).where(Rol.codigo == datos.rol, Rol.estado == ESTADO_ACTIVO))
    if rol is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "El rol seleccionado no está disponible")

    usuario = Usuario(
        rol=rol,
        correo=correo,
        nombres=datos.nombres,
        apellidos=datos.apellidos,
        clave_hash=hash_clave(datos.clave),
        nombre_empresa=datos.nombre_empresa,
        ruc_empresa=datos.ruc_empresa,
    )
    db.add(usuario)
    db.flush()  # asigna id_usuario antes de registrar la auditoría

    registrar_evento(
        db, request, ACC_REGISTRO_USUARIO,
        usuario=usuario,
        tabla_afectada="seg_usuario",
        id_registro=usuario.id_usuario,
        datos_nuevos={
            "correo": usuario.correo,
            "rol": rol.codigo,
            "nombre_empresa": usuario.nombre_empresa,
        },
    )
    db.commit()
    db.refresh(usuario)
    return usuario


@router.post("/login", response_model=Token)
def iniciar_sesion(
    request: Request,
    formulario: Annotated[OAuth2PasswordRequestForm, Depends()],
    db: DbSession,
):
    correo = formulario.username.strip().lower()
    usuario = db.scalar(select(Usuario).where(Usuario.correo == correo))

    def rechazar(motivo: str, codigo: int, mensaje: str):
        registrar_evento(
            db, request, ACC_INICIO_SESION_FALLIDO,
            usuario=usuario, correo=correo, resultado=FALLO, observacion=motivo,
        )
        db.commit()
        raise HTTPException(codigo, mensaje)

    # Al usuario se le muestra un mensaje genérico; el motivo real queda en la auditoría
    if usuario is None:
        rechazar("Correo no registrado", status.HTTP_401_UNAUTHORIZED, "Correo o contraseña incorrectos")
    if not verificar_clave(formulario.password, usuario.clave_hash):
        rechazar("Contraseña incorrecta", status.HTTP_401_UNAUTHORIZED, "Correo o contraseña incorrectos")
    if usuario.estado != ESTADO_ACTIVO:
        rechazar("Cuenta inactiva", status.HTTP_403_FORBIDDEN, "La cuenta está desactivada")

    usuario.fecha_ultimo_acceso = datetime.now(timezone.utc)
    registrar_evento(
        db, request, ACC_INICIO_SESION,
        usuario=usuario, tabla_afectada="seg_usuario", id_registro=usuario.id_usuario,
    )
    db.commit()

    minutos = obtener_entero(db, PAR_SESION_MINUTOS, settings.jwt_expire_minutes)
    return Token(access_token=crear_token(usuario.id_usuario, usuario.codigo_rol, minutos))


@router.get("/perfil", response_model=UsuarioSalida)
def perfil(usuario: UsuarioActual):
    return usuario