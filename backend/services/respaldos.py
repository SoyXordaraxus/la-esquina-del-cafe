"""
Respaldos de la base de datos (RF 21).

  - generar_respaldo(): volcado .sql en backups/ (MySQL o SQLite), copia a la unidad
    externa si está configurada y retención de 30 días en ambas carpetas.
  - Respaldo diario programado: un hilo daemon revisa cada minuto si ya pasó la
    hora HORA_RESPALDO (hora del negocio, services/tiempo.py) y si aún no existe
    el respaldo "diario" de hoy. La misma revisión, hecha al arrancar, cubre la
    recuperación (la laptop estaba apagada a la hora programada).
  - No se duplica el diario aunque haya varios procesos (uvicorn --reload,
    reinicios): se verifica por nombre (respaldo_diario_AAAAMMDD_*.sql) dentro de
    un candado de hilo + candado de archivo (backups/.respaldo_diario.lock).

Variables de entorno (se leen en cada uso):
  HORA_RESPALDO          HH:MM, hora del negocio. Por omisión 23:00.
  RUTA_RESPALDO_EXTERNO  Carpeta de la unidad externa (debe existir), p. ej.
                         E:\\RespaldosCafe o /media/usb/respaldos.
"""
import logging
import os
import re
import shutil
import threading
import time as _time
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import func, text
from sqlalchemy.orm import Session

from database import SessionLocal, engine
from models import Usuario
from services import tiempo
from services.bitacora import registrar_bitacora

logger = logging.getLogger("esquina.respaldos")

CARPETA_BACKUPS = Path(__file__).resolve().parent.parent / "backups"
DIAS_RETENCION = 30
HORA_POR_OMISION = "23:00"
TIPOS = {"manual", "diario", "auto_cierre"}
ETIQUETAS_TIPO = {
    "manual": "Manual",
    "diario": "Automático diario",
    "auto_cierre": "Al cerrar el sistema",
}
PATRON_NOMBRE = re.compile(r"^respaldo_(?P<tipo>.+)_(?P<fecha>\d{8})_(?P<hora>\d{6})\.sql$")
INTERVALO_REVISION = 60          # segundos entre revisiones del hilo
CANDADO_VENCIDO = 15 * 60        # un candado de archivo más viejo se considera abandonado

_candado_hilo = threading.Lock()
_detener = threading.Event()
_hilo: Optional[threading.Thread] = None


# ---------------------------------------------------------
# Configuración
# ---------------------------------------------------------
def hora_programada() -> time:
    valor = (os.getenv("HORA_RESPALDO") or HORA_POR_OMISION).strip()
    try:
        return datetime.strptime(valor, "%H:%M").time()
    except ValueError:
        logger.warning("HORA_RESPALDO=%r no es válida (formato HH:MM); se usa %s.", valor, HORA_POR_OMISION)
        return datetime.strptime(HORA_POR_OMISION, "%H:%M").time()


def carpeta_externa() -> Optional[Path]:
    """Ruta configurada (exista o no) o None si no hay RUTA_RESPALDO_EXTERNO."""
    valor = (os.getenv("RUTA_RESPALDO_EXTERNO") or "").strip()
    return Path(valor) if valor else None


def estado_externa() -> dict:
    """estado: 'conectada' | 'no_configurada' | 'no_disponible'."""
    ruta = carpeta_externa()
    if ruta is None:
        return {"estado": "no_configurada", "ruta": None, "texto": "No configurada"}
    if ruta.is_dir():
        return {"estado": "conectada", "ruta": str(ruta), "texto": f"Conectada: {ruta}"}
    return {"estado": "no_disponible", "ruta": str(ruta), "texto": "No disponible"}


def primer_admin(db: Session) -> Optional[Usuario]:
    return (
        db.query(Usuario)
        .filter(func.lower(Usuario.rol).like("%admin%"))
        .order_by(Usuario.id_usuario.asc())
        .first()
    )


# ---------------------------------------------------------
# Nombres, listado y retención
# ---------------------------------------------------------
def info_nombre(nombre: str) -> Optional[dict]:
    """respaldo_<tipo>_<AAAAMMDD>_<HHMMSS>.sql -> {tipo, fecha (hora del negocio)}."""
    m = PATRON_NOMBRE.match(nombre)
    if not m:
        return None
    try:
        fecha = datetime.strptime(m["fecha"] + m["hora"], "%Y%m%d%H%M%S")
    except ValueError:
        return None
    return {"tipo": m["tipo"], "fecha": fecha}


