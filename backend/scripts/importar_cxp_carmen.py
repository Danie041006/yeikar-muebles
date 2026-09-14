# -*- coding: utf-8 -*-
"""Migra la hoja de control de SR CARMEN MANILLAS (insumos de fábrica) al ERP.

Crea el proveedor SR CARMEN MANILLAS y una CuentaPorPagar por FECHA con un
renglón (DetalleCuentaPorPagar) por cada ítem de la hoja: descripción,
cantidad, precio unitario, y el cliente/obra destino (columna "CLIENTE").
Los ABONOS de la hoja se aplican FIFO sobre las deudas más antiguas.

La hoja original es una "cuenta de control" manuscrita: fecha · cant ·
descripción · precio unitario · total · abonos · saldo · cliente/obra.
Cada renglón responde "qué se compró y PARA QUIÉN", que es justo el detalle
que ahora guarda el ERP.

Regla de miles: NO CUADRA con un factor único. La hoja mezcla dos notaciones:
renglones que ya dan el total sin miles (145×2=290 ✓, 30×5=150 ✓) y renglones
donde el total está dividido por 1000 (600×20=12.000 pero escrito 12.00;
50×70=3.500 pero escrito 3.50). Por eso NO se migra con montos automáticos
hasta definir el monto REAL de cada renglón (la columna "total" de la hoja,
revisada a mano). El script queda como estructura de migración lista.

Uso:
    python scripts/importar_cxp_carmen.py                       # dry-run
    python scripts/importar_cxp_carmen.py --x1000 --ejecutar    # aplica (NO recomendado: no cuadra)
    python scripts/importar_cxp_carmen.py --db-url postgresql://... # otra BD
"""
import argparse
import os
import sys
from datetime import date
from decimal import Decimal

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__) + "/.."))

TAG = "MIGRA-CARMEN"

PROVEEDOR_NOMBRE = "SR CARMEN MANILLAS"
PROVEEDOR_RIESGO_TAG = "ferretería/insumos de fábrica"

