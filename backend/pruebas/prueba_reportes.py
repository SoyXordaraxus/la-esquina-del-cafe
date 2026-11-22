"""
Prueba de los reportes exportables (RF 12): PDF y CSV de ventas, consumo y mermas.

Uso (desde backend/):  python3 pruebas/prueba_reportes.py
Usa una base SQLite temporal (o DATABASE_URL si se define, debe estar vacía).
Revisa con y sin datos: PDF válido (estructura, xref, páginas), "Café", "TOTAL",
"Página X de Y", encabezado con periodo y hora de México, montos, y CSV UTF-8 con BOM
con los mismos encabezados y la fila de TOTAL.
"""
import csv
import io
import os
import re
import sys
import tempfile
import zlib
from datetime import date, datetime, timezone
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(RAIZ / "backend"))
if not os.getenv("DATABASE_URL"):
    os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.mkdtemp()}/prueba_reportes.db"

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

import seed  # noqa: E402
import services.tiempo as tiempo  # noqa: E402
from database import SessionLocal  # noqa: E402
from main import app  # noqa: E402
from services.reportes_export import dinero, generar_pdf, numero  # noqa: E402

fallas = []


def ok(cond, msg):
    print(("  OK    " if cond else "  FALLA ") + msg)
    if not cond:
        fallas.append(msg)


# ---------------------------------------------------------------- utilidades PDF
def texto_pdf(datos: bytes) -> str:
    """Texto de los content streams (fpdf2 los comprime con Flate; Helvetica = latin-1)."""
    crudo = b""
    for stream in re.findall(rb"stream\r?\n(.*?)\r?\nendstream", datos, re.S):
        try:
            crudo += zlib.decompress(stream)
        except zlib.error:
            crudo += stream
    # fpdf2 parte algunos textos en varios Tj (p. ej. "Página 1 de " + "9"): se unen
    crudo = re.sub(rb"\)\s*Tj\s*\(", b"", crudo)
    crudo = re.sub(rb"\)\s*Tj\s*(?:-?[\d.]+\s+-?[\d.]+\s+Td\s*)?\(", b"", crudo)
    return crudo.replace(rb"\(", b"(").replace(rb"\)", b")").decode("latin-1")


def pdf_valido(datos: bytes):
    """(es_valido, num_paginas, horizontal): encabezado, %%EOF, startxref -> tabla xref."""
    if not (datos.startswith(b"%PDF-") and datos.rstrip().endswith(b"%%EOF")):
        return False, 0, False
    m = re.search(rb"startxref\s+(\d+)\s+%%EOF\s*$", datos)
    if not m or not datos[int(m.group(1)):].startswith(b"xref"):
        return False, 0, False
    paginas = len(re.findall(rb"/Type\s*/Page(?![s\w])", datos))
    caja = re.search(rb"/MediaBox\s*\[\s*0\s+0\s+([\d.]+)\s+([\d.]+)\s*\]", datos)
    horizontal = bool(caja) and float(caja.group(1)) > float(caja.group(2))
    return paginas > 0, paginas, horizontal


def leer_csv(datos: bytes):
    return list(csv.reader(io.StringIO(datos.decode("utf-8-sig"))))


# ---------------------------------------------------------------- datos
seed.poblar_base()
c = TestClient(app)
admin = c.post("/api/auth/login", json={"usuario": "admin@esquinadelcafe.mx", "contrasena": "admin123"}).json()
A = {"Authorization": f"Bearer {admin['token']}"}
K = {"Authorization": f"Bearer {c.post('/api/auth/login', json={'usuario': 'Osvaldo Vazquez', 'contrasena': 'cajero123'}).json()['token']}"}

# Una venta que se queda (2 capuchinos) y otra que se cancela (1 latte), para que haya
# consumo real y cancelaciones distintas de cero
prods = {p["nombre"]: p for p in c.get("/api/ventas/productos-disponibles", headers=K).json()}
r = c.post("/api/ventas/cobrar", headers=K, json={"forma_pago": "Efectivo", "monto_recibido": 100,
                                                  "detalles": [{"id_producto": prods["Capuchino"]["id_producto"], "cantidad": 2}]})
