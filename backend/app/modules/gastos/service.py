from sqlalchemy.orm import Session, joinedload
from typing import List, Optional
from datetime import date
from decimal import Decimal
from app.modules.gastos import model, schemas
from app.modules.catalogos.model import TipoGasto, Moneda, Area
from app.modules.auditoria.service import record_event
from app.modules.users.deps import filtrar_registros_propios
from app.modules.users.model import Usuario


def _validar_fks(db: Session, tipo_gasto_id: int, moneda_id: int) -> Moneda:
    """Valida que el tipo de gasto y la moneda existan; devuelve la moneda (o lanza ValueError)."""
    if not db.query(TipoGasto).filter(TipoGasto.id == tipo_gasto_id).first():
        raise ValueError(f"El tipo de gasto con id {tipo_gasto_id} no existe.")
    moneda = db.query(Moneda).filter(Moneda.id == moneda_id).first()
    if not moneda:
        raise ValueError(f"La moneda con id {moneda_id} no existe.")
    return moneda


def _validar_area(db: Session, area_id: Optional[int]) -> None:
    """Valida que el área exista si se indica (None = sin área, válido); lanza ValueError si no."""
    if area_id is None:
        return
    if not db.query(Area).filter(Area.id == area_id).first():
        raise ValueError(f"El área con id {area_id} no existe.")


def _resolver_tasa(db: Session, moneda: Moneda, fecha: date, tasa_cambio) -> Decimal:
    """Devuelve la tasa a COP: 1.0 si es COP, la indicada, o la vigente si no se indicó."""
    if moneda.codigo == "COP":
        return Decimal("1.0")
    if tasa_cambio is None:
        from app.modules.tasas_cambio.service import obtener_tasa_moneda_a_cop
        tasa_cambio = obtener_tasa_moneda_a_cop(db, moneda.id, fecha)
    if Decimal(str(tasa_cambio)) <= 0:
        raise ValueError("La tasa de cambio debe ser mayor que cero.")
    return Decimal(str(tasa_cambio))

def _adjuntar_metodo_caja(db: Session, gastos):
    """Adjunta la cuenta de caja de cada gasto (id + nombre) desde su movimiento."""
    from app.modules.reports.model import MovimientoCaja, MetodoCaja
    solo = not isinstance(gastos, list)
    lista = [gastos] if solo else gastos
    if not lista:
        return gastos
    refs = {f"Gasto #{g.id}": g for g in lista}
    cuentas = {c.id: c.nombre for c in db.query(MetodoCaja).all()}
    for mv in db.query(MovimientoCaja).filter(MovimientoCaja.referencia.in_(refs.keys())).all():
        g = refs.get(mv.referencia)
        if g is not None:
            g.metodo_caja_id = mv.metodo_caja_id
            g.metodo_caja_nombre = cuentas.get(mv.metodo_caja_id)
    return gastos


def _snapshot(gasto: model.Gasto) -> dict:
    return {
        "tipo_gasto_id": gasto.tipo_gasto_id,
        "moneda_id": gasto.moneda_id,
        "fecha": gasto.fecha,
        "monto": gasto.monto,
        "descripcion": gasto.descripcion,
        "observaciones": gasto.observaciones,
    }


def obtener_gasto(db: Session, gasto_id: int, usuario: Usuario | None = None):
    query = db.query(model.Gasto).options(
        joinedload(model.Gasto.tipo_gasto),
        joinedload(model.Gasto.moneda),
        joinedload(model.Gasto.area)
    ).filter(model.Gasto.id == gasto_id)
    if usuario is not None:
        query = filtrar_registros_propios(query, model.Gasto.creado_por_id, usuario)
    gasto = query.first()
    if gasto:
        _adjuntar_metodo_caja(db, gasto)
    return gasto

def obtener_gastos(
    db: Session,
    skip: int = 0,
    limit: int = 100,
    tipo_gasto_id: Optional[int] = None,
    categoria: Optional[str] = None,
    area_id: Optional[int] = None,
    fecha_desde: Optional[date] = None,
    fecha_hasta: Optional[date] = None,
    usuario: Usuario | None = None,
) -> List[model.Gasto]:
    query = db.query(model.Gasto).options(
        joinedload(model.Gasto.tipo_gasto),
        joinedload(model.Gasto.moneda),
        joinedload(model.Gasto.area)
    )
    if usuario is not None:
        query = filtrar_registros_propios(query, model.Gasto.creado_por_id, usuario)
    if tipo_gasto_id:
        query = query.filter(model.Gasto.tipo_gasto_id == tipo_gasto_id)
    if categoria:
        query = query.join(model.Gasto.tipo_gasto).filter(TipoGasto.categoria == categoria.upper())
    if area_id:
        query = query.filter(model.Gasto.area_id == area_id)
    if fecha_desde:
        query = query.filter(model.Gasto.fecha >= fecha_desde)
    if fecha_hasta:
        query = query.filter(model.Gasto.fecha <= fecha_hasta)
    gastos = query.order_by(model.Gasto.fecha.desc()).offset(skip).limit(limit).all()
    return _adjuntar_metodo_caja(db, gastos)

