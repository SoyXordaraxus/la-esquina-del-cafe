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

/* ---------- Mensajes de error del API ----------
   Convierte cualquier respuesta de error en un texto legible en español:
     - detail como texto (400, 401, 403, 404, 409 de nuestros endpoints)
     - detail como lista de errores 422 de FastAPI/pydantic
     - sin detail (500, respuesta vacía o no JSON) -> texto de respaldo */
const CAMPOS_API = {
  contrasena: ["La contraseña", "f"], correo: ["El correo electrónico", "m"],
  nombre_usuario: ["El nombre de usuario", "m"], usuario: ["El usuario", "m"],
  rol: ["El rol", "m"], estado: ["El estado", "m"],
  nombre: ["El nombre", "m"], categoria: ["La categoría", "f"],
  unidad_medida: ["La unidad base", "f"], unidad_compra: ["La unidad de compra", "f"],
  factor_conversion: ["El factor de conversión", "m"], minimo_reposicion: ["El mínimo de reposición", "m"],
  es_perecedero: ["El campo perecedero", "m"], precio_venta: ["El precio de venta", "m"],
  receta: ["La receta", "f"], cantidad_necesaria: ["La cantidad de la receta", "f"],
  id_insumo: ["El insumo", "m"], id_proveedor: ["El proveedor", "m"], id_lote: ["El lote", "m"],
  id_producto: ["El producto", "m"], cantidad: ["La cantidad", "f"],
  cantidad_ingresada: ["La cantidad recibida", "f"], costo_unitario: ["El costo unitario", "m"],
  caducidad: ["La fecha de caducidad", "f"], numero_factura: ["El número de factura", "m"],
  motivo: ["El motivo", "m"], notas: ["Las notas", "fp"], password_admin: ["La contraseña del Administrador", "f"],
  forma_pago: ["La forma de pago", "f"], monto_recibido: ["El monto recibido", "m"],
  detalles: ["La comanda", "f"], fecha: ["La fecha", "f"],
  fecha_inicio: ["La fecha de inicio", "f"], fecha_fin: ["La fecha final", "f"],
};

const MENSAJES_POR_ESTADO = {
  400: "Los datos enviados no son válidos.",
  401: "Tu sesión expiró. Inicia sesión de nuevo.",
  403: "No tienes permiso para realizar esta acción.",
  404: "No se encontró el recurso solicitado.",
  409: "El registro ya existe o entra en conflicto con otro.",
  422: "Revisa los datos del formulario.",
  500: "Error interno del servidor. Intenta de nuevo.",
};

function _campoApi(loc) {
  const partes = (Array.isArray(loc) ? loc : []).filter(p => !["body", "query", "path"].includes(p));
  const clave = [...partes].reverse().find(p => typeof p === "string");
  if (clave && CAMPOS_API[clave]) return CAMPOS_API[clave];
  if (clave) return [`El campo «${clave.replace(/_/g, " ")}»`, "m"];
  return ["El dato enviado", "m"];
}

function _errorPydantic(e) {
  if (!e || typeof e !== "object") return String(e || "");
  const [campo, genero] = _campoApi(e.loc);
  const ctx = e.ctx || {};
  const oblig = genero === "f" ? "obligatoria" : genero === "fp" ? "obligatorias" : "obligatorio";
  const valida = genero === "f" ? "válida" : genero === "fp" ? "válidas" : "válido";
  const debe = genero === "fp" ? "deben" : "debe";
  switch (e.type) {
    case "missing": return `${campo} es ${oblig}.`;
    case "string_too_short":
      return Number(ctx.min_length) <= 1 ? `${campo} es ${oblig}.` : `${campo} ${debe} tener al menos ${ctx.min_length} caracteres.`;
    case "string_too_long": return `${campo} no puede tener más de ${ctx.max_length} caracteres.`;
    case "too_short":
      return Number(ctx.min_length) === 1 ? `${campo} ${debe} tener al menos un elemento.` : `${campo} ${debe} tener al menos ${ctx.min_length} elementos.`;
    case "greater_than": return Number(ctx.gt) === 0 ? `${campo} ${debe} ser mayor a cero.` : `${campo} ${debe} ser mayor a ${ctx.gt}.`;
    case "greater_than_equal": return `${campo} ${debe} ser mayor o igual a ${ctx.ge}.`;
    case "less_than": return `${campo} ${debe} ser menor a ${ctx.lt}.`;
    case "less_than_equal": return `${campo} ${debe} ser menor o igual a ${ctx.le}.`;
    case "int_parsing": case "int_type": case "int_from_float": return `${campo} ${debe} ser un número entero.`;
    case "float_parsing": case "float_type": case "decimal_parsing": case "decimal_type": return `${campo} ${debe} ser un número válido.`;
    case "date_parsing": case "date_type": case "date_from_datetime_parsing": case "date_from_datetime_inexact":
      return `${campo} no es una fecha válida.`;
    case "bool_parsing": case "bool_type": return `${campo} ${debe} ser sí o no.`;
    case "string_type": return `${campo} ${debe} ser texto.`;
    case "string_pattern_mismatch": return `${campo} no tiene el formato correcto.`;
    case "json_invalid": return "Los datos enviados no tienen un formato válido.";
    case "value_error": return String(e.msg || "").replace(/^Value error,\s*/i, "") || `${campo} no es ${valida}.`;
    default: return `${campo} no es ${valida}.`;
  }
}

function mensajeError(data, respaldo = "Ocurrió un error. Intenta de nuevo.", estado = null) {
  const detalle = data && typeof data === "object" ? data.detail : data;
  if (typeof detalle === "string" && detalle.trim()) return detalle.trim();
  if (Array.isArray(detalle) && detalle.length) {
    const textos = [...new Set(detalle.map(_errorPydantic).filter(Boolean))];
    if (textos.length) return textos.join(" ");
  }
  if (detalle && typeof detalle === "object" && typeof detalle.msg === "string") return detalle.msg;
  if (data && typeof data === "object" && typeof data.mensaje === "string" && data.mensaje) return data.mensaje;
  return (estado && MENSAJES_POR_ESTADO[estado]) || respaldo;
}

// resp.json() sin tronar si el servidor respondió vacío o con texto (p. ej. un 500)
async function leerJsonSeguro(resp) {
  try { return await resp.json(); } catch (e) { return {}; }
}

// Texto para un catch: fallo de red -> mensaje de conexión; Error propio -> su mensaje
function mensajeExcepcion(err, respaldo = "No se pudo completar la operación.") {
  if (err instanceof TypeError && /fetch|network|load failed/i.test(err.message || "")) {
    return "No se pudo conectar con el servidor. Verifica que esté encendido.";
  }
  return (err && err.message) || respaldo;
}
