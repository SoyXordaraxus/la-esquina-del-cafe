"""
routes/ventas.py  —  Endpoints de Caja y Cobro (Francisco)
===========================================================
Capa de API/Controladores. Solo recibe, valida el formato y llama al servicio.

  GET  /api/ventas/productos-disponibles   -> catálogo para la pantalla Caja
  POST /api/ventas/cobrar                  -> registra la venta (ACID + PEPS)
  GET  /api/ventas/motivos-cancelacion     -> catálogo de motivos (RF 18)
  GET  /api/ventas/historial               -> lista de ventas (para ventas.html)
  GET  /api/ventas/{id_venta}              -> detalle con precios e insumos usados (RF 3)
  POST /api/ventas/{id_venta}/cancelar     -> cancelación/devolución, solo Admin (RF 9)

En main.py (Osvaldo):
    from routes import ventas
    app.include_router(ventas.router)

Requisitos en el resto del proyecto:
  - database.py debe exponer  get_db()  (generador de sesión SQLAlchemy).
  - main.py debe habilitar CORS si el frontend NO se sirve desde FastAPI
    (por ejemplo, abriendo los .html con Live Server o doble clic).
"""

import time
from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from database import get_db
from models import Usuario
from services.sesion import requiere_admin, usuario_actual
from services.venta_service import (
    MENSAJE_STOCK,
    MOTIVOS_CANCELACION,
    DatosInvalidos,
    NoAutorizado,
    NoEncontrado,
    StockInsuficiente,
    VentaYaCancelada,
    cancelar_venta,
    listar_productos_disponibles,
    listar_ventas,
    obtener_venta,
    registrar_venta,
)

router = APIRouter(prefix="/api/ventas", tags=["Ventas (Caja)"])


# ---------- Esquemas de entrada (lo que manda caja.js) ----------
class DetalleCobro(BaseModel):
    id_producto: int
    cantidad: int = Field(gt=0)


class CobroEntrada(BaseModel):
    id_usuario: Optional[int] = None        # se ignora: el cajero se toma de la sesión
    forma_pago: str                         # "Efectivo" | "Tarjeta externa"
    monto_recibido: Optional[float] = None  # solo aplica con Efectivo
    detalles: List[DetalleCobro] = Field(min_length=1)


class CancelacionEntrada(BaseModel):
    id_usuario: Optional[int] = None   # se ignora: quien autoriza se toma de la sesión
    motivo: str              # uno de MOTIVOS_CANCELACION


# ---------- Endpoints ----------
@router.get("/productos-disponibles", dependencies=[Depends(usuario_actual)])
def productos_disponibles(db: Session = Depends(get_db)):
    """
    {"productos": [...], "stock_insumos": {id_insumo: cantidad}}. Cada producto trae
    'disponible', 'max_porciones' y su 'receta' [{id_insumo, cantidad}] (RF 7.1).
    """
    return listar_productos_disponibles(db)


@router.post("/cobrar", status_code=201)
def cobrar(datos: CobroEntrada, db: Session = Depends(get_db), cajero: Usuario = Depends(usuario_actual)):
    """
    Registra la venta. Respuestas:
      201 -> venta guardada (incluye id_venta y cambio)
      409 -> inventario insuficiente (no se altera nada)
      400 -> datos inválidos (pago menor al total, producto inexistente, etc.)
    En los errores, 'detail' es un texto que caja.js muestra en la alerta roja.
    """
    inicio = time.perf_counter()
    try:
        resultado = registrar_venta(
            db,
            id_usuario=cajero.id_usuario,
            forma_pago=datos.forma_pago,
            monto_recibido=datos.monto_recibido,
            items=[d.model_dump() for d in datos.detalles],
        )
        # RF 15: evidencia de que el cobro tarda menos de 2 s.
        resultado["tiempo_ms"] = round((time.perf_counter() - inicio) * 1000, 1)
        return resultado
    except StockInsuficiente as error:
        return JSONResponse(
            status_code=409,
            content={"detail": MENSAJE_STOCK, "faltantes": error.faltantes},
        )
    except DatosInvalidos as error:
        raise HTTPException(status_code=400, detail=str(error))
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=400, detail="Usuario o producto no válido. No se realizó el cobro.")


@router.get("/motivos-cancelacion")
def motivos_cancelacion():
    """Opciones para el <select> de cancelación (sin texto libre, RF 18)."""
    return list(MOTIVOS_CANCELACION)


@router.get("/historial", dependencies=[Depends(requiere_admin)])
def historial(fecha: Optional[date] = None, limite: int = 100, db: Session = Depends(get_db)):
    """Ventas más recientes primero. ?fecha=2026-11-18 filtra un día."""
    return listar_ventas(db, fecha=fecha, limite=min(max(limite, 1), 500))


@router.get("/{id_venta}", dependencies=[Depends(requiere_admin)])
def detalle_venta(id_venta: int, db: Session = Depends(get_db)):
    """Detalle con el precio cobrado y los insumos que realmente se descontaron."""
    try:
        return obtener_venta(db, id_venta)
    except NoEncontrado as error:
        raise HTTPException(status_code=404, detail=str(error))


@router.post("/{id_venta}/cancelar")
def cancelar(id_venta: int, datos: CancelacionEntrada, db: Session = Depends(get_db), admin: Usuario = Depends(requiere_admin)):
    """
    Respuestas:
      200 -> venta cancelada; insumos devueltos a su lote (o a merma si caducó)
      403 -> el usuario no es Administrador
      404 -> la venta no existe
      409 -> la venta ya estaba cancelada
      400 -> motivo no válido
    """
    try:
        return cancelar_venta(db, id_venta=id_venta, id_usuario=admin.id_usuario, motivo=datos.motivo)
    except NoAutorizado as error:
        raise HTTPException(status_code=403, detail=str(error))
    except NoEncontrado as error:
        raise HTTPException(status_code=404, detail=str(error))
    except VentaYaCancelada as error:
        raise HTTPException(status_code=409, detail=str(error))
    except DatosInvalidos as error:
        raise HTTPException(status_code=400, detail=str(error))