# Rubor & Co. — Tienda de maquillaje full-stack (Proyecto 3)

Proyecto integrador de **Programación IV**: tienda web con persistencia en archivos **CSV**, analítica con **Pandas** y dashboard con **Chart.js**.

- **Backend:** FastAPI + Pandas
- **Almacenamiento:** `data/productos.csv` y `data/ventas.csv`
- **Frontend:** HTML / CSS / JavaScript (`fetch`) + Chart.js (incluido en `frontend/vendor/`, funciona sin internet)

## Giro y personalización

Rubor & Co. es una tienda de maquillaje y cuidado de la piel. El catálogo inicial (rubor, labial mate, rímel, protector solar, delineador, sombras) vive en `data/productos.csv`. La interfaz usa una paleta rosa/vino con dorado, tipografía Fraunces + Inter y un diseño propio.

## Estructura

```
.
├── backend/main.py        # API FastAPI (CRUD en CSV + endpoints con Pandas)
├── data/
│   ├── productos.csv      # id, nombre, precio, cantidad
│   └── ventas.csv         # fecha, id_producto, producto, precio, cantidad, total
├── frontend/
│   ├── index.html
│   ├── styles.css
│   ├── app.js
│   └── vendor/chart.umd.js
├── tests/test_api.py      # pruebas automatizadas
├── requirements.txt
└── requirements-dev.txt
```

## Cómo ejecutarlo

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn backend.main:app --reload
```

Abre **http://127.0.0.1:8000/** (la API sirve también el frontend en `/tienda/`).
Documentación interactiva de la API: http://127.0.0.1:8000/docs

## Endpoints

| Método | Ruta | Descripción |
|---|---|---|
| GET | `/productos` | Lista el catálogo leyendo `productos.csv` |
| POST | `/productos` | Crea un producto (agrega una fila al CSV) |
| POST | `/productos/{id}` | Compra: valida stock, descuenta en `productos.csv` y registra la venta en `ventas.csv`. Cuerpo opcional `{"cantidad": n}` (por defecto 1) |
| DELETE | `/productos/{id}` | Elimina el producto y reescribe `productos.csv` sin ese registro |
| GET | `/analitica/kpis` | Producto estrella, ingresos totales, transacciones, ticket promedio, unidades vendidas |
| GET | `/analitica/ventas-por-producto` | Unidades e ingresos por producto |
| GET | `/analitica/ventas-por-fecha` | Ingresos, unidades y transacciones por día |

Códigos de error: `400` stock insuficiente, `404` producto inexistente, `422` datos inválidos.

## Dashboard

- Tarjetas de KPIs (producto estrella, ingresos, transacciones, ticket promedio).
- Tres gráficas con Chart.js: barras (ingresos por producto), líneas (evolución por fecha) y dona (distribución de unidades).
- Al comprar, agregar o eliminar un producto se actualizan tabla, KPIs y gráficas sin recargar la página; antes de redibujar se destruye la instancia previa de cada gráfica.

## Pruebas

```bash
pip install -r requirements-dev.txt
python -m pytest -q
```

Las pruebas usan una copia temporal de los CSV (variable de entorno `DATA_DIR`), así que no modifican tus datos. Cubren: lectura, alta, compra (stock y `ventas.csv`), compra sin stock, eliminación, KPIs y series con Pandas, ventas vacías y compras concurrentes.

## Notas

- `data/ventas.csv` trae un historial de ejemplo (48 ventas de 10 días) para que el dashboard no inicie vacío. Para empezar de cero, deja solo la fila de encabezado.
- Un `asyncio.Lock` serializa las lecturas/escrituras de los CSV para evitar condiciones de carrera (tema del Proyecto 2).
