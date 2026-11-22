const API_URL = `${API_BASE}/api/dashboard/resumen`;

function formatearMoneda(valor) {
  return valor.toLocaleString("es-MX", {
    style: "currency",
    currency: "MXN",
    minimumFractionDigits: 2
  });
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
        <td><strong>${item.insumo}</strong></td>
        <td class="texto-tenue">${item.lote}</td>
        <td class="texto-${item.vencimiento_tipo}">${item.vencimiento}</td>
        <td><strong>${item.cantidad_restante}</strong></td>
        <td>
          <span class="badge-${item.estado_tipo}">● ${item.estado}</span>
        </td>
        <td>
          <button class="btn btn-secundario" type="button">${item.accion}</button>
        </td>
      </tr>
    `).join("");

    document.getElementById("contador-alertas").textContent = `${data.alertas.length} alertas mostradas`;
  } catch (err) {
    console.error("Error cargando el panel principal:", err);
  }
}

document.addEventListener("DOMContentLoaded", cargarPanelPrincipal);