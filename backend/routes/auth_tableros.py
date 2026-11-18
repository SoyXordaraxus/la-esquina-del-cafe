from datetime import date, timedelta
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func

from backend.database import get_db
from backend.models import Insumo, LoteInsumo, Venta, Merma

router = APIRouter(prefix="/api", tags=["Tableros"])


# ==========================================
# 1. PANEL PRINCIPAL (02_Panel) - DESDE MYSQL
# ==========================================
@router.get("/dashboard/resumen")
def obtener_resumen_dia(db: Session = Depends(get_db)):
    hoy = date.today()
    limite_caducidad = hoy + timedelta(days=7)

    # Ventas del día (o acumuladas si aún no hay ventas con fecha de hoy)
    ventas_hoy = db.query(Venta).filter(func.date(Venta.fecha_emision_ticket) == hoy).all()
    if not ventas_hoy:
        ventas_hoy = db.query(Venta).all()

    ventas_dia = sum(float(v.total) for v in ventas_hoy)
    tickets_dia = len(ventas_hoy)

    # Mermas registradas
    mermas = db.query(Merma).all()
    registros_mermas = len(mermas)
    mermas_mes = 0.0
    for m in mermas:
        lote = db.query(LoteInsumo).filter(LoteInsumo.id_lote == m.id_lote).first()
        costo = float(lote.costo_unitario) if lote else 25.0
        mermas_mes += float(m.cantidad) * costo

    # Insumos y lotes activos
    insumos = db.query(Insumo).filter(Insumo.estado == "Activo").all()
    insumos_bajo_minimo = 0
    alertas = []

    for ins in insumos:
        lotes_insumo = (
            db.query(LoteInsumo)
            .filter(LoteInsumo.id_insumo == ins.id_insumo, LoteInsumo.cantidad_disponible > 0)
            .order_by(LoteInsumo.caducidad.asc())
            .all()
        )
        stock_total = sum(float(l.cantidad_disponible) for l in lotes_insumo)
        minimo = float(ins.minimo_reposicion)

        if stock_total <= minimo:
            insumos_bajo_minimo += 1
            lote_ref = lotes_insumo[0].numero_factura if lotes_insumo and lotes_insumo[0].numero_factura else f"INS-{ins.id_insumo:03d}"
            alertas.append({
                "insumo": ins.nombre,
                "lote": lote_ref,
                "vencimiento": f"Mínimo: {minimo:g} {ins.unidad_medida}",
                "vencimiento_tipo": "neutro",
                "cantidad_restante": f"{stock_total:g} {ins.unidad_medida}",
                "estado": "Stock bajo",
                "estado_tipo": "rojo",
                "accion": "Reabastecer"
            })

    # Lotes caducados o próximos a caducar (<= 7 días)
    lotes_proximos = (
        db.query(LoteInsumo)
        .filter(
            LoteInsumo.cantidad_disponible > 0,
            LoteInsumo.caducidad != None,
            LoteInsumo.caducidad <= limite_caducidad
        )
        .order_by(LoteInsumo.caducidad.asc())
        .all()
    )

    lotes_proximos_caducar = len(lotes_proximos)

    for lote in lotes_proximos:
        ins = db.query(Insumo).filter(Insumo.id_insumo == lote.id_insumo).first()
        if not ins:
            continue
        dias = (lote.caducidad - hoy).days
        codigo_lote = lote.numero_factura or f"LOTE-{lote.id_lote:03d}"

        if dias < 0:
            texto_venc = "Venció ayer" if dias == -1 else f"Venció hace {abs(dias)} días"
            alertas.insert(0, {
                "insumo": ins.nombre,
                "lote": codigo_lote,
                "vencimiento": texto_venc,
                "vencimiento_tipo": "rojo",
                "cantidad_restante": f"{float(lote.cantidad_disponible):g} {ins.unidad_medida}",
                "estado": "Caducado",
                "estado_tipo": "rojo",
                "accion": "Registrar merma"
            })
        else:
            texto_venc = "Vence hoy" if dias == 0 else f"Vence en {dias} días"
            alertas.append({
                "insumo": ins.nombre,
                "lote": codigo_lote,
                "vencimiento": texto_venc,
                "vencimiento_tipo": "amarillo",
                "cantidad_restante": f"{float(lote.cantidad_disponible):g} {ins.unidad_medida}",
                "estado": "Por vencer",
                "estado_tipo": "amarillo",
                "accion": "Ver lote"
            })

    return {
        "estado_turno": "Regla PEPS activa",
        "metricas": {
            "ventas_dia": round(ventas_dia, 2),
            "tickets_dia": tickets_dia,
            "insumos_bajo_minimo": insumos_bajo_minimo,
            "lotes_proximos_caducar": lotes_proximos_caducar,
            "mermas_mes": round(mermas_mes, 2),
            "registros_mermas": registros_mermas
        },
        "alertas": alertas
    }


# ==========================================
# 2. SEMÁFORO (06_Inventario) - DESDE MYSQL
# ==========================================
def calcular_estado_semaforo(existencia_actual: float, existencia_minima: float) -> dict:
    porcentaje = round((existencia_actual / existencia_minima) * 100) if existencia_minima > 0 else 100

    if porcentaje > 120:
        return {
            "color": "verde",
            "etiqueta": "Existencias suficientes",
            "porcentaje": porcentaje
        }
    elif porcentaje > 100:
        return {
            "color": "amarillo",
            "etiqueta": "Existencias bajas",
            "porcentaje": porcentaje
        }
    else:
        return {
            "color": "rojo",
            "etiqueta": "Existencias críticas",
            "porcentaje": porcentaje
        }


@router.get("/inventario/semaforo")
def obtener_inventario_semaforo(db: Session = Depends(get_db)):
    insumos = db.query(Insumo).filter(Insumo.estado == "Activo").all()

    resultado = []
    resumen = {"verde": 0, "amarillo": 0, "rojo": 0}

    for ins in insumos:
        lotes = (
            db.query(LoteInsumo)
            .filter(LoteInsumo.id_insumo == ins.id_insumo, LoteInsumo.cantidad_disponible > 0)
            .order_by(LoteInsumo.caducidad.asc())
            .all()
        )
        existencia_actual = sum(float(l.cantidad_disponible) for l in lotes)
        existencia_minima = float(ins.minimo_reposicion)
        codigo = lotes[0].numero_factura if lotes and lotes[0].numero_factura else f"INS-{ins.id_insumo:03d}"

        estado = calcular_estado_semaforo(existencia_actual, existencia_minima)
        resumen[estado["color"]] += 1

        resultado.append({
            "id": ins.id_insumo,
            "codigo": codigo,
            "nombre": ins.nombre,
            "categoria": ins.categoria,
            "subcategoria": "Perecederos" if ins.es_perecedero else "No perecederos",
            "unidad": ins.unidad_medida,
            "existencia_actual": round(existencia_actual, 2),
            "existencia_minima": round(existencia_minima, 2),
            "semaforo": estado
        })

    return {
        "resumen": resumen,
        "total": len(resultado),
        "productos": resultado
    }