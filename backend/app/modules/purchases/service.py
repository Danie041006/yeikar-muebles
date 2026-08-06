from sqlalchemy.orm import Session
from typing import List, Optional
from decimal import Decimal
from datetime import datetime

from app.modules.purchases import model, schemas
from app.modules.inventory import service as inventory_service, schemas as inventory_schemas
from app.modules.productos.model import Material


def _ubicacion_entrada(db: Session, preferida: Optional[int] = None) -> int:
    """Resuelve la ubicación destino de una entrada por compra.

    Usa la ubicación preferida si se indica; si no, busca el depósito principal
    (tipo DEPOSITO) con nombre que contenga 'PRINCIPAL'/'DEPOSITO', y cae a la
    primera ubicación activa. Nunca hardcodea a un id mágico.
    """
    from app.modules.catalogos.model import Ubicacion

    if preferida:
        ubi = db.query(Ubicacion).filter(Ubicacion.id == preferida, Ubicacion.activo == True).first()
        if ubi:
            return ubi.id

    ubi = db.query(Ubicacion).filter(
        Ubicacion.activo == True,
        Ubicacion.tipo == "DEPOSITO",
    ).order_by(Ubicacion.nombre).first()
    if ubi:
        return ubi.id

    ubi = db.query(Ubicacion).filter(Ubicacion.activo == True).order_by(Ubicacion.id).first()
    if ubi:
        return ubi.id
    raise ValueError("No hay ninguna ubicación activa. Crea una antes de recibir compras.")


def _actualizar_costo_promedio_material(
    db: Session,
    material_id: int,
    cantidad: Decimal,
    costo_unitario: Decimal,
    ubicacion_id: int,
) -> None:
    """
    Actualiza material.costo_base con el promedio ponderado tras una entrada.

    nuevo_costo = (stock_anterior * costo_anterior + cantidad * costo_nuevo)
                  / (stock_anterior + cantidad)

    Los pedidos/cotizaciones YA creados conservan su precio congelado
    (snapshot), así que solo impacta nuevas cotizaciones y nuevos pedidos.
    """
    material = db.query(Material).filter(Material.id == material_id).first()
    if not material:
        return

    from app.modules.inventory.model import Inventario
    inv = db.query(Inventario).filter(
        Inventario.material_id == material_id,
        Inventario.ubicacion_id == ubicacion_id,
    ).first()

    stock_anterior = inv.cantidad if inv else Decimal("0")
    costo_anterior = material.costo_base if material.costo_base is not None else Decimal("0")
    cantidad = Decimal(str(cantidad))
    costo_nuevo = Decimal(str(costo_unitario))

    total_stock = stock_anterior + cantidad
    if total_stock <= 0:
        material.costo_base = costo_nuevo
    else:
        material.costo_base = round(
            (stock_anterior * costo_anterior + cantidad * costo_nuevo) / total_stock, 2
        )


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
    from app.modules.tasas_cambio.service import obtener_tasa_moneda_a_cop
    tasa_cambio = obtener_tasa_moneda_a_cop(db, compra.moneda_id, compra.fecha)
    total_en_base = sum(
        float(d.cantidad) * float(d.costo_unitario) for d in compra.detalle
    ) * float(tasa_cambio)

    db_compra = model.Compra(
        proveedor_id=compra.proveedor_id,
        moneda_id=compra.moneda_id,
        fecha=compra.fecha,
        estado=compra.estado or "BORRADOR",
        tipo_pago=compra.tipo_pago or "CREDITO",
        tasa_cambio=tasa_cambio,
        total_en_moneda_base=round(total_en_base, 2),
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
        ubicacion_id = _ubicacion_entrada(db)
        for detalle in compra.detalle:
            movimiento = inventory_schemas.MovimientoCreate(
                material_id=detalle.material_id,
                ubicacion_id=ubicacion_id,
                tipo="ENTRADA",
                cantidad=detalle.cantidad,
                referencia_tipo="COMPRA",
                referencia_id=db_compra.id,
                observaciones="Entrada por compra",
            )
            inventory_service.registrar_movimiento(db, movimiento)
            # Actualizar costo promedio ponderado del material
            _actualizar_costo_promedio_material(
                db, detalle.material_id, detalle.cantidad, detalle.costo_unitario, ubicacion_id
            )

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
            ubicacion_id = _ubicacion_entrada(db)
            for detalle in db_compra.detalles:
                movimiento = inventory_schemas.MovimientoCreate(
                    material_id=detalle.material_id,
                    ubicacion_id=ubicacion_id,
                    tipo="ENTRADA",
                    cantidad=detalle.cantidad,
                    referencia_tipo="COMPRA",
                    referencia_id=db_compra.id,
                    observaciones="Entrada por compra (actualizada a recibida)",
                )
                inventory_service.registrar_movimiento(db, movimiento)
                _actualizar_costo_promedio_material(
                    db, detalle.material_id, detalle.cantidad, detalle.costo_unitario, ubicacion_id
                )

    # Revertir stock si la compra SALIÓ de RECIBIDA (CANCELADA, BORRADOR, EMITIDA).
    # La entrada de inventario solo tiene validez mientras la compra siga RECIBIDA.
    if viejo_estado == "RECIBIDA" and db_compra.estado != "RECIBIDA":
        from app.modules.inventory.model import MovimientoInventario
        movimientos = db.query(MovimientoInventario).filter(
            MovimientoInventario.referencia_tipo == "COMPRA",
            MovimientoInventario.referencia_id == db_compra.id
        ).all()
        for mov in movimientos:
            if mov.tipo == "ENTRADA":
                for detalle in db_compra.detalles:
                    if detalle.material_id == mov.material_id:
                        salida = inventory_schemas.MovimientoCreate(
                            material_id=mov.material_id,
                            ubicacion_id=mov.ubicacion_id,
                            tipo="SALIDA",
                            cantidad=mov.cantidad,
                            referencia_tipo="COMPRA",
                            referencia_id=db_compra.id,
                            observaciones=f"Reversa de entrada por compra ({db_compra.estado})",
                        )
                        inventory_service.registrar_movimiento(db, salida)

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
