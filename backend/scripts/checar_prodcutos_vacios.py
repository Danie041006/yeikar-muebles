import csv

BASE_DIR = "/home/daniel-castellanos/YEIKAR/docs/documentos_de_negocio/yeikar_costos_csv_v1"

def cargar_mapeo(csv_path, col_id, col_nombre):
    mapeo = {}
    with open(csv_path, newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            old_id = row.get(col_id, '').strip()
            nombre = row.get(col_nombre, '').strip()
            if old_id and nombre:
                mapeo[old_id] = nombre
    return mapeo

prod_map = cargar_mapeo(f"{BASE_DIR}/producto.csv", 'product_id', 'nombre')
mat_map = cargar_mapeo(f"{BASE_DIR}/material.csv", 'id', 'nombre')

faltantes_producto = set()
faltantes_material = set()
total = 0
with open(f"{BASE_DIR}/producto_material.csv", newline='', encoding='utf-8') as f:
    reader = csv.DictReader(f)
    for row in reader:
        total += 1
        pid = row['producto_id'].strip()
        mid = row['material_id'].strip()
        if pid not in prod_map:
            faltantes_producto.add(pid)
        if mid not in mat_map:
            faltantes_material.add(mid)

print(f"Total filas: {total}")
print(f"IDs de producto faltantes en producto.csv: {len(faltantes_producto)}")
print(sorted(faltantes_producto))
print(f"IDs de material faltantes en material.csv: {len(faltantes_material)}")
print(sorted(faltantes_material))