from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import date
from decimal import Decimal
from app.modules.tasas_cambio import model, schemas

def obtener_tasa_moneda_a_cop(db: Session, moneda_id: int, fecha: date = None):
    """
    Devuelve cuántos COP vale 1 unidad de la moneda indicada en la fecha dada.
    Usa la tasa registrada exactamente en esa fecha, o la más reciente anterior.
    Para COP devuelve 1.0. Si no hay tasa registrada, devuelve 1.0.
    """
    if moneda_id in (None, 1):
        return Decimal("1.0")
    fecha = fecha or date.today()
    query = db.query(model.TasaCambio).filter(
        model.TasaCambio.moneda_origen_id == moneda_id,
        model.TasaCambio.moneda_destino_id == 1,
        model.TasaCambio.fecha <= fecha,
    ).order_by(model.TasaCambio.fecha.desc())
    tasa = query.first()
    if not tasa:
        # Buscar hacia el futuro (si solo hay tasas posteriores)
        tasa = db.query(model.TasaCambio).filter(
            model.TasaCambio.moneda_origen_id == moneda_id,
            model.TasaCambio.moneda_destino_id == 1,
        ).order_by(model.TasaCambio.fecha.asc()).first()
    return Decimal(str(tasa.valor)) if tasa else Decimal("1.0")


def obtener_tasa(db: Session, tasa_id: int):
    return db.query(model.TasaCambio).filter(model.TasaCambio.id == tasa_id).first()

def obtener_tasa_por_fecha(db: Session, moneda_origen_id: int, moneda_destino_id: int, fecha: date):
    return db.query(model.TasaCambio).filter(
        model.TasaCambio.moneda_origen_id == moneda_origen_id,
        model.TasaCambio.moneda_destino_id == moneda_destino_id,
        model.TasaCambio.fecha == fecha
    ).first()

def obtener_ultima_tasa(db: Session, moneda_origen_id: int, moneda_destino_id: int):
    return db.query(model.TasaCambio).filter(
        model.TasaCambio.moneda_origen_id == moneda_origen_id,
        model.TasaCambio.moneda_destino_id == moneda_destino_id
    ).order_by(model.TasaCambio.fecha.desc()).first()

def listar_tasas(
    db: Session,
    skip: int = 0,
    limit: int = 100,
    moneda_origen_id: Optional[int] = None,
    moneda_destino_id: Optional[int] = None
) -> List[model.TasaCambio]:
    query = db.query(model.TasaCambio)
    if moneda_origen_id:
        query = query.filter(model.TasaCambio.moneda_origen_id == moneda_origen_id)
    if moneda_destino_id:
        query = query.filter(model.TasaCambio.moneda_destino_id == moneda_destino_id)
    return query.order_by(model.TasaCambio.fecha.desc()).offset(skip).limit(limit).all()

def crear_tasa(db: Session, tasa: schemas.TasaCambioCreate):
    # Verificar si ya existe la misma tasa para esa fecha y pares
    existente = obtener_tasa_por_fecha(db, tasa.moneda_origen_id, tasa.moneda_destino_id, tasa.fecha)
    if existente:
        raise ValueError("Ya existe una tasa para ese par y fecha")
    db_tasa = model.TasaCambio(**tasa.model_dump())
    db.add(db_tasa)
    db.commit()
    db.refresh(db_tasa)
    return db_tasa

def eliminar_tasa(db: Session, tasa_id: int) -> bool:
    db_tasa = obtener_tasa(db, tasa_id)
    if not db_tasa:
        return False
    db.delete(db_tasa)
    db.commit()
    return True