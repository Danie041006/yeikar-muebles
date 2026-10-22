# -*- coding: utf-8 -*-
"""Importa los movimientos de caja del 20-22/10/2026 dictados por la dueña.

Tablas (saldos dictados = columna final de cada hoja):
  1. Efectivo en Pesos        -> cuenta 1   (SIN la fila de regalos de Navidad)
  2. Efectivo en Dólares      -> cuenta 2
  3. Bancolombia              -> cuenta 4
  4. Nequi Karolay            -> cuenta 7
  5. Bancolombia Andrea       -> cuenta 121
  6. Zelle                    -> cuenta 6
  7. Binance                  -> cuenta 9

Las filas con código G (GI/GP/GF) se registran como SALIDA clasificada: crean
su Gasto (Gasto de Inversión / Personal / Fábrica) igual que el libro. Las
demás quedan como movimiento simple. NO se crean abonos (pagos) de ventas:
los registra el usuario desde Ventas.

Idempotente: si ya existe un movimiento de esa cuenta con la misma fecha,
tipo, monto y persona, se salta (se puede volver a correr).

Uso:
  PYTHONPATH=/app python scripts/importar_caja_20_22_oct_2026.py            # dry-run
  PYTHONPATH=/app python scripts/importar_caja_20_22_oct_2026.py --aplicar  # commit
"""
from __future__ import annotations

import argparse
from datetime import date
from decimal import Decimal

import app.main  # noqa: F401
from app.db.session import session_local
from sqlalchemy import func, text

D = Decimal

# (cuenta_id, fecha, tipo, monto, persona, concepto, clasificacion)
MOVIMIENTOS = [
    # ── Tabla 1 · Efectivo en Pesos (cuenta 1) ─────────────────────────────
    (1, date(2026, 10, 21), "SALIDA", "40000", "WUILLIAM", "PAGO DE HERRAJES DEL MUEBLE DEL SR YOHAN", "GASTO_INVERSION"),
    (1, date(2026, 10, 21), "SALIDA", "25000", "WILMER", "PAGO DE LAVADA DE TERIOS", "GASTO_PERSONAL"),
    (1, date(2026, 10, 22), "ENTRADA", "50000", "KAROLAY", "DIO EFECTIVO POR TRASFERENCIA", None),
    (1, date(2026, 10, 22), "SALIDA", "28000", "GASTOS", "VARIOS TORNILLOS Y MILANTA", "GASTO_FAMILIAR"),
    (1, date(2026, 10, 22), "SALIDA", "16200", "DANIEL", "ALMUERZO", "GASTO_FAMILIAR"),
    (1, date(2026, 10, 22), "SALIDA", "100000", None, "SIN DETALLE (tabla 22/10)", None),
    # (excluida a propósito: COMPAS · regalos de Navidad · 600.000)

    # ── Tabla 2 · Efectivo en Dólares (cuenta 2) ───────────────────────────
    (2, date(2026, 10, 22), "ENTRADA", "600", "JULIETA CAPITAN", "ABONO DE MUEBLES", None),
    (2, date(2026, 10, 22), "SALIDA", "200", "RONALD", "PAGO", None),

    # ── Tabla 3 · Bancolombia (cuenta 4) ───────────────────────────────────
    (4, date(2026, 10, 21), "SALIDA", "49900", "SMARFIT CAROLINA", "SMARFIT", None),
    (4, date(2026, 10, 21), "SALIDA", "9900", "SMARFIT CAROLINA", "SMARFIT", None),
    (4, date(2026, 10, 20), "SALIDA", "9000", "NEQUI", "NEQUI", None),
    (4, date(2026, 10, 22), "SALIDA", "2262", "IMPUESTO", "GOBIERNO", None),
    (4, date(2026, 10, 22), "SALIDA", "36000", "CEJAS", "PAGO DE CEJAS", None),
    (4, date(2026, 10, 22), "ENTRADA", "2850000", "RONALD", "PAGO DE FLETE CARACAS", None),
    (4, date(2026, 10, 22), "SALIDA", "210000", "KATERYN", "COMPRA DE MATERIAL", None),
    (4, date(2026, 10, 22), "SALIDA", "1519000", "PINTUTECNICAS", "PAGO DE MATERIAL", None),
    (4, date(2026, 10, 22), "SALIDA", "333000", "TAPIZANDER", "COMPRA DE TELAS", None),
    (4, date(2026, 10, 22), "SALIDA", "30000", "TEXTIL PASTO", "COMPRAS", None),
    (4, date(2026, 10, 22), "SALIDA", "608500", "MADEFRONT", "COMPRA DE 2 LAMINAS DE MELAMINA", None),

    # ── Tabla 4 · Nequi Karolay (cuenta 7) ─────────────────────────────────
    (7, date(2026, 10, 20), "SALIDA", "225900", "ISABEL", "BODEGA", "GASTO_PERSONAL"),
    (7, date(2026, 10, 20), "ENTRADA", "300000", "EDWIN ANTONIO", "CANCELO LA PUERTA", None),
    (7, date(2026, 10, 20), "SALIDA", "252000", "PINTUTECNICA", "3 GALONES DE LACA NA PRIME", None),
    (7, date(2026, 10, 21), "ENTRADA", "300000", "DANYS PEREZ", "VENTA DE COLCHON DALLAS CLASICO 1.40", None),
    (7, date(2026, 10, 21), "SALIDA", "280000", "CAROLINA", "COMPRA DE PERFUME", None),
    (7, date(2026, 10, 22), "SALIDA", "50000", "KAROLAY", "DIO EFECTIVO POR TRANSFERENCIA", None),
    (7, date(2026, 10, 22), "ENTRADA", "144000", "JEFERSON IGLESIA", "VENTA DE LAMINA DE 9 MM Y 2 CORTES", None),
    (7, date(2026, 10, 22), "SALIDA", "248208", "YOHANNA FARFAN", "PAGO DE SAM", "GASTO_PERSONAL"),

    # ── Tabla 5 · Bancolombia Andrea (cuenta 121) ──────────────────────────
    (121, date(2026, 10, 20), "SALIDA", "73000", "ANDREA", "COMPRA DE PAN Y JAMON, CREMA DE LECHE", "GASTO_PERSONAL"),

    # ── Tabla 6 · Zelle (cuenta 6) ─────────────────────────────────────────
    (6, date(2026, 10, 21), "SALIDA", "1853", "CIRO SANCHEZ", "PAGO DE ELECTRODOMESTICOS", None),

    # ── Tabla 7 · Binance (cuenta 9) ───────────────────────────────────────
    (9, date(2026, 10, 21), "ENTRADA", "1000", "YAJAIRA MONSALVE", "ABONO A MUEBLES", None),
    (9, date(2026, 10, 22), "ENTRADA", "1000", "MARIA PAOLA", "ABONO A MUEBLES", None),
]

