/* =========================================================
   menu.js - Barra superior + menú lateral + modales globales
   La Esquina del Café
   ========================================================= */
const MOSTRAR_SELECTOR_ROL = false;
const PAGINA_LOGIN = "login.html";

const CLAVE_USUARIO = "usuario";
const USUARIO_PRUEBA = { id_usuario: 1, nombre: "Andres Mosso", rol: "Administrador" };
const BADGES_INICIALES = { "caducidades.html": 4 };

/* ---------- Iconos (SVG de línea, sin librerías) ---------- */
const ICONOS = {
  inicio:      "M3 11l9-8 9 8v9a1 1 0 0 1-1 1h-5v-6H9v6H4a1 1 0 0 1-1-1z",
  caja:        "M12 2l9 5v10l-9 5-9-5V7zM3 7l9 5 9-5M12 12v10",
  recepcion:   "M2 5h7a3 3 0 0 1 3 3v12a2 2 0 0 0-2-2H2zM22 5h-7a3 3 0 0 0-3 3v12a2 2 0 0 1 2-2h8z",
  mermas:      "M3 12a9 9 0 1 0 3-6.7L3 8M3 3v5h5M12 8v4l3 2",
  inventario:  "M12 3a3 3 0 1 0 0 6 3 3 0 0 0 0-6zM6 13a3 3 0 1 0 0 6 3 3 0 0 0 0-6zM18 13a3 3 0 1 0 0 6 3 3 0 0 0 0-6z",
  caducidades: "M4 6h16v14H4zM4 10h16M8 3v4M16 3v4",
  insumos:     "M2 5h7a3 3 0 0 1 3 3v12a2 2 0 0 0-2-2H2zM22 5h-7a3 3 0 0 0-3 3v12a2 2 0 0 1 2-2h8z",
  productos:   "M12 2l9 5v10l-9 5-9-5V7zM3 7l9 5 9-5M12 12v10",
  ventas:      "M5 8h14l-1 12H6zM9 8a3 3 0 0 1 6 0",
  reportes:    "M4 20V10M10 20V4M16 20v-8M22 20H2",
  usuarios:    "M16 20v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2M10 10a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7z",
  bitacora:    "M9 4h6v3H9zM7 5H6a1 1 0 0 0-1 1v14a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1V6a1 1 0 0 0-1-1h-1M9 12h6M9 16h6",
  respaldos:   "M4 6c0-1.7 3.6-3 8-3s8 1.3 8 3-3.6 3-8 3-8-1.3-8-3zM4 6v12c0 1.7 3.6 3 8 3s8-1.3 8-3V6M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3",
  campana:     "M6 8a6 6 0 1 1 12 0c0 7 3 9 3 9H3s3-2 3-9M10 21a2 2 0 0 0 4 0",
  grano:       "M12 3c4 2 6 6 6 9s-2 7-6 9c-4-2-6-6-6-9s2-7 6-9zM12 3c-2 4-2 10 0 18",
};

function svg(nombre, tam = 18) {
  return `<svg width="${tam}" height="${tam}" viewBox="0 0 24 24" fill="none" stroke="currentColor"
    stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="${ICONOS[nombre]}"/></svg>`;
}

/* ---------- Opciones del menú y roles que las ven ---------- */
const MENU_ITEMS = [
  { archivo: "inicio.html",      texto: "Inicio",      icono: "inicio",      roles: ["Administrador"] },
  { archivo: "caja.html",        texto: "Caja",        icono: "caja",        roles: ["Administrador", "Cajero"] },
  { archivo: "recepcion.html",   texto: "Recepción",   icono: "recepcion",   roles: ["Administrador", "Cajero"] },
  { archivo: "mermas.html",      texto: "Mermas",      icono: "mermas",      roles: ["Administrador", "Cajero"] },
  { archivo: "semaforo.html",    texto: "Inventario",  icono: "inventario",  roles: ["Administrador"] },
  { archivo: "caducidades.html", texto: "Caducidades", icono: "caducidades", roles: ["Administrador"] },
  { archivo: "insumos.html",     texto: "Insumos",     icono: "insumos",     roles: ["Administrador"] },
  { archivo: "productos.html",   texto: "Productos",   icono: "productos",   roles: ["Administrador"] },
  { archivo: "ventas.html",      texto: "Ventas",      icono: "ventas",      roles: ["Administrador"] },
  { archivo: "reportes.html",    texto: "Reportes",    icono: "reportes",    roles: ["Administrador"] },
  { archivo: "usuarios.html",    texto: "Usuarios",    icono: "usuarios",    roles: ["Administrador"] },
  { archivo: "bitacora.html",    texto: "Bitácora",    icono: "bitacora",    roles: ["Administrador"] },
  { archivo: "respaldos.html",   texto: "Respaldos",   icono: "respaldos",   roles: ["Administrador"] },
];

