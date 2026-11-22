"""
Zona horaria del negocio: el único lugar donde se define.

Convención:
  - En la base de datos todas las fechas-hora se guardan en UTC, sin zona
    (naive). Así SQLite (CURRENT_TIMESTAMP = UTC) y MySQL (sesión en +00:00,
    ver database.py) guardan lo mismo, sin importar la zona del servidor.
  - Todo lo que es "de calendario" (hoy, un día del filtro, vence hoy/mañana)
    se calcula en la zona del negocio y se convierte a UTC para comparar.
  - Lo que regresa el API se convierte a la zona del negocio.

Zona configurable con la variable de entorno TZ_NEGOCIO (por omisión
America/Mexico_City).
"""
import os
from datetime import date, datetime, time, timedelta, timezone
from typing import Optional, Tuple
from zoneinfo import ZoneInfo

NOMBRE_ZONA = os.getenv("TZ_NEGOCIO", "America/Mexico_City")
ZONA_NEGOCIO = ZoneInfo(NOMBRE_ZONA)


def _reloj() -> datetime:
    """Hora actual en UTC (aware). Las pruebas lo reemplazan para simular una hora."""
    return datetime.now(timezone.utc)


def ahora_utc() -> datetime:
    """Para guardar en la BD: UTC sin zona."""
    return _reloj().replace(tzinfo=None)


def ahora_local() -> datetime:
    return _reloj().astimezone(ZONA_NEGOCIO)


def hoy_local() -> date:
    """Fecha de calendario en el negocio (no la del servidor)."""
    return ahora_local().date()


def a_utc_naive(dt_local: datetime) -> datetime:
    """Fecha-hora local del negocio (naive o aware) -> UTC naive para comparar en la BD."""
    if dt_local.tzinfo is None:
        dt_local = dt_local.replace(tzinfo=ZONA_NEGOCIO)
    return dt_local.astimezone(timezone.utc).replace(tzinfo=None)


def rango_utc(dia_inicio: date, dia_fin: Optional[date] = None) -> Tuple[datetime, datetime]:
    """
    Días de calendario del negocio [dia_inicio, dia_fin] como rango UTC semiabierto
    [inicio, fin). Usar:  columna >= inicio  y  columna < fin.
    """
    dia_fin = dia_fin or dia_inicio
    inicio = a_utc_naive(datetime.combine(dia_inicio, time.min))
    fin = a_utc_naive(datetime.combine(dia_fin + timedelta(days=1), time.min))
    return inicio, fin


def a_local(dt: Optional[datetime]) -> Optional[datetime]:
    """Fecha-hora guardada (UTC naive) -> zona del negocio (aware)."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(ZONA_NEGOCIO)


def iso_local(dt: Optional[datetime]) -> Optional[str]:
    """ISO 8601 con desfase, p. ej. 2026-11-21T23:30:00-06:00."""
    local = a_local(dt)
    return local.isoformat(timespec="seconds") if local else None


def formato_local(dt: Optional[datetime], formato: str, vacio: str = "") -> str:
    local = a_local(dt)
    return local.strftime(formato) if local else vacio
