# -*- coding: utf-8 -*-
"""Migración de deudores históricos (hoja "Deuda Pendiente x Cobrar y Entregados").

Crea la cadena Cliente → Cotización (APROBADA) → Pedido (ENTREGADO) → Venta
(PENDIENTE) por cada fila de la hoja, sin tocar inventario ni stock.

Uso:
    python scripts/importar_deudores_historicos.py            # dry-run
    python scripts/importar_deudores_historicos.py --ejecutar # commit real
    python scripts/importar_deudores_historicos.py --tasa-usd 4000
    python scripts/importar_deudores_historicos.py --db-url postgresql://...  # otra BD

Notas:
- Idempotente: si re-corres, salta filas ya migradas (match por cliente+fecha+total
  con la marca en observaciones).
- Race-safe: advisory lock transaccional de Postgres; dos ejecuciones simultáneas
  se serializan.
- Tasa USD→COP: usa --tasa-usd si se pasa; si no, busca la tasa registrada en el
  sistema para la fecha de cada venta; si no hay ninguna, el modo --ejecutar
  aborta (nunca migra USD con tasa 1:1 silenciosa).
"""
import argparse
import os
import sys
import unicodedata
from datetime import date
from decimal import Decimal

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__) + "/.."))

TAG_MIGRACION = "MIGRACION-DEUDORES-HISTORICOS"
TELEFONO_PLACEHOLDER = "N/D"
TIPO_PRODUCTO_DEUDA = "DEUDA HISTORICA"
NOMBRE_PRODUCTO_DEUDA = "DEUDA HISTÓRICA (MIGRACIÓN)"

# (fecha ISO, cliente, monto, moneda) — transcripción de la hoja del 2026-09-08.
# Agustino (325 + 696 del 14/09) excluido a pedido del Dueño; el 365.000 COP de
# Yofre Velandia va con fecha 12-01-2026 (corrección verbal de Daniel).
DATA: list[tuple[str, str, str, str]] = [
    # ---- Página 1 ----
    ("2026-06-04", "Daniel Gomez Montaña", "500", "USD"),
    ("2026-08-13", "Lilibeth Villalobos", "4.804", "USD"),
    ("2026-09-02", "Maria Angelica", "159", "USD"),
    ("2026-08-31", "Felix Enrique", "134", "USD"),
    ("2026-09-03", "Edwar Emmanuel", "700", "USD"),
    ("2026-04-16", "Tatiana", "51", "USD"),
    ("2026-08-11", "Yuraima", "911,75", "USD"),
    ("2026-07-28", "Zuleima", "520", "USD"),
    ("2026-07-27", "Cesar Patiño", "7.286", "USD"),
    ("2026-06-04", "Yofre Velandia", "618", "USD"),
    ("2026-01-12", "Yofre Velandia", "365.000", "COP"),
    ("2026-07-27", "Capitan Almoranday", "2.980.000", "COP"),
    ("2026-08-11", "Arbin Castillo", "434", "USD"),
    ("2026-08-06", "Mayor Morales", "115", "USD"),
    ("2026-06-10", "Maria Sanchez", "55", "USD"),
    ("2026-07-09", "Hector Cumpleaños de Lilibeth", "143", "USD"),
    ("2026-01-20", "Yefrey Rodriguez", "817.000", "COP"),
    ("2026-05-11", "Wilber Auxilio Gonzalez / Arnulfo", "364", "USD"),
    ("2026-07-02", "Arnulfo", "1.164.500", "COP"),
    ("2026-06-12", "Sargento Varela", "336.000", "COP"),
    ("2026-08-05", "UniHome", "33.995", "USD"),
    ("2026-04-28", "Yeferson Higuaran", "1.369", "USD"),
    ("2026-04-28", "Osman Señal", "1.150.000", "COP"),
    ("2026-04-07", "SENIAT Yain", "133.400", "COP"),
    ("2026-03-30", "Eldis Contreras (Pocho)", "969", "USD"),
    ("2026-03-30", "Eldis Contreras (Pocho)", "1.903", "USD"),
    ("2026-04-01", "Zodi", "934", "USD"),
    ("2026-01-23", "General Santiago Eddy Delgado", "863", "USD"),
    ("2026-02-02", "Zuleika Ramirez", "16.206", "USD"),
    # ---- Página 2 ----
    ("2026-06-23", "Paola Bonilla", "32", "USD"),
    ("2026-03-12", "Capitán Pinto", "170", "USD"),
    ("2026-03-18", "Gregorio Bento", "546", "USD"),
    ("2026-07-11", "Morice Ochoa", "236", "USD"),
    ("2026-02-16", "Jhon Castellano", "280.000", "COP"),
    ("2026-03-10", "Patsy Antonio", "560", "USD"),
    ("2025-11-04", "Sargento Caceres", "1.014.470", "COP"),
    ("2025-12-01", "Jhon Carrillo", "2.200.000", "COP"),
    ("2025-09-09", "Brayan Gomez Tránsito", "1.295.000", "COP"),
    ("2025-08-20", "Yorledy Farfan", "388", "USD"),
    ("2025-07-12", "Willian Cristóbal", "310", "USD"),
    ("2024-12-04", "Sandra Garcia", "219", "USD"),
    ("2025-08-25", "CICPC Ureña", "200.000", "COP"),
    ("2025-09-05", "Dayana", "1.400.000", "COP"),
]

