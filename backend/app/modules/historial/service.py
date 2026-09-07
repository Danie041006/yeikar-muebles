"""
historial/service.py — Expediente digital: la cadena completa de un negocio.

Une la información dispersa en los módulos en una sola ficha:
cotización → pedido → producción (etapas/áreas, consumos, mano de obra, costo)
→ venta y pagos (ingresos) → gastos (egresos) → factura fiscal → despacho,
más la auditoría de cambios (solo administradores).

Módulo de SOLO LECTURA: no crea ni modifica datos.
"""
from datetime import date, datetime

from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload

from app.modules.adjuntos.service import adjuntos_info
from app.modules.auditoria.model import AuditEvent
from app.modules.clients.model import Client
from app.modules.envios.model import Envio, EnvioAsignacion, EnvioUbicacion
from app.modules.facturacion.model import DetalleFactura, Factura
from app.modules.gastos.model import Gasto
from app.modules.orders.model import DetallePedido, Pedido
from app.modules.production.model import (
    ConsumoMaterial,
    CostoProduccion,
    EtapaAsignadoAdicional,
    EtapaProduccion,
    ManoObra,
    OrdenProduccion,
)
from app.modules.quotes.model import Cotizacion, DetalleCotizacion
from app.modules.reports.model import MetodoCaja, MovimientoCaja
from app.modules.sales.model import DetalleVenta, Pago, Venta


# ---------------------------------------------------------------------------
# Serialización de valores
# ---------------------------------------------------------------------------
def _f(v):
    return float(v) if v is not None else None


def _d(v):
    return v.isoformat() if isinstance(v, (date, datetime)) else v


def _dt(v):
    return v.isoformat() if isinstance(v, datetime) else _d(v)


def _nombre_usuario(u):
    return (u.nombre or u.nombre_usuario) if u else None


def _nombre_item(det):
    """Nombre visible de un renglón: producto (FABRICADO/REVENTA) o material
    (INSUMO vendido suelto, producto_id NULL). None si no hay ninguno."""
    if det.producto is not None and det.producto.nombre:
        return det.producto.nombre
    material = getattr(det, "material", None)
    if material is not None and material.nombre:
        return material.nombre
    return None


# ---------------------------------------------------------------------------
# Cadena completa de un pedido
# ---------------------------------------------------------------------------
def cadena_expediente(db: Session, pedido_id: int, incluir_auditoria: bool = False) -> dict:
    pedido = (
        db.query(Pedido)
        .options(
            joinedload(Pedido.cliente),
            joinedload(Pedido.creador),
            joinedload(Pedido.cotizacion).joinedload(Cotizacion.detalles).joinedload(DetalleCotizacion.producto),
            joinedload(Pedido.cotizacion).joinedload(Cotizacion.detalles).joinedload(DetalleCotizacion.material),
            joinedload(Pedido.cotizacion).joinedload(Cotizacion.moneda),
            joinedload(Pedido.cotizacion).joinedload(Cotizacion.creador),
            joinedload(Pedido.detalles).joinedload(DetallePedido.producto),
            joinedload(Pedido.detalles).joinedload(DetallePedido.material),
        )
        .filter(Pedido.id == pedido_id)
        .first()
    )
    if not pedido:
        return None

    cotizacion = pedido.cotizacion
    detalles_pedido = _produccion_por_detalle(db, pedido)
    venta = _venta_y_pagos(db, pedido.id)
    facturas = _facturas(db, pedido.id)
    envio = _envio(db, pedido.id)
    gastos = _gastos_del_pedido(db, detalles_pedido)

    entidades_auditoria = {
        "cotizacion": [cotizacion.id] if cotizacion else [],
        "pedido": [pedido.id],
        "orden_produccion": [o["produccion"]["orden"]["id"] for o in detalles_pedido if o.get("produccion") and o["produccion"].get("orden")],
        "consumo_material": [
            c["id"] for o in detalles_pedido
            for e in (o.get("produccion") or {}).get("etapas", [])
            for c in e.get("consumos", [])
        ],
        "mano_obra": [
            m["id"] for o in detalles_pedido
            for e in (o.get("produccion") or {}).get("etapas", [])
            for m in e.get("mano_obra", [])
        ],
        "venta": [venta["id"]] if venta else [],
        "pago": [p["id"] for p in (venta.get("pagos") or [])] if venta else [],
        "envio": [envio["id"]] if envio else [],
        "factura": [f["id"] for f in facturas],
    }
    auditoria = _auditoria(db, entidades_auditoria) if incluir_auditoria else []

    return {
        "cliente": _serializar_cliente(pedido.cliente),
        "cotizacion": _serializar_cotizacion(db, cotizacion) if cotizacion else None,
        "pedido": _serializar_pedido(pedido),
        "detalles_pedido": detalles_pedido,
        "venta": venta,
        "gastos": gastos,
        "facturas": facturas,
        "envio": envio,
        "auditoria": auditoria,
    }


