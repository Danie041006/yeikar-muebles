# -*- coding: utf-8 -*-
"""Renombra el cliente placeholder "MDF MES SEPTIEMBRE" → "MDF (Cupertino)".

La nota de Cupertino del 18/09/2026 ($5.400.000 COP) se importó antes como
cuenta por cobrar bajo un cliente sin nombre ("MDF MES SEPTIEMBRE"). Se
etiqueta para que quede claro a quién corresponde. Idempotente.

Uso:
    python scripts/renombrar_cliente_mdf_cupertino.py            # dry-run
    python scripts/renombrar_cliente_mdf_cupertino.py --ejecutar
    python scripts/renombrar_cliente_mdf_cupertino.py --db-url postgresql://...
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__) + "/.."))

VIEJO = "MDF MES SEPTIEMBRE"
NUEVO = "MDF (Cupertino)"


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

    db = session_local()
    try:
        clientes = db.query(Client).filter(Client.nombre.ilike(f"%{VIEJO}%")).all()
        if not clientes:
            print(f"= No existe ningún cliente que contenga '{VIEJO}'. Nada que hacer.")
            return
        for c in clientes:
            print(f"Cliente: {c.nombre} (id={c.id}) → {NUEVO}")
            c.nombre = NUEVO
        if args.ejecutar:
            db.commit()
            print(f"\n✓ EJECUTADO — {len(clientes)} cliente(s) renombrado(s)")
        else:
            db.rollback()
            print(f"\nDRY-RUN (rollback) — se renombrarían {len(clientes)} cliente(s). Usa --ejecutar.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
