-- Migración: Soporte para pagos multi-moneda con conversión TRM
-- Fecha: 2026-07-20
-- Descripción:
--   Agrega dos columnas a la tabla `pago`:
--   1. tasa_cambio: la tasa (TRM) usada al momento del pago. Si el pago es en la misma
--      moneda que la venta, este valor es 1.0.
--   2. monto_en_moneda_base: el equivalente del monto en la moneda base de la venta
--      (monto × tasa_cambio). Este es el valor que se descuenta del saldo de la venta.
--
-- IMPORTANTE: Para pagos existentes se asume que su monto ya estaba en la moneda
-- correcta (tasa_cambio = 1.0 y monto_en_moneda_base = monto).

BEGIN;

-- 1. Agregar columna tasa_cambio con default 1.0 para no romper registros existentes
ALTER TABLE public.pago
    ADD COLUMN IF NOT EXISTS tasa_cambio numeric(15,6) NOT NULL DEFAULT 1.0;

-- 2. Agregar columna monto_en_moneda_base.
--    Para registros existentes, igualamos al monto original (asumiendo misma moneda).
ALTER TABLE public.pago
    ADD COLUMN IF NOT EXISTS monto_en_moneda_base numeric(15,2);

-- 3. Poblar monto_en_moneda_base para registros existentes
UPDATE public.pago
    SET monto_en_moneda_base = monto
    WHERE monto_en_moneda_base IS NULL;

-- 4. Ahora que todos los valores están poblados, agregar restricción NOT NULL
ALTER TABLE public.pago
    ALTER COLUMN monto_en_moneda_base SET NOT NULL;

-- 5. Agregar default para nuevos registros (el service lo sobreescribirá correctamente)
ALTER TABLE public.pago
    ALTER COLUMN monto_en_moneda_base SET DEFAULT 0.0;

COMMIT;
