from datetime import date
from decimal import Decimal
from typing import List, Optional

from sqlalchemy.orm import Session, joinedload

from app.modules.catalogos.model import Moneda, TipoGasto
from app.modules.cuentas_por_pagar import model, schemas
from app.modules.gastos.schemas import GastoCreate
from app.modules.gastos.service import crear_gasto
from app.modules.proveedores.model import Proveedor
from app.modules.users.deps import filtrar_registros_propios
from app.modules.users.model import Usuario
from app.modules.auditoria.service import record_event

MONEDA_BASE_ID = 1  # COP
TIPO_GASTO_COMPRA_INSUMOS = "COMPRA DE INSUMOS"


def _validar_fks(db: Session, proveedor_id: int, tipo_gasto_id: int, moneda_id: int) -> Moneda:
    if not db.query(Proveedor).filter(Proveedor.id == proveedor_id).first():
        raise ValueError(f"El proveedor con id {proveedor_id} no existe.")
    if not db.query(TipoGasto).filter(TipoGasto.id == tipo_gasto_id).first():
        raise ValueError(f"El tipo de gasto con id {tipo_gasto_id} no existe.")
    moneda = db.query(Moneda).filter(Moneda.id == moneda_id).first()
    if not moneda:
        raise ValueError(f"La moneda con id {moneda_id} no existe.")
    return moneda


def _resolver_tasa(db: Session, moneda: Moneda, fecha: date, tasa_cambio) -> Decimal:
    if moneda.codigo == "COP":
        return Decimal("1.0")
    if tasa_cambio is None:
        from app.modules.tasas_cambio.service import obtener_tasa_moneda_a_cop
        tasa_cambio = obtener_tasa_moneda_a_cop(db, moneda.id, fecha)
    if Decimal(str(tasa_cambio)) <= 0:
        raise ValueError("La tasa de cambio debe ser mayor que cero.")
    return Decimal(str(tasa_cambio))


def _resolver_tipo_compra_insumos(db: Session) -> TipoGasto:
    tipo_gasto = db.query(TipoGasto).filter(TipoGasto.nombre == TIPO_GASTO_COMPRA_INSUMOS).first()
    if not tipo_gasto:
        tipo_gasto = TipoGasto(nombre=TIPO_GASTO_COMPRA_INSUMOS, categoria="OPERATIVO")
        db.add(tipo_gasto)
        db.flush()
    return tipo_gasto


def _snapshot(cxp: model.CuentaPorPagar) -> dict:
    return {
        "proveedor_id": cxp.proveedor_id,
        "monto": cxp.monto,
        "monto_pagado": cxp.monto_pagado,
        "estado": cxp.estado,
        "fecha": cxp.fecha,
    }


def _registrar_gasto_deuda(db: Session, cxp: model.CuentaPorPagar, usuario) -> None:
    """El egreso entra al P&L al nacer la deuda, sin tocar caja: abonar solo
    mueve caja, así el egreso no se duplica en el P&L."""
    gasto = crear_gasto(
        db,
        GastoCreate(
            tipo_gasto_id=cxp.tipo_gasto_id,
            moneda_id=cxp.moneda_id,
            fecha=cxp.fecha,
            descripcion=cxp.descripcion or f"Deuda con proveedor #{cxp.proveedor_id}",
            monto=cxp.monto,
            tasa_cambio=cxp.tasa_cambio,
            observaciones=f"Fiado — Por Pagar #{cxp.id}",
        ),
        commit=False,
        usuario=usuario,
    )
    cxp.gasto_id = gasto.id


def obtener_cuenta(db: Session, cxp_id: int, usuario: Optional[Usuario] = None):
    query = db.query(model.CuentaPorPagar).options(
        joinedload(model.CuentaPorPagar.proveedor),
        joinedload(model.CuentaPorPagar.moneda),
        joinedload(model.CuentaPorPagar.tipo_gasto),
        joinedload(model.CuentaPorPagar.pagos).joinedload(model.PagoCuentaPorPagar.metodo_caja),
    ).filter(model.CuentaPorPagar.id == cxp_id)
    if usuario is not None:
        query = filtrar_registros_propios(query, model.CuentaPorPagar.creado_por_id, usuario)
    return query.first()


