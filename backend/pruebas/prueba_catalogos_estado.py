"""
Prueba de Editar / Desactivar-Activar / Eliminar en Insumos y Productos.

Uso (desde backend/):  python3 pruebas/prueba_catalogos_estado.py
Usa una base SQLite temporal (o DATABASE_URL si se define, debe estar vacía).
Las partes del frontend (insumos.js, productos.js) se ejecutan con Node si está instalado.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent.parent
FRONT = RAIZ / "frontend"
sys.path.insert(0, str(RAIZ / "backend"))
if not os.getenv("DATABASE_URL"):
    os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.mkdtemp()}/prueba_catalogos.db"

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

import seed  # noqa: E402
from database import SessionLocal  # noqa: E402
from main import app  # noqa: E402

fallas = []


def ok(cond, msg):
    print(("  OK    " if cond else "  FALLA ") + msg)
    if not cond:
        fallas.append(msg)


def bitacora(accion, contiene):
    with SessionLocal() as db:
        filas = db.execute(text("SELECT detalle FROM bitacora WHERE accion = :a"), {"a": accion}).fetchall()
    return any(contiene in d for (d,) in filas)


seed.poblar_base()
c = TestClient(app)
A = {"Authorization": f"Bearer {c.post('/api/auth/login', json={'usuario': 'admin@esquinadelcafe.mx', 'contrasena': 'admin123'}).json()['token']}"}
K = {"Authorization": f"Bearer {c.post('/api/auth/login', json={'usuario': 'Osvaldo Vazquez', 'contrasena': 'cajero123'}).json()['token']}"}
API = "/api/catalogos"


def insumos():
    return {i["nombre"]: i for i in c.get(f"{API}/insumos", headers=A).json()["insumos"]}


def productos():
    return {p["nombre"]: p for p in c.get(f"{API}/productos", headers=A).json()["productos"]}


def patch(ruta, estado):
    return c.patch(ruta, headers=A, json={"estado": estado})


ins = insumos()
prods = productos()
LECHE, JARABE = ins["Leche entera"], ins["Jarabe de vainilla"]
FRAPPE = prods["Frappé"]

# ------------------------------------------------------------------ listado
print("== Listado: quién se puede eliminar y por qué no")
ok(not LECHE["puede_eliminar"] and LECHE["motivo_no_eliminar"].startswith("Tiene historial (") and LECHE["motivo_no_eliminar"].endswith(": usa Desactivar"),
   f"insumo con recetas y lotes -> no se puede eliminar: «{LECHE['motivo_no_eliminar']}»")
ok(LECHE["usado_en_productos_activos"] == ["Capuchino", "Frappé", "Latte"], f"Leche se usa en {LECHE['usado_en_productos_activos']}")

# ------------------------------------------------------------------ desactivar con recetas activas
print("== Desactivar insumo usado en productos activos -> 409 con la lista")
r = patch(f"{API}/insumos/{LECHE['id_insumo']}/estado", "Inactivo")
ok(r.status_code == 409 and r.json()["detail"] == "No se puede desactivar «Leche entera». Se usa en: Capuchino, Frappé, Latte. Desactiva o cambia esas recetas primero.",
   f"409: {r.json().get('detail')}")
ok(insumos()["Leche entera"]["estado"] == "Activo", "el insumo sigue Activo")

# ------------------------------------------------------------------ DELETE con historial
print("== Eliminar con historial -> 409 que sugiere Desactivar (ya no desactiva en silencio)")
r = c.delete(f"{API}/insumos/{JARABE['id_insumo']}", headers=A)
ok(r.status_code == 409 and "Desactivar" in r.json()["detail"] and "historial" in r.json()["detail"], f"409: {r.json().get('detail')}")
ok(insumos()["Jarabe de vainilla"]["estado"] == "Activo", "el insumo sigue Activo y en el catálogo")

# ------------------------------------------------------------------ PUT ya no cambia el estado
print("== Editar (PUT) ya no cambia el estado")
cuerpo = {k: JARABE[k] for k in ("nombre", "categoria", "unidad_medida", "unidad_compra", "factor_conversion", "es_perecedero", "minimo_reposicion")}
r = c.put(f"{API}/insumos/{JARABE['id_insumo']}", headers=A, json={**cuerpo, "minimo_reposicion": 600, "estado": "Inactivo"})
j = insumos()["Jarabe de vainilla"]
ok(r.status_code == 200 and j["estado"] == "Activo" and j["minimo_reposicion"] == 600, f"PUT con estado=Inactivo -> guarda el mínimo y sigue {j['estado']}")
p_cuerpo = {"nombre": FRAPPE["nombre"], "categoria": FRAPPE["categoria"], "precio_venta": FRAPPE["precio_venta"],
            "receta": [{"id_insumo": x["id_insumo"], "cantidad_necesaria": x["cantidad_necesaria"]} for x in FRAPPE["receta"]]}
r = c.put(f"{API}/productos/{FRAPPE['id_producto']}", headers=A, json={**p_cuerpo, "estado": "inactivo"})
ok(r.status_code == 200 and productos()["Frappé"]["estado"] == "activo", "PUT de producto con estado=inactivo -> sigue activo")

# ------------------------------------------------------------------ flujo completo con Jarabe (solo en Frappé)
print("== Venta, desactivar producto y luego el insumo; reportes conservan el historial")
disp = {p["nombre"]: p for p in c.get("/api/ventas/productos-disponibles", headers=K).json()["productos"]}
r = c.post("/api/ventas/cobrar", headers=K, json={"forma_pago": "Efectivo", "monto_recibido": 100,
                                                   "detalles": [{"id_producto": disp["Frappé"]["id_producto"], "cantidad": 1}]})
ok(r.status_code == 201, f"se vende un Frappé -> {r.status_code}")
r = patch(f"{API}/insumos/{JARABE['id_insumo']}/estado", "Inactivo")
ok(r.status_code == 409 and "Se usa en: Frappé." in r.json()["detail"], f"jarabe en Frappé activo -> 409: {r.json().get('detail')}")

ok(not productos()["Frappé"]["puede_eliminar"] and "1 venta" in productos()["Frappé"]["motivo_no_eliminar"], "producto vendido -> no se puede eliminar (motivo: 1 venta)")
r = c.delete(f"{API}/productos/{FRAPPE['id_producto']}", headers=A)
ok(r.status_code == 409 and "Desactivar" in r.json()["detail"], f"DELETE de producto con ventas -> 409: {r.json().get('detail')}")
r = patch(f"{API}/productos/{FRAPPE['id_producto']}/estado", "inactivo")
ok(r.status_code == 200 and productos()["Frappé"]["estado"] == "inactivo", f"desactivar Frappé -> {r.status_code}")
ok("Frappé" not in {p["nombre"] for p in c.get("/api/ventas/productos-disponibles", headers=K).json()["productos"]}, "Frappé inactivo ya no aparece en Caja")
ok(bitacora("PRODUCTO_DESACTIVADO", "Frappé"), "bitácora PRODUCTO_DESACTIVADO")

r = patch(f"{API}/insumos/{JARABE['id_insumo']}/estado", "Inactivo")
ok(r.status_code == 200 and insumos()["Jarabe de vainilla"]["estado"] == "Inactivo", f"ahora sí se desactiva el jarabe -> {r.status_code}: {r.json().get('mensaje')}")
ok(bitacora("INSUMO_DESACTIVADO", "Jarabe de vainilla"), "bitácora INSUMO_DESACTIVADO (services/bitacora)")
r = patch(f"{API}/insumos/{JARABE['id_insumo']}/estado", "Inactivo")
ok(r.status_code == 200 and "ya estaba" in r.json()["mensaje"], "desactivar dos veces -> 200 'ya estaba inactivo'")

print("== Insumo inactivo: fuera de Recepción y de recetas nuevas, pero en reportes e historial")
ok("Jarabe de vainilla" not in {i["nombre"] for i in c.get("/api/almacen/catalogos", headers=K).json()["insumos"]}, "no aparece en el catálogo de Recepción")
ok("Jarabe de vainilla" not in {i["nombre"] for i in c.get(f"{API}/insumos?incluir_inactivos=false", headers=A).json()["insumos"]},
   "no aparece en la lista de insumos para armar recetas")
r = c.post("/api/almacen/recepcion", headers=K, json={"id_insumo": JARABE["id_insumo"], "cantidad_ingresada": 1, "unidad_compra": "L", "costo_unitario": 10})
ok(r.status_code == 409 and "inactivo" in r.json()["detail"], f"recepción de un insumo inactivo -> 409: {r.json().get('detail')}")
r = c.post(f"{API}/productos", headers=A, json={"nombre": "Prueba jarabe", "categoria": "Bebidas frías", "precio_venta": 10,
                                                 "receta": [{"id_insumo": JARABE["id_insumo"], "cantidad_necesaria": 5}]})
ok(r.status_code == 409 and "Jarabe de vainilla" in r.json()["detail"], f"receta nueva con insumo inactivo -> 409: {r.json().get('detail')}")
ok("Jarabe de vainilla" in insumos(), "sigue en el catálogo de Insumos (con filtro Todos)")
ok(any(l["insumo"] == "Jarabe de vainilla" for l in c.get("/api/almacen/lotes", headers=A).json()["lotes"]), "sus lotes siguen en el historial de lotes")
rep = c.get("/api/admin/reportes?tipo=consumo", headers=A)
ok(rep.status_code == 200 and "Jarabe de vainilla" in json.dumps(rep.json(), ensure_ascii=False), "sigue en el reporte de consumo")
ok("Frappé" in json.dumps(c.get("/api/ventas/historial", headers=A).json(), ensure_ascii=False) or
   any("Frappé" in json.dumps(c.get(f"/api/ventas/{v['id_venta']}", headers=A).json(), ensure_ascii=False)
       for v in (c.get("/api/ventas/historial", headers=A).json().get("ventas") or [])[:3]),
   "la venta del Frappé sigue en el historial de ventas")

print("== Producto inactivo con insumo inactivo")
r = patch(f"{API}/productos/{FRAPPE['id_producto']}/estado", "activo")
ok(r.status_code == 409 and "Jarabe de vainilla" in r.json()["detail"], f"activar Frappé con jarabe inactivo -> 409: {r.json().get('detail')}")
r = c.put(f"{API}/productos/{FRAPPE['id_producto']}", headers=A, json={**p_cuerpo, "precio_venta": 62})
ok(r.status_code == 200, f"editar Frappé inactivo conservando el jarabe que ya tenía -> {r.status_code}")
r = patch(f"{API}/insumos/{ins['Rebanada de pastel']['id_insumo']}/estado", "Inactivo")
ok(r.status_code == 409, "la rebanada de pastel se usa en Pastel (activo) -> 409")
patch(f"{API}/productos/{prods['Pastel']['id_producto']}/estado", "inactivo")
ok(patch(f"{API}/insumos/{ins['Rebanada de pastel']['id_insumo']}/estado", "Inactivo").status_code == 200, "tras desactivar Pastel, se desactiva la rebanada")
r = c.put(f"{API}/productos/{FRAPPE['id_producto']}", headers=A,
          json={**p_cuerpo, "receta": p_cuerpo["receta"] + [{"id_insumo": ins["Rebanada de pastel"]["id_insumo"], "cantidad_necesaria": 1}]})
ok(r.status_code == 409 and "Rebanada de pastel" in r.json()["detail"], "agregar a la receta OTRO insumo inactivo -> 409")

r = patch(f"{API}/insumos/{JARABE['id_insumo']}/estado", "Activo")
ok(r.status_code == 200 and insumos()["Jarabe de vainilla"]["estado"] == "Activo", "activar el jarabe -> 200")
ok(bitacora("INSUMO_ACTIVADO", "Jarabe de vainilla"), "bitácora INSUMO_ACTIVADO")
ok("Jarabe de vainilla" in {i["nombre"] for i in c.get("/api/almacen/catalogos", headers=K).json()["insumos"]}, "vuelve a aparecer en Recepción")
r = patch(f"{API}/productos/{FRAPPE['id_producto']}/estado", "activo")
ok(r.status_code == 200 and productos()["Frappé"]["estado"] == "activo", "ahora sí se activa Frappé")
ok(bitacora("PRODUCTO_ACTIVADO", "Frappé"), "bitácora PRODUCTO_ACTIVADO")

print("== Eliminar sin historial")
r = c.post(f"{API}/insumos", headers=A, json={"nombre": "Canela molida", "categoria": "Abarrotes", "unidad_medida": "g",
                                               "unidad_compra": "kg", "factor_conversion": 1000, "es_perecedero": False, "minimo_reposicion": 100})
id_canela = r.json()["id_insumo"]
canela = insumos()["Canela molida"]
ok(canela["puede_eliminar"] and canela["motivo_no_eliminar"] == "", "insumo nuevo sin historial -> se puede eliminar")
r = c.post(f"{API}/productos", headers=A, json={"nombre": "Café con canela", "categoria": "Bebidas calientes", "precio_venta": 40,
                                                 "receta": [{"id_insumo": id_canela, "cantidad_necesaria": 2}]})
id_prod = r.json()["id_producto"]
ok(r.status_code == 201 and productos()["Café con canela"]["estado"] == "activo" and productos()["Café con canela"]["puede_eliminar"],
   "producto nuevo: se crea activo y sin ventas se puede eliminar")
ok(not insumos()["Canela molida"]["puede_eliminar"], "la canela ya está en una receta -> ya no se puede eliminar")
r = c.delete(f"{API}/productos/{id_prod}", headers=A)
ok(r.status_code == 200 and "Café con canela" not in productos(), f"DELETE producto sin ventas -> {r.status_code}")
with SessionLocal() as db:
    ok(db.execute(text("SELECT COUNT(*) FROM receta WHERE id_producto = :p"), {"p": id_prod}).scalar() == 0, "también se borró su receta")
ok(bitacora("PRODUCTO_ELIMINADO", "Café con canela"), "bitácora PRODUCTO_ELIMINADO")
r = c.delete(f"{API}/insumos/{id_canela}", headers=A)
ok(r.status_code == 200 and "Canela molida" not in insumos(), f"DELETE insumo sin historial -> {r.status_code}")
ok(bitacora("INSUMO_ELIMINADO", "Canela molida"), "bitácora INSUMO_ELIMINADO")

print("== Validaciones")
ok(patch(f"{API}/insumos/{JARABE['id_insumo']}/estado", "Borrado").status_code == 400, "estado inválido -> 400")
ok(patch(f"{API}/insumos/999999/estado", "Inactivo").status_code == 404, "insumo inexistente -> 404")
ok(c.delete(f"{API}/productos/999999", headers=A).status_code == 404, "producto inexistente -> 404")
ok(c.patch(f"{API}/insumos/{JARABE['id_insumo']}/estado", headers=K, json={"estado": "Inactivo"}).status_code == 403, "cajero -> 403")
ok(c.patch(f"{API}/insumos/{JARABE['id_insumo']}/estado", json={"estado": "Inactivo"}).status_code == 401, "sin token -> 401")

# ------------------------------------------------------------------ estático
print("== HTML/JS: sin campo Estado en los modales")
for archivo in ("insumos.html", "productos.html", "js/insumos.js", "js/productos.js"):
    t = (FRONT / archivo).read_text(encoding="utf-8")
    ok(not re.search(r"insumo-estado|grupo-estado-insumo|prod-estado|id_usuario", t), f"{archivo}: sin select de estado ni id_usuario en el cuerpo")

# ------------------------------------------------------------------ frontend
NODE = shutil.which("node")
if not NODE:
    print("== Node no está instalado: se omiten las pruebas del frontend")
else:
    print("== Frontend (Node): botones, confirmación y mensajeError")
    datos = {"insumos": c.get(f"{API}/insumos", headers=A).json(), "productos": c.get(f"{API}/productos", headers=A).json()}
    # Un inactivo para ver "Activar"
    datos["insumos"]["insumos"].append({**datos["insumos"]["insumos"][0], "id_insumo": 9999, "nombre": "Inactivo X", "estado": "Inactivo",
                                         "puede_eliminar": True, "motivo_no_eliminar": "", "usado_en_productos_activos": []})
    script = r"""
