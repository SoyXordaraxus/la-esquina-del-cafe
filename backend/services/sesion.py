"""
Sesión y control de acceso por rol (RF 1, RF 1.2).

El login entrega un token firmado (JWT HS256) con el id del usuario. El frontend lo
manda en cada petición como  Authorization: Bearer <token>  (lo agrega config.js).
Para descargas abiertas con <a href> o window.open también se acepta ?token=...

Uso en las rutas:
    usuario: Usuario = Depends(usuario_actual)    # cualquier usuario activo
    admin:   Usuario = Depends(requiere_admin)    # solo Administrador
"""
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends, HTTPException, Request
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from database import get_db
from models import Usuario

logger = logging.getLogger("esquina.sesion")

ALGORITMO = "HS256"
HORAS_VIGENCIA = int(os.getenv("SESION_HORAS", "12"))
ROL_ADMIN = "Administrador"
ROL_CAJERO = "Cajero"

SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    SECRET_KEY = "esquina-del-cafe-clave-de-desarrollo"
    logger.warning("SECRET_KEY no está definida: se usa una clave de desarrollo para firmar sesiones.")


def rol_normalizado(rol: Optional[str]) -> str:
    """Contrato del frontend: 'Administrador' | 'Cajero'."""
    return ROL_ADMIN if "admin" in (rol or "").lower() else ROL_CAJERO


def crear_token(usuario: Usuario) -> str:
    expira = datetime.now(timezone.utc) + timedelta(hours=HORAS_VIGENCIA)
    datos = {"sub": str(usuario.id_usuario), "rol": rol_normalizado(usuario.rol), "exp": expira}
    return jwt.encode(datos, SECRET_KEY, algorithm=ALGORITMO)


def _leer_token(request: Request) -> Optional[str]:
    cabecera = request.headers.get("Authorization", "")
    if cabecera.lower().startswith("bearer "):
        return cabecera[7:].strip()
    return request.query_params.get("token")


def usuario_actual(request: Request, db: Session = Depends(get_db)) -> Usuario:
    token = _leer_token(request)
    if not token:
        raise HTTPException(status_code=401, detail="Sesión no iniciada. Inicia sesión de nuevo.")
    try:
        datos = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITMO])
        id_usuario = int(datos["sub"])
    except (JWTError, KeyError, ValueError):
        raise HTTPException(status_code=401, detail="La sesión expiró o no es válida. Inicia sesión de nuevo.")

    usuario = db.get(Usuario, id_usuario)
    if usuario is None or (usuario.estado or "Activo").strip().lower() != "activo":
        raise HTTPException(status_code=401, detail="La cuenta no existe o está desactivada.")
    return usuario


def requiere_admin(usuario: Usuario = Depends(usuario_actual)) -> Usuario:
    if rol_normalizado(usuario.rol) != ROL_ADMIN:
        raise HTTPException(status_code=403, detail="Esta acción requiere rol Administrador.")
    return usuario
