const API_ALMACEN = `${API_BASE}/api/almacen`;
let catalogosInsumos = [];

function mostrarMensajeRecepcion(texto, esError = false) {
  const cont = document.getElementById("alerta-recepcion");
  cont.innerHTML = `<div style="padding:12px 16px; border-radius:8px; margin-bottom:16px; font-weight:500;
    background:${esError ? "#fee2e2" : "#dcfce7"}; color:${esError ? "#b91c1c" : "#166534"};">
    ${escaparHtml(texto)}
  </div>`;
  setTimeout(() => { cont.innerHTML = ""; }, 5000);
}

async function cargarCatalogosRecepcion() {
  try {
    const res = await fetch(`${API_ALMACEN}/catalogos`);
    const data = await res.json();
    catalogosInsumos = data.insumos || [];

    const selInsumo = document.getElementById("rec-insumo");
    selInsumo.innerHTML = catalogosInsumos.map(i =>
      `<option value="${i.id_insumo}">${escaparHtml(i.nombre)} (Base: ${escaparHtml(i.unidad_medida)})</option>`
    ).join("");

    const selProv = document.getElementById("rec-proveedor");
    selProv.innerHTML = `<option value="">-- Sin proveedor --</option>` +
      (data.proveedores || []).map(p => `<option value="${p.id_proveedor}">${escaparHtml(p.nombre)}</option>`).join("");

    preseleccionarInsumoDeUrl();
    actualizarUnidadPorDefecto();
  } catch (err) {
    mostrarMensajeRecepcion("No se pudieron cargar los catálogos desde el backend.", true);
  }
}

// ?insumo=<id_insumo> (botón "Reabastecer" del Panel principal): deja ese insumo elegido
function preseleccionarInsumoDeUrl() {
  const valor = new URLSearchParams(window.location.search).get("insumo");
  if (!valor) return;
  const ins = catalogosInsumos.find(i => String(i.id_insumo) === valor);
  if (!ins) {
    mostrarMensajeRecepcion("El insumo indicado ya no está activo o no existe. Elige uno de la lista.", true);
    return;
  }
  document.getElementById("rec-insumo").value = String(ins.id_insumo);
  document.getElementById("rec-cantidad").focus();
}

function actualizarUnidadPorDefecto() {
  const idSel = parseInt(document.getElementById("rec-insumo").value, 10);
  const ins = catalogosInsumos.find(i => i.id_insumo === idSel);
  if (!ins) return;

  const selUnidad = document.getElementById("rec-unidad");
  const u = ins.unidad_medida.toLowerCase();
  if (u === "g") selUnidad.value = "kg";
  else if (u === "ml") selUnidad.value = "L";
  else selUnidad.value = "unidades";

  document.getElementById("rec-caducidad").required = Boolean(ins.es_perecedero);
}

async function cargarTablaLotes() {
  const tbody = document.getElementById("tabla-lotes-body");
  try {
    const res = await fetch(`${API_ALMACEN}/lotes`);
    const data = await res.json();
    const lotes = data.lotes || [];

    if (!lotes.length) {
      tbody.innerHTML = `<tr><td colspan="7" style="padding:12px;">No hay lotes registrados.</td></tr>`;
      return;
    }

    tbody.innerHTML = lotes.map(l => `
      <tr style="border-bottom:1px solid #eee;">
        <td style="padding:10px; font-weight:600;">#L-${l.id_lote}</td>
        <td style="padding:10px;">${escaparHtml(l.insumo)}</td>
        <td style="padding:10px;">${escaparHtml(l.proveedor)}</td>
        <td style="padding:10px;">${l.cantidad_recibida} ${escaparHtml(l.unidad)}</td>
        <td style="padding:10px; font-weight:600;">${l.cantidad_disponible} ${escaparHtml(l.unidad)}</td>
        <td style="padding:10px;">${escaparHtml(l.caducidad)}</td>
        <td style="padding:10px;">${escaparHtml(l.numero_factura)}</td>
      </tr>
    `).join("");
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="7" style="padding:12px; color:#b91c1c;">Error al conectar con el servidor.</td></tr>`;
  }
}

// Acepta lo que se pegue (ej. "FAC-1045") y deja solo los dígitos, máximo 8
function soloDigitosFactura(texto) {
  return String(texto || "").replace(/^\s*FAC-/i, "").replace(/\D/g, "").slice(0, 8);
}

document.addEventListener("DOMContentLoaded", () => {
  cargarCatalogosRecepcion();
  cargarTablaLotes();

  document.getElementById("rec-insumo").addEventListener("change", actualizarUnidadPorDefecto);

  // El input de factura solo acepta dígitos; el prefijo "FAC-" es fijo en pantalla
  const inputFactura = document.getElementById("rec-factura");
  inputFactura.addEventListener("input", () => {
    inputFactura.value = soloDigitosFactura(inputFactura.value);
  });

  document.getElementById("form-recepcion").addEventListener("submit", async (e) => {
    e.preventDefault();
    const provVal = document.getElementById("rec-proveedor").value;
    const cadVal = document.getElementById("rec-caducidad").value;

    const digitos = soloDigitosFactura(document.getElementById("rec-factura").value);
    if (!/^\d{3,8}$/.test(digitos)) {
      mostrarMensajeRecepcion("El número de factura debe tener de 3 a 8 dígitos (ej. FAC-1045).", true);
      return;
    }

    const payload = {
      id_insumo: parseInt(document.getElementById("rec-insumo").value, 10),
      id_proveedor: provVal ? parseInt(provVal, 10) : null,
      cantidad_ingresada: parseFloat(document.getElementById("rec-cantidad").value),
      unidad_compra: document.getElementById("rec-unidad").value,
      costo_unitario: parseFloat(document.getElementById("rec-costo").value),
      caducidad: cadVal || null,
      numero_factura: `FAC-${digitos}`
    };

    try {
      const res = await fetch(`${API_ALMACEN}/recepcion`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
      const data = await leerJsonSeguro(res);

      if (!res.ok) {
        mostrarMensajeRecepcion(mensajeError(data, "Error al registrar la entrada.", res.status), true);
        return;
      }

      mostrarMensajeRecepcion(`${data.mensaje}: +${data.cantidad_guardada} ${data.unidad_base} de ${data.insumo}`);
      document.getElementById("form-recepcion").reset();
      actualizarUnidadPorDefecto();
      cargarTablaLotes();
    } catch (err) {
      mostrarMensajeRecepcion(mensajeExcepcion(err, "Error de red al guardar el lote."), true);
    }
  });
});