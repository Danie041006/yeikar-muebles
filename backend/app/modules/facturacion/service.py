from sqlalchemy.orm import Session
from datetime import date
from typing import Dict, List, Optional

from app.modules.facturacion.model import Factura, DetalleFactura, TasaImpuesto
from app.modules.facturacion.schemas import FacturaCreate, TasaImpuestoUpdate
from app.modules.orders.model import Pedido
from app.modules.sales.model import Venta
from app.modules.auditoria.service import record_event
from app.modules.users.deps import es_admin_user, filtrar_registros_propios
from app.modules.users.model import Usuario


class FacturaNoAutorizadaError(Exception):
    """Facturación con saldo pendiente: solo autorizada por Dueño/Administrador."""


# ------------------------------------------------------------
# Motor de impuestos (único punto de cambio para tasas/lógica)
# ------------------------------------------------------------
def calcular_impuestos(base_imponible_bs: float, tasa_iva: float, tasa_igtf: float):
    """Desglose fiscal de la factura SENIAT.

    IVA sobre la base imponible; IGTF sobre el total con IVA (tal como se
    venía imprimiendo). Las tasas llegan en porcentaje (16.0 = 16%).
    """
    iva_bs = round(base_imponible_bs * (tasa_iva / 100.0), 2)
    total_con_iva_bs = round(base_imponible_bs + iva_bs, 2)
    igtf_bs = round(total_con_iva_bs * (tasa_igtf / 100.0), 2)
    total_bs = round(total_con_iva_bs + igtf_bs, 2)
    return iva_bs, igtf_bs, total_bs


def obtener_tasas_impuesto(db: Session) -> Dict[str, float]:
    """{clave: tasa} vigentes con defaults por si no están configuradas."""
    filas = db.query(TasaImpuesto).filter(TasaImpuesto.vigente.is_(True)).all()
    tasas = {fila.clave: float(fila.tasa) for fila in filas}
    tasas.setdefault("IVA", 16.0)
    tasas.setdefault("IGTF", 3.0)
    return tasas


def listar_tasas_impuesto(db: Session) -> List[TasaImpuesto]:
    return db.query(TasaImpuesto).order_by(TasaImpuesto.clave).all()


def actualizar_tasa_impuesto(db: Session, clave: str, esquema: TasaImpuestoUpdate, usuario: Usuario | None = None):
    fila = db.query(TasaImpuesto).filter(TasaImpuesto.clave == clave.upper()).first()
    if not fila:
        raise ValueError(f"No existe la tasa de impuesto '{clave}'.")
    antes = {"tasa": float(fila.tasa)}
    fila.tasa = esquema.tasa
    record_event(
        db,
        actor=usuario,
        action="UPDATE",
        entity_type="tasa_impuesto",
        entity_id=fila.id,
        before=antes,
        after={"tasa": float(fila.tasa)},
    )
    db.commit()
    db.refresh(fila)
    return fila


# ------------------------------------------------------------
# Consultas
# ------------------------------------------------------------
def _snapshot(factura: Factura) -> dict:
    return {
        "pedido_id": factura.pedido_id,
        "fecha_emision": factura.fecha_emision,
        "total_usd": float(factura.total_usd),
        "tasa_usd_ves": float(factura.tasa_usd_ves),
        "total_bs": float(factura.total_bs),
        "estado": factura.estado,
    }


def obtener_factura(db: Session, id_factura: int, usuario: Usuario | None = None):
    query = db.query(Factura).filter(Factura.id == id_factura)
    if usuario is not None:
        query = filtrar_registros_propios(query, Factura.creado_por_id, usuario)
    return query.first()


def obtener_facturas(db: Session, usuario: Usuario | None = None):
    query = db.query(Factura)
    if usuario is not None:
        query = filtrar_registros_propios(query, Factura.creado_por_id, usuario)
    return query.order_by(Factura.id.desc()).limit(500).all()


