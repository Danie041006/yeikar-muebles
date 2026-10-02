"""
importar_plasticos_manaplas.py
=============================
Carga los productos de las dos facturas de MANAPLAS en el rubro PLÁSTICOS:

  - Factura HOGAR:      descuento combinado 35% + 3% = 36.95% sobre el precio
                        de catálogo. El precio de venta es el de catálogo.
  - Factura DURARESINA: descuento por renglón; precio de venta = neto × 1.60
                        (60% de ganancia) redondeado, tal como la factura.

Por cada renglón CON precio crea el Producto (es_reventa=True, tipo y
categoría PLÁSTICOS, moneda USD) y registra una ENTRADA de inventario con el
costo neto de la factura (actualiza el costo promedio). No genera gasto ni
salida de caja: la compra al proveedor se registra aparte cuando se pague.

Los renglones SIN precio de la factura HOGAR (tapas incluidas en cestas y
pipotes) NO se cargan como productos: vienen dentro del artículo principal.

Idempotente por código: si el producto ya existe, no lo duplica ni vuelve a
meter stock (solo completa precios si le faltan).

Uso:  cd backend && source venv/bin/activate
      python scripts/importar_plasticos_manaplas.py
"""
import os
import sys
from decimal import Decimal

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app.main  # noqa: F401  (registra todos los mappers de SQLAlchemy)
from app.db.session import session_local
from app.modules.catalogos.model import CategoriaInventario, TipoProducto
from app.modules.productos.model import Producto
from app.modules.inventory import service as inv_service
from app.modules.inventory.schemas import MovimientoProductoCreate

UBICACION_DEPOSITO = 1
MONEDA_USD = 2
PROVEEDOR = "MANAPLAS"
NOMBRE_RUBRO = "PLÁSTICOS"

# (codigo, nombre, unidades, costo_neto_usd, precio_venta_usd, factura)
PRODUCTOS = [
    # ── Factura HOGAR (35% + 3%) ────────────────────────────────────────────
    ("042-3794-4", "CESTA ROPA RED. C/TAPA GALAXY", 6, "12.64", "20.04", "HOGAR"),
    ("042-3795-1", "CESTA ROPA RED. GALAXY PEQ. C/TAPA", 6, "8.76", "13.89", "HOGAR"),
    ("042-3795-2", "CESTA ROPA RED. GALAXY PEQ. C/TAPA", 6, "8.76", "13.89", "HOGAR"),
    ("087-9064-6", "ESTANTERIA MULTIORG. 4 NIVELES C/", 1, "57.75", "91.59", "HOGAR"),
    ("087-9065-6", "ESTANTERIA MULTIORG. 5 NIVELES C/", 1, "74.68", "118.45", "HOGAR"),
    ("124-0100-1", "GAVETERO MULT. SET-4 C/RUEDAS", 2, "50.60", "80.26", "HOGAR"),
    ("323-1083-4", "PAPELERA PEDAL RED. ELEG. C/BLANCO", 4, "10.71", "16.98", "HOGAR"),
    ("324-7213-0", "PIPOTE ELEG. P/BASURA 120 LTS", 4, "34.77", "55.15", "HOGAR"),
    ("324-7216-0", "PIPOTE ELEG. P/BASURA 170 LTS", 4, "45.86", "72.74", "HOGAR"),
    ("324-7217-0", "PIPOTE ELEGANCE 41 LITROS", 4, "14.60", "23.15", "HOGAR"),
    ("403-2360-0", "TINA PROFUNDA MEDIANA 48 LTS.", 6, "9.62", "15.26", "HOGAR"),
    ("404-0060-0", "TOBOS GALAXY 12 LTS", 12, "4.27", "6.77", "HOGAR"),
    ("404-6221-0", "TOBO 10 LITROS CON TAPA", 12, "6.68", "10.59", "HOGAR"),
    # ── Factura DURARESINA (neto × 1.60 = precio de venta) ─────────────────
    ("022-6815-1", "ESCALEBANCO 2 PELDAÑOS C/TACOS", 6, "8.46", "14.00", "DURARESINA"),
    ("027-6829-1", "BUTACA CONFORT C/TACOS C/AZUL", 6, "9.50", "15.00", "DURARESINA"),
    ("027-6831-6", "BUTACA BABY C/ROSADO INTENSO", 6, "3.85", "6.00", "DURARESINA"),
    ("250-9006-2", "MESA CUADRADA FESTIVAL C/AZUL 80", 1, "27.30", "44.00", "DURARESINA"),
    ("250-9006-3", "MESA CUADRADA FESTIVAL C/VERDE 80", 1, "27.30", "44.00", "DURARESINA"),
    ("250-9008-0", "MESA FAMILIAR C/BLANCO 138 X 83.5 CM", 1, "38.89", "62.00", "DURARESINA"),
    ("250-9008-2", "MESA FAMILIAR C/AZUL 138 X 83.5 C", 1, "38.89", "62.00", "DURARESINA"),
    ("250-9011-6", "MESA INFANTIL 50 X 55 C/ROSADO", 4, "9.23", "15.00", "DURARESINA"),
    ("380-6825-0", "SILLA ELEGANCE COLOR BLANCO", 6, "8.70", "14.00", "DURARESINA"),
    ("380-6825-1", "SILLA ELEGANCE COLOR AZUL", 6, "8.70", "14.00", "DURARESINA"),
    ("390-6839-1", "SILLON RELAX COLOR AZUL", 6, "27.00", "43.00", "DURARESINA"),
]


