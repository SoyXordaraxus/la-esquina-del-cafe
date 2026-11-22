const API_LOGIN = `${API_BASE}/api/auth/login`;
const API_RECUPERAR = `${API_BASE}/api/auth/recuperar`;

document.addEventListener("DOMContentLoaded", () => {
  const form = document.getElementById("form-login");
  const errorBox = document.getElementById("login-error");
  const okBox = document.getElementById("login-ok");
  const btn = document.getElementById("btn-login");

  // Modal de recuperación con Código Maestro
  const modalRec = document.getElementById("modal-recuperar");
  const btnAbrirRec = document.getElementById("btn-abrir-recuperar");
  const btnCancelarRec = document.getElementById("btn-cancelar-rec");
  const formRec = document.getElementById("form-recuperar");
  const recError = document.getElementById("rec-error");
  const btnGuardarRec = document.getElementById("btn-guardar-rec");

  function abrirModalRec() {
    recError.style.display = "none";
    formRec.reset();
    const usuarioActual = document.getElementById("login-usuario").value.trim();
    if (usuarioActual) document.getElementById("rec-usuario").value = usuarioActual;
    modalRec.classList.add("abierto");
    modalRec.setAttribute("aria-hidden", "false");
  }

  function cerrarModalRec() {
    modalRec.classList.remove("abierto");
    modalRec.setAttribute("aria-hidden", "true");
  }

  if (btnAbrirRec && modalRec) btnAbrirRec.addEventListener("click", abrirModalRec);
  if (btnCancelarRec && modalRec) btnCancelarRec.addEventListener("click", cerrarModalRec);
  if (modalRec) {
    modalRec.addEventListener("click", (e) => {
      if (e.target === modalRec) cerrarModalRec();
    });
  }

  // --- Inicio de sesión ---
  if (form) {
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      errorBox.style.display = "none";
      if (okBox) okBox.style.display = "none";
      btn.disabled = true;
      btn.textContent = "Verificando...";

      const usuario = document.getElementById("login-usuario").value.trim();
      const contrasena = document.getElementById("login-password").value;

      try {
        const resp = await fetch(API_LOGIN, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ usuario, contrasena }),
        });

        const data = await leerJsonSeguro(resp);
        if (!resp.ok) {
          throw new Error(mensajeError(data, "Usuario o contraseña incorrectos.", resp.status));
        }

        const datos = data.usuario || data;
        if (!datos.id_usuario || !datos.token || !datos.rol) {
          throw new Error("Respuesta de inicio de sesión incompleta. Intenta de nuevo.");
        }
        const sesion = {
          id_usuario: datos.id_usuario,
          nombre_usuario: datos.nombre_usuario || datos.nombre,
          nombre: datos.nombre || datos.nombre_usuario,
          correo: datos.correo,
          rol: datos.rol,
          token: datos.token,
          zona_horaria: datos.zona_horaria,
        };
        localStorage.setItem(CLAVE_SESION, JSON.stringify(sesion));

        if (sesion.rol === "Administrador") {
          window.location.replace("inicio.html");
        } else {
          window.location.replace("caja.html");
        }
      } catch (err) {
        errorBox.textContent = mensajeExcepcion(err);
        errorBox.style.display = "block";
      } finally {
        btn.disabled = false;
        btn.textContent = "Iniciar sesión";
      }
    });
  }

  // --- Recuperación local con Código Maestro (público, sin token) ---
  if (formRec) {
    formRec.addEventListener("submit", async (e) => {
      e.preventDefault();
      recError.style.display = "none";

      const usuario = document.getElementById("rec-usuario").value.trim();
      const codigo_maestro = document.getElementById("rec-codigo").value;
      const nueva_contrasena = document.getElementById("rec-nueva").value;
      const confirmar = document.getElementById("rec-confirmar").value;

      if (nueva_contrasena !== confirmar) {
        recError.textContent = "Las contraseñas nuevas no coinciden.";
        recError.style.display = "block";
        return;
      }

      btnGuardarRec.disabled = true;
      btnGuardarRec.textContent = "Actualizando...";

      try {
        const resp = await fetch(API_RECUPERAR, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ usuario, codigo_maestro, nueva_contrasena }),
        });

        const data = await leerJsonSeguro(resp);
        if (!resp.ok) {
          throw new Error(mensajeError(data, "No se pudo restablecer la contraseña.", resp.status));
        }

        cerrarModalRec();
        errorBox.style.display = "none";
        if (okBox) {
          okBox.textContent = data.mensaje || "Contraseña actualizada correctamente.";
          okBox.style.display = "block";
        }
        document.getElementById("login-usuario").value = usuario;
        document.getElementById("login-password").value = "";
        document.getElementById("login-password").focus();
      } catch (err) {
        recError.textContent = mensajeExcepcion(err, "No se pudo restablecer la contraseña.");
        recError.style.display = "block";
      } finally {
        btnGuardarRec.disabled = false;
        btnGuardarRec.textContent = "Restablecer contraseña";
      }
    });
  }
});
