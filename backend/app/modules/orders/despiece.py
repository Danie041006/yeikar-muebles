"""Despiece de muebles de exhibición al confirmar un pedido compuesto.

Una cotización puede combinar piezas de VARIOS muebles del showroom (la mesa
de un comedor + las sillas de otro). Al convertirla a pedido hay que:

1. Sacar del inventario los conjuntos completos que se van a despiezar
   (SALIDA), de modo que no se puedan vender dos veces.
2. Repartir el costo del conjunto entre TODAS sus piezas (pesos = costo de
   catálogo; si falta, cantidad) y congelar ese costo en cada pieza llevada.
3. Devolver al showroom las piezas que NO se llevó el cliente como piezas
   sueltas vendibles (ENTRADA), conservando el valor total del conjunto.
4. Apartar las piezas de exhibición que ya estaban sueltas (SALIDA simple).

La operación es idempotente por renglón (`detalle_pedido.piezas_apartadas`):
un reintento dentro de la misma transacción no vuelve a mover el inventario.
"""

from decimal import Decimal, ROUND_CEILING

from sqlalchemy.orm import Session

REFERENCIA_TIPO = "PRODUCCION_DESPIEZA"
UBICACION_EXHIBICION = "EXHIBICIÓN"


def _d(valor) -> Decimal:
    return Decimal(str(valor or 0))


def _redondear2(valor: Decimal) -> Decimal:
    return valor.quantize(Decimal("0.01"))


def _ubicacion_exhibicion(db: Session):
    from app.modules.catalogos.model import Ubicacion

    return db.query(Ubicacion).filter(Ubicacion.nombre == UBICACION_EXHIBICION).first()


def _mover(
    db: Session,
    *,
    producto_id: int,
    ubicacion_id: int,
    tipo: str,
    cantidad: Decimal,
    costo_unitario,
    pedido_id: int,
    observaciones: str,
    usuario=None,
) -> None:
    from app.modules.inventory.schemas import MovimientoProductoCreate
    from app.modules.inventory.service import registrar_movimiento_producto

    # El schema exige costo > 0; un costo 0/null significa "sin costo conocido".
    costo = None
    if costo_unitario is not None:
        try:
            if Decimal(str(costo_unitario)) > 0:
                costo = costo_unitario
        except Exception:  # noqa: BLE001
            costo = None

    registrar_movimiento_producto(
        db,
        MovimientoProductoCreate(
            producto_id=producto_id,
            ubicacion_id=ubicacion_id,
            tipo=tipo,
            cantidad=cantidad,
            costo_unitario=costo,
            referencia_tipo=REFERENCIA_TIPO,
            referencia_id=pedido_id,
            observaciones=observaciones,
        ),
        usuario=usuario,
    )


def _pesos_conjunto(db: Session, composicion) -> dict[int, Decimal]:
    """Peso de cada pieza del conjunto para prorratear su costo.

    Preferimos el costo de catálogo de la pieza (× cantidad en el conjunto)
    porque refleja cuánto vale cada parte. Si a alguna le falta el costo, se
    cae a la cantidad para no inventar valores.
    """
    from app.modules.productos.model import Producto
    from app.modules.productos.service import convertir_a_moneda_base

    ids = [fila.pieza_producto_id for fila in composicion]
    productos = {
        p.id: p for p in db.query(Producto).filter(Producto.id.in_(ids)).all()
    }
    costos: dict[int, Decimal | None] = {}
    for fila in composicion:
        producto = productos.get(fila.pieza_producto_id)
        costo = None
        if producto is not None and producto.precio_costo_base is not None:
            convertido = convertir_a_moneda_base(
                db, producto.moneda_id, float(producto.precio_costo_base)
            )
            if convertido is not None:
                costo = Decimal(str(convertido))
        costos[fila.pieza_producto_id] = costo

    usar_catalogo = all(c is not None and c > 0 for c in costos.values())
    pesos: dict[int, Decimal] = {}
    for fila in composicion:
        base = (
            costos[fila.pieza_producto_id]
            if usar_catalogo
            else Decimal("1")
        )
        pesos[fila.pieza_producto_id] = (base or Decimal("1")) * _d(fila.cantidad)
    return pesos


