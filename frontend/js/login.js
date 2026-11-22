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
      btn.disabled = false;
      btn.textContent = "Iniciar sesión";
    }
  });
});