# Totales verificados contra la hoja (protección contra errores de transcripción).
ESPERADO_USD = Decimal("75494.75")
ESPERADO_COP = Decimal("13335370")


def parsear_monto(texto: str) -> Decimal:
    """Convierte montos de la hoja: '4.804'→4804, '911,75'→911.75, '365.000'→365000."""
    limpio = texto.strip().replace(" ", "").replace(".", "").replace(",", ".")
    valor = Decimal(limpio)
    if valor <= 0:
        raise ValueError(f"Monto inválido: {texto!r}")
    return valor


def normalizar_nombre(nombre: str) -> str:
    """Clave de match de clientes: mayúsculas, sin acentos, espacios colapsados."""
    sin_acentos = "".join(
        c for c in unicodedata.normalize("NFD", nombre.strip().upper()) if unicodedata.category(c) != "Mn"
    )
    return " ".join(sin_acentos.split())


def resolver_moneda(db, codigo: str):
    from app.modules.catalogos.model import Moneda

    moneda = db.query(Moneda).filter(Moneda.codigo == codigo).first()
    if not moneda:
        raise ValueError(f"La moneda {codigo} no existe en el catálogo.")
    return moneda


def obtener_tasa_sistema(db, moneda_id: int, fecha: date) -> Decimal | None:
    """Tasa moneda→COP registrada en el sistema para esa fecha (None si no hay)."""
    from app.modules.tasas_cambio.model import TasaCambio

    tasa = (
        db.query(TasaCambio)
        .filter(
            TasaCambio.moneda_origen_id == moneda_id,
            TasaCambio.moneda_destino_id == 1,
            TasaCambio.fecha <= fecha,
        )
        .order_by(TasaCambio.fecha.desc())
        .first()
    )
    return Decimal(str(tasa.valor)) if tasa else None


def obtener_usuario_migrador(db, usuario_id: int | None):
    from app.modules.users.model import Usuario
    from app.modules.catalogos.model import Rol

    if usuario_id:
        usuario = db.query(Usuario).filter(Usuario.id == usuario_id).first()
        if not usuario:
            raise ValueError(f"El usuario {usuario_id} no existe.")
        return usuario
    usuario = (
        db.query(Usuario)
        .join(Usuario.roles)
        .filter(Rol.nombre == "Dueño")
        .order_by(Usuario.id)
        .first()
    )
    if not usuario:
        raise ValueError("No hay usuario Dueño en la BD. Pasa --usuario-id explícito.")
    return usuario


