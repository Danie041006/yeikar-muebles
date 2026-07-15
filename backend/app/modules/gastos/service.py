from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import date
from app.modules.gastos import model, schemas

def obtener_gasto(db: Session, gasto_id: int):
    return db.query(model.Gasto).filter(model.Gasto.id == gasto_id).first()

def obtener_gastos(
    db: Session,
    skip: int = 0,
    limit: int = 100,
    tipo_gasto_id: Optional[int] = None,
    fecha_desde: Optional[date] = None,
    fecha_hasta: Optional[date] = None
) -> List[model.Gasto]:
    query = db.query(model.Gasto)
    if tipo_gasto_id:
        query = query.filter(model.Gasto.tipo_gasto_id == tipo_gasto_id)
    if fecha_desde:
        query = query.filter(model.Gasto.fecha >= fecha_desde)
    if fecha_hasta:
        query = query.filter(model.Gasto.fecha <= fecha_hasta)
    return query.order_by(model.Gasto.fecha.desc()).offset(skip).limit(limit).all()

def crear_gasto(db: Session, gasto: schemas.GastoCreate):
    db_gasto = model.Gasto(**gasto.model_dump())
    db.add(db_gasto)
    db.commit()
    db.refresh(db_gasto)
    return db_gasto

def actualizar_gasto(db: Session, gasto_id: int, gasto_update: schemas.GastoUpdate):
    db_gasto = obtener_gasto(db, gasto_id)
    if not db_gasto:
        return None
    data = gasto_update.model_dump(exclude_unset=True)
    for key, value in data.items():
        setattr(db_gasto, key, value)
    db.commit()
    db.refresh(db_gasto)
    return db_gasto

def eliminar_gasto(db: Session, gasto_id: int) -> bool:
    db_gasto = obtener_gasto(db, gasto_id)
    if not db_gasto:
        return False
    db.delete(db_gasto)
    db.commit()
    return True