/* ---------- Utilidades ---------- */
function escaparHtml(texto) {
  return String(texto).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function guardarUsuario(usuario) {
  try { localStorage.setItem(CLAVE_USUARIO, JSON.stringify(usuario)); } catch (e) { /* almacenamiento no disponible */ }
}

function obtenerUsuario() {
  try {
    const g = JSON.parse(localStorage.getItem(CLAVE_USUARIO));
    if (g && g.nombre && (g.rol === "Administrador" || g.rol === "Cajero")) return g;
  } catch (e) { /* sin sesión válida */ }
  guardarUsuario(USUARIO_PRUEBA);
  return { ...USUARIO_PRUEBA };
}

function iniciales(nombre) {
  return nombre.split(" ").filter(Boolean).slice(0, 2).map(p => p[0].toUpperCase()).join("");
}

function actualizarReloj() {
  const el = document.getElementById("top-fecha");
  if (!el) return;
  const ahora = new Date();
  const dia = ahora.toLocaleDateString("es-MX", { weekday: "long", day: "numeric", month: "long", year: "numeric" });
  const hora = ahora.toLocaleTimeString("es-MX", { hour: "2-digit", minute: "2-digit", hour12: false });
  el.innerHTML = `${dia.charAt(0).toUpperCase() + dia.slice(1)}<br><strong>${hora} h · Ciudad de México</strong>`;
}

/* ---------- Modales: funciones globales ---------- */
function abrirModal(id) {
  const m = document.getElementById(id);
  if (!m) return;
  m.classList.add("abierto");
  m.setAttribute("aria-hidden", "false");
  document.body.classList.add("modal-abierto");
}

function cerrarModal(id) {
  const m = document.getElementById(id);
  if (!m) return;
  m.classList.remove("abierto");
  m.setAttribute("aria-hidden", "true");
  if (!document.querySelector(".modal-fondo.abierto")) document.body.classList.remove("modal-abierto");
}

document.addEventListener("click", e => {
  if (e.target.classList && e.target.classList.contains("modal-fondo")) cerrarModal(e.target.id);
});
document.addEventListener("keydown", e => {
  if (e.key !== "Escape") return;
  const abiertos = document.querySelectorAll(".modal-fondo.abierto");
  if (abiertos.length) cerrarModal(abiertos[abiertos.length - 1].id);
});

/* ---------- Modal M1_Confirmacion (reutilizable) ---------- */
let _accionConfirmada = null;

function insertarModalConfirmacion() {
  if (document.getElementById("modal-confirmacion")) return;
  const div = document.createElement("div");
  div.className = "modal-fondo";
  div.id = "modal-confirmacion";
  div.setAttribute("role", "dialog");
  div.setAttribute("aria-modal", "true");
  div.setAttribute("aria-labelledby", "m1-titulo");
  div.setAttribute("aria-hidden", "true");
  div.innerHTML = `
    <div class="modal">
      <h2 id="m1-titulo">Confirmar acción</h2>
      <p id="m1-mensaje"></p>
      <p class="modal-nota">Esta acción no se puede deshacer</p>
      <div class="modal-acciones">
        <button type="button" class="btn btn-secundario" id="m1-no">No</button>
        <button type="button" class="btn btn-primario" id="m1-si">Sí, confirmar</button>
      </div>
    </div>`;
  document.body.appendChild(div);

  document.getElementById("m1-no").addEventListener("click", () => { _accionConfirmada = null; cerrarModal("modal-confirmacion"); });
  document.getElementById("m1-si").addEventListener("click", () => {
    const accion = _accionConfirmada;
    _accionConfirmada = null;
    cerrarModal("modal-confirmacion");
    if (typeof accion === "function") accion();
  });
}

function mostrarConfirmacion({ titulo = "Confirmar acción", mensaje = "¿Está seguro?", textoConfirmar = "Sí, confirmar", onConfirmar = null } = {}) {
  insertarModalConfirmacion();
  document.getElementById("m1-titulo").textContent = titulo;
  document.getElementById("m1-mensaje").textContent = mensaje;
  document.getElementById("m1-si").textContent = textoConfirmar;
  _accionConfirmada = onConfirmar;
  abrirModal("modal-confirmacion");
}

/* ---------- Sesión ---------- */
function cerrarSesion() {
  try { localStorage.removeItem(CLAVE_USUARIO); } catch (e) { /* nada */ }
  if (PAGINA_LOGIN) window.location.href = PAGINA_LOGIN;
  else window.location.reload();
}

function cambiarRolDev(nuevoRol) {
  const u = obtenerUsuario();
  guardarUsuario({ ...u, rol: nuevoRol });
  window.location.reload();
}

/* ---------- Barra superior + menú lateral ---------- */
function construirLayout() {
  document.title = "La esquina del café";
  if (!document.querySelector("link[rel='icon']")) {
    const link = document.createElement("link");
    link.rel = "icon";
    link.type = "image/svg+xml";
    link.href = "data:image/svg+xml," + encodeURIComponent(
      `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32">
        <rect width="32" height="32" rx="8" fill="#4a3222"/>
        <path d="M16 7c4 2 6 6 6 9s-2 7-6 9c-4-2-6-6-6-9s2-7 6-9zM16 7c-2 4-2 10 0 18"
              fill="none" stroke="#fff" stroke-width="2" stroke-linecap="round"/>
      </svg>`
    );
    document.head.appendChild(link);
  }

  const usuario = obtenerUsuario();
  const paginaActual = (window.location.pathname.split("/").pop() || "inicio.html").toLowerCase();
  const permitidos = MENU_ITEMS.filter(i => i.roles.includes(usuario.rol));

  const selectorDev = MOSTRAR_SELECTOR_ROL ? `
      <label class="dev-rol" title="Solo para desarrollo: cambia de rol sin login">
        <span>DEV · Rol</span>
        <select id="dev-rol" aria-label="Cambiar rol de prueba">
          <option value="Administrador" ${usuario.rol === "Administrador" ? "selected" : ""}>Administrador</option>
          <option value="Cajero" ${usuario.rol === "Cajero" ? "selected" : ""}>Cajero</option>
        </select>
      </label>` : "";

  document.getElementById("topbar").innerHTML = `
    <div class="topbar-marca">
      <div class="logo-cuadro">${svg("grano", 20)}</div>
      <span>La esquina del café</span>
    </div>
    <div class="topbar-der">
      ${selectorDev}
      <div class="topbar-fecha" id="top-fecha"></div>
      <button type="button" class="btn-icono" title="Notificaciones" aria-label="Notificaciones">${svg("campana", 20)}</button>
      <div class="topbar-usuario">
        <div class="avatar">${escaparHtml(iniciales(usuario.nombre))}</div>
        <div class="topbar-usuario-texto"><strong>${escaparHtml(usuario.nombre)}</strong><span>${escaparHtml(usuario.rol)}</span></div>
      </div>
      <button type="button" class="btn-cerrar" onclick="cerrarSesion()">Cerrar sesión</button>
    </div>`;
  actualizarReloj();
  setInterval(actualizarReloj, 30000);

  const selector = document.getElementById("dev-rol");
  if (selector) selector.addEventListener("change", e => cambiarRolDev(e.target.value));

  const seccion = usuario.rol === "Administrador" ? "Administración" : "Operación";
  const itemActual = MENU_ITEMS.find(i => i.archivo === paginaActual) || MENU_ITEMS[0];
  document.getElementById("sidebar").innerHTML = `
    <div class="sidebar-titulo">
      ${svg(itemActual.icono, 22)}
      <div class="sb-txt"><strong>${itemActual.texto}</strong><small>${seccion}</small></div>
    </div>
    <div class="sidebar-seccion">${seccion}</div>
    <nav aria-label="Menú principal">
      <ul class="sidebar-menu">
        ${permitidos.map(i => `
          <li><a href="${i.archivo}" data-archivo="${i.archivo}" title="${i.texto}"
                 class="${i.archivo === paginaActual ? "activo" : ""}" ${i.archivo === paginaActual ? 'aria-current="page"' : ""}>
            ${svg(i.icono)}<span class="sb-txt">${i.texto}</span></a></li>`).join("")}
      </ul>
    </nav>`;

  Object.entries(BADGES_INICIALES).forEach(([archivo, n]) => ponerBadge(archivo, n));

  const esDelMenu = MENU_ITEMS.some(i => i.archivo === paginaActual);
  if (esDelMenu && !permitidos.some(i => i.archivo === paginaActual)) {
    const zona = document.querySelector(".pantalla");
    if (zona) {
      const aviso = document.createElement("div");
      aviso.className = "alerta-error";
      aviso.textContent = `El rol ${usuario.rol} no tiene acceso a esta pantalla.`;
      zona.prepend(aviso);
    }
  }

  insertarModalConfirmacion();
}

function ponerBadge(archivo, numero) {
  const enlace = document.querySelector(`.sidebar-menu a[data-archivo="${archivo}"]`);
  if (!enlace) return;
  let b = enlace.querySelector(".menu-badge");
  if (!b) { b = document.createElement("span"); b.className = "menu-badge"; enlace.appendChild(b); }
  b.textContent = numero;
}

document.addEventListener("DOMContentLoaded", construirLayout);