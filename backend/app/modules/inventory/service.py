import unicodedata
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Optional, List

from sqlalchemy.orm import Session, joinedload
from sqlalchemy import and_, or_
from sqlalchemy.exc import IntegrityError


from app.modules.inventory import model, schemas
from app.modules.productos.model import Material, Producto
from app.modules.catalogos.model import Area, CategoriaInventario, Ubicacion, UnidadMedida
from app.modules.proveedores.model import Proveedor
from app.modules.clients.model import Client
from app.core.hora_ve import ahora_ve, hoy_ve

MONEDA_BASE_ID = 1  # COP


def _resolver_proveedor_cliente(
    db: Session,
    proveedor_id: Optional[int],
    proveedor_nombre: Optional[str],
    cliente_id: Optional[int],
    cliente_nombre: Optional[str],
) -> tuple:
    """El proveedor/cliente de un movimiento se puede indicar por id (registro
    existente) o por NOMBRE LIBRE. Si viene el nombre y coincide con un registro,
    se linkea el id; si no, el nombre queda como texto en el movimiento — no se
    crea un registro del catálogo a la fuerza."""
    proveedor_nombre = (proveedor_nombre or "").strip() or None
    cliente_nombre = (cliente_nombre or "").strip() or None
    if proveedor_nombre and proveedor_id is None:
        prov = db.query(Proveedor).filter(Proveedor.nombre == proveedor_nombre).first()
        if prov:
            proveedor_id = prov.id
    if cliente_nombre and cliente_id is None:
        cli = db.query(Client).filter(Client.nombre == cliente_nombre).first()
        if cli:
            cliente_id = cli.id
    return proveedor_id, proveedor_nombre, cliente_id, cliente_nombre


def _fecha_movimiento(fecha: Optional[date]) -> datetime:
    """Fecha/hora que se guarda en el kardex.

    - Sin fecha (formulario por defecto): AHORA en hora VE, como siempre.
    - Fecha de hoy: también AHORA (conserva la hora real de captura).
    - Fecha anterior: se ancla al mediodía, igual que los pagos, para que el
      día no se corra por zona horaria.
    - Fechas futuras: se rechazan (el inventario no se registra por adelantado).
    """
    if fecha is None:
        return ahora_ve()
    if fecha > hoy_ve():
        raise ValueError("La fecha del movimiento no puede ser futura.")
    if fecha == hoy_ve():
        return ahora_ve()
    return datetime.combine(fecha, time(12, 0))


def _gasto_compra_contado(
    db: Session,
    *,
    tipo_gasto_nombre: str,
    descripcion: str,
    total_ref: Decimal,
    ref_moneda_id: int,
    metodo_caja_id: int,
    moneda_pago_id: Optional[int] = None,
    tasa_pago: Optional[Decimal] = None,
    fecha: Optional[date] = None,
    usuario=None,
):
    """Compra de contado: registra el gasto + la SALIDA de caja correspondiente.

    Filosofía de tasas YEIKAR: se digitan manualmente por operación ("1 [moneda]
    = X COP"); NO hay tabla de tasas. Reglas:
      - Pago en COP → sin tasa; el monto ya está en pesos.
      - Pago en la MISMA moneda de referencia (≠ COP) → tasa obligatoria solo
        como equivalente en COP para el P&L; la caja descuenta el total tal cual.
      - Referencia en COP pagada desde moneda extranjera → deducción =
        total ÷ tasa (tasa obligatoria).
    """
    from app.modules.gastos.service import crear_gasto
    from app.modules.gastos.schemas import GastoCreate
    from app.modules.catalogos.model import TipoGasto, Moneda
    from app.modules.reports.model import MetodoCaja

    cuenta = db.query(MetodoCaja).filter(MetodoCaja.id == metodo_caja_id).first()
    if not cuenta:
        raise ValueError("La cuenta de caja indicada no existe.")

    ref_moneda_id = ref_moneda_id or MONEDA_BASE_ID
    pago = moneda_pago_id or ref_moneda_id
    if pago != MONEDA_BASE_ID and not db.query(Moneda).filter(Moneda.id == pago).first():
        raise ValueError(f"La moneda de pago #{pago} no existe.")

    def _codigo(mid):
        return db.query(Moneda.codigo).filter(Moneda.id == mid).scalar() or f"#{mid}"

    CURRENCY_PRIORITY = ["EUR", "USD", "VES", "COP"]

    def _resolver_par(cod_a: str, cod_b: str):
        idx_a = CURRENCY_PRIORITY.index(cod_a) if cod_a in CURRENCY_PRIORITY else 99
        idx_b = CURRENCY_PRIORITY.index(cod_b) if cod_b in CURRENCY_PRIORITY else 99
        if idx_a <= idx_b:
            return cod_a, cod_b
        return cod_b, cod_a

    from app.modules.tasas_cambio.service import obtener_tasa_moneda_a_cop

    ref_cod = _codigo(ref_moneda_id)
    pago_cod = _codigo(pago)

    if pago == ref_moneda_id:
        monto = total_ref
        gasto_moneda = pago
        if pago == MONEDA_BASE_ID:
            tasa = Decimal("1.0")
        else:
            tasa = Decimal(str(tasa_pago)) if tasa_pago and tasa_pago > 0 else obtener_tasa_moneda_a_cop(db, pago)
    else:
        base_cod, quote_cod = _resolver_par(ref_cod, pago_cod)
        if not tasa_pago or tasa_pago <= 0:
            raise ValueError(
                f"Indica la tasa de cambio: 1 {base_cod} = ? {quote_cod} "
                "(la tasa se ingresa manualmente en cada operación)."
            )
        tasa_dec = Decimal(str(tasa_pago))

        # Conversión del monto a debitar de la cuenta (en moneda pago_cod):
        if ref_cod == base_cod and pago_cod == quote_cod:
            monto = (total_ref * tasa_dec).quantize(Decimal("0.01"))
        else:
            monto = (total_ref / tasa_dec).quantize(Decimal("0.01"))

        gasto_moneda = pago

        # Tasa de cambio hacia COP para la contabilidad del Gasto:
        if pago == MONEDA_BASE_ID:
            tasa = Decimal("1.0")
        elif ref_moneda_id == MONEDA_BASE_ID:
            tasa = tasa_dec
        else:
            tasa = obtener_tasa_moneda_a_cop(db, pago)

    tipo_gasto = db.query(TipoGasto).filter(TipoGasto.nombre == tipo_gasto_nombre).first()
    if not tipo_gasto:
        tipo_gasto = TipoGasto(nombre=tipo_gasto_nombre, categoria="OPERATIVO")
        db.add(tipo_gasto)
        db.flush()

    return crear_gasto(
        db,
        GastoCreate(
            tipo_gasto_id=tipo_gasto.id,
            moneda_id=gasto_moneda,
            fecha=fecha or hoy_ve(),
            descripcion=descripcion,
            monto=monto.quantize(Decimal("0.01")),
            tasa_cambio=tasa,
            metodo_caja_id=metodo_caja_id,
            observaciones="Generado automáticamente por entrada de inventario",
        ),
        commit=False,
        usuario=usuario,
    )


def obtener_inventario(
    db: Session,
    material_id: Optional[int] = None,
    ubicacion_id: Optional[int] = None ) -> List[schemas.InventarioResponse]:
    """
    Retorna el stock actual de materiales por ubicación.
    Opcionalmente filtra por material y/o ubicación.
    """
    query = db.query(model.Inventario).options(
        joinedload(model.Inventario.material).joinedload(Material.unidad_medida),
        joinedload(model.Inventario.material).joinedload(Material.categoria_inventario),
        joinedload(model.Inventario.ubicacion)
    )
    if material_id:
        query = query.filter(model.Inventario.material_id == material_id)
    if ubicacion_id:
        query = query.filter(model.Inventario.ubicacion_id == ubicacion_id)

    resultados = query.all()
    return [
        schemas.InventarioResponse(
            id=inv.id,
            material_id=inv.material_id,
            material_nombre=inv.material.nombre,
            ubicacion_id=inv.ubicacion_id,
            ubicacion_nombre=inv.ubicacion.nombre,
            cantidad=inv.cantidad,
            material_largo_cm=inv.material.largo_cm,
            material_ancho_cm=inv.material.ancho_cm,
            material_unidad=inv.material.unidad_medida.abreviatura if inv.material.unidad_medida else None,
            categoria_inventario_id=inv.material.categoria_inventario_id,
            categoria_inventario_nombre=inv.material.categoria_inventario.nombre if inv.material.categoria_inventario else None,
            created_at=inv.created_at,
            updated_at=inv.updated_at
        )
        for inv in resultados
    ]


