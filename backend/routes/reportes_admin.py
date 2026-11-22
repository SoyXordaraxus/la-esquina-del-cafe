import re
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import func, text
from sqlalchemy.orm import Session

from database import get_db, engine
from services.bitacora import registrar_bitacora
from services.contrasenas import MENSAJE_POLITICA, cumple_politica, hashear
from services.reportes_export import (
    cantidades_por_unidad, dinero, fecha_dmy, generar_csv, generar_pdf, meta_reporte, nombre_archivo, numero,
)
from services.sesion import requiere_admin
from services.tiempo import ZONA_NEGOCIO, ahora_local, formato_local, hoy_local, rango_utc
from models import (
    Usuario,
    Insumo,
    LoteInsumo,
    Venta,
    DetalleVenta,
    Producto,
    MovimientoInventario,
    Merma,
    Bitacora,
)

router = APIRouter(
    prefix="/api/admin",
    tags=["Administración, Reportes y Auditoría"],
    dependencies=[Depends(requiere_admin)],
)

CARPETA_BACKUPS = Path(__file__).resolve().parent.parent / "backups"
CARPETA_BACKUPS.mkdir(parents=True, exist_ok=True)


class UsuarioCrearSchema(BaseModel):
    nombre_usuario: str
    correo: str
    contrasena: str = Field(min_length=8)
    rol: str  # "Administrador" | "Cajero"
    id_admin: int = 1


class UsuarioEditarSchema(BaseModel):
    nombre_usuario: str
    correo: str
    contrasena: Optional[str] = None
    rol: str
    estado: str  # "Activo" | "Inactivo"
    id_admin: int = 1


# =========================================================
# 1. REPORTES EXPORTABLES (RF 12)
# =========================================================
def _costo_base_lote(lote: Optional[LoteInsumo], insumo: Optional[Insumo]) -> float:
    """costo_unitario del lote es por unidad de compra; se divide entre factor_conversion."""
    if lote is None:
        return 0.0
    factor = float(insumo.factor_conversion or 1) if insumo is not None else 1.0
    return float(lote.costo_unitario) / factor if factor > 0 else float(lote.costo_unitario)