def obtener_cuentas(
    db: Session,
    skip: int = 0,
    limit: int = 100,
    estado: Optional[str] = None,
    proveedor_id: Optional[int] = None,
    usuario: Optional[Usuario] = None,
) -> List[model.CuentaPorPagar]:
    query = db.query(model.CuentaPorPagar).options(
        joinedload(model.CuentaPorPagar.proveedor),
        joinedload(model.CuentaPorPagar.moneda),
        joinedload(model.CuentaPorPagar.tipo_gasto),
        joinedload(model.CuentaPorPagar.pagos).joinedload(model.PagoCuentaPorPagar.metodo_caja),
    )
    if usuario is not None:
        query = filtrar_registros_propios(query, model.CuentaPorPagar.creado_por_id, usuario)
    if estado:
        query = query.filter(model.CuentaPorPagar.estado == estado.upper())
    if proveedor_id:
        query = query.filter(model.CuentaPorPagar.proveedor_id == proveedor_id)
    return query.order_by(
        model.CuentaPorPagar.fecha.desc(), model.CuentaPorPagar.id.desc()
    ).offset(skip).limit(limit).all()


def obtener_resumen(db: Session, usuario: Optional[Usuario] = None) -> schemas.ResumenCuentasPorPagar:
    query = db.query(model.CuentaPorPagar).options(
        joinedload(model.CuentaPorPagar.proveedor)
    )
    if usuario is not None:
        query = filtrar_registros_propios(query, model.CuentaPorPagar.creado_por_id, usuario)
    por_proveedor: dict = {}
    total_pendiente = Decimal("0.0")
    total_pagado = Decimal("0.0")
    deudas_pendientes = 0
    for cxp in query.all():
        total_pagado += Decimal(str(cxp.monto_pagado))
        if cxp.estado == "PENDIENTE":
            deudas_pendientes += 1
            saldo = cxp.saldo
            total_pendiente += saldo
            linea = por_proveedor.setdefault(cxp.proveedor_id, {
                "proveedor_id": cxp.proveedor_id,
                "proveedor_nombre": cxp.proveedor.nombre,
                "saldo": Decimal("0.0"),
            })
            linea["saldo"] += saldo
    return schemas.ResumenCuentasPorPagar(
        total_pendiente=total_pendiente.quantize(Decimal("0.01")),
        total_pagado=total_pagado.quantize(Decimal("0.01")),
        total_deudas=deudas_pendientes,
        por_proveedor=[schemas.LineaSaldoProveedor(**linea) for linea in sorted(
            por_proveedor.values(), key=lambda l: l["saldo"], reverse=True
        )],
    )


def crear_cuenta(db: Session, datos: schemas.CuentaPorPagarCreate, usuario: Optional[Usuario] = None) -> model.CuentaPorPagar:
    moneda = _validar_fks(db, datos.proveedor_id, datos.tipo_gasto_id, datos.moneda_id)
    tasa = _resolver_tasa(db, moneda, datos.fecha, datos.tasa_cambio)

    cxp = model.CuentaPorPagar(
        proveedor_id=datos.proveedor_id,
        tipo_gasto_id=datos.tipo_gasto_id,
        moneda_id=datos.moneda_id,
        fecha=datos.fecha,
        descripcion=datos.descripcion,
        monto=datos.monto,
        tasa_cambio=tasa,
        monto_en_moneda_base=(datos.monto * tasa).quantize(Decimal("0.01")),
        estado="PENDIENTE",
        origen_tipo="MANUAL",
        creado_por_id=usuario.id if usuario is not None else None,
    )
    db.add(cxp)
    db.flush()
    _registrar_gasto_deuda(db, cxp, usuario)
    record_event(
        db,
        actor=usuario,
        action="CREATE",
        entity_type="cuenta_por_pagar",
        entity_id=cxp.id,
        after=_snapshot(cxp),
    )
    db.commit()
    db.refresh(cxp)
    return cxp


