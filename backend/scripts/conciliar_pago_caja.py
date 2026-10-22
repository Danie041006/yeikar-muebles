# -*- coding: utf-8 -*-
"""Concilia un abono REAL (ya visible en el libro de caja) con una venta.

Crea el Pago de la venta y lo enlaza al movimiento_caja ENTRADA que ya existe
(importado del libro), SIN crear otro movimiento de caja. Esto evita duplicar
el dinero: la caja ya lo tiene, lo único que faltaba era el abono en la venta.

Casos típicos: libros de caja importados con `libro_caja` (referencia
'[Libro ... 2026-10]') cuyos cobros nunca se registraron como Pago.

Uso (dentro del contenedor backend, con el venv/código de la app):

    python scripts/conciliar_pago_caja.py \
        --venta 159 --monto 980 --moneda 2 --metodo EFECTIVO_USD \
        --fecha 2026-10-02 --movimiento 474 \
        --obs "2 poltronas (libro EFECTIVO_USD)" --aplicar

Sin `--aplicar` hace DRY-RUN: imprime lo que haría y revierte todo.

Validaciones (abortan sin escribir):
  - la venta existe y no está CANCELADA/PAGADA
  - el método de pago es una cuenta activa y su moneda coincide
  - el monto en moneda de la venta no excede el saldo pendiente
  - el movimiento de caja existe, es ENTRADA, está libre (pago_id NULL),
    es de la misma cuenta/moneda/fecha y por el mismo monto
"""
from __future__ import annotations

import argparse
from datetime import date, datetime

import app.main  # noqa: F401  (registra todos los modelos en el mapper)
from app.db.session import session_local
from app.modules.auditoria.service import record_event
from app.modules.reports.model import MetodoCaja, MovimientoCaja
from app.modules.sales.model import Pago, Venta
from app.modules.sales.service import (
    _convertir_a_moneda_venta,
    _normalizar_fecha_pago,
    _recalcular_estado_venta,
    _saldo_pendiente,
)
from app.modules.users.model import Usuario


def _fecha(valor: str) -> date:
    return datetime.strptime(valor, "%Y-%m-%d").date()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--venta", type=int, required=True)
    ap.add_argument("--monto", type=float, required=True, help="Monto en la moneda del pago")
    ap.add_argument("--moneda", type=int, required=True, help="id de moneda (1=COP, 2=USD, ...)")
    ap.add_argument("--metodo", required=True, help="codigo de metodo_caja (EFECTIVO_USD, NEQUI...)")
    ap.add_argument("--fecha", type=_fecha, required=True, help="YYYY-MM-DD del cobro real")
    ap.add_argument("--movimiento", type=int, required=True, help="id de movimiento_caja ENTRADA")
    ap.add_argument("--tasa", type=float, default=None, help="tasa del pago cuando la moneda difiere de la venta")
    ap.add_argument("--obs", default=None, help="observaciones del pago")
    ap.add_argument("--usuario", type=int, default=4, help="usuario que queda en auditoria")
    ap.add_argument("--aplicar", action="store_true", help="confirma los cambios (sin esto es dry-run)")
    args = ap.parse_args()

    db = session_local()
    try:
        venta = (
            db.query(Venta)
            .filter(Venta.id == args.venta)
            .with_for_update()
            .first()
        )
        if venta is None:
            raise ValueError(f"La venta {args.venta} no existe.")
        if venta.estado in ("CANCELADA", "PAGADA"):
            raise ValueError(f"La venta {venta.id} está {venta.estado}; no admite un abono nuevo.")

        cuenta = (
            db.query(MetodoCaja)
            .filter(MetodoCaja.codigo == args.metodo)
            .first()
        )
        if cuenta is None or not cuenta.activo:
            raise ValueError(f"El método '{args.metodo}' no es una cuenta activa del catálogo.")
        if cuenta.moneda_id is not None and cuenta.moneda_id != args.moneda:
            raise ValueError(
                f"La cuenta {cuenta.nombre} es de moneda {cuenta.moneda_id}, "
                f"pero el pago viene en moneda {args.moneda}."
            )

        tasa, monto_base, margen = _convertir_a_moneda_venta(
            db, args.moneda, args.monto, args.tasa, venta
        )
        saldo = _saldo_pendiente(db, venta)
        if monto_base > saldo + margen:
            raise ValueError(
                f"El abono ({monto_base:,.2f} en moneda de la venta) excede el "
                f"saldo pendiente ({saldo:,.2f})."
            )

        mov = (
            db.query(MovimientoCaja)
            .filter(MovimientoCaja.id == args.movimiento)
            .with_for_update()
            .first()
        )
        if mov is None:
            raise ValueError(f"El movimiento {args.movimiento} no existe.")
        if mov.tipo != "ENTRADA":
            raise ValueError(f"El movimiento {mov.id} es {mov.tipo}; debe ser ENTRADA.")
        if mov.pago_id is not None:
            raise ValueError(f"El movimiento {mov.id} ya está ligado al pago #{mov.pago_id}.")
        if mov.metodo_caja_id != cuenta.id:
            raise ValueError(
                f"El movimiento {mov.id} es de la cuenta {mov.metodo_caja_id}, "
                f"no de {cuenta.nombre} ({cuenta.id})."
            )
        if int(mov.moneda_id or 0) != args.moneda:
            raise ValueError(f"El movimiento {mov.id} está en moneda {mov.moneda_id}, no {args.moneda}.")
        if abs(float(mov.monto) - args.monto) > 0.01:
            raise ValueError(f"El movimiento {mov.id} es de {mov.monto}, no de {args.monto}.")
        if mov.fecha != args.fecha:
            raise ValueError(f"El movimiento {mov.id} es del {mov.fecha}, no del {args.fecha}.")

        usuario = db.get(Usuario, args.usuario) if args.usuario else None

        pago = Pago(
            venta_id=venta.id,
            moneda_id=args.moneda,
            fecha=_normalizar_fecha_pago(datetime.combine(args.fecha, datetime.min.time())),
            monto=args.monto,
            tasa_cambio=tasa,
            monto_en_moneda_base=monto_base,
            metodo_pago=cuenta.codigo,
            observaciones=args.obs,
            creado_por_id=usuario.id if usuario else None,
        )
        db.add(pago)
        db.flush()
        mov.pago_id = pago.id
        _recalcular_estado_venta(db, venta, margen)

        record_event(
            db,
            actor=usuario,
            action="CREATE",
            entity_type="pago",
            entity_id=pago.id,
            after={
                "venta_id": venta.id,
                "monto": args.monto,
                "moneda_id": args.moneda,
                "metodo_pago": cuenta.codigo,
                "fecha": args.fecha.isoformat(),
                "monto_en_moneda_base": monto_base,
                "conciliado_con_movimiento": mov.id,
            },
        )

        print(
            f"{'APLICADO' if args.aplicar else 'DRY-RUN'} · pago #{pago.id} "
            f"venta #{venta.id} · {args.monto:,.2f} moneda {args.moneda} "
            f"({monto_base:,.2f} en moneda de la venta) · {cuenta.nombre} · "
            f"mov {mov.id} enlazado · venta queda {venta.estado}"
        )
        print(f"venta total {venta.total} · saldo nuevo {_saldo_pendiente(db, venta):,.2f}")

        if args.aplicar:
            db.commit()
        else:
            db.rollback()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
