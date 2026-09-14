# -*- coding: utf-8 -*-
"""Carga el inventario físico de EBANISTERÍA (conteo Septiembre 2026) al ERP.

Crea (si no existen) las categorías de inventario, los materiales con
departamento=EBANISTERIA y el stock inicial en el Depósito Principal
(ubicacion_id=1), registrando un movimiento ENTRADA por cada material.

Idempotente: re-ejecutar no duplica ni pisa cantidades ya cargadas.

Uso:
    python scripts/importar_inventario_ebanisteria.py                # dry-run
    python scripts/importar_inventario_ebanisteria.py --ejecutar     # commit real
    python scripts/importar_inventario_ebanisteria.py --db-url postgresql://...  # otra BD
"""
import argparse
import os
import sys
from decimal import Decimal

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__) + "/.."))

from datetime import datetime

from app.modules.catalogos.model import CategoriaInventario, UnidadMedida
from app.modules.inventory.model import Inventario, MovimientoInventario
from app.modules.productos.model import Material

DEPARTAMENTO = "EBANISTERIA"
UBICACION_ID = 1  # Depósito Principal
COSTO_BASE = Decimal("0.00")

# ── Categorías de inventario (desglose de la UI) ────────────────────────────
CATEGORIAS = [
    "TABLEROS Y MATERIALES",
    "GRAPAS",
    "HERRAJES Y ACCESORIOS",
    "CONSUMIBLES Y HERRAMIENTAS",
    "TORNILLERIA",
]

# (categoría, nombre del material, unidad, cantidad)
# Unidad: "LAMINA" | "TIRAS" | "PAR" | "UD"
DATA: list[tuple[str, str, str, str]] = [
    # ── Tableros y Materiales ──
    ("TABLEROS Y MATERIALES", "Melamina Tula 25 mm", "LAMINA", "1"),
    ("TABLEROS Y MATERIALES", "Melamina Tula 5.5 mm", "LAMINA", "7"),
    ("TABLEROS Y MATERIALES", "Melamina Flor Morado 15 mm", "LAMINA", "1"),
    ("TABLEROS Y MATERIALES", "Melamina Flor Morado", "LAMINA", "1"),
    ("TABLEROS Y MATERIALES", "Melamina Guengue 15 H.M.", "LAMINA", "4"),
    ("TABLEROS Y MATERIALES", "Melamina Gala 15 H.M.", "LAMINA", "1"),
    ("TABLEROS Y MATERIALES", "P.U", "LAMINA", "2"),
    ("TABLEROS Y MATERIALES", "H.D.F 2.5 mm", "LAMINA", "46"),
    ("TABLEROS Y MATERIALES", "H.D.F 5.5 mm", "LAMINA", "24"),
    ("TABLEROS Y MATERIALES", "H.D.F 9 mm", "LAMINA", "8"),
    ("TABLEROS Y MATERIALES", "H.D.F 15 mm", "LAMINA", "1"),
    # ── Grapas (cantidad en TIRAS; cada caja = 50 tiras) ──
    ("GRAPAS", "Grapas F 20", "TIRAS", "27"),
    ("GRAPAS", "Grapas F 25", "TIRAS", "68"),
    ("GRAPAS", "Grapas F 30", "TIRAS", "175"),
    ("GRAPAS", "Grapas F 40", "TIRAS", "256"),
    ("GRAPAS", "Grapas F 50", "TIRAS", "194"),
    ("GRAPAS", "Grapas F 75", "TIRAS", "135"),
    # ── Herrajes y Accesorios ──
    ("HERRAJES Y ACCESORIOS", "Ganchos de cama 18 cm", "UD", "11"),
    ("HERRAJES Y ACCESORIOS", "Ganchos de cama 11 cm", "UD", "8"),
    ("HERRAJES Y ACCESORIOS", "Correderas 30 Normal", "PAR", "3"),
    ("HERRAJES Y ACCESORIOS", "Correderas 35 Normal", "PAR", "27"),
    ("HERRAJES Y ACCESORIOS", "Correderas 35 Push", "PAR", "24"),
    ("HERRAJES Y ACCESORIOS", "Correderas 45 Normal", "PAR", "2"),
    ("HERRAJES Y ACCESORIOS", "Correderas 45 Push", "PAR", "6"),
    ("HERRAJES Y ACCESORIOS", "Correderas 50 Normal", "PAR", "4"),
    ("HERRAJES Y ACCESORIOS", "Correderas Montaje Bajo", "PAR", "6"),
    ("HERRAJES Y ACCESORIOS", "Topes de puertas", "UD", "14"),
    ("HERRAJES Y ACCESORIOS", "Kit de pie de amigo plegable", "UD", "1"),
    ("HERRAJES Y ACCESORIOS", "Tubitos de aluminio", "UD", "8"),
    ("HERRAJES Y ACCESORIOS", "Rodachines giratorios", "UD", "9"),
    ("HERRAJES Y ACCESORIOS", "Bisagras de cazoleta semicurva", "UD", "25"),
    ("HERRAJES Y ACCESORIOS", "Bisagras de cazoleta curva", "UD", "19"),
    ("HERRAJES Y ACCESORIOS", "Bisagras semiplanas cierre lento", "UD", "6"),
    ("HERRAJES Y ACCESORIOS", "Bisagras planas cierre lento", "UD", "8"),
    ("HERRAJES Y ACCESORIOS", "Bisagras planas", "UD", "13"),
    ("HERRAJES Y ACCESORIOS", "Bisagras cierre lento normal", "UD", "0"),
    ("HERRAJES Y ACCESORIOS", "Gatos de cocina", "PAR", "1"),
    ("HERRAJES Y ACCESORIOS", "Gatos pequeños", "UD", "14"),
    # ── Consumibles y Herramientas ──
    ("CONSUMIBLES Y HERRAMIENTAS", "Brocas", "UD", "4"),
    ("CONSUMIBLES Y HERRAMIENTAS", "Fresas", "UD", "30"),
    ("CONSUMIBLES Y HERRAMIENTAS", "Manijas", "UD", "0"),
    ("CONSUMIBLES Y HERRAMIENTAS", "Super / Super PL", "UD", "0"),
    ("CONSUMIBLES Y HERRAMIENTAS", "Punta Estría", "UD", "0"),
    # ── Tornillería ──
    ("TORNILLERIA", "Tornillos de 1\"", "UD", "1900"),
    ("TORNILLERIA", "Tornillos de 1\" ½", "UD", "5000"),
    ("TORNILLERIA", "Tornillos de 2\"", "UD", "1400"),
    ("TORNILLERIA", "Tornillos de 2\" ½", "UD", "500"),
    ("TORNILLERIA", "Tornillos de 3\"", "UD", "800"),
    ("TORNILLERIA", "Tornillos Avellanado 1\" ½", "UD", "100"),
    ("TORNILLERIA", "Tornillos Drywall 1\" ¼", "UD", "100"),
    ("TORNILLERIA", "Tornillos Drywall 2\" ½", "UD", "200"),
]