def obtener_stock_material(db: Session, material_id: int, ubicacion_id: int) -> Decimal:
    """Devuelve la cantidad disponible de un material en una ubicación específica."""
    inv = db.query(model.Inventario).filter(
        model.Inventario.material_id == material_id,
        model.Inventario.ubicacion_id == ubicacion_id
    ).first()
    return inv.cantidad if inv else Decimal(0)



def _ubicacion_deposito_predeterminada(db: Session) -> int:
    """Depósito destino por defecto de los movimientos manuales de insumos.

    El formulario ya no pide almacén (los insumos se organizan por
    departamentos): se busca el depósito principal activo, sin hardcodear ids.
    """
    deposito = db.query(Ubicacion).filter(
        Ubicacion.activo == True,
        Ubicacion.tipo == "DEPOSITO",
    ).order_by(Ubicacion.nombre).first()
    if deposito:
        return deposito.id
    cualquiera = db.query(Ubicacion).filter(Ubicacion.activo == True).order_by(Ubicacion.id).first()
    if cualquiera:
        return cualquiera.id
    raise ValueError("No hay ubicaciones activas para registrar el movimiento.")


def registrar_movimiento(db: Session, movimiento: schemas.MovimientoCreate, usuario=None) -> model.MovimientoInventario:
    """
    Registra un movimiento de inventario (entrada, salida, ajuste, etc.)
    y actualiza la cantidad en la tabla inventario.
    """
    if movimiento.cantidad < 0 or (movimiento.cantidad == 0 and movimiento.tipo != "AJUSTE"):
        raise ValueError("La cantidad debe ser positiva (solo un AJUSTE puede quedar en 0)")

    # El CHECK de la BD solo conoce 'DANO' (sin Ñ): normalizamos antes de
    # persistir para que el tipo "DAÑO" de la UI no termine en un 409 falso
    # de "conflicto simultáneo".
    if movimiento.tipo == "DAÑO":
        movimiento.tipo = "DANO"

    # Fecha real del movimiento: por defecto hoy; admite un día anterior
    # (compras registradas tarde). Rige también el gasto/deuda generados.
    fecha_mov = _fecha_movimiento(getattr(movimiento, "fecha", None))

    # El formulario de insumos ya no pide almacén (la organización es por
    # departamentos): sin ubicación, el movimiento va al depósito principal.
    if movimiento.ubicacion_id is None:
        movimiento.ubicacion_id = _ubicacion_deposito_predeterminada(db)

    # Obtener o crear el registro de inventario para ese material y ubicación.
    # FOR UPDATE bloquea la fila para que dos SALIDAS concurrentes no lean el
    # mismo stock y descuenten dos veces (race condition).
    inventario = db.query(model.Inventario).filter(
        model.Inventario.material_id == movimiento.material_id,
        model.Inventario.ubicacion_id == movimiento.ubicacion_id
    ).with_for_update().first()

    if not inventario:
        try:
            # Savepoint: si dos requests crean la fila a la vez, el único
            # constraint (uq_inventario_material_ubicacion) permite capturar el
            # conflicto y re-leer la fila del ganador en vez de lanzar 500.
            with db.begin_nested():
                inventario = model.Inventario(
                    material_id=movimiento.material_id,
                    ubicacion_id=movimiento.ubicacion_id,
                    cantidad=Decimal(0)
                )
                db.add(inventario)
                db.flush()
        except IntegrityError:
            inventario = db.query(model.Inventario).filter(
                model.Inventario.material_id == movimiento.material_id,
                model.Inventario.ubicacion_id == movimiento.ubicacion_id
            ).with_for_update().first()
            if not inventario:
                raise

    # Aplicar cambio según tipo de movimiento
    if movimiento.tipo == "ENTRADA":
        inventario.cantidad += movimiento.cantidad
        # Actualizar costo_base del material al instante con el último precio de entrada
        if movimiento.costo_unitario is not None:
            material = db.query(Material).filter(Material.id == movimiento.material_id).first()
            if material:
                material.costo_base = Decimal(str(movimiento.costo_unitario))
    elif movimiento.tipo in ("SALIDA", "DAÑO", "DANO"):
        if inventario.cantidad < movimiento.cantidad:
            raise ValueError(f"Stock insuficiente. Disponible: {inventario.cantidad}")
        inventario.cantidad -= movimiento.cantidad
    elif movimiento.tipo == "AJUSTE":
        inventario.cantidad = movimiento.cantidad
    elif movimiento.tipo == "DEVOLUCION":
        inventario.cantidad += movimiento.cantidad
    else:
        raise ValueError(f"Tipo de movimiento inválido: {movimiento.tipo}")

    # Crear el registro de movimiento
    proveedor_id, proveedor_nombre, cliente_id, cliente_nombre = _resolver_proveedor_cliente(
        db,
        getattr(movimiento, "proveedor_id", None),
        getattr(movimiento, "proveedor_nombre", None),
        getattr(movimiento, "cliente_id", None),
        getattr(movimiento, "cliente_nombre", None),
    )
    if proveedor_id is not None and not db.query(Proveedor).filter(Proveedor.id == proveedor_id).first():
        raise ValueError(f"El proveedor #{proveedor_id} no existe.")
    if cliente_id is not None and not db.query(Client).filter(Client.id == cliente_id).first():
        raise ValueError(f"El cliente #{cliente_id} no existe.")

    db_mov = model.MovimientoInventario(
        material_id=movimiento.material_id,
        ubicacion_id=movimiento.ubicacion_id,
        tipo=movimiento.tipo,
        cantidad=movimiento.cantidad,
        costo_unitario=movimiento.costo_unitario,
        llevada=getattr(movimiento, "llevada", None),
        proveedor_id=proveedor_id,
        cliente_id=cliente_id,
        proveedor_nombre=proveedor_nombre,
        cliente_nombre=cliente_nombre,
        departamento=getattr(movimiento, "departamento", None),
        recibido_por=getattr(movimiento, "recibido_por", None),
        consumido_por=getattr(movimiento, "consumido_por", None),
        pagado_desde_metodo_caja_id=getattr(movimiento, "pagado_desde_metodo_caja_id", None),
        moneda_pago_id=getattr(movimiento, "moneda_pago_id", None),
        tasa_pago=getattr(movimiento, "tasa_pago", None),
        descuento_porcentaje=getattr(movimiento, "descuento_porcentaje", None),
        fiar=bool(getattr(movimiento, "fiar", False)),
        referencia_tipo=movimiento.referencia_tipo,
        referencia_id=movimiento.referencia_id,
        observaciones=movimiento.observaciones,
        fecha=fecha_mov
    )
    db.add(db_mov)
    # IMPORTANTE: flush, NO commit. Un commit aquí rompería la transacción del
    # llamador (compra/producción): si algo falla después, la compra, el detalle y
    # el movimiento ya quedarían persistidos a medias. El caller commitea al final.
    db.flush()
    db.refresh(db_mov)

    # ── Compra de contado: gasto + salida de caja ─────────────────────────
    # SOLO con el campo explícito nuevo: registrar_movimiento también lo llaman
    # compras y reversas de producción; dispararlo por "es ENTRADA" crearía
    # gastos fantasma. Insumos se referencian en COP → sin tasa salvo que se
    # pague desde una cuenta en otra moneda.
    # Los insumos de OFICINA se clasifican como PAPELERÍA DE OFICINA
    # (ADMINISTRATIVO) para que el gasto caiga en la línea correcta del P&L.
    es_oficina = (getattr(movimiento, "departamento", None) or "").strip().upper() == "OFICINA"
    tipo_gasto_compra = "PAPELERIA DE OFICINA" if es_oficina else "COMPRA DE INSUMOS"
    if (
        movimiento.tipo == "ENTRADA"
        and getattr(movimiento, "pagado_desde_metodo_caja_id", None)
        and movimiento.costo_unitario is not None
        and Decimal(str(movimiento.costo_unitario)) > 0
    ):
        gasto_compra = _gasto_compra_contado(
            db,
            tipo_gasto_nombre=tipo_gasto_compra,
            descripcion=f"Compra {material.nombre} x{movimiento.cantidad}",
            total_ref=(Decimal(str(movimiento.costo_unitario)) * movimiento.cantidad).quantize(Decimal("0.01")),
            ref_moneda_id=MONEDA_BASE_ID,
            metodo_caja_id=movimiento.pagado_desde_metodo_caja_id,
            moneda_pago_id=getattr(movimiento, "moneda_pago_id", None),
            tasa_pago=getattr(movimiento, "tasa_pago", None),
            fecha=fecha_mov.date(),
        )
        if gasto_compra is not None:
            db_mov.gasto_id = gasto_compra.id
            db.flush()

    # ── "La llevada" (flete/aduana): gasto aparte, misma cuenta ────────────
    # Además del dinero de la compra, pagan el flete para que el insumo pase.
    # Opcional: solo si la ENTRADA se pagó desde una cuenta y hay llevada > 0.
    llevada = getattr(movimiento, "llevada", None)
    if (
        movimiento.tipo == "ENTRADA"
        and getattr(movimiento, "pagado_desde_metodo_caja_id", None)
        and llevada is not None
        and Decimal(str(llevada)) > 0
    ):
        mat_ll = db.query(Material).filter(Material.id == movimiento.material_id).first()
        _gasto_compra_contado(
            db,
            tipo_gasto_nombre="FLETE / LLEVADA DE INSUMO",
            descripcion=f"Llevada (flete/aduana) de {mat_ll.nombre if mat_ll else 'insumo'} x{movimiento.cantidad}",
            total_ref=Decimal(str(llevada)).quantize(Decimal("0.01")),
            ref_moneda_id=MONEDA_BASE_ID,
            metodo_caja_id=movimiento.pagado_desde_metodo_caja_id,
            moneda_pago_id=getattr(movimiento, "moneda_pago_id", None),
            tasa_pago=getattr(movimiento, "tasa_pago", None),
            fecha=fecha_mov.date(),
)
    # ── "Fiar": ENTRADA sin pagar → cuenta por pagar (compra + pasada) ─────
    # El usuario se lleva el insumo hoy y queda debiendo al proveedor. La
    # deuda nace solo con el flag explícito; sin él (crédito histórico) no se
    # registra nada, igual que antes.
    fiar = getattr(movimiento, "fiar", False)
    if movimiento.tipo == "ENTRADA" and fiar:
        if getattr(movimiento, "pagado_desde_metodo_caja_id", None):
            raise ValueError("Elige entre pagar de una cuenta o fiar, no ambos.")
        # La deuda nace contra un proveedor del CATÁLOGO: si se escribió un
        # nombre libre que no coincide con ninguno, se crea (es el único caso
        # donde el nombre libre sí materializa un registro).
        if not proveedor_id and proveedor_nombre:
            proveedor_nuevo = Proveedor(nombre=proveedor_nombre)
            db.add(proveedor_nuevo)
            db.flush()
            proveedor_id = proveedor_nuevo.id
        if not proveedor_id:
            raise ValueError("Para fiar debes indicar el proveedor (campo Proveedor del movimiento).")
        if movimiento.costo_unitario is None or Decimal(str(movimiento.costo_unitario)) <= 0:
            raise ValueError("Para fiar debes indicar el costo unitario del insumo.")
        from app.modules.cuentas_por_pagar.service import crear_cuenta_desde_entrada
        from app.modules.catalogos.model import TipoGasto
        tipo_gasto_fiar = db.query(TipoGasto).filter(TipoGasto.nombre == tipo_gasto_compra).first()
        crear_cuenta_desde_entrada(
            db,
            proveedor_id=proveedor_id,
            material_id=material.id,
            material_nombre=material.nombre,
            cantidad=movimiento.cantidad,
            costo_unitario=movimiento.costo_unitario or Decimal("0.0"),
            llevada=llevada or Decimal("0.0"),
            fecha=fecha_mov.date(),
            movimiento_id=db_mov.id,
            tipo_gasto_id=tipo_gasto_fiar.id if tipo_gasto_fiar else None,
            cliente_id=cliente_id,
            cliente_nombre=cliente_nombre,
            usuario=usuario,
        )
    return db_mov


