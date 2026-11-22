const API_LOGIN = `${API_BASE}/api/auth/login`;

document.addEventListener("DOMContentLoaded", () => {
  const form = document.getElementById("form-login");
  const errorBox = document.getElementById("login-error");
  const btn = document.getElementById("btn-login");

  if (!form) return;

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    errorBox.style.display = "none";
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
});