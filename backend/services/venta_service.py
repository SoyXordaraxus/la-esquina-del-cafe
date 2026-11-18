import re
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
    Merma,
    Receta,
    Usuario,
    Venta,
)

FORMA_EFECTIVO = "Efectivo"
FORMA_TARJETA = "Tarjeta externa"
ESTADO_COMPLETADA = "completada"
ESTADO_CANCELADA = "cancelada"
TIPO_SALIDA_VENTA = "SALIDA_VENTA"
TIPO_ENTRADA_CANCELACION = "ENTRADA_CANCELACION"
TIPO_CANCELACION_A_MERMA = "CANCELACION_A_MERMA"
ROL_ADMIN = "Administrador"

# RF 5: estado del lote. models.py todavía NO tiene la columna lote_insumo.estado;
# este código solo se activa cuando el dueño de models.py la agregue.
LOTE_AGOTADO = "Agotado"
LOTE_DISPONIBLE = "Disponible"

# RF 18: la cancelación no usa texto libre, solo motivos de catálogo.
MOTIVOS_CANCELACION = (
    "Error de captura",
    "Devolución del cliente",
    "Producto en mal estado",
)

# El motivo que escribe registrar_venta() en cada movimiento: "Venta #12 (Lote #3)".
# Sirve para saber de qué lote salió cada insumo (RF 3 historial y RF 9 restitución).
_PATRON_MOV_VENTA = re.compile(r"^Venta #(\d+) \(Lote #(\d+)\)$")

MENSAJE_STOCK = "Inventario insuficiente. No se realizó el cobro."


class ErrorVenta(Exception):
    """Base de los errores de la venta."""


class DatosInvalidos(ErrorVenta):
    """Comanda vacía, pago insuficiente, producto inexistente, etc."""


class NoAutorizado(ErrorVenta):
    """La acción requiere rol Administrador."""


class NoEncontrado(ErrorVenta):
    """La venta no existe."""


class VentaYaCancelada(ErrorVenta):
    """La venta ya estaba cancelada."""


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


def _actualizar_estado_lote(lote) -> None:
    """RF 5: marca el lote como Agotado al llegar a 0 (si la columna existe)."""
    if not hasattr(LoteInsumo, "estado"):
        return
    if _dec(lote.cantidad_disponible) <= 0:
        lote.estado = LOTE_AGOTADO
    elif (lote.estado or "") == LOTE_AGOTADO:
        lote.estado = LOTE_DISPONIBLE


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
            _actualizar_estado_lote(lote)
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

# =====================================================================
# RF 3 — Historial: la venta conserva precio e insumos usados
# =====================================================================
def _movimientos_de_venta(db: Session, id_venta: int) -> list:
    """Salidas de inventario que generó la venta, con el lote de origen."""
    movs = db.scalars(
        select(MovimientoInventario)
        .where(
            MovimientoInventario.tipo_movimiento == TIPO_SALIDA_VENTA,
            MovimientoInventario.motivo.like(f"Venta #{id_venta} (Lote #%"),
        )
        .order_by(MovimientoInventario.id_movimiento)
    ).all()
    resultado = []
    for m in movs:
        coincide = _PATRON_MOV_VENTA.match(m.motivo or "")
        if coincide and int(coincide.group(1)) == id_venta:
            resultado.append((m, int(coincide.group(2))))
    return resultado


def _venta_a_dict(db: Session, venta: Venta, con_insumos: bool) -> dict:
    detalles = []
    for d in db.scalars(select(DetalleVenta).where(DetalleVenta.id_venta == venta.id_venta)):
        producto = db.get(Producto, d.id_producto)
        detalles.append({
            "id_producto": d.id_producto,
            "nombre": producto.nombre if producto else f"Producto #{d.id_producto}",
            "cantidad": d.cantidad,
            "precio_unitario": float(d.precio_unitario),   # precio del día de la venta
            "subtotal": float(d.subtotal),
        })
    usuario = db.get(Usuario, venta.id_usuario)
    datos = {
        "id_venta": venta.id_venta,
        "fecha": venta.fecha_emision_ticket.isoformat(timespec="seconds") if venta.fecha_emision_ticket else None,
        "usuario": usuario.nombre_usuario if usuario else str(venta.id_usuario),
        "forma_pago": venta.forma_pago,
        "total": float(venta.total),
        "monto_recibido": float(venta.monto_recibido),
        "cambio": float(venta.cambio),
        "estado": venta.estado,
        "detalles": detalles,
    }
    if con_insumos:
        # Lo que realmente se descontó (receta vigente al momento de vender).
        consumidos = defaultdict(Decimal)
        for mov, _id_lote in _movimientos_de_venta(db, venta.id_venta):
            consumidos[mov.id_insumo] += _dec(mov.cantidad)
        datos["insumos_consumidos"] = []
        for id_insumo, cantidad in consumidos.items():
            insumo = db.get(Insumo, id_insumo)
            datos["insumos_consumidos"].append({
                "id_insumo": id_insumo,
                "insumo": insumo.nombre if insumo else str(id_insumo),
                "unidad": insumo.unidad_medida if insumo else None,
                "cantidad": float(cantidad),
            })
    return datos