def _despiezar_conjunto(
    db: Session,
    conjunto_id: int,
    items: list[tuple],
    pedido,
    usuario=None,
) -> None:
    """Saca N conjuntos del showroom y devuelve sus sobrantes como piezas."""
    from app.modules.inventory.model import ProductoInventario
    from app.modules.productos.model import Producto, ProductoPieza
    from app.modules.productos.service import (
        convertir_a_moneda_base,
        convertir_desde_moneda_base,
    )

    conjunto = db.query(Producto).filter(Producto.id == conjunto_id).first()
    if conjunto is None:
        raise ValueError(f"El conjunto de exhibición #{conjunto_id} no existe.")

    composicion = (
        db.query(ProductoPieza)
        .filter(ProductoPieza.producto_id == conjunto_id)
        .all()
    )
    if not composicion:
        raise ValueError(
            f"El conjunto '{conjunto.nombre}' no tiene composición de piezas. "
            "Configúrala en Productos → Piezas del conjunto para poder despiezarlo."
        )
    por_producto = {fila.pieza_producto_id: fila for fila in composicion}

    # Unidades físicas que se lleva el pedido de cada pieza.
    requerido: dict[int, Decimal] = {}
    for detalle, pieza in items:
        if not pieza.producto_id:
            raise ValueError(
                f"La pieza '{pieza.nombre}' no tiene producto del catálogo; "
                "no se puede despiezar el conjunto."
            )
        cantidad = _d(pieza.cantidad) * _d(detalle.cantidad)
        requerido[int(pieza.producto_id)] = (
            requerido.get(int(pieza.producto_id), Decimal("0")) + cantidad
        )

    for producto_id in requerido:
        if producto_id not in por_producto:
            nombre = next(
                (p.nombre for _, p in items if int(p.producto_id or 0) == producto_id),
                f"#{producto_id}",
            )
            raise ValueError(
                f"La pieza '{nombre}' no forma parte del conjunto '{conjunto.nombre}'."
            )

    # Un conjunto se despieza COMPLETO: se necesitan tantos como la pieza que
    # más se lleva (2 mesas de un juego con 1 mesa ⇒ 2 juegos).
    sets = Decimal("0")
    for producto_id, cantidad in requerido.items():
        por_set = _d(por_producto[producto_id].cantidad)
        if por_set <= 0:
            continue
        sets = max(sets, (cantidad / por_set).to_integral_value(rounding=ROUND_CEILING))
    sets = max(Decimal("1"), sets)

    ubi = _ubicacion_exhibicion(db)
    if ubi is None:
        raise ValueError(
            "No existe la ubicación EXHIBICIÓN. Créala para poder despiezar muebles del showroom."
        )

    fila_conjunto = (
        db.query(ProductoInventario)
        .filter(
            ProductoInventario.producto_id == conjunto_id,
            ProductoInventario.ubicacion_id == ubi.id,
        )
        .with_for_update()
        .first()
    )
    if fila_conjunto is None:
        # Exhibición de alta simple (sin kardex): se comporta como la venta de
        # una pieza de exhibición sin stock. No se inventan movimientos ni
        # sobrantes, pero la operación no bloquea la conversión.
        return
    disponible = _d(fila_conjunto.cantidad)
    if disponible < sets:
        raise ValueError(
            f"No hay suficientes '{conjunto.nombre}' en EXHIBICIÓN para despiezar: "
            f"se necesitan {sets:g} y hay {disponible:g}."
        )

    # Costo total del conjunto (en COP) que se reparte entre todas sus piezas.
    costo_unitario_conjunto = fila_conjunto.costo_promedio
    valor_total_cop = None
    if costo_unitario_conjunto is not None:
        convertido = convertir_a_moneda_base(
            db, conjunto.moneda_id, float(costo_unitario_conjunto)
        )
        if convertido is not None:
            valor_total_cop = Decimal(str(convertido)) * sets

    piezas_conjunto = {fila.pieza_producto_id: fila.pieza for fila in composicion}
    pesos = _pesos_conjunto(db, composicion)
    total_peso = sum(pesos.values(), Decimal("0"))
    costo_unit_cop: dict[int, Decimal | None] = {pid: None for pid in pesos}
    if valor_total_cop is not None and total_peso > 0:
        for producto_id, peso in pesos.items():
            unidades_totales = _d(por_producto[producto_id].cantidad) * sets
            if unidades_totales <= 0:
                continue
            asignado = valor_total_cop * peso / total_peso
            costo_unit_cop[producto_id] = _redondear2(asignado / unidades_totales)

    # 1) Sale el conjunto completo del showroom (una sola vez).
    _mover(
        db,
        producto_id=conjunto_id,
        ubicacion_id=ubi.id,
        tipo="SALIDA",
        cantidad=sets,
        costo_unitario=costo_unitario_conjunto,
        pedido_id=pedido.id,
        observaciones=(
            f"Despiece por el pedido #{pedido.id}: "
            f"{sets:g} × {conjunto.nombre} para entregar piezas del cliente"
        ),
        usuario=usuario,
    )

    # 2) Congelar el costo de las piezas que se lleva el pedido.
    for detalle, pieza in items:
        costo = costo_unit_cop.get(int(pieza.producto_id))
        if costo is None:
            producto = piezas_conjunto.get(int(pieza.producto_id))
            if producto is not None and producto.precio_costo_base is not None:
                convertido = convertir_a_moneda_base(
                    db, producto.moneda_id, float(producto.precio_costo_base)
                )
                costo = Decimal(str(convertido)) if convertido is not None else None
        pieza.costo_unitario = float(costo) if costo is not None else None

    # 3) Sobrantes: vuelven al showroom como piezas sueltas, con su parte del
    #    valor del conjunto (el valor total se conserva).
    for producto_id, fila_comp in por_producto.items():
        unidades_set = _d(fila_comp.cantidad)
        if unidades_set <= 0:
            continue
        total_piezas = unidades_set * sets
        sobrante = total_piezas - requerido.get(producto_id, Decimal("0"))
        if sobrante <= 0:
            continue
        producto = piezas_conjunto.get(producto_id)
        if producto is None:
            continue
        costo_pieza_moneda = None
        costo_cop = costo_unit_cop.get(producto_id)
        if costo_cop is not None:
            convertido = convertir_desde_moneda_base(
                db, producto.moneda_id, float(costo_cop)
            )
            if convertido is not None:
                costo_pieza_moneda = convertido
        if costo_pieza_moneda is None and producto.precio_costo_base is not None:
            costo_pieza_moneda = float(producto.precio_costo_base)
        # El sobrante queda VENDIBLE como pieza suelta del showroom: se marca
        # como exhibición (sin tocar su receta ni su costo/precio) para que
        # Cotizaciones lo trate como stock y aparezca en Inventario → Exhibición.
        producto.es_exhibicion = True
        producto.activo = True
        _mover(
            db,
            producto_id=producto_id,
            ubicacion_id=ubi.id,
            tipo="ENTRADA",
            cantidad=sobrante,
            costo_unitario=costo_pieza_moneda,
            pedido_id=pedido.id,
            observaciones=(
                f"Sobrante del despiece de {sets:g} × {conjunto.nombre} "
                f"(pedido #{pedido.id}); queda vendible como pieza suelta"
            ),
            usuario=usuario,
        )


