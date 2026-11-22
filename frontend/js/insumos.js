const API_INSUMOS = `${API_BASE}/api/catalogos/insumos`;
let listaInsumos = [];

function actualizarPreviewConversion() {
  const uBase = document.getElementById("insumo-u-base").value;
  const uCompra = document.getElementById("insumo-u-compra").value;
  const factor = parseFloat(document.getElementById("insumo-factor").value) || 0;
  const nombres = { g: "gramos", ml: "mililitros", pza: "piezas" };

  document.getElementById("preview-conversion").innerHTML = `
    <strong>1 ${escaparHtml(uCompra)} = ${factor} ${escaparHtml(uBase)}</strong><br>
    <span style="color:var(--texto-suave); font-size:0.84rem;">La receta y el umbral mínimo se registran en ${nombres[uBase] || uBase}.</span>
  `;
}

function sugerirFactor() {
  const uBase = document.getElementById("insumo-u-base").value;
  const uCompra = document.getElementById("insumo-u-compra").value;
  const inputFactor = document.getElementById("insumo-factor");

  if ((uCompra === "kg" && uBase === "g") || (uCompra === "L" && uBase === "ml")) {
    inputFactor.value = 1000;
  } else if (uCompra === uBase) {
    inputFactor.value = 1;
  }
  actualizarPreviewConversion();
}

function abrirModalNuevo() {
  document.getElementById("titulo-modal-insumo").textContent = "Nuevo insumo";
  document.getElementById("insumo-id").value = "";
  document.getElementById("form-insumo").reset();
  document.getElementById("insumo-u-base").value = "g";
  document.getElementById("insumo-u-compra").value = "kg";
  document.getElementById("insumo-factor").value = 1000;
  document.getElementById("error-modal-insumo").style.display = "none";
  actualizarPreviewConversion();
  abrirModal("modal-insumo");
}

function abrirModalEditar(id) {
  const ins = listaInsumos.find(i => i.id_insumo === id);
  if (!ins) return;

  document.getElementById("titulo-modal-insumo").textContent = "Editar insumo";
  document.getElementById("insumo-id").value = ins.id_insumo;
  document.getElementById("insumo-nombre").value = ins.nombre;
  document.getElementById("insumo-categoria").value = ins.categoria;
  document.getElementById("insumo-perecedero").value = String(ins.es_perecedero);
  document.getElementById("insumo-minimo").value = ins.minimo_reposicion;
  document.getElementById("insumo-u-base").value = ins.unidad_medida;
  document.getElementById("insumo-u-compra").value = ins.unidad_compra;
  document.getElementById("insumo-factor").value = ins.factor_conversion;
  document.getElementById("error-modal-insumo").style.display = "none";
  actualizarPreviewConversion();
  abrirModal("modal-insumo");
}

function mostrarMensajeInsumos(texto, esError = false) {
  const msg = document.getElementById("msg-insumos");
  msg.className = esError ? "alerta-error" : "badge-verde";
  msg.style.display = "block";
  msg.style.padding = "12px 16px";
  msg.style.borderRadius = "10px";
  msg.textContent = texto;
}

// PATCH/DELETE con el mensaje del backend (409 explica qué productos o historial lo impiden)
async function enviarAccionInsumo(url, opciones, respaldo) {
  try {
    const resp = await fetch(url, opciones);
    const data = await leerJsonSeguro(resp);
    if (!resp.ok) throw new Error(mensajeError(data, respaldo, resp.status));
    mostrarMensajeInsumos(data.mensaje);
  } catch (err) {
    mostrarMensajeInsumos(mensajeExcepcion(err, respaldo), true);
  }
  await cargarInsumos();
}

function cambiarEstadoInsumo(id, estado) {
  return enviarAccionInsumo(`${API_INSUMOS}/${id}/estado`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ estado }),
  }, "No se pudo cambiar el estado del insumo.");
}

// Desactivar pide confirmación (RF 14); Activar se aplica directo
function confirmarDesactivarInsumo(id) {
  const ins = listaInsumos.find(i => i.id_insumo === id);
  if (!ins) return;
  const usados = ins.usado_en_productos_activos || [];
  const nota = usados.length
    ? `Se usa en productos activos (${usados.join(", ")}): primero desactiva o cambia esas recetas.`
    : "Dejará de aparecer en Recepción y al armar recetas; su historial y reportes se conservan.";
  mostrarConfirmacion({
    titulo: `¿Desactivar «${ins.nombre}»?`,
    mensaje: `${nota} ¿Deseas continuar?`,
    textoConfirmar: "Sí, desactivar",
    onConfirmar: () => cambiarEstadoInsumo(id, "Inactivo"),
  });
}

function confirmarEliminarInsumo(id) {
  const ins = listaInsumos.find(i => i.id_insumo === id);
  if (!ins || !ins.puede_eliminar) return;
  mostrarConfirmacion({
    titulo: `¿Eliminar «${ins.nombre}»?`,
    mensaje: "No tiene recetas, lotes ni movimientos, así que se borrará del catálogo de forma permanente. ¿Deseas continuar?",
    textoConfirmar: "Sí, eliminar insumo",
    onConfirmar: () => enviarAccionInsumo(`${API_INSUMOS}/${id}`, { method: "DELETE" }, "No se pudo eliminar el insumo."),
  });
}

