from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import func

from database import get_db
from models import Insumo, Producto, Receta, LoteInsumo, DetalleVenta, Bitacora

router = APIRouter(prefix="/api/catalogos", tags=["Catálogos (Insumos y Productos)"])

UNIDADES_BASE_VALIDAS = ("g", "ml", "pza")
UNIDADES_COMPRA_VALIDAS = ("kg", "L", "cja", "paq", "g", "ml", "pza")


class InsumoEntrada(BaseModel):
    nombre: str
    categoria: str
    unidad_medida: str
    unidad_compra: str = "pza"
    factor_conversion: float = Field(gt=0)
    es_perecedero: bool = True
    minimo_reposicion: float = Field(ge=0)
    estado: str = "Activo"
    id_usuario: int = 1


class RenglonRecetaEntrada(BaseModel):
    id_insumo: int
    cantidad_necesaria: float = Field(gt=0)


class ProductoEntrada(BaseModel):
    nombre: str
    categoria: str
    precio_venta: float = Field(gt=0)
    estado: str = "activo"
    receta: List[RenglonRecetaEntrada] = Field(min_length=1)
    id_usuario: int = 1


# =========================================================
# 1. CATÁLOGO MAESTRO DE INSUMOS (RF 2, RF 14, RF 18)
# =========================================================
@router.get("/insumos")
def listar_insumos(incluir_inactivos: bool = True, db: Session = Depends(get_db)):
    consulta = db.query(Insumo).order_by(Insumo.nombre.asc())
    if not incluir_inactivos:
        consulta = consulta.filter(Insumo.estado == "Activo")

    insumos = consulta.all()
    resultado = []
    for i in insumos:
        usado_en_recetas = db.query(Receta).filter(Receta.id_insumo == i.id_insumo).count()
        tiene_lotes = db.query(LoteInsumo).filter(LoteInsumo.id_insumo == i.id_insumo).count()
        resultado.append({
            "id_insumo": i.id_insumo,
            "nombre": i.nombre,
            "categoria": i.categoria,
            "unidad_medida": i.unidad_medida,
            "unidad_compra": i.unidad_compra or i.unidad_medida,
            "factor_conversion": float(i.factor_conversion or 1),
            "es_perecedero": bool(i.es_perecedero),
            "minimo_reposicion": float(i.minimo_reposicion),
            "estado": i.estado or "Activo",
            "en_uso": (usado_en_recetas > 0 or tiene_lotes > 0),
        })
    return {"insumos": resultado}


@router.post("/insumos", status_code=201)
def crear_insumo(datos: InsumoEntrada, db: Session = Depends(get_db)):
    nombre = datos.nombre.strip()
    if not nombre:
        raise HTTPException(status_code=400, detail="El nombre del insumo es obligatorio.")
    if datos.unidad_medida not in UNIDADES_BASE_VALIDAS:
        raise HTTPException(status_code=400, detail="Unidad base no válida. Usa g, ml o pza.")
    if datos.unidad_compra not in UNIDADES_COMPRA_VALIDAS:
        raise HTTPException(status_code=400, detail="Unidad de compra no válida.")
    if datos.factor_conversion <= 0:
        raise HTTPException(status_code=400, detail="El factor de conversión debe ser mayor a cero.")

    duplicado = db.query(Insumo).filter(func.lower(Insumo.nombre) == nombre.lower()).first()
    if duplicado:
        raise HTTPException(status_code=400, detail="Ya existe un insumo registrado con ese nombre.")

    nuevo = Insumo(
        nombre=nombre,
        categoria=datos.categoria.strip(),
        unidad_medida=datos.unidad_medida,
        unidad_compra=datos.unidad_compra,
        factor_conversion=datos.factor_conversion,
        es_perecedero=datos.es_perecedero,
        minimo_reposicion=datos.minimo_reposicion,
        estado="Activo",
    )
    db.add(nuevo)
    db.flush()

    db.add(Bitacora(
        id_usuario=datos.id_usuario,
        accion="INSUMO_CREADO",
        detalle=f"Alta de insumo: {nuevo.nombre} ({nuevo.unidad_compra} -> {nuevo.factor_conversion:g} {nuevo.unidad_medida})",
    ))
    db.commit()
    db.refresh(nuevo)
    return {"mensaje": "Insumo registrado correctamente.", "id_insumo": nuevo.id_insumo}


