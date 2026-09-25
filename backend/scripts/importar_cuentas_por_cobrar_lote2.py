# -*- coding: utf-8 -*-
"""Importa el lote 2 de cuentas por cobrar históricas (fotos del cuaderno).

Crea la cadena Cliente → Cotización (APROBADA) → Pedido (ENTREGADO) → Venta
(con sus abonos como pagos), replicando el patrón de las notas N02–N44 ya
importadas. No toca inventario, producción ni caja.

Uso:
    python scripts/importar_cuentas_por_cobrar_lote2.py                     # dry-run
    python scripts/importar_cuentas_por_cobrar_lote2.py --ejecutar          # commit
    python scripts/importar_cuentas_por_cobrar_lote2.py --db-url postgresql://... [--ejecutar]
    python scripts/importar_cuentas_por_cobrar_lote2.py --usuario-id 4

Idempotente: si el marcador CxC-L2-XX ya está en la venta, la salta.
"""
import argparse
import os
import sys
import unicodedata
from datetime import date
from decimal import Decimal

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__) + "/.."))

TAG = "CxC-L2"
TELEFONO_PLACEHOLDER = "N/D"

# (codigo, cliente, cliente_id_forzado, moneda, fecha, lineas, abonos, nota)
# lineas: (cantidad, precio_unitario, descripcion)
# abonos: (fecha, monto, metodo_pago, nota)
CUENTAS = [
    {
        "codigo": "L2-01",
        "cliente": "ALEXANDER SENIAT TRAILER",
        "moneda": "COP",
        "fecha": "2024-11-22",
        "lineas": [("1", "1061000", "SALDO ANTERIOR DE LA CUENTA DE 3 PUERTAS")],
        "abonos": [("2025-02-05", "500000", "EFECTIVO_COP", "ABONO EN EFECTIVO")],
        "nota": "",
    },
    {
        "codigo": "L2-02",
        "cliente": "GUSTAVO RIOS",
        "moneda": "COP",
        "fecha": "2025-03-11",
        "lineas": [
            ("1", "207000", "LAMINA 15MM"),
            ("1", "10000", "CORTE"),
        ],
        "abonos": [],
        "nota": "",
    },
    {
        "codigo": "L2-03",
        "cliente": "MARTIN AMADO",
        "moneda": "COP",
        "fecha": "2026-08-03",
        "lineas": [
            ("52725", "150", "CMTS DE MADERA APAMATE (EVER)"),
            ("1", "35000", "FLETE"),
            ("2071", "150", "CMTS DE MADERA APAMATE ENTREGADA EL 19/08/2026"),
        ],
        "abonos": [
            ("2026-08-19", "3000000", "BANCOLOMBIA", "ABONO AL BANCOLOMBIA"),
            ("2026-08-31", "1695000", "BANCOLOMBIA", "TRANSFERENCIA BANCOLOMBIA"),
            ("2026-09-01", "2000000", "BANCOLOMBIA", "TRANSFERENCIA BANCOLOMBIA"),
            ("2026-09-19", "1500000", "BANCOLOMBIA", "TRANSFERENCIA BANCOLOMBIA"),
        ],
        "nota": "",
    },
    {
        "codigo": "L2-04",
        "cliente": "COLCHONES",
        "moneda": "USD",
        "fecha": "2026-08-25",
        "lineas": [
            ("1", "325", "COLCHON LADY BEST 1.40 DOBLE PILLON (ENTREGADO 25/08/2026)"),
            ("3", "232", "COLCHONES DALLAS CLASICO DE 1,40 (ENTREGADO 07/09/2026)"),
            ("1", "338", "COLCHON DALLAS 1 PILLON DE 1.60 (ENTREGADO 11/09/2026)"),
        ],
        "abonos": [],
        "nota": "hoja sin nombre de cliente — categoría COLCHONES",
    },
    {
        "codigo": "L2-05",
        "cliente": "MDF MES SEPTIEMBRE",
        "moneda": "COP",
        "fecha": "2026-09-18",
        "lineas": [
            ("35", "65000", "LAMINAS DE MDF DE 2,5 (ENTREGADO 18/09/2026)"),
            ("25", "125000", "LAMINAS DE MDF 9MM (ENTREGADO 18/09/2026)"),
        ],
        "abonos": [],
        "nota": "hoja sin nombre de cliente — categoría MDF MES SEPTIEMBRE",
    },
    {
        "codigo": "L2-06",
        "cliente": "ZULEIKA RAMIREZ",
        "moneda": "USD",
        "fecha": "2025-05-11",
        "lineas": [
            ("1", "5971", "CUENTA DE ZULEIKA"),
            ("1", "10235", "CUENTA DE SOFIA"),
        ],
        "abonos": [],
        "nota": "",
    },
    {
        "codigo": "L2-07",
        "cliente": "SEÑOR JORGE 0414-6941384",
        "moneda": "USD",
        "fecha": "2024-09-20",
        "lineas": [("1", "50", "SALDO PENDIENTE DE UNA CAMA CON NOCHEROS (LEONARDO)")],
        "abonos": [],
        "nota": "",
    },
    {
        "codigo": "L2-08",
        "cliente": "FAMULY STAR C.A BARQUISIMETO",
        "moneda": "USD",
        "fecha": "2024-10-28",
        "lineas": [("1", "3075", "SALDO ANTERIOR DE LA CUENTA DE VARIOS ARTICULOS VENDIDOS")],
        "abonos": [
            ("2025-02-07", "1500", "EFECTIVO_USD", "ABONO"),
            ("2025-03-12", "800", "EFECTIVO_USD", "MARCA NORVAIR DE 1800 BTU CORTINA DE AIRE"),
            ("2025-04-28", "280", "EFECTIVO_USD", "EFECTIVO"),
            ("2025-04-28", "470", "EFECTIVO_USD", "ABONO (sin fecha en el papel)"),
        ],
        "nota": "",
    },
    {
        "codigo": "L2-09",
        "cliente": "CASA VIVA MUEBLES PATSSY PUNTO FIJO",
        "moneda": "USD",
        "fecha": "2025-12-05",
        "lineas": [
            ("1", "1750", "MODULAR BLANCO"),
            ("1", "580", "POLTRONA RICLINOMATICO"),
            ("1", "1200", "COMEDOR CON SILLA PRINCESA"),
        ],
        "abonos": [
            ("2025-10-14", "470", "EFECTIVO_USD", "ABONO"),
            ("2025-12-09", "1000", "ZELLE", "ABONO ZELLE"),
            ("2025-12-20", "500", "ZELLE", "ABONO ZELLE"),
            ("2026-01-23", "500", "ZELLE", "ABONO ZELLE"),
            ("2026-02-15", "500", "ZELLE", "ABONO ZELLE"),
        ],
        "nota": "observación: debemos la base y 1 vidrio de 6",
    },
    {
        "codigo": "L2-10",
        "cliente": "ARBIN CARRILLO",
        "cliente_id": 17,
        "moneda": "COP",
        "fecha": "2026-09-10",
        "lineas": [
            ("10", "65000", "LAMINAS DE MDF DE 2,5MM (ENTREGADO 10/09/2026)"),
            ("10", "125000", "LAMINAS DE MDF DE 9MM (ENTREGADO 10/09/2026)"),
            ("1", "35000", "FLETE"),
        ],
        "abonos": [],
        "nota": "",
    },
    {
        "codigo": "L2-11",
        "cliente": "ARBIN CARRILLO",
        "cliente_id": 17,
        "moneda": "USD",
        "fecha": "2026-09-21",
        "lineas": [("1", "358", "COLCHON DALLAS 1 PILLON DE 1,60 (ENTREGADO 21/09/2026)")],
        "abonos": [],
        "nota": "revisar si es la misma deuda de la venta #17 (nota N13, $348)",
    },
    {
        "codigo": "L2-12",
        "cliente": "ARNULFO MDF",
        "cliente_id": 24,
        "moneda": "COP",
        "fecha": "2026-05-19",
        "lineas": [
            ("6", "135000", "LAMINAS DE MDF 9MM"),
            ("4", "210000", "LAMINAS DE MDF 15MM"),
            ("6", "65000", "LAMINAS DE MDF DE 2,5"),
            ("1", "30000", "FLETE"),
        ],
        "abonos": [("2026-06-06", "1000000", "EFECTIVO_COP", "ABONO EFECTIVO")],
        "nota": "entregado el 19/05/2026",
    },
    {
        "codigo": "L2-13",
        "cliente": "LUIS TAPICERO",
        "moneda": "COP",
        "fecha": "2026-03-01",
        "lineas": [("10655", "150", "CMTS DE MADERA")],
        "abonos": [],
        "nota": "cuenta de marzo 2026",
    },
    {
        "codigo": "L2-14",
        "cliente": "EVER ALVARADO",
        "moneda": "COP",
        "fecha": "2026-07-29",
        "lineas": [("2264", "160", "CMTS DE MADERA")],
        "abonos": [],
        "nota": "",
    },
    {
        "codigo": "L2-15",
        "cliente": "RAFAEL",
        "moneda": "COP",
        "fecha": "2026-04-14",
        "lineas": [
            ("1", "210000", 'SALDO DE LAMINAS DE PENTA BLANCA DE 2"'),
            ("2", "55000", "SUPER NORMAL"),
        ],
        "abonos": [("2026-07-29", "102698", "EFECTIVO_COP", "ABONO LA PASADA DE MERCANCIA DEL DIA 29/07/2026")],
        "nota": "",
    },
    {
        "codigo": "L2-16",
        "cliente": "CASA DE LOS COLCHONES ACARIGUA, C.A",
        "moneda": "USD",
        "fecha": "2026-04-17",
        "lineas": [("3", "1060", "COMEDORES DE 6 PTOS")],
        "abonos": [
            ("2026-04-17", "1000", "EFECTIVO_USD", "ABONO"),
            ("2026-04-24", "350", "EFECTIVO_VES", "ABONO EN BOLIVARES A 6.30"),
        ],
        "nota": "RIF J-30365520-3 · ACARIGUA",
    },
    {
        "codigo": "L2-17",
        "cliente": "COMANDO AEROPUERTO",
        "moneda": "COP",
        "fecha": "2024-11-23",
        "lineas": [("1", "855300", "SALDO ANTERIOR DE LA CUENTA DE VARIOS ARTICULOS VENDIDOS")],
        "abonos": [],
        "nota": "",
    },
    {
        "codigo": "L2-18",
        "cliente": "MEGA TIENDA COLCHON",
        "moneda": "USD",
        "fecha": "2024-11-22",
        "lineas": [("1", "75", "SALDO ANTERIOR DE LA CUENTA DE VARIAS COSAS")],
        "abonos": [],
        "nota": "",
    },
    {
        "codigo": "L2-19",
        "cliente": "ALFONZO",
        "moneda": "COP",
        "fecha": "2025-10-30",
        "lineas": [
            ("21849", "140", "CNTS. MADERA APAMATE"),
            ("1", "36400", "SALDO ANTERIOR DE LA FACTURA A NOMBRE DE MARTIN"),
        ],
        "abonos": [
            ("2025-11-22", "1000000", "BANCOLOMBIA", "ABONO AL BANCOLOMBIA"),
            ("2026-01-30", "1000000", "BANCOLOMBIA", "ABONO AL BANCOLOMBIA"),
            ("2026-03-26", "500000", "BANCOLOMBIA", "ABONO AL BANCOLOMBIA"),
        ],
        "nota": "",
    },
    {
        "codigo": "L2-20",
        "cliente": "JOHEL VELANDIA",
        "cliente_id": 15,
        "moneda": "COP",
        "fecha": "2026-04-29",
        "lineas": [("1", "100000", "SILLA PARA PEINADORA ISIDRO")],
        "abonos": [
            ("2026-04-29", "65000", "EFECTIVO_COP", "LAMINA DE MDF DE 2,5 (ABONO EN ESPECIE)"),
            ("2026-05-12", "13980", "EFECTIVO_COP", "ABONO A LA SILLA DEL 29/04/2026"),
        ],
        "nota": "fabricación",
    },
    {
        "codigo": "L2-21",
        "cliente": "JOHEL VELANDIA",
        "cliente_id": 15,
        "moneda": "COP",
        "fecha": "2026-04-11",
        "lineas": [
            ("10207", "140", "CMTS DE MADERA APAMATE"),
            ("1", "35000", "FLETE"),
        ],
        "abonos": [
            ("2026-05-12", "1450000", "BANCOLOMBIA", "ABONO POR BANCOLOMBIA"),
            ("2026-05-12", "13980", "EFECTIVO_COP", "ABONADO A LA SILLA DEL 29/04/2026"),
        ],
        "nota": "madera (queda pagada)",
    },
    {
        "codigo": "L2-22",
        "cliente": "SR REY BORQUES",
        "moneda": "COP",
        "fecha": "2025-05-17",
        "lineas": [
            ("1", "136000", "LAMINA DE MDF DE 9MM"),
            ("1", "136000", "LAMINA DE MDF 9"),
        ],
        "abonos": [
            ("2025-05-17", "100000", "EFECTIVO_COP", "ABONO"),
            ("2025-06-05", "68000", "EFECTIVO_COP", "ABONO EFECTIVO"),
        ],
        "nota": "",
    },
    {
        "codigo": "L2-23",
        "cliente": "HECTOR MULATERO LUIS POLO",
        "moneda": "COP",
        "fecha": "2025-04-15",
        "lineas": [
            ("1", "175000", "LAMINA DE 12 MM"),
            ("1", "10000", "CARRERA A AGUAS CALIENTES"),
        ],
        "abonos": [],
        "nota": "",
    },
    {
        "codigo": "L2-24",
        "cliente": "GERMAN NIETO",
        "moneda": "COP",
        "fecha": "2025-05-29",
        "lineas": [
            ("1", "2000000", "FLETE PARA SAN FERNANDO DE PURE Y BARINA"),
            ("1", "620000", "FACTURA INCLUYENDO RETENCION, IVA, YGTF Y PAGO DE SELLADA"),
        ],
        "abonos": [
            ("2025-06-02", "2200000", "EFECTIVO_COP", "ABONO (600-50 QUE LE PRESTO OSCAR, SALDO 550 DOLARES X 4000)"),
        ],
        "nota": "V-1061814 · tel 04121659596",
    },
    {
        "codigo": "L2-25",
        "cliente": "SARGENTO ROA",
        "moneda": "COP",
        "fecha": "2026-01-23",
        "lineas": [
            ("40", "75630.25", "MDF T 9MM 183244"),
            ("3", "193277.31", "UNICOR MDF RH HUMO S/B 5.5 MM TM 183"),
            ("3", "18067.23", "AFIX MONTAJE PU X 310 TUBO X 310 ML"),
            ("1", "298319.33", "PRIMA TAUSA RH 15MM 1.83*2.44 LUNA"),
        ],
        "abonos": [],
        "nota": "total papel 3.957.563",
    },
]

