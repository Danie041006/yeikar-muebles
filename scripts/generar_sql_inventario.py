"""Genera el SQL (CTEs) para importar el inventario real a PRODUCCIÓN (Neon).

Emite 4 statements en orden: materiales+inventario, movimientos de materiales,
productos reventa+producto_inventario, movimientos de productos. Se ejecutan
con el MCP de Neon en una transacción.
"""
from decimal import Decimal

from importar_inventario_real import (
    PINTURAS, TAPICERIA, COLCHONES,
    parse_filas, costo_insumo, costo_reventa,
)


def values_materiales(depto, bloque):
    filas = parse_filas(bloque)
    vals = []
    for nombre, compra, pasada, total, existencia in filas:
        costo = costo_insumo(compra, pasada, total)
        vals.append(f"('{nombre}', {costo}, {existencia}, '{depto}')")
    return ",\n    ".join(vals)


def values_colchones():
    vals = []
    for nombre, compra, pasada, total, existencia in parse_filas(COLCHONES):
        costo = costo_reventa(compra, pasada, total)
        costo_sql = "NULL" if costo is None else str(costo)
        vals.append(f"('{nombre}', {costo_sql}, {existencia})")
    return ",\n    ".join(vals)


def valores_materiales_completos():
    """TODOS los materiales (nombre, costo, cant, depto): el material y su fila
    de inventario se crean aunque la existencia sea 0 (el insumo existe)."""
    vals = []
    for depto, bloque in (("PINTURA", PINTURAS), ("TAPICERIA", TAPICERIA)):
        for nombre, compra, pasada, total, existencia in parse_filas(bloque):
            costo = costo_insumo(compra, pasada, total)
            vals.append(f"('{nombre}', {costo}, {existencia}, '{depto}')")
    return ",\n    ".join(vals)


def valores_materiales_para_movimientos():
    """Solo materiales con existencia > 0 (el movimiento ENTRADA exige > 0)."""
    vals = []
    for depto, bloque in (("PINTURA", PINTURAS), ("TAPICERIA", TAPICERIA)):
        for nombre, compra, pasada, total, existencia in parse_filas(bloque):
            if existencia <= 0:
                continue
            costo = costo_insumo(compra, pasada, total)
            vals.append(f"('{nombre}', {costo}, {existencia}, '{depto}')")
    return ",\n    ".join(vals)


M = valores_materiales_completos()
MV = valores_materiales_para_movimientos()

sql_materiales_inv = f"""WITH datos AS (
  SELECT * FROM (VALUES
    {M}
  ) AS v(nombre, costo, cant, depto)
), mats AS (
  INSERT INTO material (nombre, unidad_medida_id, costo_base, stock_minimo, activo, departamento)
  SELECT nombre, 1, costo, 8, true, depto FROM datos
  RETURNING id, nombre, departamento
)
INSERT INTO inventario (material_id, ubicacion_id, cantidad)
SELECT m.id, 1, d.cant FROM mats m JOIN datos d ON d.nombre = m.nombre AND d.depto = m.departamento;"""

sql_movimientos_materiales = f"""INSERT INTO movimiento_inventario
(material_id, ubicacion_id, tipo, cantidad, costo_unitario, fecha, referencia_tipo, observaciones)
SELECT m.id, 1, 'ENTRADA', d.cant, d.costo, now(), 'CARGA_INICIAL', 'Carga inicial de inventario (Excel)'
FROM (VALUES
  {MV}
) AS d(nombre, costo, cant, depto)
JOIN material m ON m.nombre = d.nombre AND m.departamento = d.depto;"""

C = values_colchones()

sql_productos_inv = f"""WITH datos AS (
  SELECT * FROM (VALUES
    {C}
  ) AS v(nombre, costo, cant)
), prods AS (
  INSERT INTO producto (nombre, tipo_producto_id, descripcion, activo, stock_minimo, es_reventa, moneda_id, precio_costo_base)
  SELECT nombre, 2, 'Colchón de reventa (carga inicial)', true, 0, true, 2, costo FROM datos
  RETURNING id, nombre
)
INSERT INTO producto_inventario (producto_id, ubicacion_id, cantidad, costo_promedio)
SELECT p.id, 1, d.cant, d.costo FROM prods p JOIN datos d ON d.nombre = p.nombre;"""

sql_movimientos_productos = f"""INSERT INTO movimiento_producto_inventario
(producto_id, ubicacion_id, tipo, cantidad, costo_unitario, fecha, referencia_tipo, observaciones)
SELECT p.id, 1, 'ENTRADA', d.cant, d.costo, now(), 'CARGA_INICIAL', 'Carga inicial de inventario (Excel)'
FROM (VALUES
  {C}
) AS d(nombre, costo, cant)
JOIN producto p ON p.nombre = d.nombre;"""


def guardar(nombre, contenido):
    ruta = f"/home/daniel-castellanos/YEIKAR/scripts/sql_{nombre}.sql"
    with open(ruta, "w") as f:
        f.write(contenido)
    print(f"{nombre}: {len(contenido)} bytes → {ruta}")


guardar("materiales", sql_materiales_inv)
guardar("movimientos_materiales", sql_movimientos_materiales)
guardar("productos", sql_productos_inv)
guardar("movimientos_productos", sql_movimientos_productos)