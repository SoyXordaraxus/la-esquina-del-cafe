// =========================================================
// Módulo 03_Caja + Modales M3_Cobro y M1_Confirmacion
// Autor: Francisco
// =========================================================

const API_URL = `${API_BASE}/api/ventas`;

// Catálogo local de respaldo (se usa si el backend aún no está encendido)
const CATALOGO_RESPALDO = [
  { id_producto: 1, nombre: "Café americano", categoria: "Bebidas calientes", precio: 35.00, disponible: true },
  { id_producto: 2, nombre: "Capuchino",      categoria: "Bebidas calientes", precio: 45.00, disponible: true },
  { id_producto: 3, nombre: "Latte",          categoria: "Bebidas calientes", precio: 50.00, disponible: true },
  { id_producto: 4, nombre: "Chocolate",      categoria: "Bebidas calientes", precio: 45.00, disponible: true },
  { id_producto: 5, nombre: "Frappé",         categoria: "Bebidas frías",     precio: 60.00, disponible: true },
  { id_producto: 6, nombre: "Latte frío",     categoria: "Bebidas frías",     precio: 52.00, disponible: true },
  { id_producto: 7, nombre: "Panini",         categoria: "Alimentos",         precio: 55.00, disponible: true },
  { id_producto: 8, nombre: "Pastel",         categoria: "Alimentos",         precio: 40.00, disponible: false } // Sin stock (RF 7.1)
];

let productos = [];
let stockInsumos = null;   // { id_insumo: cantidad vigente } desde el backend; null = sin datos (modo local)
let categoriaActual = "Bebidas calientes";
let comanda = []; // [{ id_producto, nombre, precio, cantidad }]

document.addEventListener("DOMContentLoaded", () => {
  cargarProductos();
  configurarEventos();
});

// 1. Cargar productos desde FastAPI o usar respaldo local
async function cargarProductos() {
  try {
    const resp = await fetch(`${API_URL}/productos-disponibles`);
    if (!resp.ok) throw new Error("Backend no disponible");
    const data = await resp.json();
    productos = data.productos || [];
    stockInsumos = data.stock_insumos || {};
  } catch (e) {
    console.warn("Usando catálogo local de prueba en Caja:", e.message);
    productos = CATALOGO_RESPALDO;
    stockInsumos = null;
  }
  renderizarProductos();
  renderizarComanda();
}

// ---------------------------------------------------------------
// Disponibilidad en pantalla (RF 7.1). Es solo una ayuda: el backend
// vuelve a validar el stock al cobrar dentro de la transacción (RF 7).
// ---------------------------------------------------------------
function buscarProducto(idProducto) {
  return productos.find(p => p.id_producto === idProducto) || null;
}

// Insumos que ya consume TODA la comanda: { id_insumo: cantidad }
function consumoComanda() {
  const consumo = {};
  comanda.forEach(item => {
    const prod = buscarProducto(item.id_producto);
    ((prod && prod.receta) || []).forEach(r => {
      consumo[r.id_insumo] = (consumo[r.id_insumo] || 0) + r.cantidad * item.cantidad;
    });
  });
  return consumo;
}

// Cuántas unidades MÁS de este producto caben con lo que ya lleva la comanda.
// Los productos comparten insumos: si la leche alcanza para 10 y ya hay 6 lattes,
// solo caben 4 capuchinos.
function cuantosMasCaben(prod) {
  if (!prod) return Infinity;
  if (!prod.disponible) return 0;
  if (stockInsumos === null || !Array.isArray(prod.receta)) return Infinity;   // modo local sin backend
  if (prod.receta.length === 0) return 0;
  const consumo = consumoComanda();
  let maximo = Infinity;
  prod.receta.forEach(r => {
    if (r.cantidad <= 0) return;
    const restante = (stockInsumos[r.id_insumo] || 0) - (consumo[r.id_insumo] || 0);
    // pequeño margen para errores de redondeo con decimales (0.1 + 0.2)
    const caben = Math.floor(restante / r.cantidad + 1e-9);
    maximo = Math.min(maximo, Math.max(caben, 0));
  });
  return maximo;
}