ESPERADO_CARGOS = {"COP": Decimal("33766992.95"), "USD": Decimal("27833")}
ESPERADO_ABONOS = {"COP": Decimal("16208658"), "USD": Decimal("7370")}


def normalizar_nombre(nombre: str) -> str:
    sin_acentos = "".join(
        c for c in unicodedata.normalize("NFD", nombre.strip().upper()) if unicodedata.category(c) != "Mn"
    )
    return " ".join(sin_acentos.split())


def telefono_placeholder(nombre: str) -> str:
    return ("N/D-" + normalizar_nombre(nombre).replace(" ", "-"))[:50]


def resolver_moneda(db, codigo: str):
    from app.modules.catalogos.model import Moneda

    moneda = db.query(Moneda).filter(Moneda.codigo == codigo).first()
    if not moneda:
        raise ValueError(f"La moneda {codigo} no existe en el catálogo.")
    return moneda


def obtener_usuario_migrador(db, usuario_id: int | None):
    from app.modules.users.model import Usuario
    from app.modules.catalogos.model import Rol

    if usuario_id:
        usuario = db.query(Usuario).filter(Usuario.id == usuario_id).first()
        if not usuario:
            raise ValueError(f"El usuario {usuario_id} no existe.")
        return usuario
    usuario = db.query(Usuario).join(Usuario.roles).filter(Rol.nombre == "Dueño").order_by(Usuario.id).first()
    if not usuario:
        raise ValueError("No hay usuario Dueño en la BD. Pasa --usuario-id explícito.")
    return usuario


