from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import func

from database import get_db
from models import (
    AlertaInventario, DetalleVenta, Insumo, LoteInsumo, Merma, MovimientoInventario,
    Producto, Receta, Usuario,
)
from services.bitacora import registrar_bitacora
from services.sesion import requiere_admin

router = APIRouter(
    prefix="/api/catalogos",
    tags=["Catálogos (Insumos y Productos)"],
    dependencies=[Depends(requiere_admin)],
)

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
    # El estado ya no se cambia aquí: PATCH /insumos/{id}/estado


class RenglonRecetaEntrada(BaseModel):
    id_insumo: int
    cantidad_necesaria: float = Field(gt=0)


class ProductoEntrada(BaseModel):
    nombre: str
    categoria: str
    precio_venta: float = Field(gt=0)
    receta: List[RenglonRecetaEntrada] = Field(min_length=1)
    # El estado ya no se cambia aquí: PATCH /productos/{id}/estado


class EstadoEntrada(BaseModel):
    estado: str = Field(min_length=1)   # "Activo" | "Inactivo" (sin importar mayúsculas)


def _estado_pedido(datos: EstadoEntrada) -> bool:
    """True = activar, False = desactivar; 400 si no es Activo/Inactivo."""
    valor = datos.estado.strip().lower()
    if valor not in ("activo", "inactivo"):
        raise HTTPException(status_code=400, detail="El estado debe ser Activo o Inactivo.")
    return valor == "activo"


def _lista(nombres) -> str:
    return ", ".join(nombres)


def _plural(n: int, singular: str, plural: str) -> str:
    return f"{n} {singular if n == 1 else plural}"


# =========================================================
# 1. CATÁLOGO MAESTRO DE INSUMOS (RF 2, RF 14, RF 18)
#    Editar (PUT) no toca el estado. Desactivar/Activar: PATCH .../estado.
#    Eliminar (DELETE) solo si el insumo no tiene historial; si lo tiene -> 409.
#    Un insumo Inactivo no aparece en Recepción ni al armar recetas, pero sí
#    en reportes, lotes e historial.
# =========================================================
def es_activo(estado: Optional[str]) -> bool:
    return (estado or "Activo").strip().lower() == "activo"


def historial_insumo(db: Session, id_insumo: int) -> dict:
    """Registros que impiden borrar el insumo (recetas, lotes y movimientos)."""
    return {
        "recetas": db.query(Receta).filter(Receta.id_insumo == id_insumo).count(),
        "lotes": db.query(LoteInsumo).filter(LoteInsumo.id_insumo == id_insumo).count(),
        "movimientos": db.query(MovimientoInventario).filter(MovimientoInventario.id_insumo == id_insumo).count(),
        "mermas": db.query(Merma).filter(Merma.id_insumo == id_insumo).count(),
        "alertas": db.query(AlertaInventario).filter(AlertaInventario.id_insumo == id_insumo).count(),
    }


def describir_historial(h: dict) -> str:
    partes = []
    if h["recetas"]:
        partes.append(_plural(h["recetas"], "receta", "recetas"))
    if h["lotes"]:
        partes.append(_plural(h["lotes"], "lote", "lotes"))
    movimientos = h["movimientos"] + h["mermas"] + h["alertas"]
    if movimientos:
        partes.append(_plural(movimientos, "movimiento", "movimientos"))
    return ", ".join(partes)


def productos_activos_con_insumo(db: Session, id_insumo: int) -> List[str]:
    filas = (
        db.query(Producto.nombre, Producto.estado)
        .join(Receta, Receta.id_producto == Producto.id_producto)
        .filter(Receta.id_insumo == id_insumo)
        .order_by(Producto.nombre.asc())
        .all()
    )
    return [nombre for nombre, estado in filas if es_activo(estado)]


@router.get("/insumos")
def listar_insumos(incluir_inactivos: bool = True, db: Session = Depends(get_db)):
    consulta = db.query(Insumo).order_by(Insumo.nombre.asc())
    if not incluir_inactivos:
        consulta = consulta.filter(Insumo.estado == "Activo")

    insumos = consulta.all()
    resultado = []
    for i in insumos:
        historial = historial_insumo(db, i.id_insumo)
        con_historial = any(historial.values())
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
            "en_uso": con_historial,
            "puede_eliminar": not con_historial,
            "motivo_no_eliminar": (
                f"Tiene historial ({describir_historial(historial)}): usa Desactivar" if con_historial else ""
            ),
            "usado_en_productos_activos": productos_activos_con_insumo(db, i.id_insumo),
        })
    return {"insumos": resultado}


