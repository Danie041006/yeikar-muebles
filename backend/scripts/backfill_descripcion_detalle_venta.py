# -*- coding: utf-8 -*-
"""Rellena detalle_venta.descripcion_especifica desde el PEDIDO cuando está
vacío (notas históricas migradas).

Es la misma regla de la migración 2826f753ef1e, pero se re-ejecuta para las
ventas creadas DESPUÉS de esa migración (las 50 notas de sept 2026). Sin esto,
el detalle de cobro muestra "Ítem personalizado" en vez del texto anotado.

Idempotente: solo toca filas con descripcion_especifica NULL y sin producto.

Uso:
    python scripts/backfill_descripcion_detalle_venta.py            # dry-run
    python scripts/backfill_descripcion_detalle_venta.py --ejecutar
    python scripts/backfill_descripcion_detalle_venta.py --db-url postgresql://...
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__) + "/.."))

SELECCION = """
    SELECT dv2.id AS dv_id, (
        SELECT dp.descripcion_especifica
        FROM detalle_pedido dp
        JOIN venta v ON v.id = dv2.venta_id
        WHERE dp.pedido_id = v.pedido_id
          AND dp.cantidad = dv2.cantidad
          AND dp.precio = dv2.precio
          AND dp.tipo_item = dv2.tipo_item
          AND dp.descripcion_especifica IS NOT NULL
        ORDER BY dp.id LIMIT 1
    ) AS descripcion
    FROM detalle_venta dv2
    WHERE dv2.descripcion_especifica IS NULL
      AND dv2.producto_id IS NULL
"""

UPDATE = f"""
    UPDATE detalle_venta dv
    SET descripcion_especifica = src.descripcion
    FROM ({SELECCION}) AS src
    WHERE dv.id = src.dv_id AND src.descripcion IS NOT NULL
"""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ejecutar", action="store_true", help="Aplica los cambios (default: dry-run)")
    parser.add_argument("--db-url", help="URL de la BD (default: DATABASE_URL del entorno)")
    args = parser.parse_args()

    if args.db_url:
        os.environ["DATABASE_URL"] = args.db_url

    from app.db.session import engine
    from sqlalchemy import text

    with engine.begin() as conn:
        filas = conn.execute(text(SELECCION)).fetchall()
        con_texto = [(r[0], r[1]) for r in filas if r[1]]
        print(f"Renglones de venta sin descripción: {len(filas)}")
        print(f"  · con texto recuperable del pedido: {len(con_texto)}")
        for dv_id, desc in con_texto[:10]:
            print(f"      #{dv_id} ← {desc[:70]}")
        if len(con_texto) > 10:
            print(f"      ... y {len(con_texto) - 10} más")

        if args.ejecutar:
            res = conn.execute(text(UPDATE))
            print(f"\n✓ EJECUTADO — {res.rowcount} renglón(es) actualizado(s)")
        else:
            print("\nDRY-RUN — usa --ejecutar para aplicar.")


if __name__ == "__main__":
    main()
