"""Cierra órdenes del taller según la realidad reportada el 15/10/2026.

Contexto: los pedidos #166/#167 se importaron de notas de entrega (entraron
como ENTREGADO) y el 2/oct se reabrieron a PRODUCCION con
`sincronizar_pedidos_importados.py` para rastrear en el Kanban las piezas que
seguían en el taller. Hoy el taller reporta:

  · #166 Eddy Ascanio     — el sofacama fue entregado: cerrar SOLO su orden
                            (Tapicería → COMPLETADA). El pedido sigue abierto
                            por el Modular y el Comedor (sin etapa), que se
                            cierran cuando se reporten.
  · #167 Jesús Orlando    — el sofá de 2 puestos está listo: cerrar su orden
                            (Ebanistería). El pedido pasa a TERMINADO y el
                            envío espera despacho. NO se marca entregado.
  · #197 Mayor J. Ceballos — la mesa de centro está en depósito (hecha, sin
                            entregar): completar el retrabajo de Ebanistería,
                            cerrar la orden de la mesa. Pedido TERMINADO.

Usa los servicios reales de producción: costos, envío automático al terminar
y auditoría se disparan igual que con el botón "Finalizar" de la UI.
Idempotente (salta lo ya hecho) y dry-run por defecto.

Uso:
    python -m scripts.cerrar_ordenes_taller            # dry-run
    python -m scripts.cerrar_ordenes_taller --aplicar  # escribe

Para una próxima actualización del taller: editar las listas del PLAN y
volver a correr (dos veces el mismo plan no rompe nada).
"""

import argparse

import app.main  # noqa: F401  registra TODOS los modelos en los mappers de SQLAlchemy
from app.db.session import session_local
from app.modules.envios.model import Envio
from app.modules.envios.schemas import EnvioUpdate
from app.modules.envios.service import actualizar_envio
from app.modules.production.model import EtapaProduccion, OrdenProduccion
from app.modules.production.service import (
    cambiar_estado_etapa_produccion,
    cambiar_estado_orden_produccion,
)

# ── PLAN (15/10/2026) ────────────────────────────────────────────────────────
# Etapas abiertas que el taller ya terminó (se completan antes de finalizar).
COMPLETAR_ETAPAS = [3, 4, 12]
# Órdenes a cerrar (las PENDIENTE pasan por EN_PRODUCCION primero).
FINALIZAR_ORDENES = [6, 7, 17]
# Pedidos cuyo envío hay que marcar ENTREGADO (PREPARADO→EN_TRANSITO→ENTREGADO).
# #167 (Jesús Orlando) queda SOLO TERMINADO por decisión del usuario; si
# confirma la entrega, agregar 167 aquí y re-correr.
ENTREGAR_PEDIDOS: list[int] = []


def _texto_orden(orden: OrdenProduccion) -> str:
    """Descripción corta de la orden para los print (línea del pedido)."""
    detalle = orden.detalle_pedido
    if detalle is None:
        return "sin pedido"
    nombre = detalle.producto.nombre if detalle.producto else None
    texto = nombre or (detalle.descripcion_especifica or "")
    return texto[:55]


def _completar_etapa(db, etapa_id: int, aplicar: bool) -> None:
    etapa = db.query(EtapaProduccion).filter(EtapaProduccion.id == etapa_id).first()
    if etapa is None:
        print(f"  [ERROR] etapa #{etapa_id} no existe")
        return
    area = etapa.area.nombre if etapa.area else "¿?"
    if etapa.estado == "COMPLETADA":
        print(f"  = etapa #{etapa_id} ({area}) ya está COMPLETADA")
        return
    print(f"  → etapa #{etapa_id} ({area}, orden #{etapa.orden_produccion_id}): "
          f"{etapa.estado} → COMPLETADA")
    if aplicar:
        cambiar_estado_etapa_produccion(db, etapa_id, "COMPLETADA")