def _construir_datos_reporte(tipo: str, fecha_inicio: date, fecha_fin: date, db: Session) -> dict:
    """
    Estructura común para la vista previa (JSON), el PDF y el CSV:
      titulo, columnas, alineacion (L/R), filas (texto ya formateado), total (fila
      TOTAL formateada) y resumen (números sin formato).
    """
    # Días de calendario del negocio -> rango UTC semiabierto [inicio_dt, fin_dt)
    inicio_dt, fin_dt = rango_utc(fecha_inicio, fecha_fin)

    if tipo == "ventas":
        ventas = (
            db.query(Venta)
            .filter(Venta.fecha_emision_ticket >= inicio_dt, Venta.fecha_emision_ticket < fin_dt)
            .order_by(Venta.fecha_emision_ticket.asc())
            .all()
        )
        por_dia = {}
        for v in ventas:
            dia = formato_local(v.fecha_emision_ticket, "%Y-%m-%d")   # clave ordenable
            d = por_dia.setdefault(dia, {"completadas": 0, "brutas": 0.0, "cancelaciones": 0.0})
            monto = float(v.total)
            d["brutas"] += monto
            if (v.estado or "").lower() == "cancelada":
                d["cancelaciones"] += monto
            else:
                d["completadas"] += 1

        filas = []
        tot = {"completadas": 0, "brutas": 0.0, "cancelaciones": 0.0, "netas": 0.0}
        for dia, d in sorted(por_dia.items()):
            netas = d["brutas"] - d["cancelaciones"]
            for k in ("completadas", "brutas", "cancelaciones"):
                tot[k] += d[k]
            tot["netas"] += netas
            filas.append([
                fecha_dmy(date.fromisoformat(dia)),
                str(d["completadas"]),
                dinero(d["brutas"]),
                dinero(d["cancelaciones"], negativo=True),
                dinero(netas),
            ])

        return {
            "titulo": "Reporte de Ventas Netas",
            "columnas": ["Fecha", "Ventas completadas", "Ventas brutas", "Cancelaciones", "Ventas netas"],
            "alineacion": ["L", "R", "R", "R", "R"],
            "filas": filas,
            "total": ["TOTAL", str(tot["completadas"]), dinero(tot["brutas"]),
                      dinero(tot["cancelaciones"], negativo=True), dinero(tot["netas"])],
            "resumen": {k: (round(v, 2) if isinstance(v, float) else v) for k, v in tot.items()},
        }

    elif tipo == "consumo":
        # Solo ventas no canceladas: al cancelar, lo consumido regresa al lote (o pasa
        # a merma si el lote caducó, y entonces aparece en el reporte de mermas).
        movs = (
            db.query(MovimientoInventario)
            .outerjoin(Venta, Venta.id_venta == MovimientoInventario.id_venta)
            .filter(
                MovimientoInventario.tipo_movimiento == "SALIDA_VENTA",
                MovimientoInventario.fecha_movimiento >= inicio_dt,
                MovimientoInventario.fecha_movimiento < fin_dt,
                (Venta.id_venta.is_(None)) | (func.lower(Venta.estado) != "cancelada"),
            )
            .all()
        )
        insumos = {}
        lotes = {}
        acumulado = {}   # id_insumo -> {"cantidad", "costo"}
        for m in movs:
            ins = insumos.setdefault(m.id_insumo, db.get(Insumo, m.id_insumo))
            lote = lotes.setdefault(m.id_lote, db.get(LoteInsumo, m.id_lote) if m.id_lote else None)
            a = acumulado.setdefault(m.id_insumo, {"cantidad": 0.0, "costo": 0.0})
            a["cantidad"] += float(m.cantidad)
            a["costo"] += float(m.cantidad) * _costo_base_lote(lote, ins)

        filas = []
        por_unidad = {}
        costo_total = 0.0
        for id_ins, a in sorted(acumulado.items(), key=lambda x: x[1]["costo"], reverse=True):
            ins = insumos.get(id_ins)
            unidad = ins.unidad_medida if ins else ""
            por_unidad[unidad] = por_unidad.get(unidad, 0.0) + a["cantidad"]
            costo_total += a["costo"]
            filas.append([
                ins.nombre if ins else f"Insumo #{id_ins}",
                ins.categoria if ins else "-",
                numero(a["cantidad"]),
                unidad,
                dinero(a["costo"]),
            ])
        return {
            "titulo": "Reporte de Consumo de Insumos",
            "columnas": ["Insumo", "Categoría", "Cantidad consumida", "Unidad", "Costo"],
            "alineacion": ["L", "L", "R", "L", "R"],
            "filas": filas,
            # Cantidades de unidades distintas no se suman: se desglosan por unidad
            "total": ["TOTAL", "", cantidades_por_unidad(por_unidad), "", dinero(costo_total)],
            "resumen": {"insumos_distintos": len(filas), "cantidad_por_unidad": {u: round(v, 2) for u, v in por_unidad.items()},
                        "costo_total": round(costo_total, 2)},
        }

    elif tipo == "mermas":
        mermas = (
            db.query(Merma)
            .filter(Merma.fecha >= inicio_dt, Merma.fecha < fin_dt)
            .order_by(Merma.fecha.asc())
            .all()
        )
        filas = []
        por_unidad = {}
        total_perdida = 0.0
        for m in mermas:
            ins = db.get(Insumo, m.id_insumo)
            unidad = ins.unidad_medida if ins else ""
            costo = float(m.costo_perdida)
            total_perdida += costo
            por_unidad[unidad] = por_unidad.get(unidad, 0.0) + float(m.cantidad)
            filas.append([
                formato_local(m.fecha, "%d/%m/%Y %H:%M"),
                ins.nombre if ins else f"Insumo #{m.id_insumo}",
                numero(m.cantidad),
                unidad,
                m.motivo or "",
                dinero(costo),
            ])
        return {
            "titulo": "Reporte de Mermas",
            "columnas": ["Fecha", "Insumo", "Cantidad", "Unidad", "Motivo", "Costo de pérdida"],
            "alineacion": ["L", "L", "R", "L", "L", "R"],
            "filas": filas,
            "total": [f"TOTAL ({len(filas)} {'registro' if len(filas) == 1 else 'registros'})", "",
                      cantidades_por_unidad(por_unidad), "", "", dinero(total_perdida)],
            "resumen": {"registros": len(filas), "cantidad_por_unidad": {u: round(v, 2) for u, v in por_unidad.items()},
                        "costo_total": round(total_perdida, 2)},
        }

    raise HTTPException(status_code=400, detail="Tipo de reporte no válido (ventas, consumo, mermas).")


