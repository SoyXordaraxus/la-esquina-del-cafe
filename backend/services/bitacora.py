"""Registro en la tabla bitacora (RF 13), compartido por rutas y servicios."""
from sqlalchemy.orm import Session

from models import Bitacora


def registrar_bitacora(db: Session, id_usuario: int, accion: str, detalle: str) -> None:
    """Agrega el registro a la sesión; se guarda con el commit de la operación."""
    db.add(Bitacora(id_usuario=id_usuario, accion=accion, detalle=(detalle or "")[:255]))