def main():
    db = session_local()
    creados = 0
    existentes = 0
    stock_total = Decimal("0")
    try:
        tipo = db.query(TipoProducto).filter(TipoProducto.nombre == NOMBRE_RUBRO).first()
        if not tipo:
            tipo = TipoProducto(nombre=NOMBRE_RUBRO)
            db.add(tipo)
            db.flush()
            print(f"[+] Tipo de producto '{NOMBRE_RUBRO}' creado (#{tipo.id})")
        categoria = db.query(CategoriaInventario).filter(
            CategoriaInventario.nombre == NOMBRE_RUBRO,
            CategoriaInventario.tipo == "PRODUCTO",
        ).first()
        if not categoria:
            categoria = CategoriaInventario(
                nombre=NOMBRE_RUBRO, tipo="PRODUCTO", orden=20, activo=True
            )
            db.add(categoria)
            db.flush()
            print(f"[+] Categoría de inventario '{NOMBRE_RUBRO}' creada (#{categoria.id})")
        db.commit()

        for codigo, nombre, unidades, costo, venta, factura in PRODUCTOS:
            costo_d = Decimal(costo)
            venta_d = Decimal(venta)
            producto = db.query(Producto).filter(Producto.codigo == codigo).first()
            if producto:
                existentes += 1
                if producto.precio_costo_base is None:
                    producto.precio_costo_base = costo_d
                if producto.precio_venta_base is None:
                    producto.precio_venta_base = venta_d
                print(f"[=] Ya existe #{producto.id} {codigo} {nombre}")
                continue

            producto = Producto(
                nombre=nombre,
                codigo=codigo,
                tipo_producto_id=tipo.id,
                descripcion="Producto de plástico",
                activo=True,
                stock_minimo=Decimal("8"),
                es_reventa=True,
                moneda_id=MONEDA_USD,
                categoria_inventario_id=categoria.id,
                precio_costo_base=costo_d,
                precio_venta_base=venta_d,
            )
            db.add(producto)
            db.flush()

            mov = MovimientoProductoCreate(
                producto_id=producto.id,
                ubicacion_id=UBICACION_DEPOSITO,
                tipo="ENTRADA",
                cantidad=Decimal(unidades),
                costo_unitario=costo_d,
                proveedor_nombre=PROVEEDOR,
                referencia_tipo="IMPORTACION MANAPLAS",
                observaciones=f"Carga inicial factura {factura} MANAPLAS ({codigo})",
            )
            inv_service.registrar_movimiento_producto(db, mov)
            db.commit()
            creados += 1
            stock_total += Decimal(unidades)
            print(f"[+] #{producto.id} {codigo} {nombre} — {unidades} uds a ${costo}")
    finally:
        db.close()

    print(f"\n[OK] Creados: {creados} · Ya existían: {existentes} · Unidades ingresadas: {stock_total}")
    print("[i] Las tapas sin precio de la factura HOGAR no se cargaron (vienen incluidas en cestas/pipotes).")


if __name__ == "__main__":
    main()
