"""
Prueba de mensajes de error y de cierre de sesión.

Uso (desde backend/):  python3 pruebas/prueba_errores_sesion.py
Usa una base SQLite temporal (o DATABASE_URL si se define, debe estar vacía).
Las partes del frontend (config.js, menu.js) se ejecutan con Node si está instalado.
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
sys.path.insert(0, str(RAIZ / "backend"))
if not os.getenv("DATABASE_URL"):
    os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.mkdtemp()}/prueba_err.db"

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
muestras = {}   # respuestas reales que luego se pasan por mensajeError() en Node

print("== Usuarios: validaciones del backend")
r = c.post("/api/admin/usuarios", headers=A, json={"nombre_usuario": "Nuevo", "correo": "nuevo@x.mx", "contrasena": "abc", "rol": "Cajero"})
ok(r.status_code == 422 and isinstance(r.json()["detail"], list), f"contraseña de 3 caracteres -> {r.status_code} con detail lista")
muestras["pass_corta"] = r.json()
r = c.post("/api/admin/usuarios", headers=A, json={"correo": "x@x.mx", "rol": "Cajero"})
muestras["faltan_campos"] = r.json()
r = c.post("/api/catalogos/productos", headers=A, json={"nombre": "X", "categoria": "Y", "precio_venta": 0, "receta": []})
muestras["producto_invalido"] = r.json()
r = c.post("/api/almacen/mermas", headers=K, json={"id_lote": "abc", "cantidad": "mucho", "motivo": "Derrame"})
muestras["merma_tipos"] = r.json()

r = c.post("/api/admin/usuarios", headers=A, json={"nombre_usuario": "Andres Mosso", "correo": "otro@x.mx", "contrasena": "clave1234", "rol": "Cajero"})
ok(r.status_code == 409 and "ya está en uso" in r.json()["detail"], f"nombre duplicado -> {r.status_code}: {r.json()['detail']}")
r = c.post("/api/admin/usuarios", headers=A, json={"nombre_usuario": "Otro", "correo": "ADMIN@esquinadelcafe.mx", "contrasena": "clave1234", "rol": "Cajero"})
ok(r.status_code == 409 and "ya está registrado" in r.json()["detail"], f"correo duplicado (mayúsculas) -> {r.status_code}: {r.json()['detail']}")
r = c.post("/api/admin/usuarios", headers=A, json={"nombre_usuario": "Otro", "correo": "sin-arroba", "contrasena": "clave1234", "rol": "Cajero"})
ok(r.status_code == 400 and "correo" in r.json()["detail"].lower(), f"correo inválido -> {r.status_code}: {r.json()['detail']}")
r = c.post("/api/admin/usuarios", headers=A, json={"nombre_usuario": "Otro", "correo": "otro@x.mx", "contrasena": "solotexto", "rol": "Cajero"})
ok(r.status_code == 400 and "alfanumérica" in r.json()["detail"], f"contraseña sin números -> {r.status_code}")
r = c.post("/api/admin/usuarios", headers=A, json={"nombre_usuario": "Otro", "correo": "otro@x.mx", "contrasena": "clave1234", "rol": "Cajero"})
ok(r.status_code == 201, f"alta válida -> {r.status_code}")
nuevo = r.json()["id_usuario"]
r = c.put(f"/api/admin/usuarios/{nuevo}", headers=A, json={"nombre_usuario": "Osvaldo Vazquez", "correo": "otro@x.mx", "rol": "Cajero", "estado": "Activo"})
ok(r.status_code == 409, f"editar con nombre de otro usuario -> {r.status_code}")
r = c.put(f"/api/admin/usuarios/{nuevo}", headers=A, json={"nombre_usuario": "Otro", "correo": "otro@x", "rol": "Cajero", "estado": "Activo"})
ok(r.status_code == 400, f"editar con correo inválido -> {r.status_code}")

print("== Merma: contraseña de Administrador incorrecta no cierra la sesión")
lotes = c.get("/api/almacen/lotes", headers=K).json()["lotes"]
cafe = next(l for l in lotes if l["insumo"] == "Café en grano 1 kg")
r = c.post("/api/almacen/mermas", headers=K, json={"id_lote": cafe["id_lote"], "cantidad": 600, "motivo": "Derrame", "password_admin": "mala1234"})
ok(r.status_code == 403, f"contraseña de admin incorrecta -> {r.status_code} (antes 401 = sesión vencida)")

print("== Cache-Control")
for ruta, esperado in [("/usuarios.html", True), ("/login.html", True), ("/caja.html", True),
                       ("/css/estilos.css", False), ("/js/config.js", False), ("/js/menu.js", False)]:
    cc = c.get(ruta).headers.get("cache-control", "")
    ok(("no-store" in cc) == esperado, f"{ruta}: Cache-Control={cc or '(ninguno)'}")
ok("no-store" not in c.get("/api/ventas/motivos-cancelacion").headers.get("cache-control", ""), "el API no lleva no-store")

print("== 401 en TODO el API sin token o con token inválido")
PUBLICAS = {("POST", "/api/auth/login"), ("GET", "/api/ventas/motivos-cancelacion")}
rutas = c.get("/openapi.json").json()["paths"]
revisadas = 0
for ruta, metodos in rutas.items():
    url = re.sub(r"\{[^}]+\}", "1", ruta)
    for metodo in metodos:
        m = metodo.upper()
        if (m, ruta) in PUBLICAS:
            continue
        sin = c.request(m, url, json={}).status_code
        malo = c.request(m, url, json={}, headers={"Authorization": "Bearer token-falso"}).status_code
        query = c.request(m, url + "?token=token-falso", json={}).status_code
        revisadas += 1
        if not (sin == malo == query == 401):
            ok(False, f"{m} {ruta}: sin token={sin}, token falso={malo}, ?token falso={query}")
ok(revisadas >= 25, f"{revisadas} rutas protegidas responden 401 sin token / token falso (cabecera y ?token)")
c.put(f"/api/admin/usuarios/{nuevo}", headers=A, json={"nombre_usuario": "Otro", "correo": "otro@x.mx", "rol": "Cajero", "estado": "Inactivo"})
otro_token = c.post("/api/auth/login", json={"usuario": "otro@x.mx", "contrasena": "clave1234"})
ok(otro_token.status_code == 403, "cuenta desactivada no inicia sesión")

# ------------------------------------------------------------------ frontend
NODE = shutil.which("node")
if not NODE:
    print("== Node no está instalado: se omiten las pruebas del frontend")
else:
    print("== Frontend (Node): mensajeError, 401 y pageshow")
    script = r"""