def obtener_movimientos_por_material(
    db: Session,
    material_id: int,
    limit: int = 100
) -> List[model.MovimientoInventario]:
    """
    Retorna el historial de movimientos (kardex) de un material.
    """
    movs = db.query(model.MovimientoInventario).options(
        joinedload(model.MovimientoInventario.proveedor),
        joinedload(model.MovimientoInventario.cliente),
    ).filter(
        model.MovimientoInventario.material_id == material_id
    ).order_by(model.MovimientoInventario.fecha.desc()).limit(limit).all()
    for m in movs:
        m.proveedor_nombre = m.proveedor_nombre or (m.proveedor.nombre if m.proveedor else None)
        m.cliente_nombre = m.cliente_nombre or (m.cliente.nombre if m.cliente else None)
    return movs


def costo_unitario_real_material(db: Session, material_id: int) -> dict:
    """
    Costo real por unidad de un material = costo de compra + "la pasada"
    (llevada/flete) prorrateada sobre las unidades de la última entrada.

    La llevada se registra como monto TOTAL del flete en la entrada; para el
    costo unitario real se reparte entre lo comprado en esa entrada:
        pasada_unitaria = llevada / cantidad_entrada
        costo_real       = costo_unitario + pasada_unitaria

    Si el material nunca tuvo entrada con costo (o la entrada no tuvo llevada),
    se usa `material.costo_base` como costo de compra y pasada = 0.
    """
    material = db.query(Material).filter(Material.id == material_id).first()
    if not material:
        raise ValueError("El material no existe.")

    costo_compra = float(material.costo_base or 0)
    pasada_unitaria = 0.0

    ultima_entrada = db.query(model.MovimientoInventario).filter(
        model.MovimientoInventario.material_id == material_id,
        model.MovimientoInventario.tipo == "ENTRADA",
        model.MovimientoInventario.costo_unitario.isnot(None),
        # Solo sirve una entrada que aporte costo: las cargas iniciales suelen
        # venir con costo_unitario = 0 y borrarían el costo del catálogo. Una
        # entrada con costo 0 pero con "la pasada" (flete) sí aporta costo real.
        or_(
            model.MovimientoInventario.costo_unitario > 0,
            model.MovimientoInventario.llevada > 0,
        ),
    ).order_by(
        model.MovimientoInventario.fecha.desc(),
        model.MovimientoInventario.id.desc(),
    ).first()

    if ultima_entrada is not None:
        costo_compra = float(ultima_entrada.costo_unitario)
        cantidad = ultima_entrada.cantidad
        llevada = ultima_entrada.llevada
        if llevada is not None and Decimal(str(llevada)) > 0 and cantidad and Decimal(str(cantidad)) > 0:
            pasada_unitaria = float(Decimal(str(llevada)) / Decimal(str(cantidad)))

    costo_real = round(costo_compra + pasada_unitaria, 2)
    return {
        "material_id": material_id,
        "costo_compra": round(costo_compra, 2),
        "pasada_unitaria": round(pasada_unitaria, 2),
        "costo_real": costo_real,
    }