@router.post("/insumos", status_code=201)
def crear_insumo(datos: InsumoEntrada, db: Session = Depends(get_db), admin: Usuario = Depends(requiere_admin)):
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

    registrar_bitacora(
        db, admin.id_usuario, "INSUMO_CREADO",
        f"Alta de insumo: {nuevo.nombre} ({nuevo.unidad_compra} -> {nuevo.factor_conversion:g} {nuevo.unidad_medida})",
    )
    db.commit()
    db.refresh(nuevo)
    return {"mensaje": "Insumo registrado correctamente.", "id_insumo": nuevo.id_insumo}


@router.put("/insumos/{id_insumo}")
def actualizar_insumo(id_insumo: int, datos: InsumoEntrada, db: Session = Depends(get_db), admin: Usuario = Depends(requiere_admin)):
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
    # El estado NO se cambia al editar (se usa PATCH /insumos/{id}/estado)

    registrar_bitacora(db, admin.id_usuario, "INSUMO_EDITADO", f"Actualización de insumo #{id_insumo}: {insumo.nombre}")
    db.commit()
    return {"mensaje": "Cambios guardados en el catálogo de insumos."}


@router.patch("/insumos/{id_insumo}/estado")
def cambiar_estado_insumo(id_insumo: int, datos: EstadoEntrada, db: Session = Depends(get_db), admin: Usuario = Depends(requiere_admin)):
    insumo = db.query(Insumo).filter(Insumo.id_insumo == id_insumo).first()
    if not insumo:
        raise HTTPException(status_code=404, detail="Insumo no encontrado.")

    activar = _estado_pedido(datos)
    if activar == es_activo(insumo.estado):
        estado_txt = "activo" if activar else "inactivo"
        return {"mensaje": f"«{insumo.nombre}» ya estaba {estado_txt}.", "estado": insumo.estado}

    if not activar:
        productos = productos_activos_con_insumo(db, id_insumo)
        if productos:
            raise HTTPException(
                status_code=409,
                detail=f"No se puede desactivar «{insumo.nombre}». Se usa en: {_lista(productos)}. "
                       "Desactiva o cambia esas recetas primero.",
            )

    insumo.estado = "Activo" if activar else "Inactivo"
    if activar:
        registrar_bitacora(db, admin.id_usuario, "INSUMO_ACTIVADO", f"Insumo activado: {insumo.nombre}")
        mensaje = f"«{insumo.nombre}» está activo otra vez: ya aparece en Recepción y en las recetas."
    else:
        registrar_bitacora(db, admin.id_usuario, "INSUMO_DESACTIVADO", f"Insumo desactivado (conserva su historial): {insumo.nombre}")
        mensaje = f"«{insumo.nombre}» quedó inactivo: ya no aparece en Recepción ni en recetas nuevas; su historial se conserva."
    db.commit()
    return {"mensaje": mensaje, "estado": insumo.estado}


@router.delete("/insumos/{id_insumo}")
def eliminar_insumo(id_insumo: int, db: Session = Depends(get_db), admin: Usuario = Depends(requiere_admin)):
    insumo = db.query(Insumo).filter(Insumo.id_insumo == id_insumo).first()
    if not insumo:
        raise HTTPException(status_code=404, detail="Insumo no encontrado.")

    historial = historial_insumo(db, id_insumo)
    if any(historial.values()):
        raise HTTPException(
            status_code=409,
            detail=f"No se puede eliminar «{insumo.nombre}» porque tiene historial ({describir_historial(historial)}). "
                   "Usa Desactivar para ocultarlo sin perder sus registros.",
        )

    nombre = insumo.nombre
    db.delete(insumo)
    registrar_bitacora(db, admin.id_usuario, "INSUMO_ELIMINADO", f"Insumo eliminado del catálogo: {nombre}")
    db.commit()
    return {"mensaje": f"«{nombre}» se eliminó del catálogo."}


