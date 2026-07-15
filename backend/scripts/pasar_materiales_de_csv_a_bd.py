#!/usr/bin/env python3
import csv
import sys
import os
from decimal import Decimal
from sqlalchemy import text   # <-- Importa text

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.session import session_local
from app.modules.productos.model import Material, UnidadMedida

db = session_local()
csv_path = "/home/daniel-castellanos/YEIKAR/docs/documentos_de_negocio/yeikar_costos_csv_v1/material.csv"
from sqlalchemy import text

def limpiar_tabla_material():
    """Elimina todos los registros de material y reinicia la secuencia manualmente"""
    print("🗑️ Limpiando tabla material...")

    # 1. Eliminar todos los registros
    db.execute(text("DELETE FROM material;"))

    # 2. Reiniciar el contador de la secuencia (equivale a RESTART IDENTITY)
    db.execute(text("ALTER SEQUENCE material_id_seq RESTART WITH 1;"))

    db.commit()
    print("✅ Tabla material limpiada y secuencia reiniciada.")

def normalizar_nombre_unidad(nombre):
    """Convierte nombres de unidad a un formato estándar para búsqueda"""
    if not nombre:
        return None
    nombre = nombre.upper().stripd()
    # Mapeo de nombres comunes a su versión en la BD
    mapeo = {
        "LITRO": "LITRO",
        "LITROS": "LITRO",
        "METRO": "METROS",
        "METROS": "METROS",
        "M": "METROS",
        "CM": "CMS",
        "CMS": "CMS",
        "KG": "KG",
        "KILO": "KILO",
        "KILOS": "KILO",
        "UNIDAD": "UNIDAD",
        "UNIDADES": "UNIDAD",
        "PAR": "PAR",
        "PARES": "PARES",
        "CAJA": "CAJA",
        "CAJAS": "CAJA",
        "TIRA": "TIRA",
        "TIRAS": "TIRAS",
        "ROLLO": "ROLLO",
        "ROLLOS": "ROLLO",
        "PISTOLADA": "PISTOLADA",
        "PISTOLADAS": "PISTOLADAS",
        "GALON": "GALON",
        "GALONES": "GALON",
        "LAMINA": "LAMINA",
        "LAMINAS": "LAMINA",
        "JUEGO DE 4": "JUEGO DE 4",
        "DE 2X2": "DE 2X2",
        "* UNIDADES": "UNIDAD",
        "* LITRO": "LITRO",
        "*5%": "PORCENTAJE",
        "* 5%": "PORCENTAJE",
        "CON EL 5%": "PORCENTAJE",
        "16.0": "PORCENTAJE",
        "0.05": "PORCENTAJE",
        "JALADORES": "JALADORES",
        "JALADOR": "JALADORES",
        "MDF": "UNIDAD",
        "PATAS": "UNIDAD",
        "RETAL": "UNIDAD",
        "ROSADA": "UNIDAD",
        "AZUL": "UNIDAD",
        "DANIEL": "UNIDAD",
        "TATI": "UNIDAD",
        "PEOPLE": "UNIDAD",
        "LAMINA ( 55*56)": "LAMINA",
        "1 PEDAZO 90X120": "UNIDAD",
        "TIRASDE 51X1,21": "UNIDAD",
        "50*80": "UNIDAD",
        "2X7X5+1X7X5=105": "UNIDAD",
        "187 CENTIMETROS": "CMS",
        "MANO DE OBRA": "MANO_OBRA",
        "MANO DE OBRA=": "MANO_OBRA",
        "1 PEDASO DE 1.25 X55=68,75": "UNIDAD",
        "1 PEDAZO DE 2,7X 1,83": "UNIDAD",
        "1 PEDAZO DE 1.00X46=46": "UNIDAD",
        "1 PEDAZO DE 1,20X45=54": "UNIDAD",
        "2,10X22X18= 832 2,10X20X15=630": "UNIDAD",
        "3 PEASOS DE 49X49": "UNIDAD",
        "6 PEDASOS DE 49X49": "UNIDAD",
        "DE CIERRELENTO": "UNIDAD",
        "LUIS ALFONSO": "UNIDAD",
        "MULTIUSOS": "UNIDAD",
        "UNIDAD 0": "UNIDAD",
        "UNIDAD DE 6": "UNIDAD",
        "Unidad Bastidores": "UNIDAD",
        "APAMATE": "UNIDAD",
        "KILO": "KG",    # Unificar KILO a KG
        "KG": "KG",
        "MTS": "METROS",
        "METROS": "METROS",
        "TIRAS": "TIRAS",
        "CAJA": "CAJA",
        "JUEGO DE 4": "JUEGO_DE_4",
        "DE 2X2": "DE_2X2",
        "PORCENTAJE": "PORCENTAJE",  # Para servicios y porcentajes
        "MANO_OBRA": "MANO_OBRA",
        "UNIDAD": "UNIDAD",
    }
    return mapeo.get(nombre, "UNIDAD")  # Por defecto, UNIDAD

def obtener_unidad(nombre_raw):
    """Busca o crea la unidad de medida según el nombre normalizado"""
    if not nombre_raw:
        return None
    nombre_normalizado = normalizar_nombre_unidad(nombre_raw)
    unidad = db.query(UnidadMedida).filter(UnidadMedida.nombre == nombre_normalizado).first()
    if not unidad:
        # Intentar búsqueda exacta
        unidad = db.query(UnidadMedida).filter(UnidadMedida.nombre == nombre_raw).first()
    if not unidad:
        # Si aún no existe, crear una nueva unidad (solo si es necesario)
        # Pero para simplificar, asignamos la unidad 'UNIDAD'
        unidad = db.query(UnidadMedida).filter(UnidadMedida.nombre == "UNIDAD").first()
        if not unidad:
            # Crear UNIDAD si no existe
            unidad = UnidadMedida(nombre="UNIDAD", abreviatura="UN")
            db.add(unidad)
            db.flush()
            print(f"📌 Creada unidad por defecto: UNIDAD")
        print(f"⚠️ Unidad no encontrada para '{nombre_raw}', se asigna UNIDAD por defecto")
    return unidad

def importar_materiales():
    contador = 0
    with open(csv_path, newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            nombre = row['nombre'].strip()
            if not nombre:
                continue
            
            # Obtener unidad usando el campo 'unidad_referida'
            unidad_nombre_raw = row.get('unidad_referida', '').strip()
            unidad = obtener_unidad(unidad_nombre_raw)
            
            # Costo base
            costo_base_str = row.get('costo_base', '0').strip()
            costo_base = Decimal(costo_base_str) if costo_base_str else Decimal(0)
            
            # Activo (si no hay columna, por defecto True)
            activo = row.get('activo', 'True').lower() == 'true'
            
            material = Material(
                nombre=nombre,
                unidad_medida_id=unidad.id if unidad else None,
                costo_base=costo_base,
                activo=activo
            )
            db.add(material)
            contador += 1
            if contador % 50 == 0:
                print(f"   Procesados {contador} materiales...")
            # No imprimo cada material para no saturar, solo progreso
    
    db.commit()
    print(f"\n✅ Importación completada. {contador} materiales añadidos.")

if __name__ == "__main__":
    limpiar_tabla_material()
    importar_materiales()
    db.close()
    print("🎉 Listo")