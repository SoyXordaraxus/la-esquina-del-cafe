const API_BKP = `${API_BASE}/api/admin/respaldos`;

const CLASE_UNIDAD = {
  conectada: "badge-verde",
  no_configurada: "badge-gris",
  no_disponible: "badge-amarillo",
};

async function cargarEstado() {
  try {
    const resp = await fetch(`${API_BKP}/estado`);
    const data = await leerJsonSeguro(resp);
    if (!resp.ok) throw new Error(mensajeError(data, "No se pudo consultar el estado de los respaldos.", resp.status));

    document.getElementById("lbl-hora-programada").textContent = `${data.hora_programada} (hora del negocio)`;
    document.getElementById("lbl-proximo-bkp").textContent = data.proximo_pendiente
      ? `${data.proximo_respaldo} · pendiente, se ejecuta en breve`
      : data.proximo_respaldo;
    document.getElementById("lbl-ultimo-diario").textContent = data.ultimo_diario || "Aún no hay respaldo diario";

    const unidad = data.unidad_externa || {};
    const lbl = document.getElementById("lbl-unidad-externa");
    lbl.className = `badge ${CLASE_UNIDAD[unidad.estado] || "badge-gris"}`;
    lbl.textContent = unidad.texto || "—";
  } catch (err) {
    document.getElementById("lbl-proximo-bkp").textContent = mensajeExcepcion(err);
  }
}

async function cargarRespaldos() {
  const resp = await fetch(API_BKP);
  const data = await resp.json();

  document.getElementById("lbl-ultimo-bkp").textContent = data.ultimo_respaldo || "Sin respaldos";
  const lista = data.respaldos || [];
  const tbody = document.getElementById("tabla-respaldos");

  if (!lista.length) {
    tbody.innerHTML = `<tr><td colspan="7" style="text-align:center; padding:18px;">Aún no hay respaldos generados. Haz clic en "Respaldar base de datos ahora".</td></tr>`;
    return;
  }

  tbody.innerHTML = lista.map(r => `
    <tr>
      <td>${escaparHtml(r.fecha)}</td>
      <td>${escaparHtml(r.tipo)}</td>
      <td><span class="badge badge-verde">${escaparHtml(r.estado)}</span></td>
      <td><strong>${escaparHtml(r.folio)}</strong><div style="font-size:0.8rem; color:var(--texto-suave);">${escaparHtml(r.archivo)}</div></td>
      <td><span class="badge ${r.externa ? "badge-verde" : "badge-gris"}">${escaparHtml(r.ubicacion)}</span></td>
      <td>${escaparHtml(r.tamano)}</td>
      <td>
        <a href="${conToken(`${API_BKP}/descargar/${encodeURIComponent(r.archivo)}`)}" class="btn btn-secundario">Descargar .SQL</a>
      </td>
    </tr>
  `).join("");
}

document.addEventListener("DOMContentLoaded", async () => {
  await Promise.all([cargarEstado(), cargarRespaldos()]);

  document.getElementById("btn-respaldar-ahora").addEventListener("click", async () => {
    const btn = document.getElementById("btn-respaldar-ahora");
    const msg = document.getElementById("msg-respaldo");
    btn.disabled = true;
    btn.textContent = "Generando respaldo...";

    try {
      // El backend identifica al administrador por el token de la sesión
      const resp = await fetch(`${API_BKP}/ejecutar?tipo=manual`, { method: "POST" });
      const data = await leerJsonSeguro(resp);
      if (!resp.ok) throw new Error(mensajeError(data, "Error al generar respaldo.", resp.status));

      msg.className = data.falla_externa ? "alerta-error" : "badge-verde";
      msg.style.display = "block";
      msg.style.padding = "12px 16px";
      msg.style.borderRadius = "10px";
      msg.textContent = data.falla_externa ? `${data.mensaje}. Aviso: ${data.aviso_externo}` : data.mensaje;
      await Promise.all([cargarEstado(), cargarRespaldos()]);
    } catch (err) {
      msg.className = "alerta-error";
      msg.style.display = "block";
      msg.textContent = mensajeExcepcion(err);
    } finally {
      btn.disabled = false;
      btn.textContent = "Respaldar base de datos ahora";
    }
  });
});
