import re
from datetime import date
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import func

from database import get_db
from models import Usuario, Insumo, Proveedor, LoteInsumo, MovimientoInventario, Merma, Bitacora
from services.contrasenas import verificar
from services.sesion import usuario_actual
from services.tiempo import formato_local, hoy_local

router = APIRouter(prefix="/api/almacen", tags=["Almacén"], dependencies=[Depends(usuario_actual)])

MOTIVOS_MERMA = (
    "Caducidad",
    "Derrame",
    "Error de preparación",
    "Daño en empaque",
)


# RF 18: número de factura con formato fijo "FAC-" + 3 a 8 dígitos (FAC-1045, FAC-45425).
# Solo se valida en lotes nuevos; los lotes ya guardados con otro formato se conservan.
PATRON_FACTURA = re.compile(r"^FAC-\d{3,8}$")


def normalizar_factura(texto: Optional[str]) -> str:
    """Quita espacios y pone el prefijo en mayúsculas; lanza 400 si falta o no cumple el formato."""
    valor = (texto or "").strip().upper()
    if not valor:
        raise HTTPException(status_code=400, detail="El número de factura es obligatorio (formato FAC-1045).")
    if not PATRON_FACTURA.fullmatch(valor):
        raise HTTPException(
            status_code=400,
            detail="El número de factura debe tener el formato FAC- seguido de 3 a 8 dígitos (ej. FAC-1045).",
        )
    return valor


class EntradaLoteSchema(BaseModel):
    id_insumo: int
    id_proveedor: Optional[int] = None
    cantidad_ingresada: float
    unidad_compra: str
    costo_unitario: float
    caducidad: Optional[date] = None
    numero_factura: Optional[str] = None
    id_usuario: int = 1


class RegistroMermaSchema(BaseModel):
    id_lote: int
    cantidad: float
    motivo: str
    notas: Optional[str] = None
    id_usuario: int = 1
    password_admin: Optional[str] = None  # Requerida por RF 11.1 si monto > $100 y usuario es Cajero


def convertir_a_unidad_base(cantidad: float, unidad_compra: str, insumo: Insumo) -> float:
    u_comp = (unidad_compra or "").strip().lower()
    u_base = (insumo.unidad_medida or "").strip().lower()

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
    # Si usa unidad de compra configurada en catálogo (cja, paq, etc.)
    if u_comp == (insumo.unidad_compra or "").strip().lower() and float(insumo.factor_conversion or 0) > 0:
        return cantidad * float(insumo.factor_conversion)

    return cantidad


def sincronizar_caducidades(db: Session, hoy: date) -> None:
    """RF 6: actualiza automáticamente a 'Caducado' los lotes vencidos con saldo."""
    vencidos = (
        db.query(LoteInsumo)
        .filter(
            LoteInsumo.cantidad_disponible > 0,
            LoteInsumo.caducidad != None,
            LoteInsumo.caducidad < hoy,
            LoteInsumo.estado != "Caducado",
        )
        .all()
    )
    if vencidos:
        for l in vencidos:
            l.estado = "Caducado"
        db.commit()


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
                "unidad_compra": i.unidad_compra,
                "factor_conversion": float(i.factor_conversion or 1),
                "es_perecedero": i.es_perecedero,
            }
            for i in insumos
        ],
        "proveedores": [{"id_proveedor": p.id_proveedor, "nombre": p.nombre} for p in proveedores],
    }


@router.get("/lotes")
def listar_lotes(db: Session = Depends(get_db)):
    hoy = hoy_local()   # "vence hoy / mañana" según el calendario del negocio
    sincronizar_caducidades(db, hoy)

    lotes = (
        db.query(LoteInsumo)
        .order_by(LoteInsumo.caducidad.is_(None).asc(), LoteInsumo.caducidad.asc(), LoteInsumo.fecha_entrada.asc())
        .all()
    )
    resultado = []
    for l in lotes:
        ins = db.query(Insumo).filter(Insumo.id_insumo == l.id_insumo).first()
        prov = db.query(Proveedor).filter(Proveedor.id_proveedor == l.id_proveedor).first() if l.id_proveedor else None

        disp = float(l.cantidad_disponible)
        if disp <= 0:
            estado_lote = "Agotado"
            semaforo = "gris"
            dias_restantes = None
            texto_venc = "Sin existencias"
        elif l.caducidad is None:
            estado_lote = "Vigente"
            semaforo = "verde"
            dias_restantes = None
            texto_venc = "No perecedero"
        else:
            dias_restantes = (l.caducidad - hoy).days
            if dias_restantes < 0:
                estado_lote = "Caducado"
                semaforo = "rojo"
                texto_venc = "Venció ayer" if dias_restantes == -1 else f"Venció hace {abs(dias_restantes)} días"
            elif dias_restantes <= 3:
                estado_lote = "Vigente"
                semaforo = "rojo"
                texto_venc = "Vence hoy" if dias_restantes == 0 else ("Vence mañana" if dias_restantes == 1 else f"Vence en {dias_restantes} días")
            elif dias_restantes <= 5:
                estado_lote = "Vigente"
                semaforo = "amarillo"
                texto_venc = f"Vence en {dias_restantes} días"
            else:
                estado_lote = "Vigente"
                semaforo = "verde"
                texto_venc = f"Vence en {dias_restantes} días"

        # Costo por unidad base (para calcular monto de merma con precisión)
        factor = float(ins.factor_conversion or 1) if ins else 1.0
        costo_base = float(l.costo_unitario) / factor if factor > 0 else float(l.costo_unitario)

        resultado.append({
            "id_lote": l.id_lote,
            "codigo_lote": l.numero_factura or f"LOTE-{l.id_lote:04d}",
            "id_insumo": l.id_insumo,
            "insumo": ins.nombre if ins else f"Insumo #{l.id_insumo}",
            "unidad": ins.unidad_medida if ins else "",
            "proveedor": prov.nombre if prov else "Sin proveedor",
            "cantidad_recibida": float(l.cantidad_recibida),
            "cantidad_disponible": disp,
            "costo_unitario": float(l.costo_unitario),
            "costo_unitario_base": round(costo_base, 4),
            "caducidad": str(l.caducidad) if l.caducidad else None,
            "dias_restantes": dias_restantes,
            "texto_vencimiento": texto_venc,
            "estado": estado_lote,
            "semaforo": semaforo,
            "numero_factura": l.numero_factura or "—",
            "fecha_entrada": formato_local(l.fecha_entrada, "%Y-%m-%d %H:%M"),
        })
    return {"lotes": resultado}