def _periodo(fecha_inicio: Optional[date], fecha_fin: Optional[date]):
    f_fin = fecha_fin or hoy_local()
    f_ini = fecha_inicio or (f_fin - timedelta(days=30))
    if f_ini > f_fin:
        raise HTTPException(status_code=400, detail="La fecha de inicio no puede ser posterior a la fecha final.")
    return f_ini, f_fin


@router.get("/reportes")
def consultar_reporte(
    tipo: str = "ventas",
    fecha_inicio: Optional[date] = None,
    fecha_fin: Optional[date] = None,
    db: Session = Depends(get_db),
):
    f_ini, f_fin = _periodo(fecha_inicio, fecha_fin)
    datos = _construir_datos_reporte(tipo, f_ini, f_fin, db)
    datos["periodo"] = f"{fecha_dmy(f_ini)} al {fecha_dmy(f_fin)}"
    return datos


@router.get("/reportes/exportar")
def exportar_reporte(
    tipo: str = "ventas",
    formato: str = "csv",
    fecha_inicio: Optional[date] = None,
    fecha_fin: Optional[date] = None,
    db: Session = Depends(get_db),
    admin: Usuario = Depends(requiere_admin),
):
    formato = (formato or "").lower()
    if formato not in ("csv", "pdf"):
        raise HTTPException(status_code=400, detail="Formato no soportado. Usa csv o pdf.")
    f_ini, f_fin = _periodo(fecha_inicio, fecha_fin)
    datos = _construir_datos_reporte(tipo, f_ini, f_fin, db)
    meta = meta_reporte((f_ini, f_fin), admin.nombre_usuario, ahora_local())

    if formato == "csv":
        contenido, media = generar_csv(datos, meta), "text/csv; charset=utf-8"
    else:
        try:
            contenido, media = generar_pdf(datos, meta), "application/pdf"
        except RuntimeError as error:   # fpdf2 no instalada
            raise HTTPException(status_code=500, detail=str(error))

    registrar_bitacora(
        db, admin.id_usuario, "REPORTE_GENERADO",
        f"{datos['titulo']} · {fecha_dmy(f_ini)} al {fecha_dmy(f_fin)} · {formato.upper()}",
    )
    db.commit()

    return Response(
        content=contenido,
        media_type=media,
        headers={"Content-Disposition": f'attachment; filename="{nombre_archivo(tipo, f_ini, f_fin, formato)}"'},
    )


# =========================================================
# 2. GESTIÓN DE USUARIOS (RF 1, RF 1.1, RF 14)
# =========================================================
PATRON_CORREO = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _validar_correo(correo: str):
    if not PATRON_CORREO.match(correo or ""):
        raise HTTPException(status_code=400, detail="El correo electrónico no es válido. Ejemplo: nombre@dominio.com")


def _validar_password_rf11(pwd: str):
    if not cumple_politica(pwd):
        raise HTTPException(status_code=400, detail=MENSAJE_POLITICA)