def obtener_o_crear_cliente(db, clientes_por_clave, cuenta, usuario):
    from app.modules.clients.model import Client

    if cuenta.get("cliente_id"):
        cliente = db.query(Client).filter(Client.id == cuenta["cliente_id"]).first()
        if not cliente:
            raise ValueError(f"El cliente id={cuenta['cliente_id']} no existe.")
        return cliente, "forzado"

    clave = normalizar_nombre(cuenta["cliente"])
    cliente = clientes_por_clave.get(clave)
    if cliente:
        return cliente, "existente"

    fecha = date.fromisoformat(cuenta["fecha"])
    cliente = Client(
        nombre=cuenta["cliente"].strip(),
        telefono=telefono_placeholder(cuenta["cliente"]),
        fecha_registro=fecha,
        creado_por_id=usuario.id,
        actualizado_por_id=usuario.id,
    )
    db.add(cliente)
    db.flush()
    clientes_por_clave[clave] = cliente
    return cliente, "NUEVO"


def estado_venta(total: Decimal, pagado: Decimal) -> str:
    if pagado <= 0:
        return "PENDIENTE"
    if pagado + Decimal("0.009") >= total:
        return "PAGADA"
    return "ABONADA"


def crear_cuenta(db, usuario, cliente, cuenta, moneda, total, abonos):
    from app.modules.quotes.model import Cotizacion, DetalleCotizacion
    from app.modules.orders.model import Pedido
    from app.modules.sales.model import Venta, Pago

    codigo = cuenta["codigo"]
    marca = f"{TAG}-{codigo}"
    fecha = date.fromisoformat(cuenta["fecha"])
    nota = cuenta.get("nota") or ""
    obs_base = f"Importación histórica — cuenta por cobrar {marca}"
    if nota:
        obs_base += f" · {nota}"

    cotizacion = Cotizacion(
        cliente_id=cliente.id,
        fecha=fecha,
        estado="APROBADA",
        total_estimado=total,
        moneda_id=moneda.id,
        tasa_cambio=Decimal("1.0"),
        total_en_moneda_base=total,
        observaciones=f"{marca} · cuenta por cobrar histórica (importación) · montos en {moneda.codigo}",
        creado_por_id=usuario.id,
        actualizado_por_id=usuario.id,
    )
    db.add(cotizacion)
    db.flush()
    for cantidad, precio, descripcion in cuenta["lineas"]:
        db.add(
            DetalleCotizacion(
                cotizacion_id=cotizacion.id,
                producto_id=None,
                material_id=None,
                tipo_item="FABRICADO",
                cantidad=Decimal(cantidad),
                precio=Decimal(precio),
                observaciones=descripcion,
            )
        )

    pedido = Pedido(
        cotizacion_id=cotizacion.id,
        cliente_id=cliente.id,
        fecha=fecha,
        estado="ENTREGADO",
        observaciones=obs_base,
        fecha_entrega_estimada=fecha,
        creado_por_id=usuario.id,
        actualizado_por_id=usuario.id,
    )
    db.add(pedido)
    db.flush()

    pagado = sum((Decimal(monto) for _, monto, _, _ in abonos), Decimal("0"))
    venta = Venta(
        pedido_id=pedido.id,
        cliente_id=cliente.id,
        moneda_id=moneda.id,
        fecha=fecha,
        total=total,
        estado=estado_venta(total, pagado),
        tasa_cambio=Decimal("1.0"),
        total_en_moneda_base=total,
        observaciones=obs_base,
        creado_por_id=usuario.id,
        actualizado_por_id=usuario.id,
    )
    db.add(venta)
    db.flush()

    for fecha_abono, monto, metodo, nota_abono in abonos:
        db.add(
            Pago(
                venta_id=venta.id,
                moneda_id=moneda.id,
                fecha=date.fromisoformat(fecha_abono),
                monto=Decimal(monto),
                tasa_cambio=Decimal("1.0"),
                monto_en_moneda_base=Decimal(monto),
                metodo_pago=metodo,
                observaciones=nota_abono,
            )
        )
    db.flush()
    return venta


