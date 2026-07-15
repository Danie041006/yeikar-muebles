YEIKAR CSV exports generated from CAMAS CON SUS MESAS DE NOCHE(3).xlsx

Files:
- tipo_producto.csv
- unidad_medida.csv
- material.csv
- producto.csv
- producto_material.csv
- line_items_raw.csv
- sheet_summary.csv

Suggested import order:
1) tipo_producto
2) unidad_medida
3) material
4) producto
5) producto_material

Notes:
- producto.csv includes sheet-level summary values when they were present in the workbook.
- material.csv uses median unit price per normalized material name as costo_base.
- line_items_raw.csv preserves the original worksheet rows for manual review.
- Some rows in the source workbook contain descriptive quantities instead of pure numbers; those were preserved in formula_personalizada / observaciones.

Filtered out sheets with zero extracted line items.
