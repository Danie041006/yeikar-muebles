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


# ── Textos legibles de las compras de inventario ──────────────────────────
# El movimiento de caja y el gasto espejo se leen en el libro de caja: en vez
# de "Compra TELA CUSCO HIELO x15" se escribe
# "Compra de material: 15 metros de TELA CUSCO HIELO". Las unidades del
# catálogo son muy dispares (Metro, METROS, m, Lámina, LAMINA, ...): se
# normalizan a su forma singular/plural y, si no se reconoce, se respeta el
# nombre tal cual lo cargó el usuario.
_UNIDADES_SINGULAR_PLURAL: dict[str, tuple[str, str]] = {
    "unidad": ("unidad", "unidades"),
    "unidades": ("unidad", "unidades"),
    "ud": ("unidad", "unidades"),
    "uds": ("unidad", "unidades"),
    "un": ("unidad", "unidades"),
    "und": ("unidad", "unidades"),
    "uni": ("unidad", "unidades"),
    "unitario": ("unidad", "unidades"),
    "unitarios": ("unidad", "unidades"),
    "metro": ("metro", "metros"),
    "metros": ("metro", "metros"),
    "mts": ("metro", "metros"),
    "m": ("metro", "metros"),
    "metro cubico": ("metro cúbico", "metros cúbicos"),
    "metros cubicos": ("metro cúbico", "metros cúbicos"),
    "m3": ("metro cúbico", "metros cúbicos"),
    "centimetro": ("centímetro", "centímetros"),
    "centimetros": ("centímetro", "centímetros"),
    "cm": ("centímetro", "centímetros"),
    "cms": ("centímetro", "centímetros"),
    "kilogramo": ("kilogramo", "kilogramos"),
    "kilogramos": ("kilogramo", "kilogramos"),
    "kilo": ("kilo", "kilos"),
    "kilos": ("kilo", "kilos"),
    "kg": ("kilogramo", "kilogramos"),
    "litro": ("litro", "litros"),
    "litros": ("litro", "litros"),
    "lt": ("litro", "litros"),
    "lts": ("litro", "litros"),
    "l": ("litro", "litros"),
    "lamina": ("lámina", "láminas"),
    "laminas": ("lámina", "láminas"),
    "lam": ("lámina", "láminas"),
    "galon": ("galón", "galones"),
    "galones": ("galón", "galones"),
    "gal": ("galón", "galones"),
    "caja": ("caja", "cajas"),
    "cajas": ("caja", "cajas"),
    "rollo": ("rollo", "rollos"),
    "rollos": ("rollo", "rollos"),
    "par": ("par", "pares"),
    "pares": ("par", "pares"),
    "tabla": ("tabla", "tablas"),
    "tablas": ("tabla", "tablas"),
    "tira": ("tira", "tiras"),
    "tiras": ("tira", "tiras"),
    "pistola": ("pistola", "pistolas"),
    "pistolas": ("pistola", "pistolas"),
    "pistolada": ("pistolada", "pistoladas"),
    "pistoladas": ("pistolada", "pistoladas"),
    "cunete": ("cuñete", "cuñetes"),
    "cunetes": ("cuñete", "cuñetes"),
    "juego": ("juego", "juegos"),
    "juegos": ("juego", "juegos"),
    "bolsa": ("bolsa", "bolsas"),
    "bolsas": ("bolsa", "bolsas"),
}


def _clave_unidad(nombre: Optional[str]) -> str:
    """Normaliza el nombre de la unidad (sin acentos, minúsculas, sin ruido)."""
    if not nombre:
        return ""
    texto = unicodedata.normalize("NFKD", str(nombre))
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    texto = texto.replace("*", " ").replace(".", " ").strip().lower()
    return " ".join(texto.split())


def _texto_cantidad(cantidad) -> str:
    """Cantidad con separador de miles (.) y decimales (,), como en Colombia."""
    valor = Decimal(str(cantidad)).normalize()
    if valor == valor.to_integral_value():
        return f"{int(valor):,}".replace(",", ".")
    entero, _, decimales = f"{valor:f}".partition(".")
    entero = f"{int(entero):,}".replace(",", ".")
    return f"{entero},{decimales.rstrip('0')}"


def _texto_unidad(nombre: Optional[str], cantidad) -> str:
    """Unidad en singular o plural según la cantidad comprada."""
    clave = _clave_unidad(nombre)
    par = _UNIDADES_SINGULAR_PLURAL.get(clave)
    valor = Decimal(str(cantidad))
    if par:
        singular, plural = par
        return singular if valor == 1 else plural
    if not nombre:
        return "unidad" if valor == 1 else "unidades"
    return str(nombre).strip()


def _descripcion_compra_material(nombre: str, cantidad, unidad: Optional[str]) -> str:
    """Concepto legible de una entrada de inventario.

    Ej: "Compra de material: 15 metros de TELA CUSCO HIELO".
    """
    return (
        f"Compra de material: {_texto_cantidad(cantidad)} "
        f"{_texto_unidad(unidad, cantidad)} de {nombre}"
    )


def _persona_compra(db: Session, usuario, proveedor_id, proveedor_nombre) -> Optional[str]:
    """Tercero del movimiento de caja: el proveedor si se indicó; si no, quien
    registró la compra (así el libro nunca queda con la persona en blanco)."""
    persona = (proveedor_nombre or "").strip()
    if not persona and proveedor_id:
        persona = (
            db.query(Proveedor.nombre).filter(Proveedor.id == proveedor_id).scalar()
            or ""
        ).strip()
    if not persona and usuario is not None:
        persona = (getattr(usuario, "nombre", None) or getattr(usuario, "nombre_usuario", "") or "").strip()
    return persona or None


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


_PRIORIDAD_MONEDA = ["EUR", "USD", "VES", "COP"]


def _par_monedas(cod_a: str, cod_b: str) -> tuple[str, str]:
    """(base, quote) del par: la tasa humana SIEMPRE se escribe 1 base = X quote."""
    a = (cod_a or "").upper()
    b = (cod_b or "").upper()
    ia = _PRIORIDAD_MONEDA.index(a) if a in _PRIORIDAD_MONEDA else 99
    ib = _PRIORIDAD_MONEDA.index(b) if b in _PRIORIDAD_MONEDA else 99
    if ia <= ib:
        return a, b
    return b, a


