"""
routes/ventas.py  —  Endpoints de Caja y Cobro (Francisco)
===========================================================
Capa de API/Controladores. Solo recibe, valida el formato y llama al servicio.

  GET  /api/ventas/productos-disponibles   -> catálogo para la pantalla Caja
  POST /api/ventas/cobrar                  -> registra la venta (ACID + PEPS)

En main.py (Osvaldo):
    from routes import ventas
    app.include_router(ventas.router)

Requisitos en el resto del proyecto:
  - database.py debe exponer  get_db()  (generador de sesión SQLAlchemy).
  - main.py debe habilitar CORS si el frontend NO se sirve desde FastAPI
    (por ejemplo, abriendo los .html con Live Server o doble clic).
"""

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from database import get_db
from services.venta_service import (
    MENSAJE_STOCK,
    DatosInvalidos,
    StockInsuficiente,
    listar_productos_disponibles,
    registrar_venta,
)

router = APIRouter(prefix="/api/ventas", tags=["Ventas (Caja)"])


# ---------- Esquemas de entrada (lo que manda caja.js) ----------
class DetalleCobro(BaseModel):
    id_producto: int
    cantidad: int = Field(gt=0)


class CobroEntrada(BaseModel):
    id_usuario: int = 1
    forma_pago: str                         # "Efectivo" | "Tarjeta externa"
    monto_recibido: Optional[float] = None  # solo aplica con Efectivo
    detalles: List[DetalleCobro] = Field(min_length=1)


# ---------- Endpoints ----------
@router.get("/productos-disponibles")
def productos_disponibles(db: Session = Depends(get_db)):
    """Productos activos con 'disponible' = true/false según el stock vigente."""
    return listar_productos_disponibles(db)


@router.post("/cobrar", status_code=201)
def cobrar(datos: CobroEntrada, db: Session = Depends(get_db)):
    """
    Registra la venta. Respuestas:
      201 -> venta guardada (incluye id_venta y cambio)
      409 -> inventario insuficiente (no se altera nada)
      400 -> datos inválidos (pago menor al total, producto inexistente, etc.)
    En los errores, 'detail' es un texto que caja.js muestra en la alerta roja.
    """
    try:
        return registrar_venta(
            db,
            id_usuario=datos.id_usuario,
            forma_pago=datos.forma_pago,
            monto_recibido=datos.monto_recibido,
            items=[d.model_dump() for d in datos.detalles],
        )
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
