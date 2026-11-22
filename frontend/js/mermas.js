const API_ALMACEN = `${API_BASE}/api/almacen`;
let lotesDisponibles = [];
let payloadPendiente = null;

function esAdministrador() {
  const u = obtenerUsuario();
  return u && u.rol === "Administrador";
}

function obtenerLoteSeleccionado() {
  const id = parseInt(document.getElementById("select-lote").value, 10);
  return lotesDisponibles.find(l => l.id_lote === id) || null;
}

function actualizarInfoLote() {
  const lote = obtenerLoteSeleccionado();
  const box = document.getElementById("detalle-lote-box");
  const inputCant = document.getElementById("input-cantidad");
  const costoAdminSpan = document.getElementById("txt-costo-admin");
  const banner = document.getElementById("banner-limite");

  if (!lote) {
    box.style.display = "none";
    return;
  }

  box.style.display = "flex";
  inputCant.max = lote.cantidad_disponible;
  document.getElementById("txt-saldo-lote").innerHTML =
    `Saldo disponible: <strong>${lote.cantidad_disponible} ${escaparHtml(lote.unidad)}</strong>`;
  document.getElementById("txt-caducidad-lote").textContent =
    `Caducidad: ${lote.caducidad || "No perecedero"} (${lote.estado})`;

  const cant = parseFloat(inputCant.value) || 0;
  const costoEst = cant * lote.costo_unitario_base;

  // RF 11.2: Cajero NO ve el valor monetario exacto, solo alerta si supera $100
  if (esAdministrador()) {
    costoAdminSpan.style.display = "inline";
    costoAdminSpan.textContent = `Costo estimado: $${costoEst.toFixed(2)} MXN`;
  } else {
    costoAdminSpan.style.display = "none";
    if (costoEst > 100) {
      banner.style.background = "#fdf2f0";
      banner.style.borderColor = "#f5b5ae";
      banner.style.color = "#b42318";
      banner.innerHTML = "⚠️ Alerta: El valor de esta merma supera los <strong>$100.00 MXN</strong>. Se solicitará clave de Administrador al confirmar.";
    } else {
      banner.style.background = "#fef6e7";
      banner.style.borderColor = "#f2c97d";
      banner.style.color = "#7a4b00";
      banner.innerHTML = "Atención: Mermas mayores a <strong>$100.00 MXN</strong> registradas por Cajero requieren autorización de Administrador.";
    }
  }
}