def _produccion_por_detalle(db: Session, pedido: Pedido) -> list[dict]:
    """Por cada detalle del pedido: su orden de producción con etapas,
    consumos, mano de obra y costo."""
    detalle_ids = [d.id for d in pedido.detalles]
    resultado = []
    if not detalle_ids:
        return resultado

    ordenes = (
        db.query(OrdenProduccion)
        .options(
            joinedload(OrdenProduccion.creador),
            joinedload(OrdenProduccion.costo),
            joinedload(OrdenProduccion.etapas).joinedload(EtapaProduccion.area),
            joinedload(OrdenProduccion.etapas).joinedload(EtapaProduccion.empleado_responsable),
            joinedload(OrdenProduccion.etapas).joinedload(EtapaProduccion.consumos).joinedload(ConsumoMaterial.material),
            joinedload(OrdenProduccion.etapas).joinedload(EtapaProduccion.consumos).joinedload(ConsumoMaterial.creador),
            joinedload(OrdenProduccion.etapas).joinedload(EtapaProduccion.mano_obras).joinedload(ManoObra.empleado),
            joinedload(OrdenProduccion.etapas).joinedload(EtapaProduccion.asignados_adicionales).joinedload(EtapaAsignadoAdicional.empleado),
        )
        .filter(OrdenProduccion.detalle_pedido_id.in_(detalle_ids))
        .all()
    )
    ordenes_por_detalle = {o.detalle_pedido_id: o for o in ordenes}

    for det in pedido.detalles:
        item = {
            "id": det.id,
            "producto_id": det.producto_id,
            "material_id": det.material_id,
            "tipo_item": det.tipo_item,
            "producto_nombre": _nombre_item(det),
            "cantidad": _f(det.cantidad),
            "precio": _f(det.precio),
            "costo_unitario": _f(det.costo_unitario),
            "porcentaje_ganancia": _f(det.porcentaje_ganancia),
            "dimensiones": {
                "alto": _f(det.alto),
                "ancho": _f(det.ancho),
                "largo": _f(det.largo),
            },
            "color": det.color,
            "acabado": det.acabado,
            "descripcion_especifica": det.descripcion_especifica,
            "observaciones": det.observaciones,
            "produccion": None,
        }
        orden = ordenes_por_detalle.get(det.id)
        if orden:
            item["produccion"] = {
                "orden": {
                    "id": orden.id,
                    "estado": orden.estado,
                    "fecha_inicio": _d(orden.fecha_inicio),
                    "fecha_fin": _d(orden.fecha_fin),
                    "creado_por": _nombre_usuario(orden.creador),
                },
                "etapas": [
                    {
                        "id": et.id,
                        "area_id": et.area_id,
                        "area_nombre": et.area.nombre if et.area else None,
                        "empleado_responsable": et.empleado_responsable.nombre if et.empleado_responsable else None,
                        "empleados_adicionales": [a.empleado.nombre for a in et.asignados_adicionales if a.empleado],
                        "estado": et.estado,
                        "fecha_inicio": _dt(et.fecha_inicio),
                        "fecha_fin": _dt(et.fecha_fin),
                        "es_retrabajo": bool(et.es_retrabajo),
                        "observaciones": et.observaciones,
                        "consumos": [
                            {
                                "id": c.id,
                                "material_id": c.material_id,
                                "material_nombre": c.material.nombre if c.material else None,
                                "cantidad": _f(c.cantidad),
                                "costo_unitario": _f(c.costo_unitario),
                                "seccion": c.seccion,
                                "fecha": _dt(c.fecha),
                                "creado_por": _nombre_usuario(c.creador),
                                "observaciones": c.observaciones,
                            }
                            for c in et.consumos
                        ],
                        "mano_obra": [
                            {
                                "id": m.id,
                                "empleado_nombre": m.empleado.nombre if m.empleado else None,
                                "monto": _f(m.monto),
                                "porcentaje_recargo": _f(m.porcentaje_recargo),
                                "pagado": bool(m.pagado),
                                "observaciones": m.observaciones,
                            }
                            for m in et.mano_obras
                        ],
                    }
                    for et in orden.etapas
                ],
                "costo": _serializar_costo(orden.costo) if orden.costo else None,
            }
        resultado.append(item)
    return resultado


