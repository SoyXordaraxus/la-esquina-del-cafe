from datetime import date, timedelta
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import func

from database import get_db
from models import Usuario, Insumo, LoteInsumo, Venta, Merma, Bitacora

router = APIRouter(prefix="/api", tags=["Auth y Tableros"])


class LoginSchema(BaseModel):
    usuario: str
    contrasena: str


def registrar_bitacora(db: Session, id_usuario: int, accion: str, detalle: str):
    db.add(Bitacora(id_usuario=id_usuario, accion=accion, detalle=detalle))


# ==========================================
# 0. INICIO DE SESIÓN (RF 1, RF 1.1, RF 1.2, RF 13)
# ==========================================
@router.post("/auth/login")
def iniciar_sesion(datos: LoginSchema, db: Session = Depends(get_db)):
    user_input = (datos.usuario or "").strip()
    pass_input = (datos.contrasena or "").strip()

    if not user_input or len(pass_input) < 8:
        raise HTTPException(status_code=400, detail="Usuario requerido y contraseña de al menos 8 caracteres.")

    usuario = (
        db.query(Usuario)
        .filter(
            (func.lower(Usuario.nombre_usuario) == user_input.lower()) |
            (func.lower(Usuario.correo) == user_input.lower())
        )
        .first()
    )

    if not usuario or usuario.contrasena != pass_input:
        raise HTTPException(status_code=401, detail="Usuario o contraseña incorrectos.")

    if (usuario.estado or "").lower() != "activo":
        raise HTTPException(status_code=403, detail="Esta cuenta está desactivada. Contacta al Administrador.")

    # Normalizar rol para el contrato del frontend ("Administrador" | "Cajero")
    rol_norm = "Administrador" if "admin" in usuario.rol.lower() else "Cajero"

    registrar_bitacora(db, usuario.id_usuario, "SESION_INICIADA", f"Inicio de sesión correcto · Rol: {rol_norm}")
    db.commit()

    return {
        "id_usuario": usuario.id_usuario,
        "nombre": usuario.nombre_usuario,
        "correo": usuario.correo,
        "rol": rol_norm,
    }


# ==========================================
# 1. PANEL PRINCIPAL (02_Panel)
# ==========================================
@router.get("/dashboard/resumen")
def obtener_resumen_dia(db: Session = Depends(get_db)):
    hoy = date.today()
    limite_caducidad = hoy + timedelta(days=5)  # RF 6.1: alertas hasta 5 días

    ventas_hoy = db.query(Venta).filter(
        func.date(Venta.fecha_emision_ticket) == hoy,
        func.lower(Venta.estado) == "completada"
    ).all()
    if not ventas_hoy:
        ventas_hoy = db.query(Venta).filter(func.lower(Venta.estado) == "completada").all()

    ventas_dia = sum(float(v.total) for v in ventas_hoy)
    tickets_dia = len(ventas_hoy)

    mermas = db.query(Merma).all()
    registros_mermas = len(mermas)
    mermas_mes = sum(float(m.costo_perdida) for m in mermas)

    insumos = db.query(Insumo).filter(Insumo.estado == "Activo").all()
    insumos_bajo_minimo = 0
    alertas = []

    for ins in insumos:
        # RF 10: excluir estrictamente lotes caducados o agotados
        lotes_vigentes = (
            db.query(LoteInsumo)
            .filter(
                LoteInsumo.id_insumo == ins.id_insumo,
                LoteInsumo.cantidad_disponible > 0,
                (LoteInsumo.caducidad == None) | (LoteInsumo.caducidad >= hoy)
            )
            .order_by(LoteInsumo.caducidad.asc())
            .all()
        )
        stock_total = sum(float(l.cantidad_disponible) for l in lotes_vigentes)
        minimo = float(ins.minimo_reposicion)

        if stock_total <= minimo:
            insumos_bajo_minimo += 1
            lote_ref = lotes_vigentes[0].numero_factura if lotes_vigentes and lotes_vigentes[0].numero_factura else f"INS-{ins.id_insumo:03d}"
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
        elif dias <= 3:
            texto_venc = "Vence hoy" if dias == 0 else ("Vence mañana" if dias == 1 else f"Vence en {dias} días")
            alertas.append({
                "insumo": ins.nombre,
                "lote": codigo_lote,
                "vencimiento": texto_venc,
                "vencimiento_tipo": "rojo",
                "cantidad_restante": f"{float(lote.cantidad_disponible):g} {ins.unidad_medida}",
                "estado": "Urgente",
                "estado_tipo": "rojo",
                "accion": "Ver lote"
            })
        else:
            alertas.append({
                "insumo": ins.nombre,
                "lote": codigo_lote,
                "vencimiento": f"Vence en {dias} días",
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
# 2. SEMÁFORO DE INVENTARIO (RF 10, RF 10.1)
# ==========================================
def calcular_estado_semaforo(existencia_actual: float, existencia_minima: float) -> dict:
    porcentaje = round((existencia_actual / existencia_minima) * 100) if existencia_minima > 0 else 100
    if porcentaje > 120:
        return {"color": "verde", "etiqueta": "Existencias suficientes", "porcentaje": porcentaje}
    elif porcentaje > 100:
        return {"color": "amarillo", "etiqueta": "Existencias bajas", "porcentaje": porcentaje}
    else:
        return {"color": "rojo", "etiqueta": "Existencias críticas", "porcentaje": porcentaje}


@router.get("/inventario/semaforo")
def obtener_inventario_semaforo(db: Session = Depends(get_db)):
    hoy = date.today()
    insumos = db.query(Insumo).filter(Insumo.estado == "Activo").all()

    resultado = []
    resumen = {"verde": 0, "amarillo": 0, "rojo": 0}

    for ins in insumos:
        lotes = (
            db.query(LoteInsumo)
            .filter(
                LoteInsumo.id_insumo == ins.id_insumo,
                LoteInsumo.cantidad_disponible > 0,
                (LoteInsumo.caducidad == None) | (LoteInsumo.caducidad >= hoy)
            )
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

    return {"resumen": resumen, "total": len(resultado), "productos": resultado}