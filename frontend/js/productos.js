const API_CATALOGOS = `${API_BASE}/api/catalogos`;
let listaProductos = [];
let insumosActivos = [];

// Las recetas nuevas solo ofrecen insumos activos. Al editar, un insumo que ya estaba en
// la receta y ahora está inactivo (renglonActual) se muestra marcado para no cambiarlo
// en silencio por otro; el backend solo lo acepta si el producto está inactivo.
function crearFilaReceta(idInsumo = "", cantidad = "", renglonActual = null) {
  const contenedor = document.getElementById("lista-renglones-receta");
  const fila = document.createElement("div");
  fila.className = "renglon-receta";

  const opcionesInsumo = [...insumosActivos];
  if (renglonActual && !insumosActivos.some(i => String(i.id_insumo) === String(renglonActual.id_insumo))) {
    opcionesInsumo.unshift({ id_insumo: renglonActual.id_insumo, nombre: `${renglonActual.insumo} (inactivo)`, unidad_medida: renglonActual.unidad_medida });
  }

  const opciones = opcionesInsumo.map(i =>
    `<option value="${i.id_insumo}" data-unidad="${escaparHtml(i.unidad_medida)}" ${String(i.id_insumo) === String(idInsumo) ? "selected" : ""}>
      ${escaparHtml(i.nombre)}
    </option>`
  ).join("");

  const insInicial = opcionesInsumo.find(i => String(i.id_insumo) === String(idInsumo)) || opcionesInsumo[0];
  const unidadInicial = insInicial ? insInicial.unidad_medida : "g";

  fila.innerHTML = `
    <select class="sel-insumo-receta" required>${opciones}</select>
    <input type="number" class="inp-cant-receta" step="0.01" min="0.01" placeholder="Cantidad" value="${cantidad}" required>
    <span class="unidad-tag">${escaparHtml(unidadInicial)}</span>
    <button type="button" class="btn btn-peligro btn-quitar-renglon" title="Quitar insumo">Quitar</button>
  `;

  const sel = fila.querySelector(".sel-insumo-receta");
  const tag = fila.querySelector(".unidad-tag");
  sel.addEventListener("change", () => {
    const opt = sel.options[sel.selectedIndex];
    tag.textContent = opt ? opt.dataset.unidad : "";
  });

  fila.querySelector(".btn-quitar-renglon").addEventListener("click", () => {
    if (contenedor.children.length > 1) {
      fila.remove();
    }
  });

  contenedor.appendChild(fila);
}

function abrirModalNuevoProducto() {
  document.getElementById("titulo-modal-prod").textContent = "Nuevo producto";
  document.getElementById("prod-id").value = "";
  document.getElementById("form-producto").reset();
  document.getElementById("error-modal-prod").style.display = "none";
  document.getElementById("lista-renglones-receta").innerHTML = "";
  crearFilaReceta();
  abrirModal("modal-producto");
}

function abrirModalEditarProducto(id) {
  const prod = listaProductos.find(p => p.id_producto === id);
  if (!prod) return;

  document.getElementById("titulo-modal-prod").textContent = "Editar producto";
  document.getElementById("prod-id").value = prod.id_producto;
  document.getElementById("prod-nombre").value = prod.nombre;
  document.getElementById("prod-categoria").value = prod.categoria;
  document.getElementById("prod-precio").value = prod.precio_venta;
  document.getElementById("error-modal-prod").style.display = "none";

  const contenedor = document.getElementById("lista-renglones-receta");
  contenedor.innerHTML = "";
  if (prod.receta && prod.receta.length) {
    prod.receta.forEach(r => crearFilaReceta(r.id_insumo, r.cantidad_necesaria, r));
  } else {
    crearFilaReceta();
  }

  abrirModal("modal-producto");
}

function mostrarMensajeProductos(texto, esError = false) {
  const msg = document.getElementById("msg-productos");
  msg.className = esError ? "alerta-error" : "badge-verde";
  msg.style.display = "block";
  msg.style.padding = "12px 16px";
  msg.style.borderRadius = "10px";
  msg.textContent = texto;
}

async function enviarAccionProducto(url, opciones, respaldo) {
  try {
    const resp = await fetch(url, opciones);
    const data = await leerJsonSeguro(resp);
    if (!resp.ok) throw new Error(mensajeError(data, respaldo, resp.status));
    mostrarMensajeProductos(data.mensaje);
  } catch (err) {
    mostrarMensajeProductos(mensajeExcepcion(err, respaldo), true);
  }
  await cargarProductosEInsumos();
}

function cambiarEstadoProducto(id, estado) {
  return enviarAccionProducto(`${API_CATALOGOS}/productos/${id}/estado`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ estado }),
  }, "No se pudo cambiar el estado del producto.");
}

// Desactivar y Eliminar piden confirmación (RF 14); Activar se aplica directo
function confirmarDesactivarProducto(id) {
  const prod = listaProductos.find(p => p.id_producto === id);
  if (!prod) return;
  mostrarConfirmacion({
    titulo: `¿Desactivar «${prod.nombre}»?`,
    mensaje: "Dejará de aparecer en Caja; sus ventas y reportes se conservan. ¿Deseas continuar?",
    textoConfirmar: "Sí, desactivar",
    onConfirmar: () => cambiarEstadoProducto(id, "inactivo"),
  });
}

function confirmarEliminarProducto(id) {
  const prod = listaProductos.find(p => p.id_producto === id);
  if (!prod || !prod.puede_eliminar) return;
  mostrarConfirmacion({
    titulo: `¿Eliminar «${prod.nombre}»?`,
    mensaje: "Nunca se ha vendido, así que se borrará del catálogo junto con su receta de forma permanente. ¿Deseas continuar?",
    textoConfirmar: "Sí, eliminar producto",
    onConfirmar: () => enviarAccionProducto(`${API_CATALOGOS}/productos/${id}`, { method: "DELETE" }, "No se pudo eliminar el producto."),
  });
}