def etiqueta_tipo(tipo: str) -> str:
    return ETIQUETAS_TIPO.get(tipo, tipo.replace("_", " ").capitalize())


def archivos_locales() -> list:
    """Respaldos locales, del más reciente al más antiguo."""
    if not CARPETA_BACKUPS.is_dir():
        return []

    def clave(p: Path):
        info = info_nombre(p.name)
        return info["fecha"].timestamp() if info else p.stat().st_mtime

    return sorted(CARPETA_BACKUPS.glob("respaldo_*.sql"), key=clave, reverse=True)


def limpiar_antiguos(carpeta: Path, dias: int = DIAS_RETENCION) -> int:
    """Borra respaldo_*.sql con más de `dias` días (por fecha de modificación)."""
    if carpeta is None or not carpeta.is_dir():
        return 0
    limite = tiempo._reloj().timestamp() - dias * 86400
    borrados = 0
    for archivo in carpeta.glob("respaldo_*.sql"):
        try:
            if archivo.stat().st_mtime < limite:
                archivo.unlink(missing_ok=True)
                borrados += 1
        except OSError:
            logger.warning("No se pudo revisar/borrar el respaldo antiguo %s", archivo)
    return borrados


def esta_en_externa(nombre: str) -> bool:
    ext = estado_externa()
    return ext["estado"] == "conectada" and (Path(ext["ruta"]) / nombre).is_file()


def diario_de(dia: date) -> Optional[Path]:
    """Respaldo diario ya generado ese día (fecha del negocio), si existe."""
    if not CARPETA_BACKUPS.is_dir():
        return None
    encontrados = sorted(CARPETA_BACKUPS.glob(f"respaldo_diario_{dia.strftime('%Y%m%d')}_*.sql"))
    return encontrados[-1] if encontrados else None


def ultimo_diario() -> Optional[Path]:
    for p in archivos_locales():
        info = info_nombre(p.name)
        if info and info["tipo"] == "diario":
            return p
    return None


def proximo_respaldo(ahora: Optional[datetime] = None) -> datetime:
    """Siguiente ejecución del diario (hora del negocio, naive)."""
    ahora = (ahora or tiempo.ahora_local()).replace(tzinfo=None)
    hoy_programado = datetime.combine(ahora.date(), hora_programada())
    if ahora < hoy_programado:
        return hoy_programado
    if diario_de(ahora.date()) is not None:
        return hoy_programado + timedelta(days=1)
    return ahora.replace(second=0, microsecond=0)   # vencido: se ejecuta en la siguiente revisión


# ---------------------------------------------------------
# Generación
# ---------------------------------------------------------
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


def _copiar_a_externa(ruta: Path) -> dict:
    """Copia el respaldo a la unidad externa. Nunca lanza excepción."""
    ext = estado_externa()
    if ext["estado"] == "no_configurada":
        logger.info("Respaldo %s solo local: RUTA_RESPALDO_EXTERNO no está configurada.", ruta.name)
        return {"externo": False, "aviso": "Unidad externa no configurada: el respaldo quedó solo en local."}
    if ext["estado"] == "no_disponible":
        aviso = f"Unidad externa no disponible ({ext['ruta']}): el respaldo quedó solo en local."
        logger.warning(aviso)
        return {"externo": False, "aviso": aviso, "registrar": True}
    destino = Path(ext["ruta"])
    try:
        shutil.copy2(ruta, destino / ruta.name)   # copy2 conserva la fecha (retención)
        limpiar_antiguos(destino)
        return {"externo": True, "aviso": None}
    except OSError as e:
        aviso = f"No se pudo copiar a la unidad externa ({destino}): {e}"
        logger.warning(aviso)
        return {"externo": False, "aviso": aviso[:255], "registrar": True}