const fs = require("fs"), vm = require("vm");
const [argMuestras, raiz] = process.argv.slice(-2);
const muestras = JSON.parse(argMuestras);
function contexto(sesion) {
  const almacen = sesion ? { usuario: JSON.stringify(sesion) } : {};
  const oyentes = {};
  const ctx = {
    console, Intl, Date, URLSearchParams, Headers: class { constructor(h) { this.h = Object.assign({}, h); } has(k) { return k in this.h; } set(k, v) { this.h[k] = v; } },
    localStorage: { getItem: k => almacen[k] ?? null, setItem: (k, v) => almacen[k] = v, removeItem: k => delete almacen[k] },
    almacen, oyentes, reemplazos: [], respuestaFalsa: { status: 200 },
    document: { addEventListener() {}, querySelector() { return null; }, getElementById() { return null; }, head: { appendChild() {} }, body: { classList: { add() {}, remove() {} } } },
    setInterval() {},
  };
  ctx.window = { location: { protocol: "http:", hostname: "127.0.0.1", port: "8000", origin: "http://127.0.0.1:8000",
                             pathname: "/usuarios.html", replace: u => ctx.reemplazos.push(u) },
                 fetch: async () => ctx.respuestaFalsa,
                 addEventListener: (ev, fn) => (oyentes[ev] = oyentes[ev] || []).push(fn) };
  ctx.window.window = ctx.window;
  ctx.location = ctx.window.location;
  ctx.addEventListener = ctx.window.addEventListener;
  vm.createContext(ctx);
  vm.runInContext(fs.readFileSync(raiz + "/frontend/js/config.js", "utf8"), ctx);
  vm.runInContext("this.fetch = window.fetch;", ctx);
  return ctx;
}
const res = {};
const c = contexto(null);
for (const [k, v] of Object.entries(muestras)) res[k] = vm.runInContext(`mensajeError(${JSON.stringify(v)})`, c);
res.texto = vm.runInContext(`mensajeError({detail: "El lote no existe."})`, c);
res.vacio500 = vm.runInContext(`mensajeError({}, "No se pudo guardar.", 500)`, c);
res.vacio = vm.runInContext(`mensajeError(null, "No se pudo guardar.")`, c);
res.red = vm.runInContext(`mensajeExcepcion(new TypeError("Failed to fetch"))`, c);