ok(r.status_code == 201, f"preparación: venta de 2 capuchinos -> {r.status_code}")
venta = c.post("/api/ventas/cobrar", headers=K, json={"forma_pago": "Efectivo", "monto_recibido": 100,
                                                      "detalles": [{"id_producto": prods["Latte"]["id_producto"], "cantidad": 1}]}).json()
r = c.post(f"/api/ventas/{venta['id_venta']}/cancelar", headers=A, json={"motivo": "Error de captura"})
ok(r.status_code == 200, f"preparación: venta #{venta['id_venta']} cancelada -> {r.status_code}")

# Reloj fijo: 03:30 UTC del 23/11 = 21:30 del 22/11 en Ciudad de México
reloj_original = tiempo._reloj
tiempo._reloj = lambda: datetime(2026, 11, 23, 3, 30, tzinfo=timezone.utc)
HOY = tiempo.hoy_local()
CON_DATOS = {"fecha_inicio": "2026-10-01", "fecha_fin": HOY.isoformat()}
SIN_DATOS = {"fecha_inicio": "2020-01-01", "fecha_fin": "2020-01-31"}
TIPOS = {"ventas": "Reporte de Ventas Netas", "consumo": "Reporte de Consumo de Insumos", "mermas": "Reporte de Mermas"}

print("== Formato de montos")
ok(dinero(1234.5) == "$1,234.50" and dinero(0) == "$0.00", "dinero: $1,234.50 y $0.00")
ok(dinero(0, negativo=True) == "$0.00" and dinero(45, negativo=True) == "-$45.00", "cancelaciones: cero -> $0.00 (no -$0.00); 45 -> -$45.00")
ok(numero(2000) == "2,000" and numero(1250.5) == "1,250.5" and numero(0.25) == "0.25", "cantidades sin ceros de más")

