import csv
import io
import os
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, text
from sqlalchemy.orm import Session

from database import get_db, engine
from services.contrasenas import hashear
from services.sesion import requiere_admin
from services.tiempo import ZONA_NEGOCIO, ahora_local, formato_local, hoy_local, rango_utc
from models import (
    Usuario,
    Insumo,
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
# HELPER: GENERADOR PDF NATIVO (100% LOCAL, SIN DEPENDENCIAS)
# =========================================================
def _escapar_pdf(texto: str) -> str:
    limpio = (
        str(texto)
        .replace("á", "a").replace("é", "e").replace("í", "i").replace("ó", "o").replace("ú", "u")
        .replace("Á", "A").replace("É", "E").replace("Í", "I").replace("Ó", "O").replace("Ú", "U")
        .replace("ñ", "n").replace("Ñ", "N").replace("·", "-")
    )
    return limpio.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def generar_pdf_tabla(titulo: str, subtitulo: str, columnas: list, filas: list) -> bytes:
    lineas_por_pagina = 38
    paginas_datos = [filas[i:i + lineas_por_pagina] for i in range(0, max(len(filas), 1), lineas_por_pagina)]

    objetos = []
    # 1: Catalog, 2: Pages, 3: Font Regular, 4: Font Bold
    objetos.append("<< /Type /Catalog /Pages 2 0 R >>")
    objetos.append("")  # placeholder Pages
    objetos.append("<< /Type /Font /Subtype /Type1 /BaseFont /Courier >>")
    objetos.append("<< /Type /Font /Subtype /Type1 /BaseFont /Courier-Bold >>")

    ids_paginas = []
    next_id = 5

    for idx_pag, bloque in enumerate(paginas_datos, start=1):
        comandos = [
            "BT",
            "/F2 14 Tf",
            "40 755 Td",
            f"({_escapar_pdf(titulo)}) Tj",
            "/F1 9 Tf",
            "0 -16 Td",
            f"({_escapar_pdf(subtitulo)} | Pagina {idx_pag}/{len(paginas_datos)}) Tj",
            "0 -22 Td",
            "/F2 9 Tf",
            f"({_escapar_pdf(' | '.join(columnas))}) Tj",
            "0 -12 Td",
            f"({'-' * 92}) Tj",
            "/F1 9 Tf",
        ]
        for fila in bloque:
            linea = " | ".join(str(c) for c in fila)[:95]
            comandos.append("0 -14 Td")
            comandos.append(f"({_escapar_pdf(linea)}) Tj")
        comandos.append("ET")

        stream_bytes = "\n".join(comandos).encode("latin-1", errors="replace")
        id_contenido = next_id
        id_pagina = next_id + 1
        next_id += 2

        objetos.append(f"<< /Length {len(stream_bytes)} >>\nstream\n{stream_bytes.decode('latin-1')}\nendstream")
        objetos.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            f"/Resources << /Font << /F1 3 0 R /F2 4 0 R >> >> /Contents {id_contenido} 0 R >>"
        )
        ids_paginas.append(f"{id_pagina} 0 R")

    objetos[1] = f"<< /Type /Pages /Kids [{' '.join(ids_paginas)}] /Count {len(ids_paginas)} >>"

    salida = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for num, contenido in enumerate(objetos, start=1):
        offsets.append(len(salida))
        salida.extend(f"{num} 0 obj\n{contenido}\nendobj\n".encode("latin-1"))

    pos_xref = len(salida)
    salida.extend(f"xref\n0 {len(objetos) + 1}\n".encode("latin-1"))
    salida.extend(b"0000000000 65535 f \n")
    for off in offsets[1:]:
        salida.extend(f"{off:010d} 00000 n \n".encode("latin-1"))

    salida.extend(
        f"trailer\n<< /Size {len(objetos) + 1} /Root 1 0 R >>\nstartxref\n{pos_xref}\n%%EOF".encode("latin-1")
    )
    return bytes(salida)