def ensure_producto_deuda(db):
    """Producto genérico e inactivo al que apuntan los detalles migrados.

    Los schemas de pedido/venta exigen producto_id para tipo_item FABRICADO;
    sin él, GET /pedido/ y GET /venta/ rompen la validación de respuesta.
    """
    from app.modules.catalogos.model import TipoProducto
    from app.modules.productos.model import Producto

    tipo = db.query(TipoProducto).filter(TipoProducto.nombre == TIPO_PRODUCTO_DEUDA).first()
    if not tipo:
        tipo = TipoProducto(nombre=TIPO_PRODUCTO_DEUDA)
        db.add(tipo)
        db.flush()
    producto = db.query(Producto).filter(Producto.nombre == NOMBRE_PRODUCTO_DEUDA).first()
    if not producto:
        producto = Producto(
            nombre=NOMBRE_PRODUCTO_DEUDA,
            tipo_producto_id=tipo.id,
            descripcion="Línea contenedora de deudas históricas migradas (sin producto físico).",
            activo=False,
            es_reventa=False,
            moneda_id=1,
        )
        db.add(producto)
        db.flush()
    return producto


def obtener_o_crear_cliente(db, clientes_por_clave: dict, nombre: str, fecha: date, usuario):
    """Matchea el cliente por nombre normalizado; lo crea con teléfono placeholder si no existe."""
    clave = normalizar_nombre(nombre)
    cliente = clientes_por_clave.get(clave)
    if cliente:
        return cliente, "existente"
    cliente = Client(
        nombre=nombre.strip(),
        telefono=TELEFONO_PLACEHOLDER,
        fecha_registro=fecha,
        creado_por_id=usuario.id,
        actualizado_por_id=usuario.id,
    )
    db.add(cliente)
    db.flush()
    clientes_por_clave[clave] = cliente
    return cliente, "NUEVO"


def resolver_tasa(db, tasa_usd_cli, moneda, codigo_moneda: str, fecha: date) -> Decimal:
    """COP siempre 1.0; USD exige tasa del CLI o registrada en el sistema.

    El guard `tasa <= 1` es deliberado: una USD→COP real nunca es ≤1 y sin él
    una BD sin tasas migraría USD a tasa 1:1 silenciosa, corrompiendo el libro base.
    """
    if codigo_moneda != "USD":
        return Decimal("1.0")
    tasa = Decimal(str(tasa_usd_cli)) if tasa_usd_cli else obtener_tasa_sistema(db, moneda.id, fecha)
    if not tasa or tasa <= 1:
        raise ValueError("Sin tasa USD→COP registrada para esa fecha. Usa --tasa-usd o registra la tasa.")
    return tasa


def crear_cadena_deuda(db, usuario, producto_deuda, cliente, fecha: date, monto: Decimal, moneda, tasa: Decimal):
    """Crea Cotización (APROBADA) → Pedido (ENTREGADO) → Venta (PENDIENTE) + detalles + evento de auditoría."""
    total_base = (monto * tasa).quantize(Decimal("0.01"))

    cotizacion = Cotizacion(
        cliente_id=cliente.id,
        fecha=fecha,
        estado="APROBADA",
        total_estimado=monto,
        moneda_id=moneda.id,
        tasa_cambio=tasa,
        total_en_moneda_base=total_base,
        observaciones=TAG_MIGRACION,
        creado_por_id=usuario.id,
        actualizado_por_id=usuario.id,
    )
    db.add(cotizacion)
    db.flush()
    db.add(
        DetalleCotizacion(
            cotizacion_id=cotizacion.id,
            producto_id=producto_deuda.id,
            cantidad=Decimal("1"),
            precio=monto,
            observaciones="Deuda histórica migrada",
        )
    )

    pedido = Pedido(
        cotizacion_id=cotizacion.id,
        cliente_id=cliente.id,
        fecha=fecha,
        estado="ENTREGADO",
        observaciones=f"{TAG_MIGRACION} · pedido despachado pendiente de cobro",
        fecha_entrega_estimada=fecha,
        creado_por_id=usuario.id,
        actualizado_por_id=usuario.id,
    )
    db.add(pedido)
    db.flush()
    db.add(
        DetallePedido(
            pedido_id=pedido.id,
            producto_id=producto_deuda.id,
            tipo_item="FABRICADO",
            cantidad=Decimal("1"),
            precio=monto,
            descripcion_especifica="Deuda histórica migrada",
        )
    )

    venta = Venta(
        pedido_id=pedido.id,
        cliente_id=cliente.id,
        moneda_id=moneda.id,
        fecha=fecha,
        total=monto,
        estado="PENDIENTE",
        tasa_cambio=tasa,
        total_en_moneda_base=total_base,
        observaciones=TAG_MIGRACION,
        creado_por_id=usuario.id,
        actualizado_por_id=usuario.id,
    )
    db.add(venta)
    db.flush()
    db.add(
        DetalleVenta(
            venta_id=venta.id,
            producto_id=producto_deuda.id,
            tipo_item="FABRICADO",
            cantidad=Decimal("1"),
            precio=monto,
            descuento=Decimal("0"),
        )
    )
    record_event(
        db,
        actor=usuario,
        action="CREATE",
        entity_type="venta",
        entity_id=venta.id,
        after={"origen": TAG_MIGRACION, "cliente": cliente.nombre, "total": float(monto), "moneda": moneda.codigo},
    )
    return venta


