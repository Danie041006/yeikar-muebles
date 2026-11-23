"""Créditos de clientes: excedentes y aplicaciones sin duplicar caja."""
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP, ROUND_UP

from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload, selectinload

from app.modules.auditoria.service import record_event
from app.modules.sales.model import AplicacionSaldoFavor, Pago, SaldoFavor, Venta
from app.modules.sales.cobros import monto_aplicado

CENTAVO = Decimal("0.01")


def dinero(valor) -> Decimal:
    return Decimal(str(valor)).quantize(CENTAVO, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class RepartoCobro:
    aplicado: Decimal
    excedente: Decimal


def repartir_cobro(monto, tasa, equivalente, saldo) -> RepartoCobro:
    """El crédito nace del dinero real, nunca del redondeo de la conversión."""
    recibido = dinero(monto)
    pendiente = max(Decimal("0"), dinero(saldo))
    conversion = Decimal(str(tasa))
    necesario = (pendiente / conversion).quantize(CENTAVO, rounding=ROUND_UP)
    excedente = max(Decimal("0"), recibido - necesario)
    aplicado = pendiente if excedente else min(pendiente, dinero(equivalente))
    return RepartoCobro(aplicado=aplicado, excedente=excedente)


def confirmar_reparto(reparto: RepartoCobro, confirmado: bool, saldo_confirmado, saldo) -> None:
    if not reparto.excedente:
        return
    if confirmado and saldo_confirmado is not None and dinero(saldo_confirmado) == dinero(saldo):
        return
    raise HTTPException(status_code=409, detail={
        "codigo": "CONFIRMAR_EXCEDENTE",
        "mensaje": "Confirma el cobro y el saldo a favor antes de registrarlo.",
        "monto_aplicado": str(reparto.aplicado),
        "saldo_favor": str(reparto.excedente),
        "saldo_confirmado": str(max(Decimal("0"), dinero(saldo))),
    })


@dataclass(frozen=True)
class ConfirmacionConversion:
    confirmado: bool
    total: Decimal | None


def confirmar_abonos_conversion(
    db: Session, venta: Venta, pagos: list, confirmacion: ConfirmacionConversion,
) -> None:
    """Verifica todos los abonos antes de escribir: si alguno deja crédito, exige confirmar."""
    from app.modules.sales.service import _convertir_a_moneda_venta
    from app.modules.catalogos.model import Moneda

    pendiente = dinero(venta.total)
    excedentes = []
    for pago in pagos:
        tasa, equivalente, _ = _convertir_a_moneda_venta(db, pago.moneda_id, pago.monto, pago.tasa_cambio, venta)
        reparto = repartir_cobro(pago.monto, tasa, equivalente, pendiente)
        pendiente -= reparto.aplicado
        if reparto.excedente:
            moneda = db.query(Moneda).filter(Moneda.id == pago.moneda_id).one()
            excedentes.append({"monto": str(reparto.excedente), "moneda": moneda.codigo})
    if not excedentes:
        return
    total_confirmado = confirmacion.total
    if confirmacion.confirmado and total_confirmado is not None and dinero(total_confirmado) == dinero(venta.total):
        return
    raise HTTPException(status_code=409, detail={
        "codigo": "CONFIRMAR_ABONOS", "total_confirmado": str(venta.total),
        "excedentes": excedentes,
        "mensaje": "Los abonos dejan saldo a favor. Revisa los excedentes antes de confirmar.",
    })


def bloquear_credito(db: Session, credito_id: int) -> SaldoFavor:
    credito = db.query(SaldoFavor).filter(SaldoFavor.id == credito_id).with_for_update().populate_existing().first()
    if not credito:
        raise ValueError("El saldo a favor no existe.")
    db.expire(credito, ["aplicaciones"])
    return credito


def _validar_sin_uso(credito: SaldoFavor) -> None:
    if credito.aplicaciones:
        ventas = sorted({a.pago.venta_id for a in credito.aplicaciones})
        raise HTTPException(status_code=409, detail=(
            f"El saldo a favor ya se usó en las ventas {', '.join(map(str, ventas))}. "
            "Revierte primero esas aplicaciones; no se modificó el cobro ni la caja."
        ))


def guardar_excedente(db: Session, pago: Pago, monto: Decimal, usuario=None) -> None:
    credito = db.query(SaldoFavor).filter(SaldoFavor.pago_origen_id == pago.id).with_for_update().first()
    if credito:
        db.expire(credito, ["aplicaciones"])
        _validar_sin_uso(credito)
        antes = {"monto": credito.monto, "anulado": credito.anulado}
        credito.monto = monto
        credito.anulado = not bool(monto)
    elif monto:
        antes = None
        credito = SaldoFavor(
            cliente_id=pago.venta.cliente_id, moneda_id=pago.moneda_id,
            pago_origen_id=pago.id, monto=monto, referencia=f"Cobro #{pago.id} · Venta #{pago.venta_id}",
            creado_por_id=usuario.id if usuario else pago.creado_por_id,
        )
        db.add(credito)
    else:
        return
    db.flush()
    record_event(db, actor=usuario, action="UPDATE" if antes else "CREATE",
                 entity_type="saldo_favor", entity_id=credito.id, before=antes,
                 after={"monto": monto, "pago_id": pago.id, "anulado": credito.anulado})
    db.expire(pago, ["credito_generado"])


def revertir_credito_pago(db: Session, pago: Pago, usuario=None) -> None:
    """Se ejecuta dentro de la misma transacción que revierte pago y caja."""
    aplicacion = db.query(AplicacionSaldoFavor).filter(AplicacionSaldoFavor.pago_id == pago.id).first()
    if aplicacion:
        credito = bloquear_credito(db, aplicacion.saldo_favor_id)
        record_event(db, actor=usuario, action="UPDATE", entity_type="saldo_favor",
                     entity_id=credito.id, before={"saldo": credito.saldo},
                     after={"reversion_pago_id": pago.id, "devuelto": aplicacion.monto})
        db.delete(aplicacion)
        db.flush()
        db.expire(credito, ["aplicaciones"])
    credito = db.query(SaldoFavor).filter(SaldoFavor.pago_origen_id == pago.id).with_for_update().first()
    if credito:
        db.expire(credito, ["aplicaciones"])
        _validar_sin_uso(credito)
        record_event(db, actor=usuario, action="UPDATE", entity_type="saldo_favor",
                     entity_id=credito.id, before={"monto": credito.monto},
                     after={"anulado": True, "pago_eliminado_id": pago.id})
        credito.anulado = True
        credito.pago_origen_id = None
        db.flush()


def listar_saldos(db: Session, cliente_id: int | None, salto: int, limite: int):
    usados = (
        db.query(AplicacionSaldoFavor.saldo_favor_id,
                 func.sum(AplicacionSaldoFavor.monto).label("usado"))
        .group_by(AplicacionSaldoFavor.saldo_favor_id).subquery()
    )
    consulta = db.query(SaldoFavor).outerjoin(usados, usados.c.saldo_favor_id == SaldoFavor.id).filter(
        SaldoFavor.anulado.is_(False), SaldoFavor.monto > func.coalesce(usados.c.usado, 0),
    )
    if cliente_id is not None:
        consulta = consulta.filter(SaldoFavor.cliente_id == cliente_id)
    return consulta.options(
        joinedload(SaldoFavor.cliente), joinedload(SaldoFavor.moneda),
        joinedload(SaldoFavor.creador), selectinload(SaldoFavor.aplicaciones),
    ).order_by(SaldoFavor.id).offset(salto).limit(limite).all()


def _importe_aplicacion(moneda_id: int, venta: Venta, monto, tasa) -> tuple[Decimal, Decimal]:
    conversion = Decimal("1") if moneda_id == venta.moneda_id else Decimal(str(tasa or 0))
    if not conversion.is_finite() or conversion <= 0:
        raise ValueError("Digita la tasa manual: 1 unidad del saldo a favor = X de la moneda de la venta.")
    equivalente = dinero(Decimal(str(monto)) * conversion)
    if equivalente <= 0:
        raise ValueError("El equivalente no puede ser cero. Revisa el monto y la tasa manual.")
    return conversion, equivalente


@dataclass(frozen=True)
class UsoCredito:
    monto: Decimal
    equivalente: Decimal
    pendiente: Decimal


def _validar_aplicacion(credito: SaldoFavor, venta: Venta, uso: UsoCredito) -> None:
    if credito.cliente_id != venta.cliente_id:
        raise ValueError("El saldo a favor pertenece a otro cliente.")
    if credito.anulado or uso.monto > credito.saldo:
        raise HTTPException(status_code=409, detail="El saldo a favor disponible cambió. Recarga antes de cobrar.")
    if uso.equivalente > dinero(uso.pendiente):
        raise ValueError("Aplica solo lo pendiente de la factura. El resto continúa a favor del cliente.")


def aplicar_saldo(db: Session, esquema, usuario=None) -> Pago:
    from app.modules.sales.service import _normalizar_fecha_pago, _recalcular_estado_venta, _saldo_pendiente

    venta = db.query(Venta).filter(Venta.id == esquema.venta_id).with_for_update().first()
    if not venta or venta.estado == "CANCELADA":
        raise ValueError("La venta no existe o está cancelada.")
    existente = db.query(Pago).filter(Pago.operacion_id == str(esquema.operacion_id)).first()
    if existente:
        aplicacion = existente.aplicacion_credito
        if (existente.venta_id != venta.id or not aplicacion
                or aplicacion.saldo_favor_id != esquema.saldo_favor_id
                or dinero(existente.monto) != dinero(esquema.monto)):
            raise ValueError("La operación ya se registró con otros datos.")
        return existente
    credito = bloquear_credito(db, esquema.saldo_favor_id)
    tasa, equivalente = _importe_aplicacion(credito.moneda_id, venta, esquema.monto, esquema.tasa_cambio)
    _validar_aplicacion(credito, venta, UsoCredito(
        monto=dinero(esquema.monto), equivalente=equivalente, pendiente=_saldo_pendiente(db, venta),
    ))
    fecha = _normalizar_fecha_pago(esquema.fecha)
    if credito.pago_origen and fecha.date() < credito.pago_origen.fecha.date():
        raise ValueError("No puedes usar un saldo a favor antes de la fecha en que se recibió.")
    pago = Pago(
        venta_id=venta.id, moneda_id=credito.moneda_id, monto=esquema.monto,
        tasa_cambio=tasa, monto_en_moneda_base=equivalente, monto_aplicado=equivalente,
        tipo="SALDO_FAVOR", metodo_pago="SALDO_FAVOR", fecha=fecha,
        operacion_id=str(esquema.operacion_id), creado_por_id=usuario.id if usuario else None,
        referencia=f"Aplicación de saldo a favor #{credito.id}",
    )
    db.add(pago)
    db.flush()
    db.add(AplicacionSaldoFavor(saldo_favor_id=credito.id, pago_id=pago.id, monto=esquema.monto))
    record_event(db, actor=usuario, action="CREATE", entity_type="saldo_favor_aplicacion",
                 entity_id=pago.id, after={"saldo_favor_id": credito.id, "monto": esquema.monto,
                                          "tasa_manual": tasa, "aplicado": equivalente, "venta_id": venta.id})
    db.flush()
    _recalcular_estado_venta(db, venta)
    if usuario:
        venta.actualizado_por_id = usuario.id
    db.commit()
    db.refresh(pago)
    return pago


def corregir_aplicacion(db: Session, pago: Pago, venta: Venta, datos: dict, motivo: str | None, usuario=None) -> Pago:
    from app.modules.sales.model import PagoCorreccion
    from app.modules.sales.service import _normalizar_fecha_pago, _recalcular_estado_venta, _saldo_pendiente
    from app.core.hora_ve import ahora_ve

    if datos.get("metodo_pago") not in (None, "SALDO_FAVOR"):
        raise ValueError("Aplicar saldo a favor no es un ingreso de caja; no puedes elegir una cuenta.")
    if not motivo:
        raise ValueError("Indica el motivo de la corrección de la aplicación.")
    aplicacion = pago.aplicacion_credito
    credito = bloquear_credito(db, aplicacion.saldo_favor_id)
    nuevo_monto = dinero(datos.get("monto") or pago.monto)
    tasa, equivalente = _importe_aplicacion(
        credito.moneda_id, venta, nuevo_monto, datos.get("tasa_cambio", pago.tasa_cambio),
    )
    if nuevo_monto > credito.saldo + aplicacion.monto:
        raise ValueError("El nuevo monto excede el saldo a favor disponible.")
    if equivalente > dinero(_saldo_pendiente(db, venta)) + monto_aplicado(pago):
        raise ValueError("El nuevo equivalente excede el saldo pendiente de la venta.")
    fecha = _normalizar_fecha_pago(datos.get("fecha") or pago.fecha)
    if credito.pago_origen and fecha.date() < credito.pago_origen.fecha.date():
        raise ValueError("La aplicación no puede ser anterior al cobro de origen.")
    antes = {"monto": pago.monto, "aplicado": monto_aplicado(pago), "tasa": pago.tasa_cambio}
    if nuevo_monto != pago.monto:
        db.add(PagoCorreccion(pago_id=pago.id, usuario_id=usuario.id if usuario else None,
                             monto_anterior=pago.monto, monto_nuevo=nuevo_monto,
                             monto_base_anterior=pago.monto_en_moneda_base, monto_base_nuevo=equivalente,
                             motivo=motivo, created_at=ahora_ve()))
    pago.monto = aplicacion.monto = nuevo_monto
    pago.monto_aplicado = pago.monto_en_moneda_base = equivalente
    pago.tasa_cambio = tasa
    pago.fecha = fecha
    for campo in ("referencia", "observaciones"):
        if campo in datos:
            setattr(pago, campo, datos[campo])
    record_event(db, actor=usuario, action="UPDATE", entity_type="pago", entity_id=pago.id,
                 before=antes, after={"monto": nuevo_monto, "aplicado": equivalente, "tasa": tasa, "motivo": motivo})
    db.flush()
    _recalcular_estado_venta(db, venta)
    db.commit()
    db.refresh(pago)
    return pago
