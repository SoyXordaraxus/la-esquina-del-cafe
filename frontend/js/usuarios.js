const API_USUARIOS = `${API_BASE}/api/admin/usuarios`;
let listaUsuarios = [];

const PATRON_CORREO = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

function mostrarMensajeUsuarios(texto, esError = false) {
  const msg = document.getElementById("msg-usuarios");
  msg.className = esError ? "alerta-error" : "badge-verde";
  msg.style.display = "block";
  msg.style.padding = "12px 16px";
  msg.style.borderRadius = "10px";
  msg.textContent = texto;
}

// Mismas reglas que el backend (RF 1.1); devuelve el primer problema o null
function validarFormularioUsuario(payload, idEditando) {
  if (!payload.nombre_usuario) return "El nombre de usuario es obligatorio.";
  if (!payload.correo) return "El correo electrónico es obligatorio.";
  if (!PATRON_CORREO.test(payload.correo)) return "El correo electrónico no es válido. Ejemplo: nombre@dominio.com";

  const pass = payload.contrasena;
  if (!idEditando && !pass) return "La contraseña es obligatoria.";
  if (pass) {
    if (pass.length < 8) return "La contraseña debe tener al menos 8 caracteres.";
    if (!/[A-Za-zÁÉÍÓÚÑáéíóúñ]/.test(pass) || !/\d/.test(pass)) return "La contraseña debe combinar letras y números.";
  }

  const otro = listaUsuarios.filter(u => String(u.id_usuario) !== String(idEditando || ""));
  if (otro.some(u => u.nombre_usuario.toLowerCase() === payload.nombre_usuario.toLowerCase())) {
    return `El nombre de usuario «${payload.nombre_usuario}» ya está en uso. Elige otro.`;
  }
  if (otro.some(u => u.correo.toLowerCase() === payload.correo.toLowerCase())) {
    return `El correo ${payload.correo.toLowerCase()} ya está registrado en otra cuenta.`;
  }
  return null;
}

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
      if (!resp.ok) {
        mostrarMensajeUsuarios(mensajeError(await leerJsonSeguro(resp), "No se pudo cambiar el estado de la cuenta.", resp.status), true);
        return;
      }
      await cargarUsuarios();
    },
  });
}

async function cargarUsuarios() {
  let data;
  try {
    const resp = await fetch(API_USUARIOS);
    data = await leerJsonSeguro(resp);
    if (!resp.ok) throw new Error(mensajeError(data, "No se pudo cargar la lista de usuarios.", resp.status));
  } catch (err) {
    mostrarMensajeUsuarios(mensajeExcepcion(err, "No se pudo cargar la lista de usuarios."), true);
    return;
  }
  listaUsuarios = data.usuarios || [];

  document.getElementById("tabla-usuarios").innerHTML = listaUsuarios.map(u => `
    <tr>
      <td><strong>${escaparHtml(u.nombre_usuario)}</strong></td>
      <td>${escaparHtml(u.correo)}</td>
      <td>${escaparHtml(u.rol)}</td>
      <td>${u.estado === "Activo" ? '<span class="badge badge-verde">Activo</span>' : '<span class="badge badge-rojo">Inactivo</span>'}</td>
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

  // Validación propia con mensajes en español (en lugar de la burbuja del navegador)
  document.getElementById("form-usuario").noValidate = true;

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

    const problema = validarFormularioUsuario(payload, id);
    if (problema) {
      errBox.textContent = problema;
      errBox.style.display = "block";
      return;
    }

    try {
      const resp = await fetch(id ? `${API_USUARIOS}/${id}` : API_USUARIOS, {
        method: id ? "PUT" : "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await leerJsonSeguro(resp);
      if (!resp.ok) throw new Error(mensajeError(data, "No se pudo guardar el usuario.", resp.status));

      cerrarModal("modal-usuario");
      mostrarMensajeUsuarios(data.mensaje);
      await cargarUsuarios();
    } catch (err) {
      errBox.textContent = mensajeExcepcion(err, "No se pudo guardar el usuario.");
      errBox.style.display = "block";
    }
  });
});