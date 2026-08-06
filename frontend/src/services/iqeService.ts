/**
 * iqeService.ts
 * =============
 * Servicio frontend para el Motor de Cotización Inteligente (IQE).
 * 
 * Todos los endpoints apuntan a /api/v1/intelligent-quotation/
 * 
 * FLUJO:
 *   1. analyzeImage(file, contexto?) → FurnitureAttributesOut  (IA analiza la foto)
 *   2. findSimilar(attrs)            → FindSimilarResponse     (busca Top N históricos)
 *   3. createDraft(payload)          → DraftOut                (genera borrador con costos actuales)
 *   4. recalculate(payload)          → DraftOut                (recalcula con cambios del vendedor)
 *   5. finalize(payload)             → FinalizeResponse        (guarda cotización y genera PDF)
 */

import api from './api';

// ─── Tipos de la API ──────────────────────────────────────────────────────────

export interface FurnitureAttributesOut {
  tipo_mueble: string;
  familia_probable: string | null;
  estilo_general: string | null;
  tipo_patas: string | null;
  tiene_tapiceria: boolean;
  tiene_luces: boolean;
  nivel_confianza: number;
  observaciones: string | null;
  atributos_extra: Record<string, any>;
  requiere_revision_humana: boolean;
  estructura_propuesta: any[];
  analisis_id?: number | null;
  percepcion?: string | null;
  dimensiones_referencia?: Record<string, any>;
  preguntas_faltantes?: PreguntaFaltanteOut[];
}

export interface PreguntaFaltanteOut {
  clave: string;
  pregunta: string;
  tipo: 'select' | 'multi' | 'si_no' | 'numero' | 'texto';
  opciones: string[];
  requerida: boolean;
  por_que: string;
}

export interface DatosProyecto {
  ancho?: number | null;
  largo?: number | null;
  alto?: number | null;
  fondo?: number | null;
  material_principal?: string;
  espesor_tablero?: string;
  acabado?: string;
  cantidad_puertas?: number | null;
  tiene_espejo?: boolean;
}

export interface SimilarityResultOut {
  producto_id: number;
  nombre: string;
  tipo_mueble: string;
  score: number;
  score_pct: number;
  coincidencias: string[];
  diferencias: string[];
  ancho_base: number | null;
  largo_base: number | null;
  tiene_receta: boolean;
  es_estructura_nueva: boolean;
}

export interface FindSimilarResponse {
  resultados: SimilarityResultOut[];
  tipo_mueble_buscado: string;
  hay_resultados: boolean;
  mensaje: string | null;
}

export interface MaterialLineaOut {
  id?: number;
  material_id: number;
  nombre: string;
  tipo_escala: string;
  cantidad_base: number;
  cantidad_calculada: number;
  unidad: string;
  costo_unitario: number;
  costo_total: number;
  activo: boolean;
  observaciones?: string;
}

export interface DraftOut {
  producto_base_id: number;
  producto_base_nombre: string;
  nuevo_ancho: number;
  nuevo_largo: number;
  materiales: MaterialLineaOut[];
  costo_materiales: number;
  costo_mano_obra: number;
  costo_gastos: number;
  costo_produccion: number;
  ganancia_porcentaje: number;
  precio_sin_iva: number;
  iva_porcentaje: number;
  precio_con_iva: number;
}

export interface FindSimilarRequest {
  tipo_mueble: string;
  familia_probable?: string | null;
  estilo_general?: string | null;
  tipo_patas?: string | null;
  tiene_tapiceria: boolean;
  tiene_luces: boolean;
  atributos_extra: Record<string, any>;
  top_n?: number;
}

export interface CreateDraftRequest {
  producto_base_id: number;
  nuevo_ancho: number;
  nuevo_largo: number;
  ganancia_porcentaje?: number;
  iva_porcentaje?: number;
  pct_mano_obra?: number;
  pct_gastos?: number;
  atributos?: Record<string, any>;
}

export interface MaterialLineaIn {
  material_id: number;
  cantidad_calculada: number;
  activo: boolean;
}

export interface RecalculateRequest {
  producto_base_id: number;
  nuevo_ancho: number;
  nuevo_largo: number;
  materiales: MaterialLineaIn[];
  ganancia_porcentaje?: number;
  iva_porcentaje?: number;
  pct_mano_obra?: number;
  pct_gastos?: number;
  atributos?: Record<string, any>;
}

export interface FinalizeRequest {
  cliente_id: number;
  producto_base_id: number;
  nuevo_ancho: number;
  nuevo_largo: number;
  materiales: MaterialLineaIn[];
  ganancia_porcentaje?: number;
  iva_porcentaje?: number;
  pct_mano_obra?: number;
  pct_gastos?: number;
  observaciones?: string;
  analisis_id?: number;
  atributos?: Record<string, any>;
}

export interface FinalizeResponse {
  cotizacion_id: number;
  total_estimado: number;
  pdf_url: string;
  mensaje: string;
}

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
}

