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

    actualizarUnidadPorDefecto();
  } catch (err) {
    mostrarMensajeRecepcion("No se pudieron cargar los catálogos desde el backend.", true);
  }
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

document.addEventListener("DOMContentLoaded", () => {
  cargarCatalogosRecepcion();
  cargarTablaLotes();

  document.getElementById("rec-insumo").addEventListener("change", actualizarUnidadPorDefecto);

  document.getElementById("form-recepcion").addEventListener("submit", async (e) => {
    e.preventDefault();
    const provVal = document.getElementById("rec-proveedor").value;
    const cadVal = document.getElementById("rec-caducidad").value;

    const payload = {
      id_insumo: parseInt(document.getElementById("rec-insumo").value, 10),
      id_proveedor: provVal ? parseInt(provVal, 10) : null,
      cantidad_ingresada: parseFloat(document.getElementById("rec-cantidad").value),
      unidad_compra: document.getElementById("rec-unidad").value,
      costo_unitario: parseFloat(document.getElementById("rec-costo").value),
      caducidad: cadVal || null,
      numero_factura: document.getElementById("rec-factura").value.trim() || null
    };

    try {
      const res = await fetch(`${API_ALMACEN}/recepcion`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
      const data = await res.json();

      if (!res.ok) {
        mostrarMensajeRecepcion(data.detail || "Error al registrar la entrada.", true);
        return;
      }

      mostrarMensajeRecepcion(`${data.mensaje}: +${data.cantidad_guardada} ${data.unidad_base} de ${data.insumo}`);
      document.getElementById("form-recepcion").reset();
      actualizarUnidadPorDefecto();
      cargarTablaLotes();
    } catch (err) {
      mostrarMensajeRecepcion("Error de red al guardar el lote.", true);
    }
  });
});