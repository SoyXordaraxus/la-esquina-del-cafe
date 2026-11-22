const API_ADMIN = `${API_BASE}/api/admin`;
let tipoSeleccionado = "ventas";

async function cargarReporte() {
  const inicio = document.getElementById("rep-inicio").value;
  const fin = document.getElementById("rep-fin").value;

  const params = new URLSearchParams({ tipo: tipoSeleccionado });
  if (inicio) params.append("fecha_inicio", inicio);
  if (fin) params.append("fecha_fin", fin);

  const resp = await fetch(`${API_ADMIN}/reportes?${params.toString()}`);
  const data = await resp.json();

  document.getElementById("rep-titulo-previa").textContent = `Vista previa · ${data.titulo}`;
  document.getElementById("rep-subtitulo-previa").textContent = `Periodo: ${data.periodo} · Sucursal Centro`;

  document.getElementById("rep-thead").innerHTML =
    `<tr>${data.columnas.map(c => `<th>${escaparHtml(c)}</th>`).join("")}</tr>`;

  const tbody = document.getElementById("rep-tbody");
  if (!data.filas || !data.filas.length) {
    tbody.innerHTML = `<tr><td colspan="${data.columnas.length}" style="text-align:center; padding:18px;">No hay movimientos en el rango de fechas seleccionado.</td></tr>`;
    return;
  }

  tbody.innerHTML = data.filas.map(fila =>
    `<tr>${fila.map((celda, idx) => idx === 0 ? `<td><strong>${escaparHtml(celda)}</strong></td>` : `<td>${escaparHtml(celda)}</td>`).join("")}</tr>`
  ).join("");
}

function descargarArchivo(formato) {
  const inicio = document.getElementById("rep-inicio").value;
  const fin = document.getElementById("rep-fin").value;
  const u = obtenerUsuario();

  const params = new URLSearchParams({
    tipo: tipoSeleccionado,
    formato,
    id_usuario: u.id_usuario || 1,
  });
  if (inicio) params.append("fecha_inicio", inicio);
  if (fin) params.append("fecha_fin", fin);

  window.open(`${API_ADMIN}/reportes/exportar?${params.toString()}`, "_blank");
}

document.addEventListener("DOMContentLoaded", async () => {
  const hoy = new Date();
  const hace7 = new Date();
  hace7.setDate(hoy.getDate() - 7);

  document.getElementById("rep-fin").value = hoy.toISOString().split("T")[0];
  document.getElementById("rep-inicio").value = hace7.toISOString().split("T")[0];

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