export interface GenerateStructureRequest {
  tipo_mueble: string;
  atributos: Record<string, any>;
  estructura_propuesta: any[];
  nuevo_ancho: number;
  nuevo_largo: number;
  nuevo_alto?: number | null;
  nuevo_fondo?: number | null;
  respuestas?: Record<string, any>;
  dimensiones_referencia?: Record<string, any>;
  ganancia_porcentaje?: number;
  iva_porcentaje?: number;
  pct_mano_obra?: number;
  pct_gastos?: number;
}

export interface RecalculateStructureRequest {
  secciones: SeccionCostoOut[];
  ganancia_porcentaje?: number;
  iva_porcentaje?: number;
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
  pct_mano_obra?: number;
  pct_gastos?: number;
  observaciones?: string | null;
  analisis_id?: number | null;
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
   * Paso 1: Sube imagen y extrae atributos visuales con IA.
   * Usa multipart/form-data. El campo `contexto_adicional` es opcional.
   * `datosProyecto` son las medidas/opciones que el vendedor definió ANTES
   * del análisis (ancho, largo, alto, fondo, material, acabado…).
   */
  async analyzeImage(file: File, contextoAdicional?: string, datosProyecto?: DatosProyecto): Promise<FurnitureAttributesOut> {
    const formData = new FormData();
    formData.append('file', file);
    if (contextoAdicional?.trim()) {
      formData.append('contexto_adicional', contextoAdicional.trim());
    }
    if (datosProyecto && Object.keys(datosProyecto).length > 0) {
      formData.append('datos_proyecto', JSON.stringify(datosProyecto));
    }
    const res = await api.post('/intelligent-quotation/analyze-image', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
    return res.data;
  },

  /**
   * Paso 1.5: La IA genera dinámicamente SOLO las preguntas críticas que la
   * imagen no respondió y que SÍ afectan la estructura de costos.
   */
  async generateQuestions(file: File, contextoAdicional?: string, datosProyecto?: DatosProyecto): Promise<PreguntaFaltanteOut[]> {
    const formData = new FormData();
    formData.append('file', file);
    if (contextoAdicional?.trim()) {
      formData.append('contexto_adicional', contextoAdicional.trim());
    }
    if (datosProyecto && Object.keys(datosProyecto).length > 0) {
      formData.append('datos_proyecto', JSON.stringify(datosProyecto));
    }
    const res = await api.post('/intelligent-quotation/generate-questions', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
    return res.data;
  },

  /**
   * Paso 2: Busca Top N estructuras históricas similares.
   * Usa los atributos VALIDADOS POR EL VENDEDOR (no directamente de la IA).
   */
  async findSimilar(payload: FindSimilarRequest): Promise<FindSimilarResponse> {
    const res = await api.post('/intelligent-quotation/find-similar', payload);
    return res.data;
  },

  /**
   * Paso 3: Genera borrador con costos escalados y precios del inventario actual.
   */
  async createDraft(payload: CreateDraftRequest): Promise<DraftOut> {
    const res = await api.post('/intelligent-quotation/create-draft', payload);
    return res.data;
  },

  /**
   * Paso 4: Recalcula con cambios manuales del vendedor.
   */
  async recalculate(payload: RecalculateRequest): Promise<DraftOut> {
    const res = await api.post('/intelligent-quotation/recalculate', payload);
    return res.data;
  },

  /**
   * Paso 5: Guarda la cotización definitiva en la BD.
   */
  async finalize(payload: FinalizeRequest): Promise<FinalizeResponse> {
    const res = await api.post('/intelligent-quotation/finalize', payload);
    return res.data;
  },

  /**
   * Generar estructura combinada IA + histórico
   */
  async generateStructure(payload: GenerateStructureRequest): Promise<GenerateStructureOut> {
    const res = await api.post('/intelligent-quotation/generate-structure', payload);
    return res.data;
  },

  /**
   * Recalcular estructura organizada en secciones
   */
  async recalculateStructure(payload: RecalculateStructureRequest): Promise<GenerateStructureOut> {
    const res = await api.post('/intelligent-quotation/recalculate-structure', payload);
    return res.data;
  },

  /**
   * Guardar definitivamente como cotización o nuevo producto
   */
  async finalizeStructure(payload: FinalizeStructureRequest): Promise<FinalizeResponse> {
    const res = await api.post('/intelligent-quotation/finalize-structure', payload);
    return res.data;
  },

  /**
   * Obtener todas las unidades de medida de los catálogos
   */
  async getUnidadesMedida(): Promise<UnidadMedida[]> {
    const res = await api.get('/catalogos/unidad-medida/');
    return res.data;
  },

  /**
   * Obtener todos los tipos de producto de los catálogos
   */
  async getTiposProducto(): Promise<TipoProducto[]> {
    const res = await api.get('/catalogos/tipo-producto/');
    return res.data;
  },

  /**
   * Healthcheck del módulo IQE.
   */
  async health(): Promise<{ status: string; vision_provider: string; confianza_minima: number }> {
    const res = await api.get('/intelligent-quotation/health');
    return res.data;
  },
};