def obtener_alertas_stock(
    db: Session,
    umbral: Decimal = Decimal(8)   # umbral por defecto si el material no tiene stock_minimo
) -> List[schemas.AlertaStockResponse]:
    """
    Retorna todos los materiales cuyo stock actual es menor o igual a su
    stock_minimo configurado (columna material.stock_minimo, default 8).
    Los materiales sin fila de inventario con cantidad 0 también alertan.
    """
    # Todos los materiales activos + su stock actual agregado
    resultados = db.query(model.Inventario).options(
        joinedload(model.Inventario.material),
        joinedload(model.Inventario.ubicacion)
    ).all()

    alertas = []
    por_material = {}
    for inv in resultados:
        key = (inv.material_id, inv.ubicacion_id)
        por_material[key] = inv

    # Materiales que SÍ tienen fila de inventario
    for (mat_id, ubi_id), inv in por_material.items():
        minimo = inv.material.stock_minimo if inv.material.stock_minimo is not None else umbral
        if inv.cantidad <= minimo:
            alertas.append(schemas.AlertaStockResponse(
                material_id=inv.material_id,
                material_nombre=inv.material.nombre,
                stock_actual=inv.cantidad,
                stock_minimo=minimo,
                ubicacion_id=inv.ubicacion_id,
                ubicacion_nombre=inv.ubicacion.nombre,
            ))

    # Materiales activos SIN ninguna fila de inventario (stock = 0) también alertan
    mats_con_stock = {mat_id for (mat_id, _) in por_material}
    materiales_sin_fila = db.query(Material).options(
        joinedload(Material.unidad_medida)
    ).filter(Material.activo == True).all()
    for mat in materiales_sin_fila:
        if mat.id in mats_con_stock:
            continue
        minimo = mat.stock_minimo if mat.stock_minimo is not None else umbral
        if Decimal("0") <= minimo:
            alertas.append(schemas.AlertaStockResponse(
                material_id=mat.id,
                material_nombre=mat.nombre,
                stock_actual=Decimal("0"),
                stock_minimo=minimo,
                ubicacion_id=0,
                ubicacion_nombre="Sin ubicación",
            ))

    return alertas


# =========================================================================
# Inventario de PRODUCTOS (terminados / de reventa)
# =========================================================================

def obtener_inventario_productos(
    db: Session,
    producto_id: Optional[int] = None,
    ubicacion_id: Optional[int] = None,
    solo_reventa: bool = False,
) -> List[schemas.ProductoInventarioResponse]:
    """Stock actual de productos (terminados/de reventa) por ubicación.

    Con solo_reventa=True solo devuelve productos marcados es_reventa
    (los que la empresa compra para revender: colchones, neveras, etc.).
    """
    query = db.query(model.ProductoInventario).options(
        joinedload(model.ProductoInventario.producto),
        joinedload(model.ProductoInventario.ubicacion),
    )
    if solo_reventa:
        query = query.join(Producto, model.ProductoInventario.producto_id == Producto.id).filter(Producto.es_reventa == True)
    if producto_id:
        query = query.filter(model.ProductoInventario.producto_id == producto_id)
    if ubicacion_id:
        query = query.filter(model.ProductoInventario.ubicacion_id == ubicacion_id)

    resultados = query.all()
    return [
        schemas.ProductoInventarioResponse(
            id=inv.id,
            producto_id=inv.producto_id,
            producto_nombre=inv.producto.nombre if inv.producto else None,
            producto_codigo=inv.producto.codigo if inv.producto else None,
            es_reventa=inv.producto.es_reventa if inv.producto else None,
            ubicacion_id=inv.ubicacion_id,
            ubicacion_nombre=inv.ubicacion.nombre if inv.ubicacion else None,
            cantidad=inv.cantidad,
            costo_promedio=inv.costo_promedio,
            stock_minimo=inv.producto.stock_minimo if inv.producto else None,
            created_at=inv.created_at,
            updated_at=inv.updated_at,
        )
        for inv in resultados
    ]


def registrar_movimiento_producto(
    db: Session,
    movimiento: schemas.MovimientoProductoCreate,
    usuario=None,
) -> model.MovimientoProductoInventario:
    """
    Registra un movimiento de inventario de producto (entrada, salida, ajuste...)
    y actualiza la cantidad + costo en producto_inventario.

    Si el movimiento es ENTRADA y trae costo_unitario, el costo_promedio del
    producto se actualiza AL INSTANTE con el último precio (no promedio).
    """
    if movimiento.cantidad <= 0:
        raise ValueError("La cantidad debe ser positiva")

    # Fecha real del movimiento: por defecto hoy; admite un día anterior.
    # Rige también el gasto/deuda generados por la compra.
    fecha_mov = _fecha_movimiento(getattr(movimiento, "fecha", None))

    producto = db.query(Producto).filter(Producto.id == movimiento.producto_id).first()
    if not producto:
        raise ValueError(f"El producto con id {movimiento.producto_id} no existe.")

    inv = db.query(model.ProductoInventario).filter(
        model.ProductoInventario.producto_id == movimiento.producto_id,
        model.ProductoInventario.ubicacion_id == movimiento.ubicacion_id,
    ).with_for_update().first()

    if not inv:
        try:
            with db.begin_nested():
                inv = model.ProductoInventario(
                    producto_id=movimiento.producto_id,
                    ubicacion_id=movimiento.ubicacion_id,
                    cantidad=Decimal(0),
                    costo_promedio=None,
                )
                db.add(inv)
                db.flush()
        except IntegrityError:
            inv = db.query(model.ProductoInventario).filter(
                model.ProductoInventario.producto_id == movimiento.producto_id,
                model.ProductoInventario.ubicacion_id == movimiento.ubicacion_id,
            ).with_for_update().first()
            if not inv:
                raise

    # Aplicar cambio según tipo de movimiento
    if movimiento.tipo == "ENTRADA":
        inv.cantidad += movimiento.cantidad
        # El costo se actualiza AL INSTANTE con el último precio de entrada.
        # No se usa promedio ponderado: si el insumo sube, el nuevo precio
        # rige desde ya para nuevas cotizaciones/pedidos.
        if movimiento.costo_unitario is not None:
            inv.costo_promedio = Decimal(str(movimiento.costo_unitario))
            # El costo de referencia del producto solo lo actualiza la compra
            # de REVENTA (su costo ES el de la última compra). Un fabricado
            # toma su costo de la receta/producción: una entrada manual
            # (p. ej. carga de piezas de exhibición) no debe pisarlo.
            if producto.es_reventa:
                producto.precio_costo_base = Decimal(str(movimiento.costo_unitario))
    elif movimiento.tipo in ("SALIDA", "DAÑO", "DANO"):
        if inv.cantidad < movimiento.cantidad:
            raise ValueError(f"Stock insuficiente. Disponible: {inv.cantidad}")
        inv.cantidad -= movimiento.cantidad
    elif movimiento.tipo == "AJUSTE":
        inv.cantidad = movimiento.cantidad
    elif movimiento.tipo == "DEVOLUCION":
        inv.cantidad += movimiento.cantidad
    else:
        raise ValueError(f"Tipo de movimiento inválido: {movimiento.tipo}")

    proveedor_id, proveedor_nombre, cliente_id, cliente_nombre = _resolver_proveedor_cliente(
        db,
        getattr(movimiento, "proveedor_id", None),
        getattr(movimiento, "proveedor_nombre", None),
        getattr(movimiento, "cliente_id", None),
        getattr(movimiento, "cliente_nombre", None),
    )
    if proveedor_id is not None and not db.query(Proveedor).filter(Proveedor.id == proveedor_id).first():
        raise ValueError(f"El proveedor #{proveedor_id} no existe.")
    if cliente_id is not None and not db.query(Client).filter(Client.id == cliente_id).first():
        raise ValueError(f"El cliente #{cliente_id} no existe.")

    db_mov = model.MovimientoProductoInventario(
        producto_id=movimiento.producto_id,
        ubicacion_id=movimiento.ubicacion_id,
        tipo=movimiento.tipo,
        cantidad=movimiento.cantidad,
        costo_unitario=movimiento.costo_unitario,
        llevada=getattr(movimiento, "llevada", None),
        proveedor_id=proveedor_id,
        cliente_id=cliente_id,
        proveedor_nombre=proveedor_nombre,
        cliente_nombre=cliente_nombre,
        pagado_desde_metodo_caja_id=getattr(movimiento, "pagado_desde_metodo_caja_id", None),
        descuento_porcentaje=getattr(movimiento, "descuento_porcentaje", None),
        fiar=bool(getattr(movimiento, "fiar", False)),
        referencia_tipo=movimiento.referencia_tipo,
        referencia_id=movimiento.referencia_id,
        observaciones=movimiento.observaciones,
        fecha=fecha_mov,
    )
    db.add(db_mov)

    # ── Egreso automático de compra (reventa de contado) ─────────────────
    # ENTRADA con costo + cuenta elegida = dinero que sale de esa caja.
    # Genera el gasto "COMPRA INVENTARIO REVENTA" en la MISMA transacción
    # (el router commitea al final) para que la utilidad bruta sea real:
    # la venta ya ingresa a caja; sin esto el costo nunca aparecería.
    if (
        movimiento.tipo == "ENTRADA"
        and movimiento.pagado_desde_metodo_caja_id
        and movimiento.costo_unitario is not None
        and Decimal(str(movimiento.costo_unitario)) > 0
        and producto.es_reventa
    ):
        costo_total = (Decimal(str(movimiento.costo_unitario)) * movimiento.cantidad).quantize(Decimal("0.01"))
        _gasto_compra_contado(
            db,
            tipo_gasto_nombre="COMPRA INVENTARIO REVENTA",
            descripcion=f"Compra inventario reventa — {producto.nombre} x{movimiento.cantidad}",
            total_ref=costo_total,
            ref_moneda_id=producto.moneda_id or 1,
            metodo_caja_id=movimiento.pagado_desde_metodo_caja_id,
            moneda_pago_id=getattr(movimiento, "moneda_pago_id", None),
            tasa_pago=getattr(movimiento, "tasa_pago", None),
            fecha=fecha_mov.date(),
            usuario=usuario,
        )

    # ── "La llevada" (flete/aduana) de productos de reventa ───────────────
    # Misma mecánica que la compra: gasto aparte desde la misma cuenta.
    llevada = getattr(movimiento, "llevada", None)
    if (
        movimiento.tipo == "ENTRADA"
        and movimiento.pagado_desde_metodo_caja_id
        and llevada is not None
        and Decimal(str(llevada)) > 0
    ):
        _gasto_compra_contado(
            db,
            tipo_gasto_nombre="FLETE / LLEVADA REVENTA",
            descripcion=f"Llevada (flete/aduana) de reventa — {producto.nombre} x{movimiento.cantidad}",
            total_ref=Decimal(str(llevada)).quantize(Decimal("0.01")),
            ref_moneda_id=producto.moneda_id or 1,
            metodo_caja_id=movimiento.pagado_desde_metodo_caja_id,
            moneda_pago_id=getattr(movimiento, "moneda_pago_id", None),
            tasa_pago=getattr(movimiento, "tasa_pago", None),
            fecha=fecha_mov.date(),
            usuario=usuario,
        )

    # ── "Fiar": ENTRADA sin pagar → cuenta por pagar (igual que insumos) ───
    fiar = getattr(movimiento, "fiar", False)
    if movimiento.tipo == "ENTRADA" and fiar:
        _fiar_entrada_producto(
            db, db_mov, producto, movimiento, proveedor_id, proveedor_nombre,
            cliente_id, cliente_nombre, llevada, usuario,
        )

    db.flush()
    db.refresh(db_mov)
    return db_mov


