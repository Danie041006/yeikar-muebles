"""Servicio de nómina semanal.

Generación automática desde las etapas COMPLETADAS del periodo:
cada etapa → una línea (producto + área + cliente + cantidad + precio del
catálogo `precio_produccion`), agrupada por empleado responsable. El pago
genera UN EGRESO por empleado (gasto "NÓMINA SEMANAL" + salida de caja) y
acumula el bono de aguinaldo (porcentaje del área) en el saldo del empleado.
"""
from datetime import date, datetime, time
from decimal import Decimal
from typing import List, Optional

from sqlalchemy.orm import Session, joinedload
from sqlalchemy import text

from app.modules.nomina import model, schemas
from app.modules.empleados.model import Empleado
from app.modules.costos_produccion.model import PrecioProduccion
from app.modules.production.model import EtapaProduccion, OrdenProduccion
from app.modules.orders.model import DetallePedido, Pedido
from app.modules.catalogos.model import Area, Cargo, TipoGasto, Moneda
from app.modules.gastos.model import Gasto
from app.modules.users.model import Usuario


TIPO_GASTO_NOMINA = "NÓMINA SEMANAL"
TIPO_GASTO_AGUINALDO = "AGUINALDO ANUAL"


# ------------------------------------------------------------
# Config de áreas (aguinaldo %)
# ------------------------------------------------------------
def listar_config_areas(db: Session) -> List[model.NominaAreaConfig]:
    return (
        db.query(model.NominaAreaConfig)
        .options(joinedload(model.NominaAreaConfig.area))
        .order_by(model.NominaAreaConfig.id)
        .all()
    )

def actualizar_config_area(
    db: Session, area_id: int, porcentaje: Decimal
) -> Optional[model.NominaAreaConfig]:
    cfg = db.query(model.NominaAreaConfig).filter(model.NominaAreaConfig.area_id == area_id).first()
    if not cfg:
        cfg = model.NominaAreaConfig(area_id=area_id, porcentaje_aguinaldo=porcentaje)
        db.add(cfg)
    else:
        cfg.porcentaje_aguinaldo = porcentaje
    db.commit()
    db.refresh(cfg)
    return cfg


# ------------------------------------------------------------
# Generación del borrador (draft)
# ------------------------------------------------------------
def _porcentaje_area(db: Session, area_id: Optional[int]) -> Decimal:
    if area_id is None:
        return Decimal("0")
    cfg = db.query(model.NominaAreaConfig).filter(model.NominaAreaConfig.area_id == area_id).first()
    return cfg.porcentaje_aguinaldo if cfg else Decimal("0")


def _etapas_del_periodo(db: Session, desde: date, hasta: date):
    inicio = datetime.combine(desde, time.min)
    fin = datetime.combine(hasta, time.max)
    return (
        db.query(EtapaProduccion)
        .options(
            joinedload(EtapaProduccion.area),
            joinedload(EtapaProduccion.orden)
            .joinedload(OrdenProduccion.detalle_pedido)
            .joinedload(DetallePedido.producto),
            joinedload(EtapaProduccion.orden)
            .joinedload(OrdenProduccion.detalle_pedido)
            .joinedload(DetallePedido.pedido)
            .joinedload(Pedido.cliente),
        )
        .filter(
            EtapaProduccion.estado == "COMPLETADA",
            # El retrabajo (etapa recreada en un área ya completada de la misma
            # orden) NO paga destajo: evita pagar dos veces el mismo trabajo.
            EtapaProduccion.es_retrabajo.is_(False),
            EtapaProduccion.fecha_fin >= inicio,
            EtapaProduccion.fecha_fin <= fin,
        )
        .all()
    )


def _precio_catalogo(db: Session, area_id: int, producto_id: Optional[int]) -> Decimal:
    """Precio del catálogo para (área, producto) si está vinculado; si no, 0."""
    if producto_id is None:
        return Decimal("0")
    item = (
        db.query(PrecioProduccion)
        .filter(
            PrecioProduccion.area_id == area_id,
            PrecioProduccion.producto_id == producto_id,
            PrecioProduccion.activo.is_(True),
        )
        .first()
    )
    return item.precio if item else Decimal("0")


