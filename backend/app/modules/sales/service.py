from sqlalchemy.orm import Session
from sqlalchemy import or_, func
from datetime import date, datetime
from app.modules.sales.model import Venta, DetalleVenta, Pago
from app.modules.sales.schemas import VentaCreate, VentaUpdate, PagoCreate
from app.modules.orders.model import Pedido, DetallePedido
from app.modules.clients.model import Client
from app.modules.catalogos.model import Moneda

# ------------------------------------------------------------
# Servicios para Ventas (Facturas)
# ------------------------------------------------------------
def obtener_venta(db: Session, id_venta: int):
    return db.query(Venta).filter(Venta.id == id_venta).first()

def obtener_ventas(db: Session, salto: int = 0, limite: int = 100, buscar: str = None):
    query = db.query(Venta)
    if buscar:
        query = query.join(Client).filter(
            or_(
                Venta.estado.ilike(f"%{buscar}%"),
                Venta.observaciones.ilike(f"%{buscar}%"),
                Client.nombre.ilike(f"%{buscar}%")
            )
        )
    return query.offset(salto).limit(limite).all()

def crear_venta_desde_pedido(db: Session, esquema: VentaCreate):
    
    pedido = db.query(Pedido).filter(Pedido.id == esquema.pedido_id).first()
    if not pedido:
        raise ValueError("El pedido especificado no existe.")

    # 2. Validar estado del pedido
    estados_facturables = ["APROBADO", "PRODUCCION", "TERMINADO", "ENTREGADO"]
    if pedido.estado not in estados_facturables:
        raise ValueError(
            f"El pedido debe estar en estado {', '.join(estados_facturables)} para poder ser facturado. "
            f"Estado actual: {pedido.estado}"
        )

    # 3. Validar si ya existe una factura para este pedido
    venta_existente = db.query(Venta).filter(Venta.pedido_id == esquema.pedido_id).first()
    if venta_existente:
        raise ValueError("Ya existe una factura de venta para este pedido.")

    # 4. Crear cabecera de la venta
    db_venta = Venta(
        pedido_id=esquema.pedido_id,
        cliente_id=pedido.cliente_id,
        moneda_id=esquema.moneda_id,
        fecha=esquema.fecha or date.today(),
        total=0.0,
        estado="PENDIENTE",
        observaciones=esquema.observaciones
    )
    db.add(db_venta)
    db.flush()  # Para obtener db_venta.id

    # 5. Crear detalles de venta a partir de los detalles de pedido
    total = 0.0
    for dp in pedido.detalles:
        subtotal = float(dp.cantidad) * float(dp.precio)
        total += subtotal
        db_detalle = DetalleVenta(
            venta_id=db_venta.id,
            producto_id=dp.producto_id,
            cantidad=dp.cantidad,
            precio=dp.precio
        )
        db.add(db_detalle)

    # 6. Actualizar el total de la venta
    db_venta.total = total
    db.commit()
    db.refresh(db_venta)
    return db_venta

def actualizar_venta(db: Session, id_venta: int, esquema: VentaUpdate):
    db_venta = obtener_venta(db, id_venta)
    if not db_venta:
        return None
    data = esquema.model_dump(exclude_unset=True)
    for clave, valor in data.items():
        setattr(db_venta, clave, valor)
    db.commit()
    db.refresh(db_venta)
    return db_venta

def eliminar_venta(db: Session, id_venta: int):
    db_venta = obtener_venta(db, id_venta)
    if not db_venta:
        return False
    # La eliminacion en cascada eliminara detalle_venta, pero pago tiene ON DELETE RESTRICT
    # por lo que si hay pagos asociados, fallara a nivel de BD de forma segura.
    db.delete(db_venta)
    db.commit()
    return True


# ------------------------------------------------------------
# Servicios para Pagos (Abonos)
# ------------------------------------------------------------
def obtener_pago(db: Session, id_pago: int):
    return db.query(Pago).filter(Pago.id == id_pago).first()

def crear_pago(db: Session, esquema: PagoCreate):
    # 1. Obtener la venta
    venta = obtener_venta(db, esquema.venta_id)
    if not venta:
        raise ValueError("La venta especificada no existe.")

    # 2. Validar que la venta no este cancelada ni pagada
    if venta.estado == "CANCELADA":
        raise ValueError("No se pueden registrar pagos en una venta cancelada.")
    if venta.estado == "PAGADA":
        raise ValueError("La venta ya se encuentra totalmente pagada.")

    # 3. Validar coincidencia de monedas
    if esquema.moneda_id != venta.moneda_id:
        raise ValueError("La moneda del pago debe coincidir con la moneda de la factura.")

    # 4. Validar metodo de pago valido
    metodos_validos = ['EFECTIVO_COP', 'EFECTIVO_USD', 'EFECTIVO_VES', 'BANCOLOMBIA', 'BANCARIBE', 'ZELLE']
    if esquema.metodo_pago not in metodos_validos:
        raise ValueError(f"Metodo de pago invalido. Debe ser uno de: {metodos_validos}")

    # 5. Debemos comprobar que el dinero que se va a abonar no supere el saldo pendiente
    pagos_previos = db.query(Pago).filter(Pago.venta_id == venta.id).all()
    total_pagado = sum(float(p.monto) for p in pagos_previos)
    if total_pagado + float(esquema.monto) > float(venta.total):
        raise ValueError("El monto del pago excede el saldo pendiente de la factura. revisa de nuevo el monto que deseas registrar")
        
    



    # 6. Crear el pago
    db_pago = Pago(
        venta_id=esquema.venta_id,
        moneda_id=esquema.moneda_id,
        fecha=esquema.fecha,
        monto=esquema.monto,
        metodo_pago=esquema.metodo_pago,
        referencia=esquema.referencia,
        observaciones=esquema.observaciones
    )
    db.add(db_pago)
    db.flush()

    # 7. Recalcular estado de la venta
    pagos = db.query(Pago).filter(Pago.venta_id == venta.id).all()
    total_pagado = sum(float(p.monto) for p in pagos)
    total_venta = float(venta.total)

    if total_pagado >= total_venta:
        venta.estado = "PAGADA"
    elif total_pagado > 0.0:
        venta.estado = "ABONADA"
    else:
        venta.estado = "PENDIENTE"

    db.commit()
    db.refresh(db_pago)
    return db_pago


# ------------------------------------------------------------
# Reporte de Cuentas por Cobrar
# ------------------------------------------------------------
def obtener_cuentas_por_cobrar(db: Session):
    # Obtener todas las ventas pendientes o abonadas
    ventas = db.query(Venta).filter(
        Venta.estado.in_(["PENDIENTE", "ABONADA"])
    ).all()

    cuentas = []
    for v in ventas:
        pagos = db.query(Pago).filter(Pago.venta_id == v.id).all()
        total_pagado = sum(float(p.monto) for p in pagos)
        saldo_pendiente = float(v.total) - total_pagado

        if saldo_pendiente > 0.0:
            # Obtener nombre de cliente y codigo de moneda
            cliente_nombre = v.cliente.nombre if v.cliente else "Desconocido"
            moneda_codigo = v.moneda.codigo if v.moneda else "COP"

            cuentas.append({
                "venta_id": v.id,
                "cliente_nombre": cliente_nombre,
                "fecha": v.fecha,
                "total": float(v.total),
                "total_pagado": total_pagado,
                "saldo_pendiente": saldo_pendiente,
                "moneda_codigo": moneda_codigo
            })

    return cuentas
