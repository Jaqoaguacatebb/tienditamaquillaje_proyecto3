import csv
import importlib
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

DATA_ORIGINAL = Path(__file__).resolve().parent.parent / "data"


@pytest.fixture()
def client(tmp_path, monkeypatch):
    """Cada prueba trabaja con una copia de los CSV, sin tocar los reales."""
    shutil.copytree(DATA_ORIGINAL, tmp_path / "data")
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    import backend.main as main
    importlib.reload(main)
    return TestClient(main.app), tmp_path / "data"


def filas(ruta):
    with open(ruta, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def test_listar_lee_csv(client):
    c, _ = client
    r = c.get("/productos")
    assert r.status_code == 200 and len(r.json()) == 6


def test_crear_persiste_en_csv(client):
    c, d = client
    r = c.post("/productos", json={"nombre": "Brillo labial", "precio": 80, "cantidad": 15})
    assert r.status_code == 201 and r.json()["id"] == 7
    assert any(f["nombre"] == "Brillo labial" for f in filas(d / "productos.csv"))


def test_comprar_descuenta_y_registra_venta(client):
    c, d = client
    antes = len(filas(d / "ventas.csv"))
    r = c.post("/productos/6", json={"cantidad": 2})
    assert r.status_code == 200 and r.json()["stock_restante"] == 8
    assert next(f for f in filas(d / "productos.csv") if f["id"] == "6")["cantidad"] == "8"
    ventas = filas(d / "ventas.csv")
    assert len(ventas) == antes + 1
    assert ventas[-1]["producto"] == "Sombras" and float(ventas[-1]["total"]) == 500


def test_comprar_sin_body_es_una_unidad(client):
    c, _ = client
    assert c.post("/productos/1").json()["stock_restante"] == 49


def test_comprar_sin_stock_400_y_no_cambia_csv(client):
    c, d = client
    antes = len(filas(d / "ventas.csv"))
    assert c.post("/productos/6", json={"cantidad": 11}).status_code == 400
    assert len(filas(d / "ventas.csv")) == antes


def test_comprar_inexistente_404(client):
    c, _ = client
    assert c.post("/productos/99").status_code == 404


def test_eliminar_reescribe_csv(client):
    c, d = client
    assert c.delete("/productos/2").status_code == 200
    ids = [f["id"] for f in filas(d / "productos.csv")]
    assert "2" not in ids and len(ids) == 5
    assert c.delete("/productos/2").status_code == 404


def test_kpis_y_series(client):
    c, _ = client
    k = c.get("/analitica/kpis").json()
    assert k["total_transacciones"] == 48 and k["ingresos_totales"] > 0 and k["producto_estrella"]
    pp = c.get("/analitica/ventas-por-producto").json()
    assert sum(x["ingresos"] for x in pp) == pytest.approx(k["ingresos_totales"])
    pf = c.get("/analitica/ventas-por-fecha").json()
    assert len(pf) == 10 and sum(x["transacciones"] for x in pf) == 48


def test_kpis_se_actualizan_tras_compra(client):
    c, _ = client
    antes = c.get("/analitica/kpis").json()
    c.post("/productos/4")
    despues = c.get("/analitica/kpis").json()
    assert despues["total_transacciones"] == antes["total_transacciones"] + 1
    assert despues["ingresos_totales"] == antes["ingresos_totales"] + 400


def test_ventas_vacias_no_rompen(client):
    c, d = client
    (d / "ventas.csv").write_text("fecha,id_producto,producto,precio,cantidad,total\n", encoding="utf-8")
    assert c.get("/analitica/kpis").json()["total_transacciones"] == 0
    assert c.get("/analitica/ventas-por-producto").json() == []
    assert c.get("/analitica/ventas-por-fecha").json() == []


def test_compras_concurrentes_no_pasan_del_stock(client):
    """25 compradores simultáneos de un producto con stock 10: solo 10 deben lograrlo."""
    import asyncio
    import httpx
    import backend.main as main
    _, d = client

    async def correr():
        transport = httpx.ASGITransport(app=main.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
            return await asyncio.gather(*[ac.post("/productos/6") for _ in range(25)])

    codigos = [r.status_code for r in asyncio.run(correr())]
    assert codigos.count(200) == 10 and codigos.count(400) == 15
    assert next(f for f in filas(d / "productos.csv") if f["id"] == "6")["cantidad"] == "0"
