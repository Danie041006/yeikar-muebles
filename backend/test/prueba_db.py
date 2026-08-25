#!/usr/bin/env python3
print("Script iniciado...")

import sys
print(f"Python version: {sys.version}")

try:
    print("Importando sqlalchemy...")
    from sqlalchemy import create_engine, text
    print("  OK")
except Exception as e:
    print(f"  ERROR: {e}")
    sys.exit(1)

try:
    print("Importando dotenv...")
    from dotenv import load_dotenv
    import os
    print("  OK")
except Exception as e:
    print(f"  ERROR: {e}")
    sys.exit(1)

print("Cargando .env...")
load_dotenv()

db_url = os.getenv("DATABASE_URL")
print(f"DATABASE_URL encontrada: {db_url}")

if not db_url:
    print("ERROR: No se encontró DATABASE_URL en .env")
    print("Creando URL por defecto...")
    db_url = "postgresql://yeikar@localhost:5432/yeikar"
    print(f"Usando: {db_url}")

print("Intentando conectar...")
try:
    engine = create_engine(db_url)
    with engine.connect() as conn:
        result = conn.execute(text("SELECT 1"))
        print(" CONEXION EXITOSA!")
        print(f"Resultado: {result.scalar()}")
except Exception as e:
    print(f" ERROR de conexión: {e}")
    import traceback
    traceback.print_exc()

print("Script finalizado")