def _serializar_costo(costo: CostoProduccion) -> dict:
    return {
        "costo_material": _f(costo.costo_material),
        "costo_mano_obra": _f(costo.costo_mano_obra),
        "costo_gastos": _f(costo.costo_gastos),
        "precio_impuestos_base": _f(costo.precio_impuestos_base),
        "ganancia_porcentaje": _f(costo.ganancia_porcentaje),
        "precio_venta_calculado": _f(costo.precio_venta_calculado),
        "costo_total": _f(costo.costo_total),
    }


def _venta_y_pagos(db: Session, pedido_id: int) -> dict | None:
    venta = (
        db.query(Venta)
        .options(
            joinedload(Venta.moneda),
            joinedload(Venta.creador),
            joinedload(Venta.detalles).joinedload(DetalleVenta.producto),
            joinedload(Venta.detalles).joinedload(DetalleVenta.material),
            joinedload(Venta.pagos).joinedload(Pago.moneda),
        )
        .filter(Venta.pedido_id == pedido_id)
        .first()
    )
    if not venta:
        return None

    pago_ids = [p.id for p in venta.pagos]
    movimientos: dict[int, dict] = {}
    if pago_ids:
        filas = (
            db.query(MovimientoCaja, MetodoCaja)
            .join(MetodoCaja, MetodoCaja.id == MovimientoCaja.metodo_caja_id)
            .filter(MovimientoCaja.pago_id.in_(pago_ids))
            .all()
        )
        movimientos = {
            mc.pago_id: {
                "cuenta": mca.nombre,
                "tipo": mc.tipo,
                "monto_en_moneda_base": _f(mc.monto_en_moneda_base),
                "responsable": _nombre_usuario(mc.usuario) if mc.usuario else None,
                "referencia": mc.referencia,
            }
            for mc, mca in filas
        }

    from app.modules.adjuntos.service import adjuntos_info

    pagos = []
    for p in venta.pagos:
        pagos.append({
            "id": p.id,
            "fecha": _dt(p.fecha),
            "moneda": p.moneda.codigo if p.moneda else None,
            "monto": _f(p.monto),
            "tasa_cambio": _f(p.tasa_cambio),
            "monto_en_moneda_base": _f(p.monto_en_moneda_base),
            "metodo_pago": p.metodo_pago,
            "referencia": p.referencia,
            "observaciones": p.observaciones,
            "recibos": adjuntos_info(db, "PAGO", p.id),
            "caja": movimientos.get(p.id),
        })

    total_pagado = sum(float(p.monto_en_moneda_base) for p in venta.pagos)
    return {
        "id": venta.id,
        "fecha": _d(venta.fecha),
        "estado": venta.estado,
        "moneda": venta.moneda.codigo if venta.moneda else None,
        "total": _f(venta.total),
        "tasa_cambio": _f(venta.tasa_cambio),
        "total_en_moneda_base": _f(venta.total_en_moneda_base),
        "creado_por": _nombre_usuario(venta.creador),
        "observaciones": venta.observaciones,
        "total_pagado": total_pagado,
        "saldo_pendiente": float(venta.total) - total_pagado,
        "detalles": [
            {
                "producto_id": d.producto_id,
                "material_id": d.material_id,
                "tipo_item": d.tipo_item,
                "producto_nombre": _nombre_item(d),
                "cantidad": _f(d.cantidad),
                "precio": _f(d.precio),
                "costo_unitario": _f(d.costo_unitario),
                "porcentaje_ganancia": _f(d.porcentaje_ganancia),
                "utilidad": _f(d.utilidad),
                "descuento": _f(d.descuento),
            }
            for d in venta.detalles
        ],
        "pagos": pagos,
    }


