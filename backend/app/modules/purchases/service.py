from sqlalchemy.orm import Session
from typing import List, Optional
from decimal import Decimal
from datetime import datetime

from app.modules.purchases import model, schemas
from app.modules.inventory import service as inventory_service, schemas as inventory_schemas


def obtener_compra(db: Session, compra_id: int) -> Optional[model.Compra]:
    return db.query(model.Compra).filter(model.Compra.id == compra_id).first()


def obtener_compras(
    db: Session,
    skip: int = 0,
    limit: int = 100,
    proveedor_id: Optional[int] = None,
    fecha_desde: Optional[datetime] = None,
    fecha_hasta: Optional[datetime] = None,
) -> List[model.Compra]:
    query = db.query(model.Compra)
    if proveedor_id:
        query = query.filter(model.Compra.proveedor_id == proveedor_id)
    if fecha_desde:
        query = query.filter(model.Compra.fecha >= fecha_desde)
    if fecha_hasta:
        query = query.filter(model.Compra.fecha <= fecha_hasta)
    return query.order_by(model.Compra.fecha.desc()).offset(skip).limit(limit).all()


def crear_compra(db: Session, compra: schemas.CompraCreate) -> model.Compra:
    # Crear registro de compra y sus detalles
    db_compra = model.Compra(
        proveedor_id=compra.proveedor_id,
        moneda_id=compra.moneda_id,
        fecha=compra.fecha,
        estado=compra.estado or "BORRADOR",
        observaciones=compra.observaciones,
    )
    db.add(db_compra)
    db.flush()  # asigna id antes de crear los movimientos

    # Para cada detalle, crear DetalleCompra
    for detalle in compra.detalle:
        db_detalle = model.DetalleCompra(
            compra_id=db_compra.id,
            material_id=detalle.material_id,
            cantidad=detalle.cantidad,
            costo_unitario=detalle.costo_unitario,
        )
        db.add(db_detalle)

    # Registrar movimiento de inventario (entrada) ÚNICAMENTE si está RECIBIDA
    if db_compra.estado == "RECIBIDA":
        for detalle in compra.detalle:
            movimiento = inventory_schemas.MovimientoCreate(
                material_id=detalle.material_id,
                ubicacion_id=1,  # Depósito principal
                tipo="ENTRADA",
                cantidad=detalle.cantidad,
                referencia_tipo="COMPRA",
                referencia_id=db_compra.id,
                observaciones="Entrada por compra",
            )
            inventory_service.registrar_movimiento(db, movimiento)

    db.commit()
    db.refresh(db_compra)
    return db_compra


def actualizar_compra(db: Session, compra_id: int, compra_update: schemas.CompraBase) -> Optional[model.Compra]:
    db_compra = obtener_compra(db, compra_id)
    if not db_compra:
        return None
        
    viejo_estado = db_compra.estado
    for attr, value in compra_update.model_dump(exclude_unset=True).items():
        setattr(db_compra, attr, value)
        
    # Registrar movimiento de inventario (entrada) si transiciona a RECIBIDA y no existía previo
    if viejo_estado != "RECIBIDA" and db_compra.estado == "RECIBIDA":
        from app.modules.inventory.model import MovimientoInventario
        existe_mov = db.query(MovimientoInventario).filter(
            MovimientoInventario.referencia_tipo == "COMPRA",
            MovimientoInventario.referencia_id == db_compra.id
        ).first()
        
        if not existe_mov:
            for detalle in db_compra.detalles:
                movimiento = inventory_schemas.MovimientoCreate(
                    material_id=detalle.material_id,
                    ubicacion_id=1,  # Depósito principal
                    tipo="ENTRADA",
                    cantidad=detalle.cantidad,
                    referencia_tipo="COMPRA",
                    referencia_id=db_compra.id,
                    observaciones="Entrada por compra (actualizada a recibida)",
                )
                inventory_service.registrar_movimiento(db, movimiento)
                
    db.commit()
    db.refresh(db_compra)
    return db_compra


def eliminar_compra(db: Session, compra_id: int) -> bool:
    db_compra = obtener_compra(db, compra_id)
    if not db_compra:
        return False
    db.delete(db_compra)
    db.commit()
    return True
