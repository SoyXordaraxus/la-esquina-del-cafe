"""
Prueba de respaldos (RF 21): diario programado, recuperación al arrancar, sin
duplicados, copia a unidad externa, retención de 30 días, unidad no disponible,
etiquetas de tipo y endpoint de estado.

Uso (desde backend/):
    python3 pruebas/prueba_respaldos.py                 # SQLite temporal
    DATABASE_URL=mysql+pymysql://... python3 pruebas/prueba_respaldos.py   # base MySQL VACÍA

No espera horas reales: congela el reloj de services/tiempo.py (como
prueba_zona_horaria.py) y usa carpetas temporales para backups/ y la unidad externa.
"""
import os
import sys
import tempfile
import threading
import time as _time
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
TMP = Path(tempfile.mkdtemp(prefix="prueba_respaldos_"))
if not os.getenv("DATABASE_URL"):
    os.environ["DATABASE_URL"] = f"sqlite:///{TMP}/prueba_respaldos.db"
os.environ.setdefault("TZ_NEGOCIO", "America/Mexico_City")
os.environ.pop("RUTA_RESPALDO_EXTERNO", None)
os.environ["HORA_RESPALDO"] = "23:00"

from fastapi.testclient import TestClient  # noqa: E402

import seed  # noqa: E402
from database import SessionLocal, engine  # noqa: E402
from main import app  # noqa: E402
from models import Bitacora  # noqa: E402
from services import respaldos, tiempo  # noqa: E402

LOCAL = TMP / "backups"
EXTERNA = TMP / "usb" / "RespaldosCafe"
respaldos.CARPETA_BACKUPS = LOCAL          # nunca toca backend/backups real
fallas = []


def ok(cond, msg):
    print(("  OK    " if cond else "  FALLA ") + msg)
    if not cond:
        fallas.append(msg)


# Día base = hoy en México (real), para que la retención por fecha de archivo sea coherente.
DIA0 = datetime.now(tiempo.ZONA_NEGOCIO).date()


def poner_reloj(dias: int, hhmm: str):
    """Congela el reloj en DIA0 + dias a la hora hhmm (hora de México)."""
    h, m = map(int, hhmm.split(":"))
    local = datetime(DIA0.year, DIA0.month, DIA0.day, h, m, tzinfo=tiempo.ZONA_NEGOCIO) + timedelta(days=dias)
    # sumar días en hora local (aunque hubiera cambio de horario)
    local = datetime.combine(local.date(), local.time(), tzinfo=tiempo.ZONA_NEGOCIO)
    utc = local.astimezone(timezone.utc)
    tiempo._reloj = lambda: utc
    return local


def diarios():
    return sorted(p.name for p in LOCAL.glob("respaldo_diario_*.sql"))


def de_tipo(tipo, carpeta=LOCAL):
    return sorted(p.name for p in carpeta.glob(f"respaldo_{tipo}_*.sql"))


def bitacora(accion):
    db = SessionLocal()
    try:
        return [b.detalle for b in db.query(Bitacora).filter(Bitacora.accion == accion).order_by(Bitacora.id_bitacora)]
    finally:
        db.close()


def esperar(cond, segundos=10):
    fin = _time.time() + segundos
    while _time.time() < fin:
        if cond():
            return True
        _time.sleep(0.05)
    return cond()


poner_reloj(0, "12:00")
seed.poblar_base()
c = TestClient(app)
admin = c.post("/api/auth/login", json={"usuario": "admin@esquinadelcafe.mx", "contrasena": "admin123"}).json()
cajero = c.post("/api/auth/login", json={"usuario": "Osvaldo Vazquez", "contrasena": "cajero123"}).json()
A = {"Authorization": f"Bearer {admin['token']}"}
K = {"Authorization": f"Bearer {cajero['token']}"}
print(f"Motor: {engine.dialect.name} · zona {tiempo.NOMBRE_ZONA} · día base {DIA0}")

# ---------------------------------------------------------------
print("== Configuración HORA_RESPALDO")
ok(respaldos.hora_programada().strftime("%H:%M") == "23:00", "HORA_RESPALDO=23:00")
os.environ["HORA_RESPALDO"] = "25:99"
ok(respaldos.hora_programada().strftime("%H:%M") == "23:00", "HORA_RESPALDO inválida -> 23:00 por omisión")
del os.environ["HORA_RESPALDO"]
ok(respaldos.hora_programada().strftime("%H:%M") == "23:00", "sin HORA_RESPALDO -> 23:00")
os.environ["HORA_RESPALDO"] = "23:00"