async function enviarMerma(payload) {
  const msg = document.getElementById("msg-merma");
  msg.style.display = "none";

  const resp = await fetch(`${API_ALMACEN}/mermas`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const data = await leerJsonSeguro(resp);

  if (!resp.ok) {
    if (resp.status === 403 && typeof data.detail === "string" && data.detail.includes("AUTORIZACION_REQUERIDA")) {
      payloadPendiente = payload;
      document.getElementById("error-modal-admin").style.display = "none";
      document.getElementById("pass-admin-modal").value = "";
      abrirModal("modal-auth-admin");
      return false;
    }
    throw new Error(mensajeError(data, "No se pudo registrar la merma.", resp.status));
  }

  cerrarModal("modal-auth-admin");
  payloadPendiente = null;
  document.getElementById("form-merma").reset();
  document.getElementById("detalle-lote-box").style.display = "none";

  msg.className = "badge-verde";
  msg.style.display = "block";
  msg.style.padding = "12px 16px";
  msg.style.borderRadius = "10px";
  msg.textContent = data.mensaje;

  await cargarDatosIniciales();
  return true;
}

async function cargarDatosIniciales() {
  const admin = esAdministrador();
  document.getElementById("col-costo-header").style.display = admin ? "" : "none";

  const [respLotes, respMermas] = await Promise.all([
    fetch(`${API_ALMACEN}/lotes`),
    fetch(`${API_ALMACEN}/mermas`),
  ]);
  const dataLotes = await respLotes.json();
  const dataMermas = await respMermas.json();

  lotesDisponibles = (dataLotes.lotes || []).filter(l => l.cantidad_disponible > 0);
  const select = document.getElementById("select-lote");
  select.innerHTML = `<option value="">-- Selecciona un insumo y lote --</option>` +
    lotesDisponibles.map(l =>
      `<option value="${l.id_lote}">${escaparHtml(l.insumo)} · ${escaparHtml(l.codigo_lote)} (${l.cantidad_disponible} ${escaparHtml(l.unidad)}) [${l.estado}]</option>`
    ).join("");

  // Preseleccionar si viene ?lote=ID desde caducidades.html
  const params = new URLSearchParams(window.location.search);
  const loteParam = params.get("lote");
  if (loteParam && lotesDisponibles.some(l => String(l.id_lote) === loteParam)) {
    select.value = loteParam;
    document.getElementById("select-motivo").value = "Caducidad";
    actualizarInfoLote();
  }

  const tbody = document.getElementById("tabla-mermas");
  const mermas = dataMermas.mermas || [];
  if (!mermas.length) {
    tbody.innerHTML = `<tr><td colspan="${admin ? 7 : 6}" style="text-align:center; padding:18px;">Aún no hay mermas registradas.</td></tr>`;
    return;
  }

  tbody.innerHTML = mermas.map(m => `
    <tr>
      <td>${escaparHtml(m.fecha)}</td>
      <td><strong>${escaparHtml(m.insumo)}</strong></td>
      <td>Lote #${m.id_lote || "—"}</td>
      <td>${m.cantidad} ${escaparHtml(m.unidad)}</td>
      <td>${escaparHtml(m.motivo)}</td>
      <td>${escaparHtml(m.responsable)}</td>
      ${admin ? `<td>$${Number(m.costo_perdida).toFixed(2)}</td>` : ""}
    </tr>`).join("");
}

document.addEventListener("DOMContentLoaded", async () => {
  await cargarDatosIniciales();

  document.getElementById("select-lote").addEventListener("change", actualizarInfoLote);
  document.getElementById("input-cantidad").addEventListener("input", actualizarInfoLote);

  document.getElementById("form-merma").addEventListener("submit", async (e) => {
    e.preventDefault();
    const lote = obtenerLoteSeleccionado();
    const cantidad = parseFloat(document.getElementById("input-cantidad").value);
    const motivo = document.getElementById("select-motivo").value;
    const notas = document.getElementById("input-notas").value;
    const u = obtenerUsuario();

    if (!lote || !cantidad || cantidad <= 0) return;

    const payload = {
      id_lote: lote.id_lote,
      cantidad,
      motivo,
      notas,
      id_usuario: u.id_usuario || 1,
    };

    // RF 14: Cuadro de confirmación explícita antes de dar de baja
    mostrarConfirmacion({
      titulo: "Confirmar baja por merma",
      mensaje: `¿Deseas descontar ${cantidad} ${lote.unidad} de "${lote.insumo}" (Lote #${lote.id_lote}) por motivo de ${motivo}?`,
      textoConfirmar: "Sí, registrar merma",
      onConfirmar: async () => {
        try {
          await enviarMerma(payload);
        } catch (err) {
          const msg = document.getElementById("msg-merma");
          msg.className = "alerta-error";
          msg.style.display = "block";
          msg.textContent = mensajeExcepcion(err);
        }
      },
    });
  });

  document.getElementById("btn-confirmar-admin").addEventListener("click", async () => {
    const pass = document.getElementById("pass-admin-modal").value;
    const errModal = document.getElementById("error-modal-admin");
    if (!pass || !payloadPendiente) return;

    try {
      await enviarMerma({ ...payloadPendiente, password_admin: pass });
    } catch (err) {
      errModal.textContent = mensajeExcepcion(err);
      errModal.style.display = "block";
    }
  });
});