def _apartar_piezas_sueltas(db: Session, items: list[tuple], pedido, usuario=None) -> None:
    """Saca del stock las piezas de exhibición que ya estaban sueltas.

    Si la pieza no tiene fila de inventario (exhibición de alta simple), no se
    bloquea: se comporta como cualquier venta de exhibición sin kardex.
    """
    from app.modules.inventory.model import ProductoInventario
    from app.modules.productos.model import Producto
    from app.modules.productos.service import convertir_a_moneda_base

    ubi = _ubicacion_exhibicion(db)

    requerido: dict[int, Decimal] = {}
    for detalle, pieza in items:
        if not pieza.producto_id:
            continue
        cantidad = _d(pieza.cantidad) * _d(detalle.cantidad)
        requerido[int(pieza.producto_id)] = (
            requerido.get(int(pieza.producto_id), Decimal("0")) + cantidad
        )

    for producto_id, cantidad in requerido.items():
        filas = (
            db.query(ProductoInventario)
            .filter(ProductoInventario.producto_id == producto_id)
            .order_by(ProductoInventario.id)
            .with_for_update()
            .all()
        )
        # Preferir EXHIBICIÓN, sin ignorar stock en otras ubicaciones.
        if ubi is not None:
            filas.sort(key=lambda fila: 0 if fila.ubicacion_id == ubi.id else 1)

        producto = db.query(Producto).filter(Producto.id == producto_id).first()
        if not filas:
            # Alta simple: no hay stock que mover. El costo estimado del
            # catálogo queda como referencia (si existe).
            costo = None
            if producto is not None and producto.precio_costo_base is not None:
                convertido = convertir_a_moneda_base(
                    db, producto.moneda_id, float(producto.precio_costo_base)
                )
                costo = float(convertido) if convertido is not None else None
            for _, pieza in items:
                if int(pieza.producto_id or 0) == producto_id:
                    pieza.costo_unitario = costo
            continue

        disponible = sum((_d(f.cantidad) for f in filas), Decimal("0"))
        if disponible < cantidad:
            nombre = producto.nombre if producto else f"#{producto_id}"
            raise ValueError(
                f"No hay suficiente '{nombre}' en el inventario de exhibición: "
                f"se necesitan {cantidad:g} y hay {disponible:g}."
            )

        restante = cantidad
        costo_promedio = None
        for fila in filas:
            if restante <= 0:
                break
            a_sacar = min(restante, _d(fila.cantidad))
            if a_sacar <= 0:
                continue
            if costo_promedio is None and fila.costo_promedio is not None:
                costo_promedio = fila.costo_promedio
            _mover(
                db,
                producto_id=producto_id,
                ubicacion_id=fila.ubicacion_id,
                tipo="SALIDA",
                cantidad=a_sacar,
                costo_unitario=fila.costo_promedio,
                pedido_id=pedido.id,
                observaciones=(
                    f"Pieza de exhibición apartada para el pedido #{pedido.id}"
                ),
                usuario=usuario,
            )
            restante -= a_sacar

        costo_cop = None
        if costo_promedio is not None and producto is not None:
            convertido = convertir_a_moneda_base(
                db, producto.moneda_id, float(costo_promedio)
            )
            costo_cop = float(convertido) if convertido is not None else None
        elif producto is not None and producto.precio_costo_base is not None:
            convertido = convertir_a_moneda_base(
                db, producto.moneda_id, float(producto.precio_costo_base)
            )
            costo_cop = float(convertido) if convertido is not None else None

        for _, pieza in items:
            if int(pieza.producto_id or 0) == producto_id:
                pieza.costo_unitario = costo_cop


