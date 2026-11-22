const API_CATALOGOS = `${API_BASE}/api/catalogos`;
let listaProductos = [];
let insumosActivos = [];

function crearFilaReceta(idInsumo = "", cantidad = "") {
  const contenedor = document.getElementById("lista-renglones-receta");
  const fila = document.createElement("div");
  fila.className = "renglon-receta";

  const opciones = insumosActivos.map(i =>
    `<option value="${i.id_insumo}" data-unidad="${escaparHtml(i.unidad_medida)}" ${String(i.id_insumo) === String(idInsumo) ? "selected" : ""}>
      ${escaparHtml(i.nombre)}
    </option>`
  ).join("");

  const insInicial = insumosActivos.find(i => String(i.id_insumo) === String(idInsumo)) || insumosActivos[0];
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
  document.getElementById("prod-estado").value = prod.estado;
  document.getElementById("error-modal-prod").style.display = "none";

  const contenedor = document.getElementById("lista-renglones-receta");
  contenedor.innerHTML = "";
  if (prod.receta && prod.receta.length) {
    prod.receta.forEach(r => crearFilaReceta(r.id_insumo, r.cantidad_necesaria));
  } else {
    crearFilaReceta();
  }

  abrirModal("modal-producto");
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
      <td>${p.estado === "activo" ? '<span class="badge-verde">Activo</span>' : '<span class="badge-amarillo" style="background:#eee;color:#555;">Inactivo</span>'}</td>
      <td>${p.total_insumos} ${p.total_insumos === 1 ? "insumo" : "insumos"}</td>
      <td>
        <button type="button" class="btn btn-secundario" onclick="abrirModalEditarProducto(${p.id_producto})">Editar</button>
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
    const u = obtenerUsuario();

    const filas = [...document.querySelectorAll("#lista-renglones-receta .renglon-receta")];
    const receta = filas.map(f => ({
      id_insumo: parseInt(f.querySelector(".sel-insumo-receta").value, 10),
      cantidad_necesaria: parseFloat(f.querySelector(".inp-cant-receta").value),
    }));

    const payload = {
      nombre: document.getElementById("prod-nombre").value.trim(),
      categoria: document.getElementById("prod-categoria").value,
      precio_venta: parseFloat(document.getElementById("prod-precio").value),
      estado: document.getElementById("prod-estado").value,
      receta,
      id_usuario: u.id_usuario || 1,
    };

    try {
      const url = id ? `${API_CATALOGOS}/productos/${id}` : `${API_CATALOGOS}/productos`;
      const method = id ? "PUT" : "POST";
      const resp = await fetch(url, {
        method,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await resp.json();
      if (!resp.ok) throw new Error(data.detail || "No se pudo guardar el producto.");

      cerrarModal("modal-producto");
      const msg = document.getElementById("msg-productos");
      msg.className = "badge-verde";
      msg.style.display = "block";
      msg.style.padding = "12px 16px";
      msg.style.borderRadius = "10px";
      msg.textContent = data.mensaje;
      await cargarProductosEInsumos();
    } catch (err) {
      errBox.textContent = err.message;
      errBox.style.display = "block";
    }
  });
});