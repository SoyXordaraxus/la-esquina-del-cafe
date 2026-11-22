const API_BKP = `${API_BASE}/api/admin/respaldos`;

async function cargarRespaldos() {
  const resp = await fetch(API_BKP);
  const data = await resp.json();

  document.getElementById("lbl-ultimo-bkp").textContent = data.ultimo_respaldo || "Sin respaldos";
  const lista = data.respaldos || [];
  const tbody = document.getElementById("tabla-respaldos");

  if (!lista.length) {
    tbody.innerHTML = `<tr><td colspan="6" style="text-align:center; padding:18px;">Aún no hay respaldos generados. Haz clic en "Respaldar base de datos ahora".</td></tr>`;
    return;
  }

  tbody.innerHTML = lista.map(r => `
    <tr>
      <td>${escaparHtml(r.fecha)}</td>
      <td>${escaparHtml(r.tipo)}</td>
      <td><span class="badge-verde">${escaparHtml(r.estado)}</span></td>
      <td><strong>${escaparHtml(r.folio)}</strong> · ${escaparHtml(r.ubicacion)}</td>
      <td>${escaparHtml(r.tamano)}</td>
      <td>
        <a href="${API_BKP}/descargar/${encodeURIComponent(r.archivo)}" class="btn btn-secundario">Descargar .SQL</a>
      </td>
    </tr>
  `).join("");
}

document.addEventListener("DOMContentLoaded", async () => {
  await cargarRespaldos();

  document.getElementById("btn-respaldar-ahora").addEventListener("click", async () => {
    const btn = document.getElementById("btn-respaldar-ahora");
    const msg = document.getElementById("msg-respaldo");
    btn.disabled = true;
    btn.textContent = "Generando respaldo...";

    try {
      const u = obtenerUsuario();
      const resp = await fetch(`${API_BKP}/ejecutar?tipo=manual&id_usuario=${u.id_usuario || 1}`, {
        method: "POST",
      });
      const data = await resp.json();
      if (!resp.ok) throw new Error(data.detail || "Error al generar respaldo.");

      msg.className = "badge-verde";
      msg.style.display = "block";
      msg.style.padding = "12px 16px";
      msg.style.borderRadius = "10px";
      msg.textContent = data.mensaje;
      await cargarRespaldos();
    } catch (err) {
      msg.className = "alerta-error";
      msg.style.display = "block";
      msg.textContent = err.message;
    } finally {
      btn.disabled = false;
      btn.textContent = "Respaldar base de datos ahora";
    }
  });
});