def generar_nomina(db: Session, desde: date, hasta: date) -> schemas.NominaDraftResponse:
    if desde > hasta:
        raise ValueError("La fecha inicial no puede ser posterior a la final.")

    # Empleados en nómina (destajo y fijos)
    empleados = (
        db.query(Empleado)
        .options(joinedload(Empleado.cargo))
        .filter(Empleado.en_nomina.is_(True), Empleado.activo.is_(True))
        .order_by(Empleado.cargo_id, Empleado.nombre)
        .all()
    )
    por_empleado = {e.id: e for e in empleados}

    # Producción completada del periodo, agrupada por responsable
    etapas = _etapas_del_periodo(db, desde, hasta)
    lineas_por_empleado: dict = {e.id: [] for e in empleados}
    for ep in etapas:
        if ep.empleado_responsable_id not in por_empleado:
            continue
        emp = por_empleado[ep.empleado_responsable_id]
        if emp.tipo_pago != "DESTAJO":
            continue
        detalle = ep.orden.detalle_pedido
        producto = detalle.producto
        cliente = detalle.pedido.cliente
        cantidad = detalle.cantidad
        precio = _precio_catalogo(db, ep.area_id, detalle.producto_id)
        total = precio * cantidad
        lineas_por_empleado[emp.id].append(
            schemas.LineaDraft(
                origen="ETAPA",
                etapa_id=ep.id,
                descripcion=producto.nombre if producto else "Producción",
                area_id=ep.area_id,
                area_nombre=ep.area.nombre if ep.area else None,
                cliente_nombre=cliente.nombre if cliente else None,
                cantidad=cantidad,
                precio_unitario=precio,
                total=total,
            )
        )

    detalles_draft: List[schemas.DetalleDraft] = []
    for emp in empleados:
        lineas = lineas_por_empleado[emp.id]
        if emp.tipo_pago == "FIJO":
            # Los fijos entran con su sueldo semanal como línea
            sueldo = emp.sueldo_semanal or Decimal("0")
            if sueldo > 0:
                lineas = [
                    schemas.LineaDraft(
                        origen="MANUAL",
                        descripcion="NOMINA SEMANA",
                        cantidad=Decimal("1"),
                        precio_unitario=sueldo,
                        total=sueldo,
                    )
                ]
            else:
                lineas = []
        total_produccion = sum((l.total for l in lineas), Decimal("0"))
        bono = Decimal("0")
        if emp.tipo_pago == "DESTAJO":
            for l in lineas:
                pct = _porcentaje_area(db, l.area_id)
                bono += l.total * pct / Decimal("100")
        # Sobrescritura opcional: porcentaje de aguinaldo propio del empleado
        if emp.porcentaje_aguinaldo is not None and emp.tipo_pago == "DESTAJO":
            bono = total_produccion * emp.porcentaje_aguinaldo / Decimal("100")
        monto = total_produccion if emp.tipo_pago == "DESTAJO" else (emp.sueldo_semanal or Decimal("0"))
        detalles_draft.append(
            schemas.DetalleDraft(
                empleado_id=emp.id,
                empleado_nombre=emp.nombre,
                cargo_nombre=emp.cargo.nombre if emp.cargo else None,
                tipo_pago=emp.tipo_pago,
                total_produccion=total_produccion,
                bono_aguinaldo=bono,
                monto_a_pagar=monto,
                lineas=lineas,
            )
        )

    total_nomina = sum((d.monto_a_pagar for d in detalles_draft), Decimal("0"))
    return schemas.NominaDraftResponse(
        periodo_desde=desde,
        periodo_hasta=hasta,
        detalles=detalles_draft,
        total_nomina=total_nomina,
    )