# (fecha, cantidad, descripción, precio_unitario, destino)
# Transcripción fiel de la hoja. Los renglones sin fecha heredan la anterior.
RENGLONES: list[tuple[str, str, str, str, str]] = [
    ("15/12/2025", "20", "SOPOLI 90 (TOPE PARA COLGAR CUADROS)", "600", "FABRICA"),
    ("17/12/2025", "2", "HERRAJE DE CAMA BAUL", "145.00", "CAMA COMANDANTE"),
    ("17/12/2025", "1", "CHAPA DE PUERTA CUADRADA ALCOBA", "63.00", "ZULEIKA"),
    ("17/12/2025", "1", "CHAPA DE PUERTA CUADRADA BAÑO", "63.00", "ZULEIKA"),
    ("24/12/2025", "4", "RIEL PLASTICO", "8.00", "VITRINAS DAYANA"),
    ("19/1/2026", "4", "PERFIL ESQUINERO DE LUZ LED DE 4 METROS", "26.00", "JHONATAN AMAZONIA"),
    ("19/1/2026", "6", "CHAPA CUADRADAS BAÑO", "63.00", "CAPITAN RAMIREZ"),
    ("19/1/2026", "2", "CHAPA CUADRADAS ALCOBA", "63.00", "CAPITAN RAMIREZ"),
    ("19/1/2026", "1", "BROCA DE 1/8", "5.50", "JHONATAN AMAZONIA"),
    ("19/1/2026", "30", "METROS DE CABLE DE #14", "5.00", "JHONATAN AMAZONIA"),
    ("19/1/2026", "3", "TERMOENCOGIBLE", "2.50", "JHONATAN AMAZONIA"),
    ("20/1/2026", "2000", "TORNILLOS DE 1\"X 6", "30", "SARGENTO ROA"),
    ("26/1/2026", "50", "SOPORTES BLANCOS", "70", "ESCRITORIO GENERAL"),
    ("26/1/2026", "500", "TORNILLOS DE 5/8 X 8", "35", "JHONATAN AMAZONIA"),
    ("31/1/2026", "45", "METROS DE CANTO ARENA", "800", "JHONATAN ZULEIKA"),
    ("31/1/2026", "1", "PU", "23.50", "JHONATAN ZULEIKA"),
    ("3/2/2026", "100", "TORNILLO DRIWALL 3X12", "240", "CAPITAN RAMIREZ"),
    ("3/2/2026", "1", "BOLSA DE CHAZO AZUL", "10.00", "CAPITAN RAMIREZ"),
    ("3/2/2026", "5", "ROLLOS DE LUZ BLANCA", "45.00", "ZULIKA Y AMAZONIA"),
    ("3/2/2026", "25", "METROS D CABLE #14", "5.00", "ZULIKA Y AMAZONIA"),
    ("3/2/2026", "2", "TERMOENCOGIBLE", "2.50", "ZULIKA Y AMAZONIA"),
    ("3/2/2026", "1", "ROLLO DE TEIPE", "4.00", "ZULIKA Y AMAZONIA"),
    ("6/2/2026", "35", "TOMA DOBLE GRIS", "9.20", "CASA SRA CAROLINA"),
    ("6/2/2026", "4", "APAGADORES DOBLES GRIS", "9.50", "CASA SRA CAROLINA"),
    ("6/2/2026", "13", "APAGADORES SENCILLOS GRIS", "9.00", "CASA SRA CAROLINA"),
    ("6/2/2026", "1", "APAGADORES TRIPLES GRIS", "13.00", "CASA SRA CAROLINA"),
    ("6/2/2026", "11", "TAPA LISA GRIS", "7.80", "CASA SRA CAROLINA"),
    ("7/2/2026", "25", "PLATINAS DORADA", "2.05", "MUEBLE DORA"),
    ("10/2/2026", "8", "GATOS 80", "4.50", "CLOSET CAP. RAMIREZ"),
    ("10/2/2026", "7", "TOMA DOBLE", "9.20", "CLOSET CAP. RAMIREZ"),
    ("16/2/2026", "8", "DILATADOR", "3.50", "JHONATAN ZULEIKA"),
    ("16/2/2026", "4", "TORNILLO 2\"*3/8", "1.20", "JHONATAN ZULEIKA"),
    ("16/2/2026", "4", "TORNILLO 1\" 1/2* 3/8", "1.00", "JHONATAN ZULEIKA"),
    ("16/2/2026", "8", "DESLIZADOR", "800", "JHONATAN ZULEIKA"),
    ("18/2/2026", "2", "TUBO 3/8 ALUMINIO", "13.00", "RECLAMO JHONATAN"),
    ("18/2/2026", "1", "LIJA#1200", "4.50", ""),
    ("21/2/2026", "3", "CHAPA ALCOBA CUADRADA", "63.00", "CASA JEFA"),
    ("21/2/2026", "1", "CHAPA BAÑO CUADRADA", "63.00", "CASA JEFA"),
    ("27/2/2026", "12", "CONECTORES", "4.00", "JHONATHAN"),
    ("3/3/2026", "5", "BROCHES DORADOS", "8.50", ""),
    ("4/3/2026", "1", "JUEGO DE BROCAS", "20.00", "FABRICA"),
    ("4/3/2026", "1", "PISTOLA DE CALEFATE TOTA", "38.00", "EVER VENDIDO"),
    ("9/3/2026", "3", "ROLLOS DE LUZ BLANCA", "45.00", "RECEPCION"),
    ("10/3/2026", "10", "CANCAMOS #6", "300", ""),
    ("11/3/2026", "5", "METROS DE PERFIL", "24.00", "CLOSET MIGUEL"),
    ("16/3/2026", "2", "SENSOR DE LUZ 110", "30.00", "DEPOSITO"),
    ("24/3/2026", "8", "BOTONES DIAMANTADOS", "4.50", "NOCHEROS"),
    ("24/3/2026", "4", "BOTONES ACERADOS", "3.50", "NOCHEROS"),
    ("24/3/2026", "4", "BOTON CHAPAN", "6.00", "NOCHEROS"),
    ("25/3/2026", "10", "BOTON DIAMANTADO", "4.50", "NOCHEROS"),
    ("28/3/2026", "10", "METROS DE CANTO BLANCO", "1.40", "ESCRITORIO YOSSI UZCATEGUI"),
    ("28/3/2026", "1", "ROLLO DE LUZ LED BLANCA", "45.00", "DEPOSITO"),
    ("1/4/2026", "1", "GRILLO", "8.00", "BAUL AMURANDAI"),
    ("7/4/2026", "10", "BOTON DE CRISTAL", "4.50", "NOCHEROS DEL SOL"),
    ("9/4/2026", "3", "PATA 7X2 AC", "8.50", "NOCHEROS DEL SOL"),
    ("11/4/2026", "200", "5/8 X 8", "35", "ISIDRO URIBE"),
    ("11/4/2026", "100", "1X6", "30", "ISIDRO URIBE"),
    ("11/4/2026", "100", "11/2X 2", "35", "ISIDRO URIBE"),
    ("11/4/2026", "100", "1X6", "30", "ISIDRO URIBE"),
    ("17/3/2026", "10", "PUSS TITO", "4.00", "ISIDRO"),
    ("20/4/2026", "1", "RIEL DE 2 METROS", "45.00", "JHONATAN MIGUEL"),
    ("20/4/2026", "1", "SISTEMA DE 2 PUERTAS", "16.00", "JHONATAN MIGUEL"),
    ("20/4/2026", "2", "MANIJA DE ALUMINIO", "6.00", "JHONATAN MIGUEL"),
    ("20/4/2026", "10", "CANTO GLAXIAL", "1.80", "JHONATAN MIGUEL"),
    ("20/4/2026", "1", "ADESIVO TAPA TORNILLO", "2.00", "JHONATAN MIGUEL"),
    ("21/4/2026", "10", "BOTONES DIAMANTADOS", "4.50", "NOCHEROS ANA APALESHAUCER"),
    ("25/4/2026", "6", "MANIJAS DORADAS", "12.00", "CEIBO EXIBICION"),
    ("25/4/2026", "5", "PATAS DE 5CM", "6.50", "PATAS CAMA HERRAJE"),
    ("5/5/2026", "5", "PARES DE CORREDERAS DE 30", "21.50", "PEINADORA MARYORI GOMEZ"),
    ("15/5/2026", "2", "BOTON ENVEJECIDO", "2.50", "NOCHEROS DEL SOL"),
    ("18/5/2026", "1", "GATO 600", "110.00", "DEPOSITO"),
    ("18/5/2026", "14", "JALADORES CUADRADOS", "4.00", "NOCHEROS DEL SOL"),
    ("18/5/2026", "18", "MANIJAS NEGRAS DE 95", "4.80", "NOCHEROS DEL SOL"),
    ("18/5/2026", "8", "MANIJAS BOTON NEGRO", "2.50", "NOCHEROS DEL SOL"),
    ("18/5/2026", "8", "PESADO BOTON", "3.50", "NOCHEROS DEL SOL"),
    ("20/5/2026", "1", "HERRAJE C14 (con la sima factura entro despues)", "25.00", "SOFA CAMA MARILIN SERRANO"),
    ("19/5/2026", "50", "TORNILLOS DE 40ML (entraron el 20/05)", "100", "NOCHEROS DEL SOL"),
    ("19/5/2026", "1", "GRILLO NEGRO", "9.00", "BAUL CAPITAN AMURADAI"),
    ("21/5/2026", "6", "MANIJAS NEGRAS DE 95", "5.80", "NOCHEROS DEL SOL"),
    ("22/5/2026", "4", "PARES DE GRILLO", "9.00", "DEPOSITO Y SAHARUN GALVIS"),
    ("28/5/2026", "4", "CHAPAS DE ALCOBA", "63.00", "PUERTAS MOISES ROJAS"),
    ("28/5/2026", "3", "CHAPA DE BAÑO CUADRADA", "63.00", "PUERTAS MOISES ROJAS"),
    ("2/6/2026", "1", "C-14", "25.00", "MODULAR TIPO SOFA KRISAURA ABREU"),
    ("2/6/2026", "14", "BOTON DE CRISTAL", "4.50", "FABRICA"),
    ("2/6/2026", "2", "CLIK-CLAK", "10.50", "MODULAR TIPO SOFA KRISAURA ABREU"),
    ("11/6/2026", "5", "MANIJAS 128", "5.80", "PUERTAS DE CLOSET MOISES"),
    ("11/6/2026", "5", "IMANES CAFÉ", "800", "PUERTAS DE CLOSET MOISES"),
    ("11/6/2026", "1", "C14", "25.00", "SOFA CAMA CRISAURA"),
    ("11/6/2026", "1", "CLIK CLIK", "10.50", "SOFA CAMA CRISAURA"),
    ("11/6/2026", "100", "TORNILLOS DE 1/2*8", "40", "FABRICA"),
    ("11/6/2026", "100", "1\"X6 DRIWALL", "30", "FABRICA"),
    ("12/6/2026", "4", "CANALETAS NEGRA", "22.00", "JHONATAN MIGUEL"),
    ("12/6/2026", "1", "SENSOR DE LUZ 110", "30.00", "JHONATAN MIGUEL"),
    ("12/6/2026", "1", "ROLLO DE LUZ CALIDA", "45.00", "JHONATAN MIGUEL"),
    ("12/6/2026", "15", "CONECTORES LED", "2.50", "JHONATAN MIGUEL"),
    ("12/6/2026", "2", "METROS DE TERMOENCOGIBLE", "3.00", "JHONATAN MIGUEL"),
    ("22/6/2026", "50", "METROS DE COLA RATA # 4", "700", "SILLAS ARUBA GLADIS"),
    ("25/6/2026", "5", "MANIJAS DE 128 PLATEADAS", "4.50", "ESCRITORIO LILIBETH"),
    ("26/6/2026", "4", "PARES DE CABECEROS", "26.00", "MODULAR IRLANDES EXIBICION"),
    ("26/6/2026", "200", "SOPORTES DE ENTREPAÑOS", "35", "MODULAR KRISAURA Y DEPOSITO"),
    ("29/6/2026", "1", "CHAPA DE ALCOBA CUADRADA", "63.00", "DEPOSITO"),
    ("3/7/2026", "2", "PERFILES DE 3MTS", "22.00", "ALVEIRO ESCRITORIO DANIEL MONTOYA"),
    ("3/7/2026", "1", "ROLLO DE LUZ NEUTRA", "45.00", "ALVEIRO ESCRITORIO DANIEL MONTOYA"),
    ("16/7/2026", "2", "MANIJA GRANDE", "7.00", "CAMA DE METRO DGCIN"),
    ("16/7/2026", "3", "MANIJA PEQUEÑA", "5.50", "CAMA DE METRO DGCIN"),
    ("16/7/2026", "1", "HERRAJE C14", "25.00", "CAMA DE METRO DGCIN"),
    ("16/7/2026", "1", "CLIK CLAK", "10.50", "SOFA SR CRISAURA"),
    ("16/7/2026", "30", "CANTO ROBLE MAYA 40MM", "1.80", "CAMA DE METRO DGCIN"),
    ("16/7/2026", "1", "KITS DE MTS M52", "65.00", "CAMA DE METRO DGCIN"),
    ("21/7/2026", "5", "MANIJAS DORADAS", "12.00", "DANIEL GOMEZ ESCRITORIO"),
    ("21/7/2026", "2", "JUEGOS DE CLIC CLAK", "10.50", "DEPOSITO"),
    ("23/7/2026", "1", "BOLSA DE TAPA TORNILLO DE MADERA", "18.00", "PUERTAS COMANDO DE ZONA"),
    ("25/7/2026", "1", "BOLSA DE 100 TORNILLOS D 1\"*6", "3.00", "COCINA LILIANA"),
    ("25/7/2026", "5", "JUEGO 50 M/BOD", "41.00", "COCINA LILIANA"),
    ("25/7/2026", "1", "OIL 750", "21.50", "COCINA LILIANA"),
    ("25/7/2026", "1", "RIEL M52 X 2ECO", "65.00", "COCINA LILIANA"),
    ("25/7/2026", "1", "BOLSA DE 50 SOPORTE ACRILICO", "3.50", "COCINA LILIANA"),
    ("25/7/2026", "6", "LARGO PISTILLO", "11.00", "COCINA LILIANA"),
    ("25/7/2026", "300", "5/8 * 8", "35", "COCINA LILIANA"),
    ("25/7/2026", "1", "PLATILLERA GOMA", "50.00", "COCINA LILIANA"),
    ("25/7/2026", "15", "MTS DE CANTO 44 GRAFO 1800", "1.80", "COCINA LILIANA"),
    ("25/7/2026", "200", "11/2 X 6 2M", "35", "COCINA LILIANA"),
    ("25/7/2026", "1", "ADESIVO TAPA TORNILLO GRAFO", "2.00", "COCINA LILIANA"),
    ("25/7/2026", "20", "ELE DE 1/2", "700", "COCINA LILIANA"),
    ("28/7/2026", "2", "CHAPAS DE ALCOBA", "63.00", "PUERTAS COMANDO DE ZONA"),
    ("28/7/2026", "1", "BOLSA DE 100 DESLISADORES BLANCOS DE PUNTILLA", "18.00", "ESCRITORIO DANIEL MONTOYA"),
    ("28/7/2026", "15", "CANTO ROVERE MAYA 19MM", "800", "MESA EXAGONAL MIGUEL IZAGUIRRE"),
    ("28/7/2026", "15", "MTS DE CANTO ROVERE MAYA", "1.80", "MESA EXAGONAL MIGUEL IZAGUIRRE"),
    ("30/7/2026", "1", "LITRO DE SUPER PEGA", "68.00", "PUERTAS COMANDO DE ZONA"),
    ("5/8/2026", "7", "METROS DE CANTO ROBLE RAYADO", "1.80", "MESA EXAGONAL MIGUEL IZAGUIRRE"),
    ("6/8/2026", "15", "METROS DE CANTO 19MM", "800", ""),
    ("12/8/2026", "50", "METROS DE CANTO DE 40MM AMARATO", "1.80", "DEPOSITO"),
    ("13/8/2026", "2", "HERRAJES C14", "25.00", "SOFA CAMA LILIBET VILLALOBOS"),
    ("13/8/2026", "1", "PAR DE CLIK CLAK", "10.50", "SOFA CAMA LILIBET VILLALOBOS"),
    ("25/8/2026", "1", "GRILLO (factura que pidió Antonio — la Jefa sabe)", "8.00", "ANTONIO"),
    ("27/8/2026", "2", "CAJAS DE PUNTILLAS SIN CABEZAS DE 1\"/8", "700", "UNA PARA JHONATAN Y OTRA PARA DEPOSITO"),
    ("28/8/2026", "6", "METROS DE CANTO BLANCO DE 19MM", "600", ""),
]