for tipo, titulo in TIPOS.items():
    print(f"== {titulo}")
    vista = c.get("/api/admin/reportes", headers=A, params={"tipo": tipo, **CON_DATOS}).json()
    ok(vista["filas"] and vista["total"] and len(vista["total"]) == len(vista["columnas"]) == len(vista["alineacion"]),
       f"vista previa con {len(vista['filas'])} filas, TOTAL y alineación por columna")
    ok(vista["periodo"] == f"01/10/2026 al {HOY:%d/%m/%Y}", f"periodo dd/mm/aaaa: {vista['periodo']}")
    ok(all(re.fullmatch(r"-?\$\d{1,3}(,\d{3})*\.\d{2}", celda) for fila in vista["filas"] + [vista["total"]]
           for celda, al in zip(fila, vista["alineacion"]) if "$" in celda and al == "R"),
       "todos los montos con formato $1,234.50")
    ok(not any("-$0.00" in celda for fila in vista["filas"] + [vista["total"]] for celda in fila), "ningún -$0.00")

    for nombre_caso, periodo in (("con datos", CON_DATOS), ("sin datos", SIN_DATOS)):
        # ---- PDF
        r = c.get("/api/admin/reportes/exportar", headers=A, params={"tipo": tipo, "formato": "pdf", **periodo})
        valido, paginas, _ = pdf_valido(r.content)
        ok(r.status_code == 200 and r.headers["content-type"] == "application/pdf" and valido,
           f"PDF {nombre_caso}: válido ({paginas} página(s), {len(r.content):,} bytes)")
        t = texto_pdf(r.content)
        ini = date.fromisoformat(periodo["fecha_inicio"])
        fin = date.fromisoformat(periodo["fecha_fin"])
        ok("La Esquina del Café" in t and "TOTAL" in t and titulo in t, f"PDF {nombre_caso}: contiene 'Café', 'TOTAL' y el título")
        ok(f"Periodo: {ini:%d/%m/%Y} al {fin:%d/%m/%Y}" in t and "Generado el 22/11/2026 21:30 por Andres Mosso" in t,
           f"PDF {nombre_caso}: periodo dd/mm/aaaa y 'Generado el …' en hora de México")
        ok(f"Página 1 de {paginas}" in t, f"PDF {nombre_caso}: 'Página 1 de {paginas}'")
        if nombre_caso == "sin datos":
            ok("Sin registros en este periodo" in t, "PDF sin datos: fila 'Sin registros en este periodo'")
        else:
            ok(all(celda in t for celda in vista["total"] if celda), f"PDF con datos: la fila TOTAL trae {[x for x in vista['total'] if x]}")

        # ---- CSV
        r = c.get("/api/admin/reportes/exportar", headers=A, params={"tipo": tipo, "formato": "csv", **periodo})
        ok(r.status_code == 200 and r.content.startswith(b"\xef\xbb\xbf") and "charset=utf-8" in r.headers["content-type"],
           f"CSV {nombre_caso}: UTF-8 con BOM")
        filas = leer_csv(r.content)
        ok(filas[0] == ["La Esquina del Café"] and filas[1] == [titulo]
           and filas[2] == [f"Periodo: {ini:%d/%m/%Y} al {fin:%d/%m/%Y}"]
           and filas[3] == ["Generado el 22/11/2026 21:30 por Andres Mosso"],
           f"CSV {nombre_caso}: encabezado con negocio, título, periodo y generado")
        ok(filas[5] == vista["columnas"], f"CSV {nombre_caso}: mismos encabezados que el PDF/vista previa")
        ok(filas[-1][0].startswith("TOTAL"), f"CSV {nombre_caso}: termina con la fila TOTAL {filas[-1]}")
        if nombre_caso == "sin datos":
            ok(filas[6] == ["Sin registros en este periodo"], "CSV sin datos: fila 'Sin registros en este periodo'")
        else:
            ok(filas[6:-1] == vista["filas"] and filas[-1] == vista["total"], "CSV con datos: mismas filas y TOTAL que la vista previa")

print("== Totales correctos")
v = c.get("/api/admin/reportes", headers=A, params={"tipo": "ventas", **CON_DATOS}).json()
dec = lambda s: float(s.replace("$", "").replace(",", ""))  # noqa: E731
ok(sum(int(f[1]) for f in v["filas"]) == v["resumen"]["completadas"] == int(v["total"][1]), "ventas: completadas = suma de filas")
ok(abs(sum(dec(f[4]) for f in v["filas"]) - dec(v["total"][4])) < 0.01, "ventas: netas = suma de filas")
ok(v["resumen"]["cancelaciones"] > 0 and v["total"][3].startswith("-$"), f"ventas: cancelaciones del periodo {v['total'][3]}")
ok(abs(v["resumen"]["brutas"] - v["resumen"]["cancelaciones"] - v["resumen"]["netas"]) < 0.01, "ventas: brutas - cancelaciones = netas")
co = c.get("/api/admin/reportes", headers=A, params={"tipo": "consumo", **CON_DATOS}).json()
ok(abs(sum(dec(f[4]) for f in co["filas"]) - dec(co["total"][4])) < 0.01 and co["resumen"]["costo_total"] > 0,
   f"consumo: costo total {co['total'][4]} = suma de filas")
# 2 capuchinos = 36 g de café y 300 ml de leche; el latte cancelado (18 g + 200 ml) no cuenta
ok({f[0]: f[2] for f in co["filas"]} == {"Café molido": "36", "Leche entera": "300"},
   f"consumo: solo ventas no canceladas (2 capuchinos; el latte cancelado no cuenta): {[(f[0], f[2], f[3]) for f in co['filas']]}")
