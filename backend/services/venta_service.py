"""
services/venta_service.py  —  Lógica de Caja (Francisco)
=========================================================
Capa de SERVICIOS: aquí vive la regla de negocio de la venta.
No sabe nada de HTTP; las rutas (routes/ventas.py) traducen sus
excepciones a códigos de respuesta.

Qué hace registrar_venta():
  1. Valida la comanda y la forma de pago.
  2. Calcula el total con los PRECIOS DE LA BASE (no confía en el cliente).
  3. Explosiona la receta de cada producto vendido (en unidad base g / ml / pza).
  4. Valida que haya stock VIGENTE suficiente de cada insumo.
  5. Descuenta por PEPS: del lote más antiguo al más nuevo.
  6. Guarda Venta + DetalleVenta + MovimientoInventario (para que Nico pueda
     restituir el stock al cancelar).
  Todo dentro de UNA transacción ACID: si algo falla, no se altera nada.

------------------------------------------------------------------
SUPUESTOS SOBRE models.py (Andrés)  -> AJUSTAR si los nombres difieren
------------------------------------------------------------------
Producto(id_producto, nombre, categoria[str], precio, activo[bool])
Insumo(id_insumo, nombre, unidad_base)
Receta(id_producto, id_insumo, cantidad)           # cantidad en unidad base, 1 fila por ingrediente
LoteInsumo(id_lote, id_insumo, cantidad_actual, fecha_recepcion, fecha_caducidad[nullable])
Venta(id_venta, id_usuario, fecha, total, forma_pago, monto_recibido[nullable], cambio, estado)
DetalleVenta(id_venta, id_producto, cantidad, precio_unitario, subtotal)
MovimientoInventario(id_insumo, id_lote, id_venta, tipo, cantidad, fecha)
"""

from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

# === ADAPTAR AQUÍ: nombres de las clases de models.py ===
from models import (
    DetalleVenta,
    Insumo,
    LoteInsumo,
    MovimientoInventario,
    Producto,
    Receta,
    Venta,
)

# Valores que manda el frontend (caja.js)
FORMA_EFECTIVO = "Efectivo"
FORMA_TARJETA = "Tarjeta externa"
ESTADO_COMPLETADA = "Completada"
TIPO_SALIDA_VENTA = "SALIDA_VENTA"

MENSAJE_STOCK = "Inventario insuficiente. No se realizó el cobro."


# ---------------------------------------------------------------
# Excepciones de negocio (las rutas las convierten a HTTP)
# ---------------------------------------------------------------
class ErrorVenta(Exception):
    """Base de los errores de la venta."""


class DatosInvalidos(ErrorVenta):
    """Comanda vacía, pago insuficiente, producto inexistente, etc."""


class StockInsuficiente(ErrorVenta):
    """Falta algún insumo. 'faltantes' lista qué insumos y cuánto."""

    def __init__(self, faltantes):
        super().__init__(MENSAJE_STOCK)
        self.faltantes = faltantes


# ---------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------
def _dec(valor) -> Decimal:
    return valor if isinstance(valor, Decimal) else Decimal(str(valor))


def _dinero(valor) -> Decimal:
    return _dec(valor).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _normalizar_forma_pago(texto) -> str:
    t = (texto or "").strip().lower()
    if t == "efectivo":
        return FORMA_EFECTIVO
    if t in ("tarjeta externa", "tarjeta"):
        return FORMA_TARJETA
    raise DatosInvalidos("Forma de pago no válida. Use Efectivo o Tarjeta externa.")


def _lote_vigente(hoy: date):
    """Un lote sirve para vender si no ha caducado (los lotes caducados no se usan)."""
    return or_(LoteInsumo.fecha_caducidad.is_(None), LoteInsumo.fecha_caducidad >= hoy)


def _stock_vigente_por_insumo(db: Session, hoy: date) -> dict:
    filas = db.execute(
        select(LoteInsumo.id_insumo, func.coalesce(func.sum(LoteInsumo.cantidad_actual), 0))
        .where(LoteInsumo.cantidad_actual > 0, _lote_vigente(hoy))
        .group_by(LoteInsumo.id_insumo)
    ).all()
    return {id_insumo: _dec(cantidad) for id_insumo, cantidad in filas}


# ---------------------------------------------------------------
# Catálogo para la pantalla de Caja
# ---------------------------------------------------------------
def listar_productos_disponibles(db: Session) -> list:
    """
    Devuelve los productos activos con la bandera 'disponible'.
    Un producto está disponible si tiene receta y alcanza el stock vigente
    de TODOS sus insumos para preparar al menos una unidad (RF 7.1).
    """
    hoy = date.today()
    productos = db.scalars(select(Producto).where(Producto.activo.is_(True)).order_by(Producto.nombre)).all()

    recetas = defaultdict(list)
    for id_producto, id_insumo, cantidad in db.execute(
        select(Receta.id_producto, Receta.id_insumo, Receta.cantidad)
    ).all():
        recetas[id_producto].append((id_insumo, _dec(cantidad)))

    stock = _stock_vigente_por_insumo(db, hoy)

    resultado = []
    for p in productos:
        ingredientes = recetas.get(p.id_producto)
        disponible = bool(ingredientes) and all(
            stock.get(id_insumo, Decimal("0")) >= cantidad for id_insumo, cantidad in ingredientes
        )
        resultado.append({
            "id_producto": p.id_producto,
            "nombre": p.nombre,
            "categoria": p.categoria,
            "precio": float(p.precio),
            "disponible": disponible,
        })
    return resultado


