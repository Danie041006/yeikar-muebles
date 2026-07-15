-- =============================================================================
-- MIGRACIÓN: Sistema de costeo paramétrico para YEIKAR
-- Fecha: 2026-06-10
-- Descripción: Agrega columnas de dimensiones base a `producto` y crea la
--              tabla `producto_material` con reglas de escalado por material.
-- =============================================================================

-- 1. Agregar columnas de dimensiones base al producto
-- (Si ya existen, el IF NOT EXISTS lo ignora)
ALTER TABLE public.producto
    ADD COLUMN IF NOT EXISTS ancho_base NUMERIC(10,2) DEFAULT 1.60,
    ADD COLUMN IF NOT EXISTS largo_base NUMERIC(10,2) DEFAULT 1.90,
    ADD COLUMN IF NOT EXISTS alto_base  NUMERIC(10,2) DEFAULT NULL;

COMMENT ON COLUMN public.producto.ancho_base IS 'Ancho de referencia para calcular escalado (metros).';
COMMENT ON COLUMN public.producto.largo_base IS 'Largo de referencia para calcular escalado (metros).';
COMMENT ON COLUMN public.producto.alto_base  IS 'Alto de referencia para calcular escalado (metros), opcional.';

-- 2. Crear tabla producto_material (receta paramétrica)
CREATE TABLE IF NOT EXISTS public.producto_material (
    id                    BIGSERIAL PRIMARY KEY,
    producto_id           BIGINT       NOT NULL REFERENCES public.producto(id) ON DELETE CASCADE,
    material_id           BIGINT       NOT NULL REFERENCES public.material(id) ON DELETE RESTRICT,
    cantidad_base         NUMERIC(14,4) NOT NULL,
    tipo_escala           VARCHAR(20)  NOT NULL,

    -- Solo para ESPACIADO
    distancia_pauta_cm    NUMERIC(8,2)  DEFAULT NULL,
    tornillos_por_pieza   INTEGER       DEFAULT NULL,

    -- Condición de activación: expresión JSON  {"campo": "nuevo_largo", "op": ">", "valor": 2.0}
    -- Si está vacío/nulo, el material siempre aplica.
    condicion_activacion  JSONB         DEFAULT NULL,

    -- Para POR_RANGO: lista de rangos [{"max": 1.8, "cantidad": 2}, {"max": 2.2, "cantidad": 4}]
    -- La clave "max" se refiere al nuevo_largo
    rangos                JSONB         DEFAULT NULL,

    -- Fórmula personalizada como texto (ej. "cantidad_base * (nuevo_largo / largo_base) + 2")
    -- Solo evaluada si tipo_escala = 'FORMULA'
    formula_personalizada TEXT          DEFAULT NULL,

    -- Si TRUE, la cantidad_base es fija sin importar el tipo_escala (override manual)
    es_fijo_override      BOOLEAN       DEFAULT FALSE,

    -- Notas para el operador que carga la receta
    observaciones         TEXT          DEFAULT NULL,

    created_at            TIMESTAMP     DEFAULT CURRENT_TIMESTAMP,
    updated_at            TIMESTAMP     DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT pm_tipo_escala_check CHECK (
        tipo_escala IN ('FIJO', 'LINEAL', 'AREA', 'ESPACIADO', 'POR_RANGO', 'FORMULA')
    ),
    CONSTRAINT pm_cantidad_positiva CHECK (cantidad_base > 0)
);

ALTER TABLE public.producto_material OWNER TO postgres;

COMMENT ON TABLE public.producto_material IS
    'Receta paramétrica: relaciona cada producto con sus materiales y define cómo escala la cantidad cuando cambian las dimensiones.';

COMMENT ON COLUMN public.producto_material.tipo_escala IS
    'FIJO=no cambia | LINEAL=escala con largo | AREA=escala con área | ESPACIADO=perímetro/pauta | POR_RANGO=saltos discretos | FORMULA=expresión personalizada';

COMMENT ON COLUMN public.producto_material.condicion_activacion IS
    'JSON: {"campo":"nuevo_largo","op":">","valor":2.0}. Si no se cumple, la cantidad se fuerza a 0.';

COMMENT ON COLUMN public.producto_material.rangos IS
    'JSON para POR_RANGO: [{"max":1.8,"cantidad":2},{"max":2.2,"cantidad":4}].';

-- Índices
CREATE INDEX IF NOT EXISTS idx_pm_producto  ON public.producto_material(producto_id);
CREATE INDEX IF NOT EXISTS idx_pm_material  ON public.producto_material(material_id);

-- Trigger para updated_at automático
CREATE OR REPLACE TRIGGER trg_pm_updated
    BEFORE UPDATE ON public.producto_material
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

-- 3. Tabla para guardar ajustes manuales de Carolina en cotizaciones
CREATE TABLE IF NOT EXISTS public.cotizacion_material_ajuste (
    id                      BIGSERIAL PRIMARY KEY,
    cotizacion_id           BIGINT        NOT NULL REFERENCES public.cotizacion(id) ON DELETE CASCADE,
    producto_material_id    BIGINT        NOT NULL REFERENCES public.producto_material(id) ON DELETE CASCADE,
    ancho_usado             NUMERIC(10,2) NOT NULL,
    largo_usado             NUMERIC(10,2) NOT NULL,
    cantidad_calculada      NUMERIC(14,4) NOT NULL,
    cantidad_ajustada       NUMERIC(14,4) NOT NULL,
    motivo                  TEXT          DEFAULT NULL,
    created_at              TIMESTAMP     DEFAULT CURRENT_TIMESTAMP
);

ALTER TABLE public.cotizacion_material_ajuste OWNER TO postgres;

COMMENT ON TABLE public.cotizacion_material_ajuste IS
    'Guarda los ajustes manuales que hace el usuario sobre la lista de materiales calculada. Permite aprendizaje futuro.';

-- Permisos
GRANT SELECT, INSERT, UPDATE ON public.producto_material TO yeikar;
GRANT SELECT, INSERT, UPDATE ON public.cotizacion_material_ajuste TO yeikar;
GRANT USAGE, SELECT ON SEQUENCE public.producto_material_id_seq TO yeikar;
GRANT USAGE, SELECT ON SEQUENCE public.cotizacion_material_ajuste_id_seq TO yeikar;

-- Verificación final
DO $$
BEGIN
    RAISE NOTICE '✅ Migración completada: columnas en producto + tablas producto_material y cotizacion_material_ajuste creadas.';
END $$;
