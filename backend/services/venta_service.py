import re
from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from models import (
    DetalleConsumoPeps,
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
from services.bitacora import registrar_bitacora
from services.tiempo import ahora_utc, hoy_local, iso_local, rango_utc

FORMA_EFECTIVO = "Efectivo"
FORMA_TARJETA = "Tarjeta externa"
ESTADO_COMPLETADA = "completada"
ESTADO_CANCELADA = "cancelada"
TIPO_SALIDA_VENTA = "SALIDA_VENTA"
TIPO_ENTRADA_CANCELACION = "ENTRADA_CANCELACION"
TIPO_CANCELACION_A_MERMA = "CANCELACION_A_MERMA"
ROL_ADMIN = "Administrador"

# RF 5 / RF 6: estado del lote
LOTE_AGOTADO = "Agotado"
LOTE_DISPONIBLE = "Disponible"
LOTE_CADUCADO = "Caducado"
MOTIVO_MERMA_CADUCIDAD = "Caducidad"   # del catálogo MOTIVOS_MERMA de almacen.py

# RF 18: la cancelación no usa texto libre, solo motivos de catálogo.
MOTIVOS_CANCELACION = (
    "Error de captura",
    "Devolución del cliente",
    "Producto en mal estado",
)

# Texto del motivo de cada movimiento de venta: "Venta #12 (Lote #3)".
# El origen real de cada descuento está en detalle_consumo_peps; el patrón solo se usa
# para ventas antiguas registradas antes de que existiera esa tabla.
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
    """RF 5: Agotado al llegar a 0; vuelve a Disponible si recupera existencias."""
    if _dec(lote.cantidad_disponible) <= 0:
        lote.estado = LOTE_AGOTADO
    elif (lote.estado or "") == LOTE_AGOTADO:
        lote.estado = LOTE_DISPONIBLE


def _lote_vigente(hoy: date):
    """Lotes que pueden surtir una venta: no vencidos y ni Caducados ni Agotados."""
    return (
        or_(LoteInsumo.caducidad.is_(None), LoteInsumo.caducidad >= hoy),
        or_(LoteInsumo.estado.is_(None), LoteInsumo.estado.notin_((LOTE_CADUCADO, LOTE_AGOTADO))),
    )


def _lote_caducado(lote, hoy: date) -> bool:
    return (lote.estado or "") == LOTE_CADUCADO or (lote.caducidad is not None and lote.caducidad < hoy)


def _costo_base(lote, insumo) -> Decimal:
    """costo_unitario es por unidad de compra; se divide entre factor_conversion (RF 2)."""
    factor = _dec(insumo.factor_conversion or 1) if insumo is not None else Decimal("1")
    costo = _dec(lote.costo_unitario)
    return costo / factor if factor > 0 else costo


def _stock_vigente_por_insumo(db: Session, hoy: date) -> dict:
    filas = db.execute(
        select(LoteInsumo.id_insumo, func.coalesce(func.sum(LoteInsumo.cantidad_disponible), 0))
        .where(LoteInsumo.cantidad_disponible > 0, *_lote_vigente(hoy))
        .group_by(LoteInsumo.id_insumo)
    ).all()
    return {id_insumo: _dec(cantidad) for id_insumo, cantidad in filas}


def _max_porciones(ingredientes, stock: dict) -> int:
    """Cuántas unidades del producto alcanzan con el stock vigente (0 si no tiene receta)."""
    if not ingredientes:
        return 0
    maximo = None
    for id_insumo, cantidad in ingredientes:
        if cantidad <= 0:
            continue
        alcanza = int(stock.get(id_insumo, Decimal("0")) // cantidad)
        maximo = alcanza if maximo is None else min(maximo, alcanza)
    return max(maximo or 0, 0)


def listar_productos_disponibles(db: Session) -> dict:
    """
    Catálogo de Caja (RF 7.1). Por producto: receta y max_porciones con el stock
    vigente (lotes Disponibles y no caducados según la fecha del negocio).
    'stock_insumos' permite a caja.js calcular el consumo combinado de la comanda,
    porque varios productos comparten insumos. Es solo ayuda en pantalla: el cobro
    vuelve a validar todo dentro de la transacción.
    """
    hoy = hoy_local()
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
    usados = set()
    for p in productos:
        ingredientes = recetas.get(p.id_producto, [])
        usados.update(i for i, _ in ingredientes)
        maximo = _max_porciones(ingredientes, stock)
        resultado.append({
            "id_producto": p.id_producto,
            "nombre": p.nombre,
            "categoria": p.categoria,
            "precio": float(p.precio_venta),
            "disponible": maximo > 0,
            "max_porciones": maximo,
            "receta": [{"id_insumo": i, "cantidad": float(c)} for i, c in ingredientes],
        })
    return {
        "productos": resultado,
        "stock_insumos": {str(i): float(stock.get(i, Decimal("0"))) for i in sorted(usados)},
    }


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

    hoy = hoy_local()

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

        # 4. Validar existencias PEPS (caducidad más próxima y entrada más antigua primero)
        lotes_por_insumo = {}
        faltantes = []
        for id_insumo in sorted(requerido):
            necesario = requerido[id_insumo]
            lotes = db.scalars(
                select(LoteInsumo)
                .where(
                    LoteInsumo.id_insumo == id_insumo,
                    LoteInsumo.cantidad_disponible > 0,
                    *_lote_vigente(hoy),
                )
                .order_by(
                    LoteInsumo.caducidad.is_(None).asc(),
                    LoteInsumo.caducidad.asc(),
                    LoteInsumo.fecha_entrada.asc(),
                    LoteInsumo.id_lote.asc(),
                )
                .with_for_update()
            ).all()
            lotes_por_insumo[id_insumo] = lotes
            disponible = sum((_dec(l.cantidad_disponible) for l in lotes), Decimal("0"))

            if disponible < necesario:
                insumo = db.get(Insumo, id_insumo)
                faltantes.append({
                    "insumo": insumo.nombre if insumo else str(id_insumo),
                    "unidad": getattr(insumo, "unidad_medida", None),
                    "necesario": float(necesario),
                    "disponible": float(disponible),
                })

        if faltantes:
            raise StockInsuficiente(faltantes)

        # 5. Guardar Venta, Detalles, consumo PEPS y Movimientos (una sola transacción)
        ahora = ahora_utc()
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

        recetas_por_producto = defaultdict(list)
        for r in recetas:
            recetas_por_producto[r.id_producto].append(r)

        detalles = []
        for id_producto, cantidad in pedido.items():
            producto = productos[id_producto]
            precio = _dinero(producto.precio_venta)
            subtotal = _dinero(precio * cantidad)
            detalle = DetalleVenta(
                id_venta=venta.id_venta,
                id_producto=id_producto,
                cantidad=cantidad,
                precio_unitario=precio,
                subtotal=subtotal,
            )
            db.add(detalle)
            db.flush()
            detalles.append({
                "id_producto": id_producto,
                "nombre": producto.nombre,
                "cantidad": cantidad,
                "precio_unitario": float(precio),
                "subtotal": float(subtotal),
            })

            # Descuento PEPS de cada insumo de la receta, ligado a este renglón de venta
            for r in recetas_por_producto[id_producto]:
                insumo = db.get(Insumo, r.id_insumo)
                restante = _dec(r.cantidad_necesaria) * cantidad
                for lote in lotes_por_insumo[r.id_insumo]:
                    if restante <= 0:
                        break
                    saldo = _dec(lote.cantidad_disponible)
                    if saldo <= 0:
                        continue
                    tomar = min(saldo, restante)
                    restante -= tomar
                    lote.cantidad_disponible = saldo - tomar
                    _actualizar_estado_lote(lote)
                    db.add(DetalleConsumoPeps(
                        id_detalle_venta=detalle.id_detalle,
                        id_lote=lote.id_lote,
                        cantidad_descontada=tomar,
                        costo_aplicado=_dinero(tomar * _costo_base(lote, insumo)),
                    ))
                    db.add(MovimientoInventario(
                        id_insumo=r.id_insumo,
                        id_lote=lote.id_lote,
                        id_venta=venta.id_venta,
                        id_usuario=id_usuario,
                        tipo_movimiento=TIPO_SALIDA_VENTA,
                        cantidad=tomar,
                        motivo=f"Venta #{venta.id_venta} (Lote #{lote.id_lote})",
                        fecha_movimiento=ahora,
                    ))

        registrar_bitacora(
            db, id_usuario, "VENTA_REGISTRADA",
            f"Venta #{venta.id_venta} · ${total:.2f} · {forma} · {sum(pedido.values())} artículo(s)",
        )

        db.commit()
        db.refresh(venta)

        return {
            "id_venta": venta.id_venta,
            "fecha": iso_local(ahora),
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
def _consumos_de_venta(db: Session, id_venta: int, bloquear: bool = False) -> list:
    """
    Lo que se descontó de cada lote: [(id_insumo, id_lote, cantidad, costo_aplicado)].
    Fuente: detalle_consumo_peps. Para ventas anteriores a esa tabla se usan los
    movimientos SALIDA_VENTA (costo_aplicado = None).
    """
    filas = db.execute(
        select(LoteInsumo.id_insumo, DetalleConsumoPeps.id_lote,
               DetalleConsumoPeps.cantidad_descontada, DetalleConsumoPeps.costo_aplicado)
        .join(DetalleVenta, DetalleVenta.id_detalle == DetalleConsumoPeps.id_detalle_venta)
        .join(LoteInsumo, LoteInsumo.id_lote == DetalleConsumoPeps.id_lote)
        .where(DetalleVenta.id_venta == id_venta)
        .order_by(DetalleConsumoPeps.id_consumo)
    ).all()
    if filas:
        return [(i, l, _dec(c), _dec(costo)) for i, l, c, costo in filas]
    return [(m.id_insumo, id_lote, _dec(m.cantidad), None) for m, id_lote in _movimientos_de_venta(db, id_venta)]


def _movimientos_de_venta(db: Session, id_venta: int) -> list:
    """(Ventas antiguas) Salidas de inventario de la venta, con el lote tomado del motivo."""
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
        "fecha": iso_local(venta.fecha_emision_ticket),   # hora del negocio con desfase
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
        for id_insumo, _id_lote, cantidad, _costo in _consumos_de_venta(db, venta.id_venta):
            consumidos[id_insumo] += cantidad
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
        # 'fecha' es un día de calendario del negocio; se compara su rango en UTC
        inicio, fin = rango_utc(fecha)
        consulta = consulta.where(Venta.fecha_emision_ticket >= inicio, Venta.fecha_emision_ticket < fin)
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

    hoy = hoy_local()
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

        ahora = ahora_utc()
        restituidos, a_merma = [], []

        for id_insumo, id_lote, cantidad, costo_aplicado in _consumos_de_venta(db, id_venta):
            lote = db.get(LoteInsumo, id_lote, with_for_update=True)
            caducado = lote is None or _lote_caducado(lote, hoy)

            if not caducado:
                # Regresa exactamente lo que salió de este lote y lo reactiva
                lote.cantidad_disponible = _dec(lote.cantidad_disponible) + cantidad
                lote.estado = LOTE_DISPONIBLE
                db.add(MovimientoInventario(
                    id_insumo=id_insumo,
                    id_lote=id_lote,
                    id_venta=id_venta,
                    id_usuario=id_usuario,
                    tipo_movimiento=TIPO_ENTRADA_CANCELACION,
                    cantidad=cantidad,
                    motivo=f"Cancelación venta #{id_venta} (Lote #{id_lote}) - {motivo}",
                    fecha_movimiento=ahora,
                ))
                restituidos.append({"id_lote": id_lote, "id_insumo": id_insumo, "cantidad": float(cantidad)})
            else:
                # El lote ya caducó: la cantidad devuelta se pierde como merma
                if costo_aplicado is not None:
                    costo_perdida = _dinero(costo_aplicado)
                elif lote is not None:
                    costo_perdida = _dinero(cantidad * _costo_base(lote, db.get(Insumo, id_insumo)))
                else:
                    costo_perdida = Decimal("0.00")
                if lote is not None and _dec(lote.cantidad_disponible) > 0:
                    lote.estado = LOTE_CADUCADO
                db.add(Merma(
                    id_insumo=id_insumo,
                    id_lote=id_lote if lote is not None else None,
                    id_usuario=id_usuario,
                    autorizado_por=id_usuario,
                    cantidad=cantidad,
                    costo_perdida=costo_perdida,
                    motivo=MOTIVO_MERMA_CADUCIDAD,
                    notas=f"Cancelación venta #{id_venta} ({motivo}): lote #{id_lote} caducado",
                    fecha=ahora,
                ))
                db.add(MovimientoInventario(
                    id_insumo=id_insumo,
                    id_lote=id_lote if lote is not None else None,
                    id_venta=id_venta,
                    id_usuario=id_usuario,
                    tipo_movimiento=TIPO_CANCELACION_A_MERMA,
                    cantidad=cantidad,
                    motivo=f"Cancelación venta #{id_venta} (Lote #{id_lote} caducado) - {motivo}",
                    fecha_movimiento=ahora,
                ))
                a_merma.append({"id_lote": id_lote, "id_insumo": id_insumo, "cantidad": float(cantidad),
                                "costo_perdida": float(costo_perdida)})

        venta.estado = ESTADO_CANCELADA
        registrar_bitacora(
            db, id_usuario, "VENTA_CANCELADA",
            f"Venta #{id_venta} · ${_dec(venta.total):.2f} · Motivo: {motivo} · "
            f"{len(restituidos)} lote(s) restituido(s), {len(a_merma)} a merma",
        )
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