import os
import sys

# Añadir el path para importar app
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.db.session import session_local
from app.modules.productos.model import Material, MaterialSinonimo

def main():
    db = session_local()
    try:
        # Definir los mapeos de sinónimos canónicos
        # Nombre Canónico -> Lista de Sinónimos
        mappings = {
            "MDF DE 9": [
                "LAM MDF 9", "LAMINA DE 9", "LAM MFF 9\"", "lamina de 9 mdf", "lamina de 9mdf", "LAMINA DE 9\""
            ],
            "MDF DE 15": [
                "LAMINA DE 15", "LAM MDF 15", "LAM MDF 15\"", "LAMINA DE 15\"", "MDF 15", "MDF DE 15\"", "MDF DE 15"
            ],
            "MDF DE 3": [
                "MDF DE 3\"", "MDF 3"
            ],
            "MDF DE 2.7": [
                "MDF 2,7", "MDF DE 2,7", "MDF DE 2,7\"", "LAM MDF 2,7", "LAM MDF 2,7\"", "LAM MDF 2.7", "LAMINA DE 2,7", "LAMINA DE 2,7\"", "LAMINA DE 2.5\"", "LAM MDF 2.5", "MDF DE 2,5\"", "lamina de 2.5 mdf", "MDF DE 2.7"
            ],
            "LAMINA DE 5.5": [
                "LAMINA DE 5.5\"", "LAMINA DE 5,5", "LAMINA DE 5,5\"", "LAM MDF 5,5\"", "LAM MDF 5", "LAMINA DE 5.5"
            ],
            "COLBON": [
                "COLBON", "PEGANTE COLBON"
            ],
            "GRAPAS": [
                "GRAPAS", "GRAPA"
            ],
            "TORNILLOS DE 2\"": [
                "TORNILLOS DE 2\"", "TORNILLO DE 2\"", "TORNILLOS 2\""
            ],
            "SELLADOR": [
                "SELLADOR DE MADERA", "SELLADOR LACA"
            ]
        }

        # Limpiar tabla primero
        db.query(MaterialSinonimo).delete()
        db.commit()

        count = 0
        for canonical_name, synonyms in mappings.items():
            # Buscar el material canónico
            canonical_material = db.query(Material).filter(Material.nombre.ilike(canonical_name)).first()
            if not canonical_material:
                print(f"⚠️ No se encontró el material canónico '{canonical_name}' en la base de datos.")
                continue
            
            # Insertar los sinónimos
            for synonym in synonyms:
                # Evitar duplicados exactos del nombre canónico si ya está como sinónimo
                if synonym.strip().upper() == canonical_material.nombre.strip().upper():
                    # No necesitamos registrar el nombre canónico exacto como sinónimo del mismo
                    continue

                # Verificar si ya existe el sinónimo
                existing = db.query(MaterialSinonimo).filter(MaterialSinonimo.sinonimo.ilike(synonym)).first()
                if existing:
                    continue

                new_sin = MaterialSinonimo(
                    material_id=canonical_material.id,
                    sinonimo=synonym
                )
                db.add(new_sin)
                count += 1
                
        db.commit()
        print(f"Normalización completada. Se guardaron {count} sinónimos de materiales.")
    except Exception as e:
        db.rollback()
        print(f"Error durante la importación: {e}")
    finally:
        db.close()

if __name__ == '__main__':
    main()
