"""
Prueba de: límite de la comanda según stock compartido (RF 7 / RF 7.1) y
número de factura FAC-#### en Recepción (RF 18).

Uso (desde backend/):  python3 pruebas/prueba_caja_stock_factura.py
Usa una base SQLite temporal (o DATABASE_URL si se define, debe estar vacía).
Las partes del frontend (caja.js, recepcion.js) se ejecutan con Node si está instalado.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import timedelta
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(RAIZ / "backend"))
if not os.getenv("DATABASE_URL"):
    os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.mkdtemp()}/prueba_caja_factura.db"

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import select, update  # noqa: E402

import seed  # noqa: E402
from database import SessionLocal  # noqa: E402
from main import app  # noqa: E402
from models import Insumo, LoteInsumo  # noqa: E402
from services.tiempo import hoy_local  # noqa: E402

fallas = []


def ok(cond, msg):
    print(("  OK    " if cond else "  FALLA ") + msg)
    if not cond:
        fallas.append(msg)


seed.poblar_base()
c = TestClient(app)
A = {"Authorization": f"Bearer {c.post('/api/auth/login', json={'usuario': 'admin@esquinadelcafe.mx', 'contrasena': 'admin123'}).json()['token']}"}
K = {"Authorization": f"Bearer {c.post('/api/auth/login', json={'usuario': 'Osvaldo Vazquez', 'contrasena': 'cajero123'}).json()['token']}"}


def disponibles():
    return c.get("/api/ventas/productos-disponibles", headers=K).json()


# ------------------------------------------------------------------ escenario controlado
# Leche para exactamente 10 lattes (200 ml c/u) y 13 capuchinos (150 ml c/u): 2000 ml vigentes.
# Además: un lote de leche caducado y uno Agotado que NO deben contar.
with SessionLocal() as db:
    leche = db.scalar(select(Insumo).where(Insumo.nombre == "Leche entera"))
    cafe = db.scalar(select(Insumo).where(Insumo.nombre == "Café molido"))
    ID_LECHE, ID_CAFE = leche.id_insumo, cafe.id_insumo
    db.execute(update(LoteInsumo).where(LoteInsumo.id_insumo == ID_LECHE).values(cantidad_disponible=0, estado="Agotado"))
    hoy = hoy_local()
    db.add_all([
        LoteInsumo(id_insumo=ID_LECHE, cantidad_recibida=2000, cantidad_disponible=2000, costo_unitario=20,
                   caducidad=hoy + timedelta(days=5), numero_factura="FAC-7001", estado="Disponible"),
        LoteInsumo(id_insumo=ID_LECHE, cantidad_recibida=5000, cantidad_disponible=5000, costo_unitario=20,
                   caducidad=hoy - timedelta(days=1), numero_factura="FAC-7002", estado="Disponible"),   # vencido por fecha
        LoteInsumo(id_insumo=ID_LECHE, cantidad_recibida=5000, cantidad_disponible=5000, costo_unitario=20,
                   caducidad=hoy + timedelta(days=5), numero_factura="FAC-7003", estado="Caducado"),     # marcado Caducado
    ])
    db.commit()

print("== /api/ventas/productos-disponibles: receta, max_porciones y stock_insumos")
d = disponibles()
prods = {p["nombre"]: p for p in d["productos"]}
latte, capu, americano, panini, pastel = (prods[n] for n in ("Latte", "Capuchino", "Café americano", "Panini", "Pastel"))
ok(d["stock_insumos"].get(str(ID_LECHE)) == 2000, f"stock vigente de leche = 2000 (ignora caducados/agotados) -> {d['stock_insumos'].get(str(ID_LECHE))}")
ok(d["stock_insumos"].get(str(ID_CAFE)) == 5000, f"stock vigente de café = 5000 -> {d['stock_insumos'].get(str(ID_CAFE))}")
ok(sorted((r["id_insumo"], r["cantidad"]) for r in latte["receta"]) == sorted([(ID_CAFE, 18.0), (ID_LECHE, 200.0)]),
   f"receta de Latte = café 18 + leche 200 -> {latte['receta']}")
ok(latte["max_porciones"] == 10, f"max_porciones Latte = 10 (2000/200) -> {latte['max_porciones']}")
ok(capu["max_porciones"] == 13, f"max_porciones Capuchino = 13 (2000/150) -> {capu['max_porciones']}")
ok(americano["max_porciones"] == 277, f"max_porciones Americano = 277 (5000/18) -> {americano['max_porciones']}")
ok(panini["max_porciones"] == 40, f"max_porciones Panini = 40 (limita el pan: 40 pzas) -> {panini['max_porciones']}")
ok(pastel["max_porciones"] == 0 and pastel["disponible"] is False, "Pastel con lote agotado -> max_porciones 0, disponible false")
ok(all(p["disponible"] == (p["max_porciones"] > 0) for p in d["productos"]), "disponible == (max_porciones > 0) en todos")

print("== El backend sigue validando al cobrar (RF 7)")
r = c.post("/api/ventas/cobrar", headers=K, json={"forma_pago": "Tarjeta externa", "detalles": [
    {"id_producto": latte["id_producto"], "cantidad": 6}, {"id_producto": capu["id_producto"], "cantidad": 6}]})
ok(r.status_code == 409, f"6 lattes + 6 capuchinos (2100 ml > 2000) -> 409 aunque cada uno por separado cabría: {r.status_code}")
r = c.post("/api/ventas/cobrar", headers=K, json={"forma_pago": "Tarjeta externa", "detalles": [
    {"id_producto": latte["id_producto"], "cantidad": 7}, {"id_producto": capu["id_producto"], "cantidad": 4}]})
ok(r.status_code == 201, f"7 lattes + 4 capuchinos (2000 ml exactos) -> 201: {r.status_code}")
d2 = {p["nombre"]: p for p in disponibles()["productos"]}
ok(d2["Latte"]["max_porciones"] == 0 and not d2["Latte"]["disponible"] and d2["Capuchino"]["max_porciones"] == 0,
   "tras la venta ya no hay leche -> Latte y Capuchino con max_porciones 0")

# ------------------------------------------------------------------ recepción: número de factura
print("== Recepción: número de factura FAC-#### (RF 18)")
with SessionLocal() as db:
    ID_PAN = db.scalar(select(Insumo.id_insumo).where(Insumo.nombre == "Pan para panini"))
    ID_QUESO = db.scalar(select(Insumo.id_insumo).where(Insumo.nombre == "Queso para panini"))
cad = str(hoy_local() + timedelta(days=5))


def recibir(factura, id_insumo=None, **extra):
    cuerpo = {"id_insumo": id_insumo or ID_PAN, "cantidad_ingresada": 1, "unidad_compra": "paq", "costo_unitario": 60, "caducidad": cad, **extra}
    if factura is not ...:
        cuerpo["numero_factura"] = factura
    return c.post("/api/almacen/recepcion", headers=K, json=cuerpo)


for invalida in ("555555", "FAC-12", "FAC-123456789", "FAC-12a4", "FAC 1045", "LA-001", "FAC-", "XFAC-1045"):
    r = recibir(invalida)
    ok(r.status_code == 400 and "FAC-" in r.json().get("detail", ""), f"factura «{invalida}» -> 400: {r.json().get('detail')}")
r = recibir(...)
ok(r.status_code == 400 and "obligatorio" in r.json()["detail"], f"sin factura -> 400: {r.json().get('detail')}")
r = recibir("   ")
ok(r.status_code == 400 and "obligatorio" in r.json()["detail"], "factura en blanco -> 400")

r = recibir("FAC-1045")
ok(r.status_code == 201 and r.json().get("id_lote"), f"FAC-1045 válida -> 201: {r.status_code}")
r = recibir("FAC-45425678")
ok(r.status_code == 201, f"FAC- con 8 dígitos -> 201: {r.status_code}")
r = recibir("FAC-1045")
ok(r.status_code == 409 and r.json()["detail"] == "Esa factura ya fue registrada para este insumo.",
   f"FAC-1045 repetida para el mismo insumo -> 409: {r.json().get('detail')}")
r = recibir(" fac-1045 ")
ok(r.status_code == 409, f"misma factura con espacios/minúsculas -> 409: {r.status_code}")
r = recibir("FAC-1045", id_insumo=ID_QUESO, unidad_compra="kg")
ok(r.status_code == 201, f"misma factura para OTRO insumo (una factura trae varios insumos) -> 201: {r.status_code}")
lotes = c.get("/api/almacen/lotes", headers=A).json()["lotes"]
ok(sum(1 for l in lotes if l["numero_factura"] == "FAC-1045") == 2, "se guardaron 2 lotes con FAC-1045 (pan y queso)")

print("== Seed y lotes existentes")
with SessionLocal() as db:
    facturas = [f for (f,) in db.execute(select(LoteInsumo.numero_factura))]
    import re
    ok(all(re.fullmatch(r"FAC-\d{3,8}", f or "") for f in facturas), "todos los lotes del seed (y de esta prueba) usan FAC-####")
    # Un lote viejo con otro formato no estorba: se puede seguir vendiendo/listando
    db.add(LoteInsumo(id_insumo=ID_PAN, cantidad_recibida=5, cantidad_disponible=5, costo_unitario=60,
                      caducidad=hoy_local() + timedelta(days=5), numero_factura="LA-001", estado="Disponible"))
    db.commit()
ok(c.get("/api/almacen/lotes", headers=A).status_code == 200 and any(l["numero_factura"] == "LA-001" for l in c.get("/api/almacen/lotes", headers=A).json()["lotes"]),
   "un lote antiguo con «LA-001» se sigue listando (solo se validan los nuevos)")
ok(recibir("FAC-2001").status_code == 201, "y se pueden recibir lotes nuevos para ese insumo")

# ------------------------------------------------------------------ frontend
NODE = shutil.which("node")
if not NODE:
    print("== Node no está instalado: se omiten las pruebas del frontend")
else:
    print("== Frontend (Node): caja.js limita la comanda y recepcion.js arma FAC-####")
    # Catálogo controlado: leche para 10 lattes / 13 capuchinos
    catalogo = {
        "productos": [
            {"id_producto": 1, "nombre": "Latte", "categoria": "Bebidas calientes", "precio": 50, "disponible": True, "max_porciones": 10,
             "receta": [{"id_insumo": 1, "cantidad": 18}, {"id_insumo": 2, "cantidad": 200}]},
            {"id_producto": 2, "nombre": "Capuchino", "categoria": "Bebidas calientes", "precio": 45, "disponible": True, "max_porciones": 13,
             "receta": [{"id_insumo": 1, "cantidad": 18}, {"id_insumo": 2, "cantidad": 150}]},
            {"id_producto": 3, "nombre": "Americano", "categoria": "Bebidas calientes", "precio": 35, "disponible": True, "max_porciones": 277,
             "receta": [{"id_insumo": 1, "cantidad": 18}]},
            {"id_producto": 4, "nombre": "Pastel", "categoria": "Bebidas calientes", "precio": 40, "disponible": False, "max_porciones": 0,
             "receta": [{"id_insumo": 3, "cantidad": 1}]},
        ],
        "stock_insumos": {"1": 5000, "2": 2000, "3": 0},
    }
    script = r"""
