const API_USUARIOS = `${API_BASE}/api/admin/usuarios`;
let listaUsuarios = [];

function abrirNuevoUsuario() {
  document.getElementById("titulo-modal-usr").textContent = "Nuevo usuario";
  document.getElementById("usr-id").value = "";
  document.getElementById("form-usuario").reset();
  document.getElementById("usr-pass").required = true;
  document.getElementById("lbl-usr-pass").textContent = "Contraseña (mín. 8 caracteres alfanuméricos)";
  document.getElementById("grupo-usr-estado").style.display = "none";
  document.getElementById("error-modal-usr").style.display = "none";
  abrirModal("modal-usuario");
}

function abrirEditarUsuario(id) {
  const u = listaUsuarios.find(x => x.id_usuario === id);
  if (!u) return;

  document.getElementById("titulo-modal-usr").textContent = "Editar usuario";
  document.getElementById("usr-id").value = u.id_usuario;
  document.getElementById("usr-nombre").value = u.nombre_usuario;
  document.getElementById("usr-correo").value = u.correo;
  document.getElementById("usr-rol").value = u.rol;
  document.getElementById("usr-estado").value = u.estado;
  document.getElementById("usr-pass").value = "";
  document.getElementById("usr-pass").required = false;
  document.getElementById("lbl-usr-pass").textContent = "Nueva contraseña (dejar vacío para conservar actual)";
  document.getElementById("grupo-usr-estado").style.display = "";
  document.getElementById("error-modal-usr").style.display = "none";
  abrirModal("modal-usuario");
}

function alternarEstadoUsuario(id) {
  const u = listaUsuarios.find(x => x.id_usuario === id);
  if (!u) return;
  const nuevoEstado = u.estado === "Activo" ? "Inactivo" : "Activo";

  mostrarConfirmacion({
    titulo: `${nuevoEstado === "Inactivo" ? "Desactivar" : "Reactivar"} cuenta`,
    mensaje: `¿Seguro que deseas cambiar el estado de "${u.nombre_usuario}" a ${nuevoEstado}?`,
    textoConfirmar: "Sí, confirmar",
    onConfirmar: async () => {
      const admin = obtenerUsuario();
      const resp = await fetch(`${API_USUARIOS}/${id}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          nombre_usuario: u.nombre_usuario,
          correo: u.correo,
          rol: u.rol,
          estado: nuevoEstado,
          id_admin: admin.id_usuario || 1,
        }),
      });
      if (resp.ok) await cargarUsuarios();
    },
  });
}

async function cargarUsuarios() {
  const resp = await fetch(API_USUARIOS);
  const data = await resp.json();
  listaUsuarios = data.usuarios || [];

  document.getElementById("tabla-usuarios").innerHTML = listaUsuarios.map(u => `
    <tr>
      <td><strong>${escaparHtml(u.nombre_usuario)}</strong></td>
      <td>${escaparHtml(u.correo)}</td>
      <td>${escaparHtml(u.rol)}</td>
      <td>${u.estado === "Activo" ? '<span class="badge-verde">Activo</span>' : '<span class="badge-rojo">Inactivo</span>'}</td>
      <td>${escaparHtml(u.fecha_registro)}</td>
      <td style="white-space:nowrap;">
        <button type="button" class="btn btn-secundario" onclick="abrirEditarUsuario(${u.id_usuario})">Editar</button>
        <button type="button" class="btn ${u.estado === "Activo" ? "btn-peligro" : "btn-secundario"}" onclick="alternarEstadoUsuario(${u.id_usuario})">
          ${u.estado === "Activo" ? "Desactivar" : "Activar"}
        </button>
      </td>
    </tr>
  `).join("");
}

document.addEventListener("DOMContentLoaded", async () => {
  await cargarUsuarios();
  document.getElementById("btn-nuevo-usuario").addEventListener("click", abrirNuevoUsuario);

  document.getElementById("form-usuario").addEventListener("submit", async (e) => {
    e.preventDefault();
    const errBox = document.getElementById("error-modal-usr");
    errBox.style.display = "none";

    const id = document.getElementById("usr-id").value;
    const admin = obtenerUsuario();
    const payload = {
      nombre_usuario: document.getElementById("usr-nombre").value.trim(),
      correo: document.getElementById("usr-correo").value.trim(),
      rol: document.getElementById("usr-rol").value,
      contrasena: document.getElementById("usr-pass").value,
      estado: document.getElementById("usr-estado").value || "Activo",
      id_admin: admin.id_usuario || 1,
    };

    try {
      const resp = await fetch(id ? `${API_USUARIOS}/${id}` : API_USUARIOS, {
        method: id ? "PUT" : "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await resp.json();
      if (!resp.ok) throw new Error(data.detail || "No se pudo guardar el usuario.");

      cerrarModal("modal-usuario");
      const msg = document.getElementById("msg-usuarios");
      msg.className = "badge-verde";
      msg.style.display = "block";
      msg.style.padding = "12px 16px";
      msg.style.borderRadius = "10px";
      msg.textContent = data.mensaje;
      await cargarUsuarios();
    } catch (err) {
      errBox.textContent = err.message;
      errBox.style.display = "block";
    }
  });
});