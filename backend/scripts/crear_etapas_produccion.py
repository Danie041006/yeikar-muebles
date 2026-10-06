"""Crea etapas EN_PROCESO para un pedido ya en producción.

Para las líneas cuyo mueble el usuario/vendor declaró estar en un área ahora.
No toca el estado del pedido ni de las órdenes: solo agrega la etapa, que es
lo que hace visible el mueble en el Kanban.

Dry-run por defecto.
"""

import argparse

import app.main  # noqa: F401
from app.db.session import session_local
from app.modules.orders import model as pedido_model
from app.modules.production.model import EtapaProduccion, OrdenProduccion

AREAS = {
    "ebanisteria": "Ebanistería",
    "tapiceria": "Tapicería",
    "pintura": "Pintura",
    "vidrieria": "Vidriería",
}

# (pedido_id, detalle_pedido_id, area)
PLAN = [
    (197, 177, "tapiceria"),   # Mueble Irlandés 5pts con puff → tapizado en Málaga Grafito
    (197, 178, "ebanisteria"), # Mesa de centro → solo pintar gris plata
]


def main(aplicar=False):
    from app.modules.catalogos.model import Area

    db = session_local()
    try:
        areas = {a.nombre: a.id for a in db.query(Area).all()}
        for pedido_id, detalle_id, area_key in PLAN:
            area_nombre = AREAS[area_key]
            if area_nombre not in areas:
                raise SystemExit(f"área {area_nombre} no encontrada")
            area_id = areas[area_nombre]

            detalle = db.query(pedido_model.DetallePedido).filter(
                pedido_model.DetallePedido.id == detalle_id
            ).first()
            if not detalle or detalle.pedido_id != pedido_id:
                print(f"[ERROR] detalle {detalle_id} no pertenece al pedido {pedido_id}")
                continue
            orden = db.query(OrdenProduccion).filter(
                OrdenProduccion.detalle_pedido_id == detalle_id
            ).first()
            if not orden:
                print(f"[ERROR] detalle {detalle_id} no tiene orden de producción")
                continue
            existente = db.query(EtapaProduccion).filter(
                EtapaProduccion.orden_produccion_id == orden.id
            ).first()
            if existente:
                print(f"· orden#{orden.id} ya tiene etapa ({existente.estado})")
                continue
            print(f"+ orden#{orden.id} · detalle {detalle_id} → etapa "
                  f"{area_nombre} EN_PROCESO")
            if aplicar:
                db.add(EtapaProduccion(
                    orden_produccion_id=orden.id,
                    area_id=area_id,
                    empleado_responsable_id=None,
                    estado="EN_PROCESO",
                    observaciones="Sincronizado desde nota de entrega",
                ))
        if aplicar:
            db.commit()
            print("\n[OK] commit realizado")
        else:
            db.rollback()
            print("\n[DRY-RUN] nada escrito. Usa --aplicar.")
    finally:
        db.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--aplicar", action="store_true")
    main(aplicar=ap.parse_args().aplicar)