// 401 del API -> limpia la sesión y manda a login.html
const sesion = { id_usuario: 1, token: "t", rol: "Administrador", nombre: "A" };
const c401 = contexto(sesion);
c401.respuestaFalsa = { status: 401 };
vm.runInContext(`fetch(API_BASE + "/api/admin/usuarios")`, c401).then(() => {
  res.r401 = { sesion: c401.almacen.usuario ?? null, reemplazos: c401.reemplazos };
  // 401 del login (contraseña mala) NO cierra nada
  const cLogin = contexto(null); cLogin.respuestaFalsa = { status: 401 };
  return vm.runInContext(`fetch(API_BASE + "/api/auth/login", {method: "POST"})`, cLogin).then(() => { res.r401login = cLogin.reemplazos; });
}).then(() => {
  // menu.js: con sesión no redirige; tras cerrar sesión, pageshow (bfcache) manda a login
  const cm = contexto(sesion);
  vm.runInContext(fs.readFileSync(raiz + "/frontend/js/menu.js", "utf8"), cm);
  res.menuInicial = [...cm.reemplazos];
  delete cm.almacen.usuario;
  (cm.oyentes.pageshow || []).forEach(fn => fn({ persisted: true }));
  res.menuPageshow = cm.reemplazos;
  // Cajero que vuelve con "Atrás" a una pantalla de Administrador
  const cc = contexto({ ...sesion, rol: "Cajero" });
  vm.runInContext(fs.readFileSync(raiz + "/frontend/js/menu.js", "utf8"), cc);
  res.cajeroAdmin = cc.reemplazos;
  // cerrarSesion usa replace
  const cs = contexto(sesion);
  vm.runInContext(fs.readFileSync(raiz + "/frontend/js/menu.js", "utf8") + "\ncerrarSesion();", cs);
  res.logout = { reemplazos: cs.reemplazos, sesion: cs.almacen.usuario ?? null };
  console.log(JSON.stringify(res));
});
"""
    salida = subprocess.run([NODE, "-e", script, json.dumps(muestras), str(RAIZ)], capture_output=True, text=True)
    if salida.returncode != 0:
        ok(False, "Node falló: " + salida.stderr[-500:])
    else:
        res = json.loads(salida.stdout.strip().splitlines()[-1])
        for k in ("pass_corta", "faltan_campos", "producto_invalido", "merma_tipos"):
            print(f"        {k}: {res[k]}")
        ok(res["pass_corta"] == "La contraseña debe tener al menos 8 caracteres.", "422 contraseña corta -> texto en español (no [object Object])")
        ok("El nombre de usuario es obligatorio." in res["faltan_campos"] and "La contraseña es obligatoria." in res["faltan_campos"], "422 campos faltantes")
        ok("El precio de venta debe ser mayor a cero." in res["producto_invalido"] and "La receta" in res["producto_invalido"], "422 producto inválido")
        ok("El lote debe ser un número entero." in res["merma_tipos"] and "La cantidad debe ser un número válido." in res["merma_tipos"], "422 tipos incorrectos")
        ok(not any("[object" in v or "object Object" in v for v in res.values() if isinstance(v, str)), "ningún mensaje es [object Object]")
        ok(res["texto"] == "El lote no existe.", "detail texto se respeta")
        ok(res["vacio500"] == "Error interno del servidor. Intenta de nuevo." and res["vacio"] == "No se pudo guardar.", "sin detail -> texto por estado o de respaldo")
        ok(res["red"].startswith("No se pudo conectar con el servidor"), "fallo de red -> mensaje en español")
        ok(res["r401"] == {"sesion": None, "reemplazos": ["login.html"]}, f"401 del API limpia la sesión y manda a login.html: {res['r401']}")
        ok(res["r401login"] == [], "401 del login (contraseña mala) no redirige")
        ok(res["menuInicial"] == [] and res["menuPageshow"] == ["login.html"], f"pageshow sin sesión (bfcache) -> login.html: {res['menuPageshow']}")
        ok(res["cajeroAdmin"] == ["caja.html"], f"cajero en pantalla de admin -> caja.html: {res['cajeroAdmin']}")
        ok(res["logout"] == {"reemplazos": ["login.html"], "sesion": None}, f"cerrarSesion borra la sesión y usa location.replace: {res['logout']}")

print()
print("RESULTADO:", "TODO OK" if not fallas else f"{len(fallas)} FALLA(S)")
sys.exit(1 if fallas else 0)