function botonesProducto(p) {
  const estado = p.estado === "activo"
    ? `<button type="button" class="btn btn-secundario" onclick="confirmarDesactivarProducto(${p.id_producto})">Desactivar</button>`
    : `<button type="button" class="btn btn-secundario" onclick="cambiarEstadoProducto(${p.id_producto}, 'activo')">Activar</button>`;
  const motivo = escaparHtml(p.motivo_no_eliminar || "Tiene historial: usa Desactivar");
  const eliminar = p.puede_eliminar
    ? `<button type="button" class="btn btn-peligro" onclick="confirmarEliminarProducto(${p.id_producto})">Eliminar</button>`
    : `<span class="btn-con-motivo" title="${motivo}"><button type="button" class="btn btn-peligro" disabled aria-disabled="true" title="${motivo}">Eliminar</button></span>`;
  return `
        <button type="button" class="btn btn-secundario" onclick="abrirModalEditarProducto(${p.id_producto})">Editar</button>
        ${estado}
        ${eliminar}`;
}

function renderizarProductos() {
  const texto = document.getElementById("buscar-prod").value.trim().toLowerCase();
  const cat = document.getElementById("filtro-cat-prod").value;
  const est = document.getElementById("filtro-est-prod").value;

  const filtrados = listaProductos.filter(p => {
    const okTexto = !texto || p.nombre.toLowerCase().includes(texto);
    const okCat = cat === "todas" || p.categoria === cat;
    const okEst = est === "todos" || p.estado === est;
    return okTexto && okCat && okEst;
  });

  const tbody = document.getElementById("tabla-productos");
  if (!filtrados.length) {
    tbody.innerHTML = `<tr><td colspan="6" style="text-align:center; padding:18px;">No se encontraron productos.</td></tr>`;
    return;
  }

  tbody.innerHTML = filtrados.map(p => `
    <tr>
      <td><strong>${escaparHtml(p.nombre)}</strong></td>
      <td>${escaparHtml(p.categoria)}</td>
      <td>$${Number(p.precio_venta).toFixed(2)}</td>
      <td>${p.estado === "activo" ? '<span class="badge badge-verde">Activo</span>' : '<span class="badge badge-gris">Inactivo</span>'}</td>
      <td>${p.total_insumos} ${p.total_insumos === 1 ? "insumo" : "insumos"}</td>
      <td class="acciones-fila">${botonesProducto(p)}
      </td>
    </tr>
  `).join("");
}

async function cargarProductosEInsumos() {
  const [respProd, respIns] = await Promise.all([
    fetch(`${API_CATALOGOS}/productos`),
    fetch(`${API_CATALOGOS}/insumos?incluir_inactivos=false`),
  ]);
  const dataProd = await respProd.json();
  const dataIns = await respIns.json();

  listaProductos = dataProd.productos || [];
  insumosActivos = dataIns.insumos || [];

  document.getElementById("kpi-prod-total").textContent = listaProductos.length;
  document.getElementById("kpi-prod-activos").textContent = listaProductos.filter(p => p.estado === "activo").length;
  const cats = [...new Set(listaProductos.map(p => p.categoria))];
  document.getElementById("kpi-prod-cats").textContent = cats.length;

  const selCat = document.getElementById("filtro-cat-prod");
  const actual = selCat.value;
  selCat.innerHTML = `<option value="todas">Todas las categorías</option>` +
    cats.map(c => `<option value="${escaparHtml(c)}">${escaparHtml(c)}</option>`).join("");
  if (cats.includes(actual)) selCat.value = actual;

  renderizarProductos();
}

document.addEventListener("DOMContentLoaded", async () => {
  await cargarProductosEInsumos();

  document.getElementById("btn-nuevo-producto").addEventListener("click", abrirModalNuevoProducto);
  document.getElementById("btn-agregar-renglon").addEventListener("click", () => crearFilaReceta());
  document.getElementById("buscar-prod").addEventListener("input", renderizarProductos);
  document.getElementById("filtro-cat-prod").addEventListener("change", renderizarProductos);
  document.getElementById("filtro-est-prod").addEventListener("change", renderizarProductos);

  document.getElementById("form-producto").addEventListener("submit", async (e) => {
    e.preventDefault();
    const errBox = document.getElementById("error-modal-prod");
    errBox.style.display = "none";

    const id = document.getElementById("prod-id").value;

    const filas = [...document.querySelectorAll("#lista-renglones-receta .renglon-receta")];
    const receta = filas.map(f => ({
      id_insumo: parseInt(f.querySelector(".sel-insumo-receta").value, 10),
      cantidad_necesaria: parseFloat(f.querySelector(".inp-cant-receta").value),
    }));

    const payload = {
      nombre: document.getElementById("prod-nombre").value.trim(),
      categoria: document.getElementById("prod-categoria").value,
      precio_venta: parseFloat(document.getElementById("prod-precio").value),
      receta,
    };

    try {
      const url = id ? `${API_CATALOGOS}/productos/${id}` : `${API_CATALOGOS}/productos`;
      const method = id ? "PUT" : "POST";
      const resp = await fetch(url, {
        method,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await leerJsonSeguro(resp);
      if (!resp.ok) throw new Error(mensajeError(data, "No se pudo guardar el producto.", resp.status));

      cerrarModal("modal-producto");
      mostrarMensajeProductos(data.mensaje);
      await cargarProductosEInsumos();
    } catch (err) {
      errBox.textContent = mensajeExcepcion(err);
      errBox.style.display = "block";
    }
  });
});