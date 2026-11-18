from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from models import (
    DetalleVenta,
    Insumo,
    LoteInsumo,
    MovimientoInventario,
    Producto,
    Receta,
    Venta,
)

FORMA_EFECTIVO = "Efectivo"
FORMA_TARJETA = "Tarjeta externa"
ESTADO_COMPLETADA = "completada"
TIPO_SALIDA_VENTA = "SALIDA_VENTA"

MENSAJE_STOCK = "Inventario insuficiente. No se realizó el cobro."


class ErrorVenta(Exception):
    """Base de los errores de la venta."""


class DatosInvalidos(ErrorVenta):
    """Comanda vacía, pago insuficiente, producto inexistente, etc."""


class StockInsuficiente(ErrorVenta):
    """Falta algún insumo. 'faltantes' lista qué insumos y cuánto."""

    def __init__(self, faltantes):
        super().__init__(MENSAJE_STOCK)
        self.faltantes = faltantes


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
    return or_(LoteInsumo.caducidad.is_(None), LoteInsumo.caducidad >= hoy)


def _stock_vigente_por_insumo(db: Session, hoy: date) -> dict:
    filas = db.execute(
        select(LoteInsumo.id_insumo, func.coalesce(func.sum(LoteInsumo.cantidad_disponible), 0))
        .where(LoteInsumo.cantidad_disponible > 0, _lote_vigente(hoy))
        .group_by(LoteInsumo.id_insumo)
    ).all()
    return {id_insumo: _dec(cantidad) for id_insumo, cantidad in filas}


def listar_productos_disponibles(db: Session) -> list:
    hoy = date.today()
    productos = db.scalars(
        select(Producto).where(func.lower(Producto.estado) == "activo").order_by(Producto.nombre)
    ).all()

    recetas = defaultdict(list)
    for id_producto, id_insumo, cantidad_necesaria in db.execute(
        select(Receta.id_producto, Receta.id_insumo, Receta.cantidad_necesaria)
    ).all():
        recetas[id_producto].append((id_insumo, _dec(cantidad_necesaria)))

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
            "precio": float(p.precio_venta),
            "disponible": disponible,
        })
    return resultado


def registrar_venta(db: Session, id_usuario: int, forma_pago: str, monto_recibido, items: list) -> dict:
    forma = _normalizar_forma_pago(forma_pago)

    pedido = defaultdict(int)
    for item in items or []:
        cantidad = int(item["cantidad"])
        if cantidad <= 0:
            raise DatosInvalidos("Las cantidades deben ser mayores a cero.")
        pedido[int(item["id_producto"])] += cantidad
    if not pedido:
        raise DatosInvalidos("La comanda está vacía.")

    hoy = date.today()

    try:
        # 1. Productos y total desde BD
        productos = {
            p.id_producto: p
            for p in db.scalars(select(Producto).where(Producto.id_producto.in_(list(pedido))))
        }
        for id_producto in pedido:
            producto = productos.get(id_producto)
            if producto is None or (producto.estado or "").lower() != "activo":
                raise DatosInvalidos(f"El producto {id_producto} no existe o no está disponible.")

        total = _dinero(sum(_dec(productos[i].precio_venta) * c for i, c in pedido.items()))

        # 2. Validación de pago
        if forma == FORMA_EFECTIVO:
            if monto_recibido is None or _dinero(monto_recibido) < total:
                raise DatosInvalidos("El monto recibido es menor al total a cobrar.")
            monto = _dinero(monto_recibido)
            cambio = monto - total
        else:
            monto = total
            cambio = Decimal("0.00")

        # 3. Explosión de recetas
        recetas = db.scalars(select(Receta).where(Receta.id_producto.in_(list(pedido)))).all()
        con_receta = {r.id_producto for r in recetas}
        sin_receta = [productos[i].nombre for i in pedido if i not in con_receta]
        if sin_receta:
            raise DatosInvalidos("Productos sin receta registrada: " + ", ".join(sin_receta) + ".")

        requerido = defaultdict(Decimal)
        for r in recetas:
            requerido[r.id_insumo] += _dec(r.cantidad_necesaria) * pedido[r.id_producto]

        # 4. Plan de descuento PEPS (caducidad más próxima y entrada más antigua primero)
        plan = []
        faltantes = []
        for id_insumo in sorted(requerido):
            necesario = requerido[id_insumo]
            restante = necesario
            lotes = db.scalars(
                select(LoteInsumo)
                .where(
                    LoteInsumo.id_insumo == id_insumo,
                    LoteInsumo.cantidad_disponible > 0,
                    _lote_vigente(hoy),
                )
                .order_by(
                    LoteInsumo.caducidad.is_(None).asc(),
                    LoteInsumo.caducidad.asc(),
                    LoteInsumo.fecha_entrada.asc(),
                    LoteInsumo.id_lote.asc(),
                )
                .with_for_update()
            ).all()

            for lote in lotes:
                if restante <= 0:
                    break
                tomar = min(_dec(lote.cantidad_disponible), restante)
                plan.append((lote, tomar, id_insumo))
                restante -= tomar

            if restante > 0:
                insumo = db.get(Insumo, id_insumo)
                faltantes.append({
                    "insumo": insumo.nombre if insumo else str(id_insumo),
                    "unidad": getattr(insumo, "unidad_medida", None),
                    "necesario": float(necesario),
                    "disponible": float(necesario - restante),
                })

        if faltantes:
            raise StockInsuficiente(faltantes)

        # 5. Guardar Venta, Detalles y Movimientos ACID
        ahora = datetime.now()
        venta = Venta(
            id_usuario=id_usuario,
            total=total,
            forma_pago=forma,
            monto_recibido=monto,
            cambio=cambio,
            estado=ESTADO_COMPLETADA,
            fecha_emision_ticket=ahora,
        )
        db.add(venta)
        db.flush()

        detalles = []
        for id_producto, cantidad in pedido.items():
            producto = productos[id_producto]
            precio = _dinero(producto.precio_venta)
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
            lote.cantidad_disponible = _dec(lote.cantidad_disponible) - tomar
            db.add(MovimientoInventario(
                id_insumo=id_insumo,
                id_usuario=id_usuario,
                tipo_movimiento=TIPO_SALIDA_VENTA,
                cantidad=tomar,
                motivo=f"Venta #{venta.id_venta} (Lote #{lote.id_lote})",
                fecha_movimiento=ahora,
            ))

        db.commit()
        db.refresh(venta)

        return {
            "id_venta": venta.id_venta,
            "fecha": ahora.isoformat(timespec="seconds"),
            "forma_pago": forma,
            "total": float(total),
            "monto_recibido": float(monto),
            "cambio": float(cambio),
            "detalles": detalles,
        }

    except Exception:
        db.rollback()
        raise