@router.get("/usuarios")
def listar_usuarios(db: Session = Depends(get_db)):
    usuarios = db.query(Usuario).order_by(Usuario.id_usuario.asc()).all()
    return {
        "usuarios": [
            {
                "id_usuario": u.id_usuario,
                "nombre_usuario": u.nombre_usuario,
                "correo": u.correo,
                "rol": "Administrador" if "admin" in (u.rol or "").lower() else "Cajero",
                "estado": u.estado or "Activo",
                "fecha_registro": formato_local(u.fecha_registro, "%Y-%m-%d", "—"),
            }
            for u in usuarios
        ]
    }


@router.post("/usuarios", status_code=201)
def crear_usuario(datos: UsuarioCrearSchema, db: Session = Depends(get_db), admin: Usuario = Depends(requiere_admin)):
    datos.id_admin = admin.id_usuario
    nombre = datos.nombre_usuario.strip()
    correo = datos.correo.strip().lower()
    if not nombre or not correo:
        raise HTTPException(status_code=400, detail="Nombre de usuario y correo son obligatorios.")

    _validar_correo(correo)
    _validar_password_rf11(datos.contrasena)

    if db.query(Usuario).filter(func.lower(Usuario.nombre_usuario) == nombre.lower()).first():
        raise HTTPException(status_code=409, detail=f"El nombre de usuario «{nombre}» ya está en uso. Elige otro.")
    if db.query(Usuario).filter(func.lower(Usuario.correo) == correo).first():
        raise HTTPException(status_code=409, detail=f"El correo {correo} ya está registrado en otra cuenta.")

    rol_valido = "Administrador" if datos.rol == "Administrador" else "Cajero"
    nuevo = Usuario(
        nombre_usuario=nombre,
        correo=correo,
        contrasena=hashear(datos.contrasena.strip()),
        rol=rol_valido,
        estado="Activo",
    )
    db.add(nuevo)
    db.flush()

    db.add(Bitacora(
        id_usuario=datos.id_admin,
        accion="USUARIO_CREADO",
        detalle=f"Cuenta creada: {nuevo.nombre_usuario} ({rol_valido})",
    ))
    db.commit()
    return {"mensaje": "Usuario creado correctamente.", "id_usuario": nuevo.id_usuario}


@router.put("/usuarios/{id_usuario}")
def editar_usuario(id_usuario: int, datos: UsuarioEditarSchema, db: Session = Depends(get_db), admin: Usuario = Depends(requiere_admin)):
    datos.id_admin = admin.id_usuario
    usr = db.query(Usuario).filter(Usuario.id_usuario == id_usuario).first()
    if not usr:
        raise HTTPException(status_code=404, detail="Usuario no encontrado.")

    nombre = datos.nombre_usuario.strip()
    correo = datos.correo.strip().lower()
    if not nombre or not correo:
        raise HTTPException(status_code=400, detail="Nombre de usuario y correo son obligatorios.")
    _validar_correo(correo)

    dup_user = (
        db.query(Usuario)
        .filter(func.lower(Usuario.nombre_usuario) == nombre.lower(), Usuario.id_usuario != id_usuario)
        .first()
    )
    if dup_user:
        raise HTTPException(status_code=409, detail=f"El nombre de usuario «{nombre}» ya está en uso. Elige otro.")

    dup_mail = (
        db.query(Usuario)
        .filter(func.lower(Usuario.correo) == correo, Usuario.id_usuario != id_usuario)
        .first()
    )
    if dup_mail:
        raise HTTPException(status_code=409, detail=f"El correo {correo} ya está registrado en otra cuenta.")

    if datos.contrasena and datos.contrasena.strip():
        _validar_password_rf11(datos.contrasena.strip())
        usr.contrasena = hashear(datos.contrasena.strip())

    estado_anterior = usr.estado
    usr.nombre_usuario = nombre
    usr.correo = correo
    usr.rol = "Administrador" if datos.rol == "Administrador" else "Cajero"
    usr.estado = "Activo" if datos.estado == "Activo" else "Inactivo"

    accion = "USUARIO_DESACTIVADO" if (estado_anterior == "Activo" and usr.estado == "Inactivo") else "USUARIO_EDITADO"
    db.add(Bitacora(
        id_usuario=datos.id_admin,
        accion=accion,
        detalle=f"Usuario #{id_usuario} ({usr.nombre_usuario}) · Rol: {usr.rol} · Estado: {usr.estado}",
    ))
    db.commit()
    return {"mensaje": "Datos del usuario actualizados."}