@router.get("/caducidades/resumen")
def resumen_caducidades(db: Session = Depends(get_db)):
    """Número del badge de Caducidades: lotes caducados o que vencen en <= 5 días."""
    lotes = listar_lotes(db)["lotes"]
    alertas = [
        l for l in lotes
        if l["estado"] == "Caducado"
        or (l["estado"] == "Vigente" and l["dias_restantes"] is not None and l["dias_restantes"] <= 5)
    ]
    return {
        "alertas": len(alertas),
        "caducados": sum(1 for l in alertas if l["estado"] == "Caducado"),
        "por_vencer": sum(1 for l in alertas if l["estado"] == "Vigente"),
        "fecha_negocio": str(hoy_local()),
    }


@router.post("/recepcion", status_code=201)
def registrar_entrada_lote(datos: EntradaLoteSchema, db: Session = Depends(get_db), actual: Usuario = Depends(usuario_actual)):
    datos.id_usuario = actual.id_usuario
    insumo = db.query(Insumo).filter(Insumo.id_insumo == datos.id_insumo).first()
    if not insumo:
        raise HTTPException(status_code=404, detail="El insumo seleccionado no existe.")
    if (insumo.estado or "Activo").strip().lower() != "activo":
        raise HTTPException(
            status_code=409,
            detail=f"El insumo «{insumo.nombre}» está inactivo. Actívalo en Insumos para poder recibir lotes.",
        )

    if datos.cantidad_ingresada <= 0:
        raise HTTPException(status_code=400, detail="La cantidad recibida debe ser mayor a 0.")

    if insumo.es_perecedero and not datos.caducidad:
        raise HTTPException(status_code=400, detail="Este insumo es perecedero y requiere fecha de caducidad.")

    # RF 4.1: la fecha de caducidad debe ser >= fecha actual
    if datos.caducidad and datos.caducidad < hoy_local():
        raise HTTPException(status_code=400, detail="La fecha de caducidad no puede ser anterior a hoy.")

    factura = normalizar_factura(datos.numero_factura)
    repetida = db.query(LoteInsumo.id_lote).filter(
        LoteInsumo.id_insumo == insumo.id_insumo,
        func.upper(func.trim(LoteInsumo.numero_factura)) == factura,
    ).first()
    if repetida:
        raise HTTPException(status_code=409, detail="Esa factura ya fue registrada para este insumo.")
    datos.numero_factura = factura

    cantidad_convertida = convertir_a_unidad_base(datos.cantidad_ingresada, datos.unidad_compra, insumo)

    nuevo_lote = LoteInsumo(
        id_insumo=insumo.id_insumo,
        id_proveedor=datos.id_proveedor,
        cantidad_recibida=cantidad_convertida,
        cantidad_disponible=cantidad_convertida,
        costo_unitario=datos.costo_unitario,
        caducidad=datos.caducidad,
        numero_factura=datos.numero_factura,
        estado="Disponible",
    )
    db.add(nuevo_lote)
    db.flush()

    db.add(MovimientoInventario(
        id_insumo=insumo.id_insumo,
        id_lote=nuevo_lote.id_lote,
        id_usuario=datos.id_usuario,
        tipo_movimiento="Entrada",
        cantidad=cantidad_convertida,
        motivo=f"Recepción de lote #{nuevo_lote.id_lote} - Factura: {datos.numero_factura or 'S/N'}",
    ))
    db.add(Bitacora(
        id_usuario=datos.id_usuario,
        accion="ENTRADA_INSUMO",
        detalle=f"{insumo.nombre} · +{cantidad_convertida:g} {insumo.unidad_medida} · Lote #{nuevo_lote.id_lote}",
    ))

    db.commit()
    db.refresh(nuevo_lote)

    return {
        "mensaje": "Lote registrado correctamente en inventario PEPS",
        "id_lote": nuevo_lote.id_lote,
        "insumo": insumo.nombre,
        "cantidad_guardada": float(nuevo_lote.cantidad_disponible),
        "unidad_base": insumo.unidad_medida,
    }


