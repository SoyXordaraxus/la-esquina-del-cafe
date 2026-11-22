const API_ADMIN = `${API_BASE}/api/admin`;
let tipoSeleccionado = "ventas";

async function cargarReporte() {
  const inicio = document.getElementById("rep-inicio").value;
  const fin = document.getElementById("rep-fin").value;

  const params = new URLSearchParams({ tipo: tipoSeleccionado });
  if (inicio) params.append("fecha_inicio", inicio);
  if (fin) params.append("fecha_fin", fin);

  const tbody = document.getElementById("rep-tbody");
  let data;
  try {
    const resp = await fetch(`${API_ADMIN}/reportes?${params.toString()}`);
    data = await leerJsonSeguro(resp);
    if (!resp.ok) throw new Error(mensajeError(data, "No se pudo generar el reporte.", resp.status));
  } catch (err) {
    tbody.innerHTML = `<tr><td class="alerta-error">${escaparHtml(mensajeExcepcion(err, "No se pudo generar el reporte."))}</td></tr>`;
    return;
  }

  document.getElementById("rep-titulo-previa").textContent = `Vista previa · ${data.titulo}`;
  document.getElementById("rep-subtitulo-previa").textContent = `Periodo: ${data.periodo} · Sucursal Centro`;

  // Misma tabla que el PDF y el CSV: números a la derecha y fila de TOTAL
  const alin = data.alineacion || [];
  const estilo = idx => (alin[idx] === "R" ? ' style="text-align:right;"' : "");
  document.getElementById("rep-thead").innerHTML =
    `<tr>${data.columnas.map((c, idx) => `<th${estilo(idx)}>${escaparHtml(c)}</th>`).join("")}</tr>`;

  const filas = (data.filas || []).length
    ? data.filas.map(fila =>
        `<tr>${fila.map((celda, idx) => `<td${estilo(idx)}>${idx === 0 ? `<strong>${escaparHtml(celda)}</strong>` : escaparHtml(celda)}</td>`).join("")}</tr>`
      ).join("")
    : `<tr><td colspan="${data.columnas.length}" style="text-align:center; padding:18px;"><em>Sin registros en este periodo</em></td></tr>`;
  const total = data.total
    ? `<tr class="fila-total">${data.total.map((celda, idx) => `<td${estilo(idx)}><strong>${escaparHtml(celda)}</strong></td>`).join("")}</tr>`
    : "";
  tbody.innerHTML = filas + total;
}

function descargarArchivo(formato) {
  const inicio = document.getElementById("rep-inicio").value;
  const fin = document.getElementById("rep-fin").value;
  const params = new URLSearchParams({ tipo: tipoSeleccionado, formato });
  if (inicio) params.append("fecha_inicio", inicio);
  if (fin) params.append("fecha_fin", fin);

  window.open(conToken(`${API_ADMIN}/reportes/exportar?${params.toString()}`), "_blank");
}

document.addEventListener("DOMContentLoaded", async () => {
  // toISOString() da la fecha UTC (de noche ya sería "mañana"): se usa el día del negocio
  document.getElementById("rep-fin").value = hoyNegocioISO();
  document.getElementById("rep-inicio").value = hoyNegocioISO(-7);

  document.querySelectorAll(".tab-btn").forEach(btn => {
    btn.addEventListener("click", async () => {
      document.querySelectorAll(".tab-btn").forEach(b => b.classList.remove("activo"));
      btn.classList.add("activo");
      tipoSeleccionado = btn.dataset.tipo;
      await cargarReporte();
    });
  });

  document.getElementById("btn-generar-rep").addEventListener("click", cargarReporte);
  document.getElementById("btn-exp-csv").addEventListener("click", () => descargarArchivo("csv"));
  document.getElementById("btn-exp-pdf").addEventListener("click", () => descargarArchivo("pdf"));

  await cargarReporte();
});