def migrar(args) -> int:
    if args.db_url:
        os.environ["DATABASE_URL"] = args.db_url

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
    from app.modules.sales.model import Venta

    db = session_local()
    try:
        db.execute(text("SELECT pg_advisory_xact_lock(hashtext('cxc-lote2'))"))

        monedas = {codigo: resolver_moneda(db, codigo) for codigo in ("COP", "USD")}
        usuario = obtener_usuario_migrador(db, args.usuario_id)
        clientes_por_clave = {normalizar_nombre(c.nombre): c for c in db.query(Client).all()}

        print(f"BD: {db.bind.url.render_as_string(hide_password=True)}")
        print(f"Usuario migrador: {usuario.nombre_usuario} (id={usuario.id})")
        print(f"Cuentas: {len(CUENTAS)}  ·  Modo: {'EJECUTAR' if args.ejecutar else 'DRY-RUN'}")
        print("-" * 118)

        creadas, saltadas, clientes_nuevos, errores = 0, 0, 0, []
        cargos = {"COP": Decimal("0"), "USD": Decimal("0")}
        abonado = {"COP": Decimal("0"), "USD": Decimal("0")}

        for cuenta in CUENTAS:
            try:
                moneda = monedas[cuenta["moneda"]]
                total = sum(
                    (Decimal(cant) * Decimal(precio) for cant, precio, _ in cuenta["lineas"]),
                    Decimal("0"),
                ).quantize(Decimal("0.01"))
                pagado = sum((Decimal(m) for _, m, _, _ in cuenta["abonos"]), Decimal("0"))

                ya_migrada = (
                    db.query(Venta).filter(Venta.observaciones.like(f"%{TAG}-{cuenta['codigo']}%")).first()
                )
                if ya_migrada:
                    saltadas += 1
                    cargos[cuenta["moneda"]] += total
                    abonado[cuenta["moneda"]] += pagado
                    print(f"  · SKIP   {cuenta['codigo']}  {cuenta['cliente']:<38} ya migrada (venta #{ya_migrada.id})")
                    continue

                cliente, estado_cliente = obtener_o_crear_cliente(db, clientes_por_clave, cuenta, usuario)
                if estado_cliente == "NUEVO":
                    clientes_nuevos += 1

                venta = crear_cuenta(db, usuario, cliente, cuenta, moneda, total, cuenta["abonos"])

                cargos[cuenta["moneda"]] += total
                abonado[cuenta["moneda"]] += pagado
                creadas += 1
                saldo = total - pagado
                print(
                    f"  · {'CREAR' if args.ejecutar else 'DRY  '} {cuenta['codigo']}  {cuenta['cliente']:<38} "
                    f"{total:>14,.2f} {cuenta['moneda']}  abonos={pagado:>13,.2f}  saldo={saldo:>14,.2f}  "
                    f"venta=#{venta.id} estado={venta.estado} cliente={estado_cliente}"
                )
            except Exception as exc:
                errores.append((cuenta["codigo"], cuenta["cliente"], str(exc)))

        print("-" * 118)
        print(f"Ventas nuevas: {creadas}  ·  Ya migradas (skip): {saltadas}  ·  Clientes nuevos: {clientes_nuevos}")
        for cod in ("COP", "USD"):
            saldo = cargos[cod] - abonado[cod]
            print(
                f"  {cod}: cargos {cargos[cod]:>16,.2f}  ·  abonos {abonado[cod]:>15,.2f}  ·  saldo {saldo:>16,.2f}"
                f"   (esperado cargos {ESPERADO_CARGOS[cod]:,.2f} / abonos {ESPERADO_ABONOS[cod]:,.2f})"
            )

        for cod in ("COP", "USD"):
            if cargos[cod] != ESPERADO_CARGOS[cod] or abonado[cod] != ESPERADO_ABONOS[cod]:
                errores.append(("TOTALES", cod, "Los totales no cuadran con la transcripción. NO migrar sin revisar."))

        for codigo, cliente, error in errores:
            print(f"  ✗ ERROR {codigo} {cliente}: {error}")

        if errores and args.ejecutar:
            db.rollback()
            print("\n✗ Se abortó la ejecución por errores. No se commiteó nada.")
            return 1

        if args.ejecutar:
            db.commit()
            print("\n✓ Importación COMMITADA.")
            print("  Rollback de emergencia:")
            print(f"    DELETE FROM pago WHERE venta_id IN (SELECT id FROM venta WHERE observaciones LIKE '%{TAG}-%');")
            print(f"    DELETE FROM venta WHERE observaciones LIKE '%{TAG}-%';")
            print(f"    DELETE FROM pedido WHERE observaciones LIKE '%{TAG}-%';")
            print(f"    DELETE FROM detalle_cotizacion WHERE cotizacion_id IN (SELECT id FROM cotizacion WHERE observaciones LIKE '%{TAG}-%');")
            print(f"    DELETE FROM cotizacion WHERE observaciones LIKE '%{TAG}-%';")
        else:
            db.rollback()
            estado = "CON ERRORES — revisa antes de ejecutar" if errores else "OK para ejecutar con --ejecutar"
            print(f"\n· Dry-run completo ({estado}). No se escribió nada en la BD.")
        return 0
    finally:
        db.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Importa el lote 2 de cuentas por cobrar históricas.")
    parser.add_argument("--ejecutar", action="store_true", help="Commitea los cambios (default: dry-run)")
    parser.add_argument("--usuario-id", type=int, default=None, help="Usuario responsable (default: primer Dueño)")
    parser.add_argument("--db-url", type=str, default=None, help="DATABASE_URL alternativa (ej. producción Neon)")
    args = parser.parse_args()
    sys.exit(migrar(args))


if __name__ == "__main__":
    main()