def _fiar_entrada_producto(db, db_mov, producto, movimiento, proveedor_id, proveedor_nombre,
                           cliente_id, cliente_nombre, llevada, usuario=None):
    """Crea la cuenta por pagar de una ENTRADA fiada de producto (misma
    mecánica que en insumos). NO hace commit (el llamador lo hace)."""
    if getattr(movimiento, "pagado_desde_metodo_caja_id", None):
        raise ValueError("Elige entre pagar de una cuenta o fiar, no ambos.")
    if not proveedor_id and proveedor_nombre:
        proveedor_nuevo = Proveedor(nombre=proveedor_nombre)
        db.add(proveedor_nuevo)
        db.flush()
        proveedor_id = proveedor_nuevo.id
    if not proveedor_id:
        raise ValueError("Para fiar debes indicar el proveedor (campo Proveedor del movimiento).")
    if movimiento.costo_unitario is None or Decimal(str(movimiento.costo_unitario)) <= 0:
        raise ValueError("Para fiar debes indicar el costo unitario del producto.")
    from app.modules.cuentas_por_pagar.service import crear_cuenta_desde_entrada
    crear_cuenta_desde_entrada(
        db,
        proveedor_id=proveedor_id,
        producto_id=producto.id,
        producto_nombre=producto.nombre,
        cantidad=movimiento.cantidad,
        costo_unitario=Decimal(str(movimiento.costo_unitario)),
        llevada=Decimal(str(llevada)) if llevada else Decimal("0.0"),
        fecha=db_mov.fecha.date(),
        movimiento_id=db_mov.id,
        cliente_id=cliente_id,
        cliente_nombre=cliente_nombre,
        usuario=usuario,
    )


def obtener_movimientos_producto(
    db: Session,
    producto_id: int,
    limit: int = 100,
) -> List[model.MovimientoProductoInventario]:
    """Historial (kardex) de movimientos de un producto."""
    movs = db.query(model.MovimientoProductoInventario).options(
        joinedload(model.MovimientoProductoInventario.proveedor),
        joinedload(model.MovimientoProductoInventario.cliente),
    ).filter(
        model.MovimientoProductoInventario.producto_id == producto_id
    ).order_by(model.MovimientoProductoInventario.fecha.desc()).limit(limit).all()
    for m in movs:
        m.proveedor_nombre = m.proveedor_nombre or (m.proveedor.nombre if m.proveedor else None)
        m.cliente_nombre = m.cliente_nombre or (m.cliente.nombre if m.cliente else None)
    return movs


def obtener_alertas_stock_productos(
    db: Session,
    umbral: Decimal = Decimal(8),
) -> List[schemas.AlertaStockProductoResponse]:
    """Productos de REVENTA cuyo stock actual es menor o igual a su stock_minimo."""
    resultados = db.query(model.ProductoInventario).join(
        Producto, model.ProductoInventario.producto_id == Producto.id
    ).options(
        joinedload(model.ProductoInventario.producto),
        joinedload(model.ProductoInventario.ubicacion),
    ).filter(Producto.es_reventa == True).all()

    alertas = []
    por_producto = {}
    for inv in resultados:
        por_producto[(inv.producto_id, inv.ubicacion_id)] = inv

    for (prod_id, ubi_id), inv in por_producto.items():
        minimo = inv.producto.stock_minimo if inv.producto and inv.producto.stock_minimo is not None else umbral
        if inv.cantidad <= minimo:
            alertas.append(schemas.AlertaStockProductoResponse(
                producto_id=inv.producto_id,
                producto_nombre=inv.producto.nombre if inv.producto else str(prod_id),
                stock_actual=inv.cantidad,
                stock_minimo=minimo,
                ubicacion_id=inv.ubicacion_id,
                ubicacion_nombre=inv.ubicacion.nombre if inv.ubicacion else "",
            ))

    return alertas


# =========================================================================
# Libro de Entradas y Salidas (control operativo por rango de fechas)
#
# Une los tres kardex (materiales, productos y crudo) en un solo listado:
# qué entró y qué salió en el período, con su zona del taller (departamento)
# y su origen (compra, venta, producción…). SOLO LECTURA: no toca stock,
# costos ni contabilidad.
# =========================================================================

TIPOS_POR_LADO = {
    "ENTRADAS": ("ENTRADA", "DEVOLUCION"),
    "SALIDAS": ("SALIDA", "DANO", "DAÑO"),
}

