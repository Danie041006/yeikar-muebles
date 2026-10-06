"""Sembrar el checklist de piezas en órdenes que ya existen.

Las órdenes creadas antes del checklist no tienen piezas; este script detecta
"juegos" (sofá + poltronas, etc.) desde la descripción del renglón o el nombre
del producto y crea las filas de `orden_pieza` que falten. Idempotente: nunca
toca una orden que ya tenga piezas. Dry-run por defecto.

Ejecutar:
    cd backend && venv/bin/python scripts/sembrar_piezas_ordenes.py          # dry-run
    cd backend && venv/bin/python scripts/sembrar_piezas_ordenes.py --aplicar
"""

import argparse

import app.main  # noqa: F401
from app.db.session import session_local


def main(aplicar: bool = False):
    from app.modules.production.model import OrdenProduccion
    from app.modules.production.piezas import detectar_piezas

    db = session_local()
    try:
        ordenes = (
            db.query(OrdenProduccion)
            .filter(OrdenProduccion.estado != "CANCELADA")
            .order_by(OrdenProduccion.id)
            .all()
        )
        creadas = 0
        for orden in ordenes:
            if orden.piezas:
                continue
            detalle = orden.detalle_pedido
            texto = None
            if detalle is not None:
                producto = detalle.producto
                texto = detalle.descripcion_especifica or (producto.nombre if producto else None)
            if not texto and orden.producto_id:
                texto = orden.producto.nombre if orden.producto else None
            piezas = detectar_piezas(texto)
            if not piezas:
                continue
            resumen = ", ".join(f"{p['nombre']} ×{p['cantidad']}" for p in piezas)
            print(f"[ORDEN #{orden.id}] {resumen}")
            if aplicar:
                from app.modules.production.model import PiezaOrden

                for posicion, pieza in enumerate(piezas):
                    db.add(PiezaOrden(
                        orden_produccion_id=orden.id,
                        posicion=posicion,
                        nombre=pieza["nombre"],
                        cantidad=pieza["cantidad"],
                    ))
                creadas += 1
        if aplicar:
            db.commit()
            print(f"\nÓrdenes actualizadas: {creadas}")
        else:
            print("\nDRY-RUN: usa --aplicar para escribir los cambios.")
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--aplicar", action="store_true", help="Escribe los cambios (sin esto solo muestra)")
    args = parser.parse_args()
    main(aplicar=args.aplicar)
