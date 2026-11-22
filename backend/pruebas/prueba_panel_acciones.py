"""
Prueba de los botones de Acciones del Panel principal, badges y botones sin acción.

Uso (desde backend/):  python3 pruebas/prueba_panel_acciones.py
Usa una base SQLite temporal (o DATABASE_URL si se define, debe estar vacía).
Las partes del frontend (inicio.js, caducidades.js, recepcion.js) se ejecutan con Node
si está instalado.
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
    os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.mkdtemp()}/prueba_panel.db"

from fastapi.testclient import TestClient  # noqa: E402

import seed  # noqa: E402
from main import app  # noqa: E402

fallas = []


def ok(cond, msg):
    print(("  OK    " if cond else "  FALLA ") + msg)
    if not cond:
        fallas.append(msg)


seed.poblar_base()
c = TestClient(app)
admin = c.post("/api/auth/login", json={"usuario": "admin@esquinadelcafe.mx", "contrasena": "admin123"}).json()
cajero = c.post("/api/auth/login", json={"usuario": "Osvaldo Vazquez", "contrasena": "cajero123"}).json()
A = {"Authorization": f"Bearer {admin['token']}"}
K = {"Authorization": f"Bearer {cajero['token']}"}

# ------------------------------------------------------------------ backend
print("== Panel: cada alerta trae id_lote, id_insumo y destino")
ok(c.get("/api/dashboard/resumen", headers=K).status_code == 403, "el panel sigue siendo solo de Administrador (cajero -> 403)")
r = c.get("/api/dashboard/resumen", headers=A)
ok(r.status_code == 200, f"GET /api/dashboard/resumen -> {r.status_code}")
resumen = r.json()
alertas = resumen["alertas"]
lotes = {l["id_lote"]: l for l in c.get("/api/almacen/lotes", headers=A).json()["lotes"]}
insumos_recepcion = {i["id_insumo"] for i in c.get("/api/almacen/catalogos", headers=A).json()["insumos"]}

ESPERADO = {
    "Registrar merma": r"^mermas\.html\?lote=(\d+)$",
    "Reabastecer": r"^recepcion\.html\?insumo=(\d+)$",
    "Ver lote": r"^caducidades\.html\?lote=(\d+)$",
}
acciones_vistas = set()
fallas_antes = len(fallas)
for a in alertas:
    acciones_vistas.add(a["accion"])
    patron = ESPERADO.get(a["accion"])
    m = re.match(patron, a.get("destino") or "") if patron else None
    if not (all(k in a for k in ("id_lote", "id_insumo", "destino")) and m):
        ok(False, f"alerta sin destino correcto: {a}")
        continue
    ident = int(m.group(1))
    if a["accion"] == "Reabastecer":
        if ident != a["id_insumo"] or ident not in insumos_recepcion:
            ok(False, f"Reabastecer: el insumo {ident} no está en el catálogo de recepción: {a}")
    else:
        lote = lotes.get(ident)
        if ident != a["id_lote"] or not lote or lote["insumo"] != a["insumo"]:
            ok(False, f"{a['accion']}: el lote {ident} no corresponde a la alerta: {a}")
        elif a["accion"] == "Registrar merma" and not (lote["estado"] == "Caducado" and lote["cantidad_disponible"] > 0):
            ok(False, f"Registrar merma: el lote {ident} debe estar caducado con saldo (mermas.js lo preselecciona): {lote}")
ok(len(alertas) > 0 and len(fallas) == fallas_antes,
   f"{len(alertas)} alertas con destino coherente ({', '.join(sorted(acciones_vistas))})")
ok({"Registrar merma", "Ver lote"} <= acciones_vistas, "los datos de prueba cubren Registrar merma y Ver lote")
if "Reabastecer" not in acciones_vistas:
    # El seed no deja insumos bajo mínimo: se fuerza uno subiendo su mínimo
    from database import SessionLocal  # noqa: E402
    from models import Insumo  # noqa: E402
    with SessionLocal() as db:
        ins = db.query(Insumo).filter(Insumo.estado == "Activo").first()
        ins.minimo_reposicion = 10 ** 9
        db.commit()
        id_forzado = ins.id_insumo
    alertas = c.get("/api/dashboard/resumen", headers=A).json()["alertas"]
    reab = [a for a in alertas if a["accion"] == "Reabastecer" and a["id_insumo"] == id_forzado]
    ok(len(reab) == 1 and reab[0]["destino"] == f"recepcion.html?insumo={id_forzado}" and id_forzado in insumos_recepcion,
       f"Reabastecer (stock bajo forzado) -> {reab[0]['destino'] if reab else 'sin alerta'}")

# ------------------------------------------------------------------ estático
print("== Badges con clase base y botones sin acción")
fuentes = {p: p.read_text(encoding="utf-8") for p in list(FRONT.glob("*.html")) + list((FRONT / "js").glob("*.js"))}
sin_base = [f"{p.name}:{t}" for p, t in fuentes.items() if p.name != "plantilla.html"
            for t in re.findall(r'class=\\?"(badge-[a-z]+)', t)]
ok(not sin_base, f"ningún <span class=\"badge-…\"> sin la clase base 'badge' {sin_base or ''}")

js_todo = "\n".join(t for p, t in fuentes.items() if p.suffix == ".js")
decorativos = []
for p, t in fuentes.items():
    if p.name == "plantilla.html":
        continue
    for boton in re.findall(r"<button\b[^>]*>", t):
        if "onclick=" in boton or 'type="submit"' in boton:
            continue
        ident = re.search(r'id="([^"$]+)"', boton)
        if ident and re.search(rf"[\"'#]{re.escape(ident.group(1))}[\"']", js_todo):
            continue
        clases = re.search(r'class="([^"$]+)"', boton)
        if clases and any(re.search(rf"\.{re.escape(cl)}\b", js_todo) for cl in clases.group(1).split() if cl not in ("btn", "btn-primario", "btn-secundario", "btn-peligro")):
            continue
        decorativos.append(f"{p.name}: {boton[:90]}")
ok(not decorativos, f"todos los <button> tienen acción (onclick, submit, id o clase con listener) {decorativos or ''}")
ok("window.open" not in (FRONT / "js" / "inicio.js").read_text(encoding="utf-8"), "inicio.js no usa window.open")

print("== Estilos: a.btn igual que button.btn, tabla del panel y sin campana")
css = re.sub(r"/\*.*?\*/", "", (FRONT / "css" / "estilos.css").read_text(encoding="utf-8"), flags=re.S)


def regla(selector):
    """Declaraciones de la primera regla cuyo selector (lista separada por comas) incluye `selector`."""
    for sels, cuerpo in re.findall(r"([^{}]+)\{([^}]*)\}", css):
        if selector in [x.strip() for x in sels.split(",")]:
            return cuerpo
    return ""


a_btn = regla("a.btn")
ok("text-decoration: none" in a_btn and "display: inline-flex" in a_btn and "align-items: center" in a_btn,
   "a.btn: sin subrayado, inline-flex y align-items: center")
ok("line-height" in regla(".btn") and "padding: 11px 20px" in regla(".btn") and "border-radius: 8px" in regla(".btn"),
   ".btn fija line-height, padding y border-radius para <button> y <a> por igual")
for variante in ("primario", "secundario", "peligro"):
    ok(regla(f"a.btn-{variante}:visited") == regla(f".btn-{variante}") and regla(f".btn-{variante}"),
       f"a.btn-{variante}:visited conserva el mismo color que .btn-{variante}")
ok(not re.search(r"a\.btn[^{,]*:hover[^{]*\{[^}]*(underline|color:\s*(blue|#00f))", css), "a.btn:hover no se subraya ni cambia a color de enlace")

inicio_html = (FRONT / "inicio.html").read_text(encoding="utf-8")
m = re.search(r"\.tabla-alertas td \{[^}]*padding:\s*(\d+)px", inicio_html)
ok('<table class="tabla-alertas">' in inicio_html and m and 14 <= int(m.group(1)) <= 16,
   f"tabla de alertas con padding vertical de celda 14-16px ({m.group(1) if m else 'sin regla'}px)")

restos = [f"{p.name}" for p, t in fuentes.items() if re.search(r"campana|top-campana|btn-icono", t)]
restos += ["estilos.css"] if re.search(r"campana|btn-icono", css) else []
ok(not restos, f"la campana de Notificaciones ya no existe (HTML, menu.js ni CSS) {restos or ''}")
ok("ponerBadge" in (FRONT / "js" / "menu.js").read_text(encoding="utf-8") and "cargarBadgeCaducidades" in (FRONT / "js" / "menu.js").read_text(encoding="utf-8"),
   "el badge de Caducidades del menú lateral se conserva")

# ------------------------------------------------------------------ frontend
NODE = shutil.which("node")
if not NODE:
    print("== Node no está instalado: se omiten las pruebas del frontend")
else:
    print("== Frontend (Node): inicio.js, caducidades.js y recepcion.js")
    lotes_lista = list(lotes.values())
    id_lote_ver = next(a["id_lote"] for a in alertas if a["accion"] == "Ver lote")
    id_insumo_reab = next(iter(sorted(insumos_recepcion)))
    catalogos = c.get("/api/almacen/catalogos", headers=A).json()
    script = r"""
