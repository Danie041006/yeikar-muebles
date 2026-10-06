"""Sincroniza pedidos importados (cerrados sin órdenes) con la producción real.

Los pedidos que entraron por importación masiva quedaron en ENTREGADO/TERMINADO
sin órdenes de producción: nunca entraron al Kanban, aunque parte de sus muebles
siga en el taller. Este script, dado un mapa declarativo de qué mueble está en
qué área, reconstruye ese estado:

  1. crea la orden PENDIENTE de cada línea FABRICADO que no tenga una
  2. pone el pedido en PRODUCCION (para que el estado no mienta)
  3. crea la etapa EN_PROCESO del mueble que el usuario/vendor declaró en un área

Es idempotente (se puede correr dos veces) y tiene dry-run por defecto: sin
--aplicar solo imprime el plan y no escribe nada.

Uso:
    python -m scripts.sincronizar_pedidos_importados            # dry-run
    python -m scripts.sincronizar_pedidos_importados --aplicar   # escribe

Mapa (EDITAR con la realidad del taller):
    PLAN = {
        166: {"tapiceria": [127], "sin_etapa": [125, 126]},
        167: {"ebanisteria": [128], "sin_etapa": []},
        169: {"pintura": [131], "sin_etapa": []},
    }
"""

import argparse

import app.main  # noqa: F401  registra TODOS los modelos en los mappers de SQLAlchemy
from app.db.session import session_local
from app.modules.orders import model as pedido_model
from app.modules.production.model import OrdenProduccion
from app.core.state_machine import TRANSICIONES_PEDIDO

# area_nombre -> id (se resuelve en runtime contra la tabla area)
AREAS = {
    "ebanisteria": "Ebanistería",
    "tapiceria": "Tapicería",
    "pintura": "Pintura",
    "vidrieria": "Vidriería",
}

# pedido_id -> {area: [detalle_pedido_id...], "sin_etapa": [detalle_id...]}
PLAN = {
    166: {"tapiceria": [127], "sin_etapa": [125, 126]},
    167: {"ebanisteria": [128], "sin_etapa": []},
    169: {"pintura": [131], "sin_etapa": []},
}

REABRIBLES = {"APROBADO", "PAUSADO", "TERMINADO", "ENTREGADO", "PRODUCCION"}


def _ids_areas(db):
    from app.modules.catalogos.model import Area

    return {a.nombre: a.id for a in db.query(Area).all()}


def sincronizar(db, aplicar=False):
    areas = _ids_areas(db)
    faltantes = [n for n in AREAS.values() if n not in areas]
    if faltantes:
        raise SystemExit(f"Áreas no encontradas en la BD: {faltantes}")

    for pedido_id, spec in PLAN.items():
        pedido = db.query(pedido_model.Pedido).filter(
            pedido_model.Pedido.id == pedido_id
        ).first()
        if not pedido:
            print(f"  [ERROR] pedido #{pedido_id} no existe")
            continue

        detalles = pedido.detalles
        fabricables = [
            d for d in detalles if (d.tipo_item or "FABRICADO") == "FABRICADO"
        ]
        print(f"\n=== Pedido #{pedido_id} · estado={pedido.estado} · "
              f"lineas_fabricables={len(fabricables)}")

        if pedido.estado not in REABRIBLES:
            print(f"  [ERROR] estado '{pedido.estado}' no es reabrible")
            continue

        for detalle in fabricables:
            orden = db.query(OrdenProduccion).filter(
                OrdenProduccion.detalle_pedido_id == detalle.id
            ).first()
            if orden:
                print(f"  · orden#{orden.id} ya existe ({orden.estado}) "
                      f"para detalle {detalle.id}")
                continue
            print(f"  + crear orden PENDIENTE para detalle {detalle.id}")
            if aplicar:
                db.add(OrdenProduccion(
                    detalle_pedido_id=detalle.id,
                    estado="PENDIENTE",
                    fecha_inicio=None,
                    fecha_fin=None,
                ))

        if pedido.estado != "PRODUCCION":
            print(f"  → pedido {pedido.estado} → PRODUCCION")
            if aplicar:
                pedido.estado = "PRODUCCION"

        # Las etapas se arman DESPUÉS de crear las órdenes: _etapa() necesita
        # el id de la orden, que solo existe tras el flush.
        db.flush()

        # Las líneas que el usuario/vendedor marcó como "sin etapa" (no han
        # empezado, o ya las dio por listas) se reportan y quedan PENDIENTES.
        for did in spec.get("sin_etapa", []):
            print(f"  = detalle {did}: queda PENDIENTE sin etapas")

        for area_key, detalle_ids in spec.items():
            if area_key == "sin_etapa":
                continue
            area_id = areas[AREAS[area_key]]
            for did in detalle_ids:
                detalle = next((d for d in fabricables if d.id == did), None)
                if not detalle:
                    print(f"  [ERROR] detalle {did} no es FABRICADO del pedido")
                    continue
                if aplicar:
                    db.add(_etapa(db, detalle, area_id))
                print(f"  + etapa {AREAS[area_key]} EN_PROCESO para detalle {did}")

    if aplicar:
        db.commit()
        print("\n[OK] commit realizado")
    else:
        db.rollback()
        print("\n[DRY-RUN] nada escrito. Usa --aplicar para confirmar.")


def _etapa(db, detalle, area_id):
    from app.modules.production.model import EtapaProduccion

    orden = db.query(OrdenProduccion).filter(
        OrdenProduccion.detalle_pedido_id == detalle.id
    ).first()
    if not orden:
        raise SystemExit(f"detalle {detalle.id}: no hay orden, no se puede crear etapa")
    return EtapaProduccion(
        orden_produccion_id=orden.id,
        area_id=area_id,
        # empleado_responsable queda NULL: la API lo exige pero la columna
        # permite null (etapas premarcadas). El supervisor lo asigna luego.
        empleado_responsable_id=None,
        estado="EN_PROCESO",
        observaciones="Sincronizado desde nota de entrega (mueble a la medida)",
    )


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--aplicar", action="store_true",
                    help="Escribe en la BD (por defecto solo imprime el plan)")
    args = ap.parse_args()

    db = session_local()
    try:
        sincronizar(db, aplicar=args.aplicar)
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()