# =========================================================
# 1. REPORTES EXPORTABLES (RF 12)
# =========================================================
def _construir_datos_reporte(tipo: str, fecha_inicio: date, fecha_fin: date, db: Session) -> dict:
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
            dia_str = formato_local(v.fecha_emision_ticket, "%Y-%m-%d")
            if dia_str not in por_dia:
                por_dia[dia_str] = {"completadas": 0, "brutas": 0.0, "cancelaciones": 0.0}
            monto = float(v.total)
            por_dia[dia_str]["brutas"] += monto
            if (v.estado or "").lower() == "cancelada":
                por_dia[dia_str]["cancelaciones"] += monto
            else:
                por_dia[dia_str]["completadas"] += 1

        filas = []
        tot_comp, tot_brutas, tot_canc, tot_netas = 0, 0.0, 0.0, 0.0
        for dia, d in sorted(por_dia.items()):
            netas = d["brutas"] - d["cancelaciones"]
            tot_comp += d["completadas"]
            tot_brutas += d["brutas"]
            tot_canc += d["cancelaciones"]
            tot_netas += netas
            filas.append([
                dia,
                d["completadas"],
                f"${d['brutas']:,.2f}",
                f"-${d['cancelaciones']:,.2f}",
                f"${netas:,.2f}",
            ])

        return {
            "titulo": "Reporte de Ventas Netas",
            "columnas": ["Fecha", "Completadas", "Ventas Brutas", "Cancelaciones", "Ventas Netas"],
            "filas": filas,
            "resumen": {
                "completadas": tot_comp,
                "brutas": round(tot_brutas, 2),
                "cancelaciones": round(tot_canc, 2),
                "netas": round(tot_netas, 2),
            },
        }

    elif tipo == "consumo":
        movs = (
            db.query(MovimientoInventario)
            .filter(
                MovimientoInventario.tipo_movimiento == "SALIDA_VENTA",
                MovimientoInventario.fecha_movimiento >= inicio_dt,
                MovimientoInventario.fecha_movimiento < fin_dt,
            )
            .all()
        )
        acumulado = {}
        for m in movs:
            acumulado[m.id_insumo] = acumulado.get(m.id_insumo, 0.0) + float(m.cantidad)

        filas = []
        for id_ins, cant in sorted(acumulado.items(), key=lambda x: x[1], reverse=True):
            ins = db.query(Insumo).filter(Insumo.id_insumo == id_ins).first()
            filas.append([
                ins.nombre if ins else f"Insumo #{id_ins}",
                ins.categoria if ins else "—",
                f"{cant:,.2f}",
                ins.unidad_medida if ins else "",
            ])
        return {
            "titulo": "Reporte de Consumo de Insumos",
            "columnas": ["Insumo", "Categoria", "Cantidad Consumida", "Unidad"],
            "filas": filas,
            "resumen": {"insumos_distintos": len(filas)},
        }

    elif tipo == "mermas":
        mermas = (
            db.query(Merma)
            .filter(Merma.fecha >= inicio_dt, Merma.fecha < fin_dt)
            .order_by(Merma.fecha.desc())
            .all()
        )
        filas = []
        total_perdida = 0.0
        for m in mermas:
            ins = db.query(Insumo).filter(Insumo.id_insumo == m.id_insumo).first()
            costo = float(m.costo_perdida)
            total_perdida += costo
            filas.append([
                formato_local(m.fecha, "%Y-%m-%d %H:%M"),
                ins.nombre if ins else f"Insumo #{m.id_insumo}",
                f"{float(m.cantidad):g} {ins.unidad_medida if ins else ''}",
                m.motivo,
                f"${costo:,.2f}",
            ])
        return {
            "titulo": "Reporte de Mermas",
            "columnas": ["Fecha", "Insumo", "Cantidad", "Motivo", "Costo Perdida"],
            "filas": filas,
            "resumen": {"registros": len(filas), "costo_total": round(total_perdida, 2)},
        }

    raise HTTPException(status_code=400, detail="Tipo de reporte no válido (ventas, consumo, mermas).")


@router.get("/reportes")
def consultar_reporte(
    tipo: str = "ventas",
    fecha_inicio: Optional[date] = None,
    fecha_fin: Optional[date] = None,
    db: Session = Depends(get_db),
):
    hoy = hoy_local()
    f_fin = fecha_fin or hoy
    f_ini = fecha_inicio or (f_fin - timedelta(days=30))
    datos = _construir_datos_reporte(tipo, f_ini, f_fin, db)
    datos["periodo"] = f"{f_ini} a {f_fin}"
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
    id_usuario = admin.id_usuario
    hoy = hoy_local()
    f_fin = fecha_fin or hoy
    f_ini = fecha_inicio or (f_fin - timedelta(days=30))
    datos = _construir_datos_reporte(tipo, f_ini, f_fin, db)

    db.add(Bitacora(
        id_usuario=id_usuario,
        accion="REPORTE_GENERADO",
        detalle=f"{datos['titulo']} · {f_ini} a {f_fin} · {formato.upper()}",
    ))
    db.commit()

    nombre_archivo = f"reporte_{tipo}_{f_ini}_{f_fin}.{formato.lower()}"

    if formato.lower() == "csv":
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow([datos["titulo"], f"Periodo: {f_ini} a {f_fin}"])
        writer.writerow([])
        writer.writerow(datos["columnas"])
        for fila in datos["filas"]:
            writer.writerow(fila)

        contenido = "\ufeff" + buffer.getvalue()
        return Response(
            content=contenido.encode("utf-8"),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{nombre_archivo}"'},
        )

    elif formato.lower() == "pdf":
        pdf_bytes = generar_pdf_tabla(
            titulo=f"La Esquina del Cafe - {datos['titulo']}",
            subtitulo=f"Periodo: {f_ini} al {f_fin}",
            columnas=datos["columnas"],
            filas=datos["filas"] or [["Sin registros en el periodo seleccionado"]],
        )
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{nombre_archivo}"'},
        )

    raise HTTPException(status_code=400, detail="Formato no soportado. Usa csv o pdf.")


# =========================================================
# 2. GESTIÓN DE USUARIOS (RF 1, RF 1.1, RF 14)
# =========================================================
def _validar_password_rf11(pwd: str):
    if len(pwd) < 8 or not any(c.isalpha() for c in pwd) or not any(c.isdigit() for c in pwd):
        raise HTTPException(
            status_code=400,
            detail="La contraseña debe ser alfanumérica (letras y números) y tener al menos 8 caracteres.",
        )


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

    _validar_password_rf11(datos.contrasena)

    if db.query(Usuario).filter(func.lower(Usuario.nombre_usuario) == nombre.lower()).first():
        raise HTTPException(status_code=400, detail="El nombre de usuario ya está en uso.")
    if db.query(Usuario).filter(func.lower(Usuario.correo) == correo).first():
        raise HTTPException(status_code=400, detail="El correo electrónico ya está registrado.")

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

    dup_user = (
        db.query(Usuario)
        .filter(func.lower(Usuario.nombre_usuario) == nombre.lower(), Usuario.id_usuario != id_usuario)
        .first()
    )
    if dup_user:
        raise HTTPException(status_code=400, detail="Otro usuario ya tiene ese nombre.")

    dup_mail = (
        db.query(Usuario)
        .filter(func.lower(Usuario.correo) == correo, Usuario.id_usuario != id_usuario)
        .first()
    )
    if dup_mail:
        raise HTTPException(status_code=400, detail="Otro usuario ya usa ese correo.")

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