def migrar(args) -> int:
    if args.db_url:
        os.environ["DATABASE_URL"] = args.db_url

    # Registro completo de mappers (mismo listado que alembic/env.py): el
    # modelo Usuario referencia a Empleado y otras relaciones cruzadas que
    # solo existen si sus módulos fueron importados.
    import app.modules.catalogos.model  # noqa: F401
    import app.modules.clients.model  # noqa: F401
    import app.modules.productos.model  # noqa: F401
    import app.modules.quotes.model  # noqa: F401
    import app.modules.orders.model  # noqa: F401
    import app.modules.production.model  # noqa: F401
    import app.modules.inventory.model  # noqa: F401
    import app.modules.users.model  # noqa: F401
    import app.modules.purchases.model  # noqa: F401
    import app.modules.sales.model  # noqa: F401
    import app.modules.facturacion.model  # noqa: F401
    import app.modules.gastos.model  # noqa: F401
    import app.modules.proveedores.model  # noqa: F401
    import app.modules.empleados.model  # noqa: F401
    import app.modules.envios.model  # noqa: F401
    import app.modules.tasas_cambio.model  # noqa: F401
    import app.modules.reports.model  # noqa: F401
    import app.modules.auditoria.model  # noqa: F401
    import app.modules.costos_produccion.model  # noqa: F401
    import app.modules.nomina.model  # noqa: F401
    import app.modules.adjuntos.model  # noqa: F401
    import app.modules.cuentas_por_pagar.model  # noqa: F401

    from sqlalchemy import text

    from app.db.session import session_local
    from app.modules.clients.model import Client
    from app.modules.quotes.model import Cotizacion, DetalleCotizacion
    from app.modules.orders.model import Pedido, DetallePedido
    from app.modules.sales.model import Venta, DetalleVenta
    from app.modules.auditoria.service import record_event

    filas = [
        (date.fromisoformat(f), nombre, parsear_monto(monto), moneda)
        for f, nombre, monto, moneda in DATA
    ]

    db = session_local()
    try:
        # Serializa migraciones concurrentes (se libera con commit/rollback).
        db.execute(text("SELECT pg_advisory_xact_lock(hashtext('migracion-deudores'))"))

        monedas = {codigo: resolver_moneda(db, codigo) for codigo in ("COP", "USD")}
        producto_deuda = ensure_producto_deuda(db)
        usuario = obtener_usuario_migrador(db, args.usuario_id)
        clientes_por_clave: dict[str, Client] = {
            normalizar_nombre(c.nombre): c for c in db.query(Client).all()
        }

        print(f"BD: {db.bind.url.render_as_string(hide_password=True)}")
        print(f"Usuario migrador: {usuario.nombre_usuario} (id={usuario.id})")
        if args.tasa_usd:
            print(f"Tasa USD→COP forzada por CLI: {args.tasa_usd}")
        print(f"Filas a migrar: {len(filas)}  ·  Modo: {'EJECUTAR' if args.ejecutar else 'DRY-RUN'}")
        print("-" * 100)

        creadas, saltadas, clientes_nuevos, errores = 0, 0, 0, []
        totales: dict[str, Decimal] = {"USD": Decimal("0"), "COP": Decimal("0")}
        tasas_usd_usadas: set[str] = set()

        for fecha, nombre, monto, codigo_moneda in filas:
            try:
                moneda = monedas[codigo_moneda]
                cliente, cliente_estado = obtener_o_crear_cliente(db, clientes_por_clave, nombre, fecha, usuario)
                if cliente_estado == "NUEVO":
                    clientes_nuevos += 1

                # Idempotencia: misma marca + cliente + fecha + total ya migrada.
                ya_migrada = (
                    db.query(Venta)
                    .filter(
                        Venta.cliente_id == cliente.id,
                        Venta.fecha == fecha,
                        Venta.total == monto,
                        Venta.observaciones == TAG_MIGRACION,
                    )
                    .first()
                )
                if ya_migrada:
                    saltadas += 1
                    totales[codigo_moneda] += monto
                    print(f"  · SKIP  {fecha}  {nombre:<38} {monto:>12,.2f} {codigo_moneda} (ya migrada #{ya_migrada.id})")
                    continue

                tasa = resolver_tasa(db, args.tasa_usd, moneda, codigo_moneda, fecha)
                if codigo_moneda == "USD":
                    tasa_origen = "CLI" if args.tasa_usd else "sistema"
                    tasas_usd_usadas.add(f"{tasa} ({tasa_origen})")

                venta = crear_cadena_deuda(db, usuario, producto_deuda, cliente, fecha, monto, moneda, tasa)

                totales[codigo_moneda] += monto
                creadas += 1
                print(
                    f"  · {'CREAR' if args.ejecutar else 'DRY  '} {fecha}  {nombre:<38} {monto:>12,.2f} {codigo_moneda}"
                    f"  cliente={cliente_estado:<8} venta=#{venta.id} tasa={tasa}"
                )
            except Exception as exc:
                errores.append((nombre, str(exc)))

        print("-" * 100)
        print(f"Ventas nuevas: {creadas}  ·  Ya migradas (skip): {saltadas}  ·  Clientes nuevos: {clientes_nuevos}")
        print(f"Total USD: {totales['USD']:,.2f} (esperado {ESPERADO_USD:,.2f})  ·  Total COP: {totales['COP']:,.2f} (esperado {ESPERADO_COP:,.2f})")
        if tasas_usd_usadas:
            print(f"Tasas USD usadas: {', '.join(sorted(tasas_usd_usadas))}")

        if totales["USD"] != ESPERADO_USD or totales["COP"] != ESPERADO_COP:
            errores.append(("TOTALES", "Los totales no cuadran con la hoja verificada. NO migrar sin revisar."))

        for nombre, error in errores:
            print(f"  ✗ ERROR {nombre}: {error}")

        if errores and args.ejecutar:
            db.rollback()
            print("\n✗ Se abortó la ejecución por errores. No se commiteó nada.")
            return 1

        if args.ejecutar:
            db.commit()
            print("\n✓ Migración COMMITADA. Verifica en /ventas → Cuentas por cobrar.")
            print("  Rollback de emergencia:")
            print("    DELETE FROM venta WHERE observaciones = '" + TAG_MIGRACION + "';")
            print("    DELETE FROM pedido WHERE observaciones LIKE '" + TAG_MIGRACION + "%';")
            print("    DELETE FROM cotizacion WHERE observaciones = '" + TAG_MIGRACION + "';")
            print("  (Los clientes creados quedan; son datos válidos del negocio.)")
        else:
            db.rollback()
            estado = "CON ERRORES — revisa antes de ejecutar" if errores else "OK para ejecutar con --ejecutar"
            print(f"\n· Dry-run completo ({estado}). No se escribió nada en la BD.")
        return 0
    finally:
        db.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Migra la hoja de deudores históricos al ERP.")
    parser.add_argument("--ejecutar", action="store_true", help="Commitea los cambios (default: dry-run)")
    parser.add_argument("--tasa-usd", type=float, default=None, help="Tasa USD→COP forzada para todas las ventas en USD")
    parser.add_argument("--usuario-id", type=int, default=None, help="Usuario responsable (default: primer Dueño)")
    parser.add_argument("--db-url", type=str, default=None, help="DATABASE_URL alternativa (ej. producción Neon)")
    args = parser.parse_args()
    sys.exit(migrar(args))


if __name__ == "__main__":
    main()
