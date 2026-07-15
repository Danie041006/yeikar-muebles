from sqlalchemy.orm import Session, joinedload
from sqlalchemy import or_
from decimal import Decimal
from datetime import datetime, date
from app.modules.production.model import OrdenProduccion, EtapaProduccion, ConsumoMaterial, ManoObra, CostoProduccion
from app.modules.production.schemas import (
    OrdenProduccionCreate, OrdenProduccionUpdate,
    EtapaProduccionCreate, EtapaProduccionUpdate,
    ConsumoMaterialCreate, ManoObraCreate, CostoProduccionCreate
)
from app.modules.orders.model import DetallePedido
from app.modules.orders.model import DetallePedido, Pedido
from app.modules.productos.model import Material
from app.modules.catalogos.model import Ubicacion
from app.modules.inventory.service import registrar_movimiento
from app.modules.inventory.schemas import MovimientoCreate
# ------------------------------------------------------------
# Servicios para Órdenes de Producción
# ------------------------------------------------------------
def obtener_orden_produccion(db: Session, id_orden: int):
    return db.query(OrdenProduccion).options(
        joinedload(OrdenProduccion.detalle_pedido).joinedload(DetallePedido.producto)
    ).filter(OrdenProduccion.id == id_orden).first()
def obtener_ordenes_produccion(db: Session, salto: int = 0, limite: int = 100, buscar: str = None):
    query = db.query(OrdenProduccion).options(
        joinedload(OrdenProduccion.detalle_pedido).joinedload(DetallePedido.producto)
    )
    if buscar:
        if buscar.isdigit():
            id_val = int(buscar)
            query = query.filter(
                or_(
                    OrdenProduccion.id == id_val,
                    OrdenProduccion.detalle_pedido_id == id_val,
                    OrdenProduccion.estado.ilike(f"%{buscar}%")
                )
            )
        else:
            query = query.filter(OrdenProduccion.estado.ilike(f"%{buscar}%"))
    return query.offset(salto).limit(limite).all()
def crear_orden_produccion(db: Session, esquema: OrdenProduccionCreate):
    db_orden = OrdenProduccion(
        detalle_pedido_id=esquema.detalle_pedido_id,
        estado=esquema.estado,
        fecha_inicio=esquema.fecha_inicio,
        fecha_fin=esquema.fecha_fin
    )
    db.add(db_orden)
    db.commit()
    db.refresh(db_orden)
    return db_orden
def crear_orden_desde_detalle_pedido(db: Session, detalle_pedido_id: int):
    # Verificar que el detalle del pedido exista
    detalle = db.query(DetallePedido).filter(DetallePedido.id == detalle_pedido_id).first()
    if not detalle:
        raise ValueError("El detalle de pedido especificado no existe.")
    
    # Verificar si ya existe una orden de producción para este detalle
    existente = db.query(OrdenProduccion).filter(OrdenProduccion.detalle_pedido_id == detalle_pedido_id).first()
    if existente:
        return existente
        
    db_orden = OrdenProduccion(
        detalle_pedido_id=detalle_pedido_id,
        estado="PENDIENTE",
        fecha_inicio=None,
        fecha_fin=None
    )
    db.add(db_orden)
    db.commit()
    db.refresh(db_orden)
    return db_orden
def actualizar_orden_produccion(db: Session, id_orden: int, esquema: OrdenProduccionUpdate):
    db_orden = obtener_orden_produccion(db, id_orden)
    if not db_orden:
        return None
    data = esquema.model_dump(exclude_unset=True)
    for clave, valor in data.items():
        setattr(db_orden, clave, valor)
    db.commit()
    db.refresh(db_orden)
    return db_orden
