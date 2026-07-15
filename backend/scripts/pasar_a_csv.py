import csv

BASE = "/home/daniel-castellanos/YEIKAR/docs/documentos_de_negocio/yeikar_costos_csv_v1"

# Mapeo de productos
prod_nombre = {}
with open(f"{BASE}/producto.csv", newline='', encoding='utf-8-sig') as f:
    reader = csv.DictReader(f)
    for row in reader:
        pid = row['product_id'].strip()
        nombre = row['nombre'].strip()
        if pid:
            prod_nombre[pid] = nombre
    print(f"Productos mapeados: {len(prod_nombre)}")

# Mapeo de materiales
mat_nombre = {}
with open(f"{BASE}/material.csv", newline='', encoding='utf-8-sig') as f:
    reader = csv.DictReader(f)
    for row in reader:
        mid = row['id'].strip()
        nombre = row['nombre'].strip()
        if mid:
            mat_nombre[mid] = nombre
    print(f"Materiales mapeados: {len(mat_nombre)}")

# Generar CSV con nombres
output_path = f"{BASE}/producto_material_con_nombres.csv"
with open(f"{BASE}/producto_material.csv", newline='', encoding='utf-8-sig') as infile, \
     open(output_path, 'w', newline='', encoding='utf-8') as outfile:
    reader = csv.DictReader(infile)
    writer = csv.DictWriter(outfile, fieldnames=['nombre_producto', 'nombre_material', 'cantidad_base', 'tipo_escala', 
                                                 'distancia_pauta_cm', 'tornillos_por_pieza', 'condicion_activacion', 
                                                 'rangos', 'formula_personalizada', 'observaciones'])
    writer.writeheader()
    count = 0
    for row in reader:
        pid = row['producto_id'].strip()
        mid = row['material_id'].strip()
        pname = prod_nombre.get(pid)
        mname = mat_nombre.get(mid)
        if pname and mname:
            writer.writerow({
                'nombre_producto': pname,
                'nombre_material': mname,
                'cantidad_base': row.get('cantidad_base', ''),
                'tipo_escala': row.get('tipo_escala', 'LINEAL'),
                'distancia_pauta_cm': row.get('distancia_pauta_cm', ''),
                'tornillos_por_pieza': row.get('tornillos_por_pieza', ''),
                'condicion_activacion': row.get('condicion_activacion', ''),
                'rangos': row.get('rangos', ''),
                'formula_personalizada': row.get('formula_personalizada', ''),
                'observaciones': row.get('observaciones', '')
            })
            count += 1
        else:
            print(f"Fila omitida: producto_id={pid} (existe? {pid in prod_nombre}), material_id={mid} (existe? {mid in mat_nombre})")
    print(f"✅ Archivo generado: {output_path}")
    print(f"   Filas escritas: {count} de {reader.line_num - 1} totales")