def _monto_en_moneda(monto: Decimal, cod_origen: str, cod_destino: str, tasa: Decimal) -> Decimal:
    """Convierte con la tasa humana del par (1 base = X quote)."""
    if cod_origen == cod_destino:
        return monto
    base, quote = _par_monedas(cod_origen, cod_destino)
    if cod_origen == base and cod_destino == quote:
        return monto * tasa
    if cod_origen == quote and cod_destino == base:
        if tasa <= 0:
            raise ValueError(
                f"La moneda de pago difiere de la moneda de la compra. Indica la tasa del pago "
                f"({cod_origen} ≡ {cod_destino})."
            )
        return monto / tasa
    return monto


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
    persona_entidad: Optional[str] = None,
    clasificacion: Optional[str] = None,
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
            clasificacion=clasificacion,
            observaciones="Generado automáticamente por entrada de inventario",
        ),
        commit=False,
        usuario=usuario,
        persona_entidad=persona_entidad,
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
    persona_compra = _persona_compra(db, usuario, proveedor_id, proveedor_nombre)
    total_compra = (
        (Decimal(str(movimiento.costo_unitario)) * movimiento.cantidad).quantize(Decimal("0.01"))
        if movimiento.costo_unitario is not None
        else Decimal("0.00")
    )

    # ── Pago de la compra: UNA cuenta (compatibilidad) o VARIAS ────────────
    # La compra puede pagarse de dos maneras (la mitad en efectivo COP y el
    # resto por Zelle, p. ej.). Cada pago genera su propio gasto + salida de
    # caja y queda en `entrada_compra_pago` para el desglose del libro.
    pagos = list(getattr(movimiento, "pagos", None) or [])
    if movimiento.tipo == "ENTRADA" and pagos and getattr(movimiento, "fiar", False):
        raise ValueError("Elige entre pagar (una o varias cuentas) o fiar, no ambos.")
    if movimiento.tipo == "ENTRADA" and pagos and total_compra <= 0:
        raise ValueError("Para registrar pagos indica el costo unitario de la entrada.")

    if movimiento.tipo == "ENTRADA" and pagos and total_compra > 0:
        from app.modules.reports.model import MetodoCaja
        from app.modules.catalogos.model import Moneda

        if getattr(movimiento, "pagado_desde_metodo_caja_id", None):
            # El frontend manda el pago principal por los dos caminos: si
            # apuntan a la MISMA cuenta es telefonía vieja y se ignora el
            # campo clásico; si difieren, hay algo mal y no adivinamos.
            coincide = (
                getattr(movimiento, "pagado_desde_metodo_caja_id", None)
                == pagos[0].metodo_caja_id
            )
            if not coincide:
                raise ValueError(
                    "Envía el pago por `pagos` o por pagado_desde_metodo_caja_id, "
                    "no con valores distintos."
                )
            movimiento.pagado_desde_metodo_caja_id = None
            movimiento.moneda_pago_id = None
            movimiento.tasa_pago = None

        cuentas_pago: dict[int, object] = {}
        codigos_moneda: dict[int, str] = {}
        resumen: list[tuple[object, Decimal, Decimal, Decimal]] = []
        acumulado = Decimal("0.00")
        for indice, pago in enumerate(pagos, start=1):
            cuenta = cuentas_pago.get(pago.metodo_caja_id)
            if cuenta is None:
                cuenta = (
                    db.query(MetodoCaja)
                    .filter(MetodoCaja.id == pago.metodo_caja_id)
                    .first()
                )
                cuentas_pago[pago.metodo_caja_id] = cuenta
            if cuenta is None or not cuenta.activo:
                raise ValueError(
                    f"El pago {indice} apunta a una cuenta de caja inexistente o inactiva."
                )
            moneda_pago_cod = codigos_moneda.get(pago.moneda_id)
            if moneda_pago_cod is None:
                moneda_pago_cod = (
                    db.query(Moneda.codigo).filter(Moneda.id == pago.moneda_id).scalar()
                )
                codigos_moneda[pago.moneda_id] = moneda_pago_cod or f"#{pago.moneda_id}"
            if cuenta.moneda_id and cuenta.moneda_id != pago.moneda_id:
                raise ValueError(
                    f"El pago {indice} pagó en {moneda_pago_cod} pero eligió la cuenta "
                    f"'{cuenta.nombre}', que es de otra moneda. Usa una cuenta en "
                    f"{moneda_pago_cod}."
                )
            monto = Decimal(str(pago.monto)).quantize(Decimal("0.01"))
            if monto <= 0:
                raise ValueError(f"El pago {indice} debe ser mayor que 0.")
            if pago.moneda_id != MONEDA_BASE_ID:
                if not pago.tasa_pago or Decimal(str(pago.tasa_pago)) <= 0:
                    raise ValueError(
                        f"El pago {indice} (en {moneda_pago_cod}) necesita la tasa de "
                        f"cambio: 1 {moneda_pago_cod} = ? COP."
                    )
                tasa = Decimal(str(pago.tasa_pago))
            else:
                tasa = Decimal("1")
            monto_cop = (monto * tasa).quantize(Decimal("0.01"))
            if monto_cop <= 0:
                raise ValueError(
                    f"El pago {indice} queda en 0 COP con la tasa indicada. Revisa la tasa."
                )
            acumulado += monto_cop
            resumen.append((pago, monto, tasa, monto_cop))

        diferencia = (acumulado - total_compra).quantize(Decimal("0.01"))
        if abs(diferencia) > Decimal("1.00"):
            raise ValueError(
                f"Los pagos suman ${acumulado:,.2f} COP y la compra ${total_compra:,.2f} COP: "
                f"{'faltan' if diferencia < 0 else 'sobran'} ${abs(diferencia):,.2f} COP. "
                "Ajusta los montos para que cuadren con la compra."
            )

        descripcion_compra = _descripcion_compra_material(
            material.nombre,
            movimiento.cantidad,
            material.unidad_medida.nombre if material.unidad_medida else None,
        )
        total_pagos = len(pagos)
        for indice, (pago, monto, tasa, monto_cop) in enumerate(resumen, start=1):
            cuenta = cuentas_pago[pago.metodo_caja_id]
            gasto_i = _gasto_compra_contado(
                db,
                tipo_gasto_nombre=tipo_gasto_compra,
                descripcion=(
                    descripcion_compra
                    + (f" · pago {indice} de {total_pagos} en {cuenta.nombre}" if total_pagos > 1 else "")
                ),
                total_ref=monto_cop,
                ref_moneda_id=MONEDA_BASE_ID,
                metodo_caja_id=pago.metodo_caja_id,
                moneda_pago_id=pago.moneda_id,
                tasa_pago=pago.tasa_pago,
                fecha=fecha_mov.date(),
                usuario=usuario,
                persona_entidad=persona_compra,
                # Las compras de insumos son gasto de fábrica (oficina tiene su
                # propia canasta) — decisión de la dueña, 03/11/2026.
                clasificacion="GASTO_OFICINA" if es_oficina else "GASTO_FABRICA",
            )
            db.add(model.EntradaCompraPago(
                movimiento_inventario_id=db_mov.id,
                gasto_id=gasto_i.id,
                metodo_caja_id=pago.metodo_caja_id,
                moneda_id=pago.moneda_id,
                monto=monto,
                tasa_cambio=tasa,
                monto_en_moneda_base=monto_cop,
            ))
            if indice == 1:
                gasto_primero = gasto_i
                # Compatibilidad con el kardex/libro: los campos clásicos del
                # movimiento apuntan al PRIMER pago.
                db_mov.pagado_desde_metodo_caja_id = pago.metodo_caja_id
                db_mov.moneda_pago_id = pago.moneda_id
                db_mov.tasa_pago = pago.tasa_pago
                movimiento.pagado_desde_metodo_caja_id = pago.metodo_caja_id
                movimiento.moneda_pago_id = pago.moneda_id
                movimiento.tasa_pago = pago.tasa_pago
        db_mov.gasto_id = gasto_primero.id
        db.flush()
    elif (
        movimiento.tipo == "ENTRADA"
        and getattr(movimiento, "pagado_desde_metodo_caja_id", None)
        and movimiento.costo_unitario is not None
        and Decimal(str(movimiento.costo_unitario)) > 0
    ):
        gasto_compra = _gasto_compra_contado(
            db,
            tipo_gasto_nombre=tipo_gasto_compra,
            descripcion=_descripcion_compra_material(
                material.nombre,
                movimiento.cantidad,
                material.unidad_medida.nombre if material.unidad_medida else None,
            ),
            total_ref=total_compra,
            ref_moneda_id=MONEDA_BASE_ID,
            metodo_caja_id=movimiento.pagado_desde_metodo_caja_id,
            moneda_pago_id=getattr(movimiento, "moneda_pago_id", None),
            tasa_pago=getattr(movimiento, "tasa_pago", None),
            fecha=fecha_mov.date(),
            usuario=usuario,
            persona_entidad=persona_compra,
            # Las compras de insumos son gasto de fábrica (oficina tiene su
            # propia canasta) — decisión de la dueña, 03/11/2026.
            clasificacion="GASTO_OFICINA" if es_oficina else "GASTO_FABRICA",
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
        nombre_ll = mat_ll.nombre if mat_ll else "insumo"
        unidad_ll = mat_ll.unidad_medida.nombre if mat_ll and mat_ll.unidad_medida else None
        gasto_llevada = _gasto_compra_contado(
            db,
            tipo_gasto_nombre="FLETE / LLEVADA DE INSUMO",
            descripcion=(
                f"Llevada (flete/aduana): {_texto_cantidad(movimiento.cantidad)} "
                f"{_texto_unidad(unidad_ll, movimiento.cantidad)} de {nombre_ll}"
            ),
            total_ref=Decimal(str(llevada)).quantize(Decimal("0.01")),
            ref_moneda_id=MONEDA_BASE_ID,
            metodo_caja_id=movimiento.pagado_desde_metodo_caja_id,
            moneda_pago_id=getattr(movimiento, "moneda_pago_id", None),
            tasa_pago=getattr(movimiento, "tasa_pago", None),
            fecha=fecha_mov.date(),
            usuario=usuario,
            persona_entidad=_persona_compra(db, usuario, proveedor_id, proveedor_nombre),
            clasificacion="GASTO_OFICINA" if es_oficina else "GASTO_FABRICA",
        )
        if gasto_llevada is not None:
            db_mov.llevada_gasto_id = gasto_llevada.id
            db.flush()
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


# ─────────────────────────────────────────────────────────────────────────────
# Corrección / anulación de ENTRADAS manuales
# ─────────────────────────────────────────────────────────────────────────────
# Una entrada manual pagada desde caja crea tres caras que deben moverse
# juntas: stock, gasto (P&L) y salida de caja. Editar solo una deja el sistema
# descuadrado. Estas funciones corrigen las tres en una sola transacción.
#
# Reglas de seguridad:
#  - Solo ENTRADAS manuales (referencia_tipo NULL). Compras/producción/cargas
#    iniciales tienen su propio flujo y no se tocan desde el kardex.
#  - No se editan entradas fiadas ni con flete/llevada (tienen gastos/deudas
#    externos que requieren un tratamiento aparte).
#  - No se permite dejar el stock negativo.
#  - La cuenta de pago solo se cambia si es de la misma moneda; los pagos
#    mixtos conservan sus cuentas y se reescalan proporcionalmente.
#  - La edición/anulación la puede hacer el autor del gasto o Dueño/Admin.


def _snapshot_movimiento_inventario(m: model.MovimientoInventario) -> dict:
    return {
        "id": m.id,
        "material_id": m.material_id,
        "ubicacion_id": m.ubicacion_id,
        "tipo": m.tipo,
        "cantidad": float(m.cantidad),
        "costo_unitario": float(m.costo_unitario) if m.costo_unitario is not None else None,
        "llevada": float(m.llevada) if m.llevada is not None else None,
        "proveedor_id": m.proveedor_id,
        "proveedor_nombre": m.proveedor_nombre,
        "cliente_id": m.cliente_id,
        "cliente_nombre": m.cliente_nombre,
        "departamento": m.departamento,
        "recibido_por": m.recibido_por,
        "pagado_desde_metodo_caja_id": m.pagado_desde_metodo_caja_id,
        "moneda_pago_id": m.moneda_pago_id,
        "tasa_pago": float(m.tasa_pago) if m.tasa_pago is not None else None,
        "gasto_id": m.gasto_id,
        "llevada_gasto_id": m.llevada_gasto_id,
        "descuento_porcentaje": float(m.descuento_porcentaje) if m.descuento_porcentaje is not None else None,
        "fiar": bool(m.fiar),
        "referencia_tipo": m.referencia_tipo,
        "referencia_id": m.referencia_id,
        "observaciones": m.observaciones,
        "fecha": m.fecha.isoformat() if m.fecha else None,
    }


def _snapshot_gasto(g) -> dict:
    return {
        "id": g.id,
        "descripcion": g.descripcion,
        "monto": float(g.monto),
        "moneda_id": g.moneda_id,
        "tasa_cambio": float(g.tasa_cambio) if g.tasa_cambio is not None else None,
        "monto_en_moneda_base": float(g.monto_en_moneda_base) if g.monto_en_moneda_base is not None else None,
        "tipo_gasto_id": g.tipo_gasto_id,
        "clasificacion": g.clasificacion,
        "fecha": g.fecha.isoformat() if g.fecha else None,
    }


def _snapshot_movimiento_caja(mc) -> dict:
    if mc is None:
        return {}
    return {
        "id": mc.id,
        "metodo_caja_id": mc.metodo_caja_id,
        "tipo": mc.tipo,
        "monto": float(mc.monto),
        "moneda_id": mc.moneda_id,
        "tasa_cambio": float(mc.tasa_cambio) if mc.tasa_cambio is not None else None,
        "monto_en_moneda_base": float(mc.monto_en_moneda_base) if mc.monto_en_moneda_base is not None else None,
        "fecha": mc.fecha.isoformat() if mc.fecha else None,
        "referencia": mc.referencia,
        "concepto": mc.concepto,
        "persona_entidad": mc.persona_entidad,
    }


def _pagos_de_entrada(db: Session, m: model.MovimientoInventario):
    """Devuelve [(fila_entrada_compra_pago | None, gasto, movimiento_caja)].

    Las entradas nuevas con pagos mixtos guardan una fila por pago en
    `entrada_compra_pago`; las de una sola cuenta (flujo clásico) solo tienen
    `movimiento_inventario.gasto_id`.
    """
    from app.modules.gastos.model import Gasto
    from app.modules.reports.model import MovimientoCaja

    filas = (
        db.query(model.EntradaCompraPago)
        .filter(model.EntradaCompraPago.movimiento_inventario_id == m.id)
        .order_by(model.EntradaCompraPago.id)
        .all()
    )
    if filas:
        pagos = []
        for fila in filas:
            if fila.gasto_id is None:
                raise ValueError(
                    "La entrada tiene un pago sin gasto asociado; no se puede corregir automáticamente."
                )
            gasto = db.query(Gasto).filter(Gasto.id == fila.gasto_id).first()
            if gasto is None:
                raise ValueError(f"No se encontró el gasto #{fila.gasto_id} de la entrada.")
            caja = (
                db.query(MovimientoCaja)
                .filter(MovimientoCaja.referencia == f"Gasto #{fila.gasto_id}")
                .first()
            )
            pagos.append((fila, gasto, caja))
        return pagos

    if m.gasto_id:
        gasto = db.query(Gasto).filter(Gasto.id == m.gasto_id).first()
        if gasto is None:
            raise ValueError(f"No se encontró el gasto #{m.gasto_id} de la entrada.")
        caja = (
            db.query(MovimientoCaja)
            .filter(MovimientoCaja.referencia == f"Gasto #{m.gasto_id}")
            .first()
        )
        return [(None, gasto, caja)]

    return []


def _validar_entrada_corregible(db: Session, m: model.MovimientoInventario, usuario) -> None:
    """Solo entradas manuales.

    El permiso de ESCRITURA del módulo Inventario lo exige el router
    (`require_module('inventario')`). Por eso cualquier usuario con Inventario
    en modo gestionar puede corregir/anular, incluida Paola; no se limita al
    autor del gasto. La auditoría registra quién lo hizo.
    """
    if m.tipo != "ENTRADA":
        raise ValueError("Solo se pueden editar o anular entradas de inventario.")
    if m.referencia_tipo:
        raise ValueError(
            f"Esta entrada viene de {m.referencia_tipo}; no se corrige desde el kardex."
        )


def _ultima_entrada(db: Session, material_id: int):
    return (
        db.query(model.MovimientoInventario)
        .filter(
            model.MovimientoInventario.material_id == material_id,
            model.MovimientoInventario.tipo == "ENTRADA",
        )
        .order_by(
            model.MovimientoInventario.fecha.desc(),
            model.MovimientoInventario.id.desc(),
        )
        .first()
    )


def _tipo_gasto_compra_editado(db: Session, es_oficina: bool) -> tuple[int, str, str]:
    from app.modules.catalogos.model import TipoGasto

    nombre = "PAPELERIA DE OFICINA" if es_oficina else "COMPRA DE INSUMOS"
    tipo = db.query(TipoGasto).filter(TipoGasto.nombre == nombre).first()
    if tipo is None:
        tipo = TipoGasto(nombre=nombre, categoria="OPERATIVO")
        db.add(tipo)
        db.flush()
    return tipo.id, ("GASTO_OFICINA" if es_oficina else "GASTO_FABRICA"), nombre


def _monto_en_moneda_de_pago(monto_cop: Decimal, moneda_id, tasa) -> Decimal:
    if moneda_id == MONEDA_BASE_ID:
        return monto_cop
    tasa = Decimal(str(tasa or 0))
    if tasa <= 0:
        raise ValueError("La tasa de cambio del pago debe ser mayor que cero.")
    return (monto_cop / tasa).quantize(Decimal("0.01"))


def _actualizar_gasto_y_caja(
    db: Session,
    gasto,
    caja,
    *,
    monto_cop: Decimal,
    descripcion: str,
    fecha,
    metodo_caja_id,
    tipo_gasto_id: int,
    clasificacion: str,
    usuario,
) -> Decimal:
    """Actualiza el gasto espejo y su salida de caja. Devuelve el monto en la
    moneda del pago (el que se guarda también en `entrada_compra_pago.monto`)."""
    monto_gasto = _monto_en_moneda_de_pago(monto_cop, gasto.moneda_id, gasto.tasa_cambio)
    gasto.monto = monto_gasto
    gasto.monto_en_moneda_base = monto_cop
    gasto.fecha = fecha
    gasto.descripcion = descripcion
    gasto.tipo_gasto_id = tipo_gasto_id
    gasto.clasificacion = clasificacion
    if usuario is not None:
        gasto.actualizado_por_id = usuario.id

    if caja is not None:
        caja.monto = _monto_en_moneda_de_pago(monto_cop, caja.moneda_id, caja.tasa_cambio)
        caja.monto_en_moneda_base = monto_cop
        caja.fecha = fecha
        caja.concepto = descripcion
        if metodo_caja_id is not None:
            caja.metodo_caja_id = metodo_caja_id
    return monto_gasto


def _snapshot_cxp(cxp) -> dict:
    if cxp is None:
        return {}
    return {
        "id": cxp.id,
        "proveedor_id": cxp.proveedor_id,
        "gasto_id": cxp.gasto_id,
        "tipo_gasto_id": cxp.tipo_gasto_id,
        "moneda_id": cxp.moneda_id,
        "fecha": cxp.fecha.isoformat() if cxp.fecha else None,
        "descripcion": cxp.descripcion,
        "monto": float(cxp.monto),
        "monto_en_moneda_base": float(cxp.monto_en_moneda_base),
        "monto_pagado": float(cxp.monto_pagado or 0),
        "estado": cxp.estado,
        "origen_tipo": cxp.origen_tipo,
        "origen_id": cxp.origen_id,
    }


def _cxp_de_entrada(db: Session, m: model.MovimientoInventario):
    from app.modules.cuentas_por_pagar.model import CuentaPorPagar

    return (
        db.query(CuentaPorPagar)
        .filter(
            CuentaPorPagar.origen_tipo == "ENTRADA_INVENTARIO",
            CuentaPorPagar.origen_id == m.id,
        )
        .first()
    )


def _validar_cxp_sin_abonos(db: Session, cxp) -> None:
    if cxp is None:
        return
    from app.modules.cuentas_por_pagar.model import PagoCuentaPorPagar

    abonos = (
        db.query(PagoCuentaPorPagar)
        .filter(PagoCuentaPorPagar.cuenta_por_pagar_id == cxp.id)
        .count()
    )
    if Decimal(str(cxp.monto_pagado or 0)) > 0 or abonos:
        raise ValueError(
            "La cuenta por pagar de esta entrada ya tiene abonos. "
            "No se puede editar ni anular; corrige primero los abonos."
        )


def _gasto_de_cxp(db: Session, cxp):
    from app.modules.gastos.model import Gasto

    if cxp is None or cxp.gasto_id is None:
        return None
    return db.query(Gasto).filter(Gasto.id == cxp.gasto_id).first()


def _eliminar_cxp_entrada(db: Session, cxp, usuario, motivo=None) -> None:
    from app.modules.auditoria.service import record_event
    from app.modules.reports.model import MovimientoCaja

    _validar_cxp_sin_abonos(db, cxp)
    gasto = _gasto_de_cxp(db, cxp)
    antes_cxp = _snapshot_cxp(cxp)

    # Una deuda no debería tener salida de caja; si alguien la creó, se limpia.
    if gasto is not None:
        caja = (
            db.query(MovimientoCaja)
            .filter(MovimientoCaja.referencia == f"Gasto #{gasto.id}")
            .first()
        )
        if caja is not None:
            record_event(
                db,
                actor=usuario,
                action="DELETE",
                entity_type="movimiento_caja",
                entity_id=caja.id,
                before=_snapshot_movimiento_caja(caja),
            )
            db.delete(caja)
        record_event(
            db,
            actor=usuario,
            action="DELETE",
            entity_type="gasto",
            entity_id=gasto.id,
            before=_snapshot_gasto(gasto),
        )
        db.delete(gasto)

    record_event(
        db,
        actor=usuario,
        action="DELETE",
        entity_type="cuenta_por_pagar",
        entity_id=cxp.id,
        before=antes_cxp,
        after={"motivo": motivo} if motivo else None,
    )
    db.delete(cxp)
    db.flush()


def _actualizar_cxp_entrada(
    db: Session,
    cxp,
    *,
    proveedor_id: int,
    material,
    cantidad: Decimal,
    costo: Decimal,
    llevada: Decimal,
    fecha,
    tipo_gasto_id: int,
    clasificacion: str,
    cliente_id,
    cliente_nombre,
    usuario,
) -> None:
    from app.modules.cuentas_por_pagar.model import DetalleCuentaPorPagar

    _validar_cxp_sin_abonos(db, cxp)
    monto = (cantidad * costo + llevada).quantize(Decimal("0.01"))
    descripcion = f"Compra fiada: {material.nombre} x{cantidad:g}"

    cxp.proveedor_id = proveedor_id
    cxp.tipo_gasto_id = tipo_gasto_id
    cxp.moneda_id = MONEDA_BASE_ID
    cxp.tasa_cambio = Decimal("1.0")
    cxp.fecha = fecha
    cxp.descripcion = descripcion
    cxp.monto = monto
    cxp.monto_en_moneda_base = monto
    cxp.estado = "PENDIENTE"

    if len(cxp.detalles) > 1:
        raise ValueError(
            "La cuenta por pagar de esta entrada tiene varios renglones; "
            "no se puede corregir automáticamente."
        )
    if not cxp.detalles:
        cxp.detalles.append(DetalleCuentaPorPagar(
            orden=0,
            descripcion=material.nombre,
            material_id=material.id,
            cantidad=cantidad,
            precio_unitario=costo,
            cliente_id=cliente_id,
            cliente_nombre=cliente_nombre,
        ))
    else:
        detalle = cxp.detalles[0]
        detalle.descripcion = material.nombre
        detalle.material_id = material.id
        detalle.cantidad = cantidad
        detalle.precio_unitario = costo
        detalle.cliente_id = cliente_id
        detalle.cliente_nombre = cliente_nombre

    gasto = _gasto_de_cxp(db, cxp)
    if gasto is not None:
        gasto.tipo_gasto_id = tipo_gasto_id
        gasto.moneda_id = MONEDA_BASE_ID
        gasto.fecha = fecha
        gasto.descripcion = descripcion
        gasto.monto = monto
        gasto.tasa_cambio = Decimal("1.0")
        gasto.monto_en_moneda_base = monto
        gasto.clasificacion = clasificacion
        if usuario is not None:
            gasto.actualizado_por_id = usuario.id


def _crear_cxp_entrada(
    db: Session,
    m: model.MovimientoInventario,
    *,
    proveedor_id: int,
    material,
    cantidad: Decimal,
    costo: Decimal,
    llevada: Decimal,
    fecha,
    tipo_gasto_id: int,
    clasificacion: str,
    cliente_id,
    cliente_nombre,
    usuario,
):
    from app.modules.cuentas_por_pagar.service import crear_cuenta_desde_entrada

    cxp = crear_cuenta_desde_entrada(
        db,
        proveedor_id=proveedor_id,
        material_id=material.id,
        material_nombre=material.nombre,
        cantidad=cantidad,
        costo_unitario=costo,
        llevada=llevada,
        fecha=fecha,
        movimiento_id=m.id,
        tipo_gasto_id=tipo_gasto_id,
        cliente_id=cliente_id,
        cliente_nombre=cliente_nombre,
        usuario=usuario,
    )
    gasto = _gasto_de_cxp(db, cxp)
    if gasto is not None:
        gasto.clasificacion = clasificacion
        gasto.tipo_gasto_id = tipo_gasto_id
        if usuario is not None:
            gasto.actualizado_por_id = usuario.id
    return cxp


def _gasto_llevada_de_entrada(db: Session, m: model.MovimientoInventario):
    from app.modules.gastos.model import Gasto

    if m.llevada is None or Decimal(str(m.llevada)) <= 0:
        return None
    if m.llevada_gasto_id:
        return db.query(Gasto).filter(Gasto.id == m.llevada_gasto_id).first()

    # Entradas históricas (antes de `llevada_gasto_id`): se busca por la
    # descripción, fecha y monto. Si hay ambigüedad se bloquea para no borrar
    # el flete equivocado.
    consulta = db.query(Gasto).filter(
        Gasto.descripcion.like("Llevada (flete/aduana):%"),
        Gasto.monto_en_moneda_base == Decimal(str(m.llevada)),
    )
    if m.fecha is not None:
        consulta = consulta.filter(Gasto.fecha == m.fecha.date())
    candidatos = consulta.all()
    if len(candidatos) == 1:
        return candidatos[0]
    raise ValueError(
        "No se pudo identificar con certeza el gasto del flete/llevada de esta "
        "entrada. Corrige o elimina ese gasto manualmente antes de continuar."
    )


def _eliminar_gasto_llevada(db: Session, gasto, usuario, motivo=None) -> None:
    from app.modules.auditoria.service import record_event
    from app.modules.reports.model import MovimientoCaja

    if gasto is None:
        return
    caja = (
        db.query(MovimientoCaja)
        .filter(MovimientoCaja.referencia == f"Gasto #{gasto.id}")
        .first()
    )
    if caja is not None:
        record_event(
            db,
            actor=usuario,
            action="DELETE",
            entity_type="movimiento_caja",
            entity_id=caja.id,
            before=_snapshot_movimiento_caja(caja),
        )
        db.delete(caja)
    record_event(
        db,
        actor=usuario,
        action="DELETE",
        entity_type="gasto",
        entity_id=gasto.id,
        before=_snapshot_gasto(gasto),
        after={"motivo": motivo} if motivo else None,
    )
    db.delete(gasto)
    db.flush()


def _normalizar_pagos_edicion(db: Session, pagos, total_compra: Decimal):
    """Valida los pagos y devuelve [{pago, cuenta, monto, tasa, monto_cop}]."""
    from app.modules.reports.model import MetodoCaja

    resumen = []
    acumulado = Decimal("0")
    for indice, pago in enumerate(pagos or [], start=1):
        datos_pago = pago.model_dump() if hasattr(pago, "model_dump") else dict(pago)
        metodo_caja_id = int(datos_pago["metodo_caja_id"])
        moneda_id = int(datos_pago["moneda_id"])
        monto = Decimal(str(datos_pago["monto"])).quantize(Decimal("0.01"))
        if monto <= 0:
            raise ValueError(f"El pago {indice} debe ser mayor que cero.")
        cuenta = (
            db.query(MetodoCaja)
            .filter(MetodoCaja.id == metodo_caja_id)
            .first()
        )
        if cuenta is None or not cuenta.activo:
            raise ValueError(f"El pago {indice} apunta a una cuenta inexistente o inactiva.")
        if cuenta.moneda_id and cuenta.moneda_id != moneda_id:
            raise ValueError(
                f"El pago {indice} está en una moneda distinta a la de la cuenta "
                f"'{cuenta.nombre}'."
            )
        if moneda_id != MONEDA_BASE_ID:
            tasa_pago = datos_pago.get("tasa_pago")
            tasa = Decimal(str(tasa_pago or 0))
            if tasa <= 0:
                raise ValueError(
                    f"El pago {indice} necesita la tasa de cambio "
                    f"(1 moneda del pago = X COP)."
                )
        else:
            tasa_pago = None
            tasa = Decimal("1")
        monto_cop = (monto * tasa).quantize(Decimal("0.01"))
        if monto_cop <= 0:
            raise ValueError(f"El pago {indice} queda en 0 COP. Revisa el monto/tasa.")
        acumulado += monto_cop
        resumen.append({
            "pago": pago,
            "metodo_caja_id": metodo_caja_id,
            "moneda_id": moneda_id,
            "monto": monto,
            "tasa_pago": tasa_pago,
            "tasa": tasa,
            "monto_cop": monto_cop,
            "cuenta": cuenta,
        })

    diferencia = (acumulado - total_compra).quantize(Decimal("0.01"))
    if abs(diferencia) > Decimal("1.00"):
        raise ValueError(
            f"Los pagos suman ${acumulado:,.2f} COP y la compra ${total_compra:,.2f} COP: "
            f"{'faltan' if diferencia < 0 else 'sobran'} ${abs(diferencia):,.2f} COP. "
            "Ajusta los montos para que cuadren."
        )
    return resumen


def _pagos_existentes_a_payload(db: Session, m: model.MovimientoInventario, pagos, nuevo_total: Decimal):
    """Reescala los pagos actuales al nuevo total conservando cuentas/monedas."""
    if not pagos:
        return []
    filas = []
    old_total = Decimal("0")
    for fila, gasto, caja in pagos:
        if fila is not None:
            cop = Decimal(str(fila.monto_en_moneda_base))
            metodo = fila.metodo_caja_id
            moneda = fila.moneda_id
            tasa = Decimal(str(fila.tasa_cambio or 1))
        else:
            cop = Decimal(str(
                caja.monto_en_moneda_base if caja is not None else gasto.monto_en_moneda_base
            ))
            metodo = m.pagado_desde_metodo_caja_id
            moneda = gasto.moneda_id or m.moneda_pago_id or MONEDA_BASE_ID
            tasa = Decimal(str(gasto.tasa_cambio or m.tasa_pago or 1))
        if metodo is None:
            raise ValueError("Uno de los pagos actuales no tiene cuenta de caja.")
        old_total += cop
        filas.append((metodo, moneda, tasa, cop))

    if old_total <= 0:
        raise ValueError(
            "Los pagos actuales no tienen equivalente en COP; no se pueden reescalar."
        )

    resultado = []
    acumulado = Decimal("0")
    for indice, (metodo, moneda, tasa, cop) in enumerate(filas):
        nuevo_cop = (cop * nuevo_total / old_total).quantize(Decimal("0.01"))
        if indice == len(filas) - 1:
            nuevo_cop = nuevo_total - acumulado
        acumulado += nuevo_cop
        monto = _monto_en_moneda_de_pago(nuevo_cop, moneda, tasa)
        if monto <= 0:
            raise ValueError("El nuevo total deja un pago en cero; revisa cantidad/precio.")
        resultado.append({
            "metodo_caja_id": int(metodo),
            "moneda_id": int(moneda),
            "monto": monto,
            "tasa_pago": (tasa if moneda != MONEDA_BASE_ID else None),
        })
    return resultado


def _eliminar_pagos_entrada(db: Session, m: model.MovimientoInventario, pagos, usuario, motivo=None) -> None:
    from app.modules.auditoria.service import record_event
    from app.modules.cuentas_por_pagar.model import CuentaPorPagar

    for fila, gasto, caja in pagos:
        if gasto is not None:
            if db.query(CuentaPorPagar).filter(CuentaPorPagar.gasto_id == gasto.id).first():
                raise ValueError(
                    "El gasto de esta entrada está ligado a una cuenta por pagar."
                )
            otro = (
                db.query(model.MovimientoInventario)
                .filter(
                    model.MovimientoInventario.gasto_id == gasto.id,
                    model.MovimientoInventario.id != m.id,
                )
                .first()
            )
            if otro is not None:
                raise ValueError(
                    f"El gasto #{gasto.id} también está ligado a la entrada #{otro.id}."
                )
        if caja is not None:
            record_event(
                db,
                actor=usuario,
                action="DELETE",
                entity_type="movimiento_caja",
                entity_id=caja.id,
                before=_snapshot_movimiento_caja(caja),
            )
            db.delete(caja)
        if gasto is not None:
            record_event(
                db,
                actor=usuario,
                action="DELETE",
                entity_type="gasto",
                entity_id=gasto.id,
                before=_snapshot_gasto(gasto),
                after={"motivo": motivo} if motivo else None,
            )
            db.delete(gasto)
        if fila is not None:
            db.delete(fila)
    db.flush()
    m.gasto_id = None
    m.pagado_desde_metodo_caja_id = None
    m.moneda_pago_id = None
    m.tasa_pago = None


def _crear_pagos_entrada(
    db: Session,
    m: model.MovimientoInventario,
    *,
    material,
    resumen,
    descripcion_base: str,
    fecha,
    usuario,
    tipo_gasto_nombre: str,
    clasificacion: str,
    proveedor_nombre,
) -> None:
    total_pagos = len(resumen)
    primero = None
    for indice, item in enumerate(resumen, start=1):
        descripcion = descripcion_base
        if total_pagos > 1:
            descripcion += (
                f" · pago {indice} de {total_pagos} en {item['cuenta'].nombre}"
            )
        gasto = _gasto_compra_contado(
            db,
            tipo_gasto_nombre=tipo_gasto_nombre,
            descripcion=descripcion,
            total_ref=item["monto_cop"],
            ref_moneda_id=MONEDA_BASE_ID,
            metodo_caja_id=item["metodo_caja_id"],
            moneda_pago_id=item["moneda_id"],
            tasa_pago=item["tasa_pago"],
            fecha=fecha,
            usuario=usuario,
            persona_entidad=proveedor_nombre,
            clasificacion=clasificacion,
        )
        db.add(model.EntradaCompraPago(
            movimiento_inventario_id=m.id,
            gasto_id=gasto.id,
            metodo_caja_id=item["metodo_caja_id"],
            moneda_id=item["moneda_id"],
            monto=item["monto"],
            tasa_cambio=item["tasa"],
            monto_en_moneda_base=item["monto_cop"],
        ))
        if indice == 1:
            primero = gasto
    db.flush()
    if primero is not None:
        m.gasto_id = primero.id
        m.pagado_desde_metodo_caja_id = resumen[0]["metodo_caja_id"]
        m.moneda_pago_id = resumen[0]["moneda_id"]
        m.tasa_pago = resumen[0]["tasa_pago"]
    else:
        m.gasto_id = None
        m.pagado_desde_metodo_caja_id = None
        m.moneda_pago_id = None
        m.tasa_pago = None


def _aplicar_llevada_entrada(
    db: Session,
    m: model.MovimientoInventario,
    *,
    material,
    cantidad: Decimal,
    nueva_llevada: Decimal,
    fecha,
    usuario,
    cuenta_id,
    moneda_id,
    tasa_pago,
    proveedor_nombre,
    clasificacion: str,
    nuevo_fiar: bool,
) -> None:
    if nuevo_fiar or nueva_llevada <= 0:
        m.llevada_gasto_id = None
        m.llevada = nueva_llevada if nueva_llevada > 0 else None
        return

    if cuenta_id is None:
        raise ValueError(
            "El flete/llevada necesita una cuenta de pago. Elige una cuenta o marca Fiar."
        )

    nombre_unidad = material.unidad_medida.nombre if material.unidad_medida else None
    descripcion = (
        f"Llevada (flete/aduana): {_texto_cantidad(cantidad)} "
        f"{_texto_unidad(nombre_unidad, cantidad)} de {material.nombre}"
    )
    gasto = _gasto_compra_contado(
        db,
        tipo_gasto_nombre="FLETE / LLEVADA DE INSUMO",
        descripcion=descripcion,
        total_ref=nueva_llevada,
        ref_moneda_id=MONEDA_BASE_ID,
        metodo_caja_id=cuenta_id,
        moneda_pago_id=moneda_id,
        tasa_pago=tasa_pago,
        fecha=fecha,
        usuario=usuario,
        persona_entidad=proveedor_nombre,
        clasificacion=clasificacion,
    )
    m.llevada_gasto_id = gasto.id if gasto is not None else None
    m.llevada = nueva_llevada


def actualizar_movimiento_inventario(
    db: Session,
    movimiento_id: int,
    esquema: schemas.MovimientoUpdate,
    usuario=None,
):
    """Corrige una ENTRADA manual y todas sus caras (stock, gasto y caja).

    Cubre los campos del formulario de entrada: cantidad, precio, fecha,
    proveedor/cliente, zona, quién trajo, observaciones, descuento, cuenta(s)
    de pago, pagos mixtos, flete/llevada y fiar. El material y el tipo no se
    cambian; para eso se anula y se crea una entrada nueva.
    """
    from app.modules.auditoria.service import record_event

    m = (
        db.query(model.MovimientoInventario)
        .filter(model.MovimientoInventario.id == movimiento_id)
        .with_for_update()
        .first()
    )
    if m is None:
        return None

    _validar_entrada_corregible(db, m, usuario)
    datos = esquema.model_dump(exclude_unset=True)
    motivo = (datos.pop("motivo_correccion", None) or "").strip() or None

    antes_mov = _snapshot_movimiento_inventario(m)
    ultima_antes = _ultima_entrada(db, m.material_id)
    material = db.query(Material).filter(Material.id == m.material_id).first()
    if material is None:
        raise ValueError("El material de la entrada ya no existe.")

    nueva_cantidad = Decimal(str(datos.get("cantidad", m.cantidad)))
    if nueva_cantidad <= 0:
        raise ValueError("La cantidad de la entrada debe ser mayor que cero.")
    nuevo_costo = Decimal(
        str(datos.get("costo_unitario", m.costo_unitario if m.costo_unitario is not None else 0))
    )
    if nuevo_costo < 0:
        raise ValueError("El costo unitario no puede ser negativo.")
    fecha_mov = _fecha_movimiento(datos["fecha"]) if "fecha" in datos else m.fecha

    nuevo_fiar = bool(datos.get("fiar", m.fiar))
    nueva_llevada = Decimal(str(datos.get("llevada", m.llevada if m.llevada is not None else 0)))
    if nueva_llevada < 0:
        raise ValueError("El flete/llevada no puede ser negativo.")
    nuevo_total = (nueva_cantidad * nuevo_costo).quantize(Decimal("0.01"))

    # Proveedor / cliente.
    if "proveedor_nombre" in datos or "proveedor_id" in datos:
        pid = datos.get("proveedor_id") if "proveedor_id" in datos else None
        pnom = datos.get("proveedor_nombre") if "proveedor_nombre" in datos else None
        if pid is not None:
            if not db.query(Proveedor).filter(Proveedor.id == pid).first():
                raise ValueError(f"El proveedor #{pid} no existe.")
            if pnom is None:
                pnom = db.query(Proveedor.nombre).filter(Proveedor.id == pid).scalar()
        else:
            pid, pnom, _, _ = _resolver_proveedor_cliente(db, None, pnom, None, None)
    else:
        pid, pnom = m.proveedor_id, m.proveedor_nombre

    if "cliente_nombre" in datos or "cliente_id" in datos:
        cid = datos.get("cliente_id") if "cliente_id" in datos else None
        cnom = datos.get("cliente_nombre") if "cliente_nombre" in datos else None
        if cid is not None:
            if not db.query(Client).filter(Client.id == cid).first():
                raise ValueError(f"El cliente #{cid} no existe.")
            if cnom is None:
                cnom = db.query(Client.nombre).filter(Client.id == cid).scalar()
        else:
            cid, cnom, _, _ = _resolver_proveedor_cliente(db, None, None, None, cnom)
    else:
        cid, cnom = m.cliente_id, m.cliente_nombre

    nuevo_departamento = datos.get("departamento", m.departamento)
    es_oficina = (nuevo_departamento or "").strip().upper() == "OFICINA"
    tipo_gasto_id, clasificacion, tipo_gasto_nombre = _tipo_gasto_compra_editado(db, es_oficina)

    if nuevo_fiar:
        if datos.get("pagos"):
            raise ValueError("Elige entre pagar (una o varias cuentas) o fiar, no ambos.")
        if datos.get("pagado_desde_metodo_caja_id"):
            raise ValueError("Elige entre pagar de una cuenta o fiar, no ambos.")
        if not pid and pnom:
            # Misma regla que al crear: un nombre libre de proveedor se
            # materializa en el catálogo porque la deuda necesita el FK.
            proveedor = Proveedor(nombre=pnom)
            db.add(proveedor)
            db.flush()
            pid = proveedor.id
        if not pid:
            raise ValueError("Para fiar debes indicar el proveedor.")
        if nuevo_costo <= 0:
            raise ValueError("Para fiar debes indicar el costo unitario del insumo.")

    # Stock: validar antes de tocar cualquier registro.
    inventario = (
        db.query(model.Inventario)
        .filter(
            model.Inventario.material_id == m.material_id,
            model.Inventario.ubicacion_id == m.ubicacion_id,
        )
        .with_for_update()
        .first()
    )
    if inventario is None:
        raise ValueError("No se encontró el stock del material en esa ubicación.")
    delta = nueva_cantidad - Decimal(str(m.cantidad))
    if delta < 0 and Decimal(str(inventario.cantidad)) < -delta:
        raise ValueError(
            f"No se puede reducir la entrada: hay {inventario.cantidad} en stock y "
            f"se intentan quitar {abs(delta)}."
        )

    pagos_existentes = _pagos_de_entrada(db, m)
    cxp = _cxp_de_entrada(db, m)
    if cxp is not None:
        _validar_cxp_sin_abonos(db, cxp)

    # Flete histórico: se resuelve ANTES de borrar nada; si es ambiguo, se
    # bloquea sin dejar la entrada a medias.
    flete_existente = (
        None
        if (m.fiar or not (m.llevada_gasto_id or m.pagado_desde_metodo_caja_id))
        else _gasto_llevada_de_entrada(db, m)
    )

    resumen = []
    if not nuevo_fiar:
        if "pagos" in datos and datos["pagos"] is not None:
            resumen = _normalizar_pagos_edicion(db, datos["pagos"], nuevo_total)
        elif datos.get("pagado_desde_metodo_caja_id") is not None:
            moneda_id = int(datos.get("moneda_pago_id") or m.moneda_pago_id or MONEDA_BASE_ID)
            tasa_pago = datos.get("tasa_pago", m.tasa_pago)
            if moneda_id != MONEDA_BASE_ID:
                if not tasa_pago or Decimal(str(tasa_pago)) <= 0:
                    raise ValueError(
                        "Para pagar en otra moneda indica la tasa de cambio "
                        "(1 moneda del pago = X COP)."
                    )
                monto = _monto_en_moneda_de_pago(nuevo_total, moneda_id, tasa_pago)
            else:
                monto = nuevo_total
                tasa_pago = None
            if monto <= 0:
                raise ValueError("El pago no puede quedar en cero.")
            resumen = _normalizar_pagos_edicion(db, [{
                "metodo_caja_id": datos["pagado_desde_metodo_caja_id"],
                "moneda_id": moneda_id,
                "monto": monto,
                "tasa_pago": tasa_pago,
            }], nuevo_total)
        elif pagos_existentes:
            resumen = _normalizar_pagos_edicion(
                db,
                _pagos_existentes_a_payload(db, m, pagos_existentes, nuevo_total),
                nuevo_total,
            )
        elif nuevo_costo > 0:
            raise ValueError(
                "Indica la cuenta de pago (una o varias) o marca la entrada como fiada."
            )

        if nuevo_costo > 0 and not resumen:
            raise ValueError(
                "Indica la cuenta de pago (una o varias) o marca la entrada como fiada."
            )

    # La llevada se paga desde la cuenta principal. Una entrada cuyo costo de
    # material sea cero puede aun tener una llevada pagada, como permite el
    # formulario original; en ese caso no hay pago de compra, solo de flete.
    cuenta_flete_id = (
        datos.get("pagado_desde_metodo_caja_id")
        if "pagado_desde_metodo_caja_id" in datos
        else m.pagado_desde_metodo_caja_id
    )
    moneda_flete_id = int(datos.get("moneda_pago_id") or m.moneda_pago_id or MONEDA_BASE_ID)
    tasa_flete = datos.get("tasa_pago", m.tasa_pago)
    if resumen:
        cuenta_flete_id = resumen[0]["metodo_caja_id"]
        moneda_flete_id = resumen[0]["moneda_id"]
        tasa_flete = resumen[0]["tasa_pago"]
    if not nuevo_fiar and nueva_llevada > 0 and cuenta_flete_id is not None:
        from app.modules.reports.model import MetodoCaja

        cuenta_flete = db.query(MetodoCaja).filter(MetodoCaja.id == cuenta_flete_id).first()
        if cuenta_flete is None or not cuenta_flete.activo:
            raise ValueError("La cuenta de pago del flete no existe o está inactiva.")
        if cuenta_flete.moneda_id and cuenta_flete.moneda_id != moneda_flete_id:
            raise ValueError("La moneda del flete no coincide con la cuenta seleccionada.")
        if moneda_flete_id != MONEDA_BASE_ID and (
            tasa_flete is None or Decimal(str(tasa_flete)) <= 0
        ):
            raise ValueError("Para pagar el flete en otra moneda indica su tasa de cambio.")

    # A partir de aquí ya está todo validado. Se reemplazan las caras.
    if pagos_existentes:
        _eliminar_pagos_entrada(db, m, pagos_existentes, usuario, motivo)
    if cxp is not None and not nuevo_fiar:
        _eliminar_cxp_entrada(db, cxp, usuario, motivo)
        cxp = None

    if flete_existente is not None:
        _eliminar_gasto_llevada(db, flete_existente, usuario, motivo)
        m.llevada_gasto_id = None
        flete_existente = None

    m.cantidad = nueva_cantidad
    m.costo_unitario = nuevo_costo
    m.fecha = fecha_mov
    m.proveedor_id = pid
    m.proveedor_nombre = pnom
    m.cliente_id = cid
    m.cliente_nombre = cnom
    m.departamento = nuevo_departamento
    if "recibido_por" in datos:
        m.recibido_por = datos["recibido_por"]
    if "observaciones" in datos:
        m.observaciones = datos["observaciones"]
    if "descuento_porcentaje" in datos:
        m.descuento_porcentaje = datos["descuento_porcentaje"]
    m.fiar = nuevo_fiar
    m.llevada = nueva_llevada if nueva_llevada > 0 else None

    if nuevo_fiar:
        if cxp is not None:
            _actualizar_cxp_entrada(
                db,
                cxp,
                proveedor_id=pid,
                material=material,
                cantidad=nueva_cantidad,
                costo=nuevo_costo,
                llevada=nueva_llevada,
                fecha=fecha_mov.date(),
                tipo_gasto_id=tipo_gasto_id,
                clasificacion=clasificacion,
                cliente_id=cid,
                cliente_nombre=cnom,
                usuario=usuario,
            )
        else:
            _crear_cxp_entrada(
                db,
                m,
                proveedor_id=pid,
                material=material,
                cantidad=nueva_cantidad,
                costo=nuevo_costo,
                llevada=nueva_llevada,
                fecha=fecha_mov.date(),
                tipo_gasto_id=tipo_gasto_id,
                clasificacion=clasificacion,
                cliente_id=cid,
                cliente_nombre=cnom,
                usuario=usuario,
            )
        m.gasto_id = None
        m.pagado_desde_metodo_caja_id = None
        m.moneda_pago_id = None
        m.tasa_pago = None
        m.llevada_gasto_id = None
    else:
        descripcion_base = _descripcion_compra_material(
            material.nombre,
            nueva_cantidad,
            material.unidad_medida.nombre if material.unidad_medida else None,
        )
        if resumen:
            _crear_pagos_entrada(
                db,
                m,
                material=material,
                resumen=resumen,
                descripcion_base=descripcion_base,
                fecha=fecha_mov.date(),
                usuario=usuario,
                tipo_gasto_nombre=tipo_gasto_nombre,
                clasificacion=clasificacion,
                proveedor_nombre=pnom,
            )
        else:
            m.gasto_id = None
            m.pagado_desde_metodo_caja_id = None
            m.moneda_pago_id = None
            m.tasa_pago = None

        # Flete/llevada: se recrea con la cuenta principal (primera cuenta).
        if nueva_llevada > 0 and cuenta_flete_id is not None:
            _aplicar_llevada_entrada(
                db,
                m,
                material=material,
                cantidad=nueva_cantidad,
                nueva_llevada=nueva_llevada,
                fecha=fecha_mov.date(),
                usuario=usuario,
                cuenta_id=cuenta_flete_id,
                moneda_id=moneda_flete_id,
                tasa_pago=tasa_flete,
                proveedor_nombre=pnom,
                clasificacion=clasificacion,
                nuevo_fiar=False,
            )
            if not resumen:
                m.pagado_desde_metodo_caja_id = cuenta_flete_id
                m.moneda_pago_id = moneda_flete_id
                m.tasa_pago = tasa_flete
        elif nueva_llevada > 0:
            m.llevada = nueva_llevada
            m.llevada_gasto_id = None
        else:
            m.llevada = None
            m.llevada_gasto_id = None

    inventario.cantidad = Decimal(str(inventario.cantidad)) + delta
    db.flush()

    # Costo_base: sigue al último precio de entrada, pero solo se toca si esta
    # entrada era la última o si, al cambiar la fecha, pasó a serlo.
    nueva_ultima = _ultima_entrada(db, m.material_id)
    if (ultima_antes is not None and ultima_antes.id == m.id) or (
        nueva_ultima is not None and nueva_ultima.id == m.id
    ):
        material.costo_base = (
            Decimal(str(nueva_ultima.costo_unitario))
            if nueva_ultima is not None and nueva_ultima.costo_unitario is not None
            else Decimal("0")
        )

    despues_mov = _snapshot_movimiento_inventario(m)
    if motivo:
        despues_mov["motivo_correccion"] = motivo
    record_event(
        db,
        actor=usuario,
        action="UPDATE",
        entity_type="movimiento_inventario",
        entity_id=m.id,
        before=antes_mov,
        after=despues_mov,
    )

    db.commit()
    db.refresh(m)
    return m


def anular_movimiento_inventario(
    db: Session,
    movimiento_id: int,
    usuario=None,
    motivo: Optional[str] = None,
) -> bool:
    """Anula (elimina) una ENTRADA manual y revierte stock, gasto, caja y deuda."""
    from app.modules.auditoria.service import record_event

    m = (
        db.query(model.MovimientoInventario)
        .filter(model.MovimientoInventario.id == movimiento_id)
        .with_for_update()
        .first()
    )
    if m is None:
        return False

    _validar_entrada_corregible(db, m, usuario)
    antes_mov = _snapshot_movimiento_inventario(m)
    motivo = (motivo or "").strip() or None
    ultima_antes = _ultima_entrada(db, m.material_id)

    inventario = (
        db.query(model.Inventario)
        .filter(
            model.Inventario.material_id == m.material_id,
            model.Inventario.ubicacion_id == m.ubicacion_id,
        )
        .with_for_update()
        .first()
    )
    if inventario is None:
        raise ValueError("No se encontró el stock del material en esa ubicación.")
    if Decimal(str(inventario.cantidad)) < Decimal(str(m.cantidad)):
        raise ValueError(
            f"No se puede anular la entrada: hay {inventario.cantidad} en stock y la "
            f"entrada fue de {m.cantidad}. Parte del material ya se consumió o vendió."
        )

    pagos_existentes = _pagos_de_entrada(db, m)
    cxp = _cxp_de_entrada(db, m)
    if cxp is not None:
        _validar_cxp_sin_abonos(db, cxp)
    flete_existente = (
        None
        if (m.fiar or not (m.llevada_gasto_id or m.pagado_desde_metodo_caja_id))
        else _gasto_llevada_de_entrada(db, m)
    )

    if pagos_existentes:
        _eliminar_pagos_entrada(db, m, pagos_existentes, usuario, motivo)
    if cxp is not None:
        _eliminar_cxp_entrada(db, cxp, usuario, motivo)
    if flete_existente is not None:
        _eliminar_gasto_llevada(db, flete_existente, usuario, motivo)

    inventario.cantidad = Decimal(str(inventario.cantidad)) - Decimal(str(m.cantidad))
    db.delete(m)
    db.flush()

    if ultima_antes is not None and ultima_antes.id == m.id:
        material = db.query(Material).filter(Material.id == m.material_id).first()
        nueva_ultima = _ultima_entrada(db, m.material_id)
        if material is not None:
            material.costo_base = (
                Decimal(str(nueva_ultima.costo_unitario))
                if nueva_ultima is not None and nueva_ultima.costo_unitario is not None
                else Decimal("0")
            )

    despues = {"motivo_anulacion": motivo} if motivo else None
    record_event(
        db,
        actor=usuario,
        action="DELETE",
        entity_type="movimiento_inventario",
        entity_id=m.id,
        before=antes_mov,
        after=despues,
    )
    db.commit()
    return True


def obtener_movimiento_inventario(db: Session, movimiento_id: int):
    return (
        db.query(model.MovimientoInventario)
        .filter(model.MovimientoInventario.id == movimiento_id)
        .first()
    )


def pagos_de_entrada_para_detalle(db: Session, m: model.MovimientoInventario):
    """Desglose de pagos para precargar el formulario de edición."""
    from app.modules.gastos.model import Gasto
    from app.modules.reports.model import MovimientoCaja

    if m.fiar:
        return []

    salida = []
    filas = (
        db.query(model.EntradaCompraPago)
        .filter(model.EntradaCompraPago.movimiento_inventario_id == m.id)
        .order_by(model.EntradaCompraPago.id)
        .all()
    )
    if filas:
        for fila in filas:
            salida.append(schemas.PagoEntradaResponse(
                metodo_caja_id=fila.metodo_caja_id or m.pagado_desde_metodo_caja_id,
                moneda_id=fila.moneda_id,
                monto=fila.monto,
                tasa_pago=(
                    fila.tasa_cambio if fila.moneda_id != MONEDA_BASE_ID else None
                ),
                monto_en_moneda_base=fila.monto_en_moneda_base,
            ))
        return salida

    if m.gasto_id:
        gasto = db.query(Gasto).filter(Gasto.id == m.gasto_id).first()
        caja = (
            db.query(MovimientoCaja)
            .filter(MovimientoCaja.referencia == f"Gasto #{m.gasto_id}")
            .first()
        )
        if gasto is not None and caja is not None:
            salida.append(schemas.PagoEntradaResponse(
                metodo_caja_id=m.pagado_desde_metodo_caja_id or caja.metodo_caja_id,
                moneda_id=gasto.moneda_id,
                monto=caja.monto,
                tasa_pago=(
                    gasto.tasa_cambio if gasto.moneda_id != MONEDA_BASE_ID else None
                ),
                monto_en_moneda_base=caja.monto_en_moneda_base,
            ))
    return salida


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
    # Flush explícito: el id debe existir ANTES de crear el gasto o la cuenta
    # por pagar (origen_id). Sin esto, fiar un producto podía guardar
    # origen_id=NULL porque el INSERT aún no había tocado la BD.
    db.flush()

    # ── Egreso automático de compra (reventa de contado) ─────────────────
    # ENTRADA con costo + cuenta elegida = dinero que sale de esa caja.
    # Genera el gasto "COMPRA INVENTARIO REVENTA" en la MISMA transacción
    # (el router commitea al final) para que la utilidad bruta sea real:
    # la venta ya ingresa a caja; sin esto el costo nunca aparecería.
    # Puede pagarse de VARIAS cuentas/monedas: cada `pagos[i]` genera su
    # propio gasto + salida de caja y la suma debe cuadrar con la compra.
    ref_moneda = producto.moneda_id or 1
    costo_total = (
        (Decimal(str(movimiento.costo_unitario)) * movimiento.cantidad).quantize(Decimal("0.01"))
        if movimiento.costo_unitario is not None and Decimal(str(movimiento.costo_unitario)) > 0
        else Decimal("0.00")
    )
    pagos = list(getattr(movimiento, "pagos", None) or [])
    if (movimiento.tipo == "ENTRADA" and pagos and getattr(movimiento, "fiar", False)):
        raise ValueError("Elige entre pagar (una o varias cuentas) o fiar, no ambos.")
    if (movimiento.tipo == "ENTRADA" and pagos and costo_total <= 0):
        raise ValueError("Para registrar pagos indica el costo unitario de la entrada.")

    if (
        movimiento.tipo == "ENTRADA"
        and pagos
        and costo_total > 0
        and producto.es_reventa
    ):
        from app.modules.reports.model import MetodoCaja
        from app.modules.catalogos.model import Moneda

        if getattr(movimiento, "pagado_desde_metodo_caja_id", None):
            coincide = (
                getattr(movimiento, "pagado_desde_metodo_caja_id", None)
                == pagos[0].metodo_caja_id
            )
            if not coincide:
                raise ValueError(
                    "Envía el pago por `pagos` o por pagado_desde_metodo_caja_id, "
                    "no con valores distintos."
                )
            movimiento.pagado_desde_metodo_caja_id = None
            movimiento.moneda_pago_id = None
            movimiento.tasa_pago = None

        cod_ref = (
            db.query(Moneda.codigo).filter(Moneda.id == ref_moneda).scalar() or "COP"
        )
        cuentas_pago: dict[int, object] = {}
        resumen: list[tuple[object, Decimal, Decimal, Decimal, Decimal]] = []
        acumulado = Decimal("0.00")
        for indice, pago in enumerate(pagos, start=1):
            cuenta = cuentas_pago.get(pago.metodo_caja_id)
            if cuenta is None:
                cuenta = (
                    db.query(MetodoCaja)
                    .filter(MetodoCaja.id == pago.metodo_caja_id)
                    .first()
                )
                cuentas_pago[pago.metodo_caja_id] = cuenta
            if cuenta is None or not cuenta.activo:
                raise ValueError(
                    f"El pago {indice} apunta a una cuenta de caja inexistente o inactiva."
                )
            moneda_pago_cod = (
                db.query(Moneda.codigo).filter(Moneda.id == pago.moneda_id).scalar() or f"#{pago.moneda_id}"
            )
            if cuenta.moneda_id and cuenta.moneda_id != pago.moneda_id:
                raise ValueError(
                    f"El pago {indice} pagó en {moneda_pago_cod} pero eligió la cuenta "
                    f"'{cuenta.nombre}', que es de otra moneda."
                )
            monto = Decimal(str(pago.monto)).quantize(Decimal("0.01"))
            if monto <= 0:
                raise ValueError(f"El pago {indice} debe ser mayor que 0.")
            tasa = Decimal(str(pago.tasa_pago)) if pago.tasa_pago else None
            contribucion = _monto_en_moneda(monto, moneda_pago_cod, cod_ref, tasa).quantize(Decimal("0.01"))
            if contribucion <= 0:
                raise ValueError(
                    f"El pago {indice} queda en 0 {cod_ref} con la tasa indicada. Revisa la tasa."
                )
            acumulado += contribucion
            resumen.append((pago, monto, tasa, contribucion, moneda_pago_cod))

        tolerancia = Decimal("1.00") if ref_moneda == MONEDA_BASE_ID else Decimal("0.05")
        diferencia = (acumulado - costo_total).quantize(Decimal("0.01"))
        if abs(diferencia) > tolerancia:
            raise ValueError(
                f"Los pagos suman {acumulado:,.2f} {cod_ref} y la compra "
                f"{costo_total:,.2f} {cod_ref}: "
                f"{'faltan' if diferencia < 0 else 'sobran'} {abs(diferencia):,.2f} {cod_ref}. "
                "Ajusta los montos para que cuadren con la compra."
            )

        descripcion_compra = (
            f"Compra de producto: {_texto_cantidad(movimiento.cantidad)} "
            f"{_texto_unidad(None, movimiento.cantidad)} de {producto.nombre}"
        )
        total_pagos = len(pagos)
        primero = None
        for indice, (pago, monto, tasa, contribucion, moneda_pago_cod) in enumerate(resumen, start=1):
            cuenta = cuentas_pago[pago.metodo_caja_id]
            gasto_i = _gasto_compra_contado(
                db,
                tipo_gasto_nombre="COMPRA INVENTARIO REVENTA",
                descripcion=(
                    descripcion_compra
                    + (f" · pago {indice} de {total_pagos} en {cuenta.nombre}" if total_pagos > 1 else "")
                ),
                total_ref=contribucion,
                ref_moneda_id=ref_moneda,
                metodo_caja_id=pago.metodo_caja_id,
                moneda_pago_id=pago.moneda_id,
                tasa_pago=pago.tasa_pago,
                fecha=fecha_mov.date(),
                usuario=usuario,
                persona_entidad=_persona_compra(db, usuario, proveedor_id, proveedor_nombre),
            )
            monto_base = Decimal(str(gasto_i.monto_en_moneda_base or 0)).quantize(Decimal("0.01"))
            tasa_cop = (monto_base / monto) if monto > 0 else Decimal("1")
            db.add(model.EntradaCompraPago(
                movimiento_producto_id=db_mov.id,
                gasto_id=gasto_i.id,
                metodo_caja_id=pago.metodo_caja_id,
                moneda_id=pago.moneda_id,
                monto=monto,
                tasa_cambio=tasa_cop.quantize(Decimal("0.000001")),
                monto_en_moneda_base=monto_base,
            ))
            if indice == 1:
                primero = gasto_i
                # Compatibilidad con el libro/kardex: el movimiento clásico
                # apunta al PRIMER pago.
                db_mov.pagado_desde_metodo_caja_id = pago.metodo_caja_id
                db_mov.moneda_pago_id = pago.moneda_id
                db_mov.tasa_pago = pago.tasa_pago
                movimiento.pagado_desde_metodo_caja_id = pago.metodo_caja_id
                movimiento.moneda_pago_id = pago.moneda_id
                movimiento.tasa_pago = pago.tasa_pago
        db_mov.gasto_id = primero.id if primero else None
        db.flush()
    elif (
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
            descripcion=(
                f"Compra de producto: {_texto_cantidad(movimiento.cantidad)} "
                f"{_texto_unidad(None, movimiento.cantidad)} de {producto.nombre}"
            ),
            total_ref=costo_total,
            ref_moneda_id=producto.moneda_id or 1,
            metodo_caja_id=movimiento.pagado_desde_metodo_caja_id,
            moneda_pago_id=getattr(movimiento, "moneda_pago_id", None),
            tasa_pago=getattr(movimiento, "tasa_pago", None),
            fecha=fecha_mov.date(),
            usuario=usuario,
            persona_entidad=_persona_compra(db, usuario, proveedor_id, proveedor_nombre),
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
            descripcion=(
                f"Llevada (flete/aduana) de producto: {_texto_cantidad(movimiento.cantidad)} "
                f"{_texto_unidad(None, movimiento.cantidad)} de {producto.nombre}"
            ),
            total_ref=Decimal(str(llevada)).quantize(Decimal("0.01")),
            ref_moneda_id=producto.moneda_id or 1,
            metodo_caja_id=movimiento.pagado_desde_metodo_caja_id,
            moneda_pago_id=getattr(movimiento, "moneda_pago_id", None),
            tasa_pago=getattr(movimiento, "tasa_pago", None),
            fecha=fecha_mov.date(),
            usuario=usuario,
            persona_entidad=_persona_compra(db, usuario, proveedor_id, proveedor_nombre),
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
    # Pago mixto de la compra: [{cuenta, moneda, monto, tasa}] (vacía si pagó
    # de una sola cuenta; el desglose vive en entrada_compra_pago).
    pagos: Optional[list[dict]] = None
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
            "pagos": self.pagos or [],
            "fiado": self.fiado,
            "fiado_a": self.fiado_a,
            "fiado_estado": self.fiado_estado,
        }


def _pagos_de_compras(
    db: Session, ids_movimientos: list[int], por_producto: bool = False
) -> dict[int, list[dict]]:
    """Desglose de pagos mixtos de compras (entrada_compra_pago) por movimiento.

    Devuelve {id_movimiento: [{cuenta, moneda, monto, tasa}]}. Sirve para el
    libro de entradas de INSUMOS (movimiento_inventario_id) y de PRODUCTOS
    (reventa/plásticos, movimiento_producto_id) cuando una compra se pagó de
    más de una cuenta.
    """
    if not ids_movimientos:
        return {}
    from app.modules.reports.model import MetodoCaja
    from app.modules.catalogos.model import Moneda

    columna = (
        model.EntradaCompraPago.movimiento_producto_id
        if por_producto
        else model.EntradaCompraPago.movimiento_inventario_id
    )
    filas = (
        db.query(model.EntradaCompraPago, MetodoCaja, Moneda)
        .join(MetodoCaja, MetodoCaja.id == model.EntradaCompraPago.metodo_caja_id)
        .join(Moneda, Moneda.id == model.EntradaCompraPago.moneda_id)
        .filter(columna.in_(ids_movimientos))
        .order_by(model.EntradaCompraPago.id)
        .all()
    )
    pagos: dict[int, list[dict]] = {}
    for pago, cuenta, moneda in filas:
        clave = pago.movimiento_producto_id if por_producto else pago.movimiento_inventario_id
        pagos.setdefault(clave, []).append({
            "id": pago.id,
            "cuenta": cuenta.nombre if cuenta else None,
            "moneda": moneda.codigo if moneda else None,
            "simbolo": moneda.simbolo if moneda else None,
            "monto": float(pago.monto or 0),
            "tasa": float(pago.tasa_cambio or 1),
            "monto_cop": float(pago.monto_en_moneda_base or 0),
        })
    return pagos


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
    pagosPorMov = _pagos_de_compras(
        db, [m.id for m, *_ in movimientos if m.tipo == "ENTRADA"],
    )

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
            pagos=pagosPorMov.get(mov.id),
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
    pagos_producto = _pagos_de_compras(
        db, [m.id for m, *_ in movimientos if m.tipo == "ENTRADA"], por_producto=True,
    )

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
            pagos=pagos_producto.get(mov.id),
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
