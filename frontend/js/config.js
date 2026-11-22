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
