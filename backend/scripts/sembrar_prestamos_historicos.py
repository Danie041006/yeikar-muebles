"""Sembrar la tabla `prestamo` con préstamos ya registrados en caja.

Antes del módulo de préstamos, una salida clasificada PRESTAMO dejaba el gasto
y el movimiento de caja, pero NO creaba la deuda por cobrar. Este script crea
esa fila para los movimientos indicados, para que puedan cobrarse con el flujo
normal de "Entrada → Pago de préstamo".

OJO: no procesa todo por defecto. Hay salidas clasificadas PRESTAMO que en
realidad PAGAN una deuda de la empresa (no son por cobrar), y el clasificador
antiguo no distinguía. Hay que pasar los `--gasto-ids` revisados a mano.

Ejecutar:
    cd backend && venv/bin/python scripts/sembrar_prestamos_historicos.py \
        --gasto-ids 358,391,402
    cd backend && venv/bin/python scripts/sembrar_prestamos_historicos.py \
        --gasto-ids 358,391,402 --aplicar
"""

import argparse

import app.main  # noqa: F401
from app.db.session import session_local


def _ids(valor: str | None):
    if not valor:
        return []
    return [int(x) for x in valor.replace(" ", "").split(",") if x]


def main(aplicar: bool = False, gasto_ids: list[int] | None = None):
    from app.modules.gastos.model import Gasto
    from app.modules.prestamos import service as prestamos_service
    from app.modules.reports.model import MovimientoCaja

    if not gasto_ids:
        raise SystemExit("Indica --gasto-ids con los gastos revisados (no se procesa todo por defecto).")

    db = session_local()
    try:
        creados = 0
        for gasto_id in gasto_ids:
            gasto = db.query(Gasto).filter(Gasto.id == gasto_id).first()
            if gasto is None:
                print(f"Gasto #{gasto_id}: no existe, se omite.")
                continue
            if gasto.clasificacion != "PRESTAMO":
                print(
                    f"Gasto #{gasto_id}: clasificación {gasto.clasificacion or '—'}, "
                    "no es PRESTAMO, se omite."
                )
                continue

            mov = (
                db.query(MovimientoCaja)
                .filter(MovimientoCaja.referencia == f"Gasto #{gasto.id}")
                .first()
            )
            if mov is None:
                print(f"Gasto #{gasto_id}: no tiene movimiento de caja, se omite.")
                continue
            if mov.tipo != "SALIDA":
                print(f"Gasto #{gasto_id}: el movimiento es {mov.tipo}, no SALIDA, se omite.")
                continue

            existente = (
                db.query(prestamos_service.model.Prestamo)
                .filter(prestamos_service.model.Prestamo.movimiento_caja_id == mov.id)
                .first()
            )
            if existente is not None:
                print(f"Gasto #{gasto_id}: ya tiene préstamo #{existente.id}, se omite.")
                continue

            persona = (mov.persona_entidad or "").strip()
            if not persona:
                print(f"Gasto #{gasto_id}: el movimiento no tiene persona, se omite.")
                continue

            print(
                f"Gasto #{gasto_id} · {mov.fecha} · {persona} · "
                f"{mov.monto} (moneda #{mov.moneda_id}) · caja #{mov.metodo_caja_id} "
                f"→ préstamo por cobrar"
            )
            if aplicar:
                prestamos_service.crear_prestamo(
                    db,
                    persona_nombre=persona,
                    fecha=mov.fecha,
                    moneda_id=mov.moneda_id,
                    monto=mov.monto,
                    tasa_cambio=mov.tasa_cambio,
                    metodo_caja_id=mov.metodo_caja_id,
                    movimiento_caja_id=mov.id,
                    observaciones=mov.concepto,
                    usuario_id=gasto.creado_por_id,
                )
            creados += 1

        if aplicar:
            db.commit()
            print(f"\n✅ {creados} préstamo(s) creados.")
        else:
            print(f"\n(dry-run) {creados} préstamo(s) se crearían. Repite con --aplicar.")
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gasto-ids", help="Ids de gasto separados por coma (revisados a mano)")
    parser.add_argument("--aplicar", action="store_true", help="Escribe los préstamos (sin esto es dry-run)")
    args = parser.parse_args()
    main(aplicar=args.aplicar, gasto_ids=_ids(args.gasto_ids))