# ------------------------------------------------------------
# Pedidos facturables (venta sin factura; puede tener saldo pendiente)
# ------------------------------------------------------------
def pedidos_facturables(db: Session, usuario: Usuario | None = None):
    # Una factura ANULADA no bloquea al pedido: puede re-facturarse (corrección).
    facturados = {
        f[0] for f in db.query(Factura.pedido_id).filter(Factura.estado != "ANULADA").all()
    }

    # Todas las ventas facturables, sin importar el estado de cobro. Una venta
    # CANCELADA no se factura; el saldo pendiente decide si hace falta autorización.
    query = (
        db.query(Pedido, Venta)
        .join(Venta, Venta.pedido_id == Pedido.id)
        .filter(Venta.estado != "CANCELADA")
    )
    if usuario is not None:
        query = filtrar_registros_propios(query, Pedido.creado_por_id, usuario)

    resultado = []
    for pedido, venta in query.limit(500).all():
        if pedido.id in facturados:
            continue
        total_pagado = sum(float(p.monto_en_moneda_base) for p in venta.pagos)
        saldo_pendiente = max(0.0, float(venta.total) - total_pagado)

        moneda_codigo = None
        if pedido.cotizacion and pedido.cotizacion.moneda:
            moneda_codigo = pedido.cotizacion.moneda.codigo

        lineas = []
        for dp in pedido.detalles:
            lineas.append({
                "detalle_pedido_id": dp.id,
                "nombre": (
                    dp.producto.nombre if dp.producto
                    else (dp.material.nombre if dp.material else None)
                ) or f"Producto #{dp.producto_id}",
                "cantidad": float(dp.cantidad),
                "precio_referencia": float(dp.precio),
                "moneda_codigo": moneda_codigo,
            })

        resultado.append({
            "pedido_id": pedido.id,
            "cliente_id": pedido.cliente_id,
            "cliente_nombre": pedido.cliente.nombre if pedido.cliente else "—",
            "fecha": pedido.fecha,
            "estado": pedido.estado,
            "venta_id": venta.id,
            "total_venta": float(venta.total),
            "total_pagado": round(total_pagado, 2),
            "saldo_pendiente": round(saldo_pendiente, 2),
            "venta_estado": venta.estado,
            "venta_moneda_codigo": venta.moneda.codigo if venta.moneda else None,
            "lineas": lineas,
        })

    # Los pendientes de cobro primero (exigen autorización del admin) y dentro de
    # cada grupo el pedido más reciente.
    resultado.sort(key=lambda r: (r["saldo_pendiente"] > 0, r["fecha"]), reverse=True)
    return resultado


