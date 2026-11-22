"""
Prueba de zona horaria: una venta a las 23:30 hora del negocio (America/Mexico_City)
debe quedar en ESE día aunque en UTC ya sea el día siguiente.

Uso (desde backend/):
    python3 pruebas/prueba_zona_horaria.py                 # SQLite temporal
    DATABASE_URL=mysql+pymysql://... python3 pruebas/prueba_zona_horaria.py   # base MySQL VACÍA

Congela el reloj de services/tiempo.py en 2026-11-21 23:30 (México) = 2026-11-22 05:30 UTC.
"""
import os
import sys
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
if not os.getenv("DATABASE_URL"):
    os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.mkdtemp()}/prueba_tz.db"
os.environ.setdefault("TZ_NEGOCIO", "America/Mexico_City")

from fastapi.testclient import TestClient  # noqa: E402

import seed  # noqa: E402
from database import SessionLocal, engine  # noqa: E402
from main import app  # noqa: E402
from models import Bitacora, Insumo, LoteInsumo, Venta  # noqa: E402
from services import tiempo  # noqa: E402

AHORA_UTC = datetime(2026, 11, 22, 5, 30, tzinfo=timezone.utc)   # = 21/11/2026 23:30 en CDMX
DIA_NEGOCIO = "2026-11-21"
DIA_UTC = "2026-11-22"
fallas = []


def ok(cond, msg):
    print(("  OK    " if cond else "  FALLA ") + msg)
    if not cond:
        fallas.append(msg)


tiempo._reloj = lambda: AHORA_UTC     # reloj congelado
print(f"Motor: {engine.dialect.name} · zona {tiempo.NOMBRE_ZONA} · hoy_local={tiempo.hoy_local()}")
ok(str(tiempo.hoy_local()) == DIA_NEGOCIO, "hoy_local() es el día de México, no el de UTC")
ok(tiempo.rango_utc(date(2026, 11, 21)) == (datetime(2026, 11, 21, 6, 0), datetime(2026, 11, 22, 6, 0)),
   "rango del 21/11 en UTC = [21 06:00, 22 06:00)")

seed.poblar_base()
c = TestClient(app)
admin = c.post("/api/auth/login", json={"usuario": "admin@esquinadelcafe.mx", "contrasena": "admin123"}).json()
cajero = c.post("/api/auth/login", json={"usuario": "Osvaldo Vazquez", "contrasena": "cajero123"}).json()
A = {"Authorization": f"Bearer {admin['token']}"}
K = {"Authorization": f"Bearer {cajero['token']}"}
ok(admin.get("zona_horaria") == "America/Mexico_City", "el login entrega zona_horaria")

print("== Venta a las 23:30 hora de México")
r = c.post("/api/ventas/cobrar", headers=K, json={
    "forma_pago": "Tarjeta", "detalles": [{"id_producto": 1, "cantidad": 1}]})
ok(r.status_code == 201, f"cobrar -> {r.status_code}")
id_venta = r.json()["id_venta"]
ok(r.json()["fecha"] == "2026-11-21T23:30:00-06:00", f"respuesta en hora de México: {r.json()['fecha']}")
db = SessionLocal()
guardada = db.get(Venta, id_venta).fecha_emision_ticket
ok(guardada.replace(microsecond=0) == datetime(2026, 11, 22, 5, 30), f"se guarda en UTC: {guardada}")

print("== Filtro 'Hoy' del historial")
hist = c.get(f"/api/ventas/historial?fecha={DIA_NEGOCIO}", headers=A).json()
ok(any(v["id_venta"] == id_venta for v in hist), f"aparece con fecha={DIA_NEGOCIO} (Hoy en México)")
ok(not any(v["id_venta"] == id_venta for v in c.get(f"/api/ventas/historial?fecha={DIA_UTC}", headers=A).json()),
   f"NO aparece con fecha={DIA_UTC} (el día UTC)")
det = c.get(f"/api/ventas/{id_venta}", headers=A).json()
ok(det["fecha"].startswith("2026-11-21T23:30"), f"detalle muestra {det['fecha']}")

print("== Panel: ventas de hoy")
panel = c.get("/api/dashboard/resumen", headers=A).json()["metricas"]
ok(panel["tickets_dia"] >= 1 and panel["ventas_dia"] >= 35, f"panel cuenta la venta de hoy ({panel['tickets_dia']} tickets, ${panel['ventas_dia']})")

