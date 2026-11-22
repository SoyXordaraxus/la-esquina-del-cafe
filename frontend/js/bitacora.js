const API_ADMIN_BIT = `${API_BASE}/api/admin`;

async function cargarBitacora() {
  const usr = document.getElementById("bit-usuario").value;
  const ini = document.getElementById("bit-inicio").value;
  const fin = document.getElementById("bit-fin").value;

  const params = new URLSearchParams();
  if (usr) params.append("id_usuario", usr);
  if (ini) params.append("fecha_inicio", ini);
  if (fin) params.append("fecha_fin", fin);

  const resp = await fetch(`${API_ADMIN_BIT}/bitacora?${params.toString()}`);
  const data = await resp.json();
  const registros = data.registros || [];

  const tbody = document.getElementById("tabla-bitacora");
  if (!registros.length) {
    tbody.innerHTML = `<tr><td colspan="4" style="text-align:center; padding:18px;">No hay eventos registrados con esos filtros.</td></tr>`;
    return;
  }

  tbody.innerHTML = registros.map(r => `
    <tr>
      <td>${escaparHtml(r.fecha)}</td>
      <td>${escaparHtml(r.hora)}</td>
      <td><strong>${escaparHtml(r.usuario)}</strong><br><small style="color:var(--texto-suave);">${escaparHtml(r.rol)}</small></td>
      <td>
        <strong>${escaparHtml(r.accion)}</strong><br>
        <span style="font-size:0.86rem; color:var(--texto-suave);">${escaparHtml(r.detalle)}</span>
      </td>
    </tr>
  `).join("");
}

document.addEventListener("DOMContentLoaded", async () => {
  const respUsr = await fetch(`${API_ADMIN_BIT}/usuarios`);
  const dataUsr = await respUsr.json();
  const sel = document.getElementById("bit-usuario");
  (dataUsr.usuarios || []).forEach(u => {
    const opt = document.createElement("option");
    opt.value = u.id_usuario;
    opt.textContent = `${u.nombre_usuario} (${u.rol})`;
    sel.appendChild(opt);
  });

  document.getElementById("btn-filtrar-bit").addEventListener("click", cargarBitacora);
  await cargarBitacora();
});