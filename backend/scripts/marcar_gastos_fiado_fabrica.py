"""Marcar los gastos de deudas fiadas como Gastos de Fábrica.

Cada cuenta por pagar ("fiar") nace con su Gasto en el P&L. Los creados antes
de esta decisión quedaron sin clasificación, así que no cuentan en el resumen
de "Gastos de Fábrica". Este script completa esa canasta.

- Solo toca gastos con `clasificacion` vacía: no pisa lo ya clasificado.
- No modifica montos, saldos, caja ni movimientos.
- Dry-run por defecto: sin --aplicar solo imprime lo que cambiaría.

Ejecutar:
    cd backend && venv/bin/python scripts/marcar_gastos_fiado_fabrica.py
    cd backend && venv/bin/python scripts/marcar_gastos_fiado_fabrica.py --aplicar
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import app.main  # noqa: F401
from app.db.session import session_local

CLASIFICACION = "GASTO_FABRICA"


def main(aplicar: bool = False) -> None:
    from app.modules.cuentas_por_pagar.model import CuentaPorPagar
    from app.modules.gastos.model import Gasto

    db = session_local()
    try:
        filas = (
            db.query(CuentaPorPagar, Gasto)
            .join(Gasto, Gasto.id == CuentaPorPagar.gasto_id)
            .filter(Gasto.clasificacion.is_(None))
            .order_by(CuentaPorPagar.id)
            .all()
        )
        if not filas:
            print("No hay gastos de fiado sin clasificar.")
            return

        total = 0.0
        for cxp, gasto in filas:
            total += float(gasto.monto or 0)
            print(
                f"CxP #{cxp.id:<6} {cxp.fecha}  {gasto.monto:>14,.2f}  "
                f"{(gasto.descripcion or '')[:70]}"
            )
        print(f"\n{len(filas)} gastos sin clasificar · total {total:,.2f}")

        if not aplicar:
            print(
                "Dry-run: nada escrito. Repite con --aplicar para marcarlos "
                f"{CLASIFICACION}."
            )
            return

        for _, gasto in filas:
            gasto.clasificacion = CLASIFICACION
        db.commit()
        print(f"{len(filas)} gastos marcados como {CLASIFICACION}.")
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--aplicar",
        action="store_true",
        help="Escribe los cambios (sin esto es un dry-run)",
    )
    argumentos = parser.parse_args()
    main(aplicar=argumentos.aplicar)
