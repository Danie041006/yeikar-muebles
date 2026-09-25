# -*- coding: utf-8 -*-
"""Importa cuentas por pagar históricas (hojas de fiado) a la BD del ERP.

Crea Proveedor → CuentaPorPagar con renglones (qué se pidió, con fecha en la
observación de cada renglón) y los abonos como PagoCuentaPorPagar (sin mover
caja: son abonos históricos). No crea Gasto (igual que importar_cxp_carmen.py).

Uso:
    python scripts/importar_cxp_lote2.py                     # dry-run
    python scripts/importar_cxp_lote2.py --ejecutar          # commit
    python scripts/importar_cxp_lote2.py --db-url postgresql://... [--ejecutar]
    python scripts/importar_cxp_lote2.py --usuario-id 4

Idempotente: salta los códigos (tag) ya presentes en la descripción.
"""
import argparse
import os
import sys
from datetime import date
from decimal import Decimal

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__) + "/.."))

TAG = "CXP-L3"

# tipo_gasto por nombre (se resuelve contra la BD)
TIPO_AGUA = "AGUA DE BOTELLON"
TIPO_INSUMOS = "COMPRA DE INSUMOS"
TIPO_REVENTA = "COMPRA INVENTARIO REVENTA"

CUENTAS = [
    {
        "codigo": "L3-01",
        "proveedor": "AGUA BOTELLONES",
        "moneda": "COP",
        "fecha": "2026-09-01",
        "tipo_gasto": TIPO_AGUA,
        "descripcion": "Agua de botellón septiembre 2026 · 19 botellones (5+5+5+4)",
        "lineas": [
            ("5", "4000", "BOTELLONES", "01/09/2026"),
            ("5", "4000", "BOTELLONES", "05/09/2026"),
            ("5", "4000", "BOTELLONES", "09/09/2026"),
            ("4", "4000", "BOTELLONES", "14/09/2026"),
        ],
        "abonos": [],
    },
    {
        "codigo": "L3-02",
        "proveedor": "DANIEL VIDRIERO",
        "moneda": "COP",
        "fecha": "2026-08-31",
        "tipo_gasto": TIPO_INSUMOS,
        "descripcion": "Espejos nuevo pedido (entregados entre 31/08 y 19/09/2026) · abonos por nómina 3.900.000",
        "lineas": [
            ("1", "750000", "ESPEJO MODELO ROMBOS DE 80 X 1,90", "31/08/2026"),
            ("1", "850000", "ESPEJO MODELO ESTARLIN DE 80 X 1,90", "03/09/2026"),
            ("2", "800000", "ESPEJOS MODELO RAYO DE 80 X 1,80", "09/09/2026"),
            ("2", "750000", "MARCO ESPEJOS MODELO ESCARCHA DE 80 X 180", "19/09/2026"),
            ("1", "40000", "SALDO PENDIENTE DE LOS DOS VIDRIOS", "19/09/2026"),
        ],
        "abonos": [
            ("2026-09-05", "1600000", 1),
            ("2026-09-12", "800000", 1),
            ("2026-09-19", "1500000", 1),
        ],
    },
    {
        "codigo": "L3-03",
        "proveedor": "OBAVA",
        "moneda": "USD",
        "fecha": "2026-09-03",
        "tipo_gasto": TIPO_REVENTA,
        "descripcion": "Entrega con orden de entrega 302612 · factura con descuentos (lista $10.600 → $7.727,20) · incluye 2 garantías entregadas 03/09/2026",
        "lineas": [
            ("8", "169.12", "COLCHONES DALLAS CLASICO 1.40", "03/09/2026"),
            ("6", "236.92", "COLCHONES EURO PILLON DOBLE PILLON 1.40", "03/09/2026"),
            ("2", "347.00", "COLCHONES LADY BEST DE 2X2", "03/09/2026"),
            ("4", "291.60", "COLCHONES LADY BEST DE 1.60", "03/09/2026"),
            ("12", "206.30", "COLCHONES DALLAS 1 PILLON ORTOPEDICO DE 1,40", "03/09/2026"),
            ("2", "308.36", "COLCHONES DALLAS 1 PILLON ORTOPEDICO DE 2X2", "03/09/2026"),
        ],
        "abonos": [
            ("2026-09-15", "1727.20", 6),
            ("2026-09-22", "2000", 6),
        ],
    },
    {
        "codigo": "L3-04",
        "proveedor": "SR CARMEN MANILLAS",
        "moneda": "COP",
        "fecha": "2026-08-28",
        "tipo_gasto": TIPO_INSUMOS,
        "descripcion": "Saldo pendiente hoja de control (total 6.712.400 − abonos 4.500.000) · renglones por revisar contra la hoja",
        "lineas": [
            ("1", "2212400", "SALDO PENDIENTE HOJA SR CARMEN MANILLAS", ""),
        ],
        "abonos": [],
    },
    {
        "codigo": "L3-05",
        "proveedor": "ARBIN CARRILLO",
        "moneda": "COP",
        "fecha": "2026-06-15",
        "tipo_gasto": "Mano de Obra de Producción",
        "cliente_id": 5,
        "cliente_nombre": "LILIBETH VILLALOBOS",
        "descripcion": "Trabajos hechos a LILIBETH VILLALOBOS (Cúcuta): cocina, puerta corrediza y centro de TV · abonos por depósito Bancolombia 4.800.000",
        "lineas": [
            (
                "1",
                "5300000",
                "COCINA CAMBIO DE BISAGRAS PUERTAS DE VIDRIO ALUMINIO NATURAL CAMBIO DE CORREDERAS Y FRENTES DE PUERTAS POR ARMAR ELABORAR ALACENA EMPOTRAR MICROONDAS Y PANEL PARA TAPAR EL CALENTADOR DE AGUA Y APROVECHAR PARA PONER ESCOBAS Y TRAPEROS",
                "15/06/2026",
            ),
            ("1", "2100000", "PUERTA CORREDIZA ELABORADA EN MELAMINA AMBAR CON EL DISEÑO QUE YA TIENE LAS PUERTAS", "15/06/2026"),
            ("1", "2400000", "CENTRO DE TV COMO LA IMAGEN CAJON CON ESQUINAS Y CURVAS", "15/06/2026"),
        ],
        "abonos": [
            ("2026-09-15", "3000000", 4),
            ("2026-09-15", "1800000", 4),
        ],
    },
]