def despiezar_exhibicion(db: Session, pedido, usuario=None) -> None:
    """Ejecuta el despiece de un pedido (idempotente por renglón)."""
    pendientes: list[tuple] = []
    for detalle in pedido.detalles or []:
        if getattr(detalle, "piezas_apartadas", False):
            continue
        piezas = [
            pieza
            for pieza in (detalle.piezas or [])
            if str(pieza.origen or "FABRICADO").strip().upper() == "EXHIBICION"
        ]
        if piezas:
            pendientes.append((detalle, piezas))

    if not pendientes:
        return

    # Primero se despiezan los conjuntos (generan los sobrantes) y al final se
    # apartan las piezas sueltas, por si alguna consume un sobrante recién
    # devuelto al showroom.
    grupos: dict[int | None, list[tuple]] = {}
    for detalle, piezas in pendientes:
        for pieza in piezas:
            grupos.setdefault(pieza.conjunto_origen_id, []).append((detalle, pieza))

    for conjunto_id in [k for k in grupos if k is not None]:
        _despiezar_conjunto(db, int(conjunto_id), grupos[conjunto_id], pedido, usuario)
    if None in grupos:
        _apartar_piezas_sueltas(db, grupos[None], pedido, usuario)

    from app.modules.quotes.piezas import costo_unitario_desde_piezas

    for detalle, _ in pendientes:
        detalle.piezas_apartadas = True
        # El costo estimado del pedido pasa a usar el costo REAL congelado
        # de las piezas de exhibición (más fiel que el catálogo).
        costo = costo_unitario_desde_piezas(db, detalle.piezas, usar_snapshot=True)
        if costo is not None:
            detalle.costo_unitario = float(costo)

    db.flush()