const fs = require("fs"), vm = require("vm");
const [argDatos, raiz] = process.argv.slice(-2);
const datos = JSON.parse(argDatos);
function contexto(pagina, busqueda, respuestas) {
  const elementos = {};
  const PREDETERMINADOS = { "filtro-estado": "todos", "filtro-venc": "todos" };   // valores iniciales del HTML
  const el = id => elementos[id] = elementos[id] || {
    id, innerHTML: "", textContent: "", value: PREDETERMINADOS[id] || "", style: {}, className: "", required: false,
    addEventListener() {}, focus() { ctx.enfocado = id; }, reset() {},
  };
  const oyentes = {};
  const ctx = {
    console, Intl, Date, URLSearchParams, setTimeout() {}, setInterval() {},
    Headers: class { constructor(h) { this.h = Object.assign({}, h); } has(k) { return k in this.h; } set(k, v) { this.h[k] = v; } },
    localStorage: { getItem: () => JSON.stringify({ id_usuario: 1, token: "t", rol: "Administrador", nombre: "A" }), setItem() {}, removeItem() {} },
    elementos, desplazado: [],
    document: {
      addEventListener: (ev, fn) => (oyentes[ev] = oyentes[ev] || []).push(fn),
      getElementById: el,
      querySelector: sel => {
        const m = sel.match(/data-lote="(\d+)"/);
        if (m && elementos["tabla-caducidades"] && elementos["tabla-caducidades"].innerHTML.includes(`data-lote="${m[1]}"`))
          return { scrollIntoView: () => ctx.desplazado.push(+m[1]) };
        return null;
      },
    },
  };
  ctx.window = { location: { protocol: "http:", hostname: "127.0.0.1", port: "8000", origin: "http://127.0.0.1:8000",
                             pathname: "/" + pagina, search: busqueda, replace() {} },
                 fetch: async u => { const k = Object.keys(respuestas).find(r => u.endsWith(r));
                                     return { ok: true, status: 200, json: async () => respuestas[k] }; },
                 addEventListener() {} };
  ctx.window.window = ctx.window;
  ctx.location = ctx.window.location;
  vm.createContext(ctx);
  vm.runInContext(fs.readFileSync(raiz + "/frontend/js/config.js", "utf8"), ctx);
  vm.runInContext("this.fetch = window.fetch; function escaparHtml(t) { return String(t).replace(/[&<>\"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;',\"'\":'&#39;'}[c])); }", ctx);
  vm.runInContext(fs.readFileSync(raiz + "/frontend/js/" + pagina.replace(".html", ".js"), "utf8"), ctx);
  ctx.disparar = () => Promise.all((oyentes.DOMContentLoaded || []).map(fn => fn()));
  return ctx;
}
const espera = () => new Promise(r => setImmediate(r));
const res = {};
(async () => {
  // inicio.js con la respuesta real del panel (+ un destino malicioso que no debe pintarse)
  const resumen = JSON.parse(JSON.stringify(datos.resumen));
  resumen.alertas.push({ ...resumen.alertas[0], insumo: "<img src=x>", destino: "javascript:alert(1)", accion: "Raro" });
  const ci = contexto("inicio.html", "", { "/api/dashboard/resumen": resumen });
  await ci.disparar(); await espera(); await espera();
  res.inicio = ci.elementos["tabla-alertas-body"].innerHTML;

  const cc = contexto("caducidades.html", "?lote=" + datos.id_lote_ver, { "/api/almacen/lotes": { lotes: datos.lotes } });
  await cc.disparar(); await espera(); await espera();
  res.cad = { html: cc.elementos["tabla-caducidades"].innerHTML, aviso: cc.elementos["aviso-lote"].textContent,
              avisoVisible: cc.elementos["aviso-lote"].style.display, desplazado: cc.desplazado };
  const cc2 = contexto("caducidades.html", "?lote=999999", { "/api/almacen/lotes": { lotes: datos.lotes } });
  await cc2.disparar(); await espera(); await espera();
  res.cadNoExiste = { clase: cc2.elementos["aviso-lote"].className, aviso: cc2.elementos["aviso-lote"].textContent };

  const cr = contexto("recepcion.html", "?insumo=" + datos.id_insumo_reab, { "/api/almacen/catalogos": datos.catalogos, "/api/almacen/lotes": { lotes: [] } });
  await cr.disparar(); await espera(); await espera();
  res.rec = { valor: cr.elementos["rec-insumo"].value, enfocado: cr.enfocado };
  console.log(JSON.stringify(res));
})();
"""
    entrada = {"resumen": resumen | {"alertas": alertas}, "lotes": lotes_lista, "id_lote_ver": id_lote_ver,
               "id_insumo_reab": id_insumo_reab, "catalogos": catalogos}
    salida = subprocess.run([NODE, "-e", script, json.dumps(entrada), str(RAIZ)], capture_output=True, text=True)
    if salida.returncode != 0:
        ok(False, "Node falló: " + salida.stderr[-800:])
    else:
        res = json.loads(salida.stdout.strip().splitlines()[-1])
        html = res["inicio"]
        enlaces = re.findall(r'<a class="btn btn-secundario" href="([^"]+)">([^<]+)</a>', html)
        ok(len(enlaces) == len(alertas), f"inicio.js: {len(enlaces)} enlaces <a href> para {len(alertas)} alertas")
        ok(all(href == a["destino"] for (href, _), a in zip(enlaces, alertas)), "cada enlace lleva al destino de su alerta")
        ok("<button" not in html, "ya no quedan <button> sin handler en la tabla")
        ok("javascript:" not in html and "<img" not in html and "&lt;img" in html, "destino no permitido -> '—' y textos escapados")
        ok(re.search(r'class="badge badge-(rojo|amarillo)"', html) and not re.search(r'class="badge-', html), "estados con class=\"badge badge-…\"")
        cad = res["cad"]
        ok(f'class="fila-roja fila-resaltada" data-lote="{id_lote_ver}"' in cad["html"] or f'fila-resaltada" data-lote="{id_lote_ver}"' in cad["html"],
           f"caducidades.js resalta el lote {id_lote_ver}")
        ok(cad["html"].count("fila-resaltada") == 1, "solo una fila resaltada")
        ok(cad["desplazado"] == [id_lote_ver] and cad["avisoVisible"] == "block" and "Lote resaltado" in cad["aviso"],
           f"lleva la fila a la vista y muestra aviso: {cad['aviso']}")
        ok(res["cadNoExiste"]["clase"] == "alerta-error" and "no existe" in res["cadNoExiste"]["aviso"], "lote inexistente -> aviso de error")
        ok(res["rec"]["valor"] == str(id_insumo_reab) and res["rec"]["enfocado"] == "rec-cantidad",
           f"recepcion.js preselecciona ?insumo={id_insumo_reab} y enfoca la cantidad: {res['rec']}")

print()
print("RESULTADO:", "TODO OK" if not fallas else f"{len(fallas)} FALLA(S)")
for f in fallas:
    print("  -", f)
sys.exit(1 if fallas else 0)