function cantidadEnComanda(idProducto) {
  const item = comanda.find(i => i.id_producto === idProducto);
  return item ? item.cantidad : 0;
}

function mostrarAvisoStock(prod) {
  const total = cantidadEnComanda(prod.id_producto);
  const alerta = document.getElementById("alerta-stock");
  alerta.textContent = total > 0
    ? `Solo hay insumos para ${total} ${prod.nombre} con lo que ya llevas en la comanda.`
    : `No hay insumos para ningún ${prod.nombre} con lo que ya llevas en la comanda.`;
  alerta.style.display = "block";
}

// 2. Dibujar botones táctiles de productos según categoría activa
function renderizarProductos() {
  const grid = document.getElementById("productos-grid");
  grid.innerHTML = "";

  const filtrados = productos.filter(p => p.categoria === categoriaActual);

  if (filtrados.length === 0) {
    grid.innerHTML = `<p style="color:#8D6E63;">No hay productos en esta categoría.</p>`;
    return;
  }

  filtrados.forEach(prod => {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "btn-producto";
    const caben = cuantosMasCaben(prod);
    const agotado = caben <= 0;
    btn.disabled = agotado;

    const textoPrecio = agotado
      ? `$${prod.precio.toFixed(2)} · ${prod.disponible ? "Agotado" : "Sin stock"}`
      : `$${prod.precio.toFixed(2)}`;
    const textoQuedan = Number.isFinite(caben)
      ? `<span class="prod-quedan">${agotado ? "Quedan 0" : `Quedan ${caben}`}</span>`
      : "";

    btn.innerHTML = `
      <span class="prod-nombre">${escaparTexto(prod.nombre)}</span>
      <span class="prod-precio">${textoPrecio}</span>
      ${textoQuedan}
    `;

    if (!agotado) {
      btn.addEventListener("click", () => agregarAComanda(prod));
    }

    grid.appendChild(btn);
  });
}

// 3. Agregar producto o sumar cantidad en la comanda
function escaparTexto(t) {
  return typeof escaparHtml === "function" ? escaparHtml(t) : String(t);
}

function agregarAComanda(producto) {
  ocultarAlertaStock();
  if (cuantosMasCaben(producto) < 1) {
    mostrarAvisoStock(producto);
    renderizarProductos();
    return;
  }
  const existente = comanda.find(item => item.id_producto === producto.id_producto);

  if (existente) {
    existente.cantidad += 1;
  } else {
    comanda.push({
      id_producto: producto.id_producto,
      nombre: producto.nombre,
      precio: producto.precio,
      cantidad: 1
    });
  }
  renderizarComanda();
}

function cambiarCantidad(idProducto, delta) {
  ocultarAlertaStock();
  const idx = comanda.findIndex(item => item.id_producto === idProducto);
  if (idx === -1) return;

  if (delta > 0) {
    const prod = buscarProducto(idProducto);
    if (prod && cuantosMasCaben(prod) < delta) {
      mostrarAvisoStock(prod);
      renderizarComanda();
      return;
    }
  }

  comanda[idx].cantidad += delta;
  if (comanda[idx].cantidad <= 0) {
    comanda.splice(idx, 1);
  }
  renderizarComanda();
}