def _gastos_del_pedido(db: Session, detalles_pedido: list[dict]) -> list[dict]:
    """Egresos generados por los consumos de producción del pedido
    (marcador '[consumo {id}]' en observaciones)."""
    consumo_ids = [
        c["id"]
        for o in detalles_pedido
        if o.get("produccion")
        for e in o["produccion"].get("etapas", [])
        for c in e.get("consumos", [])
    ]
    if not consumo_ids:
        return []
    condiciones = or_(*[Gasto.observaciones.ilike(f"%[consumo {cid}]%") for cid in consumo_ids])
    gastos = (
        db.query(Gasto)
        .options(joinedload(Gasto.moneda), joinedload(Gasto.area), joinedload(Gasto.creador))
        .filter(condiciones)
        .order_by(Gasto.fecha.desc())
        .all()
    )
    return [
        {
            "id": g.id,
            "fecha": _d(g.fecha),
            "descripcion": g.descripcion,
            "monto": _f(g.monto),
            "moneda": g.moneda.codigo if g.moneda else None,
            "monto_en_moneda_base": _f(g.monto_en_moneda_base),
            "area": g.area.nombre if g.area else None,
            "creado_por": _nombre_usuario(g.creador),
            "observaciones": g.observaciones,
        }
        for g in gastos
    ]


def _facturas(db: Session, pedido_id: int) -> list[dict]:
    facturas = (
        db.query(Factura)
        .options(
            joinedload(Factura.creador),
            joinedload(Factura.detalles).joinedload(DetalleFactura.producto),
            joinedload(Factura.detalles).joinedload(DetalleFactura.material),
        )
        .filter(Factura.pedido_id == pedido_id)
        .order_by(Factura.id.desc())
        .all()
    )
    return [
        {
            "id": f.id,
            "fecha_emision": _d(f.fecha_emision),
            "estado": f.estado,
            "total_usd": _f(f.total_usd),
            "tasa_usd_ves": _f(f.tasa_usd_ves),
            "base_imponible_bs": _f(f.base_imponible_bs),
            "iva_bs": _f(f.iva_bs),
            "igtf_bs": _f(f.igtf_bs),
            "total_bs": _f(f.total_bs),
            "creado_por": _nombre_usuario(f.creador),
            "observaciones": f.observaciones,
            "detalles": [
                {
                    "producto_id": d.producto_id,
                    "material_id": d.material_id,
                    "tipo_item": d.tipo_item,
                    "producto_nombre": d.descripcion or _nombre_item(d),
                    "descripcion": d.descripcion,
                    "cantidad": _f(d.cantidad),
                    "precio_usd": _f(d.precio_usd),
                    "subtotal_usd": _f(d.subtotal_usd),
                    "subtotal_bs": _f(d.subtotal_bs),
                }
                for d in f.detalles
            ],
        }
        for f in facturas
    ]


def _envio(db: Session, pedido_id: int) -> dict | None:
    envio = (
        db.query(Envio)
        .options(
            joinedload(Envio.empleado),
            joinedload(Envio.creador),
            joinedload(Envio.asignado_por),
            joinedload(Envio.ubicaciones),
            joinedload(Envio.asignaciones).joinedload(EnvioAsignacion.empleado),
        )
        .filter(Envio.pedido_id == pedido_id)
        .first()
    )
    if not envio:
        return None
    return {
        "id": envio.id,
        "estado": envio.estado,
        "guia_despacho": envio.guia_despacho,
        "chofer": envio.empleado.nombre if envio.empleado else None,
        "asignado_por": _nombre_usuario(envio.asignado_por),
        "creado_por": _nombre_usuario(envio.creador),
        "fecha_salida": _dt(envio.fecha_salida),
        "fecha_entrega": _dt(envio.fecha_entrega),
        "direccion_entrega": envio.direccion_entrega,
        "observaciones": envio.observaciones,
        "asignaciones": [
            {
                "empleado": a.empleado.nombre if a.empleado else None,
                "asignado_por": _nombre_usuario(a.asignado_por),
                "asignado_en": _dt(a.asignado_en),
                "desasignado_en": _dt(a.desasignado_en),
                "motivo": a.motivo,
            }
            for a in envio.asignaciones
        ],
        "ubicaciones": [
            {
                "latitud": _f(u.latitud),
                "longitud": _f(u.longitud),
                "capturada_en": _dt(u.capturada_en),
                "reportado_por": _nombre_usuario(u.reportado_por),
                "fuente": u.fuente,
            }
            for u in envio.ubicaciones
        ],
    }