def obtener_usuario(db, usuario_id):
    from app.modules.users.model import Usuario

    if usuario_id:
        u = db.query(Usuario).filter(Usuario.id == usuario_id).first()
        if not u:
            raise SystemExit(f"El usuario {usuario_id} no existe.")
        return u
    return None


def migrar(args) -> int:
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
    from app.modules.proveedores.model import Proveedor
    from app.modules.catalogos.model import TipoGasto, Moneda
    from app.modules.cuentas_por_pagar.model import CuentaPorPagar, DetalleCuentaPorPagar, PagoCuentaPorPagar

    db = session_local()
    try:
        usuario = obtener_usuario(db, args.usuario_id)
        monedas = {m.codigo: m for m in db.query(Moneda).all()}
        tipos = {t.nombre: t for t in db.query(TipoGasto).all()}
        proveedores = {p.nombre.upper(): p for p in db.query(Proveedor).all()}

        print(f"BD: {db.bind.url.render_as_string(hide_password=True)}")
        print(f"Modo: {'EJECUTAR' if args.ejecutar else 'DRY-RUN (rollback)'}")
        print("-" * 110)

        creadas = saltadas = 0
        for c in CUENTAS:
            moneda = monedas.get(c["moneda"])
            if not moneda:
                print(f"  ✗ {c['codigo']} {c['proveedor']}: moneda {c['moneda']} no existe.")
                continue
            tipo = tipos.get(c["tipo_gasto"])
            if not tipo:
                print(f"  ✗ {c['codigo']} {c['proveedor']}: tipo de gasto '{c['tipo_gasto']}' no existe.")
                continue

            ya = db.query(CuentaPorPagar).filter(
                CuentaPorPagar.descripcion.like(f"%{TAG}-{c['codigo'].split('-')[-1]}%")
            ).first()
            if ya:
                saltadas += 1
                print(f"  · SKIP  {c['codigo']}  {c['proveedor']:<22} ya migrada (cxp #{ya.id})")
                continue

            monto = sum((Decimal(cant) * Decimal(precio) for cant, precio, _, _ in c["lineas"]), Decimal("0")).quantize(Decimal("0.01"))
            abonado = sum((Decimal(m) for _, m, _ in c["abonos"]), Decimal("0")).quantize(Decimal("0.01"))
            saldo = (monto - abonado).quantize(Decimal("0.01"))

            prov = proveedores.get(c["proveedor"].upper())
            if not prov:
                prov = Proveedor(nombre=c["proveedor"])
                db.add(prov)
                db.flush()
                proveedores[c["proveedor"].upper()] = prov
                accion_prov = "proveedor NUEVO"
            else:
                accion_prov = "proveedor existente"

            cxp = CuentaPorPagar(
                proveedor_id=prov.id,
                tipo_gasto_id=tipo.id,
                moneda_id=moneda.id,
                fecha=date.fromisoformat(c["fecha"]),
                descripcion=f"{TAG}-{c['codigo'].split('-')[-1]} · {c['descripcion']}",
                monto=monto,
                tasa_cambio=Decimal("1.0"),
                monto_en_moneda_base=monto,
                monto_pagado=abonado,
                estado="PAGADA" if saldo <= Decimal("0.005") else "PENDIENTE",
                origen_tipo="MANUAL",
                creado_por_id=usuario.id if usuario else None,
            )
            db.add(cxp)
            db.flush()

            for i, (cant, precio, desc, fecha_linea) in enumerate(c["lineas"]):
                db.add(DetalleCuentaPorPagar(
                    cuenta_por_pagar_id=cxp.id,
                    orden=i,
                    descripcion=desc,
                    cantidad=Decimal(cant),
                    precio_unitario=Decimal(precio),
                    cliente_id=c.get("cliente_id"),
                    cliente_nombre=c.get("cliente_nombre"),
                    observaciones=fecha_linea or None,
                ))

            for fecha_abono, monto_abono, caja_id in c["abonos"]:
                db.add(PagoCuentaPorPagar(
                    cuenta_por_pagar_id=cxp.id,
                    fecha=date.fromisoformat(fecha_abono),
                    metodo_caja_id=caja_id,
                    monto=Decimal(monto_abono),
                    tasa_cambio=Decimal("1.0"),
                    monto_en_moneda_base=Decimal(monto_abono),
                    creado_por_id=usuario.id if usuario else None,
                ))

            creadas += 1
            print(
                f"  · {'CREAR' if args.ejecutar else 'DRY  '} {c['codigo']}  {c['proveedor']:<22} "
                f"total={monto:>12,.2f} {c['moneda']}  abonos={abonado:>11,.2f}  saldo={saldo:>12,.2f}  "
                f"renglones={len(c['lineas'])}  tipo={tipo.nombre}  {accion_prov}"
            )

        print("-" * 110)
        print(f"Cuentas nuevas: {creadas}  ·  Ya migradas (skip): {saltadas}")

        if args.ejecutar:
            db.commit()
            print("\n✓ Importación COMMITADA en Por Pagar.")
            print("  Rollback de emergencia:")
            print(f"    DELETE FROM pago_cuenta_por_pagar WHERE cuenta_por_pagar_id IN (SELECT id FROM cuenta_por_pagar WHERE descripcion LIKE '%{TAG}-%');")
            print(f"    DELETE FROM detalle_cuenta_por_pagar WHERE cuenta_por_pagar_id IN (SELECT id FROM cuenta_por_pagar WHERE descripcion LIKE '%{TAG}-%');")
            print(f"    DELETE FROM cuenta_por_pagar WHERE descripcion LIKE '%{TAG}-%';")
        else:
            db.rollback()
            print("\n· Dry-run completo. No se escribió nada en la BD.")
        return 0
    finally:
        db.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Importa cuentas por pagar históricas (lote 3).")
    parser.add_argument("--ejecutar", action="store_true", help="Commitea los cambios (default: dry-run)")
    parser.add_argument("--usuario-id", type=int, default=None, help="Usuario responsable")
    parser.add_argument("--db-url", type=str, default=None, help="DATABASE_URL alternativa (ej. producción Neon)")
    args = parser.parse_args()
    sys.exit(migrar(args))


if __name__ == "__main__":
    main()
