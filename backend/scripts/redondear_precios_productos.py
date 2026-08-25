#!/usr/bin/env python3
"""Redondea los precios de venta de los productos al millar COP (múltiplos de 1.000).

Política YEIKAR: los precios de venta terminan en `000` para que ningún
descuento porcentual o cantidad fraccionaria genere decimales o cifras
inviables (moneda mínima física en Colombia: 50 COP).

Uso:
    python3 scripts/redondear_precios_productos.py                # vista previa (dry-run)
    python3 scripts/redondear_precios_productos.py --csv reporte  # vista previa + CSV
    python3 scripts/redondear_precios_productos.py --aplicar      # aplicar cambios en BD

La vista previa compara el precio ANTIGUO vs NUEVO por producto para que
el dueño revise antes de aplicar (modo por defecto = NO toca la base).
"""
import argparse
import csv
import os
import sys
from decimal import Decimal

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy import create_engine, text

PASO = Decimal("1000")


def _redondear_half_up(valor) -> Decimal:
    v = Decimal(str(valor))
    return (v / PASO).to_integral_value(rounding="ROUND_HALF_UP") * PASO


def _db_url() -> str:
    env_path = os.path.join(os.path.dirname(__file__), "..", ".env")
    db_url = os.environ.get("DATABASE_URL", "postgresql://yeikar:yeikar123@localhost:5432/yeikar")
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                if line.startswith("DATABASE_URL="):
                    db_url = line.strip().split("=", 1)[1]
    return db_url


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--aplicar", action="store_true", help="Aplicar los cambios en la base de datos (por defecto solo vista previa)")
    parser.add_argument("--csv", default="reporte_redondeo_precios.csv", help="Ruta del CSV comparativo (antiguo vs nuevo)")
    args = parser.parse_args()

    engine = create_engine(_db_url())
    with engine.connect() as conn:
        rows = conn.execute(text(
            """
            SELECT id, nombre, codigo, precio_venta_base, precio_venta_con_iva
            FROM producto
            WHERE precio_venta_base IS NOT NULL
            ORDER BY id
            """
        )).all()

    cambios = []
    for r in rows:
        id_, nombre, codigo, pvb, pvci = r
        pvb_nuevo = _redondear_half_up(pvb)
        pvci_nuevo = _redondear_half_up(pvci) if pvci is not None else None
        cambio_base = pvb_nuevo != Decimal(str(pvb))
        cambio_iva = pvci is not None and pvci_nuevo != Decimal(str(pvci))
        if not cambio_base and not cambio_iva:
            continue
        cambios.append({
            "id": id_,
            "nombre": nombre,
            "codigo": codigo or "",
            "precio_antiguo": float(pvb),
            "precio_nuevo": float(pvb_nuevo),
            "precio_con_iva_antiguo": float(pvci) if pvci is not None else None,
            "precio_con_iva_nuevo": float(pvci_nuevo) if pvci is not None else None,
            "diferencia": float(pvb_nuevo - Decimal(str(pvb))),
            "pct_cambio": float((pvb_nuevo / Decimal(str(pvb)) - 1) * 100) if pvb else 0.0,
        })

    if not cambios:
        print(" No hay productos con precios fuera del millar. Nada que redondear.")
        return 0

    # ── Reporte comparativo (antiguo vs nuevo) ─────────────────────────────
    print(f"\n{'ID':>5}  {'PRODUCTO':<40} {'ANTIGUO':>14} {'NUEVO':>14} {'DIF':>10} {'%':>7}")
    print("-" * 95)
    for c in cambios:
        print(f"{c['id']:>5}  {c['nombre'][:40]:<40} {c['precio_antiguo']:>14,.0f} {c['precio_nuevo']:>14,.0f} {c['diferencia']:>+10,.0f} {c['pct_cambio']:>+6.1f}%")
    sube = sum(1 for c in cambios if c["diferencia"] > 0)
    baja = sum(1 for c in cambios if c["diferencia"] < 0)
    print("-" * 95)
    print(f"Total productos a redondear: {len(cambios)}  |  suben: {sube}  |  bajan: {baja}")

    if args.csv:
        with open(args.csv, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=list(cambios[0].keys()))
            writer.writeheader()
            writer.writerows(cambios)
        print(f"Reporte comparativo guardado en: {args.csv}")

    if not args.aplicar:
        print("\nVista previa (no se modificó nada). Ejecuta con --aplicar para redondear los precios.")
        return 0

    # ── Aplicar ────────────────────────────────────────────────────────────
    with engine.begin() as conn:
        for c in cambios:
            conn.execute(text(
                """
                UPDATE producto
                SET precio_venta_base = :base,
                    precio_venta_con_iva = :con_iva
                WHERE id = :id
                """
            ), {
                "base": c["precio_nuevo"],
                "con_iva": c["precio_con_iva_nuevo"],
                "id": c["id"],
            })
    print(f"\n {len(cambios)} productos redondeados al millar. Cotizaciones/ventas históricas no se tocaron.")
    return 0


if __name__ == "__main__":
    sys.exit(main())