const fs = require("fs"), vm = require("vm");
const [argDatos, raiz] = process.argv.slice(-2);
const datos = JSON.parse(argDatos);
function contexto(pagina, respuestas) {
  const elementos = {}, oyentes = {};
  // innerHTML = "..." vacía los hijos, como en el navegador
  const el = id => elementos[id] = elementos[id] || { id, _html: "", get innerHTML() { return this._html; }, set innerHTML(v) { this._html = v; this.children = []; },
    textContent: "", value: "", style: {}, className: "", children: [],
    addEventListener(t, f) { (oyentes[id + ":" + t] = oyentes[id + ":" + t] || []).push(f); }, reset() {},
    appendChild(h) { this.children.push(h); } };
  const ctx = {
    console, Intl, Date, URLSearchParams, setTimeout() {}, setInterval() {}, peticiones: [], alertas: [], elementos, oyentes,
    Headers: class { constructor(h) { this.h = Object.assign({}, h); } has(k) { return k in this.h; } set(k, v) { this.h[k] = v; } },
    localStorage: { getItem: () => JSON.stringify({ id_usuario: 1, token: "t", rol: "Cajero", nombre: "K" }), setItem() {}, removeItem() {} },
    alert: m => ctx.alertas.push(m),
    document: { addEventListener(t, f) { if (t === "DOMContentLoaded") ctx.alCargar = f; }, getElementById: el, querySelectorAll: () => [], querySelector: () => ({ checked: true, value: "Efectivo" }),
                createElement: t => ({ tag: t, innerHTML: "", disabled: false, className: "", clicks: [], addEventListener(ev, f) { this.clicks.push(f); } }) },
  };
  ctx.window = { location: { protocol: "http:", hostname: "127.0.0.1", port: "8000", origin: "http://127.0.0.1:8000", pathname: "/" + pagina, search: "", replace() {} },
                 fetch: async (u, o = {}) => {
                   const url = u.replace("http://127.0.0.1:8000", "");
                   ctx.peticiones.push({ url, metodo: o.method || "GET", cuerpo: o.body || null });
                   const k = Object.keys(respuestas).find(r => r === (o.method || "GET") + " " + url);
                   const [status, cuerpo] = respuestas[k] || [200, {}];
                   return { ok: status < 400, status, json: async () => cuerpo };
                 }, addEventListener() {} };
  ctx.window.window = ctx.window;
  ctx.location = ctx.window.location;
  vm.createContext(ctx);
  vm.runInContext(fs.readFileSync(raiz + "/frontend/js/config.js", "utf8"), ctx);
  vm.runInContext(`this.fetch = window.fetch;
    function escaparHtml(t) { return String(t).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])); }
    function abrirModal() {} function cerrarModal() {} function idUsuarioActual() { return 1; } function obtenerUsuario() { return { id_usuario: 1 }; }`, ctx);
  vm.runInContext(fs.readFileSync(raiz + "/frontend/js/" + pagina.replace(".html", ".js"), "utf8"), ctx);
  return ctx;
}
(async () => {
  const res = {};
  // ---------------- Caja
  const cj = contexto("caja.html", { "GET /api/ventas/productos-disponibles": [200, datos.catalogo] });
  await vm.runInContext("cargarProductos()", cj);
  const grid = () => cj.elementos["productos-grid"].children;
  const boton = n => grid().find(b => b.innerHTML.includes(">" + n + "<"));
  res.quedanInicial = grid().map(b => (b.innerHTML.match(/Quedan (\d+)/) || [])[1]);
  res.pastelDeshabilitado = boton("Pastel").disabled;
  // 6 lattes tocando el producto
  for (let i = 0; i < 6; i++) boton("Latte").clicks[0]();
  res.quedanCapu = (boton("Capuchino").innerHTML.match(/Quedan (\d+)/) || [])[1];
  res.quedanLatte = (boton("Latte").innerHTML.match(/Quedan (\d+)/) || [])[1];
  // capuchinos: con leche para 2000 - 1200 = 800 ml -> solo caben 5 (150 c/u)
  for (let i = 0; i < 4; i++) boton("Capuchino").clicks[0]();
  res.quedanCapuTras4 = (boton("Capuchino").innerHTML.match(/Quedan (\d+)/) || [])[1];
  vm.runInContext("cambiarCantidad(2, 1)", cj);    // "+" del capuchino -> 5 (cabe)
  res.alertaAntes = cj.elementos["alerta-stock"].style.display;
  res.comanda5 = vm.runInContext("JSON.stringify(comanda.map(i => [i.nombre, i.cantidad]))", cj);
  res.capuAgotado = { disabled: boton("Capuchino").disabled, html: boton("Capuchino").innerHTML };
  res.latteAgotado = boton("Latte").disabled;                        // 6*200 + 5*150 = 1950 -> no cabe otro latte
  res.americanoLibre = boton("Americano").disabled;
  res.htmlComanda = cj.elementos["comanda-tbody"].children.map(tr => tr.innerHTML);
  vm.runInContext("cambiarCantidad(2, 1)", cj);    // ya no cabe: no suma y avisa
  res.comandaTrasExceso = vm.runInContext("JSON.stringify(comanda.map(i => [i.nombre, i.cantidad]))", cj);
  res.aviso = { display: cj.elementos["alerta-stock"].style.display, texto: cj.elementos["alerta-stock"].textContent };
  vm.runInContext("agregarAComanda(buscarProducto(1))", cj);   // tocar Latte agotado (por si llega a llamarse)
  res.comandaTrasLatte = vm.runInContext("JSON.stringify(comanda.map(i => [i.nombre, i.cantidad]))", cj);
  res.avisoLatte = cj.elementos["alerta-stock"].textContent;
  vm.runInContext("cambiarCantidad(1, -1)", cj);   // quitar un latte libera 200 ml -> cabe 1 capuchino más
  res.quedanCapuTrasQuitar = (boton("Capuchino").innerHTML.match(/Quedan (\d+)/) || [])[1];
  // Cobro rechazado -> vuelve a pedir disponibilidad
  const antes = cj.peticiones.filter(p => p.url.endsWith("/productos-disponibles")).length;
  vm.runInContext(`window.fetch = async (u, o = {}) => { peticiones.push({ url: u.replace("http://127.0.0.1:8000", ""), metodo: o.method || "GET" });
    if ((o.method || "GET") === "POST") return { ok: false, status: 409, json: async () => ({ detail: "Inventario insuficiente. No se realizó el cobro." }) };
    return { ok: true, status: 200, json: async () => (${JSON.stringify(datos.catalogo)}) }; }; this.fetch = window.fetch;`, cj);
  cj.document.getElementById("input-recibido").value = "10000";
  await vm.runInContext("procesarVenta()", cj);
  await new Promise(r => setImmediate(r));
  res.recargasTrasRechazo = cj.peticiones.filter(p => p.url.endsWith("/productos-disponibles")).length - antes;
  res.alertaRechazo = cj.elementos["alerta-stock"].textContent;
  // Cobro exitoso -> vacía comanda y vuelve a cargar
  vm.runInContext(`window.fetch = async (u, o = {}) => { peticiones.push({ url: u.replace("http://127.0.0.1:8000", ""), metodo: o.method || "GET" });
    if ((o.method || "GET") === "POST") return { ok: true, status: 201, json: async () => ({ id_venta: 9 }) };
    return { ok: true, status: 200, json: async () => (${JSON.stringify(datos.catalogo)}) }; }; this.fetch = window.fetch;`, cj);
  const antes2 = cj.peticiones.filter(p => p.url.endsWith("/productos-disponibles")).length;
  await vm.runInContext("procesarVenta()", cj);
  await new Promise(r => setImmediate(r));
  res.recargasTrasCobro = cj.peticiones.filter(p => p.url.endsWith("/productos-disponibles")).length - antes2;
  res.comandaTrasCobro = vm.runInContext("comanda.length", cj);

  // ---------------- Recepción
  const rc = contexto("recepcion.html", { "GET /api/almacen/catalogos": [200, { insumos: [{ id_insumo: 5, nombre: "Pan", unidad_medida: "pza", unidad_compra: "paq" }], proveedores: [] }],
                                          "POST /api/almacen/recepcion": [201, { mensaje: "Lote registrado", cantidad_guardada: 10, unidad_base: "pza", insumo: "Pan" }] });
  rc.alCargar();
  await new Promise(r => setImmediate(r));
  const fac = rc.elementos["rec-factura"];
  fac.value = "FAC-10a45"; rc.oyentes["rec-factura:input"].forEach(f => f());
  res.facturaFiltrada = fac.value;
  Object.assign(rc.document.getElementById("rec-insumo"), { value: "5" });
  Object.assign(rc.document.getElementById("rec-cantidad"), { value: "1" });
  Object.assign(rc.document.getElementById("rec-unidad"), { value: "paq" });
  Object.assign(rc.document.getElementById("rec-costo"), { value: "60" });
  const enviar = () => Promise.all(rc.oyentes["form-recepcion:submit"].map(f => f({ preventDefault() {} })));
  fac.value = "12";
  await enviar();
  res.postCorto = rc.peticiones.filter(p => p.metodo === "POST").length;
  res.msgCorto = rc.elementos["alerta-recepcion"].innerHTML;
  fac.value = "1045";
  await enviar();
  const post = rc.peticiones.find(p => p.metodo === "POST");
  res.cuerpoRecepcion = post && JSON.parse(post.cuerpo);
  console.log(JSON.stringify(res));
})().catch(e => { console.error(e); process.exit(1); });
"""
    salida = subprocess.run([NODE, "-e", script, json.dumps({"catalogo": catalogo}), str(RAIZ)], capture_output=True, text=True)
    if salida.returncode != 0:
        ok(False, "Node falló: " + salida.stderr[-1500:])
    else:
        res = json.loads(salida.stdout.strip().splitlines()[-1])
        ok(res["quedanInicial"][:3] == ["10", "13", "277"], f"cuadrícula muestra «Quedan N» por producto: {res['quedanInicial']}")
        ok(res["pastelDeshabilitado"], "producto sin stock deshabilitado en la cuadrícula")
        ok(res["quedanLatte"] == "4" and res["quedanCapu"] == "5",
           f"con 6 lattes en la comanda: quedan 4 lattes y 5 capuchinos (leche compartida) -> {res['quedanLatte']} / {res['quedanCapu']}")
        ok(res["quedanCapuTras4"] == "1", f"tras 4 capuchinos queda 1 -> {res['quedanCapuTras4']}")
        ok(res["comanda5"] == json.dumps([["Latte", 6], ["Capuchino", 5]], separators=(",", ":")) and res["alertaAntes"] == "none",
           f"«+» suma mientras cabe: {res['comanda5']}")
        ok(res["capuAgotado"]["disabled"] and "Agotado" in res["capuAgotado"]["html"] and "Quedan 0" in res["capuAgotado"]["html"],
           "Capuchino marcado Agotado / Quedan 0 en la cuadrícula cuando ya no cabe ninguno")
        ok(res["latteAgotado"] and res["americanoLibre"] is False, "Latte también agotado (comparte leche); Americano (sin leche) sigue disponible")
        ok(all('disabled title="No hay insumos para más"' in h for h in res["htmlComanda"]), "botón «+» deshabilitado en la comanda para Latte y Capuchino")
        ok(res["comandaTrasExceso"] == res["comanda5"], f"«+» sin insumos no suma: {res['comandaTrasExceso']}")
        ok(res["aviso"]["display"] == "block" and res["aviso"]["texto"] == "Solo hay insumos para 5 Capuchino con lo que ya llevas en la comanda.",
           f"aviso claro: {res['aviso']['texto']}")
        ok(res["comandaTrasLatte"] == res["comanda5"] and res["avisoLatte"].startswith("Solo hay insumos para 6 Latte"),
           f"tocar un producto que ya no cabe no lo agrega: {res['avisoLatte']}")
        ok(res["quedanCapuTrasQuitar"] == "1", f"al quitar un latte se libera leche: vuelve a caber 1 capuchino -> {res['quedanCapuTrasQuitar']}")
        ok(res["recargasTrasRechazo"] == 1 and "Inventario insuficiente" in res["alertaRechazo"], "cobro rechazado -> muestra el error y vuelve a cargar disponibilidad")
        ok(res["recargasTrasCobro"] == 1 and res["comandaTrasCobro"] == 0, "cobro exitoso -> vacía la comanda y vuelve a cargar disponibilidad")
        ok(res["facturaFiltrada"] == "1045", f"el input de factura solo deja dígitos (pegar «FAC-10a45» -> «{res['facturaFiltrada']}»)")
        ok(res["postCorto"] == 0 and "3 a 8 d" in res["msgCorto"], "factura con menos de 3 dígitos no se envía y muestra aviso")
        ok(res["cuerpoRecepcion"] and res["cuerpoRecepcion"]["numero_factura"] == "FAC-1045", f"se envía numero_factura «FAC-1045»: {res['cuerpoRecepcion']}")

print()
print("RESULTADO:", "TODO OK" if not fallas else f"{len(fallas)} FALLA(S)")
for f in fallas:
    print("  -", f)
sys.exit(1 if fallas else 0)