# Abonos de la hoja: (fecha, monto en COP). Se aplican FIFO a las deudas más viejas.
ABONOS: list[tuple[str, str]] = [
    ("16/2/2026", "1000000"),   # ABONO X TRASFERENCIA
    ("11/4/2026", "500000"),    # ABONO X TRASFERENCIA
    ("11/6/2026", "1000000"),   # ABONO EN EFECTIVO LLEVO KAROLAY
    ("12/6/2026", "1000000"),   # ABONO EN EFECTIVO LLEVO ANDRES
    ("25/8/2026", "1000000"),   # ABONO EN EFECTIVO
]

TOTAL_HOJA = Decimal("6712400")
ABONOS_HOJA = Decimal("4500000")
SALDO_HOJA = Decimal("2212400")


def parse_fecha(texto: str) -> date:
    from datetime import datetime
    # La hoja usa dd/mm/yyyy con barras dobles a veces ("11/04//2026").
    limpio = texto.strip().replace("//", "/")
    return datetime.strptime(limpio, "%d/%m/%Y").date()


def main():
    parser = argparse.ArgumentParser(description="Migra la hoja de control de SR CARMEN MANILLAS al ERP.")
    parser.add_argument("--ejecutar", action="store_true", help="Commitea los cambios (default: dry-run)")
    parser.add_argument("--db-url", type=str, default=None, help="DATABASE_URL alternativa (ej. producción Neon)")
    parser.add_argument("--x1000", action="store_true",
                        help="Multiplica los precios unitarios por 1000 (los totales de la hoja cuadran así)")
    parser.add_argument("--usuario-id", type=int, default=None, help="Usuario responsable (default: primer Dueño)")
    args = parser.parse_args()

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

    from app.db.session import session_local
    from app.modules.proveedores.model import Proveedor
    from app.modules.catalogos.model import TipoGasto, Moneda
    from app.modules.cuentas_por_pagar.model import CuentaPorPagar, DetalleCuentaPorPagar, PagoCuentaPorPagar

    db = session_local()
    try:
        print(f"BD: {db.bind.url.render_as_string(hide_password=True)}")
        print(f"Modo: {'EJECUTAR' if args.ejecutar else 'DRY-RUN (rollback)'}")
        print(f"Precios x1000: {'SÍ' if args.x1000 else 'no (tal cual la hoja)'}")
        print("-" * 90)

        # Proveedor
        prov = db.query(Proveedor).filter(Proveedor.nombre == PROVEEDOR_NOMBRE).first()
        if not prov:
            prov = Proveedor(nombre=PROVEEDOR_NOMBRE)
            db.add(prov)
            db.flush()
            print(f"[+] Proveedor creado: {PROVEEDOR_NOMBRE} #{prov.id}")
        else:
            print(f"[=] Proveedor ya existía: {PROVEEDOR_NOMBRE} #{prov.id}")

        # Usuario responsable (opcional; queda null en auditoría si no se indica).
        usuario_id = None
        if args.usuario_id:
            from app.modules.users.model import Usuario
            u = db.query(Usuario).filter(Usuario.id == args.usuario_id).first()
            usuario_id = u.id if u else None

        tipo_gasto = db.query(TipoGasto).filter(TipoGasto.nombre == "COMPRA DE INSUMOS").first()
        if not tipo_gasto:
            tipo_gasto = TipoGasto(nombre="COMPRA DE INSUMOS", categoria="OPERATIVO")
            db.add(tipo_gasto)
            db.flush()
        moneda_cop = db.query(Moneda).filter(Moneda.codigo == "COP").first()
        if not moneda_cop:
            raise SystemExit("No existe la moneda COP en la BD.")

        # Idempotencia: si ya existe una deuda marcada con el tag, no re-migrar.
        ya_migrado = db.query(CuentaPorPagar).filter(
            CuentaPorPagar.descripcion.like(f"%{TAG}%")
        ).first()
        if ya_migrado:
            print(f"✗ Ya migrado (deuda #{ya_migrado.id}). Abortando para no duplicar.")
            db.rollback()
            return 0

        # ── Construir deudas por fecha ──
        por_fecha: dict[date, list] = {}
        for fecha_s, cant_s, desc, precio_s, destino in RENGLONES:
            fecha = parse_fecha(fecha_s)
            cantidad = Decimal(cant_s)
            precio = Decimal(precio_s)
            if args.x1000:
                precio = precio * Decimal("1000")
            por_fecha.setdefault(fecha, []).append({
                "descripcion": desc,
                "cantidad": cantidad,
                "precio": precio,
                "destino": destino.strip() or None,
            })

        deudas = []
        total_calculado = Decimal("0.0")
        for fecha in sorted(por_fecha):
            renglones = por_fecha[fecha]
            monto = sum(r["cantidad"] * r["precio"] for r in renglones).quantize(Decimal("0.01"))
            total_calculado += monto
            desc = f"{TAG} · Compra de insumos {fecha.strftime('%d/%m/%Y')} · {len(renglones)} ítems"
            cxp = CuentaPorPagar(
                proveedor_id=prov.id,
                tipo_gasto_id=tipo_gasto.id,
                moneda_id=moneda_cop.id,
                fecha=fecha,
                descripcion=desc,
                monto=monto,
                tasa_cambio=Decimal("1.0"),
                monto_en_moneda_base=monto,
                estado="PENDIENTE",
                origen_tipo="MANUAL",
                creado_por_id=usuario_id,
            )
            db.add(cxp)
            db.flush()
            for i, r in enumerate(renglones):
                db.add(DetalleCuentaPorPagar(
                    cuenta_por_pagar_id=cxp.id,
                    orden=i,
                    descripcion=r["descripcion"],
                    cantidad=r["cantidad"],
                    precio_unitario=r["precio"],
                    cliente_nombre=r["destino"],
                ))
            deudas.append(cxp)
            print(f"  + {fecha.strftime('%d/%m/%Y')}: {len(renglones):>2} ítems · {monto:>12,.0f}")

        # ── Aplicar abonos FIFO ──
        total_abonado = Decimal("0.0")
        for fecha_s, monto_s in ABONOS:
            monto = Decimal(monto_s)
            restante = monto
            for cxp in deudas:
                if restante <= 0:
                    break
                saldo = cxp.saldo
                if saldo <= 0:
                    continue
                aplicar = min(restante, saldo)
                pago = PagoCuentaPorPagar(
                    cuenta_por_pagar_id=cxp.id,
                    fecha=parse_fecha(fecha_s),
                    metodo_caja_id=1,
                    monto=aplicar,
                    tasa_cambio=Decimal("1.0"),
                    monto_en_moneda_base=aplicar,
                )
                db.add(pago)
                cxp.monto_pagado = (Decimal(str(cxp.monto_pagado or 0)) + aplicar).quantize(Decimal("0.01"))
                if cxp.saldo <= Decimal("0.005"):
                    cxp.estado = "PAGADA"
                restante -= aplicar
                total_abonado += aplicar
            print(f"  · Abono {fecha_s}: {monto:>12,.0f} (quedó sin imputar: {restante:,.0f})")

        print("-" * 90)
        print(f"Total deudas: {total_calculado:>12,.0f}")
        print(f"Total abonado: {total_abonado:>12,.0f}")
        print(f"Saldo resultante: {total_calculado - total_abonado:>12,.0f}")
        print(f"(Hoja esperaba: total {TOTAL_HOJA:,} · abonos {ABONOS_HOJA:,} · saldo {SALDO_HOJA:,})")
        if not args.x1000:
            print("  ⚠ Sin --x1000 los totales NO cuadran con la hoja (mira el análisis de miles).")

        if args.ejecutar:
            db.commit()
            print("✓ MIGRACIÓN COMMITADA.")
        else:
            db.rollback()
            print("· Dry-run: nada escrito. Usa --ejecutar para aplicar.")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    main()