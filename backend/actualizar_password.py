#!/usr/bin/env python3
"""
Actualiza las contraseñas de los usuarios existentes en la tabla 'usuario'
Reemplaza 'TEMP_HASH' por un hash bcrypt válido.
"""

import sys
import os

# Asegurar que podemos importar los módulos de la app
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.db.session import session_local
from app.modules.users.model import Usuario
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def update_password(username: str, new_plain_password: str):
    db = session_local()
    try:
        user = db.query(Usuario).filter(Usuario.nombre_usuario == username).first()
        if not user:
            print(f"❌ Usuario '{username}' no encontrado")
            return False
        old_hash = user.password_hash
        new_hash = pwd_context.hash(new_plain_password)
        user.password_hash = new_hash
        db.commit()
        print(f"✅ Usuario '{username}' actualizado:")
        print(f"   Old hash: {old_hash[:30]}...")
        print(f"   New hash: {new_hash[:30]}...")
        return True
    except Exception as e:
        print(f"❌ Error al actualizar {username}: {e}")
        db.rollback()
        return False
    finally:
        db.close()

if __name__ == "__main__":
    # Usa los nombres de usuario y contraseñas que quieras
    print("Actualizando contraseñas de usuarios existentes...")
    update_password("carolina", "carolina2025$")
    update_password("jackson", "jackson2025$")
    print("\n✅ Listo. Ahora puedes probar login con esos usuarios.")