def crear_cuenta_desde_entrada(
    db: Session,
    *,
    proveedor_id: int,
    material_nombre: str,
    cantidad: Decimal,
    costo_unitario: Decimal,
    llevada: Decimal,
    fecha: date,
    movimiento_id: int,
    usuario=None,
) -> model.CuentaPorPagar:
    """Deuda nacida de una entrada de inventario sin pagar ("fiar"): el monto
    es compra + pasada. NO hace commit (el llamador lo hace en su transacción)."""
    if not db.query(Proveedor).filter(Proveedor.id == proveedor_id).first():
        raise ValueError(f"El proveedor con id {proveedor_id} no existe.")
    tipo_gasto = _resolver_tipo_compra_insumos(db)
    monto = (cantidad * costo_unitario + llevada).quantize(Decimal("0.01"))

    cxp = model.CuentaPorPagar(
        proveedor_id=proveedor_id,
        tipo_gasto_id=tipo_gasto.id,
        moneda_id=MONEDA_BASE_ID,
        fecha=fecha,
        descripcion=f"Compra fiada: {material_nombre} x{cantidad:g}",
        monto=monto,
        tasa_cambio=Decimal("1.0"),
        monto_en_moneda_base=monto,
        estado="PENDIENTE",
        origen_tipo="ENTRADA_INVENTARIO",
        origen_id=movimiento_id,
        creado_por_id=usuario.id if usuario is not None else None,
    )
    db.add(cxp)
    db.flush()
    _registrar_gasto_deuda(db, cxp, usuario)
    return cxp


def _calcular_abono_caja(db: Session, cxp: model.CuentaPorPagar, abono: schemas.AbonoCreate):
    """Convierte el abono (en moneda de la deuda) al movimiento de caja (en
    moneda de la cuenta). Una sola tasa manual: '1 [moneda cuenta] = X COP'.
    El equivalente COP usa la tasa de la deuda, que es la que el P&L ya contó."""
    from app.modules.reports.model import MetodoCaja
    cuenta = db.query(MetodoCaja).filter(MetodoCaja.id == abono.metodo_caja_id).first()
    if not cuenta:
        raise ValueError("La cuenta de caja indicada no existe.")
    moneda_cuenta = db.query(Moneda).filter(Moneda.id == (cuenta.moneda_id or MONEDA_BASE_ID)).first()
    if moneda_cuenta is None:
        moneda_cuenta = db.query(Moneda).filter(Moneda.id == MONEDA_BASE_ID).first()
    tasa_cuenta = Decimal(str(abono.tasa_cambio or 1.0))
    if moneda_cuenta.codigo != "COP" and not (tasa_cuenta > 0):
        raise ValueError(f"Indica la tasa de cambio: 1 {moneda_cuenta.codigo} = ? COP")
    if moneda_cuenta.codigo == "COP":
        tasa_cuenta = Decimal("1.0")
    tasa_deuda = Decimal(str(cxp.tasa_cambio or 1.0))
    monto_cuenta = (Decimal(str(abono.monto)) * tasa_deuda / tasa_cuenta).quantize(Decimal("0.01"))
    monto_base = (Decimal(str(abono.monto)) * tasa_deuda).quantize(Decimal("0.01"))
    return cuenta, moneda_cuenta, monto_cuenta, monto_base, tasa_cuenta


