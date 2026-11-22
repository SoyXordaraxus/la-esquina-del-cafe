const API_AUTH = "http://127.0.0.1:8000/api/auth";

document.addEventListener("DOMContentLoaded", () => {
  const formLogin = document.getElementById("form-login");
  const errorBox = document.getElementById("login-error");
  const okBox = document.getElementById("login-ok");
  const btnLogin = document.getElementById("btn-login");

  // Modal recuperación
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

  if (btnAbrirRec) btnAbrirRec.addEventListener("click", abrirModalRec);
  if (btnCancelarRec) btnCancelarRec.addEventListener("click", cerrarModalRec);
  if (modalRec) {
    modalRec.addEventListener("click", (e) => {
      if (e.target === modalRec) cerrarModalRec();
    });
  }

  // --- Envío de Inicio de Sesión ---
  if (formLogin) {
    formLogin.addEventListener("submit", async (e) => {
      e.preventDefault();
      errorBox.style.display = "none";
      okBox.style.display = "none";
      btnLogin.disabled = true;
      btnLogin.textContent = "Verificando...";

      const usuario = document.getElementById("login-usuario").value.trim();
      const contrasena = document.getElementById("login-password").value;

      try {
        const resp = await fetch(`${API_AUTH}/login`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ usuario, contrasena }),
        });

        const data = await resp.json();
        if (!resp.ok) {
          throw new Error(data.detail || "Usuario o contraseña incorrectos.");
        }

        const sesion = data.usuario || data;
        localStorage.setItem("usuario", JSON.stringify(sesion));

        if (sesion.rol === "Administrador") {
          window.location.href = "inicio.html";
        } else {
          window.location.href = "caja.html";
        }
      } catch (err) {
        errorBox.textContent = err.message;
        errorBox.style.display = "block";
      } finally {
        btnLogin.disabled = false;
        btnLogin.textContent = "Iniciar sesión";
      }
    });
  }

  // --- Envío de Recuperación Local ---
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
        const resp = await fetch(`${API_AUTH}/recuperar`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ usuario, codigo_maestro, nueva_contrasena }),
        });

        const data = await resp.json();
        if (!resp.ok) {
          throw new Error(data.detail || "No se pudo restablecer la contraseña.");
        }

        cerrarModalRec();
        errorBox.style.display = "none";
        okBox.textContent = data.mensaje || "Contraseña actualizada correctamente.";
        okBox.style.display = "block";
        document.getElementById("login-usuario").value = usuario;
        document.getElementById("login-password").value = "";
        document.getElementById("login-password").focus();
      } catch (err) {
        recError.textContent = err.message;
        recError.style.display = "block";
      } finally {
        btnGuardarRec.disabled = false;
        btnGuardarRec.textContent = "Restablecer contraseña";
      }
    });
  }
});