NORM = {
    "LAMINA": ("Lámina", "Lam"),
    "TIRAS": ("TIRAS", "TIRAS"),
    "PAR": ("PAR", "PAR"),
    "UD": ("Unidad", "Ud"),
}


def _unidad(db, clave: str) -> UnidadMedida:
    nombre, abrev = NORM[clave]
    u = db.query(UnidadMedida).filter(UnidadMedida.nombre == nombre).first()
    if not u:
        u = UnidadMedida(nombre=nombre, abreviatura=abrev)
        db.add(u)
        db.flush()
    return u


def _categoria(db, nombre: str) -> CategoriaInventario:
    cat = db.query(CategoriaInventario).filter(
        CategoriaInventario.nombre == nombre, CategoriaInventario.tipo == "MATERIAL"
    ).first()
    if not cat:
        cat = CategoriaInventario(nombre=nombre, tipo="MATERIAL", orden=0)
        db.add(cat)
        db.flush()
    return cat


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

    from app.db.session import session_local

    db = session_local()
    try:
        print(f"BD: {db.bind.url.render_as_string(hide_password=True)}")
        print(f"Modo: {'EJECUTAR' if args.ejecutar else 'DRY-RUN (rollback)'}")
        print("-" * 80)

        unidades = {c: _unidad(db, c) for c in NORM}
        categorias = {nombre: _categoria(db, nombre) for nombre in CATEGORIAS}

        creados = 0
        con_stock = 0
        ya_existentes = 0
        for categoria, nombre, clave_unidad, cantidad in DATA:
            cat = categorias[categoria]
            unidad = unidades[clave_unidad]
            cantidad_dec = Decimal(cantidad)

            mat = db.query(Material).filter(Material.nombre == nombre).first()
            if not mat:
                mat = Material(
                    nombre=nombre,
                    unidad_medida_id=unidad.id,
                    costo_base=COSTO_BASE,
                    stock_minimo=Decimal("8"),
                    activo=True,
                    categoria_inventario_id=cat.id,
                    departamento=DEPARTAMENTO,
                )
                db.add(mat)
                db.flush()
                creados += 1
            else:
                # Actualizar metadatos si el material ya existía (ej. re-import)
                mat.categoria_inventario_id = cat.id
                mat.departamento = DEPARTAMENTO
                ya_existentes += 1

            inv = db.query(Inventario).filter(
                Inventario.material_id == mat.id,
                Inventario.ubicacion_id == UBICACION_ID,
            ).first()
            if inv is None:
                inv = Inventario(
                    material_id=mat.id,
                    ubicacion_id=UBICACION_ID,
                    cantidad=Decimal("0"),
                )
                db.add(inv)
                db.flush()

            if cantidad_dec > 0 and inv.cantidad == 0:
                inv.cantidad = cantidad_dec
                db.add(MovimientoInventario(
                    material_id=mat.id,
                    ubicacion_id=UBICACION_ID,
                    tipo="ENTRADA",
                    cantidad=cantidad_dec,
                    costo_unitario=COSTO_BASE,
                    referencia_tipo="inventario_inicial",
                    observaciones="Inventario inicial Ebanistería (conteo físico septiembre 2026)",
                    fecha=datetime.utcnow(),
                ))
                con_stock += 1

            print(f"  {'+' if inv.cantidad > 0 else '·'} {nombre:<42} x{cantidad:<6} [{clave_unidad}] → {cat.nombre}")

        print("-" * 80)
        print(f"Materiales creados: {creados}  ·  ya existentes: {ya_existentes}  ·  con stock cargado: {con_stock}")

        if args.ejecutar:
            db.commit()
            print("✓ MIGRACIÓN COMMITADA.")
        else:
            db.rollback()
            print("· Dry-run: nada escrito. Usa --ejecutar para aplicar.")
        return 0
    finally:
        db.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Carga el inventario físico de Ebanistería al ERP.")
    parser.add_argument("--ejecutar", action="store_true", help="Commitea los cambios (default: dry-run)")
    parser.add_argument("--db-url", type=str, default=None, help="DATABASE_URL alternativa (ej. producción Neon)")
    args = parser.parse_args()
    sys.exit(migrar(args))


if __name__ == "__main__":
    main()