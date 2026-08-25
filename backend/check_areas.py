import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.db.session import session_local
from app.modules.catalogos.model import Area

db = session_local()
try:
    print("Listing Areas:")
    areas = db.query(Area).all()
    for a in areas:
        print(f"Area: ID={a.id}, Nombre={a.nombre}")
except Exception as e:
    print(f"Error: {e}")
finally:
    db.close()

    