def _finalizar_orden(db, orden_id: int, aplicar: bool) -> None:
    orden = db.query(OrdenProduccion).filter(OrdenProduccion.id == orden_id).first()
    if orden is None:
        print(f"  [ERROR] orden #{orden_id} no existe")
        return
    if orden.estado == "FINALIZADA":
        print(f"  = orden #{orden_id} ya está FINALIZADA ({_texto_orden(orden)})")
        return
    print(f"  → orden #{orden_id} ({_texto_orden(orden)})")
    if orden.estado == "PENDIENTE":
        print("      PENDIENTE → EN_PRODUCCION")
        if aplicar:
            cambiar_estado_orden_produccion(db, orden_id, "EN_PRODUCCION")
    print("      EN_PRODUCCION → FINALIZADA (calcula costos; si era la última "
          "del pedido, lo pasa a TERMINADO y crea su envío)")
    if aplicar:
        orden = cambiar_estado_orden_produccion(db, orden_id, "FINALIZADA")
        if getattr(orden, "estructura_generada", None):
            print("      (se generó la estructura de costes del producto "
                  "desde el uso real de esta orden)")


def _entregar_pedido(db, pedido_id: int, aplicar: bool) -> None:
    envio = db.query(Envio).filter(Envio.pedido_id == pedido_id).first()
    if envio is None:
        print(f"  [ERROR] pedido #{pedido_id} no tiene envío (¿no llegó a TERMINADO?)")
        return
    if envio.estado == "PREPARADO":
        print(f"  → envío #{envio.id}: PREPARADO → EN_TRANSITO")
        if aplicar:
            actualizar_envio(db, envio.id, EnvioUpdate(estado="EN_TRANSITO"))
            envio = db.query(Envio).filter(Envio.id == envio.id).first()
    if envio.estado == "EN_TRANSITO":
        print(f"  → envío #{envio.id}: EN_TRANSITO → ENTREGADO (el pedido "
              f"#{pedido_id} pasa a ENTREGADO)")
        if aplicar:
            actualizar_envio(db, envio.id, EnvioUpdate(estado="ENTREGADO"))
    elif envio.estado == "ENTREGADO":
        print(f"  = envío #{envio.id} ya está ENTREGADO")


def _resumen(db) -> None:
    from app.modules.orders.model import Pedido

    db.expire_all()
    for orden_id in sorted(set(FINALIZAR_ORDENES)):
        orden = db.query(OrdenProduccion).filter(OrdenProduccion.id == orden_id).first()
        print(f"  · orden #{orden_id}: {orden.estado} — {_texto_orden(orden)}")
    for pedido_id in (166, 167, 197):
        pedido = db.query(Pedido).filter(Pedido.id == pedido_id).first()
        if pedido is None:
            continue
        cliente = pedido.cliente.nombre if pedido.cliente else "?"
        envio = db.query(Envio).filter(Envio.pedido_id == pedido_id).first()
        cola = f" · envío {envio.estado}" if envio else " · sin envío"
        print(f"  · pedido #{pedido_id} ({cliente}): {pedido.estado}{cola}")


def aplicar_plan(db, aplicar: bool = False) -> None:
    print("== 1. Completar etapas del taller ==")
    for etapa_id in COMPLETAR_ETAPAS:
        _completar_etapa(db, etapa_id, aplicar)

    print("\n== 2. Finalizar órdenes ==")
    for orden_id in FINALIZAR_ORDENES:
        _finalizar_orden(db, orden_id, aplicar)

    if ENTREGAR_PEDIDOS:
        print("\n== 3. Marcar entregas ==")
        for pedido_id in ENTREGAR_PEDIDOS:
            _entregar_pedido(db, pedido_id, aplicar)

    print("\n== Resumen ==")
    _resumen(db)

    if aplicar:
        print("\n[OK] cambios aplicados y commiteados")
    else:
        print("\n[DRY-RUN] nada escrito. Usa --aplicar para confirmar.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--aplicar", action="store_true",
                    help="Escribe en la BD (por defecto solo imprime el plan)")
    args = ap.parse_args()

    db = session_local()
    try:
        aplicar_plan(db, aplicar=args.aplicar)
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
