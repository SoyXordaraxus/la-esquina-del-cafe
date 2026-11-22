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