def cambiar_estado_orden_produccion(db: Session, id_orden: int, nuevo_estado: str):
    db_orden = obtener_orden_produccion(db, id_orden)
    if not db_orden:
        return None
    
    estados_validos = ['PENDIENTE', 'EN_PRODUCCION', 'PAUSADA', 'FINALIZADA', 'CANCELADA']
    if nuevo_estado not in estados_validos:
        raise ValueError(f"Estado de orden invalido. Debe ser uno de: {estados_validos}")
    
    db_orden.estado = nuevo_estado
    if nuevo_estado == 'EN_PRODUCCION' and not db_orden.fecha_inicio:
        db_orden.fecha_inicio = date.today()
    elif nuevo_estado == 'FINALIZADA':
        db_orden.fecha_fin = date.today()
        # Calcular y guardar costos al finalizar orden
        try:
            calcular_y_guardar_costo(db, id_orden)
        except Exception as e:
            # Imprimir error pero no bloquear la finalización
            print(f"Error al calcular costos automáticos al finalizar orden {id_orden}: {e}")
            
        # Sincronizar estado del Pedido a TERMINADO si todas sus órdenes de producción están en FINALIZADA
        try:
            detalle = db.query(DetallePedido).filter(DetallePedido.id == db_orden.detalle_pedido_id).first()
            if detalle:
                pedido = db.query(Pedido).filter(Pedido.id == detalle.pedido_id).first()
                if pedido:
                    # Cargar todas las órdenes de producción vinculadas a este pedido
                    detalles_ids = [d.id for d in pedido.detalles]
                    ordenes = db.query(OrdenProduccion).filter(OrdenProduccion.detalle_pedido_id.in_(detalles_ids)).all()
                    
                    # Verificar si todas están FINALIZADA
                    todas_finalizadas = all(o.estado == "FINALIZADA" for o in ordenes)
                    if todas_finalizadas:
                        pedido.estado = "TERMINADO"
                        # Generar envío automático
                        from app.modules.envios.service import crear_envio_automatico
                        crear_envio_automatico(db, pedido.id)
        except Exception as e:
            print(f"Error al verificar estado del pedido e iniciar envío para orden {id_orden}: {e}")
        
    db.commit()
    db.refresh(db_orden)
    return db_orden
def eliminar_orden_produccion(db: Session, id_orden: int):
    db_orden = obtener_orden_produccion(db, id_orden)
    if not db_orden:
        return False
    db.delete(db_orden)
    db.commit()
    return True
# ------------------------------------------------------------
# Servicios para Etapas de Producción
# ------------------------------------------------------------
def obtener_etapa_produccion(db: Session, id_etapa: int):
    return db.query(EtapaProduccion).filter(EtapaProduccion.id == id_etapa).first()
def crear_etapa_produccion(db: Session, esquema: EtapaProduccionCreate):
    db_etapa = EtapaProduccion(
        orden_produccion_id=esquema.orden_produccion_id,
        area_id=esquema.area_id,
        empleado_responsable_id=esquema.empleado_responsable_id,
        estado=esquema.estado,
        observaciones=esquema.observaciones,
        fecha_inicio=esquema.fecha_inicio,
        fecha_fin=esquema.fecha_fin
    )
    db.add(db_etapa)
    
    # Si la orden está en estado PENDIENTE, cambiarla a EN_PRODUCCION al crear su primera etapa
    orden = db.query(OrdenProduccion).filter(OrdenProduccion.id == esquema.orden_produccion_id).first()
    if orden and orden.estado == "PENDIENTE":
        orden.estado = "EN_PRODUCCION"
        if not orden.fecha_inicio:
            orden.fecha_inicio = date.today()
            
    db.commit()
    db.refresh(db_etapa)
    return db_etapa
def actualizar_etapa_produccion(db: Session, id_etapa: int, esquema: EtapaProduccionUpdate):
    db_etapa = obtener_etapa_produccion(db, id_etapa)
    if not db_etapa:
        return None
    data = esquema.model_dump(exclude_unset=True)
    for clave, valor in data.items():
        setattr(db_etapa, clave, valor)
    db.commit()
    db.refresh(db_etapa)
    return db_etapa