const fs = require("fs"), vm = require("vm");
const [argDatos, raiz] = process.argv.slice(-2);
const datos = JSON.parse(argDatos);
function contexto(pagina, respuestas) {
  const elementos = {};
  const el = id => elementos[id] = elementos[id] || { id, innerHTML: "", textContent: "", value: id.startsWith("filtro-") ? (id.includes("cat") ? "todas" : "todos") : "",
                                                    style: {}, className: "", addEventListener() {}, reset() {} };
  const ctx = {
    console, Intl, Date, URLSearchParams, setTimeout() {}, setInterval() {}, peticiones: [], confirmaciones: [],
    Headers: class { constructor(h) { this.h = Object.assign({}, h); } has(k) { return k in this.h; } set(k, v) { this.h[k] = v; } },
    localStorage: { getItem: () => JSON.stringify({ id_usuario: 1, token: "t", rol: "Administrador", nombre: "A" }), setItem() {}, removeItem() {} },
    elementos,
    document: { addEventListener() {}, getElementById: el, querySelectorAll: () => [] },
  };
  ctx.window = { location: { protocol: "http:", hostname: "127.0.0.1", port: "8000", origin: "http://127.0.0.1:8000", pathname: "/" + pagina, search: "", replace() {} },
                 fetch: async (u, o = {}) => {
                   ctx.peticiones.push({ url: u.replace("http://127.0.0.1:8000", ""), metodo: o.method || "GET", cuerpo: o.body || null });
                   const k = Object.keys(respuestas).find(r => (o.method || "GET") + " " + u.replace("http://127.0.0.1:8000", "") === r)
                          || Object.keys(respuestas).find(r => u.includes(r.split(" ").pop()) && r.startsWith(o.method || "GET"));
                   const [status, cuerpo] = respuestas[k] || [200, {}];
                   return { ok: status < 400, status, json: async () => cuerpo };
                 },
                 addEventListener() {} };
  ctx.window.window = ctx.window;
  ctx.location = ctx.window.location;
  vm.createContext(ctx);
  vm.runInContext(fs.readFileSync(raiz + "/frontend/js/config.js", "utf8"), ctx);
  vm.runInContext(`this.fetch = window.fetch;
    function escaparHtml(t) { return String(t).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])); }
    function mostrarConfirmacion(o) { confirmaciones.push(o); }
    function abrirModal() {} function cerrarModal() {} function obtenerUsuario() { return { id_usuario: 1 }; }`, ctx);
  vm.runInContext(fs.readFileSync(raiz + "/frontend/js/" + pagina.replace(".html", ".js"), "utf8"), ctx);
  return ctx;
}
(async () => {
  const res = {};
  // ---- Insumos
  const ins = datos.insumos.insumos;
  const leche = ins.find(i => i.nombre === "Leche entera"), canela = ins.find(i => i.puede_eliminar && i.estado === "Activo") || null;
  const ci = contexto("insumos.html", {
    "GET /api/catalogos/insumos": [200, datos.insumos],
    [`PATCH /api/catalogos/insumos/${leche.id_insumo}/estado`]: [409, { detail: "No se puede desactivar «Leche entera». Se usa en: Capuchino, Frappé, Latte. Desactiva o cambia esas recetas primero." }],
  });
  await vm.runInContext("cargarInsumos()", ci);
  const html = ci.elementos["tabla-insumos"].innerHTML;
  const filaDe = n => html.split("<tr>").find(f => f.includes(`<strong>${n}</strong>`)) || "";
  res.filaLeche = filaDe("Leche entera");
  res.filaInactivo = filaDe("Inactivo X");
  // Desactivar: confirmación y luego PATCH con 409 -> mensajeError en la alerta
  vm.runInContext(`confirmarDesactivarInsumo(${leche.id_insumo})`, ci);
  res.confirmDesactivar = { titulo: ci.confirmaciones[0].titulo, mensaje: ci.confirmaciones[0].mensaje };
  res.antesDeConfirmar = ci.peticiones.filter(p => p.metodo === "PATCH").length;
  await ci.confirmaciones[0].onConfirmar();
  res.patch = ci.peticiones.find(p => p.metodo === "PATCH");
  res.msgError = { clase: ci.elementos["msg-insumos"].className, texto: ci.elementos["msg-insumos"].textContent };
  // Eliminar deshabilitado no hace nada; Eliminar habilitado pide confirmación y manda DELETE
  vm.runInContext(`confirmarEliminarInsumo(${leche.id_insumo})`, ci);
  res.eliminarDeshabilitado = ci.confirmaciones.length;
  vm.runInContext(`confirmarEliminarInsumo(9999)`, ci);
  res.confirmEliminar = ci.confirmaciones[1] && ci.confirmaciones[1].titulo;
  await ci.confirmaciones[1].onConfirmar();
  res.delete = ci.peticiones.find(p => p.metodo === "DELETE");
  // ---- Productos
  const prods = datos.productos.productos;
  const vendido = prods.find(p => !p.puede_eliminar);
  const cp = contexto("productos.html", {
    "GET /api/catalogos/productos": [200, datos.productos],
    "GET /api/catalogos/insumos?incluir_inactivos=false": [200, { insumos: ins.filter(i => i.estado === "Activo") }],
    [`PATCH /api/catalogos/productos/${vendido.id_producto}/estado`]: [200, { mensaje: "quedó inactivo" }],
  });
  await vm.runInContext("cargarProductosEInsumos()", cp);
  res.filaProd = cp.elementos["tabla-productos"].innerHTML.split("<tr>").find(f => f.includes(`<strong>${vendido.nombre}</strong>`));
  vm.runInContext(`confirmarDesactivarProducto(${vendido.id_producto})`, cp);
  await cp.confirmaciones[0].onConfirmar();
  res.patchProd = cp.peticiones.find(p => p.metodo === "PATCH");
  res.msgProd = cp.elementos["msg-productos"].className;
  console.log(JSON.stringify(res));
})().catch(e => { console.error(e); process.exit(1); });
"""
    salida = subprocess.run([NODE, "-e", script, json.dumps(datos), str(RAIZ)], capture_output=True, text=True)
    if salida.returncode != 0:
        ok(False, "Node falló: " + salida.stderr[-800:])
    else:
        res = json.loads(salida.stdout.strip().splitlines()[-1])
        fl = res["filaLeche"]
        ok(">Editar</button>" in fl and ">Desactivar</button>" in fl and ">Activar<" not in fl, "insumo activo: Editar + Desactivar")
        ok(re.search(r'<span class="btn-con-motivo" title="Tiene historial \([^"]+\): usa Desactivar"><button[^>]*disabled[^>]*>Eliminar</button></span>', fl),
           "Eliminar deshabilitado con tooltip «Tiene historial (...): usa Desactivar»")
        fi = res["filaInactivo"]
        ok(">Activar</button>" in fi and ">Desactivar<" not in fi and re.search(r'<button[^>]*onclick="confirmarEliminarInsumo\(9999\)"[^>]*>Eliminar', fi) and "disabled" not in fi,
           "insumo inactivo sin historial: Activar + Eliminar habilitado")
        ok(res["confirmDesactivar"]["titulo"] == "¿Desactivar «Leche entera»?" and "Capuchino" in res["confirmDesactivar"]["mensaje"] and res["antesDeConfirmar"] == 0,
           f"Desactivar pide confirmación Sí/No antes de enviar: {res['confirmDesactivar']['mensaje']}")
        ok(res["patch"]["cuerpo"] == json.dumps({"estado": "Inactivo"}, separators=(",", ":")) and res["patch"]["url"].endswith("/estado"),
           f"al confirmar manda PATCH .../estado {res['patch']['cuerpo']}")
        ok(res["msgError"]["clase"] == "alerta-error" and res["msgError"]["texto"].startswith("No se puede desactivar «Leche entera». Se usa en:"),
           f"el 409 se muestra con mensajeError(): {res['msgError']['texto']}")
        ok(res["eliminarDeshabilitado"] == 1, "Eliminar de un insumo con historial no abre la confirmación")
        ok(res["confirmEliminar"] == "¿Eliminar «Inactivo X»?" and res["delete"]["url"] == "/api/catalogos/insumos/9999",
           f"Eliminar pide confirmación y manda DELETE {res['delete']['url']} (sin ?id_usuario)")
        fp = res["filaProd"]
        ok(">Editar</button>" in fp and ">Desactivar</button>" in fp and "disabled" in fp and "usa Desactivar" in fp,
           "productos: Editar + Desactivar + Eliminar deshabilitado con motivo")
        ok(res["patchProd"]["cuerpo"] == json.dumps({"estado": "inactivo"}, separators=(",", ":")) and res["msgProd"] == "badge-verde",
           "productos: Desactivar confirma, manda PATCH y muestra el mensaje")

print()
print("RESULTADO:", "TODO OK" if not fallas else f"{len(fallas)} FALLA(S)")
for f in fallas:
    print("  -", f)
sys.exit(1 if fallas else 0)
