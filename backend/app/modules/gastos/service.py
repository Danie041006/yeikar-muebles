from sqlalchemy.orm import Session, joinedload
from typing import List, Optional
from datetime import date
from decimal import Decimal
from app.modules.gastos import model, schemas
from app.modules.catalogos.model import TipoGasto

def obtener_gasto(db: Session, gasto_id: int):
    return db.query(model.Gasto).options(
        joinedload(model.Gasto.tipo_gasto),
        joinedload(model.Gasto.moneda)
    ).filter(model.Gasto.id == gasto_id).first()

def obtener_gastos(
    db: Session,
    skip: int = 0,
    limit: int = 100,
    tipo_gasto_id: Optional[int] = None,
    categoria: Optional[str] = None,
    fecha_desde: Optional[date] = None,
    fecha_hasta: Optional[date] = None
) -> List[model.Gasto]:
    query = db.query(model.Gasto).options(
        joinedload(model.Gasto.tipo_gasto),
        joinedload(model.Gasto.moneda)
    )
    if tipo_gasto_id:
        query = query.filter(model.Gasto.tipo_gasto_id == tipo_gasto_id)
    if categoria:
        query = query.join(model.Gasto.tipo_gasto).filter(TipoGasto.categoria == categoria.upper())
    if fecha_desde:
        query = query.filter(model.Gasto.fecha >= fecha_desde)
    if fecha_hasta:
        query = query.filter(model.Gasto.fecha <= fecha_hasta)
    return query.order_by(model.Gasto.fecha.desc()).offset(skip).limit(limit).all()

def crear_gasto(db: Session, gasto: schemas.GastoCreate):
    es_cop = gasto.moneda_id == 1
    monto_en_moneda_base = gasto.monto if es_cop else (gasto.monto * gasto.tasa_cambio)

    db_gasto = model.Gasto(
        tipo_gasto_id=gasto.tipo_gasto_id,
        moneda_id=gasto.moneda_id,
        fecha=gasto.fecha,
        descripcion=gasto.descripcion,
        monto=gasto.monto,
        tasa_cambio=gasto.tasa_cambio,
        monto_en_moneda_base=monto_en_moneda_base,
        observaciones=gasto.observaciones,
    )
    db.add(db_gasto)
    db.commit()
    db.refresh(db_gasto)
    return db_gasto

def actualizar_gasto(db: Session, gasto_id: int, gasto_update: schemas.GastoUpdate):
    db_gasto = obtener_gasto(db, gasto_id)
    if not db_gasto:
        return None
    data = gasto_update.model_dump(exclude_unset=True)

    if "monto" in data or "tasa_cambio" in data or "moneda_id" in data:
        monto = data.get("monto", db_gasto.monto)
        tasa_cambio = data.get("tasa_cambio", db_gasto.tasa_cambio)
        moneda_id = data.get("moneda_id", db_gasto.moneda_id)
        es_cop = moneda_id == 1
        data["monto_en_moneda_base"] = monto if es_cop else (monto * tasa_cambio)

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