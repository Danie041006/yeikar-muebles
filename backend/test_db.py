import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.db.session import session_local
from app.modules.users.model import Usuario, usuario_rol
from app.modules.catalogos.model import Rol

db = session_local()
try:
    print("Listing roles:")
    roles = db.query(Rol).all()
    for r in roles:
        print(f"Role: ID={r.id}, Nombre={r.nombre}")

    print("\nListing users:")
    users = db.query(Usuario).all()
    for u in users:
        print(f"User: ID={u.id}, Username={u.nombre_usuario}, Roles={[r.nombre for r in u.roles]}")
except Exception as e:
    print(f"Error querying DB: {e}")
finally:
    db.close()