# ---------------------------------------------------------------
print("== Diario a la hora programada")
poner_reloj(0, "22:59")
ok(respaldos.revisar_respaldo_diario() is None and diarios() == [], "22:59: todavía no se genera")
est = c.get("/api/admin/respaldos/estado", headers=A).json()
ok(est["proximo_respaldo"] == f"{DIA0:%d/%m/%Y} 23:00", f"estado: próximo = hoy 23:00 ({est['proximo_respaldo']})")
ok(est["ultimo_diario"] is None, "estado: aún no hay último diario")

poner_reloj(0, "23:00")
generado = respaldos.revisar_respaldo_diario()
ok(generado == f"respaldo_diario_{DIA0:%Y%m%d}_230000.sql", f"23:00: se genera {generado}")
ok(diarios() == [generado], "existe un solo diario")
ok(any(generado in d for d in bitacora("RESPALDO_DB")), "queda en la bitácora (RESPALDO_DB)")

poner_reloj(0, "23:30")
ok(respaldos.revisar_respaldo_diario() is None and len(diarios()) == 1, "23:30: no se duplica el mismo día")
est = c.get("/api/admin/respaldos/estado", headers=A).json()
manana = DIA0 + timedelta(days=1)
ok(est["proximo_respaldo"] == f"{manana:%d/%m/%Y} 23:00", f"estado: próximo = mañana 23:00 ({est['proximo_respaldo']})")
ok(est["ultimo_diario"] == f"{DIA0:%d/%m/%Y} 23:00", f"estado: último diario = {est['ultimo_diario']}")
ok(est["hora_programada"] == "23:00" and est["proximo_pendiente"] is False, "estado: hora programada 23:00")

# ---------------------------------------------------------------
print("== Hilo programador: se ejecuta solo al llegar la hora")
respaldos.INTERVALO_REVISION = 0.05
poner_reloj(1, "22:00")
respaldos.iniciar_programador()
_time.sleep(0.3)
ok(len(diarios()) == 1, "día+1 22:00: el hilo no genera antes de la hora")
poner_reloj(1, "23:00")
ok(esperar(lambda: len(diarios()) == 2), "día+1 23:00: el hilo genera el diario")
_time.sleep(0.3)
ok(len(diarios()) == 2, "el hilo sigue revisando y no duplica")
respaldos.detener_programador()
respaldos._hilo.join(2)
ok(not respaldos._hilo.is_alive(), "detener_programador() termina el hilo")

# ---------------------------------------------------------------
print("== Sin duplicados con varios procesos/hilos a la vez")
poner_reloj(2, "23:10")
hilos = [threading.Thread(target=respaldos.revisar_respaldo_diario) for _ in range(8)]
for h in hilos:
    h.start()
for h in hilos:
    h.join()
ok(len(de_tipo("diario")) == 3 and len(respaldos.diario_de(poner_reloj(2, "23:10").date()).name) > 0,
   f"8 revisiones simultáneas -> un solo diario del día+2 ({len(diarios())} en total)")

poner_reloj(3, "23:10")
candado = LOCAL / ".respaldo_diario.lock"
candado.write_text("99999")                       # otro proceso (p. ej. --reload) lo tiene
ok(respaldos.revisar_respaldo_diario() is None and len(diarios()) == 3, "candado de otro proceso: se omite")
viejo = _time.time() - respaldos.CANDADO_VENCIDO - 60
os.utime(candado, (viejo, viejo))                 # proceso que murió hace mucho
ok(respaldos.revisar_respaldo_diario() is not None and len(diarios()) == 4, "candado abandonado: se recupera y genera")
ok(not candado.exists(), "el candado se libera al terminar")

# ---------------------------------------------------------------
print("== Recuperación al arrancar (laptop apagada a la hora programada)")
poner_reloj(4, "08:00")
os.environ["HORA_RESPALDO"] = "07:00"
cierres_antes = len(de_tipo("auto_cierre"))
with TestClient(app):                              # startup -> hilo -> revisión inmediata
    ok(esperar(lambda: len(diarios()) == 5), "arranque a las 08:00 (programado 07:00): genera el diario al iniciar")
ok(diarios()[-1].endswith("_080000.sql"), f"el diario de recuperación es de la hora de arranque ({diarios()[-1]})")
ok(len(de_tipo("auto_cierre")) == cierres_antes + 1, "al cerrar (shutdown) se genera respaldo auto_cierre")

with TestClient(app):                              # reinicio el mismo día: no duplica
    _time.sleep(0.3)
ok(len(diarios()) == 5, "reinicio el mismo día: no duplica el diario")

poner_reloj(5, "06:00")
with TestClient(app):                              # arranca antes de la hora: no genera
    _time.sleep(0.3)
ok(len(diarios()) == 5, "arranque antes de la hora programada: no genera")
respaldos.detener_programador()
os.environ["HORA_RESPALDO"] = "23:00"