function botonesInsumo(i) {
  const activo = i.estado === "Activo";
  const estado = activo
    ? `<button type="button" class="btn btn-secundario" onclick="confirmarDesactivarInsumo(${i.id_insumo})">Desactivar</button>`
    : `<button type="button" class="btn btn-secundario" onclick="cambiarEstadoInsumo(${i.id_insumo}, 'Activo')">Activar</button>`;
  const motivo = escaparHtml(i.motivo_no_eliminar || "Tiene historial: usa Desactivar");
  const eliminar = i.puede_eliminar
    ? `<button type="button" class="btn btn-peligro" onclick="confirmarEliminarInsumo(${i.id_insumo})">Eliminar</button>`
    : `<span class="btn-con-motivo" title="${motivo}"><button type="button" class="btn btn-peligro" disabled aria-disabled="true" title="${motivo}">Eliminar</button></span>`;
  return `
        <button type="button" class="btn btn-secundario" onclick="abrirModalEditar(${i.id_insumo})">Editar</button>
        ${estado}
        ${eliminar}`;
}

function renderizarInsumos() {
  const texto = document.getElementById("buscar-insumo").value.trim().toLowerCase();
  const cat = document.getElementById("filtro-cat-insumo").value;
  const est = document.getElementById("filtro-est-insumo").value;

  const filtrados = listaInsumos.filter(i => {
    const okTexto = !texto || i.nombre.toLowerCase().includes(texto);
    const okCat = cat === "todas" || i.categoria === cat;
    const okEst = est === "todos" || i.estado === est;
    return okTexto && okCat && okEst;
  });

  const tbody = document.getElementById("tabla-insumos");
  if (!filtrados.length) {
    tbody.innerHTML = `<tr><td colspan="8" style="text-align:center; padding:18px;">No hay insumos que coincidan con el filtro.</td></tr>`;
    return;
  }

  tbody.innerHTML = filtrados.map(i => `
    <tr>
      <td><strong>${escaparHtml(i.nombre)}</strong></td>
      <td>${escaparHtml(i.categoria)}</td>
      <td>${i.es_perecedero ? "Sí" : "No"}</td>
      <td>${escaparHtml(i.unidad_medida)}</td>
      <td>1 ${escaparHtml(i.unidad_compra)} = ${i.factor_conversion} ${escaparHtml(i.unidad_medida)}</td>
      <td>${i.minimo_reposicion} ${escaparHtml(i.unidad_medida)}</td>
      <td>${i.estado === "Activo" ? '<span class="badge badge-verde">Activo</span>' : '<span class="badge badge-rojo">Inactivo</span>'}</td>
      <td class="acciones-fila">${botonesInsumo(i)}
      </td>
    </tr>
  `).join("");
}

async function cargarInsumos() {
  const resp = await fetch(API_INSUMOS);
  const data = await resp.json();
  listaInsumos = data.insumos || [];

  document.getElementById("kpi-total").textContent = listaInsumos.length;
  document.getElementById("kpi-perecederos").textContent = listaInsumos.filter(i => i.es_perecedero).length;
  document.getElementById("kpi-no-perecederos").textContent = listaInsumos.filter(i => !i.es_perecedero).length;

  const cats = [...new Set(listaInsumos.map(i => i.categoria))];
  const selCat = document.getElementById("filtro-cat-insumo");
  const actual = selCat.value;
  selCat.innerHTML = `<option value="todas">Todas las categorías</option>` +
    cats.map(c => `<option value="${escaparHtml(c)}">${escaparHtml(c)}</option>`).join("");
  if (cats.includes(actual)) selCat.value = actual;

  renderizarInsumos();
}

document.addEventListener("DOMContentLoaded", async () => {
  await cargarInsumos();

  document.getElementById("btn-nuevo-insumo").addEventListener("click", abrirModalNuevo);
  document.getElementById("buscar-insumo").addEventListener("input", renderizarInsumos);
  document.getElementById("filtro-cat-insumo").addEventListener("change", renderizarInsumos);
  document.getElementById("filtro-est-insumo").addEventListener("change", renderizarInsumos);

  document.getElementById("insumo-u-base").addEventListener("change", sugerirFactor);
  document.getElementById("insumo-u-compra").addEventListener("change", sugerirFactor);
  document.getElementById("insumo-factor").addEventListener("input", actualizarPreviewConversion);

  document.getElementById("form-insumo").addEventListener("submit", async (e) => {
    e.preventDefault();
    const errBox = document.getElementById("error-modal-insumo");
    errBox.style.display = "none";

    const id = document.getElementById("insumo-id").value;
    const payload = {
      nombre: document.getElementById("insumo-nombre").value.trim(),
      categoria: document.getElementById("insumo-categoria").value,
      unidad_medida: document.getElementById("insumo-u-base").value,
      unidad_compra: document.getElementById("insumo-u-compra").value,
      factor_conversion: parseFloat(document.getElementById("insumo-factor").value),
      es_perecedero: document.getElementById("insumo-perecedero").value === "true",
      minimo_reposicion: parseFloat(document.getElementById("insumo-minimo").value),
    };

    try {
      const url = id ? `${API_INSUMOS}/${id}` : API_INSUMOS;
      const method = id ? "PUT" : "POST";
      const resp = await fetch(url, {
        method,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await leerJsonSeguro(resp);
      if (!resp.ok) throw new Error(mensajeError(data, "No se pudo guardar el insumo.", resp.status));

      cerrarModal("modal-insumo");
      mostrarMensajeInsumos(data.mensaje);
      await cargarInsumos();
    } catch (err) {
      errBox.textContent = mensajeExcepcion(err);
      errBox.style.display = "block";
    }
  });
});