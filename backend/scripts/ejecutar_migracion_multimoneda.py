import os
import sys
import sqlalchemy

# Leer .env del backend si existe
env_path = os.path.join(os.path.dirname(__file__), "..", ".env")
db_url = "postgresql://yeikar:yeikar123@localhost:5432/yeikar"

if os.path.exists(env_path):
    with open(env_path) as f:
        for line in f:
            if line.startswith("DATABASE_URL="):
                db_url = line.strip().split("=", 1)[1]

print(f"Conectando a {db_url}...")
engine = sqlalchemy.create_engine(db_url)

sql_statements = [
    "ALTER TABLE public.pago ADD COLUMN IF NOT EXISTS tasa_cambio numeric(15,6) NOT NULL DEFAULT 1.0;",
    "ALTER TABLE public.pago ADD COLUMN IF NOT EXISTS monto_en_moneda_base numeric(15,2);",
    "UPDATE public.pago SET monto_en_moneda_base = monto WHERE monto_en_moneda_base IS NULL;",
    "ALTER TABLE public.pago ALTER COLUMN monto_en_moneda_base SET NOT NULL;",
    "ALTER TABLE public.pago ALTER COLUMN monto_en_moneda_base SET DEFAULT 0.0;"
]

with engine.connect() as conn:
    trans = conn.begin()
    try:
        for stmt in sql_statements:
            print(f"Ejecutando: {stmt}")
            conn.execute(sqlalchemy.text(stmt))
        trans.commit()
        print("¡Migración ejecutada exitosamente!")
    except Exception as e:
        trans.rollback()
        print(f"Error ejecutando migración: {e}")
        sys.exit(1)
