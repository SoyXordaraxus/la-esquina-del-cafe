// =========================================================
// Pantalla Historial de ventas (ventas.html)
// Usa los endpoints de Francisco (routes/ventas.py):
//   GET  /api/ventas/historial?fecha=AAAA-MM-DD
//   GET  /api/ventas/{id}
//   GET  /api/ventas/motivos-cancelacion
//   POST /api/ventas/{id}/cancelar   { id_usuario, motivo }
// =========================================================

const API_VENTAS = `${API_BASE}/api/ventas`;

let ventaPorCancelar = null;   // { id_venta, total }
let cancelacionEnCurso = false;

document.addEventListener("DOMContentLoaded", () => {
  document.getElementById("filtro-fecha").value = hoyISO();
  document.getElementById("filtro-fecha").addEventListener("change", e => cargarVentas(e.target.value));
  document.getElementById("btn-hoy").addEventListener("click", () => {
    document.getElementById("filtro-fecha").value = hoyISO();
    cargarVentas(hoyISO());
  });
  document.getElementById("btn-todas").addEventListener("click", () => {
    document.getElementById("filtro-fecha").value = "";
    cargarVentas(null);
  });
  document.getElementById("btn-continuar-cancelacion").addEventListener("click", pedirConfirmacion);

  cargarMotivos();
  cargarVentas(hoyISO());
});

/* ---------- Utilidades ---------- */
// "Hoy" es el día del negocio (config.js), no el del navegador
function hoyISO() {
  return hoyNegocioISO();
}

function dinero(n) {
  return "$" + Number(n).toFixed(2);
}

function fechaLegible(iso) {
  if (!iso) return "";
  return fechaHoraNegocio(iso);
}

function esAdministrador() {
  return obtenerUsuario().rol === "Administrador";
}

// idUsuarioActual() viene de menu.js (sesión real). El backend vuelve a validar el rol
// con el token, así que un Cajero nunca puede cancelar.

function mostrarError(idElemento, texto) {
  const el = document.getElementById(idElemento);
  el.textContent = texto;
  el.style.display = texto ? "block" : "none";
}

async function leerJson(resp) {
  try { return await resp.json(); } catch (e) { return {}; }
}

/* ---------- Listado ---------- */
async function cargarVentas(fecha) {
  const cuerpo = document.getElementById("tabla-ventas-body");
  mostrarError("error-ventas", "");
  const url = fecha ? `${API_VENTAS}/historial?fecha=${fecha}` : `${API_VENTAS}/historial`;

  let ventas;
  try {
    const resp = await fetch(url);
    if (!resp.ok) throw new Error();
    ventas = await resp.json();
  } catch (e) {
    cuerpo.innerHTML = `<tr><td colspan="7" class="vacio">Sin datos</td></tr>`;
    mostrarError("error-ventas", "No se pudo consultar el historial. Verifique que el servidor esté encendido.");
    return;
  }

  if (!ventas.length) {
    cuerpo.innerHTML = `<tr><td colspan="7" class="vacio">No hay ventas registradas${fecha ? " en esta fecha" : ""}.</td></tr>`;
    return;
  }

  cuerpo.innerHTML = ventas.map(v => {
    const cancelada = (v.estado || "").toLowerCase() === "cancelada";
    const productos = v.detalles.length
      ? v.detalles.map(d => `${d.cantidad} × ${escaparHtml(d.nombre)}`).join("<br>")
      : "—";
    const badge = cancelada
      ? `<span class="badge badge-rojo">Cancelada</span>`
      : `<span class="badge badge-verde">Completada</span>`;
    const botonCancelar = (!cancelada && esAdministrador())
      ? `<button type="button" class="btn btn-peligro" onclick="abrirCancelacion(${v.id_venta}, ${v.total})">Cancelar</button>`
      : "";
    return `
      <tr class="${cancelada ? "fila-cancelada" : ""}">
        <td>#${v.id_venta}</td>
        <td>${fechaLegible(v.fecha)}</td>
        <td>${productos}</td>
        <td>${escaparHtml(v.forma_pago)}</td>
        <td class="total">${dinero(v.total)}</td>
        <td>${badge}</td>
        <td><div class="acciones">
          <button type="button" class="btn btn-secundario" onclick="verDetalle(${v.id_venta})">Ver</button>
          ${botonCancelar}
        </div></td>
      </tr>`;
  }).join("");
}