# ------------------------------------------------------------
# Emisión de la factura
# ------------------------------------------------------------
def crear_factura_desde_pedido(db: Session, esquema: FacturaCreate, commit: bool = True, usuario: Usuario | None = None):
    pedido_query = db.query(Pedido).filter(Pedido.id == esquema.pedido_id)
    if usuario is not None:
        pedido_query = filtrar_registros_propios(pedido_query, Pedido.creado_por_id, usuario)
    pedido = pedido_query.with_for_update().first()
    if not pedido:
        raise ValueError("El pedido especificado no existe.")

    # 1. Por defecto solo se facturan pedidos pagados al 100%; un Dueño/Administrador
    #    puede autorizar la emisión puntual con saldo pendiente (decisión caso a caso).
    venta = db.query(Venta).filter(Venta.pedido_id == pedido.id).first()
    if not venta:
        raise ValueError(
            "El pedido no tiene una venta registrada. Debe gestionarse el cobro en 'Ventas y cobros' primero."
        )
    total_pagado = sum(float(p.monto_en_moneda_base) for p in venta.pagos)
    saldo_pendiente = max(0.0, float(venta.total) - total_pagado)
    autorizada_con_saldo = False
    observaciones = esquema.observaciones
    if venta.estado != "PAGADA" and saldo_pendiente > 0.01:
        if not esquema.permitir_saldo_pendiente:
            raise ValueError(
                "Solo se pueden facturar pedidos pagados al 100%. "
                f"El pedido #{pedido.id} tiene saldo pendiente."
            )
        if usuario is None or not es_admin_user(usuario):
            raise FacturaNoAutorizadaError(
                "Solo un administrador puede facturar con saldo pendiente."
            )
        autorizada_con_saldo = True
        moneda_codigo = venta.moneda.codigo if venta.moneda else ""
        nota = f"Factura emitida con saldo pendiente de {saldo_pendiente:,.2f} {moneda_codigo}".strip()
        observaciones = "\n".join(parte for parte in [observaciones, nota] if parte)

    # 2. Una sola factura vigente por pedido; las ANULADAS no bloquean una corrección.
    if db.query(Factura).filter(
        Factura.pedido_id == pedido.id, Factura.estado != "ANULADA"
    ).first():
        raise ValueError("Este pedido ya tiene una factura emitida.")

    # 3. Las líneas deben cubrir cada línea del pedido (cantidad fija por línea).
    #    Se identifican por detalle_pedido.id (no por producto): un pedido puede
    #    tener varias líneas del mismo producto y se facturan de forma independiente.
    detalles_pedido = {dp.id: dp for dp in pedido.detalles}
    vistos = set()
    lineas = []
    for linea in esquema.lineas:
        dp = detalles_pedido.get(linea.detalle_pedido_id)
        if not dp:
            raise ValueError(f"La línea #{linea.detalle_pedido_id} no pertenece a este pedido.")
        if linea.detalle_pedido_id in vistos:
            raise ValueError(f"La línea #{linea.detalle_pedido_id} está repetida en las líneas enviadas.")
        vistos.add(linea.detalle_pedido_id)
        cantidad = float(dp.cantidad)
        subtotal_usd = round(cantidad * linea.precio_usd, 2)
        lineas.append((dp, linea, subtotal_usd))
    if len(lineas) != len(detalles_pedido):
        raise ValueError("Debes indicar el monto de facturación de cada línea del pedido.")

    # 4. Montos: USD decididos por la dueña → Bs. con la tasa del día.
    total_usd = round(sum(subtotal for _, _, subtotal in lineas), 2)
    tasa_usd_ves = float(esquema.tasa_usd_ves)
    base_imponible_bs = round(total_usd * tasa_usd_ves, 2)
    tasas = obtener_tasas_impuesto(db)
    iva_bs, igtf_bs, total_bs = calcular_impuestos(base_imponible_bs, tasas["IVA"], tasas["IGTF"])

    db_factura = Factura(
        pedido_id=pedido.id,
        cliente_id=pedido.cliente_id,
        fecha_emision=esquema.fecha_emision or date.today(),
        total_usd=total_usd,
        tasa_usd_ves=tasa_usd_ves,
        base_imponible_bs=base_imponible_bs,
        iva_bs=iva_bs,
        igtf_bs=igtf_bs,
        total_bs=total_bs,
        estado="EMITIDA",
        observaciones=observaciones,
        creado_por_id=usuario.id if usuario is not None else None,
        actualizado_por_id=usuario.id if usuario is not None else None,
    )
    db.add(db_factura)
    db.flush()

    for dp, linea, subtotal_usd in lineas:
        # La línea copia el tipo del pedido: FABRICADO/REVENTA → producto;
        # INSUMO → material vendido suelto (producto_id es NULL).
        db.add(DetalleFactura(
            factura_id=db_factura.id,
            tipo_item=dp.tipo_item or "FABRICADO",
            producto_id=dp.producto_id,
            material_id=dp.material_id,
            descripcion=(
                dp.producto.nombre if dp.producto
                else (dp.material.nombre if dp.material else None)
            ),
            cantidad=float(dp.cantidad),
            precio_usd=linea.precio_usd,
            subtotal_usd=subtotal_usd,
            subtotal_bs=round(subtotal_usd * tasa_usd_ves, 2),
        ))

    record_event(
        db,
        actor=usuario,
        action="CREATE",
        entity_type="factura",
        entity_id=db_factura.id,
        after=_snapshot(db_factura),
    )

    if autorizada_con_saldo:
        record_event(
            db,
            actor=usuario,
            action="FACTURAR_CON_SALDO_PENDIENTE",
            entity_type="factura",
            entity_id=db_factura.id,
            after={"saldo_pendiente": round(saldo_pendiente, 2), "moneda": moneda_codigo},
        )

    if commit:
        db.commit()
    else:
        db.flush()
    db.refresh(db_factura)
    return db_factura


def anular_factura(db: Session, id_factura: int, usuario: Usuario | None = None):
    db_factura = obtener_factura(db, id_factura, usuario)
    if not db_factura:
        return None
    if db_factura.estado == "ANULADA":
        raise ValueError("La factura ya está anulada.")
    antes = _snapshot(db_factura)
    db_factura.estado = "ANULADA"
    if usuario is not None:
        db_factura.actualizado_por_id = usuario.id
    record_event(
        db,
        actor=usuario,
        action="STATE_CHANGE",
        entity_type="factura",
        entity_id=db_factura.id,
        before=antes,
        after=_snapshot(db_factura),
    )
    db.commit()
    db.refresh(db_factura)
    return db_factura