# ------------------------------------------------------------
# CRUD de nómina
# ------------------------------------------------------------
def _con_detalles(query):
    return query.options(
        joinedload(model.Nomina.detalles)
        .joinedload(model.NominaDetalle.empleado)
        .joinedload(Empleado.cargo),
        joinedload(model.Nomina.detalles)
        .joinedload(model.NominaDetalle.lineas)
        .joinedload(model.NominaLinea.area),
        joinedload(model.Nomina.detalles)
        .joinedload(model.NominaDetalle.metodo_caja),
        joinedload(model.Nomina.conceptos_varios),
        joinedload(model.Nomina.creador),
    )


def obtener_nomina(db: Session, nomina_id: int) -> Optional[model.Nomina]:
    return _con_detalles(db.query(model.Nomina)).filter(model.Nomina.id == nomina_id).first()


def listar_nominas(db: Session, skip: int = 0, limit: int = 100) -> List[model.Nomina]:
    return (
        _con_detalles(db.query(model.Nomina))
        .order_by(model.Nomina.periodo_desde.desc(), model.Nomina.id.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )


def _validar_semana_disponible(db: Session, desde: date, hasta: date) -> None:
    """Rechaza crear una nómina para una semana que ya tiene una activa (BORRADOR o PAGADA)."""
    existente = db.query(model.Nomina).filter(
        model.Nomina.periodo_desde == desde,
        model.Nomina.periodo_hasta == hasta,
        model.Nomina.estado.in_(["BORRADOR", "PAGADA"]),
    ).first()
    if existente:
        raise ValueError(f"Ya existe una nómina para esa semana ({desde} → {hasta}).")


def crear_nomina(db: Session, esquema: schemas.NominaCreate, usuario: Optional[Usuario] = None) -> model.Nomina:
    _validar_semana_disponible(db, esquema.periodo_desde, esquema.periodo_hasta)
    draft = generar_nomina(db, esquema.periodo_desde, esquema.periodo_hasta)
    nomina = model.Nomina(
        periodo_desde=esquema.periodo_desde,
        periodo_hasta=esquema.periodo_hasta,
        estado="BORRADOR",
        descripcion=esquema.descripcion,
        creado_por_id=usuario.id if usuario else None,
    )
    db.add(nomina)
    db.flush()

    for d in draft.detalles:
        detalle = model.NominaDetalle(
            nomina_id=nomina.id,
            empleado_id=d.empleado_id,
            tipo_pago=d.tipo_pago,
            total_produccion=d.total_produccion,
            bono_aguinaldo=d.bono_aguinaldo,
            monto_a_pagar=d.monto_a_pagar,
            # Congela el sueldo del FIJO en el momento de emitir la nómina
            sueldo_snapshot=d.monto_a_pagar if d.tipo_pago == "FIJO" else None,
        )
        db.add(detalle)
        db.flush()
        for l in d.lineas:
            db.add(
                model.NominaLinea(
                    detalle_id=detalle.id,
                    origen=l.origen,
                    etapa_id=l.etapa_id,
                    descripcion=l.descripcion,
                    area_id=l.area_id,
                    cliente_nombre=l.cliente_nombre,
                    cantidad=l.cantidad,
                    precio_unitario=l.precio_unitario,
                    total=l.total,
                )
            )

    for c in esquema.conceptos_varios:
        db.add(
            model.NominaConceptoVario(
                nomina_id=nomina.id,
                descripcion=c.descripcion,
                monto=c.monto,
            )
        )

    _recalcular_total(db, nomina)
    db.commit()
    db.refresh(nomina)
    return obtener_nomina(db, nomina.id)


def _recalcular_total(db: Session, nomina: model.Nomina) -> None:
    pagos = sum((d.monto_a_pagar for d in nomina.detalles), Decimal("0"))
    varios = sum((c.monto for c in nomina.conceptos_varios), Decimal("0"))
    nomina.total_nomina = pagos + varios


def actualizar_detalle(db: Session, detalle_id: int, esquema: schemas.NominaDetalleUpdate) -> Optional[model.NominaDetalle]:
    detalle = db.query(model.NominaDetalle).filter(model.NominaDetalle.id == detalle_id).first()
    if not detalle:
        return None
    if detalle.nomina.estado != "BORRADOR":
        raise ValueError("Solo se pueden editar nóminas en borrador.")
    data = esquema.model_dump(exclude_unset=True)
    for campo, valor in data.items():
        setattr(detalle, campo, valor)
    _recalcular_total(db, detalle.nomina)
    db.commit()
    db.refresh(detalle)
    return detalle


def agregar_linea_manual(db: Session, detalle_id: int, esquema: schemas.NominaLineaCreate) -> Optional[model.NominaLinea]:
    detalle = db.query(model.NominaDetalle).filter(model.NominaDetalle.id == detalle_id).first()
    if not detalle:
        return None
    if detalle.nomina.estado != "BORRADOR":
        raise ValueError("Solo se pueden editar nóminas en borrador.")
    total = esquema.cantidad * esquema.precio_unitario
    linea = model.NominaLinea(
        detalle_id=detalle_id,
        origen="MANUAL",
        descripcion=esquema.descripcion,
        cantidad=esquema.cantidad,
        precio_unitario=esquema.precio_unitario,
        total=total,
    )
    db.add(linea)
    db.flush()
    _actualizar_totales_detalle(db, detalle)
    db.commit()
    db.refresh(linea)
    return linea


def eliminar_linea(db: Session, linea_id: int) -> bool:
    linea = db.query(model.NominaLinea).filter(model.NominaLinea.id == linea_id).first()
    if not linea:
        return False
    if linea.detalle.nomina.estado != "BORRADOR":
        raise ValueError("Solo se pueden editar nóminas en borrador.")
    detalle = linea.detalle
    db.delete(linea)
    db.flush()
    _actualizar_totales_detalle(db, detalle)
    db.commit()
    return True


def _actualizar_totales_detalle(db: Session, detalle: model.NominaDetalle) -> None:
    """Recomputa total_produccion, bono y monto a pagar de un detalle."""
    total = sum((l.total for l in detalle.lineas), Decimal("0"))
    detalle.total_produccion = total
    bono = Decimal("0")
    if detalle.tipo_pago == "DESTAJO":
        for l in detalle.lineas:
            pct = _porcentaje_area(db, l.area_id)
            bono += l.total * pct / Decimal("100")
        if detalle.empleado.porcentaje_aguinaldo is not None:
            bono = total * detalle.empleado.porcentaje_aguinaldo / Decimal("100")
    detalle.bono_aguinaldo = bono
    if detalle.tipo_pago == "DESTAJO":
        detalle.monto_a_pagar = total
    else:
        # FIJO: el sueldo base es el SNAPSHOT del momento de crear la nómina
        # (editar el sueldo del empleado después no revaloriza nóminas viejas).
        # La línea "NOMINA SEMANA" del draft ya representa ese sueldo; los pagos
        # extra se hacen editando monto_a_pagar (que es editable), no sumando líneas.
        if detalle.sueldo_snapshot is not None:
            detalle.monto_a_pagar = detalle.sueldo_snapshot
        else:
            detalle.monto_a_pagar = detalle.empleado.sueldo_semanal or Decimal("0")
    _recalcular_total(db, detalle.nomina)


def agregar_concepto_vario(db: Session, nomina_id: int, esquema: schemas.ConceptoVarioCreate) -> Optional[model.NominaConceptoVario]:
    nomina = db.query(model.Nomina).filter(model.Nomina.id == nomina_id).first()
    if not nomina:
        return None
    if nomina.estado != "BORRADOR":
        raise ValueError("Solo se pueden editar nóminas en borrador.")
    concepto = model.NominaConceptoVario(nomina_id=nomina_id, descripcion=esquema.descripcion, monto=esquema.monto)
    db.add(concepto)
    db.flush()
    _recalcular_total(db, nomina)
    db.commit()
    db.refresh(concepto)
    return concepto


def eliminar_concepto_vario(db: Session, concepto_id: int) -> bool:
    concepto = db.query(model.NominaConceptoVario).filter(model.NominaConceptoVario.id == concepto_id).first()
    if not concepto:
        return False
    if concepto.nomina.estado != "BORRADOR":
        raise ValueError("Solo se pueden editar nóminas en borrador.")
    nomina = concepto.nomina
    db.delete(concepto)
    db.flush()
    _recalcular_total(db, nomina)
    db.commit()
    return True


# ------------------------------------------------------------
# Pago y anulación
# ------------------------------------------------------------
def _tipo_gasto(db: Session, nombre: str, categoria: str = "OPERATIVO") -> TipoGasto:
    """Busca un tipo de gasto por nombre y lo crea (categoría OPERATIVO) si no existe."""
    tg = db.query(TipoGasto).filter(TipoGasto.nombre == nombre).first()
    if not tg:
        tg = TipoGasto(nombre=nombre, categoria=categoria)
        db.add(tg)
        db.flush()
    return tg


def _tipo_gasto_nomina(db: Session) -> TipoGasto:
    return _tipo_gasto(db, TIPO_GASTO_NOMINA)


def pagar_nomina(db: Session, nomina_id: int, usuario: Optional[Usuario] = None) -> Optional[model.Nomina]:
    # FOR UPDATE: dos pagos simultáneos de la misma nómina se serializan; el
    # segundo re-lee el estado ya PAGADA y recibe 400 en vez de pagar 2 veces
    # (creaba gastos y salidas de caja duplicados por la carrera de lecturas).
    nomina = (
        db.query(model.Nomina)
        .filter(model.Nomina.id == nomina_id)
        .with_for_update()
        .first()
    )
    if not nomina:
        return None
    if nomina.estado != "BORRADOR":
        raise ValueError("La nómina ya no está en borrador.")

    from app.modules.gastos.service import crear_gasto

    tg = _tipo_gasto_nomina(db)
    periodo = f"{nomina.periodo_desde} al {nomina.periodo_hasta}"
    detalles_con_pago = [d for d in nomina.detalles if (d.monto_a_pagar or 0) > 0]

    for detalle in detalles_con_pago:
        if detalle.metodo_caja_id is None:
            raise ValueError(
                f"Falta la cuenta de caja del empleado {detalle.empleado.nombre}."
            )
        # commit=False: todo el pago se commitea en UNA transacción al final.
        # crear_gasto con commit interno liberaría el lock FOR UPDATE a mitad
        # del proceso y un segundo pago simultáneo re-leería BORRADOR.
        gasto = crear_gasto(
            db,
            schemas_gasto(
                tipo_gasto_id=tg.id,
                moneda_id=1,
                fecha=date.today(),
                descripcion=f"Nómina {periodo} — {detalle.empleado.nombre}",
                monto=detalle.monto_a_pagar,
                metodo_caja_id=detalle.metodo_caja_id,
                observaciones="Generado automáticamente por la nómina",
            ),
            usuario,
            commit=False,
        )
        detalle.gasto_id = gasto.id
        # Acumula el bono de aguinaldo en el saldo del empleado
        if detalle.bono_aguinaldo and detalle.bono_aguinaldo > 0:
            detalle.empleado.saldo_aguinaldo = (
                (detalle.empleado.saldo_aguinaldo or Decimal("0")) + detalle.bono_aguinaldo
            )

    nomina.estado = "PAGADA"
    db.commit()
    db.refresh(nomina)
    return obtener_nomina(db, nomina.id)


def schemas_gasto(tipo_gasto_id: int, moneda_id: int, fecha: date, descripcion: str, monto: Decimal, metodo_caja_id: int, observaciones: str):
    from decimal import Decimal as D
    from app.modules.gastos.schemas import GastoCreate
    return GastoCreate(
        tipo_gasto_id=tipo_gasto_id,
        moneda_id=moneda_id,
        fecha=fecha,
        descripcion=descripcion,
        monto=D(monto),
        tasa_cambio=D("1.0"),
        metodo_caja_id=metodo_caja_id,
        observaciones=observaciones,
    )


def anular_nomina(db: Session, nomina_id: int, usuario: Optional[Usuario] = None) -> Optional[model.Nomina]:
    # FOR UPDATE: dos anulaciones simultáneas se serializan; la segunda ve el
    # estado ANULADA y recibe 400 (antes ambas pasaban y la reversión de
    # gastos/aguinaldo se ejecutaba dos veces).
    nomina = (
        db.query(model.Nomina)
        .filter(model.Nomina.id == nomina_id)
        .with_for_update()
        .first()
    )
    if not nomina:
        return None
    if nomina.estado != "PAGADA":
        raise ValueError("Solo se puede anular una nómina pagada.")

    # Reversión en UNA sola transacción (el lock FOR UPDATE se mantiene hasta
    # el commit final): eliminar_gasto() hace commit interno y liberaría el
    # lock a mitad de la reversión, dejando que un segundo hilo pase.
    from app.modules.reports.model import MovimientoCaja

    for detalle in nomina.detalles:
        # Revierte el bono acumulado
        if detalle.bono_aguinaldo and detalle.bono_aguinaldo > 0:
            detalle.empleado.saldo_aguinaldo = (
                (detalle.empleado.saldo_aguinaldo or Decimal("0")) - detalle.bono_aguinaldo
            )
        if detalle.gasto_id:
            db.query(MovimientoCaja).filter(
                MovimientoCaja.referencia == f"Gasto #{detalle.gasto_id}"
            ).delete(synchronize_session=False)
            gasto_obj = db.query(Gasto).filter(Gasto.id == detalle.gasto_id).first()
            if gasto_obj:
                db.delete(gasto_obj)
            detalle.gasto_id = None

    nomina.estado = "ANULADA"
    db.commit()
    db.refresh(nomina)
    return obtener_nomina(db, nomina.id)


# ------------------------------------------------------------
# Saldos de aguinaldo
# ------------------------------------------------------------
def saldos_aguinaldo(db: Session) -> List[schemas.SaldoAguinaldoResponse]:
    empleados = (
        db.query(Empleado)
        .options(joinedload(Empleado.cargo))
        .filter(Empleado.en_nomina.is_(True), Empleado.activo.is_(True))
        .order_by(Empleado.cargo_id, Empleado.nombre)
        .all()
    )
    return [
        schemas.SaldoAguinaldoResponse(
            empleado_id=e.id,
            empleado_nombre=e.nombre,
            cargo_nombre=e.cargo.nombre if e.cargo else None,
            saldo_aguinaldo=e.saldo_aguinaldo or Decimal("0"),
        )
        for e in empleados
    ]


def pagar_aguinaldo(db: Session, esquema: schemas.PagoAguinaldoRequest, usuario: Optional[Usuario] = None) -> schemas.PagoAguinaldoResponse:
    """Entrega el aguinaldo acumulado del empleado como un gasto (AGUINALDO ANUAL)
    que sale de la cuenta indicada, y resetea su saldo a cero."""
    empleado = db.query(Empleado).filter(Empleado.id == esquema.empleado_id).first()
    if not empleado:
        raise ValueError("El empleado no existe.")
    saldo = empleado.saldo_aguinaldo or Decimal("0")
    if saldo <= 0:
        raise ValueError("El empleado no tiene aguinaldo acumulado")

    from app.modules.gastos.service import crear_gasto

    tg = _tipo_gasto(db, TIPO_GASTO_AGUINALDO)
    periodo = date.today().year
    gasto = crear_gasto(
        db,
        schemas_gasto(
            tipo_gasto_id=tg.id,
            moneda_id=1,
            fecha=date.today(),
            descripcion=f"Aguinaldo {periodo} — {empleado.nombre}",
            monto=saldo,
            metodo_caja_id=esquema.metodo_caja_id,
            observaciones=esquema.observaciones or "Aguinaldo anual entregado desde la nómina",
        ),
        usuario,
    )
    empleado.saldo_aguinaldo = Decimal("0")
    db.commit()
    db.refresh(empleado)
    return schemas.PagoAguinaldoResponse(
        empleado_id=empleado.id,
        empleado_nombre=empleado.nombre,
        monto=saldo,
        gasto_id=gasto.id,
        saldo_restante=empleado.saldo_aguinaldo or Decimal("0"),
    )