# Clave de zona (departamento del taller) → etiqueta visible.
# GENERAL = insumo transversal o movimiento sin zona.
ZONAS_LIBRO = {
    "EBANISTERIA": "Ebanistería",
    "PREPARACION": "Preparación",
    "PINTURA": "Pintura",
    "TAPICERIA": "Tapicería",
    "VIDRIERIA": "Vidriería",
    "TERMINACION": "Terminación",
    "OFICINA": "Oficina",
    "GENERAL": "General",
}

_ORDEN_ZONAS = [
    "EBANISTERIA", "PREPARACION", "PINTURA", "TAPICERIA", "VIDRIERIA", "TERMINACION", "OFICINA", "GENERAL",
]

_ORIGEN_LABELS = {
    "COMPRA": "Compra",
    "VENTA": "Venta",
    "PRODUCCION": "Producción",
    "PRODUCCION_EXHIBICION": "Producción (exhibición)",
    "produccion": "Producción",
    "produccion_crudo": "Producción de crudo",
    "ENTRADA_OFICINA": "Entrada de oficina",
    "CONSUMO_OFICINA": "Consumo de oficina",
    "CONTEO_OFICINA": "Conteo de oficina",
    "ASIGNACION": "Asignación a pedido",
    "STOCK_INICIAL": "Carga inicial",
    "CARGA_INICIAL": "Carga inicial",
    "inventario_inicial": "Inventario inicial",
    "INVENTARIO_INICIAL": "Inventario inicial",
    "IMPORTACION MANAPLAS": "Importación Manaplas",
    "AJUSTE": "Ajuste",
}


def _clave_departamento(valor) -> Optional[str]:
    """Normaliza una zona a su clave canónica ('Ebanistería' → 'EBANISTERIA').

    Devuelve None si no es una zona válida del taller (p. ej. 'Depósito')."""
    if not valor:
        return None
    s = unicodedata.normalize("NFD", str(valor).upper())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn").strip()
    s = s.split("(")[0].strip().replace(" ", "_")
    return s if s in ZONAS_LIBRO else None


def _etiqueta_origen(referencia_tipo, referencia_id) -> str:
    if not referencia_tipo:
        return "Manual"
    label = _ORIGEN_LABELS.get(referencia_tipo) or referencia_tipo.replace("_", " ").capitalize()
    if referencia_id and referencia_tipo.upper() in ("COMPRA", "VENTA"):
        return f"{label} #{referencia_id}"
    return label


def _datos_consumos(db: Session, ids_consumo: List[int], ids_consumo_crudo: List[int]) -> dict:
    """Costo unitario y zona de los consumos referenciados por las SALIDAS.

    La zona de una salida de producción es el área de su etapa (producción por
    pedido) o el área del ítem en crudo (producción de crudo). El costo real
    también vive en el consumo, no en el movimiento."""
    datos: dict = {}
    if ids_consumo:
        from app.modules.production.model import ConsumoMaterial, EtapaProduccion
        filas = (
            db.query(ConsumoMaterial.id, ConsumoMaterial.costo_unitario, Area.nombre)
            .join(EtapaProduccion, ConsumoMaterial.etapa_produccion_id == EtapaProduccion.id)
            .outerjoin(Area, EtapaProduccion.area_id == Area.id)
            .filter(ConsumoMaterial.id.in_(ids_consumo))
            .all()
        )
        for consumo_id, costo, area_nombre in filas:
            datos[("produccion", consumo_id)] = {
                "costo": costo, "zona": _clave_departamento(area_nombre),
            }
    if ids_consumo_crudo:
        from app.modules.production.model import (
            ProductoCrudoInventario,
            ProduccionCrudo,
            ProduccionCrudoConsumo,
        )
        filas = (
            db.query(ProduccionCrudoConsumo.id, ProduccionCrudoConsumo.costo_unitario, Area.nombre)
            .join(ProduccionCrudo, ProduccionCrudoConsumo.produccion_crudo_id == ProduccionCrudo.id)
            .join(ProductoCrudoInventario, ProduccionCrudo.crudo_id == ProductoCrudoInventario.id)
            .outerjoin(Area, ProductoCrudoInventario.area_id == Area.id)
            .filter(ProduccionCrudoConsumo.id.in_(ids_consumo_crudo))
            .all()
        )
        for consumo_id, costo, area_nombre in filas:
            datos[("produccion_crudo", consumo_id)] = {
                "costo": costo, "zona": _clave_departamento(area_nombre),
            }
    return datos


def _costos_compras(db: Session, compra_ids: List[int]) -> dict:
    """{(compra_id, material_id): costo_unitario} de las compras referenciadas.

    Las entradas por compra no guardan el costo en el movimiento (el costo vive
    en el detalle de la compra); si un material se repite, se usa el primer
    renglón."""
    if not compra_ids:
        return {}
    from app.modules.purchases.model import DetalleCompra
    filas = (
        db.query(DetalleCompra.compra_id, DetalleCompra.material_id, DetalleCompra.costo_unitario)
        .filter(DetalleCompra.compra_id.in_(compra_ids))
        .all()
    )
    costos: dict = {}
    for compra_id, material_id, costo in filas:
        costos.setdefault((compra_id, material_id), costo)
    return costos


def _cuentas_de_pago(db: Session, cuenta_ids: List[int]) -> dict:
    """{metodo_caja_id: nombre} de las cuentas con las que se pagaron entradas."""
    ids = sorted({cuenta_id for cuenta_id in cuenta_ids if cuenta_id})
    if not ids:
        return {}
    from app.modules.reports.model import MetodoCaja
    return {
        cuenta_id: nombre
        for cuenta_id, nombre in db.query(MetodoCaja.id, MetodoCaja.nombre).filter(MetodoCaja.id.in_(ids)).all()
    }


def _deudas_de_movimientos(db: Session, movimiento_ids: List[int]) -> dict:
    """{movimiento_id: {proveedor, estado, material_id}} de las entradas fiadas:
    la cuenta por pagar nace con origen ENTRADA_INVENTARIO + id del movimiento.
    Insumos y productos viven en tablas distintas (los ids pueden repetirse):
    el renglón de la deuda desambigua (material_id lleno = insumo; vacío =
    producto) y quien consume filtra por el tipo que le corresponde."""
    if not movimiento_ids:
        return {}
    from app.modules.cuentas_por_pagar.model import CuentaPorPagar, DetalleCuentaPorPagar
    filas = (
        db.query(
            CuentaPorPagar.origen_id,
            CuentaPorPagar.estado,
            Proveedor.nombre,
            DetalleCuentaPorPagar.material_id,
        )
        .join(Proveedor, CuentaPorPagar.proveedor_id == Proveedor.id)
        .join(DetalleCuentaPorPagar, DetalleCuentaPorPagar.cuenta_por_pagar_id == CuentaPorPagar.id)
        .filter(
            CuentaPorPagar.origen_tipo == "ENTRADA_INVENTARIO",
            CuentaPorPagar.origen_id.in_(movimiento_ids),
            DetalleCuentaPorPagar.orden == 0,
        )
        .all()
    )
    return {
        origen_id: {
            "proveedor": proveedor_nombre,
            "estado": estado,
            "material_id": material_id,
        }
        for origen_id, estado, proveedor_nombre, material_id in filas
    }