# ---------------------------------------------------------------
# Venta (transacción ACID + PEPS)
# ---------------------------------------------------------------
def registrar_venta(db: Session, id_usuario: int, forma_pago: str, monto_recibido, items: list) -> dict:
    """
    items: [{"id_producto": 1, "cantidad": 2}, ...]
    Devuelve un dict con el resumen de la venta. Lanza DatosInvalidos o StockInsuficiente.
    """
    forma = _normalizar_forma_pago(forma_pago)

    # Agrupar renglones repetidos del mismo producto
    pedido = defaultdict(int)
    for item in items or []:
        cantidad = int(item["cantidad"])
        if cantidad <= 0:
            raise DatosInvalidos("Las cantidades deben ser mayores a cero.")
        pedido[int(item["id_producto"])] += cantidad
    if not pedido:
        raise DatosInvalidos("La comanda está vacía.")

    hoy = date.today()

    # IMPORTANTE: no ejecutar consultas con 'db' ANTES de este bloque; db.begin()
    # falla si la sesión ya inició una transacción.
    # Si ocurre cualquier excepción dentro del bloque, se hace ROLLBACK automático
    # y el inventario queda intacto.
    with db.begin():
        # --- 1. Productos y total (precios de la base de datos) ---
        productos = {
            p.id_producto: p
            for p in db.scalars(select(Producto).where(Producto.id_producto.in_(list(pedido))))
        }
        for id_producto in pedido:
            producto = productos.get(id_producto)
            if producto is None or not producto.activo:
                raise DatosInvalidos(f"El producto {id_producto} no existe o no está disponible.")

        total = _dinero(sum(_dec(productos[i].precio) * c for i, c in pedido.items()))

        # --- 2. Pago ---
        if forma == FORMA_EFECTIVO:
            if monto_recibido is None or _dinero(monto_recibido) < total:
                raise DatosInvalidos("El monto recibido es menor al total a cobrar.")
            monto = _dinero(monto_recibido)
            cambio = monto - total
        else:
            monto = None            # con tarjeta no se captura el monto recibido
            cambio = Decimal("0.00")

        # --- 3. Explosión de recetas: insumo -> cantidad total necesaria ---
        recetas = db.scalars(select(Receta).where(Receta.id_producto.in_(list(pedido)))).all()
        con_receta = {r.id_producto for r in recetas}
        sin_receta = [productos[i].nombre for i in pedido if i not in con_receta]
        if sin_receta:
            raise DatosInvalidos("Productos sin receta registrada: " + ", ".join(sin_receta) + ".")

        requerido = defaultdict(Decimal)
        for r in recetas:
            requerido[r.id_insumo] += _dec(r.cantidad) * pedido[r.id_producto]

        # --- 4. PEPS: armar el plan de descuento (lote más antiguo primero) ---
        # Se ordena por id_insumo para bloquear filas siempre en el mismo orden
        # (evita bloqueos cruzados entre dos ventas simultáneas).
        plan = []            # [(lote, cantidad_a_tomar, id_insumo)]
        faltantes = []
        for id_insumo in sorted(requerido):
            necesario = requerido[id_insumo]
            restante = necesario
            lotes = db.scalars(
                select(LoteInsumo)
                .where(LoteInsumo.id_insumo == id_insumo, LoteInsumo.cantidad_actual > 0, _lote_vigente(hoy))
                .order_by(LoteInsumo.fecha_recepcion.asc(), LoteInsumo.id_lote.asc())
                .with_for_update()
            ).all()
            for lote in lotes:
                if restante <= 0:
                    break
                tomar = min(_dec(lote.cantidad_actual), restante)
                plan.append((lote, tomar, id_insumo))
                restante -= tomar
            if restante > 0:
                insumo = db.get(Insumo, id_insumo)
                faltantes.append({
                    "insumo": insumo.nombre if insumo else str(id_insumo),
                    "unidad": getattr(insumo, "unidad_base", None),
                    "necesario": float(necesario),
                    "disponible": float(necesario - restante),
                })
        if faltantes:
            raise StockInsuficiente(faltantes)       # -> rollback, nada se descontó

        # --- 5. Guardar la venta y aplicar el descuento ---
        ahora = datetime.now()
        venta = Venta(
            id_usuario=id_usuario,
            fecha=ahora,
            total=total,
            forma_pago=forma,
            monto_recibido=monto,
            cambio=cambio,
            estado=ESTADO_COMPLETADA,
        )
        db.add(venta)
        db.flush()           # obtiene id_venta

        detalles = []
        for id_producto, cantidad in pedido.items():
            producto = productos[id_producto]
            precio = _dinero(producto.precio)
            subtotal = _dinero(precio * cantidad)
            db.add(DetalleVenta(
                id_venta=venta.id_venta,
                id_producto=id_producto,
                cantidad=cantidad,
                precio_unitario=precio,
                subtotal=subtotal,
            ))
            detalles.append({
                "id_producto": id_producto,
                "nombre": producto.nombre,
                "cantidad": cantidad,
                "precio_unitario": float(precio),
                "subtotal": float(subtotal),
            })

        for lote, tomar, id_insumo in plan:
            lote.cantidad_actual = _dec(lote.cantidad_actual) - tomar
            db.add(MovimientoInventario(
                id_insumo=id_insumo,
                id_lote=lote.id_lote,
                id_venta=venta.id_venta,
                tipo=TIPO_SALIDA_VENTA,
                cantidad=tomar,
                fecha=ahora,
            ))

        resultado = {
            "id_venta": venta.id_venta,
            "fecha": ahora.isoformat(timespec="seconds"),
            "forma_pago": forma,
            "total": float(total),
            "monto_recibido": float(monto) if monto is not None else None,
            "cambio": float(cambio),
            "detalles": detalles,
        }
    # Al salir del 'with' se hace COMMIT
    return resultado