// 4. Actualizar tabla de comanda y total en tiempo real
function renderizarComanda() {
  const tbody = document.getElementById("comanda-tbody");
  const totalEl = document.getElementById("comanda-total");

  if (comanda.length === 0) {
    tbody.innerHTML = `
      <tr>
        <td colspan="3" style="text-align:center; color:#8D6E63; padding:20px;">
          Sin productos agregados
        </td>
      </tr>`;
    totalEl.textContent = "Total: $0.00";
    renderizarProductos();
    return;
  }

  tbody.innerHTML = "";
  let total = 0;

  comanda.forEach(item => {
    const subtotal = item.precio * item.cantidad;
    total += subtotal;

    const sinMas = cuantosMasCaben(buscarProducto(item.id_producto)) < 1;
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td><strong>${escaparTexto(item.nombre)}</strong></td>
      <td>
        <div class="ctrl-cant">
          <button type="button" class="btn-cant" onclick="cambiarCantidad(${item.id_producto}, -1)">-</button>
          <span>${item.cantidad}</span>
          <button type="button" class="btn-cant" onclick="cambiarCantidad(${item.id_producto}, 1)"${sinMas ? ' disabled title="No hay insumos para más"' : ""}>+</button>
        </div>
      </td>
      <td>$${subtotal.toFixed(2)}</td>
    `;
    tbody.appendChild(tr);
  });

  totalEl.textContent = `Total: $${total.toFixed(2)}`;
  renderizarProductos();   // actualiza "Quedan N" y los agotados según la comanda
}

function calcularTotal() {
  return comanda.reduce((acc, item) => acc + item.precio * item.cantidad, 0);
}

function ocultarAlertaStock() {
  document.getElementById("alerta-stock").style.display = "none";
}

// 5. Configurar eventos de categorías, cancelar (M1) y cobro (M3)
function configurarEventos() {
  // Pestañas de categorías
  document.querySelectorAll(".btn-categoria").forEach(btn => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".btn-categoria").forEach(b => b.classList.remove("activa"));
      btn.classList.add("activa");
      categoriaActual = btn.dataset.cat;
      renderizarProductos();
    });
  });

  // Botón Cancelar Comanda -> invoca Modal M1_Confirmacion de menu.js
  document.getElementById("btn-cancelar-comanda").addEventListener("click", () => {
    if (comanda.length === 0) return;

    if (typeof mostrarConfirmacion === "function") {
      mostrarConfirmacion({
        titulo: "Cancelar comanda",
        mensaje: "¿Está seguro de que desea cancelar la comanda actual?",
        onConfirmar: () => {
          comanda = [];
          ocultarAlertaStock();
          renderizarComanda();
        }
      });
    } else if (confirm("¿Desea cancelar la comanda actual?")) {
      comanda = [];
      renderizarComanda();
    }
  });

  // Botón Cobrar -> abre Modal M3_Cobro
  document.getElementById("btn-abrir-cobro").addEventListener("click", () => {
    if (comanda.length === 0) {
      alert("Agrega al menos un producto a la comanda antes de cobrar.");
      return;
    }

    const total = calcularTotal();
    document.getElementById("modal-total-texto").textContent = `Total a cobrar: $${total.toFixed(2)}`;
    document.getElementById("input-recibido").value = total.toFixed(2);
    document.getElementById("texto-cambio").textContent = "Cambio: $0.00";
    document.getElementById("error-cobro").style.display = "none";

    // Efectivo marcado por defecto (cobro en <= 3 clics, RF 16)
    document.querySelector('input[name="forma_pago"][value="Efectivo"]').checked = true;
    document.getElementById("bloque-efectivo").style.display = "block";
    document.getElementById("nota-tarjeta").style.display = "none";

    abrirModal("modal-cobro");
  });

  // Cambio de forma de pago (Efectivo vs Tarjeta externa)
  document.querySelectorAll('input[name="forma_pago"]').forEach(radio => {
    radio.addEventListener("change", (e) => {
      const esEfectivo = e.target.value === "Efectivo";
      document.getElementById("bloque-efectivo").style.display = esEfectivo ? "block" : "none";
      document.getElementById("nota-tarjeta").style.display = esEfectivo ? "none" : "block";
      document.getElementById("error-cobro").style.display = "none";
    });
  });

  // Cálculo automático de cambio en Efectivo
  document.getElementById("input-recibido").addEventListener("input", () => {
    const total = calcularTotal();
    const recibido = parseFloat(document.getElementById("input-recibido").value) || 0;
    const cambio = recibido - total;
    const textoCambio = document.getElementById("texto-cambio");

    if (cambio >= 0) {
      textoCambio.style.color = "#2E7D32";
      textoCambio.textContent = `Cambio: $${cambio.toFixed(2)}`;
    } else {
      textoCambio.style.color = "#C62828";
      textoCambio.textContent = `Faltan: $${Math.abs(cambio).toFixed(2)}`;
    }
  });

  // Confirmar Pago (POST a FastAPI con transacción ACID y PEPS)
  document.getElementById("btn-confirmar-pago").addEventListener("click", procesarVenta);
}

// 6. Enviar venta al servidor FastAPI
let cobroEnCurso = false;   // evita cobrar dos veces si se hace doble clic en "Confirmar pago"

async function procesarVenta() {
  if (cobroEnCurso) return;

  const total = calcularTotal();
  const formaPago = document.querySelector('input[name="forma_pago"]:checked').value;
  const errorEl = document.getElementById("error-cobro");
  let montoRecibido = total;

  if (formaPago === "Efectivo") {
    montoRecibido = parseFloat(document.getElementById("input-recibido").value) || 0;
    if (montoRecibido < total) {
      errorEl.textContent = "El monto recibido es menor al total a cobrar.";
      errorEl.style.display = "block";
      return;
    }
  }

  const payload = {
    id_usuario: idUsuarioActual(),   // informativo: el backend toma al cajero de la sesión
    forma_pago: formaPago,
    monto_recibido: montoRecibido,
    detalles: comanda.map(item => ({
      id_producto: item.id_producto,
      cantidad: item.cantidad
    }))
  };

  const btnConfirmar = document.getElementById("btn-confirmar-pago");
  cobroEnCurso = true;
  btnConfirmar.disabled = true;

  // --- Paso 1: llamar al servidor. Solo si NO hay conexión se simula la venta ---
  let resp;
  try {
    resp = await fetch(`${API_URL}/cobrar`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
  } catch (err) {
    cobroEnCurso = false;
    btnConfirmar.disabled = false;
    // Modo prueba sin backend encendido
    cerrarModal("modal-cobro");
    const cambioLocal = formaPago === "Efectivo" ? (montoRecibido - total) : 0;
    alert(`[MODO LOCAL SIN BACKEND]\nVenta simulada por $${total.toFixed(2)}\nCambio: $${cambioLocal.toFixed(2)}`);
    comanda = [];
    renderizarComanda();
    return;
  }

  // --- Paso 2: leer la respuesta (puede venir sin JSON si el servidor falló) ---
  let data = {};
  try {
    data = await resp.json();
  } catch (e) {
    data = {};
  }
  cobroEnCurso = false;
  btnConfirmar.disabled = false;

  // --- Paso 3: el servidor rechazó la venta (falta de insumos, datos inválidos, error) ---
  if (!resp.ok) {
    cerrarModal("modal-cobro");
    const alertaStock = document.getElementById("alerta-stock");
    // 409 sin stock, 400 datos inválidos, 422 de validación o 500: siempre texto legible
    alertaStock.textContent = mensajeError(data, "No se realizó el cobro. Revise la comanda e intente de nuevo.", resp.status);
    alertaStock.style.display = "block";
    cargarProductos();   // vuelve a pedir el catálogo: los productos sin stock se ponen en gris
    return;
  }

  // --- Paso 4: venta exitosa ---
  cerrarModal("modal-cobro");
  const cambio = formaPago === "Efectivo" ? (montoRecibido - total) : 0;
  alert(`Venta #${data.id_venta || "OK"} registrada correctamente.\nCambio: $${cambio.toFixed(2)}`);
  comanda = [];
  renderizarComanda();
  cargarProductos();
}