# =========================================================
# 3. BITÁCORA DEL SISTEMA - SOLO LECTURA (RF 13)
# =========================================================
@router.get("/bitacora")
def consultar_bitacora(
    id_usuario: Optional[int] = None,
    fecha_inicio: Optional[date] = None,
    fecha_fin: Optional[date] = None,
    limite: int = 200,
    db: Session = Depends(get_db),
):
    consulta = db.query(Bitacora).order_by(Bitacora.fecha_hora.desc(), Bitacora.id_bitacora.desc())

    if id_usuario:
        consulta = consulta.filter(Bitacora.id_usuario == id_usuario)
    if fecha_inicio:
        consulta = consulta.filter(Bitacora.fecha_hora >= rango_utc(fecha_inicio)[0])
    if fecha_fin:
        consulta = consulta.filter(Bitacora.fecha_hora < rango_utc(fecha_fin)[1])

    registros = consulta.limit(min(max(limite, 1), 500)).all()
    salida = []
    for b in registros:
        usr = db.query(Usuario).filter(Usuario.id_usuario == b.id_usuario).first()
        salida.append({
            "id_bitacora": b.id_bitacora,
            "fecha": formato_local(b.fecha_hora, "%d %b %Y", "—"),
            "hora": formato_local(b.fecha_hora, "%H:%M:%S", "—"),
            "usuario": usr.nombre_usuario if usr else f"Usuario #{b.id_usuario}",
            "rol": usr.rol if usr else "—",
            "accion": b.accion,
            "detalle": b.detalle,
        })
    return {"registros": salida}


# =========================================================
# 4. RESPALDOS LOCALES DE BASE DE DATOS (RF 21)
# =========================================================
def _limpiar_respaldos_antiguos(dias_retencion: int = 30):
    limite = datetime.now().timestamp() - (dias_retencion * 86400)
    for archivo in CARPETA_BACKUPS.glob("respaldo_*.sql"):
        if archivo.stat().st_mtime < limite:
            archivo.unlink(missing_ok=True)


@router.get("/respaldos")
def listar_respaldos():
    _limpiar_respaldos_antiguos(30)
    archivos = sorted(CARPETA_BACKUPS.glob("respaldo_*.sql"), key=lambda p: p.stat().st_mtime, reverse=True)
    lista = []
    for idx, f in enumerate(archivos, start=1):
        stat = f.stat()
        dt = datetime.fromtimestamp(stat.st_mtime, ZONA_NEGOCIO)
        tam_kb = round(stat.st_size / 1024, 1)
        lista.append({
            "archivo": f.name,
            "folio": f"BKP-{idx:04d}",
            "fecha": dt.strftime("%d/%m/%Y %H:%M"),
            "tipo": "Manual de DB" if "_manual_" in f.name else "Automático Diario",
            "estado": "COMPLETADO",
            "ubicacion": f"Local ({f.name})",
            "tamano": f"{tam_kb} KB",
        })
    return {
        "estado_servidor": "ESTABLE",
        "ultimo_respaldo": lista[0]["fecha"] if lista else "Sin respaldos previos",
        "respaldos": lista,
    }


