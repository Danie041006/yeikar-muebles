import api from './api';
import { Client } from './clienteService';

export interface Moneda {
  id: number;
  codigo: string;
  nombre: string;
  simbolo: string;
  activo?: boolean;
}

export interface Product {
  id: number;
  codigo: string;
  nombre: string;
  descripcion?: string;
  precio_venta_base?: number;
  precio_costo_base?: number;
  alto_base: number;
  ancho_base: number;
  largo_base: number;
  categoria?: string;
}

export interface QuoteDetail {
  id?: number;
  cotizacion_id?: number;
  producto_id: number;
  cantidad: number;
  precio: number;
  alto?: number | null;
  ancho?: number | null;
  largo?: number | null;
  observaciones?: string | null;
  costo_materiales?: number | null;
  costo_mano_obra?: number | null;
  costo_gastos?: number | null;
  costo_total?: number | null;
  receta_personalizada?: any;
}

export interface Quote {
  id: number;
  cliente_id: number;
  fecha: string;
  estado: string; // "Borrador", "Enviada", "Aprobada", "Rechazada"
  total_estimado: number;
  moneda_id: number;
  tasa_cambio: number;
  total_en_moneda_base?: number;
  observaciones?: string;
  created_at?: string;
  updated_at?: string;
  creado_por_id?: number | null;
  actualizado_por_id?: number | null;
  creador_nombre?: string | null;
  cliente?: Client;
  moneda?: Moneda;
  detalles: QuoteDetail[];
}

export interface QuoteCreate {
  cliente_id: number;
  fecha: string;
  estado: string;
  total_estimado: number;
  moneda_id?: number;
  tasa_cambio?: number;
  observaciones?: string;
  detalles: QuoteDetail[];
}

export interface CalculationResult {
  costo_materiales: number;
  costo_mano_obra: number;
  costo_gastos_indirectos: number;
  costo_total: number;
  precio_sugerido: number;
  precio_venta: number;
  materiales_detalle: Array<{
    material_id: number;
    nombre: string;
    cantidad_calculada: number;
    unidad: string;
    costo_subtotal: number;
  }>;
  desglose_por_seccion?: any;
}

export const cotizacionService = {
  getAll: async (
    search?: string,
    soloMesActual: boolean = true,
    mes?: number,
    anio?: number
  ): Promise<Quote[]> => {
    const params: any = { solo_mes_actual: soloMesActual };
    if (search) params.buscar = search;
    if (mes !== undefined) params.mes = mes;
    if (anio !== undefined) params.anio = anio;

    const response = await api.get<Quote[]>('/cotizacion/', { params });
    return response.data;
  },

  getById: async (id: number): Promise<Quote> => {
    const response = await api.get<Quote>(`/cotizacion/${id}`);
    return response.data;
  },

  create: async (quote: QuoteCreate): Promise<Quote> => {
    const response = await api.post<Quote>('/cotizacion/', quote);
    return response.data;
  },

  update: async (id: number, quote: Partial<QuoteCreate>): Promise<Quote> => {
    const response = await api.put<Quote>(`/cotizacion/${id}`, quote);
    return response.data;
  },

  delete: async (id: number): Promise<void> => {
    await api.delete(`/cotizacion/${id}`);
  },

  // Products list
  getProducts: async (search?: string): Promise<Product[]> => {
    const response = await api.get<Product[]>('/producto/', {
      params: search ? { buscar: search } : {},
    });
    return response.data;
  },

  // Calculate pricing
  calculatePrice: async (
    productId: number,
    params: {
      ancho: number;
      largo: number;
      ganancia?: number;
      iva?: number;
      pct_mano_obra?: number;
      pct_gastos?: number;
    }
  ): Promise<CalculationResult> => {
    const response = await api.get<any>(
      `/producto/${productId}/calcular-precio`,
      {
        params: {
          ancho: params.ancho,
          largo: params.largo,
          ganancia: params.ganancia ?? 40.0,
          iva: params.iva ?? 0.0,
          pct_mano_obra: params.pct_mano_obra ?? 15.0,
          pct_gastos: params.pct_gastos ?? 10.0,
        },
      }
    );

    const data = response.data;

    // Backward-compatible mapping of summary costs
    const costo_gastos_indirectos = data.costo_gastos_indirectos !== undefined 
      ? data.costo_gastos_indirectos 
      : (data.costo_gastos !== undefined ? data.costo_gastos : 0);

    const costo_total = data.costo_total !== undefined 
      ? data.costo_total 
      : (data.costo_produccion !== undefined ? data.costo_produccion : 0);

    const precio_venta = data.precio_venta !== undefined 
      ? data.precio_venta 
      : (data.precio_con_iva !== undefined ? data.precio_con_iva : (data.precio_sin_iva !== undefined ? data.precio_sin_iva : 0));

    // Backward-compatible mapping of materials list
    const rawMateriales = data.materiales_detalle || data.materiales || [];
    const materiales_detalle = rawMateriales.map((mat: any) => ({
      material_id: mat.material_id,
      nombre: mat.nombre || mat.material_nombre || '',
      cantidad_calculada: mat.cantidad_calculada || 0,
      unidad: mat.unidad || '',
      costo_subtotal: mat.costo_subtotal !== undefined 
        ? mat.costo_subtotal 
        : (mat.costo_total !== undefined ? mat.costo_total : 0),
    }));

    return {
      costo_materiales: data.costo_materiales || 0,
      costo_mano_obra: data.costo_mano_obra || 0,
      costo_gastos_indirectos,
      costo_total,
      precio_sugerido: precio_venta,
      precio_venta,
      materiales_detalle,
    };
  },

  fetchCurrencies: async (): Promise<Moneda[]> => {
    const response = await api.get<Moneda[]>('/catalogos/moneda/');
    return response.data;
  },

  recalculateCustomRecipe: async (
    ganancia: number,
    secciones: any[]
  ): Promise<CalculationResult> => {
    const response = await api.post<any>('/recalculate-custom-recipe', {
      ganancia,
      secciones,
    });
    const data = response.data;
    
    const rawMateriales = data.materiales || [];
    const materiales_detalle = rawMateriales.map((mat: any) => ({
      material_id: mat.material_id,
      nombre: mat.nombre || '',
      cantidad_calculada: mat.cantidad || 0,
      unidad: mat.unidad || '',
      costo_subtotal: mat.costo_subtotal || 0,
    }));

    return {
      costo_materiales: data.costo_materiales || 0,
      costo_mano_obra: 0,
      costo_gastos_indirectos: 0,
      costo_total: data.costo_total || 0,
      precio_sugerido: data.precio_venta || 0,
      precio_venta: data.precio_venta || 0,
      materiales_detalle,
      desglose_por_seccion: data.desglose_por_seccion,
    } as any;
  },
};
