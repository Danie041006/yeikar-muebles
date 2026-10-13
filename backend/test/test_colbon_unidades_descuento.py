"""Descuento de stock del COLBÓN por unidad de uso (equivalencias reales).

Verifica con las equivalencias PRÁCTICAS del taller (las mismas del seed
`scripts/sembrar_unidades_uso_colbon.py`) que pedir/usar el insumo en cuñete,
galón, pistolada o tetero (de litro y de medio litro) descuente EXACTAMENTE
la fracción de cuñete que corresponde:

    1 CUÑETE = 16 PISTOLADAS = 5 GALONES
    1 GALÓN  = 3,785 LITROS  → 1 CUÑETE = 18,925 LITROS

Cubre:
  1. Uso directo por cada unidad → cantidad base, stock, etiqueta y gasto.
  2. Pedido entregado en tetero de litro + confirmación multi-uso (medio
     tetero + 2 pistoladas) → ajuste de stock exacto y renglones aislados.

Ejecutar:  pytest test/test_colbon_unidades_descuento.py -v
"""
import os
import sys
from decimal import Decimal

from sqlalchemy import text

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"
))

from conftest import (
    ADMIN_HEADERS,
    crear_material,
    crear_movimiento,
    registrar_inventario_de_material,
)

from test_cortes_laminas import (
    stock_actual,
    _pedido_con_etapa_en_proceso,
)

from test_unidades_uso import (
    _crear_unidades,
    _usar_directo,
    _pedir,
    _cerrar_etapa,
    _gasto_monto,
)

from sembrar_unidades_uso_colbon import UNIDADES_USO


COSTO = Decimal("267000")  # precio real del CUÑETE de colbón
DECIMAL_FACTOR = Decimal("0.0000000001")

# Factores EXACTOS como los aplica el seed (misma fuente, sin drift).
FACTORES = {nombre: factor.quantize(DECIMAL_FACTOR) for nombre, factor in UNIDADES_USO}

# (descripción, cantidad digitada, unidad de uso, base esperada, etiqueta esperada)
CASOS = [
    ("1 cuñete (unidad base)", Decimal("1"), None, Decimal("1.0000"), None),
    ("1 galón", Decimal("1"), "GALÓN", Decimal("0.2000"), "1 GALÓN (= 0.2 Cuñ)"),
    ("1 pistolada", Decimal("1"), "PISTOLADA", Decimal("0.0625"), "1 PISTOLADA (= 0.0625 Cuñ)"),
    ("1 tetero de litro", Decimal("1"), "LITRO", Decimal("0.0528"), "1 LITRO (= 0.0528 Cuñ)"),
    ("tetero de medio litro (medio)", Decimal("0.5"), "LITRO", Decimal("0.0264"), "0.5 LITRO (= 0.0264 Cuñ)"),
]


def _unidad_cunete(db):
    """Unidad base real del colbón: la crea igual que el seed si no existe."""
    from app.modules.catalogos.model import UnidadMedida

    unidad = db.query(UnidadMedida).filter(UnidadMedida.nombre == "Cuñete").first()
    if unidad:
        return unidad
    unidad = UnidadMedida(nombre="Cuñete", abreviatura="Cuñ")
    db.add(unidad)
    db.commit()
    db.refresh(unidad)
    return unidad


def _setup_colbon(client, cleaner, db, stock=5):
    """Etapa EN_PROCESO + colbón (base Cuñete, $267.000) con stock y equivalencias."""
    _, _, etapa = _pedido_con_etapa_en_proceso(client, cleaner)
    cunete = _unidad_cunete(db)
    mat = crear_material(client, cleaner, costo_base=float(COSTO), unidad_medida_id=cunete.id)
    crear_movimiento(client, cleaner, mat["id"], "ENTRADA", stock)
    registrar_inventario_de_material(db, cleaner, mat["id"])
    ids = _crear_unidades(client, mat["id"], [
        {"nombre": nombre, "factor_base": float(factor)} for nombre, factor in FACTORES.items()
    ])
    return etapa, mat, ids


