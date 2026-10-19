from fastapi import Request
from sqlalchemy.orm import Session

from app.constantes import CAT_ACCION_AUDITORIA, EXITO
from app.models import Auditoria, Usuario
from app.services.catalogos import obtener_id_detalle


def registrar_evento(
    db: Session,
    request: Request,
    accion: str,
    *,
    usuario: Usuario | None = None,
    correo: str | None = None,
    tabla_afectada: str | None = None,
    id_registro: int | None = None,
    resultado: str = EXITO,
    datos_anteriores: dict | None = None,
    datos_nuevos: dict | None = None,
    observacion: str | None = None,
) -> None:
    """Agrega un evento a aud_auditoria. Quien la llama confirma con db.commit().

    Nunca guarde contraseñas ni tokens en datos_anteriores / datos_nuevos.
    """
    db.add(
        Auditoria(
            id_usuario=usuario.id_usuario if usuario else None,
            id_accion=obtener_id_detalle(db, CAT_ACCION_AUDITORIA, accion),
            correo_usuario=usuario.correo if usuario else correo,
            tabla_afectada=tabla_afectada,
            id_registro=id_registro,
            resultado=resultado,
            datos_anteriores=datos_anteriores,
            datos_nuevos=datos_nuevos,
            observacion=observacion,
            direccion_ip=request.client.host if request.client else None,
            agente_usuario=(request.headers.get("user-agent") or "")[:300] or None,
        )
    )