def abonar(db: Session, cxp_id: int, abono: schemas.AbonoCreate, usuario: Optional[Usuario] = None) -> model.PagoCuentaPorPagar:
    cxp = obtener_cuenta(db, cxp_id, usuario)
    if not cxp:
        raise ValueError("La cuenta por pagar no existe.")
    saldo = cxp.saldo
    if Decimal(str(abono.monto)) > saldo + Decimal("0.005"):
        raise ValueError(f"El abono excede el saldo de la deuda (saldo: {saldo}).")
    antes = _snapshot(cxp)

    cuenta, moneda_cuenta, monto_cuenta, monto_base, tasa_cuenta = _calcular_abono_caja(db, cxp, abono)
    pago = model.PagoCuentaPorPagar(
        cuenta_por_pagar_id=cxp.id,
        fecha=abono.fecha,
        metodo_caja_id=cuenta.id,
        monto=abono.monto,
        tasa_cambio=tasa_cuenta,
        monto_en_moneda_base=monto_base,
        creado_por_id=usuario.id if usuario is not None else None,
    )
    db.add(pago)
    db.flush()

    from app.core.caja import registrar_movimiento_caja
    registrar_movimiento_caja(
        db,
        metodo_caja_id=cuenta.id,
        tipo="SALIDA",
        monto=float(monto_cuenta),
        moneda_id=moneda_cuenta.id,
        tasa_cambio=float(tasa_cuenta),
        fecha=abono.fecha,
        referencia=f"CxP #{cxp.id} abono #{pago.id}",
        observaciones=f"Abono a Por Pagar #{cxp.id}",
        usuario_id=usuario.id if usuario is not None else None,
    )

    cxp.monto_pagado = (Decimal(str(cxp.monto_pagado)) + Decimal(str(abono.monto))).quantize(Decimal("0.01"))
    if cxp.saldo <= Decimal("0.005"):
        cxp.estado = "PAGADA"
    record_event(
        db,
        actor=usuario,
        action="UPDATE",
        entity_type="cuenta_por_pagar",
        entity_id=cxp.id,
        before=antes,
    )
    db.commit()
    db.refresh(pago)
    return pago


def eliminar_abono(db: Session, abono_id: int, usuario: Optional[Usuario] = None) -> bool:
    pago = db.query(model.PagoCuentaPorPagar).filter(model.PagoCuentaPorPagar.id == abono_id).first()
    if not pago:
        return False
    cxp = obtener_cuenta(db, pago.cuenta_por_pagar_id, usuario)
    if not cxp:
        raise ValueError("La cuenta por pagar asociada no existe.")

    from app.modules.reports.model import MovimientoCaja
    db.query(MovimientoCaja).filter(
        MovimientoCaja.referencia == f"CxP #{cxp.id} abono #{pago.id}"
    ).delete(synchronize_session=False)
    cxp.monto_pagado = (Decimal(str(cxp.monto_pagado)) - Decimal(str(pago.monto))).quantize(Decimal("0.01"))
    cxp.estado = "PAGADA" if cxp.saldo <= Decimal("0.005") else "PENDIENTE"
    db.delete(pago)
    db.commit()
    return True


def eliminar_cuenta(db: Session, cxp_id: int, usuario: Optional[Usuario] = None) -> bool:
    cxp = obtener_cuenta(db, cxp_id, usuario)
    if not cxp:
        return False
    if Decimal(str(cxp.monto_pagado)) > 0:
        raise ValueError("No se puede eliminar una deuda con abonos. Elimina primero sus abonos.")

    if cxp.gasto_id:
        from app.modules.gastos.model import Gasto
        from app.modules.reports.model import MovimientoCaja
        db.query(MovimientoCaja).filter(
            MovimientoCaja.referencia == f"Gasto #{cxp.gasto_id}"
        ).delete(synchronize_session=False)
        db.query(Gasto).filter(Gasto.id == cxp.gasto_id).delete(synchronize_session=False)
    record_event(
        db,
        actor=usuario,
        action="DELETE",
        entity_type="cuenta_por_pagar",
        entity_id=cxp.id,
        before=_snapshot(cxp),
    )
    db.delete(cxp)
    db.commit()
    return True