def test_descuento_por_unidad_uso_directo(client, cleaner, db):
    etapa, mat, ids = _setup_colbon(client, cleaner, db, stock=5)

    stock = Decimal("5.0000")
    for descripcion, cantidad, nombre_unidad, base_esperada, etiqueta_esperada in CASOS:
        extra = {"unidad_uso_id": ids[nombre_unidad]} if nombre_unidad else {}
        r = _usar_directo(client, etapa, mat["id"], float(cantidad), extra)
        assert r.status_code in (200, 201), f"{descripcion} → {r.status_code}: {r.text}"
        consumo = r.json()
        # Registrar rastro ANTES de las aserciones: si una falla, el teardown limpia.
        cleaner.registrar("consumo_material", consumo["id"])
        cleaner.registrar_gastos_like(db, f"[consumo {consumo['id']}]")
        registrar_inventario_de_material(db, cleaner, mat["id"])

        assert Decimal(str(consumo["cantidad"])) == base_esperada, \
            f"{descripcion}: descontó {consumo['cantidad']} y se esperaba {base_esperada}"
        if nombre_unidad:
            assert Decimal(str(consumo["cantidad_uso"])) == cantidad
            assert consumo["unidad_uso"]["nombre"] == nombre_unidad
        else:
            assert consumo["cantidad_uso"] is None and consumo["unidad_uso"] is None
        assert consumo["detalle_uso"] == etiqueta_esperada, \
            f"{descripcion}: etiqueta {consumo['detalle_uso']!r}"

        stock -= base_esperada
        assert stock_actual(db, mat["id"]) == stock, \
            f"{descripcion}: stock quedó {stock_actual(db, mat['id'])} y se esperaba {stock}"

        gasto_esperado = (base_esperada * COSTO).quantize(Decimal("0.01"))
        assert _gasto_monto(db, consumo["id"]) == gasto_esperado, \
            f"{descripcion}: gasto {_gasto_monto(db, consumo['id'])} ≠ {gasto_esperado}"


def test_pedido_en_tetero_y_confirmacion_multi_uso(client, cleaner, db):
    etapa, mat, ids = _setup_colbon(client, cleaner, db, stock=5)

    # Piden un TETERO DE LITRO (1 L): sale del depósito 0,0528 cuñetes (provisional).
    r = _pedir(client, etapa, mat["id"], 1, {"unidad_uso_id": ids["LITRO"]})
    assert r.status_code in (200, 201), r.text
    pedido = r.json()
    registrar_inventario_de_material(db, cleaner, mat["id"])
    assert Decimal(str(pedido["cantidad_pedida"])) == Decimal("0.0528")
    assert Decimal(str(pedido["cantidad_uso"])) == Decimal("1")
    assert pedido["unidad_uso"]["nombre"] == "LITRO"
    assert stock_actual(db, mat["id"]) == Decimal("4.9472")  # 5 − 0,0528

    # Se usó MEDIO TETERO (½ L = 0,0264) + 2 pistoladas (0,125) = 0,1514 cuñetes.
    r = client.put(
        f"/api/v1/produccion/consumo/{pedido['id']}/confirmar",
        json={"usos": [
            {"cantidad": 0.5, "unidad_uso_id": ids["LITRO"]},
            {"cantidad": 2, "unidad_uso_id": ids["PISTOLADA"]},
        ]},
        headers=ADMIN_HEADERS,
    )
    assert r.status_code == 200, r.text
    head = r.json()
    # Registrar rastro ANTES de las aserciones: si una falla, el teardown limpia.
    ids_consumos = _cerrar_etapa(db, cleaner, etapa)
    registrar_inventario_de_material(db, cleaner, mat["id"])
    assert Decimal(str(head["cantidad"])) == Decimal("0.0264")
    assert head["detalle_uso"] == "0.5 LITRO (= 0.0264 Cuñ)"
    assert Decimal(str(head["cantidad_pedida"])) == Decimal("0.0528")  # se conserva

    assert len(ids_consumos) == 2  # cabeza + hermano (2 pistoladas)

    # El hermano quedó aislado con su propia unidad y etiqueta.
    hermano = db.execute(
        text(
            "SELECT cantidad, detalle_uso, unidad_uso_id FROM consumo_material"
            " WHERE etapa_produccion_id = :e AND id <> :h"
        ),
        {"e": etapa, "h": pedido["id"]},
    ).fetchone()
    assert hermano is not None
    assert Decimal(str(hermano[0])) == Decimal("0.1250")
    assert hermano[1] == "2 PISTOLADA (= 0.125 Cuñ)"
    assert hermano[2] == ids["PISTOLADA"]

    # La entrega de 1 L cubría 0,0528; se usó 0,1514 → el neto final es 5 − 0,1514.
    assert stock_actual(db, mat["id"]) == Decimal("4.8486")

    # Un gasto por uso, al costo exacto de lo usado.
    gastos = sorted(
        g for g in (_gasto_monto(db, i) for i in ids_consumos) if g is not None
    )
    assert gastos == [Decimal("7048.80"), Decimal("33375.00")]  # 0,0264 y 0,125 × 267.000
