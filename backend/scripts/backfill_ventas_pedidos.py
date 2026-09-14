# -*- coding: utf-8 -*-
"""Backfill: crea la Venta (cuenta por cobrar) a pedidos confirmados que no la tengan.

Los pedidos convertidos con la conversión actual ya nacen con su venta automática;
este script cierra la brecha de pedidos históricos anteriores a ese comportamiento.
Sin venta no hay cuenta por cobrar: el cliente debe y el ERP no lo ve.

Uso:
    python scripts/backfill_ventas_pedidos.py             # dry-run
    python scripts/backfill_ventas_pedidos.py --ejecutar  # commit real
    python scripts/backfill_ventas_pedidos.py --db-url postgresql://...

Notas:
- No toca inventario: los pedidos que arregla son históricos y su stock real ya
  se movió físicamente; descontarlo hoy distorsionaría el kardex.
- La moneda y la tasa salen de la cotización del pedido (misma regla del flujo normal).
- Idempotente por diseño: solo crea venta donde falta; con advisory lock para
  ejecuciones concurrentes.
"""
import argparse
import os
import sys
from decimal import Decimal

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__) + "/.."))

ESTADOS_FACTURABLES = ("APROBADO", "PRODUCCION", "TERMINADO", "ENTREGADO")


def backfill(args) -> int:
    if args.db_url:
        os.environ["DATABASE_URL"] = args.db_url

    # Registro completo de mappers (mismo listado que alembic/env.py).
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

    from sqlalchemy import text

    from app.db.session import session_local
    from app.modules.orders.model import Pedido
    from app.modules.sales.model import Venta, DetalleVenta
    from app.modules.users.model import Usuario
    from app.modules.catalogos.model import Rol
    from app.modules.auditoria.service import record_event

    db = session_local()
    try:
        db.execute(text("SELECT pg_advisory_xact_lock(hashtext('backfill-ventas-pedidos'))"))

        usuario = (
            db.query(Usuario).join(Usuario.roles).filter(Rol.nombre == "Dueño").order_by(Usuario.id).first()
        )
        if not usuario:
            print("✗ No hay usuario Dueño en la BD. Crea uno o ajusta el script.")
            return 1

        pedidos_sin_venta = (
            db.query(Pedido)
            .outerjoin(Venta, Venta.pedido_id == Pedido.id)
            .filter(
                Pedido.estado.in_(ESTADOS_FACTURABLES),
                Venta.id.is_(None),
            )
            .order_by(Pedido.id)
            .all()
        )

        print(f"BD: {db.bind.url.render_as_string(hide_password=True)}")
        print(f"Usuario responsable: {usuario.nombre_usuario} (id={usuario.id})")
        print(f"Pedidos confirmados sin venta: {len(pedidos_sin_venta)}  ·  Modo: {'EJECUTAR' if args.ejecutar else 'DRY-RUN'}")
        print("-" * 100)

        creadas = 0
        for pedido in pedidos_sin_venta:
            cotizacion = pedido.cotizacion
            moneda = cotizacion.moneda if cotizacion else None
            if not moneda:
                print(f"  ✗ SKIP pedido #{pedido.id}: su cotización no define moneda. Revisar manualmente.")
                continue

            # Mismo cálculo que la facturación normal: cantidad × precio por línea.
            total = sum(Decimal(str(d.cantidad)) * Decimal(str(d.precio)) for d in pedido.detalles)
            if total <= 0:
                print(f"  ✗ SKIP pedido #{pedido.id}: total calculado {total}. Revisar manualmente.")
                continue

            # Tasa congelada de la cotización si coincide la moneda; si no, la del sistema.
            tasa = Decimal("1.0")
            if moneda.codigo != "COP":
                if cotizacion.moneda_id == moneda.id and cotizacion.tasa_cambio:
                    tasa = Decimal(str(cotizacion.tasa_cambio))
                else:
                    print(f"  ✗ SKIP pedido #{pedido.id}: moneda {moneda.codigo} sin tasa clara. Revisar manualmente.")
                    continue
            total_base = (total * tasa).quantize(Decimal("0.01"))

            venta = Venta(
                pedido_id=pedido.id,
                cliente_id=pedido.cliente_id,
                moneda_id=moneda.id,
                fecha=pedido.fecha,
                total=total,
                estado="PENDIENTE",
                tasa_cambio=tasa,
                total_en_moneda_base=total_base,
                observaciones="BACKFILL-VENTA-PEDIDO",
                creado_por_id=usuario.id,
                actualizado_por_id=usuario.id,
            )
            db.add(venta)
            db.flush()
            for detalle in pedido.detalles:
                db.add(DetalleVenta(
                    venta_id=venta.id,
                    producto_id=detalle.producto_id,
                    material_id=detalle.material_id,
                    tipo_item=detalle.tipo_item or "FABRICADO",
                    cantidad=detalle.cantidad,
                    precio=detalle.precio,
                    costo_unitario=detalle.costo_unitario,
                    porcentaje_ganancia=detalle.porcentaje_ganancia,
                    descuento=Decimal("0"),
                ))
            record_event(
                db,
                actor=usuario,
                action="CREATE",
                entity_type="venta",
                entity_id=venta.id,
                after={"origen": "BACKFILL-VENTA-PEDIDO", "pedido_id": pedido.id, "total": float(total)},
            )

            creadas += 1
            print(
                f"  · {'CREAR' if args.ejecutar else 'DRY  '} pedido #{pedido.id:<5} {pedido.cliente.nombre:<35} "
                f"{total:>14,.2f} {moneda.codigo}  estado={pedido.estado:<11} venta=#{venta.id}"
            )

        print("-" * 100)
        if args.ejecutar:
            db.commit()
            print(f"✓ {creadas} ventas creadas. Los pedidos ya son cobrables en 'Ventas y cobros'.")
        else:
            db.rollback()
            print(f"· Dry-run: {creadas} ventas por crear. Ejecuta con --ejecutar para confirmar.")
        return 0
    finally:
        db.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Crea la venta faltante a pedidos confirmados.")
    parser.add_argument("--ejecutar", action="store_true", help="Commitea los cambios (default: dry-run)")
    parser.add_argument("--db-url", type=str, default=None, help="DATABASE_URL alternativa (ej. producción Neon)")
    args = parser.parse_args()
    sys.exit(backfill(args))


if __name__ == "__main__":
    main()