# ---------------------------------------------------------------
print("== Unidad externa no configurada")
poner_reloj(6, "10:00")
est = c.get("/api/admin/respaldos/estado", headers=A).json()
ok(est["unidad_externa"]["estado"] == "no_configurada" and est["unidad_externa"]["texto"] == "No configurada",
   "estado: No configurada")
r = c.post("/api/admin/respaldos/ejecutar?tipo=manual", headers=A)
ok(r.status_code == 200 and r.json()["externo"] is False and r.json()["falla_externa"] is False,
   f"respaldo manual solo local -> {r.status_code}")
ok((LOCAL / r.json()["archivo"]).is_file(), "el archivo local existe")
ok(any("solo local" in d and r.json()["archivo"] in d for d in bitacora("RESPALDO_DB")), "bitácora indica 'solo local'")

# ---------------------------------------------------------------
print("== Unidad externa no disponible (no truena)")
os.environ["RUTA_RESPALDO_EXTERNO"] = str(TMP / "unidad_desconectada" / "RespaldosCafe")
est = c.get("/api/admin/respaldos/estado", headers=A).json()
ok(est["unidad_externa"]["texto"] == "No disponible", f"estado: {est['unidad_externa']['texto']}")
avisos_antes = len(bitacora("RESPALDO_EXTERNO"))
poner_reloj(6, "10:01")
r = c.post("/api/admin/respaldos/ejecutar?tipo=manual", headers=A)
ok(r.status_code == 200 and (LOCAL / r.json()["archivo"]).is_file(), f"manual con unidad desconectada -> {r.status_code}, local OK")
ok(r.json()["falla_externa"] is True and "no disponible" in r.json()["aviso_externo"], "la respuesta trae el aviso")
ok(len(bitacora("RESPALDO_EXTERNO")) == avisos_antes + 1, "aviso registrado en la bitácora (RESPALDO_EXTERNO)")
ok(not (TMP / "unidad_desconectada").exists(), "no crea la carpeta de una unidad desconectada")
poner_reloj(6, "23:00")
ok(respaldos.revisar_respaldo_diario() is not None, "el diario también se genera con la unidad desconectada")

# ---------------------------------------------------------------
print("== Copia a unidad externa")
EXTERNA.mkdir(parents=True)
os.environ["RUTA_RESPALDO_EXTERNO"] = str(EXTERNA)
est = c.get("/api/admin/respaldos/estado", headers=A).json()
ok(est["unidad_externa"]["texto"] == f"Conectada: {EXTERNA}", f"estado: {est['unidad_externa']['texto']}")
poner_reloj(7, "09:00")
r = c.post("/api/admin/respaldos/ejecutar?tipo=manual", headers=A)
manual_ext = r.json()["archivo"]
ok(r.json()["externo"] is True and (EXTERNA / manual_ext).is_file(), "manual: copiado a la unidad externa")
ok((EXTERNA / manual_ext).read_bytes() == (LOCAL / manual_ext).read_bytes(), "la copia externa es idéntica")
poner_reloj(7, "23:00")
diario_ext = respaldos.revisar_respaldo_diario()
ok(diario_ext and (EXTERNA / diario_ext).is_file(), "diario: copiado a la unidad externa")
poner_reloj(7, "23:30")
db = SessionLocal()
cierre = respaldos.generar_respaldo(db, "auto_cierre", respaldos.primer_admin(db).id_usuario)["archivo"]
db.close()
ok((EXTERNA / cierre).is_file(), "al cerrar: copiado a la unidad externa")

# ---------------------------------------------------------------
print("== Retención de 30 días (local y externa)")
ahora_ts = tiempo._reloj().timestamp()
for carpeta in (LOCAL, EXTERNA):
    for nombre, dias in (("respaldo_manual_20200101_000000.sql", 31), ("respaldo_diario_20200102_000000.sql", 29)):
        p = carpeta / nombre
        p.write_text("-- viejo")
        ts = ahora_ts - dias * 86400
        os.utime(p, (ts, ts))
poner_reloj(7, "23:45")
c.post("/api/admin/respaldos/ejecutar?tipo=manual", headers=A)
for carpeta, nombre in ((LOCAL, "local"), (EXTERNA, "externa")):
    ok(not (carpeta / "respaldo_manual_20200101_000000.sql").exists(), f"{nombre}: se borra el de 31 días")
    ok((carpeta / "respaldo_diario_20200102_000000.sql").exists(), f"{nombre}: se conserva el de 29 días")

