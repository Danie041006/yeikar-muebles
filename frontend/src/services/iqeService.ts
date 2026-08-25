/**
 * iqeService.ts
 * =============
 * Servicio frontend del COTIZADOR MANUAL (sin APIs de pago).
 *
 * Flujo:
 *   1. exportarContexto(params)   → ContextoExportarOut  (paquete para la IA de navegador)
 *   2. importarEstructura(payload)→ GenerateStructureOut (importa el JSON pegado)
 *   3. recalculateStructure(...)  → GenerateStructureOut (recalcula con ediciones)
 *   4. finalizeStructure(...)     → FinalizeResponse     (guarda cotización o producto)
 */

import api from './api';

// ─── Tipos de la API ──────────────────────────────────────────────────────────

export interface LineaCostoOut {
  temp_id: string;
  material_id: number | null;
  nombre: string;
  cantidad: number;
  unidad: string;
  costo_unitario: number;
  costo_total: number;
  precio_pendiente: boolean;
  razon: string;
  fuente: string;
  es_opcional: boolean;
  activo: boolean;
  cantidad_ia_sugerida?: number | null;
  cantidad_referencia?: number | null;
  confianza_cantidad?: 'alta' | 'media' | 'baja' | string;
  sugerencias?: Array<{
    id: number;
    nombre: string;
    costo_base: number;
    unidad: string | null;
    abreviatura: string | null;
  }>;
}

export interface SeccionCostoOut {
  seccion: string;
  items: LineaCostoOut[];
  subtotal: number;
}

export interface ResumenCostosOut {
  costo_materiales: number;
  costo_mano_obra: number;
  costo_gastos: number;
  costo_produccion: number;
  impuesto_porcentaje: number;
  impuestos: number;
  base_con_impuestos: number;
  ganancia_porcentaje: number;
  precio_sin_iva: number;
  iva_porcentaje: number;
  precio_con_iva: number;
}

export interface GenerateStructureOut {
  producto_base_id: number | null;
  producto_base_nombre: string | null;
  score_similitud: number;
  secciones: SeccionCostoOut[];
  materiales_sin_precio: number;
  resumen: ResumenCostosOut;
  secciones_faltantes: string[];
  desviacion_vs_referencia: number | null;
  advertencia: string | null;
}

export interface ImportStructureRequest {
  estructura_propuesta: any[];
  producto_base_id?: number | null;
  tipo_mueble?: string;
  nuevo_ancho: number;
  nuevo_largo: number;
  nuevo_alto?: number | null;
  nuevo_fondo?: number | null;
  dimensiones_referencia?: Record<string, any>;
  ganancia_porcentaje?: number;
  iva_porcentaje?: number;
  impuesto_porcentaje?: number;
  pct_mano_obra?: number;
  pct_gastos?: number;
}

export interface ImportTextoRequest {
  texto: string;
  producto_base_id?: number | null;
  tipo_mueble?: string;
  nuevo_ancho: number;
  nuevo_largo: number;
  nuevo_alto?: number | null;
  nuevo_fondo?: number | null;
  dimensiones_referencia?: Record<string, any>;
  ganancia_porcentaje?: number;
  iva_porcentaje?: number;
  impuesto_porcentaje?: number;
  pct_mano_obra?: number;
  pct_gastos?: number;
}

export interface RecalculateStructureRequest {
  secciones: SeccionCostoOut[];
  ganancia_porcentaje?: number;
  iva_porcentaje?: number;
  impuesto_porcentaje?: number;
  pct_mano_obra?: number;
  pct_gastos?: number;
}

export interface FinalizeStructureRequest {
  guardar_como: 'cotizacion' | 'producto';
  cliente_id?: number | null;
  nombre_producto?: string | null;
  tipo_producto_id?: number | null;
  producto_base_id?: number | null;
  secciones: SeccionCostoOut[];
  nuevo_ancho: number;
  nuevo_largo: number;
  nuevo_alto?: number | null;
  ganancia_porcentaje?: number;
  iva_porcentaje?: number;
  impuesto_porcentaje?: number;
  pct_mano_obra?: number;
  pct_gastos?: number;
  observaciones?: string | null;
  analisis_id?: number | null;
}

export interface FinalizeResponse {
  cotizacion_id: number;
  total_estimado: number;
  pdf_url: string;
  mensaje: string;
}

export interface MaterialContextoOut {
  id: number;
  nombre: string;
  costo_base: number;
  unidad: string | null;
  abreviatura?: string | null;
  sinonimos: string[];
}

export interface PromptContextoOut {
  id: string;
  titulo: string;
  descripcion: string;
  instrucciones: string;
}

export interface ContextoExportarOut {
  producto_base_id: number | null;
  producto_base_nombre: string | null;
  inventario: MaterialContextoOut[];
  receta_similar: {
    producto_id: number;
    nombre: string;
    ancho_base: number;
    largo_base: number;
    alto_base?: number | null;
    secciones: Array<{ seccion: string; items: any[] }>;
  } | null;
  instrucciones: string;
  prompts: PromptContextoOut[];
  texto: string;
}

export interface UnidadMedida {
  id: number;
  nombre: string;
  abreviatura: string;
}

export interface TipoProducto {
  id: number;
  nombre: string;
}

// ─── Funciones de servicio ────────────────────────────────────────────────────

export const iqeService = {
  /**
   * Paso 1: genera el paquete de contexto (inventario + receta similar + reglas
   * + esquema JSON) para pegarlo en una IA de navegador.
   */
  async exportarContexto(params: {
    producto_base_id?: number | null;
    ancho?: number;
    largo?: number;
    alto?: number | null;
    con_foto?: boolean;
    descripcion?: string;
    tipo_mueble?: string;
  }): Promise<ContextoExportarOut> {
    const res = await api.get('/intelligent-quotation/contexto-exportar', { params });
    return res.data;
  },

  /**
   * Paso 2: importa el JSON que devolvió la IA de navegador, lo fusiona con la
   * receta base y lo matchea contra el inventario.
   */
  async importarEstructura(payload: ImportStructureRequest): Promise<GenerateStructureOut> {
    const res = await api.post('/intelligent-quotation/import-structure', payload);
    return res.data;
  },

  /**
   * Paso 2b: importa la respuesta de la IA en FORMATO EXCEL (tabla por
   * secciones). El backend la convierte al JSON interno y la matchea.
   */
  async importarTexto(payload: ImportTextoRequest): Promise<GenerateStructureOut> {
    const res = await api.post('/intelligent-quotation/import-texto', payload);
    return res.data;
  },

  /**
   * Paso 3: recalcula subtotales y totales tras ediciones del vendedor.
   * Los precios siempre vienen del inventario actual.
   */
  async recalculateStructure(payload: RecalculateStructureRequest): Promise<GenerateStructureOut> {
    const res = await api.post('/intelligent-quotation/recalculate-structure', payload);
    return res.data;
  },

  /**
   * Paso 4: guarda la estructura como cotización o como producto con receta.
   */
  async finalizeStructure(payload: FinalizeStructureRequest): Promise<FinalizeResponse> {
    const res = await api.post('/intelligent-quotation/finalize-structure', payload);
    return res.data;
  },

  /**
   * Catálogos auxiliares
   */
  async getUnidadesMedida(): Promise<UnidadMedida[]> {
    const res = await api.get('/catalogos/unidad-medida/');
    return res.data;
  },

  async getTiposProducto(): Promise<TipoProducto[]> {
    const res = await api.get('/catalogos/tipo-producto/');
    return res.data;
  },
};