@dataclass
class _FilaLibro:
    """Fila normalizada del libro: misma forma para los tres kardex.

    `como_dict` concentra las normalizaciones comunes (tipo DAÑO → DANO,
    cantidad numérica, costo total = cantidad × costo unitario y llevada)."""
    id: int
    item_tipo: str
    item_id: int
    item_nombre: str
    unidad: Optional[str]
    categoria: Optional[str]
    fecha: Optional[datetime]
    tipo: str
    cantidad: float | Decimal
    costo_unitario: Optional[float | Decimal]
    llevada: Optional[float | Decimal]
    zona: str
    ubicacion: Optional[str]
    origen: str
    proveedor: Optional[str]
    cliente: Optional[str]
    recibido_por: Optional[str]
    consumido_por: Optional[str]
    observaciones: Optional[str]
    # Registro de la compra (solo insumos; None/False en productos y crudo)
    descuento: Optional[float | Decimal] = None
    pagado_desde: Optional[str] = None
    fiado: bool = False
    fiado_a: Optional[str] = None
    fiado_estado: Optional[str] = None

    def como_dict(self) -> dict:
        cantidad = float(self.cantidad or 0)
        costo_unitario = float(self.costo_unitario) if self.costo_unitario is not None else None
        llevada = float(self.llevada) if self.llevada is not None else None
        descuento = float(self.descuento) if self.descuento is not None else None
        return {
            "id": self.id,
            "item_tipo": self.item_tipo,
            "item_id": self.item_id,
            "item_nombre": self.item_nombre or "",
            "unidad": self.unidad,
            "categoria": self.categoria,
            "fecha": self.fecha,
            "tipo": "DANO" if self.tipo == "DAÑO" else self.tipo,
            "cantidad": cantidad,
            "costo_unitario": costo_unitario,
            "costo_total": round(cantidad * costo_unitario, 2) if costo_unitario is not None else None,
            "llevada": llevada,
            "zona": self.zona,
            "ubicacion": self.ubicacion,
            "origen": self.origen,
            "proveedor": self.proveedor,
            "cliente": self.cliente,
            "recibido_por": self.recibido_por,
            "consumido_por": self.consumido_por,
            "observaciones": self.observaciones,
            "descuento": descuento,
            "pagado_desde": self.pagado_desde,
            "fiado": self.fiado,
            "fiado_a": self.fiado_a,
            "fiado_estado": self.fiado_estado,
        }


def _costo_y_zona_material(mov, departamento_material, datos_consumos: dict, costos_compras: dict) -> tuple:
    """Costo unitario y zona resueltos de un movimiento de material.

    Costo: lo que trae el movimiento → detalle de la compra → consumo de
    producción. Zona: departamento del movimiento → área de la etapa
    (producción) → departamento del material → 'GENERAL'."""
    datos_consumo = datos_consumos.get((mov.referencia_tipo, mov.referencia_id)) if mov.referencia_id else None
    costo_unitario = mov.costo_unitario
    if costo_unitario is None and mov.referencia_tipo == "COMPRA" and mov.referencia_id:
        costo_unitario = costos_compras.get((mov.referencia_id, mov.material_id))
    if costo_unitario is None and datos_consumo:
        costo_unitario = datos_consumo["costo"]
    zona_fila = _clave_departamento(mov.departamento)
    if zona_fila is None and datos_consumo and datos_consumo["zona"]:
        zona_fila = datos_consumo["zona"]
    if zona_fila is None:
        zona_fila = _clave_departamento(departamento_material)
    return costo_unitario, zona_fila or "GENERAL"


@dataclass
class _ConsultaResuelta:
    """Consulta ya resuelta: lado, rango de fechas y filtros del período."""
    tipos: tuple
    desde_dt: datetime
    hasta_dt: datetime
    categoria_id: Optional[int] = None
    tipo_producto_id: Optional[int] = None


def _filas_materiales(db: Session, ctx: _ConsultaResuelta) -> List[dict]:
    """Entradas/salidas de MATERIALES del período, con zona y costo resueltos.

    La zona sale del departamento del movimiento, del área de la etapa (cuando
    la referencia es una producción) o del departamento del material; el costo
    del detalle de la compra o del consumo cuando el movimiento no lo trae."""
    consulta = (
        db.query(
            model.MovimientoInventario,
            Material.nombre,
            Material.departamento,
            UnidadMedida.abreviatura,
            Ubicacion.nombre,
            CategoriaInventario.nombre,
        )
        .join(Material, model.MovimientoInventario.material_id == Material.id)
        .outerjoin(UnidadMedida, Material.unidad_medida_id == UnidadMedida.id)
        .outerjoin(Ubicacion, model.MovimientoInventario.ubicacion_id == Ubicacion.id)
        .outerjoin(CategoriaInventario, Material.categoria_inventario_id == CategoriaInventario.id)
        .options(
            joinedload(model.MovimientoInventario.proveedor),
            joinedload(model.MovimientoInventario.cliente),
        )
        .filter(
            model.MovimientoInventario.fecha >= ctx.desde_dt,
            model.MovimientoInventario.fecha < ctx.hasta_dt,
            model.MovimientoInventario.tipo.in_(ctx.tipos),
        )
    )
    if ctx.categoria_id:
        consulta = consulta.filter(Material.categoria_inventario_id == ctx.categoria_id)
    movimientos = consulta.all()

    ids_consumo = [
        m.referencia_id for m, *_ in movimientos
        if m.referencia_tipo == "produccion" and m.referencia_id
    ]
    ids_consumo_crudo = [
        m.referencia_id for m, *_ in movimientos
        if m.referencia_tipo == "produccion_crudo" and m.referencia_id
    ]
    ids_compra = [
        m.referencia_id for m, *_ in movimientos
        if m.referencia_tipo == "COMPRA" and m.referencia_id
    ]
    datos_consumos = _datos_consumos(db, ids_consumo, ids_consumo_crudo)
    costos_compras = _costos_compras(db, ids_compra)
    cuenta_pago = _cuentas_de_pago(
        db, [m.pagado_desde_metodo_caja_id for m, *_ in movimientos if m.pagado_desde_metodo_caja_id],
    )
    deudas = _deudas_de_movimientos(db, [m.id for m, *_ in movimientos])

    filas: List[dict] = []
    for mov, nombre, departamento, unidad, ubicacion_nombre, categoria in movimientos:
        costo_unitario, zona = _costo_y_zona_material(mov, departamento, datos_consumos, costos_compras)
        deuda = deudas.get(mov.id)
        if deuda and deuda["material_id"] != mov.material_id:
            deuda = None  # la deuda con ese id es de un producto, no de este insumo
        filas.append(_FilaLibro(
            id=mov.id,
            item_tipo="MATERIAL",
            item_id=mov.material_id,
            item_nombre=nombre,
            unidad=unidad,
            categoria=categoria,
            fecha=mov.fecha,
            tipo=mov.tipo,
            cantidad=mov.cantidad,
            costo_unitario=costo_unitario,
            llevada=mov.llevada,
            zona=zona,
            ubicacion=ubicacion_nombre,
            origen=_etiqueta_origen(mov.referencia_tipo, mov.referencia_id),
            proveedor=mov.proveedor_nombre or (mov.proveedor.nombre if mov.proveedor else None),
            cliente=mov.cliente_nombre or (mov.cliente.nombre if mov.cliente else None),
            recibido_por=mov.recibido_por,
            consumido_por=mov.consumido_por,
            observaciones=mov.observaciones,
            descuento=mov.descuento_porcentaje,
            pagado_desde=cuenta_pago.get(mov.pagado_desde_metodo_caja_id),
            fiado=bool(mov.fiar),
            fiado_a=deuda["proveedor"] if deuda else (mov.proveedor_nombre if mov.fiar else None),
            fiado_estado=deuda["estado"] if deuda else None,
        ).como_dict())
    return filas


