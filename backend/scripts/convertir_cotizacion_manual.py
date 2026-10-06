"""Convierte una cotización en pedido usando el servicio real (no SQL crudo).

Reproduce lo que hace POST /pedido/convertir/{id}: mismos servicios, mismas
validaciones (precios que deben calzar con la cotización, idempotencia, etc.),
misma auditoría. Por eso no puede dejar el pedido a medias: o entra todo
(pedido + detalles + órdenes + venta) o nada.

Dry-run por defecto.
"""

import argparse

import app.main  # noqa: F401  registra los mappers
from app.db.session import session_local
from app.modules.orders.service import convertir_cotizacion_a_pedido
from app.modules.orders.schemas import DetallePedidoCreate


def construir_detalles(db, cotizacion_id):
    from app.modules.quotes.model import DetalleCotizacion

    detalles = db.query(DetalleCotizacion).filter(
        DetalleCotizacion.cotizacion_id == cotizacion_id
    ).all()
    salida = []
    for dc in detalles:
        salida.append(DetallePedidoCreate(
            producto_id=dc.producto_id,
            material_id=dc.material_id,
            tipo_item=dc.tipo_item or "FABRICADO",
            cantidad=float(dc.cantidad),
            precio=float(dc.precio),
            ancho=float(dc.ancho) if dc.ancho else None,
            largo=float(dc.largo) if dc.largo else None,
            alto=float(dc.alto) if dc.alto else None,
            descripcion_especifica=dc.observaciones,
            observaciones=dc.observaciones,
        ))
    return salida


def main(aplicar=False):
    from app.modules.orders import model as pedido_model
    from app.modules.quotes.model import Cotizacion
    from app.modules.users.model import Usuario

    db = session_local()
    try:
        # Dueño/Admin: alcance total (la conversión exige autoría o alcance total).
        usuario = db.query(Usuario).join(
            Usuario.roles
        ).first()

        cot = db.query(Cotizacion).filter(Cotizacion.id == 50).first()
        if not cot:
            raise SystemExit("cotización 50 no encontrada")
        ya = db.query(pedido_model.Pedido).filter(
            pedido_model.Pedido.cotizacion_id == 50
        ).first()
        if ya:
            raise SystemExit(f"la cotización 50 ya tiene el pedido #{ya.id}")

        detalles = construir_detalles(db, 50)
        print(f"Cotización 50 · estado={cot.estado} · total={cot.total_estimado} "
              f"· moneda_id={cot.moneda_id} · trm={cot.tasa_cambio}")
        for d in detalles:
            print(f"  - producto={d.producto_id} {d.cantidad:g} x {d.precio:,.2f} "
                  f"| {d.descripcion_especifica}")

        if not aplicar:
            print("\n[DRY-RUN] nada escrito. Usa --aplicar.")
            return

        pedido = convertir_cotizacion_a_pedido(
            db, 50, None, detalles, usuario=usuario,
        )
        print(f"\n[OK] pedido #{pedido.id} creado en estado {pedido.estado}")
    finally:
        db.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--aplicar", action="store_true")
    main(aplicar=ap.parse_args().aplicar)