@router.put("/insumos/{id_insumo}")
def actualizar_insumo(id_insumo: int, datos: InsumoEntrada, db: Session = Depends(get_db)):
    insumo = db.query(Insumo).filter(Insumo.id_insumo == id_insumo).first()
    if not insumo:
        raise HTTPException(status_code=404, detail="Insumo no encontrado.")

    nombre = datos.nombre.strip()
    if not nombre:
        raise HTTPException(status_code=400, detail="El nombre del insumo es obligatorio.")
    if datos.unidad_medida not in UNIDADES_BASE_VALIDAS:
        raise HTTPException(status_code=400, detail="Unidad base no válida.")
    if datos.factor_conversion <= 0:
        raise HTTPException(status_code=400, detail="El factor de conversión debe ser mayor a cero.")

    duplicado = (
        db.query(Insumo)
        .filter(func.lower(Insumo.nombre) == nombre.lower(), Insumo.id_insumo != id_insumo)
        .first()
    )
    if duplicado:
        raise HTTPException(status_code=400, detail="Otro insumo ya tiene ese nombre.")

    insumo.nombre = nombre
    insumo.categoria = datos.categoria.strip()
    insumo.unidad_medida = datos.unidad_medida
    insumo.unidad_compra = datos.unidad_compra
    insumo.factor_conversion = datos.factor_conversion
    insumo.es_perecedero = datos.es_perecedero
    insumo.minimo_reposicion = datos.minimo_reposicion
    insumo.estado = datos.estado

    db.add(Bitacora(
        id_usuario=datos.id_usuario,
        accion="INSUMO_EDITADO",
        detalle=f"Actualización de insumo #{id_insumo}: {insumo.nombre}",
    ))
    db.commit()
    return {"mensaje": "Cambios guardados en el catálogo de insumos."}


@router.delete("/insumos/{id_insumo}")
def eliminar_o_desactivar_insumo(id_insumo: int, id_usuario: int = 1, db: Session = Depends(get_db)):
    insumo = db.query(Insumo).filter(Insumo.id_insumo == id_insumo).first()
    if not insumo:
        raise HTTPException(status_code=404, detail="Insumo no encontrado.")

    en_recetas = db.query(Receta).filter(Receta.id_insumo == id_insumo).count()
    if en_recetas > 0:
        raise HTTPException(
            status_code=400,
            detail="No se puede eliminar porque forma parte de una o más recetas activas.",
        )

    tiene_historial = db.query(LoteInsumo).filter(LoteInsumo.id_insumo == id_insumo).count()
    nombre = insumo.nombre

    if tiene_historial > 0:
        insumo.estado = "Inactivo"
        accion_txt = "INSUMO_DESACTIVADO"
        detalle_txt = f"Insumo desactivado (conservando historial): {nombre}"
        msg = "Insumo desactivado (se conservaron sus registros históricos)."
    else:
        db.delete(insumo)
        accion_txt = "INSUMO_ELIMINADO"
        detalle_txt = f"Insumo eliminado del catálogo: {nombre}"
        msg = "Insumo eliminado permanentemente del catálogo."

    db.add(Bitacora(id_usuario=id_usuario, accion=accion_txt, detalle=detalle_txt))
    db.commit()
    return {"mensaje": msg}


