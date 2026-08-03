-- Migración: Agregar columnas faltantes a gasto
ALTER TABLE public.gasto ADD COLUMN IF NOT EXISTS tasa_cambio numeric(15,6) NOT NULL DEFAULT 1.0;
ALTER TABLE public.gasto ADD COLUMN IF NOT EXISTS monto_en_moneda_base numeric(15,2) NOT NULL DEFAULT 0.0;

-- Actualizar registros existentes: si monto_en_moneda_base es 0, copiar monto
UPDATE public.gasto SET monto_en_moneda_base = monto WHERE monto_en_moneda_base = 0;

-- Agregar columna categoria a tipo_gasto si no existe
ALTER TABLE public.tipo_gasto ADD COLUMN IF NOT EXISTS categoria character varying(50) NOT NULL DEFAULT 'OPERATIVO';

-- Seed de categorías de gasto (OPERATIVO, PASIVO, PRODUCCION)
INSERT INTO public.tipo_gasto (nombre, categoria) VALUES
  ('Alquiler / Arriendo', 'OPERATIVO'),
  ('Servicios Públicos (Luz, Agua, Internet)', 'OPERATIVO'),
  ('Nómina / Sueldos', 'OPERATIVO'),
  ('Mantenimiento de Maquinaria y Taller', 'OPERATIVO'),
  ('Papelería y Artículos de Oficina', 'OPERATIVO'),
  ('Flete y Transporte', 'OPERATIVO'),
  ('Amortización de Préstamos / Deudas', 'PASIVO'),
  ('Impuestos y Tasas', 'PASIVO'),
  ('Cuentas por Pagar a Proveedores', 'PASIVO'),
  ('Consumo de Materia Prima en Producción', 'PRODUCCION')
ON CONFLICT (nombre) DO UPDATE SET categoria = EXCLUDED.categoria;