def _auditoria(db: Session, entidades: dict[str, list[int]]) -> list[dict]:
    """Eventos de auditoría de las entidades de la cadena (quién cambió qué)."""
    eventos = []
    for entidad, ids in entidades.items():
        if not ids:
            continue
        filas = (
            db.query(AuditEvent)
            .options(joinedload(AuditEvent.actor))
            .filter(AuditEvent.entity_type == entidad, AuditEvent.entity_id.in_([str(i) for i in ids]))
            .order_by(AuditEvent.created_at.asc())
            .all()
        )
        eventos.extend(filas)
    eventos.sort(key=lambda e: e.created_at)
    return [
        {
            "fecha": _dt(e.created_at),
            "accion": e.action,
            "entidad": e.entity_type,
            "entidad_id": e.entity_id,
            "actor": _nombre_usuario(e.actor),
            "cambios": e.changed_fields,
        }
        for e in eventos
    ]


# ---------------------------------------------------------------------------
# Serialización de las entidades raíz
# ---------------------------------------------------------------------------
def _serializar_cliente(cliente: Client) -> dict:
    return {
        "id": cliente.id,
        "nombre": cliente.nombre,
        "cedula": cliente.cedula,
        "telefono": cliente.telefono,
        "direccion": cliente.direccion,
        "ciudad": cliente.ciudad,
        "estado": cliente.estado,
        "observaciones": cliente.observaciones,
        "fecha_registro": _d(cliente.fecha_registro),
    }


def _serializar_cotizacion(db: Session, cotizacion: Cotizacion) -> dict:
    return {
        "id": cotizacion.id,
        "fecha": _d(cotizacion.fecha),
        "estado": cotizacion.estado,
        "total_estimado": _f(cotizacion.total_estimado),
        "moneda": cotizacion.moneda.codigo if cotizacion.moneda else None,
        "tasa_cambio": _f(cotizacion.tasa_cambio),
        "total_en_moneda_base": _f(cotizacion.total_en_moneda_base),
        "observaciones": cotizacion.observaciones,
        "creado_por": _nombre_usuario(cotizacion.creador),
        "created_at": _dt(cotizacion.created_at),
        "detalles": [
            {
                "producto_id": d.producto_id,
                "material_id": d.material_id,
                "tipo_item": d.tipo_item,
                "producto_nombre": _nombre_item(d),
                "cantidad": _f(d.cantidad),
                "precio": _f(d.precio),
                "dimensiones": {
                    "alto": _f(d.alto),
                    "ancho": _f(d.ancho),
                    "largo": _f(d.largo),
                },
                "costo_materiales": _f(d.costo_materiales),
                "costo_mano_obra": _f(d.costo_mano_obra),
                "costo_gastos": _f(d.costo_gastos),
                "costo_total": _f(d.costo_total),
                "observaciones": d.observaciones,
                "receta_personalizada": d.receta_personalizada,
                # Fotos de referencia del mueble (mismas que salen en el PDF de cotización)
                "fotos": adjuntos_info(db, "PRODUCTO", d.producto_id),
            }
            for d in cotizacion.detalles
        ],
    }


def _serializar_pedido(pedido: Pedido) -> dict:
    return {
        "id": pedido.id,
        "fecha": _d(pedido.fecha),
        "estado": pedido.estado,
        "fecha_entrega_estimada": _d(pedido.fecha_entrega_estimada),
        "observaciones": pedido.observaciones,
        "creado_por": _nombre_usuario(pedido.creador),
        "cotizacion_id": pedido.cotizacion_id,
        "created_at": _dt(pedido.created_at),
    }


# ---------------------------------------------------------------------------
# Fichas por entidad de entrada
# ---------------------------------------------------------------------------
def expediente_cotizacion(db: Session, cotizacion_id: int, incluir_auditoria: bool = False) -> dict | None:
    cotizacion = (
        db.query(Cotizacion)
        .options(
            joinedload(Cotizacion.cliente),
            joinedload(Cotizacion.moneda),
            joinedload(Cotizacion.creador),
            joinedload(Cotizacion.detalles).joinedload(DetalleCotizacion.producto),
            joinedload(Cotizacion.detalles).joinedload(DetalleCotizacion.material),
        )
        .filter(Cotizacion.id == cotizacion_id)
        .first()
    )
    if not cotizacion:
        return None
    pedido = db.query(Pedido).filter(Pedido.cotizacion_id == cotizacion.id).first()
    ficha = {
        "cliente": _serializar_cliente(cotizacion.cliente),
        "cotizacion": _serializar_cotizacion(db, cotizacion),
        "pedido": None,
        "detalles_pedido": [],
        "venta": None,
        "gastos": [],
        "facturas": [],
        "envio": None,
        "auditoria": [],
    }
    if pedido:
        ficha.update(cadena_expediente(db, pedido.id, incluir_auditoria=incluir_auditoria))
    return ficha