# =========================================================
# 2. PRODUCTOS Y RECETAS (RF 3, RF 14, RF 18)
# =========================================================
@router.get("/productos")
def listar_productos_con_recetas(db: Session = Depends(get_db)):
    productos = db.query(Producto).order_by(Producto.nombre.asc()).all()
    resultado = []

    for p in productos:
        renglones = db.query(Receta).filter(Receta.id_producto == p.id_producto).all()
        receta_det = []
        for r in renglones:
            ins = db.query(Insumo).filter(Insumo.id_insumo == r.id_insumo).first()
            receta_det.append({
                "id_receta": r.id_receta,
                "id_insumo": r.id_insumo,
                "insumo": ins.nombre if ins else f"Insumo #{r.id_insumo}",
                "unidad_medida": ins.unidad_medida if ins else "",
                "cantidad_necesaria": float(r.cantidad_necesaria),
            })

        resultado.append({
            "id_producto": p.id_producto,
            "nombre": p.nombre,
            "categoria": p.categoria,
            "precio_venta": float(p.precio_venta),
            "estado": (p.estado or "activo").lower(),
            "total_insumos": len(receta_det),
            "receta": receta_det,
        })

    return {"productos": resultado}


@router.post("/productos", status_code=201)
def crear_producto(datos: ProductoEntrada, db: Session = Depends(get_db)):
    nombre = datos.nombre.strip()
    if not nombre:
        raise HTTPException(status_code=400, detail="El nombre del producto es obligatorio.")

    insumos_ids = [r.id_insumo for r in datos.receta]
    if len(insumos_ids) != len(set(insumos_ids)):
        raise HTTPException(status_code=400, detail="No repitas el mismo insumo en la receta.")

    try:
        nuevo = Producto(
            nombre=nombre,
            categoria=datos.categoria.strip(),
            precio_venta=datos.precio_venta,
            estado=datos.estado.lower(),
        )
        db.add(nuevo)
        db.flush()

        for r in datos.receta:
            ins = db.query(Insumo).filter(Insumo.id_insumo == r.id_insumo).first()
            if not ins:
                raise HTTPException(status_code=404, detail=f"Insumo #{r.id_insumo} no encontrado.")
            db.add(Receta(
                id_producto=nuevo.id_producto,
                id_insumo=r.id_insumo,
                cantidad_necesaria=r.cantidad_necesaria,
            ))

        db.add(Bitacora(
            id_usuario=datos.id_usuario,
            accion="PRODUCTO_CREADO",
            detalle=f"Alta de producto: {nuevo.nombre} (${float(nuevo.precio_venta):.2f}) con {len(datos.receta)} insumos",
        ))
        db.commit()
        return {"mensaje": "Producto y receta registrados correctamente.", "id_producto": nuevo.id_producto}
    except Exception:
        db.rollback()
        raise


@router.put("/productos/{id_producto}")
def actualizar_producto(id_producto: int, datos: ProductoEntrada, db: Session = Depends(get_db)):
    producto = db.query(Producto).filter(Producto.id_producto == id_producto).first()
    if not producto:
        raise HTTPException(status_code=404, detail="Producto no encontrado.")

    nombre = datos.nombre.strip()
    if not nombre:
        raise HTTPException(status_code=400, detail="El nombre del producto es obligatorio.")

    insumos_ids = [r.id_insumo for r in datos.receta]
    if len(insumos_ids) != len(set(insumos_ids)):
        raise HTTPException(status_code=400, detail="No repitas el mismo insumo en la receta.")

    try:
        # RF 3: Las ventas ya registradas conservan precio_unitario en detalle_venta y movimientos históricos
        producto.nombre = nombre
        producto.categoria = datos.categoria.strip()
        producto.precio_venta = datos.precio_venta
        producto.estado = datos.estado.lower()

        db.query(Receta).filter(Receta.id_producto == id_producto).delete()
        for r in datos.receta:
            ins = db.query(Insumo).filter(Insumo.id_insumo == r.id_insumo).first()
            if not ins:
                raise HTTPException(status_code=404, detail=f"Insumo #{r.id_insumo} no encontrado.")
            db.add(Receta(
                id_producto=id_producto,
                id_insumo=r.id_insumo,
                cantidad_necesaria=r.cantidad_necesaria,
            ))

        db.add(Bitacora(
            id_usuario=datos.id_usuario,
            accion="PRODUCTO_EDITADO",
            detalle=f"Actualización de producto/receta #{id_producto}: {producto.nombre}",
        ))
        db.commit()
        return {"mensaje": "Producto y receta actualizados (aplica a ventas futuras)."}
    except Exception:
        db.rollback()
        raise