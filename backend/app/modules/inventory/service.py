from sqlalchemy.orm import Session, joinedload
from sqlalchemy import and_
from sqlalchemy.exc import IntegrityError
from decimal import Decimal
from datetime import datetime
from typing import Optional, List



from app.modules.inventory import model, schemas
from app.modules.productos.model import Material, Producto
from app.modules.catalogos.model import Ubicacion
from app.modules.proveedores.model import Proveedor
from app.modules.clients.model import Client

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
    from datetime import date as _date
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

    crear_gasto(
        db,
        GastoCreate(
            tipo_gasto_id=tipo_gasto.id,
            moneda_id=gasto_moneda,
            fecha=_date.today(),
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



def registrar_movimiento(db: Session, movimiento: schemas.MovimientoCreate, usuario=None) -> model.MovimientoInventario:
    """
    Registra un movimiento de inventario (entrada, salida, ajuste, etc.)
    y actualiza la cantidad en la tabla inventario.
    """
    if movimiento.cantidad <= 0:
        raise ValueError("La cantidad debe ser positiva")

    # El CHECK de la BD solo conoce 'DANO' (sin Ñ): normalizamos antes de
    # persistir para que el tipo "DAÑO" de la UI no termine en un 409 falso
    # de "conflicto simultáneo".
    if movimiento.tipo == "DAÑO":
        movimiento.tipo = "DANO"

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
        referencia_tipo=movimiento.referencia_tipo,
        referencia_id=movimiento.referencia_id,
        observaciones=movimiento.observaciones,
        fecha=datetime.utcnow()
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
    if (
        movimiento.tipo == "ENTRADA"
        and getattr(movimiento, "pagado_desde_metodo_caja_id", None)
        and movimiento.costo_unitario is not None
        and Decimal(str(movimiento.costo_unitario)) > 0
    ):
        _gasto_compra_contado(
            db,
            tipo_gasto_nombre="COMPRA DE INSUMOS",
            descripcion=f"Compra {material.nombre} x{movimiento.cantidad}",
            total_ref=(Decimal(str(movimiento.costo_unitario)) * movimiento.cantidad).quantize(Decimal("0.01")),
            ref_moneda_id=MONEDA_BASE_ID,
            metodo_caja_id=movimiento.pagado_desde_metodo_caja_id,
            moneda_pago_id=getattr(movimiento, "moneda_pago_id", None),
            tasa_pago=getattr(movimiento, "tasa_pago", None),
        )

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
        crear_cuenta_desde_entrada(
            db,
            proveedor_id=proveedor_id,
            material_id=material.id,
            material_nombre=material.nombre,
            cantidad=movimiento.cantidad,
            costo_unitario=movimiento.costo_unitario or Decimal("0.0"),
            llevada=llevada or Decimal("0.0"),
            fecha=datetime.utcnow().date(),
            movimiento_id=db_mov.id,
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
        referencia_tipo=movimiento.referencia_tipo,
        referencia_id=movimiento.referencia_id,
        observaciones=movimiento.observaciones,
        fecha=datetime.utcnow(),
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
        fecha=datetime.utcnow().date(),
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
# Sobrantes de láminas (retazos de materiales laminares)
# =========================================================================

def _sobrante_a_response(s: model.SobranteLamina) -> schemas.SobranteLaminaResponse:
    return schemas.SobranteLaminaResponse(
        id=s.id,
        material_id=s.material_id,
        material_nombre=s.material.nombre if s.material else None,
        material_largo_cm=s.material.largo_cm if s.material else None,
        material_ancho_cm=s.material.ancho_cm if s.material else None,
        ubicacion_id=s.ubicacion_id,
        ubicacion_nombre=s.ubicacion.nombre if s.ubicacion else None,
        largo_cm=s.largo_cm,
        ancho_cm=s.ancho_cm,
        area_cm2=s.area_cm2,
        estado=s.estado,
        consumo_origen_id=s.consumo_origen_id,
        consumo_origen_tipo=s.consumo_origen_tipo,
        observaciones=s.observaciones,
        created_at=s.created_at,
        updated_at=s.updated_at,
    )


def obtener_sobrantes(
    db: Session,
    material_id: Optional[int] = None,
    estado: Optional[str] = None,
    ubicacion_id: Optional[int] = None,
) -> List[schemas.SobranteLaminaResponse]:
    query = db.query(model.SobranteLamina).options(
        joinedload(model.SobranteLamina.material).joinedload(Material.unidad_medida),
        joinedload(model.SobranteLamina.ubicacion),
    )
    if material_id:
        query = query.filter(model.SobranteLamina.material_id == material_id)
    if estado:
        query = query.filter(model.SobranteLamina.estado == estado.upper())
    if ubicacion_id:
        query = query.filter(model.SobranteLamina.ubicacion_id == ubicacion_id)
    return [_sobrante_a_response(s) for s in query.order_by(model.SobranteLamina.id.desc()).all()]


def crear_sobrante(db: Session, datos: schemas.SobranteLaminaCreate) -> schemas.SobranteLaminaResponse:
    material = db.query(Material).filter(Material.id == datos.material_id).first()
    if not material:
        raise ValueError(f"El material #{datos.material_id} no existe.")
    s = model.SobranteLamina(
        material_id=datos.material_id,
        ubicacion_id=datos.ubicacion_id,
        largo_cm=datos.largo_cm,
        ancho_cm=datos.ancho_cm,
        estado="DISPONIBLE",
        observaciones=datos.observaciones or "Registro manual de sobrante",
    )
    db.add(s)
    db.commit()
    db.refresh(s)
    return _sobrante_a_response(s)


def actualizar_sobrante(db: Session, sobrante_id: int, datos: schemas.SobranteLaminaUpdate) -> schemas.SobranteLaminaResponse:
    s = db.query(model.SobranteLamina).filter(model.SobranteLamina.id == sobrante_id).first()
    if not s:
        raise ValueError("El sobrante no existe.")
    if datos.largo_cm is not None:
        s.largo_cm = datos.largo_cm
    if datos.ancho_cm is not None:
        s.ancho_cm = datos.ancho_cm
    if datos.estado is not None:
        s.estado = datos.estado
    if datos.ubicacion_id is not None:
        s.ubicacion_id = datos.ubicacion_id
    if datos.observaciones is not None:
        s.observaciones = datos.observaciones
    db.commit()
    db.refresh(s)
    return _sobrante_a_response(s)


def eliminar_sobrante(db: Session, sobrante_id: int) -> bool:
    s = db.query(model.SobranteLamina).filter(model.SobranteLamina.id == sobrante_id).first()
    if not s:
        return False
    db.delete(s)
    db.commit()
    return True