def cambiar_estado_etapa_produccion(db: Session, id_etapa: int, nuevo_estado: str):
    db_etapa = obtener_etapa_produccion(db, id_etapa)
    if not db_etapa:
        return None
    
    estados_validos = ['ASIGNADA', 'EN_PROCESO', 'PAUSADA', 'COMPLETADA']
    if nuevo_estado not in estados_validos:
        raise ValueError(f"Estado de etapa invalido. Debe ser uno de: {estados_validos}")
        
    db_etapa.estado = nuevo_estado
    if nuevo_estado == 'EN_PROCESO' and not db_etapa.fecha_inicio:
        db_etapa.fecha_inicio = datetime.now()
    elif nuevo_estado == 'COMPLETADA':
        db_etapa.fecha_fin = datetime.now()
        
    db.commit()
    db.refresh(db_etapa)
    return db_etapa
def eliminar_etapa_produccion(db: Session, id_etapa: int):
    db_etapa = obtener_etapa_produccion(db, id_etapa)
    if not db_etapa:
        return False
    db.delete(db_etapa)
    db.commit()
    return True
# ------------------------------------------------------------
# Servicios para Consumo de Material
# ------------------------------------------------------------
def obtener_consumo_material(db: Session, id_consumo: int):
    return db.query(ConsumoMaterial).filter(ConsumoMaterial.id == id_consumo).first()
def crear_consumo_material(db: Session, esquema: ConsumoMaterialCreate):
    # 1. Validar que la cantidad sea positiva
    if esquema.cantidad <= 0:
        raise ValueError("La cantidad debe ser mayor que cero")
    # 2. Obtener la ubicación del depósito principal (búsqueda dinámica)
    ubicacion = db.query(Ubicacion).filter(Ubicacion.nombre == "Depósito Principal").first()
    if not ubicacion:
        # Si no existe, usamos fallback
        ubicacion_id = 1
    else:
        ubicacion_id = ubicacion.id
    # 3. Obtener el costo unitario actual del material para congelarlo
    material = db.query(Material).filter(Material.id == esquema.material_id).first()
    if not material:
        raise ValueError("El material especificado no existe.")
    # 4. Crear el registro de consumo
    db_consumo = ConsumoMaterial(
        etapa_produccion_id=esquema.etapa_produccion_id,
        material_id=esquema.material_id,
        cantidad=esquema.cantidad,
        costo_unitario=material.costo_base,
        fecha=esquema.fecha,
        observaciones=esquema.observaciones
    )
    db.add(db_consumo)
    db.flush()  # para obtener db_consumo.id
    # 4. Registrar el movimiento de inventario (SALIDA)
    movimiento = MovimientoCreate(
        material_id=esquema.material_id,
        ubicacion_id=ubicacion_id,
        tipo="SALIDA",
        cantidad=Decimal(str(esquema.cantidad)),
        referencia_tipo="produccion",
        referencia_id=db_consumo.id,
        observaciones=f"Consumo en etapa {esquema.etapa_produccion_id}"
    )
    try:
        registrar_movimiento(db, movimiento)
    except ValueError as e:
        # Si falla (por ejemplo, stock insuficiente), se hace rollback
        db.rollback()
        raise ValueError(f"Error al descontar inventario: {e}")
    db.commit()
    db.refresh(db_consumo)
    return db_consumo
def eliminar_consumo_material(db: Session, id_consumo: int):
    db_consumo = obtener_consumo_material(db, id_consumo)
    if not db_consumo:
        return False
    db.delete(db_consumo)
    db.commit()
    return True
def obtener_consumos_por_orden(db: Session, orden_id: int):
    return db.query(ConsumoMaterial).join(EtapaProduccion).filter(EtapaProduccion.orden_produccion_id == orden_id).all()
