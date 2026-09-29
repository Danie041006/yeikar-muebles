# -*- coding: utf-8 -*-
"""Rellena la especificación (ítem) de la cotización/pedido de María Angélica
Becerra Mejía, que quedó con el renglón vacío.

NO toca la venta ni los pagos: esos ya están correctos.

Uso:
    python scripts/arreglar_detalle_maria_angelica.py            # dry-run
    python scripts/arreglar_detalle_maria_angelica.py --ejecutar # aplica
    python scripts/arreglar_detalle_maria_angelica.py --db-url postgresql://...
"""
import argparse
import os
import sys
from datetime import date
from decimal import Decimal

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__) + "/.."))

FECHA_NOTA = date(2026, 9, 2)
DESCRIPCION = "AIRE SPLIT INVERTER MARCA HIUNDAY DE 12.000 BTU 220"
PRECIO = Decimal("280")
CANTIDAD = Decimal("1")
TIPO_ITEM = "REVENTA"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ejecutar", action="store_true", help="Aplica los cambios (default: dry-run)")
    parser.add_argument("--db-url", help="URL de la BD (default: DATABASE_URL del entorno)")
    args = parser.parse_args()

    if args.db_url:
        os.environ["DATABASE_URL"] = args.db_url

    import app.modules.catalogos.model  # noqa: F401
    import app.modules.clients.model  # noqa: F401
    import app.modules.productos.model  # noqa: F401
    import app.modules.quotes.model  # noqa: F401
    import app.modules.orders.model  # noqa: F401
    import app.modules.production.model  # noqa: F401
    import app.modules.inventory.model  # noqa: F401
    import app.modules.users.model  # noqa: F401
    import app.modules.purchases.model  # noqa: F401
    import app.modules.sales.model  # noqa: F401
    import app.modules.facturacion.model  # noqa: F401
    import app.modules.gastos.model  # noqa: F401
    import app.modules.proveedores.model  # noqa: F401
    import app.modules.empleados.model  # noqa: F401
    import app.modules.envios.model  # noqa: F401
    import app.modules.tasas_cambio.model  # noqa: F401
    import app.modules.reports.model  # noqa: F401
    import app.modules.auditoria.model  # noqa: F401
    import app.modules.costos_produccion.model  # noqa: F401
    import app.modules.nomina.model  # noqa: F401
    import app.modules.adjuntos.model  # noqa: F401
    import app.modules.cuentas_por_pagar.model  # noqa: F401

    from app.db.session import session_local
    from app.modules.clients.model import Client
    from app.modules.quotes.model import Cotizacion, DetalleCotizacion
    from app.modules.orders.model import Pedido, DetallePedido

    db = session_local()
    try:
        cliente = (
            db.query(Client)
            .filter(Client.nombre.ilike("%Becerra%"))
            .first()
        )
        if not cliente:
            print("✗ No se encontró el cliente (nombre contiene 'Becerra'). Nada que hacer.")
            return

        cotizacion = (
            db.query(Cotizacion)
            .filter(Cotizacion.cliente_id == cliente.id, Cotizacion.fecha == FECHA_NOTA)
            .order_by(Cotizacion.id)
            .first()
        )
        if not cotizacion:
            print(f"✗ {cliente.nombre}: sin cotización del {FECHA_NOTA}. Nada que hacer.")
            return

        print(f"Cliente: {cliente.nombre} (id={cliente.id})")
        print(f"Cotización: id={cotizacion.id} fecha={cotizacion.fecha} total={cotizacion.total_estimado}")

        cambios = 0

        detalles_cot = db.query(DetalleCotizacion).filter(
            DetalleCotizacion.cotizacion_id == cotizacion.id
        ).all()
        if not detalles_cot:
            print(f"  + detalle_cotizacion vacío → INSERT '{DESCRIPCION}'")
            db.add(DetalleCotizacion(
                cotizacion_id=cotizacion.id,
                producto_id=None,
                tipo_item=TIPO_ITEM,
                cantidad=CANTIDAD,
                precio=PRECIO,
                observaciones=DESCRIPCION,
            ))
            cambios += 1
        else:
            print(f"  = detalle_cotizacion ya tiene {len(detalles_cot)} renglón(es) — no se toca")

        pedido = db.query(Pedido).filter(Pedido.cotizacion_id == cotizacion.id).first()
        if not pedido:
            print("  · no hay pedido asociado (se omite)")
        else:
            detalles_ped = db.query(DetallePedido).filter(
                DetallePedido.pedido_id == pedido.id
            ).all()
            if not detalles_ped:
                print(f"  + detalle_pedido vacío → INSERT '{DESCRIPCION}'")
                db.add(DetallePedido(
                    pedido_id=pedido.id,
                    producto_id=None,
                    tipo_item=TIPO_ITEM,
                    cantidad=CANTIDAD,
                    precio=PRECIO,
                    descripcion_especifica=DESCRIPCION,
                ))
                cambios += 1
            else:
                print(f"  = detalle_pedido ya tiene {len(detalles_ped)} renglón(es) — no se toca")

        if args.ejecutar:
            db.commit()
            print(f"\n✓ EJECUTADO — {cambios} renglón(es) insertado(s)")
        else:
            db.rollback()
            print(f"\nDRY-RUN (rollback) — se insertarían {cambios} renglón(es). Usa --ejecutar.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
