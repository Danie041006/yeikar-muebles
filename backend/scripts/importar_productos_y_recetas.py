#!/usr/bin/env python3
"""
Importa recetas (producto_material) desde producto_material_con_nombres.csv.
Filtra cantidades_base <= 0 y tipos_escala no permitidos.
"""
import csv
import sys
import os
from decimal import Decimal

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.session import session_local
from app.modules.productos.model import Producto, Material, ProductoMaterial

db = session_local()

BASE_DIR = "/home/daniel-castellanos/YEIKAR/docs/documentos_de_negocio/yeikar_costos_csv_v1"
CSV_RECETAS = os.path.join(BASE_DIR, "producto_material_con_nombres.csv")

# Tipos de escala permitidos en la base de datos
TIPOS_PERMITIDOS = {'FIJO', 'LINEAL', 'AREA', 'ESPACIADO'}

def mapear_tipo_escala(tipo):
    """Convierte tipos no estándar a uno permitido, o devuelve None si no se puede mapear."""
    if tipo in TIPOS_PERMITIDOS:
        return tipo
    # Mapeos
    if tipo in ('FORMULA', 'VOLUMEN'):
        return 'LINEAL'  # o 'AREA', según tu lógica
    # Si no se puede mapear, devolvemos None para saltar la fila
    return None

def importar_recetas():
    print(" Leyendo recetas desde:", CSV_RECETAS)
    total_leidas = 0
    insertadas = 0
    saltadas_cero = 0
    saltadas_tipo = 0
    errores_no_encontrados = 0
    duplicados = 0

    with open(CSV_RECETAS, newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            total_leidas += 1
            
            pname = row['nombre_producto'].strip()
            mname = row['nombre_material'].strip()
            cantidad_str = row.get('cantidad_base', '0').strip()
            if not cantidad_str:
                cantidad_str = '0'
            
            try:
                cantidad = Decimal(cantidad_str)
            except:
                cantidad = Decimal('0')
            
            # Filtrar cantidad <= 0
            if cantidad <= 0:
                saltadas_cero += 1
                continue
            
            # Filtrar tipo_escala no válido
            tipo_original = row.get('tipo_escala', 'LINEAL').strip().upper()
            tipo_final = mapear_tipo_escala(tipo_original)
            if tipo_final is None:
                print(f" Tipo de escala no válido o no mapeable: '{tipo_original}' para {pname} - {mname}")
                saltadas_tipo += 1
                continue
            
            # Buscar producto y material por nombre
            prod = db.query(Producto).filter(Producto.nombre == pname).first()
            mat = db.query(Material).filter(Material.nombre == mname).first()
            if not prod or not mat:
                print(f" No encontrado: producto '{pname}' o material '{mname}'")
                errores_no_encontrados += 1
                continue
            
            # Evitar duplicados
            existente = db.query(ProductoMaterial).filter(
                ProductoMaterial.producto_id == prod.id,
                ProductoMaterial.material_id == mat.id
            ).first()
            if existente:
                duplicados += 1
                continue
            
            # Crear la receta
            pm = ProductoMaterial(
                producto_id=prod.id,
                material_id=mat.id,
                cantidad_base=cantidad,
                tipo_escala=tipo_final,
                distancia_pauta_cm=Decimal(row['distancia_pauta_cm']) if row.get('distancia_pauta_cm') else None,
                tornillos_por_pieza=int(row['tornillos_por_pieza']) if row.get('tornillos_por_pieza') else None,
                condicion_activacion=row.get('condicion_activacion') or None,
                rangos=row.get('rangos') or None,
                formula_personalizada=row.get('formula_personalizada') or None,
                observaciones=row.get('observaciones') or None
            )
            db.add(pm)
            insertadas += 1
            
            if insertadas % 500 == 0:
                db.commit()
                print(f"   Insertadas {insertadas} recetas...")
    
    db.commit()
    print("\n Resumen final:")
    print(f"   Total líneas leídas: {total_leidas}")
    print(f"    Recetas insertadas: {insertadas}")
    print(f"   ⏩ Saltadas por cantidad <= 0: {saltadas_cero}")
    print(f"   ⏩ Saltadas por tipo_escala inválido: {saltadas_tipo}")
    print(f"    Producto o material no encontrado: {errores_no_encontrados}")
    print(f"    Duplicadas omitidas: {duplicados}")

if __name__ == "__main__":
    importar_recetas()
    db.close()
    print(" Proceso completado.")