# ------------------------------------------------------------
# Servicios para Mano de Obra
# ------------------------------------------------------------
def obtener_mano_obra(db: Session, id_mano_obra: int):
    return db.query(ManoObra).filter(ManoObra.id == id_mano_obra).first()
def crear_mano_obra(db: Session, esquema: ManoObraCreate):
    db_mano_obra = ManoObra(
        etapa_produccion_id=esquema.etapa_produccion_id,
        empleado_id=esquema.empleado_id,
        monto=esquema.monto,
        porcentaje_recargo=esquema.porcentaje_recargo,
        pagado=getattr(esquema, "pagado", False),
        observaciones=esquema.observaciones
    )
    db.add(db_mano_obra)
    db.commit()
    db.refresh(db_mano_obra)
    return db_mano_obra

def marcar_mano_obra_pagada(db: Session, mano_obra_id: int, pagado: bool = True):
    db_mano = obtener_mano_obra(db, mano_obra_id)
    if not db_mano:
        return None
    db_mano.pagado = pagado
    db.commit()
    db.refresh(db_mano)
    return db_mano
def eliminar_mano_obra(db: Session, id_mano_obra: int):
    db_mano = obtener_mano_obra(db, id_mano_obra)
    if not db_mano:
        return False
    db.delete(db_mano)
    db.commit()
    return True
# ------------------------------------------------------------
# Servicios para Costo de Producción (Lógica Financiera)
# ------------------------------------------------------------
def obtener_costo_por_orden(db: Session, orden_id: int):
    return db.query(CostoProduccion).filter(CostoProduccion.orden_produccion_id == orden_id).first()
def calcular_y_guardar_costo(db: Session, orden_id: int, ganancia_porcentaje: float = 0.0, costo_gastos: float = 0.0, precio_impuestos_base: float = 0.0):
    orden = db.query(OrdenProduccion).filter(OrdenProduccion.id == orden_id).first()
    if not orden:
        raise ValueError("La orden de produccion especificada no existe.")
    # Calcular costo de materiales
    consumos = obtener_consumos_por_orden(db, orden_id)
    costo_material = 0.0
    for c in consumos:
        costo_u = c.costo_unitario
        if costo_u is None:
            # Fallback a costo_base si no está congelado (para registros antiguos)
            material = db.query(Material).filter(Material.id == c.material_id).first()
            costo_u = material.costo_base if material else 0.0
        costo_material += float(c.cantidad) * float(costo_u)
    # Calcular costo de mano de obra
    mano_obras = db.query(ManoObra).join(EtapaProduccion).filter(EtapaProduccion.orden_produccion_id == orden_id).all()
    costo_mano_obra = 0.0
    for mo in mano_obras:
        recargo = float(mo.porcentaje_recargo) / 100.0 if mo.porcentaje_recargo else 0.0
        costo_mano_obra += float(mo.monto) * (1.0 + recargo)
    # Calcular costo total y precio de venta
    costo_total = costo_material + costo_mano_obra + float(costo_gastos)
    ganancia_factor = float(ganancia_porcentaje) / 100.0
    precio_venta_calculado = costo_total * (1.0 + ganancia_factor) + float(precio_impuestos_base)
    # Buscar o crear registro de CostoProduccion
    db_costo = obtener_costo_por_orden(db, orden_id)
    if not db_costo:
        db_costo = CostoProduccion(orden_produccion_id=orden_id)
        db.add(db_costo)
    db_costo.costo_material = costo_material
    db_costo.costo_mano_obra = costo_mano_obra
    db_costo.costo_gastos = costo_gastos
    db_costo.precio_impuestos_base = precio_impuestos_base
    db_costo.ganancia_porcentaje = ganancia_porcentaje
    db_costo.costo_total = costo_total
    db_costo.precio_venta_calculado = precio_venta_calculado
    db.commit()
    db.refresh(db_costo)
    return db_costo