const API_SEMAFORO = "http://127.0.0.1:8000/api/inventario/semaforo";

let productosInventario = [];
let colorActivo = "todos";

async function cargarInventario() {
  try {
    const res = await fetch(API_SEMAFORO);
    if (!res.ok) throw new Error("Error al obtener el inventario");
    const data = await res.json();

    productosInventario = data.productos;

    document.getElementById("txt-suficientes").textContent = `${data.resumen.verde} suficientes`;
    document.getElementById("txt-bajas").textContent = `${data.resumen.amarillo} con existencias bajas`;
    document.getElementById("txt-criticas").textContent = `${data.resumen.rojo} con existencias críticas`;

    poblarCategorias();
    aplicarFiltros();
  } catch (err) {
    console.error("Error cargando inventario:", err);
  }
}

function poblarCategorias() {
  const selectCat = document.getElementById("filtro-categoria");
  const categorias = [...new Set(productosInventario.map(p => p.categoria))];

  selectCat.innerHTML = `<option value="todas">Todas las categorías</option>` +
    categorias.map(c => `<option value="${c}">${c}</option>`).join("");

  actualizarSubcategorias();
}

function actualizarSubcategorias() {
  const catSeleccionada = document.getElementById("filtro-categoria").value;
  const selectSub = document.getElementById("filtro-subcategoria");

  const filtradosPorCat = catSeleccionada === "todas"
    ? productosInventario
    : productosInventario.filter(p => p.categoria === catSeleccionada);

  const subcategorias = [...new Set(filtradosPorCat.map(p => p.subcategoria))];

  selectSub.innerHTML = `<option value="todas">Todas las subcategorías</option>` +
    subcategorias.map(s => `<option value="${s}">${s}</option>`).join("");

  aplicarFiltros();
}

function alternarFiltroColor(color, elemento) {
  if (colorActivo === color) {
    colorActivo = "todos";
    elemento.classList.remove("activo");
  } else {
    colorActivo = color;
    document.querySelectorAll(".leyenda-item").forEach(el => el.classList.remove("activo"));
    elemento.classList.add("activo");
  }
  aplicarFiltros();
}

function aplicarFiltros() {
  const cat = document.getElementById("filtro-categoria").value;
  const sub = document.getElementById("filtro-subcategoria").value;
  const texto = document.getElementById("buscador-producto").value.toLowerCase().trim();

  const lista = productosInventario.filter(p => {
    const okCat = cat === "todas" || p.categoria === cat;
    const okSub = sub === "todas" || p.subcategoria === sub;
    const okColor = colorActivo === "todos" || p.semaforo.color === colorActivo;
    const okTexto = p.nombre.toLowerCase().includes(texto) || p.codigo.toLowerCase().includes(texto);
    return okCat && okSub && okColor && okTexto;
  });

  renderizarTarjetas(lista);
}

function renderizarTarjetas(lista) {
  const grid = document.getElementById("grid-productos");
  document.getElementById("contador-productos").textContent = `${lista.length} productos`;

  if (lista.length === 0) {
    grid.innerHTML = `<p style="grid-column: 1 / -1; color: #7c6f66;">No se encontraron productos con esos filtros.</p>`;
    return;
  }

  grid.innerHTML = lista.map(p => `
    <article class="prod-card ${p.semaforo.color}">
      <div>
        <div class="prod-top">
          <span class="prod-estado">
            <span class="punto-lg punto-${p.semaforo.color}"></span>
            ${p.semaforo.etiqueta}
          </span>
          <span class="prod-codigo">${p.codigo}</span>
        </div>
        <h2 class="prod-nombre">${p.nombre}</h2>
      </div>

      <div class="prod-metricas">
        <div>
          <span class="metrica-label">Existencia actual</span>
          <span class="metrica-actual">${p.existencia_actual}</span>
          <span class="metrica-unidad">${p.unidad}</span>
        </div>
        <div>
          <span class="metrica-label">Existencia mínima</span>
          <span class="metrica-minima">${p.existencia_minima}</span>
          <span class="metrica-unidad">${p.unidad}</span>
        </div>
      </div>

      <div class="prod-footer">
        <span class="prod-pct">${p.semaforo.porcentaje}% del mínimo</span>
        <button type="button" class="prod-link" onclick="verDetalleProducto(${p.id})">Consultar detalle →</button>
      </div>
    </article>
  `).join("");
}

function verDetalleProducto(id) {
  const prod = productosInventario.find(p => p.id === id);
  if (!prod) return;

  document.getElementById("modal-prod-titulo").textContent = `${prod.nombre} (${prod.codigo})`;
  document.getElementById("modal-prod-contenido").innerHTML = `
    <p><strong>Categoría:</strong> ${prod.categoria} · ${prod.subcategoria}</p>
    <p><strong>Existencia actual:</strong> ${prod.existencia_actual} ${prod.unidad}</p>
    <p><strong>Existencia mínima:</strong> ${prod.existencia_minima} ${prod.unidad}</p>
    <p><strong>Nivel actual:</strong> ${prod.semaforo.porcentaje}% del mínimo (${prod.semaforo.etiqueta})</p>
  `;
  abrirModal("modal-detalle-producto");
}

document.addEventListener("DOMContentLoaded", cargarInventario);