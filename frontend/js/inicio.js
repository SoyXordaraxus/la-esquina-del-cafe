const API_URL = `${API_BASE}/api/dashboard/resumen`;

function formatearMoneda(valor) {
  return valor.toLocaleString("es-MX", {
    style: "currency",
    currency: "MXN",
    minimumFractionDigits: 2
  });
}

// Solo clases conocidas (verde | amarillo | rojo | neutro)
function claseTipo(tipo) {
  return ["verde", "amarillo", "rojo", "neutro"].includes(tipo) ? tipo : "neutro";
}

// Botón de la columna Acciones: enlace a la pantalla que indica el backend en "destino"
// (recepcion.html?insumo=, mermas.html?lote=, caducidades.html?lote=). El panel es solo
// del Administrador, que puede abrir todas esas pantallas.
const DESTINO_VALIDO = /^(recepcion|mermas|caducidades)\.html\?(insumo|lote)=\d+$/;

function botonAccion(item) {
  if (!item.destino || !DESTINO_VALIDO.test(item.destino)) return "—";
  return `<a class="btn btn-secundario" href="${escaparHtml(item.destino)}">${escaparHtml(item.accion)}</a>`;
}

async function cargarPanelPrincipal() {
  try {
    const res = await fetch(API_URL);
    if (!res.ok) throw new Error("Error al consultar la API");
    const data = await res.json();
    const m = data.metricas;

    document.getElementById("estado-peps").textContent = data.estado_turno;
    document.getElementById("banner-bajo-minimo").textContent = `${m.insumos_bajo_minimo} insumos bajo mínimo`;
    document.getElementById("banner-por-vencer").textContent = `${m.lotes_proximos_caducar} lotes próximos a vencer`;

    document.getElementById("kpi-ventas").textContent = formatearMoneda(m.ventas_dia);
    document.getElementById("kpi-tickets").textContent = `${m.tickets_dia} tickets`;

    document.getElementById("kpi-minimo").textContent = `${m.insumos_bajo_minimo} insumos`;
    document.getElementById("kpi-caducar").textContent = `${m.lotes_proximos_caducar} lotes`;

    document.getElementById("kpi-mermas").textContent = formatearMoneda(m.mermas_mes);
    document.getElementById("kpi-registros-mermas").textContent = `${m.registros_mermas} registros`;

    const tbody = document.getElementById("tabla-alertas-body");
    tbody.innerHTML = data.alertas.map(item => `
      <tr>
        <td><strong>${escaparHtml(item.insumo)}</strong></td>
        <td class="texto-tenue">${escaparHtml(item.lote)}</td>
        <td class="texto-${claseTipo(item.vencimiento_tipo)}">${escaparHtml(item.vencimiento)}</td>
        <td><strong>${escaparHtml(item.cantidad_restante)}</strong></td>
        <td>
          <span class="badge badge-${claseTipo(item.estado_tipo)}">● ${escaparHtml(item.estado)}</span>
        </td>
        <td>${botonAccion(item)}</td>
      </tr>
    `).join("");

    document.getElementById("contador-alertas").textContent = `${data.alertas.length} alertas mostradas`;
  } catch (err) {
    console.error("Error cargando el panel principal:", err);
  }
}

document.addEventListener("DOMContentLoaded", cargarPanelPrincipal);