def listar_ventas(db: Session, fecha: date = None, limite: int = 100) -> list:
    consulta = select(Venta).order_by(Venta.id_venta.desc()).limit(limite)
    if fecha is not None:
        inicio = datetime.combine(fecha, datetime.min.time())
        fin = datetime.combine(fecha, datetime.max.time())
        consulta = consulta.where(Venta.fecha_emision_ticket.between(inicio, fin))
    return [_venta_a_dict(db, v, con_insumos=False) for v in db.scalars(consulta)]


def obtener_venta(db: Session, id_venta: int) -> dict:
    venta = db.get(Venta, id_venta)
    if venta is None:
        raise NoEncontrado(f"La venta #{id_venta} no existe.")
    return _venta_a_dict(db, venta, con_insumos=True)


# =====================================================================
# RF 9 — Cancelación / devolución (solo Administrador)
# =====================================================================
def cancelar_venta(db: Session, id_venta: int, id_usuario: int, motivo: str) -> dict:
    """
    No borra la venta: cambia su estado a 'cancelada'.
    Regresa cada insumo al MISMO lote del que salió si el lote sigue vigente;
    si el lote ya caducó, esa cantidad se registra como merma.
    Todo en una sola transacción (RF 19).
    """
    if motivo not in MOTIVOS_CANCELACION:
        raise DatosInvalidos("Motivo de cancelación no válido.")

    hoy = date.today()
    try:
        usuario = db.get(Usuario, id_usuario)
        if (
            usuario is None
            or (usuario.rol or "").strip().lower() != ROL_ADMIN.lower()
            or (usuario.estado or "Activo").strip().lower() != "activo"
        ):
            raise NoAutorizado("Solo un Administrador puede cancelar ventas.")

        venta = db.get(Venta, id_venta, with_for_update=True)
        if venta is None:
            raise NoEncontrado(f"La venta #{id_venta} no existe.")
        if (venta.estado or "").lower() == ESTADO_CANCELADA:
            raise VentaYaCancelada(f"La venta #{id_venta} ya estaba cancelada.")

        ahora = datetime.now()
        restituidos, a_merma = [], []

        for mov, id_lote in _movimientos_de_venta(db, id_venta):
            cantidad = _dec(mov.cantidad)
            lote = db.get(LoteInsumo, id_lote, with_for_update=True)
            vigente = lote is not None and (lote.caducidad is None or lote.caducidad >= hoy)

            if vigente:
                lote.cantidad_disponible = _dec(lote.cantidad_disponible) + cantidad
                _actualizar_estado_lote(lote)
                db.add(MovimientoInventario(
                    id_insumo=mov.id_insumo,
                    id_usuario=id_usuario,
                    tipo_movimiento=TIPO_ENTRADA_CANCELACION,
                    cantidad=cantidad,
                    motivo=f"Cancelación venta #{id_venta} (Lote #{id_lote}) - {motivo}",
                    fecha_movimiento=ahora,
                ))
                restituidos.append({"id_lote": id_lote, "id_insumo": mov.id_insumo, "cantidad": float(cantidad)})
            else:
                db.add(Merma(
                    id_insumo=mov.id_insumo,
                    id_lote=id_lote if lote is not None else None,
                    id_usuario=id_usuario,
                    cantidad=cantidad,
                    motivo=f"Cancelación venta #{id_venta}: lote caducado",
                    fecha=ahora,
                ))
                db.add(MovimientoInventario(
                    id_insumo=mov.id_insumo,
                    id_usuario=id_usuario,
                    tipo_movimiento=TIPO_CANCELACION_A_MERMA,
                    cantidad=cantidad,
                    motivo=f"Cancelación venta #{id_venta} (Lote #{id_lote} caducado) - {motivo}",
                    fecha_movimiento=ahora,
                ))
                a_merma.append({"id_lote": id_lote, "id_insumo": mov.id_insumo, "cantidad": float(cantidad)})

        venta.estado = ESTADO_CANCELADA
        db.commit()

        return {
            "id_venta": id_venta,
            "estado": ESTADO_CANCELADA,
            "motivo": motivo,
            "restituidos": restituidos,
            "enviados_a_merma": a_merma,
        }
    except Exception:
        db.rollback()
        raise