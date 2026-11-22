const API_LOTES = "http://127.0.0.1:8000/api/almacen/lotes";
let todosLosLotes = [];

function formatearFecha(iso) {
  if (!iso) return "No perecedero";
  const [y, m, d] = iso.split("-");
  const meses = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"];
  return `${d} ${meses[parseInt(m, 10) - 1]} ${y}`;
}

function renderizarTabla() {
  const texto = document.getElementById("filtro-buscar").value.trim().toLowerCase();
  const estado = document.getElementById("filtro-estado").value;
  const venc = document.getElementById("filtro-venc").value;

  const filtrados = todosLosLotes.filter((l) => {
    const coincideTexto = !texto ||
      l.insumo.toLowerCase().includes(texto) ||
      l.codigo_lote.toLowerCase().includes(texto) ||
      `lote-${l.id_lote}`.includes(texto);

    const coincideEstado = estado === "todos" || l.estado === estado;

    let coincideVenc = true;
    if (venc === "alertas") {
      coincideVenc = l.estado === "Caducado" || (l.estado === "Vigente" && l.dias_restantes !== null && l.dias_restantes <= 5);
    } else if (venc === "urgente") {
      coincideVenc = l.estado === "Vigente" && l.dias_restantes !== null && l.dias_restantes >= 0 && l.dias_restantes <= 3;
    } else if (venc === "precaucion") {
      coincideVenc = l.estado === "Vigente" && l.dias_restantes !== null && l.dias_restantes >= 4 && l.dias_restantes <= 5;
    }

    return coincideTexto && coincideEstado && coincideVenc;
  });

  const caducadosCount = todosLosLotes.filter(l => l.estado === "Caducado").length;
  const proximosCount = todosLosLotes.filter(l => l.estado === "Vigente" && l.dias_restantes !== null && l.dias_restantes <= 5).length;

  document.getElementById("resumen-conteo").innerHTML =
    `<strong>${filtrados.length} lotes</strong> · ${caducadosCount} caducados · ${proximosCount} próximos a vencer`;

  const tbody = document.getElementById("tabla-caducidades");
  if (!filtrados.length) {
    tbody.innerHTML = `<tr><td colspan="6" style="text-align:center; padding:20px;">No se encontraron lotes con esos filtros.</td></tr>`;
    return;
  }

  tbody.innerHTML = filtrados.map((l) => {
    const claseFila = l.semaforo === "rojo" ? "fila-roja" : (l.semaforo === "amarillo" ? "fila-amarilla" : "");
    const claseSub = l.semaforo === "rojo" ? "rojo" : (l.semaforo === "amarillo" ? "amarillo" : "neutro");

    let badge = `<span class="badge-verde">Vigente</span>`;
    if (l.estado === "Caducado") badge = `<span class="badge-rojo">Caducado</span>`;
    else if (l.estado === "Agotado") badge = `<span class="badge-amarillo" style="background:#eee;color:#555;">Agotado</span>`;

    const accion = l.estado === "Caducado"
      ? `<a href="mermas.html?lote=${l.id_lote}" class="btn btn-secundario">Registrar merma</a>`
      : "—";

    return `
      <tr class="${claseFila}">
        <td><strong>${escaparHtml(l.insumo)}</strong></td>
        <td>${escaparHtml(l.codigo_lote)}</td>
        <td>
          ${formatearFecha(l.caducidad)}
          <span class="sub-venc ${claseSub}">${escaparHtml(l.texto_vencimiento)}</span>
        </td>
        <td>${l.cantidad_disponible} ${escaparHtml(l.unidad)}</td>
        <td>${badge}</td>
        <td>${accion}</td>
      </tr>`;
  }).join("");
}

document.addEventListener("DOMContentLoaded", async () => {
  try {
    const resp = await fetch(API_LOTES);
    const data = await resp.json();
    todosLosLotes = data.lotes || [];

    const alertasTotales = todosLosLotes.filter(
      l => l.estado === "Caducado" || (l.estado === "Vigente" && l.dias_restantes !== null && l.dias_restantes <= 5)
    ).length;
    if (typeof ponerBadge === "function") ponerBadge("caducidades.html", alertasTotales);

    renderizarTabla();
  } catch (err) {
    document.getElementById("tabla-caducidades").innerHTML =
      `<tr><td colspan="6" class="alerta-error">No se pudo conectar con el servidor para cargar los lotes.</td></tr>`;
  }

  document.getElementById("filtro-buscar").addEventListener("input", renderizarTabla);
  document.getElementById("filtro-estado").addEventListener("change", renderizarTabla);
  document.getElementById("filtro-venc").addEventListener("change", renderizarTabla);
});