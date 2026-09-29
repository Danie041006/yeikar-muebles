# -*- coding: utf-8 -*-
"""Corrige la nota de Arbin Carrillo del 21/09/2026 (cot #86 / venta CxC-L2-L2-11).

La importación histórica dejó solo el SALDO: venta de $358 con 1 colchón y sin
pago. La nota real es: 2 colchones Dallas 1 Pillón 1,60 @ $358 = $716, abono
$358 (Bancolombia 21/09, ref 1.163.000/3.250) y saldo $358.

Deja la venta completa ($716) + el abono, de modo que el saldo por cobrar
sigue siendo $358. NO toca otras ventas del cliente.

Uso:
    python scripts/arreglar_arbin_2109.py            # dry-run
    python scripts/arreglar_arbin_2109.py --ejecutar
    python scripts/arreglar_arbin_2109.py --db-url postgresql://...
"""
import argparse
import os
import sys
from datetime import date, datetime
from decimal import Decimal

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__) + "/.."))

CLIENTE = "Arbin Carrillo"
FECHA = date(2026, 9, 21)
DESCRIPCION = "COLCHON DALLAS 1 PILLON DE 1,60"
CANTIDAD = Decimal("2")
PRECIO = Decimal("358")
TOTAL = Decimal("716")
ABONO = Decimal("358")
REFERENCIA = "1.163.000/3.250"
MARCA = "AJUSTE-ARBIN-2109"


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
    from app.modules.sales.model import Venta, DetalleVenta, Pago

    db = session_local()
    try:
        cliente = db.query(Client).filter(Client.nombre.ilike(CLIENTE)).first()
        if not cliente:
            print(f"✗ No se encontró el cliente '{CLIENTE}'.")
            return

        cot = (
            db.query(Cotizacion)
            .filter(Cotizacion.cliente_id == cliente.id, Cotizacion.fecha == FECHA)
            .order_by(Cotizacion.id)
            .first()
        )
        if not cot:
            print(f"✗ {CLIENTE}: sin cotización del {FECHA}.")
            return

        pedido = db.query(Pedido).filter(Pedido.cotizacion_id == cot.id).first()
        venta = (
            db.query(Venta)
            .filter(Venta.cliente_id == cliente.id, Venta.fecha == FECHA)
            .order_by(Venta.id)
            .first()
        )
        print(f"Cliente: {cliente.nombre} (id={cliente.id})")
        print(f"Cotización #{cot.id} · total {cot.total_estimado}")
        print(f"Pedido     #{pedido.id if pedido else '-'}")
        print(f"Venta      #{venta.id if venta else '-'} · total {venta.total if venta else '-'} · {venta.estado if venta else '-'}")

        if venta is None:
            print("✗ No hay venta para esta nota; nada que corregir.")
            return

        ya = db.query(Pago).filter(
            Pago.venta_id == venta.id, Pago.observaciones.contains(MARCA)
        ).first()
        if ya:
            print(f"= Ya corregida antes (pago #{ya.id}, '{MARCA}'). Nada que hacer.")
            return

        # ── 1. Detalle de cotización: 2 colchones ──
        det_cot = db.query(DetalleCotizacion).filter(
            DetalleCotizacion.cotizacion_id == cot.id
        ).all()
        objetivo = None
        for d in det_cot:
            if d.producto_id is None and (d.observaciones or "").upper().startswith("COLCHON"):
                objetivo = d
                break
        if objetivo is None and len(det_cot) == 1:
            objetivo = det_cot[0]
        if objetivo is not None:
            print(f"  + detalle_cotizacion #{objetivo.id}: cantidad {objetivo.cantidad} → {CANTIDAD}")
            objetivo.cantidad = CANTIDAD
            objetivo.precio = PRECIO
            objetivo.observaciones = f"2x {DESCRIPCION} (ENTREGADO 21/09/2026)"
        cot.total_estimado = TOTAL
        print(f"  + cotizacion #{cot.id}: total → {TOTAL}")

        # ── 2. Detalle de pedido (crear si falta) ──
        if pedido is not None:
            det_ped = db.query(DetallePedido).filter(DetallePedido.pedido_id == pedido.id).all()
            if not det_ped:
                db.add(DetallePedido(
                    pedido_id=pedido.id, producto_id=None, tipo_item="REVENTA",
                    cantidad=CANTIDAD, precio=PRECIO, descripcion_especifica=DESCRIPCION,
                ))
                print(f"  + detalle_pedido (pedido #{pedido.id}): 2x {DESCRIPCION}")

        # ── 3. Detalle de venta (crear si falta) ──
        det_ven = db.query(DetalleVenta).filter(DetalleVenta.venta_id == venta.id).all()
        if not det_ven:
            db.add(DetalleVenta(
                venta_id=venta.id, producto_id=None, tipo_item="REVENTA",
                cantidad=CANTIDAD, precio=PRECIO, descripcion_especifica=DESCRIPCION,
            ))
            print(f"  + detalle_venta (venta #{venta.id}): 2x {DESCRIPCION}")

        # ── 4. Venta: total $716 y estado ABONADA ──
        print(f"  + venta #{venta.id}: total {venta.total} → {TOTAL}, estado {venta.estado} → ABONADA")
        venta.total = TOTAL
        venta.estado = "ABONADA"
        venta.observaciones = (
            (venta.observaciones or "") +
            " | Corrección: venta completa 2 colchones $716, abono $358 (saldo $358)"
        ).strip(" |")

        # ── 5. Pago del abono ──
        db.add(Pago(
            venta_id=venta.id,
            moneda_id=venta.moneda_id,
            fecha=datetime(2026, 9, 21, 12, 0, 0),
            monto=ABONO,
            tasa_cambio=Decimal("1"),
            monto_en_moneda_base=ABONO,
            metodo_pago="BANCOLOMBIA",
            referencia=REFERENCIA,
            observaciones=f"{MARCA} · abono Bancolombia {REFERENCIA}",
        ))
        print(f"  + pago {ABONO} BANCOLOMBIA ({REFERENCIA})")

        if args.ejecutar:
            db.commit()
            print("\n✓ EJECUTADO — venta #{} corregida (saldo ${})".format(venta.id, TOTAL - ABONO))
        else:
            db.rollback()
            print("\nDRY-RUN (rollback) — usa --ejecutar para aplicar.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
