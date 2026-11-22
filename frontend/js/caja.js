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
    productos = await resp.json();
  } catch (e) {
    console.warn("Usando catálogo local de prueba en Caja:", e.message);
    productos = CATALOGO_RESPALDO;
  }
  renderizarProductos();
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
    btn.disabled = !prod.disponible;

    const textoPrecio = prod.disponible
      ? `$${prod.precio.toFixed(2)}`
      : `$${prod.precio.toFixed(2)} · Sin stock`;

    btn.innerHTML = `
      <span class="prod-nombre">${prod.nombre}</span>
      <span class="prod-precio">${textoPrecio}</span>
    `;

    if (prod.disponible) {
      btn.addEventListener("click", () => agregarAComanda(prod));
    }

    grid.appendChild(btn);
  });
}

// 3. Agregar producto o sumar cantidad en la comanda
function agregarAComanda(producto) {
  ocultarAlertaStock();
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
    return;
  }

  tbody.innerHTML = "";
  let total = 0;

  comanda.forEach(item => {
    const subtotal = item.precio * item.cantidad;
    total += subtotal;

    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td><strong>${item.nombre}</strong></td>
      <td>
        <div class="ctrl-cant">
          <button type="button" class="btn-cant" onclick="cambiarCantidad(${item.id_producto}, -1)">-</button>
          <span>${item.cantidad}</span>
          <button type="button" class="btn-cant" onclick="cambiarCantidad(${item.id_producto}, 1)">+</button>
        </div>
      </td>
      <td>$${subtotal.toFixed(2)}</td>
    `;
    tbody.appendChild(tr);
  });

  totalEl.textContent = `Total: $${total.toFixed(2)}`;
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

  const usuarioActivo = JSON.parse(localStorage.getItem("usuario") || '{"id_usuario": 1}');
  const payload = {
    id_usuario: usuarioActivo.id_usuario || 1,
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
    // "detail" es texto en 400/409; en otros errores puede ser una lista u omitirse
    alertaStock.textContent = (typeof data.detail === "string" && data.detail)
      ? data.detail
      : "No se realizó el cobro. Revise la comanda e intente de nuevo.";
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