# =========================================================
# 2. PRODUCTOS Y RECETAS (RF 3, RF 14, RF 18)
#    Mismo patrón que insumos: PUT no toca el estado, PATCH .../estado activa o
#    desactiva, DELETE solo si el producto nunca se vendió (si no -> 409).
#    Un producto activo no puede llevar insumos inactivos en su receta.
# =========================================================
def _ventas_producto(db: Session, id_producto: int) -> int:
    return db.query(DetalleVenta).filter(DetalleVenta.id_producto == id_producto).count()


def _validar_receta(db: Session, receta: List[RenglonRecetaEntrada], permitidos_inactivos: set) -> None:
    """Insumos existentes y sin repetir. Un insumo inactivo solo se acepta si ya estaba
    en la receta (permitidos_inactivos) y el producto está inactivo."""
    insumos_ids = [r.id_insumo for r in receta]
    if len(insumos_ids) != len(set(insumos_ids)):
        raise HTTPException(status_code=400, detail="No repitas el mismo insumo en la receta.")
    inactivos = []
    for r in receta:
        ins = db.query(Insumo).filter(Insumo.id_insumo == r.id_insumo).first()
        if not ins:
            raise HTTPException(status_code=404, detail=f"Insumo #{r.id_insumo} no encontrado.")
        if not es_activo(ins.estado) and r.id_insumo not in permitidos_inactivos:
            inactivos.append(ins.nombre)
    if inactivos:
        raise HTTPException(
            status_code=409,
            detail=f"Estos insumos están inactivos y no se pueden usar en la receta: {_lista(inactivos)}. "
                   "Actívalos en Insumos o elige otros.",
        )


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
                "insumo_activo": bool(ins) and es_activo(ins.estado),
                "cantidad_necesaria": float(r.cantidad_necesaria),
            })

        ventas = _ventas_producto(db, p.id_producto)
        resultado.append({
            "id_producto": p.id_producto,
            "nombre": p.nombre,
            "categoria": p.categoria,
            "precio_venta": float(p.precio_venta),
            "estado": (p.estado or "activo").lower(),
            "total_insumos": len(receta_det),
            "receta": receta_det,
            "puede_eliminar": ventas == 0,
            "motivo_no_eliminar": (
                f"Tiene historial ({_plural(ventas, 'venta', 'ventas')}): usa Desactivar" if ventas else ""
            ),
        })

    return {"productos": resultado}


@router.post("/productos", status_code=201)
def crear_producto(datos: ProductoEntrada, db: Session = Depends(get_db), admin: Usuario = Depends(requiere_admin)):
    nombre = datos.nombre.strip()
    if not nombre:
        raise HTTPException(status_code=400, detail="El nombre del producto es obligatorio.")
    _validar_receta(db, datos.receta, permitidos_inactivos=set())

    try:
        nuevo = Producto(
            nombre=nombre,
            categoria=datos.categoria.strip(),
            precio_venta=datos.precio_venta,
            estado="activo",
        )
        db.add(nuevo)
        db.flush()

        for r in datos.receta:
            db.add(Receta(
                id_producto=nuevo.id_producto,
                id_insumo=r.id_insumo,
                cantidad_necesaria=r.cantidad_necesaria,
            ))

        registrar_bitacora(
            db, admin.id_usuario, "PRODUCTO_CREADO",
            f"Alta de producto: {nuevo.nombre} (${float(nuevo.precio_venta):.2f}) con {len(datos.receta)} insumos",
        )
        db.commit()
        return {"mensaje": "Producto y receta registrados correctamente.", "id_producto": nuevo.id_producto}
    except Exception:
        db.rollback()
        raise