def _filas_productos(db: Session, ctx: _ConsultaResuelta) -> List[dict]:
    """Entradas/salidas de PRODUCTOS del período (con categoría y tipo)."""
    consulta = (
        db.query(
            model.MovimientoProductoInventario,
            Producto.nombre,
            Ubicacion.nombre,
            CategoriaInventario.nombre,
        )
        .join(Producto, model.MovimientoProductoInventario.producto_id == Producto.id)
        .outerjoin(Ubicacion, model.MovimientoProductoInventario.ubicacion_id == Ubicacion.id)
        .outerjoin(CategoriaInventario, Producto.categoria_inventario_id == CategoriaInventario.id)
        .options(
            joinedload(model.MovimientoProductoInventario.proveedor),
            joinedload(model.MovimientoProductoInventario.cliente),
        )
        .filter(
            model.MovimientoProductoInventario.fecha >= ctx.desde_dt,
            model.MovimientoProductoInventario.fecha < ctx.hasta_dt,
            model.MovimientoProductoInventario.tipo.in_(ctx.tipos),
        )
    )
    if ctx.categoria_id:
        consulta = consulta.filter(Producto.categoria_inventario_id == ctx.categoria_id)
    if ctx.tipo_producto_id:
        consulta = consulta.filter(Producto.tipo_producto_id == ctx.tipo_producto_id)
    movimientos = consulta.all()

    cuenta_pago = _cuentas_de_pago(
        db, [m.pagado_desde_metodo_caja_id for m, *_ in movimientos if m.pagado_desde_metodo_caja_id],
    )
    deudas = _deudas_de_movimientos(db, [m.id for m, *_ in movimientos])

    filas: List[dict] = []
    for mov, nombre, ubicacion_nombre, categoria in movimientos:
        deuda = deudas.get(mov.id)
        if deuda and deuda["material_id"] is not None:
            deuda = None  # la deuda con ese id es de un insumo, no de este producto
        filas.append(_FilaLibro(
            id=mov.id,
            item_tipo="PRODUCTO",
            item_id=mov.producto_id,
            item_nombre=nombre,
            unidad=None,
            categoria=categoria,
            fecha=mov.fecha,
            tipo=mov.tipo,
            cantidad=mov.cantidad,
            costo_unitario=mov.costo_unitario,
            llevada=mov.llevada,
            zona="GENERAL",
            ubicacion=ubicacion_nombre,
            origen=_etiqueta_origen(mov.referencia_tipo, mov.referencia_id),
            proveedor=mov.proveedor_nombre or (mov.proveedor.nombre if mov.proveedor else None),
            cliente=mov.cliente_nombre or (mov.cliente.nombre if mov.cliente else None),
            recibido_por=None,
            consumido_por=None,
            observaciones=mov.observaciones,
            descuento=mov.descuento_porcentaje,
            pagado_desde=cuenta_pago.get(mov.pagado_desde_metodo_caja_id),
            fiado=bool(mov.fiar),
            fiado_a=deuda["proveedor"] if deuda else (mov.proveedor_nombre if mov.fiar else None),
            fiado_estado=deuda["estado"] if deuda else None,
        ).como_dict())
    return filas


def _filas_crudo(db: Session, ctx: _ConsultaResuelta) -> List[dict]:
    """Entradas/salidas del inventario en CRUDO (zona = área del ítem)."""
    from app.modules.production.model import MovimientoCrudo, ProductoCrudoInventario

    movimientos = (
        db.query(MovimientoCrudo, ProductoCrudoInventario.nombre, Area.nombre)
        .join(ProductoCrudoInventario, MovimientoCrudo.crudo_id == ProductoCrudoInventario.id)
        .outerjoin(Area, ProductoCrudoInventario.area_id == Area.id)
        .filter(
            MovimientoCrudo.fecha >= ctx.desde_dt,
            MovimientoCrudo.fecha < ctx.hasta_dt,
            MovimientoCrudo.tipo.in_(ctx.tipos),
        )
        .all()
    )
    return [
        _FilaLibro(
            id=mov.id,
            item_tipo="CRUDO",
            item_id=mov.crudo_id,
            item_nombre=nombre,
            unidad=None,
            categoria=None,
            fecha=mov.fecha,
            tipo=mov.tipo,
            cantidad=mov.cantidad,
            costo_unitario=None,   # el crudo no costea por movimiento
            llevada=None,
            zona=_clave_departamento(area_nombre) or "GENERAL",
            ubicacion=None,
            origen=_etiqueta_origen(mov.referencia_tipo, mov.referencia_id),
            proveedor=None,
            cliente=None,
            recibido_por=None,
            consumido_por=None,
            observaciones=mov.observaciones,
        ).como_dict()
        for mov, nombre, area_nombre in movimientos
    ]


def _acumular_por_zona(filas: List[dict]) -> List[dict]:
    """Totales por zona (movimientos, costo y cuántos sin costo), en el orden
    canónico del taller."""
    por_zona: dict = {}
    for fila in filas:
        acumulado = por_zona.setdefault(fila["zona"], {
            "zona": fila["zona"],
            "label": ZONAS_LIBRO.get(fila["zona"], fila["zona"]),
            "movimientos": 0,
            "costo": 0.0,
            "sin_costo": 0,
        })
        acumulado["movimientos"] += 1
        if fila["costo_total"] is None:
            acumulado["sin_costo"] += 1
        else:
            acumulado["costo"] = round(acumulado["costo"] + fila["costo_total"], 2)
    return sorted(
        por_zona.values(),
        key=lambda zona: (
            _ORDEN_ZONAS.index(zona["zona"]) if zona["zona"] in _ORDEN_ZONAS else len(_ORDEN_ZONAS)
        ),
    )


def _construir_resumen(lado: str, desde: date, hasta: date, filas: List[dict]) -> dict:
    """Resumen del libro: movimientos, costo acumulado y desglose por zona."""
    return {
        "lado": lado,
        "desde": desde,
        "hasta": hasta,
        "movimientos": len(filas),
        "costo_total": round(sum(fila["costo_total"] for fila in filas if fila["costo_total"] is not None), 2),
        "movimientos_sin_costo": sum(1 for fila in filas if fila["costo_total"] is None),
        "por_zona": _acumular_por_zona(filas),
    }


@dataclass
class ConsultaLibro:
    """Parámetros de una consulta al libro de entradas y salidas."""
    desde: date
    hasta: date
    lado: str
    tipo_item: str = "TODOS"
    zona: Optional[str] = None
    buscar: Optional[str] = None
    limite: int = 5000
    categoria_id: Optional[int] = None
    tipo_producto_id: Optional[int] = None


def obtener_libro_entradas_salidas(db: Session, consulta: ConsultaLibro) -> dict:
    """Entradas o salidas de inventario en un rango de fechas.

    Devuelve las filas (materiales + productos + crudo) con zona y origen, más
    un resumen con totales por zona. El lado 'ENTRADAS' agrupa ENTRADA y
    DEVOLUCION; 'SALIDAS' agrupa SALIDA y DAÑO (los AJUSTE no son flujos del
    libro: se ven en el kardex de cada ítem)."""
    lado = (consulta.lado or "").upper()
    if lado not in TIPOS_POR_LADO:
        raise ValueError("El lado debe ser ENTRADAS o SALIDAS.")
    tipo_item = (consulta.tipo_item or "TODOS").upper()
    if tipo_item not in ("TODOS", "MATERIAL", "PRODUCTO", "CRUDO"):
        raise ValueError("tipo_item debe ser TODOS, MATERIAL, PRODUCTO o CRUDO.")
    if consulta.desde > consulta.hasta:
        raise ValueError("La fecha inicial no puede ser mayor que la final.")

    ctx = _ConsultaResuelta(
        tipos=TIPOS_POR_LADO[lado],
        desde_dt=datetime.combine(consulta.desde, time.min),
        hasta_dt=datetime.combine(consulta.hasta + timedelta(days=1), time.min),
        categoria_id=consulta.categoria_id,
        tipo_producto_id=consulta.tipo_producto_id,
    )

    filas: List[dict] = []
    if tipo_item in ("TODOS", "MATERIAL"):
        filas += _filas_materiales(db, ctx)
    if tipo_item in ("TODOS", "PRODUCTO"):
        filas += _filas_productos(db, ctx)
    if tipo_item in ("TODOS", "CRUDO"):
        filas += _filas_crudo(db, ctx)

    # ── Filtros, orden y resumen ──────────────────────────────────────────
    if consulta.zona:
        objetivo = _clave_departamento(consulta.zona) or consulta.zona.strip().upper()
        filas = [fila for fila in filas if fila["zona"] == objetivo]
    if consulta.buscar:
        texto = consulta.buscar.strip().lower()
        filas = [fila for fila in filas if texto in (fila["item_nombre"] or "").lower()]

    filas.sort(key=lambda fila: (fila["fecha"] or datetime.min, fila["id"]))
    return {
        "resumen": _construir_resumen(lado, consulta.desde, consulta.hasta, filas),
        "filas": filas[:consulta.limite],
        "truncado": len(filas) > consulta.limite,
    }