def expediente_factura(db: Session, factura_id: int, incluir_auditoria: bool = False) -> dict | None:
    factura = (
        db.query(Factura)
        .options(joinedload(Factura.creador), joinedload(Factura.pedido))
        .filter(Factura.id == factura_id)
        .first()
    )
    if not factura:
        return None
    ficha = cadena_expediente(db, factura.pedido_id, incluir_auditoria=incluir_auditoria)
    if ficha is None:
        return None
    ficha["factura_entrada"] = {
        "id": factura.id,
        "fecha_emision": _d(factura.fecha_emision),
        "estado": factura.estado,
        "total_usd": _f(factura.total_usd),
        "total_bs": _f(factura.total_bs),
        "creado_por": _nombre_usuario(factura.creador),
    }
    return ficha


def expediente_envio(db: Session, envio_id: int, incluir_auditoria: bool = False) -> dict | None:
    envio = (
        db.query(Envio)
        .options(joinedload(Envio.pedido))
        .filter(Envio.id == envio_id)
        .first()
    )
    if not envio:
        return None
    ficha = cadena_expediente(db, envio.pedido_id, incluir_auditoria=incluir_auditoria)
    if ficha is None:
        return None
    ficha["envio_entrada"] = {
        "id": envio.id,
        "estado": envio.estado,
        "guia_despacho": envio.guia_despacho,
        "fecha_salida": _dt(envio.fecha_salida),
        "fecha_entrega": _dt(envio.fecha_entrega),
    }
    return ficha


# ---------------------------------------------------------------------------
# Resumen de un cliente (todas sus operaciones)
# ---------------------------------------------------------------------------
def expediente_cliente(db: Session, cliente_id: int) -> dict | None:
    cliente = db.query(Client).filter(Client.id == cliente_id).first()
    if not cliente:
        return None

    cotizaciones = (
        db.query(Cotizacion)
        .options(joinedload(Cotizacion.moneda))
        .filter(Cotizacion.cliente_id == cliente_id)
        .order_by(Cotizacion.fecha.desc(), Cotizacion.id.desc())
        .limit(200)
        .all()
    )
    pedidos = db.query(Pedido).filter(Pedido.cliente_id == cliente_id).order_by(Pedido.fecha.desc(), Pedido.id.desc()).limit(200).all()
    ventas = (
        db.query(Venta)
        .options(joinedload(Venta.moneda), joinedload(Venta.pagos))
        .filter(Venta.cliente_id == cliente_id)
        .order_by(Venta.fecha.desc(), Venta.id.desc())
        .limit(200)
        .all()
    )
    facturas = (
        db.query(Factura)
        .filter(Factura.cliente_id == cliente_id)
        .order_by(Factura.fecha_emision.desc(), Factura.id.desc())
        .limit(200)
        .all()
    )
    envios = (
        db.query(Envio)
        .filter(Envio.pedido_id.in_([p.id for p in pedidos]))
        .order_by(Envio.created_at.desc())
        .limit(200)
        .all()
    ) if pedidos else []

    return {
        "cliente": _serializar_cliente(cliente),
        "resumen": {
            "cotizaciones": [
                {"id": c.id, "fecha": _d(c.fecha), "estado": c.estado, "total_estimado": _f(c.total_estimado), "moneda": c.moneda.codigo if c.moneda else None}
                for c in cotizaciones
            ],
            "pedidos": [
                {"id": p.id, "fecha": _d(p.fecha), "estado": p.estado, "cotizacion_id": p.cotizacion_id}
                for p in pedidos
            ],
            "ventas": [
                {
                    "id": v.id,
                    "fecha": _d(v.fecha),
                    "estado": v.estado,
                    "moneda": v.moneda.codigo if v.moneda else None,
                    "total": _f(v.total),
                    "total_pagado": sum(float(p.monto_en_moneda_base) for p in v.pagos),
                }
                for v in ventas
            ],
            "facturas": [
                {"id": f.id, "fecha_emision": _d(f.fecha_emision), "estado": f.estado, "total_bs": _f(f.total_bs)}
                for f in facturas
            ],
            "envios": [
                {"id": e.id, "estado": e.estado, "guia_despacho": e.guia_despacho, "fecha_salida": _dt(e.fecha_salida)}
                for e in envios
            ],
        },
    }