print("== Reporte del día")
rep = c.get(f"/api/admin/reportes?tipo=ventas&fecha_inicio={DIA_NEGOCIO}&fecha_fin={DIA_NEGOCIO}", headers=A).json()
dia_dmy = "/".join(reversed(str(DIA_NEGOCIO).split("-")))   # el reporte muestra dd/mm/aaaa
ok([f[0] for f in rep["filas"]] == [dia_dmy], f"reporte del {DIA_NEGOCIO} agrupa la venta en ese día: {rep['filas']}")
rep2 = c.get(f"/api/admin/reportes?tipo=ventas&fecha_inicio={DIA_UTC}&fecha_fin={DIA_UTC}", headers=A).json()
ok(rep2["filas"] == [], f"reporte del {DIA_UTC} no la incluye")
cons = c.get(f"/api/admin/reportes?tipo=consumo&fecha_inicio={DIA_NEGOCIO}&fecha_fin={DIA_NEGOCIO}", headers=A).json()
ok(len(cons["filas"]) >= 1, "reporte de consumo del día incluye el café de la venta")

print("== Bitácora")
bit = c.get(f"/api/admin/bitacora?fecha_inicio={DIA_NEGOCIO}&fecha_fin={DIA_NEGOCIO}", headers=A).json()["registros"]
reg = next((b for b in bit if b["accion"] == "VENTA_REGISTRADA" and f"#{id_venta}" in b["detalle"]), None)
ok(reg is not None and reg["hora"] == "23:30:00", f"bitácora del {DIA_NEGOCIO} con hora local: {reg and reg['hora']}")
ok(db.query(Bitacora).filter(Bitacora.accion == "VENTA_REGISTRADA").one().fecha_hora.replace(microsecond=0)
   == datetime(2026, 11, 22, 5, 30), "bitácora guardada en UTC")

print("== Caducidades con fecha de México")
ins = db.query(Insumo).filter_by(nombre="Pan para panini").one()
db.add(LoteInsumo(id_insumo=ins.id_insumo, cantidad_recibida=5, cantidad_disponible=5, costo_unitario=60,
                  caducidad=date(2026, 11, 22), numero_factura="TZ-MANANA", estado="Disponible"))
db.add(LoteInsumo(id_insumo=ins.id_insumo, cantidad_recibida=5, cantidad_disponible=5, costo_unitario=60,
                  caducidad=date(2026, 11, 21), numero_factura="TZ-HOY", estado="Disponible"))
db.commit()
lotes = {l["codigo_lote"]: l for l in c.get("/api/almacen/lotes", headers=A).json()["lotes"]}
ok(lotes["TZ-MANANA"]["texto_vencimiento"] == "Vence mañana", f"caduca 22/11 -> {lotes['TZ-MANANA']['texto_vencimiento']} (en UTC diría 'Vence hoy')")
ok(lotes["TZ-HOY"]["texto_vencimiento"] == "Vence hoy" and lotes["TZ-HOY"]["estado"] == "Vigente",
   f"caduca 21/11 -> {lotes['TZ-HOY']['texto_vencimiento']} / {lotes['TZ-HOY']['estado']} (en UTC ya estaría caducado)")
rec = c.post("/api/almacen/recepcion", headers=K, json={
    "id_insumo": ins.id_insumo, "cantidad_ingresada": 1, "unidad_compra": "pza",
    "costo_unitario": 6, "caducidad": DIA_NEGOCIO, "numero_factura": "FAC-9001"})
ok(rec.status_code == 201, f"recepción con caducidad de hoy (México) aceptada -> {rec.status_code}")
semaforo = c.get("/api/inventario/semaforo", headers=A)
ok(semaforo.status_code == 200, "semáforo responde")

print("== Badge de Caducidades")
res = c.get("/api/almacen/caducidades/resumen", headers=A).json()
lotes = {l["id_lote"]: l for l in c.get("/api/almacen/lotes", headers=A).json()["lotes"]}   # incluye la recepción
esperado = sum(1 for l in lotes.values()
               if l["estado"] == "Caducado" or (l["estado"] == "Vigente" and l["dias_restantes"] is not None and l["dias_restantes"] <= 5))
ok(res["alertas"] == esperado and res["fecha_negocio"] == DIA_NEGOCIO, f"resumen: {res} (esperado {esperado})")

print()
print("RESULTADO:", "TODO OK" if not fallas else f"{len(fallas)} FALLA(S)")
sys.exit(1 if fallas else 0)