def _sql_valor(v) -> str:
    if v is None:
        return "NULL"
    if isinstance(v, bool):
        return "1" if v else "0"
    if isinstance(v, (int, float)):
        return str(v)
    esc = str(v).replace("\\", "\\\\").replace("'", "\\'")
    return f"'{esc}'"


def _volcado_mysql() -> list:
    lineas = ["SET FOREIGN_KEY_CHECKS=0;\n"]
    with engine.connect() as conn:
        tablas = [row[0] for row in conn.execute(text("SHOW TABLES")).fetchall()]
        for tabla in tablas:
            create_sql = conn.execute(text(f"SHOW CREATE TABLE `{tabla}`")).fetchone()[1]
            lineas.append(f"DROP TABLE IF EXISTS `{tabla}`;")
            lineas.append(f"{create_sql};\n")

            resultado = conn.execute(text(f"SELECT * FROM `{tabla}`"))
            nombres_cols = ", ".join(f"`{c}`" for c in resultado.keys())
            filas = resultado.fetchall()
            for fila in filas:
                vals = ", ".join(_sql_valor(v) for v in fila)
                lineas.append(f"INSERT INTO `{tabla}` ({nombres_cols}) VALUES ({vals});")
            if filas:
                lineas.append("")
    lineas.append("SET FOREIGN_KEY_CHECKS=1;\n")
    return lineas


def _volcado_sqlite() -> list:
    # sqlite3 trae su propio volcado SQL (esquema + datos) desde sqlite_master
    crudo = engine.raw_connection()
    try:
        return list(crudo.driver_connection.iterdump())
    finally:
        crudo.close()


def generar_respaldo(db: Session, tipo: str, id_usuario: int) -> dict:
    """RF 21: escribe backups/respaldo_<tipo>_<fecha>.sql. Funciona con MySQL y SQLite."""
    CARPETA_BACKUPS.mkdir(parents=True, exist_ok=True)
    ahora = ahora_local()
    nombre = f"respaldo_{tipo}_{ahora.strftime('%Y%m%d_%H%M%S')}.sql"
    ruta = CARPETA_BACKUPS / nombre

    motor = engine.dialect.name
    if motor == "mysql":
        cuerpo = _volcado_mysql()
    elif motor == "sqlite":
        cuerpo = _volcado_sqlite()
    else:
        raise HTTPException(status_code=500, detail=f"Respaldo no soportado para el motor {motor}.")

    lineas = [
        "-- Respaldo Local La Esquina del Cafe",
        f"-- Generado: {ahora.isoformat(timespec='seconds')}",
        f"-- Motor: {motor}\n",
        *cuerpo,
    ]
    ruta.write_text("\n".join(lineas), encoding="utf-8")
    _limpiar_respaldos_antiguos(30)

    db.add(Bitacora(
        id_usuario=id_usuario,
        accion="RESPALDO_DB",
        detalle=f"Copia de seguridad generada: {nombre}",
    ))
    db.commit()

    return {"mensaje": f"Respaldo generado correctamente: {nombre}", "archivo": nombre}


@router.post("/respaldos/ejecutar")
def ejecutar_respaldo_sql(tipo: str = "manual", db: Session = Depends(get_db), admin: Usuario = Depends(requiere_admin)):
    return generar_respaldo(db, tipo, admin.id_usuario)


@router.get("/respaldos/descargar/{nombre_archivo}")
def descargar_respaldo(nombre_archivo: str):
    if "/" in nombre_archivo or "\\" in nombre_archivo or not nombre_archivo.endswith(".sql"):
        raise HTTPException(status_code=400, detail="Nombre de archivo no válido.")
    ruta = CARPETA_BACKUPS / nombre_archivo
    if not ruta.exists():
        raise HTTPException(status_code=404, detail="Archivo de respaldo no encontrado.")
    return Response(
        content=ruta.read_bytes(),
        media_type="application/sql",
        headers={"Content-Disposition": f'attachment; filename="{nombre_archivo}"'},
    )