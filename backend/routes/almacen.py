from datetime import date
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db
from models import Insumo, Proveedor, LoteInsumo, MovimientoInventario, Merma

router = APIRouter(prefix="/api/almacen", tags=["Almacén"])


class EntradaLoteSchema(BaseModel):
    id_insumo: int
    id_proveedor: Optional[int] = None
    cantidad_ingresada: float
    unidad_compra: str  # "kg", "g", "L", "ml", "unidades"
    costo_unitario: float
    caducidad: Optional[date] = None
    numero_factura: Optional[str] = None
    id_usuario: int = 1


class RegistroMermaSchema(BaseModel):
    id_lote: int
    cantidad: float
    motivo: str
    id_usuario: int = 1


def convertir_a_unidad_base(cantidad: float, unidad_compra: str, unidad_base: str) -> float:
    u_comp = unidad_compra.strip().lower()
    u_base = unidad_base.strip().lower()

    if u_comp == u_base:
        return cantidad
    if u_comp == "kg" and u_base in ("g", "gr", "gramos"):
        return cantidad * 1000.0
    if u_comp in ("g", "gr", "gramos") and u_base == "kg":
        return cantidad / 1000.0
    if u_comp in ("l", "lt", "litros") and u_base in ("ml", "mililitros"):
        return cantidad * 1000.0
    if u_comp in ("ml", "mililitros") and u_base in ("l", "lt", "litros"):
        return cantidad / 1000.0

    return cantidad


# =========================================================
# 1. RECEPCIÓN DE MERCANCÍA (04_Recepción)
# =========================================================
@router.get("/catalogos")
def obtener_catalogos_recepcion(db: Session = Depends(get_db)):
    insumos = db.query(Insumo).filter(Insumo.estado == "Activo").all()
    proveedores = db.query(Proveedor).all()

    return {
        "insumos": [
            {
                "id_insumo": i.id_insumo,
                "nombre": i.nombre,
                "categoria": i.categoria,
                "unidad_medida": i.unidad_medida,
                "es_perecedero": i.es_perecedero
            }
            for i in insumos
        ],
        "proveedores": [
            {
                "id_proveedor": p.id_proveedor,
                "nombre": p.nombre
            }
            for p in proveedores
        ]
    }


@router.get("/lotes")
def listar_lotes(db: Session = Depends(get_db)):
    lotes = db.query(LoteInsumo).order_by(LoteInsumo.fecha_entrada.desc()).limit(30).all()
    resultado = []
    for l in lotes:
        ins = db.query(Insumo).filter(Insumo.id_insumo == l.id_insumo).first()
        prov = db.query(Proveedor).filter(Proveedor.id_proveedor == l.id_proveedor).first() if l.id_proveedor else None
        resultado.append({
            "id_lote": l.id_lote,
            "id_insumo": l.id_insumo,
            "insumo": ins.nombre if ins else f"Insumo #{l.id_insumo}",
            "unidad": ins.unidad_medida if ins else "",
            "proveedor": prov.nombre if prov else "Sin proveedor",
            "cantidad_recibida": float(l.cantidad_recibida),
            "cantidad_disponible": float(l.cantidad_disponible),
            "costo_unitario": float(l.costo_unitario),
            "caducidad": str(l.caducidad) if l.caducidad else "No perecedero",
            "numero_factura": l.numero_factura or "—",
            "fecha_entrada": l.fecha_entrada.strftime("%Y-%m-%d %H:%M") if l.fecha_entrada else ""
        })
    return {"lotes": resultado}


@router.post("/recepcion")
def registrar_entrada_lote(datos: EntradaLoteSchema, db: Session = Depends(get_db)):
    insumo = db.query(Insumo).filter(Insumo.id_insumo == datos.id_insumo).first()
    if not insumo:
        raise HTTPException(status_code=404, detail="El insumo seleccionado no existe.")

    if datos.cantidad_ingresada <= 0:
        raise HTTPException(status_code=400, detail="La cantidad recibida debe ser mayor a 0.")

    if insumo.es_perecedero and not datos.caducidad:
        raise HTTPException(status_code=400, detail="Este insumo es perecedero y requiere fecha de caducidad.")

    cantidad_convertida = convertir_a_unidad_base(
        datos.cantidad_ingresada,
        datos.unidad_compra,
        insumo.unidad_medida
    )

    nuevo_lote = LoteInsumo(
        id_insumo=insumo.id_insumo,
        id_proveedor=datos.id_proveedor,
        cantidad_recibida=cantidad_convertida,
        cantidad_disponible=cantidad_convertida,
        costo_unitario=datos.costo_unitario,
        caducidad=datos.caducidad,
        numero_factura=datos.numero_factura
    )
    db.add(nuevo_lote)

    movimiento = MovimientoInventario(
        id_insumo=insumo.id_insumo,
        id_usuario=datos.id_usuario,
        tipo_movimiento="Entrada",
        cantidad=cantidad_convertida,
        motivo=f"Recepción de lote - Factura: {datos.numero_factura or 'S/N'}"
    )
    db.add(movimiento)

    db.commit()
    db.refresh(nuevo_lote)

    return {
        "mensaje": "Lote registrado correctamente en inventario PEPS",
        "id_lote": nuevo_lote.id_lote,
        "insumo": insumo.nombre,
        "cantidad_guardada": float(nuevo_lote.cantidad_disponible),
        "unidad_base": insumo.unidad_medida
    }


# =========================================================
# 2. MERMAS (05_Mermas)
# =========================================================
@router.get("/mermas")
def listar_mermas(db: Session = Depends(get_db)):
    mermas = db.query(Merma).order_by(Merma.fecha.desc()).limit(30).all()
    resultado = []
    for m in mermas:
        ins = db.query(Insumo).filter(Insumo.id_insumo == m.id_insumo).first()
        resultado.append({
            "id_merma": m.id_merma,
            "id_lote": m.id_lote,
            "insumo": ins.nombre if ins else f"Insumo #{m.id_insumo}",
            "unidad": ins.unidad_medida if ins else "",
            "cantidad": float(m.cantidad),
            "costo_perdida": float(m.costo_perdida),
            "motivo": m.motivo,
            "fecha": m.fecha.strftime("%Y-%m-%d %H:%M") if m.fecha else ""
        })
    return {"mermas": resultado}


@router.post("/mermas")
def registrar_merma(datos: RegistroMermaSchema, db: Session = Depends(get_db)):
    lote = db.query(LoteInsumo).filter(LoteInsumo.id_lote == datos.id_lote).first()
    if not lote:
        raise HTTPException(status_code=404, detail="Lote no encontrado.")

    if datos.cantidad <= 0 or datos.cantidad > float(lote.cantidad_disponible):
        raise HTTPException(status_code=400, detail="Cantidad inválida o mayor al disponible en el lote.")

    costo_perdida = float(lote.costo_unitario) * datos.cantidad
    lote.cantidad_disponible = float(lote.cantidad_disponible) - datos.cantidad

    nueva_merma = Merma(
        id_lote=lote.id_lote,
        id_insumo=lote.id_insumo,
        id_usuario=datos.id_usuario,
        cantidad=datos.cantidad,
        costo_perdida=costo_perdida,
        motivo=datos.motivo
    )
    db.add(nueva_merma)

    movimiento = MovimientoInventario(
        id_insumo=lote.id_insumo,
        id_usuario=datos.id_usuario,
        tipo_movimiento="Merma",
        cantidad=datos.cantidad,
        motivo=datos.motivo
    )
    db.add(movimiento)

    db.commit()
    return {"mensaje": "Merma registrada y descontada del lote.", "costo_perdida": costo_perdida}