@router.put("/productos/{id_producto}")
def actualizar_producto(id_producto: int, datos: ProductoEntrada, db: Session = Depends(get_db), admin: Usuario = Depends(requiere_admin)):
    producto = db.query(Producto).filter(Producto.id_producto == id_producto).first()
    if not producto:
        raise HTTPException(status_code=404, detail="Producto no encontrado.")

    nombre = datos.nombre.strip()
    if not nombre:
        raise HTTPException(status_code=400, detail="El nombre del producto es obligatorio.")

    # Un producto inactivo puede conservar un insumo inactivo que ya tenía; uno activo, no.
    actuales = {r.id_insumo for r in db.query(Receta).filter(Receta.id_producto == id_producto).all()}
    _validar_receta(db, datos.receta, permitidos_inactivos=set() if es_activo(producto.estado) else actuales)

    try:
        # RF 3: Las ventas ya registradas conservan precio_unitario en detalle_venta y movimientos históricos
        producto.nombre = nombre
        producto.categoria = datos.categoria.strip()
        producto.precio_venta = datos.precio_venta
        # El estado NO se cambia al editar (se usa PATCH /productos/{id}/estado)

        db.query(Receta).filter(Receta.id_producto == id_producto).delete()
        for r in datos.receta:
            db.add(Receta(
                id_producto=id_producto,
                id_insumo=r.id_insumo,
                cantidad_necesaria=r.cantidad_necesaria,
            ))

        registrar_bitacora(db, admin.id_usuario, "PRODUCTO_EDITADO", f"Actualización de producto/receta #{id_producto}: {producto.nombre}")
        db.commit()
        return {"mensaje": "Producto y receta actualizados (aplica a ventas futuras)."}
    except Exception:
        db.rollback()
        raise


@router.patch("/productos/{id_producto}/estado")
def cambiar_estado_producto(id_producto: int, datos: EstadoEntrada, db: Session = Depends(get_db), admin: Usuario = Depends(requiere_admin)):
    producto = db.query(Producto).filter(Producto.id_producto == id_producto).first()
    if not producto:
        raise HTTPException(status_code=404, detail="Producto no encontrado.")

    activar = _estado_pedido(datos)
    if activar == es_activo(producto.estado):
        estado_txt = "activo" if activar else "inactivo"
        return {"mensaje": f"«{producto.nombre}» ya estaba {estado_txt}.", "estado": (producto.estado or "activo").lower()}

    if activar:
        inactivos = [
            ins.nombre
            for ins in db.query(Insumo).join(Receta, Receta.id_insumo == Insumo.id_insumo)
                         .filter(Receta.id_producto == id_producto).order_by(Insumo.nombre.asc()).all()
            if not es_activo(ins.estado)
        ]
        if inactivos:
            raise HTTPException(
                status_code=409,
                detail=f"No se puede activar «{producto.nombre}». Su receta usa insumos inactivos: {_lista(inactivos)}. "
                       "Actívalos en Insumos o cambia la receta primero.",
            )

    producto.estado = "activo" if activar else "inactivo"
    if activar:
        registrar_bitacora(db, admin.id_usuario, "PRODUCTO_ACTIVADO", f"Producto activado: {producto.nombre}")
        mensaje = f"«{producto.nombre}» está activo otra vez: ya aparece en Caja."
    else:
        registrar_bitacora(db, admin.id_usuario, "PRODUCTO_DESACTIVADO", f"Producto desactivado (conserva sus ventas): {producto.nombre}")
        mensaje = f"«{producto.nombre}» quedó inactivo: ya no aparece en Caja; sus ventas se conservan."
    db.commit()
    return {"mensaje": mensaje, "estado": producto.estado}


@router.delete("/productos/{id_producto}")
def eliminar_producto(id_producto: int, db: Session = Depends(get_db), admin: Usuario = Depends(requiere_admin)):
    producto = db.query(Producto).filter(Producto.id_producto == id_producto).first()
    if not producto:
        raise HTTPException(status_code=404, detail="Producto no encontrado.")

    ventas = _ventas_producto(db, id_producto)
    if ventas:
        raise HTTPException(
            status_code=409,
            detail=f"No se puede eliminar «{producto.nombre}» porque tiene historial ({_plural(ventas, 'venta', 'ventas')}). "
                   "Usa Desactivar para quitarlo de Caja sin perder sus ventas.",
        )

    nombre = producto.nombre
    db.query(Receta).filter(Receta.id_producto == id_producto).delete()
    db.delete(producto)
    registrar_bitacora(db, admin.id_usuario, "PRODUCTO_ELIMINADO", f"Producto eliminado del catálogo: {nombre}")
    db.commit()
    return {"mensaje": f"«{nombre}» se eliminó del catálogo."}