def generar_respaldo(db: Session, tipo: str, id_usuario: int) -> dict:
    """Escribe backups/respaldo_<tipo>_<fecha>.sql, lo copia a la unidad externa y aplica la retención."""
    if tipo not in TIPOS:
        raise HTTPException(status_code=400, detail=f"Tipo de respaldo no válido: {tipo}.")
    CARPETA_BACKUPS.mkdir(parents=True, exist_ok=True)
    ahora = tiempo.ahora_local()
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
        f"-- Tipo: {tipo}",
        f"-- Motor: {motor}\n",
        *cuerpo,
    ]
    ruta.write_text("\n".join(lineas), encoding="utf-8")
    limpiar_antiguos(CARPETA_BACKUPS)

    copia = _copiar_a_externa(ruta)
    ubicacion = "local + externa" if copia["externo"] else "solo local"
    registrar_bitacora(db, id_usuario, "RESPALDO_DB", f"Copia de seguridad generada ({ubicacion}): {nombre}")
    if copia.get("registrar"):
        registrar_bitacora(db, id_usuario, "RESPALDO_EXTERNO", copia["aviso"])
    db.commit()

    mensaje = f"Respaldo generado correctamente: {nombre}"
    if copia["externo"]:
        mensaje += " (copiado también a la unidad externa)"
    return {"mensaje": mensaje, "archivo": nombre, "externo": copia["externo"],
            "aviso_externo": copia["aviso"], "falla_externa": bool(copia.get("registrar"))}


# ---------------------------------------------------------
# Respaldo diario programado
# ---------------------------------------------------------
class _CandadoArchivo:
    """Candado entre procesos: crear el archivo con O_EXCL. Sin dependencias."""

    def __init__(self, ruta: Path):
        self.ruta = ruta
        self.tomado = False

    def __enter__(self):
        self.ruta.parent.mkdir(parents=True, exist_ok=True)
        for _ in range(2):
            try:
                fd = os.open(self.ruta, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(fd, str(os.getpid()).encode())
                os.close(fd)
                self.tomado = True
                break
            except FileExistsError:
                try:
                    if _time.time() - self.ruta.stat().st_mtime > CANDADO_VENCIDO:
                        self.ruta.unlink(missing_ok=True)   # abandonado (proceso que murió)
                        continue
                except FileNotFoundError:
                    continue
                break
        return self

    def __exit__(self, *exc):
        if self.tomado:
            self.ruta.unlink(missing_ok=True)
        return False


def revisar_respaldo_diario() -> Optional[str]:
    """
    Si ya pasó la hora programada de hoy (hora del negocio) y no existe el diario
    de hoy, lo genera. Regresa el nombre del archivo generado o None.
    Nunca lanza excepción: los errores van al log y a la bitácora.
    """
    ahora = tiempo.ahora_local().replace(tzinfo=None)
    hoy = ahora.date()
    if ahora < datetime.combine(hoy, hora_programada()) or diario_de(hoy) is not None:
        return None

    with _candado_hilo, _CandadoArchivo(CARPETA_BACKUPS / ".respaldo_diario.lock") as candado:
        if not candado.tomado:
            logger.info("Otro proceso está generando el respaldo diario; se omite.")
            return None
        if diario_de(hoy) is not None:      # otro proceso lo terminó mientras esperábamos
            return None

        db = SessionLocal()
        admin_id = None
        try:
            admin = primer_admin(db)
            if admin is None:
                logger.warning("Respaldo diario omitido: no existe ningún usuario Administrador.")
                return None
            admin_id = admin.id_usuario
            resultado = generar_respaldo(db, tipo="diario", id_usuario=admin_id)
            logger.info("Respaldo diario: %s", resultado["archivo"])
            return resultado["archivo"]
        except Exception as e:
            logger.exception("No se pudo generar el respaldo diario")
            try:
                db.rollback()
                if admin_id is not None:
                    detalle = e.detail if isinstance(e, HTTPException) else str(e)
                    registrar_bitacora(db, admin_id, "RESPALDO_DIARIO_ERROR", f"Falló el respaldo diario: {detalle}")
                    db.commit()
            except Exception:
                logger.exception("Tampoco se pudo registrar la falla del respaldo diario en la bitácora")
            return None
        finally:
            db.close()


def _ciclo():
    while not _detener.is_set():
        try:
            revisar_respaldo_diario()
        except Exception:      # revisar_respaldo_diario ya atrapa todo; esto es por si acaso
            logger.exception("Error inesperado en el programador de respaldos")
        _detener.wait(INTERVALO_REVISION)


def iniciar_programador() -> None:
    """Arranca el hilo daemon (una vez por proceso). La primera revisión es inmediata (recuperación)."""
    global _hilo
    if _hilo is not None and _hilo.is_alive():
        return
    _detener.clear()
    _hilo = threading.Thread(target=_ciclo, name="respaldo-diario", daemon=True)
    _hilo.start()
    logger.info("Respaldo diario programado a las %s (%s).", hora_programada().strftime("%H:%M"), tiempo.NOMBRE_ZONA)


def detener_programador() -> None:
    _detener.set()
