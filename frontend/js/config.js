/* =========================================================
   config.js - Dirección única del API (cargar ANTES que cualquier otro script)
   La Esquina del Café
   ========================================================= */
const PUERTO_API = "8000";

const API_BASE = (() => {
  const { protocol, hostname, port, origin } = window.location;

  // HTML abierto con doble clic (file://): backend local
  if (protocol === "file:") return `http://127.0.0.1:${PUERTO_API}`;

  // GitHub Codespaces: https://<nombre>-<puerto>.app.github.dev
  if (hostname.includes("github.dev")) return origin.replace(/-\d+\./, `-${PUERTO_API}.`);

  // Servido por FastAPI (uvicorn en el 8000) o detrás de un proxy sin puerto
  if (port === PUERTO_API || port === "") return origin;

  // Otro servidor estático (Live Server en 5500, etc.): mismo host, puerto del API
  return `${protocol}//${hostname}:${PUERTO_API}`;
})();

/* ---------- Sesión: token que entrega /api/auth/login ---------- */
const CLAVE_SESION = "usuario";   // localStorage["usuario"] = { id_usuario, nombre_usuario, nombre, rol, token }

function leerSesion() {
  try {
    const s = JSON.parse(localStorage.getItem(CLAVE_SESION));
    if (s && s.id_usuario && s.token && (s.rol === "Administrador" || s.rol === "Cajero")) return s;
  } catch (e) { /* sesión dañada */ }
  return null;
}

function irALogin() {
  try { localStorage.removeItem(CLAVE_SESION); } catch (e) { /* nada */ }
  if (!/login\.html$/i.test(window.location.pathname)) window.location.replace("login.html");
}

// Para enlaces de descarga y window.open (no pueden mandar cabeceras)
function conToken(url) {
  const s = leerSesion();
  if (!s) return url;
  return url + (url.includes("?") ? "&" : "?") + "token=" + encodeURIComponent(s.token);
}

// Toda petición al API lleva "Authorization: Bearer <token>". Si el servidor responde
// 401 (sin sesión, expirada o cuenta desactivada) se regresa al login.
(() => {
  const fetchOriginal = window.fetch.bind(window);
  window.fetch = async (recurso, opciones = {}) => {
    const url = typeof recurso === "string" ? recurso : (recurso && recurso.url) || "";
    const esApi = url.startsWith(`${API_BASE}/api/`);
    const esLogin = url.includes("/api/auth/login");
    const sesion = leerSesion();
    if (esApi && !esLogin && sesion) {
      const cabeceras = new Headers(opciones.headers || {});
      if (!cabeceras.has("Authorization")) cabeceras.set("Authorization", `Bearer ${sesion.token}`);
      opciones = { ...opciones, headers: cabeceras };
    }
    const resp = await fetchOriginal(recurso, opciones);
    if (esApi && !esLogin && resp.status === 401) irALogin();
    return resp;
  };
})();

/* ---------- Zona horaria del negocio ----------
   La define el backend (TZ_NEGOCIO) y llega en la respuesta del login.
   Todo lo de calendario ("hoy", fechas mostradas) se calcula en esa zona,
   no en la del navegador ni en la del servidor (UTC). */
const ZONA_POR_OMISION = "America/Mexico_City";

function zonaNegocio() {
  const s = leerSesion();
  return (s && s.zona_horaria) || ZONA_POR_OMISION;
}

// "AAAA-MM-DD" de hoy en el negocio; desplazamientoDias = -7 -> hace una semana
function hoyNegocioISO(desplazamientoDias = 0) {
  const partes = new Intl.DateTimeFormat("en-CA", {
    timeZone: zonaNegocio(), year: "numeric", month: "2-digit", day: "2-digit",
  }).formatToParts(new Date());
  const v = Object.fromEntries(partes.map(p => [p.type, p.value]));
  const d = new Date(Date.UTC(+v.year, +v.month - 1, +v.day + desplazamientoDias));
  return d.toISOString().slice(0, 10);
}

// ISO del API (con desfase, p. ej. 2026-11-21T23:30:00-06:00) -> "21/11/2026, 23:30"
function fechaHoraNegocio(iso, opciones = {}) {
  if (!iso) return "";
  const d = new Date(iso);
  if (isNaN(d)) return String(iso);
  return d.toLocaleString("es-MX", {
    timeZone: zonaNegocio(), day: "2-digit", month: "2-digit", year: "numeric",
    hour: "2-digit", minute: "2-digit", hour12: false, ...opciones,
  });
}