ok(co["total"][2] == "36 g · 300 ml", f"consumo: cantidad total desglosada por unidad ({co['total'][2]})")
ok(co["total"][2] and all(u in co["total"][2] for u in {f[3] for f in co["filas"]}),
   f"consumo: cantidad total desglosada por unidad ({co['total'][2]})")
me = c.get("/api/admin/reportes", headers=A, params={"tipo": "mermas", **CON_DATOS}).json()
ok(abs(sum(dec(f[5]) for f in me["filas"]) - dec(me["total"][5])) < 0.01, f"mermas: costo total {me['total'][5]} = suma de filas")

print("== Paginación, encabezado repetido y orientación")
meta = {"periodo": (date(2026, 11, 1), date(2026, 11, 22)), "usuario": "Andrés Muñoz", "generado": datetime(2026, 11, 22, 13, 5)}
largo = {"titulo": "Reporte de Mermas", "columnas": ["Fecha", "Insumo", "Cantidad", "Unidad", "Motivo", "Costo de pérdida"],
         "alineacion": ["L", "L", "R", "L", "L", "R"],
         "filas": [[f"{d % 28 + 1:02d}/11/2026 14:00", f"Leche deslactosada orgánica de pastoreo libre #{d}", "1,250.5", "ml",
                    "Caducidad — producto vencido en la cámara de refrigeración", "$1,234.50"] for d in range(90)],
         "total": ["TOTAL (90 registros)", "", "112,545 ml", "", "", "$111,105.00"]}
pdf = generar_pdf(largo, meta)
valido, paginas, horizontal = pdf_valido(pdf)
t = texto_pdf(pdf)
ok(valido and paginas > 1, f"90 filas -> PDF válido de {paginas} páginas")
ok(all(f"Página {n} de {paginas}" in t for n in range(1, paginas + 1)), f"'Página X de {paginas}' en todas las páginas")
ok(t.count("Costo de pérdida") == paginas, f"encabezado de la tabla repetido en cada página ({t.count('Costo de pérdida')}/{paginas})")
ok(horizontal, "columnas que no caben en vertical -> hoja horizontal")
ok("Andrés Muñoz" in t and "Caducidad - producto" in t, "acentos y ñ correctos; la raya — se cambia por '-' (Helvetica)")
corto = {"titulo": "Reporte de Ventas Netas", "columnas": ["Fecha", "Total"], "alineacion": ["L", "R"],
         "filas": [["01/11/2026", "$1.00"]], "total": ["TOTAL", "$1.00"]}
ok(not pdf_valido(generar_pdf(corto, meta))[2], "pocas columnas -> hoja vertical")

print("== Validaciones y bitácora")
ok(c.get("/api/admin/reportes/exportar", headers=A, params={"tipo": "ventas", "formato": "xls"}).status_code == 400, "formato no soportado -> 400")
ok(c.get("/api/admin/reportes/exportar", headers=A, params={"tipo": "otro", "formato": "pdf"}).status_code == 400, "tipo no válido -> 400")
ok(c.get("/api/admin/reportes", headers=A, params={"tipo": "ventas", "fecha_inicio": "2026-11-20", "fecha_fin": "2026-11-01"}).status_code == 400,
   "fecha de inicio posterior a la final -> 400")
ok(c.get("/api/admin/reportes/exportar", headers=K, params={"tipo": "ventas", "formato": "pdf"}).status_code == 403, "cajero -> 403")
with SessionLocal() as db:
    n = db.execute(text("SELECT COUNT(*) FROM bitacora WHERE accion = 'REPORTE_GENERADO'")).scalar()
ok(n == 12, f"bitácora: REPORTE_GENERADO por cada exportación ({n}/12)")
ok("fpdf2" in (RAIZ / "requirements.txt").read_text(), "requirements.txt incluye fpdf2")

tiempo._reloj = reloj_original
print()
print("RESULTADO:", "TODO OK" if not fallas else f"{len(fallas)} FALLA(S)")
for f in fallas:
    print("  -", f)
sys.exit(1 if fallas else 0)