/* ---------- Detalle (RF 3) ---------- */
async function verDetalle(idVenta) {
  let v;
  try {
    const resp = await fetch(`${API_VENTAS}/${idVenta}`);
    v = await leerJson(resp);
    if (!resp.ok) throw new Error(v.detail);
  } catch (e) {
    mostrarError("error-ventas", e.message || "No se pudo consultar la venta.");
    return;
  }

  document.getElementById("detalle-titulo").textContent = `Venta #${v.id_venta} · ${v.estado}`;
  const productos = v.detalles.map(d =>
    `<li>${d.cantidad} × ${escaparHtml(d.nombre)} a ${dinero(d.precio_unitario)} = ${dinero(d.subtotal)}</li>`).join("");
  const insumos = (v.insumos_consumidos || []).map(i =>
    `<li>${escaparHtml(i.insumo)}: ${i.cantidad} ${escaparHtml(i.unidad || "")}</li>`).join("");

  document.getElementById("detalle-cuerpo").innerHTML = `
    <p>${fechaLegible(v.fecha)} · Atendió: ${escaparHtml(v.usuario)}</p>
    <p><strong>Productos</strong></p>
    <ul class="detalle-lista">${productos || "<li>Sin detalle</li>"}</ul>
    <p><strong>Insumos descontados</strong></p>
    <ul class="detalle-lista">${insumos || "<li>Sin movimientos de inventario</li>"}</ul>
    <p>Forma de pago: ${escaparHtml(v.forma_pago)} · Recibido: ${dinero(v.monto_recibido)} · Cambio: ${dinero(v.cambio)}</p>
    <p><strong>Total: ${dinero(v.total)}</strong></p>`;
  abrirModal("modal-detalle-venta");
}

/* ---------- Cancelación (RF 9 + M1 de RF 14) ---------- */
async function cargarMotivos() {
  let motivos = ["Error de captura", "Devolución del cliente", "Producto en mal estado"];
  try {
    const resp = await fetch(`${API_VENTAS}/motivos-cancelacion`);
    if (resp.ok) motivos = await resp.json();
  } catch (e) { /* se usan los de respaldo */ }
  document.getElementById("motivo-cancelacion").innerHTML =
    motivos.map(m => `<option value="${escaparHtml(m)}">${escaparHtml(m)}</option>`).join("");
}

function abrirCancelacion(idVenta, total) {
  if (!esAdministrador()) return;
  ventaPorCancelar = { id_venta: idVenta, total };
  document.getElementById("cancelar-resumen").textContent = `Venta #${idVenta} por ${dinero(total)}.`;
  document.getElementById("motivo-cancelacion").selectedIndex = 0;
  mostrarError("error-cancelacion", "");
  abrirModal("modal-cancelar-venta");
}

function pedirConfirmacion() {
  if (!ventaPorCancelar) return;
  const motivo = document.getElementById("motivo-cancelacion").value;
  cerrarModal("modal-cancelar-venta");
  mostrarConfirmacion({
    titulo: "Cancelar venta",
    mensaje: `¿Está seguro de que desea cancelar la venta #${ventaPorCancelar.id_venta} por ${dinero(ventaPorCancelar.total)}? Motivo: ${motivo}.`,
    textoConfirmar: "Sí, cancelar venta",
    onConfirmar: () => enviarCancelacion(motivo),
  });
}

async function enviarCancelacion(motivo) {
  if (cancelacionEnCurso || !ventaPorCancelar) return;   // evita doble clic
  cancelacionEnCurso = true;
  const idVenta = ventaPorCancelar.id_venta;

  let resp, data;
  try {
    resp = await fetch(`${API_VENTAS}/${idVenta}/cancelar`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id_usuario: idUsuarioActual(), motivo }),
    });
    data = await leerJson(resp);
  } catch (e) {
    cancelacionEnCurso = false;
    mostrarError("error-ventas", "No se pudo conectar con el servidor. La venta no se canceló.");
    return;
  }
  cancelacionEnCurso = false;
  ventaPorCancelar = null;

  if (!resp.ok) {
    mostrarError("error-ventas", typeof data.detail === "string" ? data.detail : "No se pudo cancelar la venta.");
    return;
  }

  const devueltos = data.restituidos.length;
  const merma = data.enviados_a_merma.length;
  alert(`Venta #${idVenta} cancelada.\nInsumos devueltos a inventario: ${devueltos} lote(s).` +
        (merma ? `\nEnviados a merma por caducidad: ${merma} lote(s).` : ""));
  cargarVentas(document.getElementById("filtro-fecha").value || null);
}