# =========================================================
# 2. MERMAS (RF 11, RF 11.1, RF 11.2)
# =========================================================
@router.get("/mermas")
def listar_mermas(db: Session = Depends(get_db)):
    mermas = db.query(Merma).order_by(Merma.fecha.desc()).limit(50).all()
    resultado = []
    for m in mermas:
        ins = db.query(Insumo).filter(Insumo.id_insumo == m.id_insumo).first()
        usr = db.query(Usuario).filter(Usuario.id_usuario == m.id_usuario).first()
        resultado.append({
            "id_merma": m.id_merma,
            "id_lote": m.id_lote,
            "insumo": ins.nombre if ins else f"Insumo #{m.id_insumo}",
            "unidad": ins.unidad_medida if ins else "",
            "cantidad": float(m.cantidad),
            "costo_perdida": float(m.costo_perdida),
            "motivo": m.motivo,
            "notas": m.notas or "",
            "responsable": f"{usr.nombre_usuario} ({usr.rol})" if usr else f"Usuario #{m.id_usuario}",
            "fecha": formato_local(m.fecha, "%d/%m/%Y %H:%M"),
        })
    return {"mermas": resultado}


@router.post("/mermas")
def registrar_merma(datos: RegistroMermaSchema, db: Session = Depends(get_db), actual: Usuario = Depends(usuario_actual)):
    datos.id_usuario = actual.id_usuario   # RF 11.1: el rol se toma de la sesión, no del navegador
    if datos.motivo not in MOTIVOS_MERMA:
        raise HTTPException(status_code=400, detail="Motivo de merma no válido.")

    lote = db.query(LoteInsumo).filter(LoteInsumo.id_lote == datos.id_lote).with_for_update().first()
    if not lote:
        raise HTTPException(status_code=404, detail="Lote no encontrado.")

    if datos.cantidad <= 0 or datos.cantidad > float(lote.cantidad_disponible):
        raise HTTPException(status_code=400, detail="Cantidad inválida o mayor al saldo disponible del lote.")

    ins = db.query(Insumo).filter(Insumo.id_insumo == lote.id_insumo).first()
    usr = db.query(Usuario).filter(Usuario.id_usuario == datos.id_usuario).first()

    factor = float(ins.factor_conversion or 1) if ins else 1.0
    costo_base = float(lote.costo_unitario) / factor if factor > 0 else float(lote.costo_unitario)
    costo_perdida = round(costo_base * datos.cantidad, 2)

    id_autorizador = None
    es_admin = usr is not None and "admin" in (usr.rol or "").lower()

    # RF 11.1: Merma > $100.00 MXN requiere contraseña de Administrador
    if costo_perdida > 100.0 and not es_admin:
        if not datos.password_admin:
            raise HTTPException(
                status_code=403,
                detail="AUTORIZACION_REQUERIDA: Esta merma supera los $100.00 MXN y requiere contraseña de Administrador.",
            )
        administradores = (
            db.query(Usuario)
            .filter(
                func.lower(Usuario.rol).like("%admin%"),
                func.lower(Usuario.estado) == "activo",
            )
            .all()
        )
        admin = next((a for a in administradores if verificar(datos.password_admin.strip(), a.contrasena)), None)
        if not admin:
            # 403 y no 401: el 401 significa "sesión vencida" y el frontend cerraría la sesión del cajero
            raise HTTPException(status_code=403, detail="Contraseña de Administrador incorrecta. Operación anulada.")
        id_autorizador = admin.id_usuario

    lote.cantidad_disponible = float(lote.cantidad_disponible) - datos.cantidad
    if lote.cantidad_disponible <= 0:
        lote.estado = "Agotado"

    nueva_merma = Merma(
        id_lote=lote.id_lote,
        id_insumo=lote.id_insumo,
        id_usuario=datos.id_usuario,
        autorizado_por=id_autorizador,
        cantidad=datos.cantidad,
        costo_perdida=costo_perdida,
        motivo=datos.motivo,
        notas=(datos.notas or "").strip() or None,
    )
    db.add(nueva_merma)

    db.add(MovimientoInventario(
        id_insumo=lote.id_insumo,
        id_lote=lote.id_lote,
        id_usuario=datos.id_usuario,
        tipo_movimiento="Merma",
        cantidad=datos.cantidad,
        motivo=f"Merma ({datos.motivo}) - Lote #{lote.id_lote}",
    ))
    db.add(Bitacora(
        id_usuario=datos.id_usuario,
        accion="MERMA_REGISTRADA",
        detalle=f"{ins.nombre if ins else 'Insumo'} · -{datos.cantidad:g} {ins.unidad_medida if ins else ''} · {datos.motivo}",
    ))

    db.commit()
    return {
        "mensaje": "Merma registrada y descontada del lote.",
        "costo_perdida": costo_perdida,
    }