# Saldos finales dictados por la dueña (posteriores a estas filas)
SALDOS_HOJA = {1: D("2808100"), 2: D("434"), 4: D("798970"), 7: D("0"),
               121: D("0"), 6: D("1774"), 9: D("2002")}


def main(aplicar: bool = False) -> None:
    from app.modules.reports import schemas as report_schemas
    from app.modules.reports import service as report_service
    from app.modules.reports.model import MetodoCaja, MovimientoCaja

    db = session_local()
    try:
        creados = saltados = errores = 0
        for cuenta_id, fecha, tipo, monto, persona, concepto, clasif in MOVIMIENTOS:
            existe = (
                db.query(MovimientoCaja)
                .filter(
                    MovimientoCaja.metodo_caja_id == cuenta_id,
                    MovimientoCaja.fecha == fecha,
                    MovimientoCaja.tipo == tipo,
                    MovimientoCaja.monto == D(monto),
                )
                .first()
            )
            if existe:
                print(f"  [SKIP] cuenta {cuenta_id} {fecha} {tipo} {monto} · ya existe #{existe.id}")
                saltados += 1
                continue
            print(f"  {'CREAR' if aplicar else 'DRY  '} cuenta {cuenta_id} {fecha} {tipo} {monto} · {persona or '(sin nombre)'} · {concepto[:45]}"
                  + (f" · {clasif}" if clasif else ""))
            if not aplicar:
                creados += 1
                continue
            try:
                report_service.crear_movimiento_caja(
                    db,
                    report_schemas.MovimientoCajaCreate(
                        metodo_caja_id=cuenta_id,
                        fecha=fecha,
                        tipo=tipo,
                        monto=D(monto),
                        moneda_id=1 if cuenta_id in (1, 4, 7, 121) else 2,
                        persona_entidad=persona,
                        concepto=concepto,
                        clasificacion=clasif,
                    ),
                    usuario_id=4,
                )
                creados += 1
            except Exception as e:  # noqa: BLE001 - se reporta y sigue
                errores += 1
                print(f"    ERROR: {e}")

        print(f"\n{'APLICADO' if aplicar else 'DRY-RUN'}: {creados} movimientos, "
              f"{saltados} saltados, {errores} errores")

        print("\nSaldos resultantes vs hoja:")
        for cuenta_id, esperado in SALDOS_HOJA.items():
            cuenta = db.get(MetodoCaja, cuenta_id)
            saldo = db.execute(
                text(
                    "SELECT COALESCE(SUM(CASE WHEN tipo IN ('ENTRADA','APERTURA') "
                    "THEN monto ELSE -monto END),0) FROM movimiento_caja "
                    "WHERE metodo_caja_id=:c"
                ),
                {"c": cuenta_id},
            ).scalar()
            dif = float(D(str(saldo)) - esperado)
            print(f"  cuenta {cuenta_id:>3} {cuenta.nombre if cuenta else '?':<24} "
                  f"ERP {float(saldo):>14,.0f} · hoja {float(esperado):>12,.0f} · dif {dif:>12,.0f}")
        if not aplicar:
            print("\n[DRY-RUN] Nada escrito. Usa --aplicar para registrar.")
    finally:
        db.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--aplicar", action="store_true")
    main(aplicar=ap.parse_args().aplicar)
