// Si la página se abre desde la propia API (/tienda/) usa el mismo origen;
// si se abre como archivo suelto (file://), apunta a uvicorn en local.
const API = location.protocol.startsWith("http") ? "" : "http://127.0.0.1:8000";

const PALETA = ["#c2456b", "#b8894b", "#7a5c8e", "#d98aa3", "#5f8f7b", "#e0a86a", "#8c4a5f", "#4f6d8f"];

const $ = (id) => document.getElementById(id);
const dinero = (n) => Number(n).toLocaleString("es-MX", { style: "currency", currency: "MXN" });

// Instancias de Chart.js: se destruyen antes de volver a dibujar
const graficas = { productos: null, fechas: null, pastel: null };

// ---------------------------------------------------------------- utilidades
let temporizadorAviso;
function aviso(texto, esError = false) {
  const el = $("aviso");
  el.textContent = texto;
  el.className = "aviso" + (esError ? " aviso--error" : "");
  el.hidden = false;
  clearTimeout(temporizadorAviso);
  temporizadorAviso = setTimeout(() => (el.hidden = true), 4500);
}

async function pedir(ruta, opciones) {
  const r = await fetch(API + ruta, opciones);
  let datos = null;
  try { datos = await r.json(); } catch (_) { /* respuesta sin cuerpo */ }
  if (!r.ok) throw new Error((datos && datos.detail) || `Error ${r.status}`);
  return datos;
}

function escapar(texto) {
  const d = document.createElement("div");
  d.textContent = texto;
  return d.innerHTML;
}

// ---------------------------------------------------------------- inventario
async function cargarProductos() {
  const productos = await pedir("/productos");
  const tbody = $("tabla");
  tbody.innerHTML = "";
  if (!productos.length) {
    tbody.innerHTML = `<tr><td colspan="5" class="vacio">No hay productos en el catálogo.</td></tr>`;
    return;
  }
  productos.forEach((p) => {
    const tr = document.createElement("tr");
    const agotado = p.cantidad <= 0;
    tr.innerHTML = `
      <td>${p.id}</td>
      <td>${escapar(p.nombre)}</td>
      <td class="num">${dinero(p.precio)}</td>
      <td class="num ${p.cantidad <= 5 ? "stock-bajo" : ""}">${agotado ? "Agotado" : p.cantidad}</td>
      <td class="acciones"><div class="acciones__botones">
        <button class="btn btn--primario" data-accion="comprar" data-id="${p.id}" ${agotado ? "disabled" : ""}>Comprar</button>
        <button class="btn btn--peligro" data-accion="eliminar" data-id="${p.id}" data-nombre="${escapar(p.nombre)}">Eliminar</button>
      </div></td>`;
    tbody.appendChild(tr);
  });
}

// ---------------------------------------------------------------- dashboard
async function cargarKpis() {
  const k = await pedir("/analitica/kpis");
  $("kpi-estrella").textContent = k.producto_estrella ?? "Sin ventas";
  $("kpi-estrella-nota").textContent = k.producto_estrella ? `${k.unidades_producto_estrella} unidades vendidas` : "";
  $("kpi-ingresos").textContent = dinero(k.ingresos_totales);
  $("kpi-transacciones").textContent = k.total_transacciones;
  $("kpi-ticket").textContent = dinero(k.ticket_promedio);
}

function dibujar(clave, idCanvas, config) {
  if (graficas[clave]) graficas[clave].destroy(); // evita gráficas encimadas
  graficas[clave] = new Chart($(idCanvas), config);
}

const opcionesBase = { responsive: true, maintainAspectRatio: false };

async function cargarGraficas() {
  const [porProducto, porFecha] = await Promise.all([
    pedir("/analitica/ventas-por-producto"),
    pedir("/analitica/ventas-por-fecha"),
  ]);

  dibujar("productos", "grafica-productos", {
    type: "bar",
    data: {
      labels: porProducto.map((d) => d.producto),
      datasets: [{ label: "Ingresos (MXN)", data: porProducto.map((d) => d.ingresos), backgroundColor: "#c2456b", borderRadius: 6 }],
    },
    options: { ...opcionesBase, plugins: { legend: { display: false } }, scales: { y: { beginAtZero: true } } },
  });

  dibujar("fechas", "grafica-fechas", {
    type: "line",
    data: {
      labels: porFecha.map((d) => d.fecha),
      datasets: [{
        label: "Ingresos por día (MXN)", data: porFecha.map((d) => d.ingresos),
        borderColor: "#9e2f52", backgroundColor: "rgba(194,69,107,.15)", fill: true, tension: 0.3, pointRadius: 3,
      }],
    },
    options: { ...opcionesBase, plugins: { legend: { display: false } }, scales: { y: { beginAtZero: true } } },
  });

  dibujar("pastel", "grafica-pastel", {
    type: "doughnut",
    data: {
      labels: porProducto.map((d) => d.producto),
      datasets: [{ data: porProducto.map((d) => d.unidades), backgroundColor: PALETA, borderColor: "#fff", borderWidth: 2 }],
    },
    options: { ...opcionesBase, plugins: { legend: { position: "right" } } },
  });
}

async function refrescarTodo() {
  try {
    await Promise.all([cargarProductos(), cargarKpis(), cargarGraficas()]);
  } catch (e) {
    aviso("No se pudo conectar con la API. ¿Está corriendo uvicorn? " + e.message, true);
  }
}

// ---------------------------------------------------------------- acciones
$("tabla").addEventListener("click", async (ev) => {
  const btn = ev.target.closest("button[data-accion]");
  if (!btn) return;
  const id = btn.dataset.id;
  btn.disabled = true;
  try {
    if (btn.dataset.accion === "comprar") {
      const r = await pedir(`/productos/${id}`, { method: "POST" });
      aviso(`Compraste ${r.producto} por ${dinero(r.total)}. Quedan ${r.stock_restante}.`);
    } else {
      if (!confirm(`¿Eliminar "${btn.dataset.nombre}" del catálogo?`)) { btn.disabled = false; return; }
      const r = await pedir(`/productos/${id}`, { method: "DELETE" });
      aviso(r.mensaje);
    }
  } catch (e) {
    aviso(e.message, true);
  }
  await refrescarTodo(); // tabla + KPIs + gráficas
});

$("formulario").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  try {
    const nuevo = await pedir("/productos", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        nombre: $("nombre").value.trim(),
        precio: parseFloat($("precio").value),
        cantidad: parseInt($("cantidad").value, 10),
      }),
    });
    aviso(`Producto "${nuevo.nombre}" agregado.`);
    ev.target.reset();
  } catch (e) {
    aviso(e.message, true);
  }
  await refrescarTodo();
});

refrescarTodo();
