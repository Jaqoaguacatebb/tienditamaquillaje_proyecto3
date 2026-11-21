"""Backend de la Tiendita de Maquillaje (Proyecto 3).

Persistencia en CSV (data/productos.csv y data/ventas.csv) y analítica con Pandas.
"""
import asyncio
import csv
import os
from datetime import datetime
from pathlib import Path

import pandas as pd
from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

BASE_DIR = Path(__file__).resolve().parent.parent
# DATA_DIR se puede sobreescribir (lo usan las pruebas para no tocar los CSV reales)
DATA_DIR = Path(os.environ.get("DATA_DIR", BASE_DIR / "data"))
PRODUCTOS_CSV = DATA_DIR / "productos.csv"
VENTAS_CSV = DATA_DIR / "ventas.csv"
FRONTEND_DIR = BASE_DIR / "frontend"

CAMPOS_PRODUCTOS = ["id", "nombre", "precio", "cantidad"]
CAMPOS_VENTAS = ["fecha", "id_producto", "producto", "precio", "cantidad", "total"]

app = FastAPI(title="Tiendita de Maquillaje - Proyecto 3")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# Evita que dos peticiones simultáneas lean/escriban el CSV al mismo tiempo
lock = asyncio.Lock()


# ---------------------------------------------------------------- utilidades CSV
def asegurar_archivos() -> None:
    """Crea los CSV con su encabezado si no existen."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    for ruta, campos in ((PRODUCTOS_CSV, CAMPOS_PRODUCTOS), (VENTAS_CSV, CAMPOS_VENTAS)):
        if not ruta.exists():
            with open(ruta, "w", newline="", encoding="utf-8") as f:
                csv.writer(f).writerow(campos)


def leer_productos() -> list[dict]:
    asegurar_archivos()
    df = pd.read_csv(PRODUCTOS_CSV)
    if df.empty:
        return []
    df["id"] = df["id"].astype(int)
    df["cantidad"] = df["cantidad"].astype(int)
    return df.to_dict(orient="records")


def escribir_productos(productos: list[dict]) -> None:
    """Reescribe completo productos.csv (se usa al comprar y al eliminar)."""
    df = pd.DataFrame(productos, columns=CAMPOS_PRODUCTOS)
    # 200.0 -> 200 para que el CSV se vea limpio; los precios con centavos se respetan
    df["precio"] = df["precio"].map(lambda x: int(x) if float(x).is_integer() else float(x)).astype(object)
    df.to_csv(PRODUCTOS_CSV, index=False, encoding="utf-8")


def registrar_venta(producto: dict, cantidad: int) -> None:
    asegurar_archivos()
    with open(VENTAS_CSV, "a", newline="", encoding="utf-8") as f:
        csv.writer(f).writerow([
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            producto["id"],
            producto["nombre"],
            producto["precio"],
            cantidad,
            round(producto["precio"] * cantidad, 2),
        ])


def leer_ventas() -> pd.DataFrame:
    asegurar_archivos()
    df = pd.read_csv(VENTAS_CSV)
    if not df.empty:
        df["fecha"] = pd.to_datetime(df["fecha"])
    return df


# ---------------------------------------------------------------- modelos
class ProductoNuevo(BaseModel):
    nombre: str = Field(min_length=1)
    precio: float = Field(gt=0)
    cantidad: int = Field(ge=0)


class Compra(BaseModel):
    cantidad: int = Field(default=1, ge=1)


# ---------------------------------------------------------------- CRUD de productos
@app.get("/productos")
async def listar_productos():
    async with lock:
        return leer_productos()


@app.post("/productos", status_code=status.HTTP_201_CREATED)
async def crear_producto(nuevo: ProductoNuevo):
    async with lock:
        productos = leer_productos()
        siguiente_id = max((p["id"] for p in productos), default=0) + 1
        producto = {"id": siguiente_id, **nuevo.model_dump()}
        productos.append(producto)
        escribir_productos(productos)
    return producto


@app.post("/productos/{producto_id}")
async def comprar_producto(producto_id: int, compra: Compra | None = None):
    cantidad = compra.cantidad if compra else 1
    async with lock:
        productos = leer_productos()
        for p in productos:
            if p["id"] == producto_id:
                if p["cantidad"] < cantidad:
                    raise HTTPException(400, f"Stock insuficiente: quedan {p['cantidad']}")
                p["cantidad"] -= cantidad
                escribir_productos(productos)
                registrar_venta(p, cantidad)
                return {"mensaje": "Producto comprado", "producto": p["nombre"],
                        "total": round(p["precio"] * cantidad, 2), "stock_restante": p["cantidad"]}
    raise HTTPException(404, "Producto no existe")


@app.delete("/productos/{producto_id}")
async def eliminar_producto(producto_id: int):
    async with lock:
        productos = leer_productos()
        restantes = [p for p in productos if p["id"] != producto_id]
        if len(restantes) == len(productos):
            raise HTTPException(404, "Producto no existe")
        escribir_productos(restantes)  # reescribe el CSV sin el registro
    return {"mensaje": f"Producto {producto_id} eliminado"}


# ---------------------------------------------------------------- analítica con Pandas
@app.get("/analitica/kpis")
async def kpis():
    async with lock:
        df = leer_ventas()
    if df.empty:
        return {"producto_estrella": None, "unidades_producto_estrella": 0, "ingresos_totales": 0.0,
                "total_transacciones": 0, "ticket_promedio": 0.0, "unidades_vendidas": 0}
    por_producto = df.groupby("producto")["cantidad"].sum().sort_values(ascending=False)
    return {
        "producto_estrella": str(por_producto.index[0]),
        "unidades_producto_estrella": int(por_producto.iloc[0]),
        "ingresos_totales": round(float(df["total"].sum()), 2),
        "total_transacciones": int(len(df)),
        "ticket_promedio": round(float(df["total"].mean()), 2),
        "unidades_vendidas": int(df["cantidad"].sum()),
    }


@app.get("/analitica/ventas-por-producto")
async def ventas_por_producto():
    async with lock:
        df = leer_ventas()
    if df.empty:
        return []
    res = (df.groupby("producto")
             .agg(unidades=("cantidad", "sum"), ingresos=("total", "sum"))
             .reset_index().sort_values("ingresos", ascending=False))
    res["ingresos"] = res["ingresos"].round(2)
    return res.to_dict(orient="records")


@app.get("/analitica/ventas-por-fecha")
async def ventas_por_fecha():
    async with lock:
        df = leer_ventas()
    if df.empty:
        return []
    df["dia"] = df["fecha"].dt.strftime("%Y-%m-%d")
    res = (df.groupby("dia")
             .agg(ingresos=("total", "sum"), unidades=("cantidad", "sum"), transacciones=("total", "count"))
             .reset_index().sort_values("dia"))
    res["ingresos"] = res["ingresos"].round(2)
    return res.rename(columns={"dia": "fecha"}).to_dict(orient="records")


# ---------------------------------------------------------------- frontend
@app.get("/", include_in_schema=False)
async def raiz():
    return RedirectResponse("/tienda/")


app.mount("/tienda", StaticFiles(directory=FRONTEND_DIR, html=True), name="tienda")