def crear_gasto(db: Session, gasto: schemas.GastoCreate, usuario: Usuario | None = None, commit: bool = True):
    _validar_area(db, gasto.area_id)
    moneda = _validar_fks(db, gasto.tipo_gasto_id, gasto.moneda_id)
    tasa = _resolver_tasa(db, moneda, gasto.fecha, gasto.tasa_cambio)
    es_cop = moneda.codigo == "COP"
    monto_en_moneda_base = gasto.monto if es_cop else gasto.monto * tasa

    db_gasto = model.Gasto(
        tipo_gasto_id=gasto.tipo_gasto_id,
        moneda_id=gasto.moneda_id,
        area_id=gasto.area_id,
        fecha=gasto.fecha,
        descripcion=gasto.descripcion,
        monto=gasto.monto,
        tasa_cambio=tasa,
        monto_en_moneda_base=monto_en_moneda_base,
        observaciones=gasto.observaciones,
        creado_por_id=usuario.id if usuario is not None else None,
        actualizado_por_id=usuario.id if usuario is not None else None,
    )
    db.add(db_gasto)
    db.flush()

    # Si el gasto indica método de caja, el efectivo SALE de esa cuenta.
    # Sin esto, los gastos existían solo como número en el P&L y el saldo de
    # caja nunca bajaba (egreso fantasma).
    if gasto.metodo_caja_id:
        from app.core.caja import registrar_movimiento_caja
        registrar_movimiento_caja(
            db,
            metodo_caja_id=gasto.metodo_caja_id,
            tipo="SALIDA",
            monto=float(gasto.monto),
            moneda_id=gasto.moneda_id,
            tasa_cambio=float(tasa),
            fecha=gasto.fecha,
            referencia=f"Gasto #{db_gasto.id}",
            observaciones=gasto.descripcion or f"Gasto #{db_gasto.id}",
            usuario_id=usuario.id if usuario is not None else None,
        )

    record_event(
        db,
        actor=usuario,
        action="CREATE",
        entity_type="gasto",
        entity_id=db_gasto.id,
        after=_snapshot(db_gasto),
    )
    if commit:
        db.commit()
        db.refresh(db_gasto)
    return _adjuntar_metodo_caja(db, db_gasto)

def actualizar_gasto(
    db: Session,
    gasto_id: int,
    gasto_update: schemas.GastoUpdate,
    usuario: Usuario | None = None,
):
    db_gasto = obtener_gasto(db, gasto_id, usuario)
    if not db_gasto:
        return None
    antes = _snapshot(db_gasto)
    data = gasto_update.model_dump(exclude_unset=True)

    # Rechazar nulos explícitos sobre columnas NOT NULL (antes: TypeError/IntegrityError 500)
    for campo in ("tipo_gasto_id", "moneda_id", "monto", "tasa_cambio"):
        if campo in data and data[campo] is None:
            raise ValueError(f"El campo {campo} no puede ser nulo.")

    # Validar FKs si vienen en el update
    moneda = None
    if "tipo_gasto_id" in data:
        if not db.query(TipoGasto).filter(TipoGasto.id == data["tipo_gasto_id"]).first():
            raise ValueError(f"El tipo de gasto con id {data['tipo_gasto_id']} no existe.")
    if "moneda_id" in data:
        moneda = _validar_fks(db, db_gasto.tipo_gasto_id, data["moneda_id"])

    # Validar el área si viene en el update (None es válido: limpia el área).
    if "area_id" in data:
        _validar_area(db, data["area_id"])

    # Recalcular monto_en_moneda_base si cambió moneda, monto o tasa
    if "monto" in data or "tasa_cambio" in data or "moneda_id" in data:
        moneda = moneda or db.query(Moneda).filter(Moneda.id == (data.get("moneda_id") or db_gasto.moneda_id)).first()
        monto = data.get("monto", db_gasto.monto)
        es_cop = moneda is not None and moneda.codigo == "COP"
        if es_cop:
            data["tasa_cambio"] = Decimal("1.0")
            data["monto_en_moneda_base"] = monto
        else:
            tasa = data.get("tasa_cambio", db_gasto.tasa_cambio)
            if tasa is None:
                from app.modules.tasas_cambio.service import obtener_tasa_moneda_a_cop
                tasa = obtener_tasa_moneda_a_cop(db, moneda.id, db_gasto.fecha)
            if Decimal(str(tasa)) <= 0:
                raise ValueError("La tasa de cambio debe ser mayor que cero.")
            data["tasa_cambio"] = Decimal(str(tasa))
            data["monto_en_moneda_base"] = monto * data["tasa_cambio"]

    for key, value in data.items():
        setattr(db_gasto, key, value)
    if usuario is not None:
        db_gasto.actualizado_por_id = usuario.id
    record_event(
        db,
        actor=usuario,
        action="UPDATE",
        entity_type="gasto",
        entity_id=db_gasto.id,
        before=antes,
        after=_snapshot(db_gasto),
    )
    db.commit()
    db.refresh(db_gasto)
    return db_gasto

def eliminar_gasto(db: Session, gasto_id: int, usuario: Usuario | None = None) -> bool:
    db_gasto = obtener_gasto(db, gasto_id, usuario)
    if not db_gasto:
        return False
    # Al eliminar un gasto con salida de caja, se revierte su movimiento para
    # que el saldo de la cuenta no quede con un egreso que ya no existe.
    from app.modules.reports.model import MovimientoCaja
    db.query(MovimientoCaja).filter(
        MovimientoCaja.referencia == f"Gasto #{db_gasto.id}"
    ).delete(synchronize_session=False)
    record_event(
        db,
        actor=usuario,
        action="DELETE",
        entity_type="gasto",
        entity_id=db_gasto.id,
        before=_snapshot(db_gasto),
    )
    db.delete(db_gasto)
    db.commit()
    return True