# ---------------------------------------------------------------
print("== Pantalla: etiquetas de tipo y ubicación")
lista = c.get("/api/admin/respaldos", headers=A).json()["respaldos"]
por_archivo = {r["archivo"]: r for r in lista}
ok(por_archivo[manual_ext]["tipo"] == "Manual", "manual -> 'Manual'")
ok(por_archivo[diario_ext]["tipo"] == "Automático diario", "diario -> 'Automático diario'")
ok(por_archivo[cierre]["tipo"] == "Al cerrar el sistema", "auto_cierre -> 'Al cerrar el sistema'")
ok(por_archivo[manual_ext]["ubicacion"] == "Local + externa", "copiado -> 'Local + externa'")
solo_local = f"respaldo_diario_{DIA0:%Y%m%d}_230000.sql"   # generado antes de conectar la unidad
ok(por_archivo[solo_local]["ubicacion"] == "Local", "sin copia -> 'Local'")
ok(lista[0]["archivo"] == max(por_archivo, key=lambda n: respaldos.info_nombre(n)["fecha"] if respaldos.info_nombre(n) else datetime.min),
   "el historial va del más reciente al más antiguo")
ok(por_archivo[cierre]["fecha"] == f"{DIA0 + timedelta(days=7):%d/%m/%Y} 23:30", f"fecha mostrada en hora de México ({por_archivo[cierre]['fecha']})")

# ---------------------------------------------------------------
print("== Folio fijo por respaldo (no cambia al generar otro)")
ok(por_archivo[manual_ext]["folio"] == f"BKP-{DIA0 + timedelta(days=7):%Y%m%d}-090000-M",
   f"folio derivado del nombre: {manual_ext} -> {por_archivo[manual_ext]['folio']}")
ok(len({r["folio"] for r in lista}) == len(lista), "no hay folios repetidos")
ok(respaldos.folio("respaldo_auto_cierre_20261122_165634.sql") != respaldos.folio("respaldo_auto_cierre_20261122_165641.sql"),
   "dos respaldos en el mismo minuto tienen folios distintos")
ok(respaldos.folio("respaldo_diario_20261126_080000.sql") == "BKP-20261126-080000-D"
   and respaldos.folio("respaldo_auto_cierre_20261126_080000.sql") == "BKP-20261126-080000-C",
   "mismo segundo, distinto tipo: folios distintos (-D / -C)")
folios_antes = {r["archivo"]: r["folio"] for r in lista}
poner_reloj(7, "23:50")
nuevo_bkp = c.post("/api/admin/respaldos/ejecutar?tipo=manual", headers=A).json()["archivo"]
lista2 = c.get("/api/admin/respaldos", headers=A).json()["respaldos"]
folios_despues = {r["archivo"]: r["folio"] for r in lista2}
ok(lista2[0]["archivo"] == nuevo_bkp, "el respaldo nuevo queda primero en la lista")
ok(all(folios_despues[a] == f for a, f in folios_antes.items() if a in folios_despues),
   "los folios existentes no cambian al generar uno nuevo")
ok(folios_despues[nuevo_bkp] not in folios_antes.values(), f"el nuevo recibe un folio que no estaba ({folios_despues[nuevo_bkp]})")

print("== Falla del diario: log + bitácora, sin tumbar el servidor")
original = respaldos._volcado_sqlite, respaldos._volcado_mysql


def _rompe():
    raise RuntimeError("disco lleno (simulado)")


respaldos._volcado_sqlite = respaldos._volcado_mysql = _rompe
poner_reloj(8, "23:00")
ok(respaldos.revisar_respaldo_diario() is None, "revisar_respaldo_diario() no lanza excepción")
ok(any("disco lleno" in d for d in bitacora("RESPALDO_DIARIO_ERROR")), "falla registrada en la bitácora")
ok(not (LOCAL / ".respaldo_diario.lock").exists(), "el candado se libera aunque falle")
respaldos._volcado_sqlite, respaldos._volcado_mysql = original
poner_reloj(8, "23:01")
ok(respaldos.revisar_respaldo_diario() is not None, "en la siguiente revisión se reintenta y genera")

# ---------------------------------------------------------------
print("== Permisos y validaciones")
ok(c.get("/api/admin/respaldos/estado", headers=K).status_code == 403, "estado: cajero -> 403")
ok(c.get("/api/admin/respaldos/estado").status_code == 401, "estado: sin sesión -> 401")
ok(c.post("/api/admin/respaldos/ejecutar?tipo=diario", headers=A).status_code == 400, "ejecutar tipo=diario desde el API -> 400")
ok(c.post("/api/admin/respaldos/ejecutar?tipo=../x", headers=A).status_code == 400, "tipo con ruta -> 400")
r = c.get(f"/api/admin/respaldos/descargar/{manual_ext}", headers=A)
ok(r.status_code == 200 and r.content.startswith(b"-- Respaldo"), "descargar respaldo -> 200")

print()
if fallas:
    print(f"{len(fallas)} FALLA(S)")
    sys.exit(1)
print("Todas las pruebas de respaldos pasaron.")
