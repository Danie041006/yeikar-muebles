import api from './api';

export interface InventarioItem {
  id: number;
  material_id: number;
  material_nombre: string;
  ubicacion_id: number;
  ubicacion_nombre: string;
  cantidad: number;
  created_at: string;
  updated_at: string;
  // additional field for table rendering (e.g. minimum stock, unit if needed, we can get from material)
  material?: {
    id: number;
    nombre: string;
    unidad_medida?: {
      abreviatura: string;
    };
    costo_base: number;
  };
}

export interface AlertaStock {
  material_id: number;
  material_nombre: string;
  stock_actual: number;
  stock_minimo: number;
  ubicacion_id: number;
  ubicacion_nombre: string;
}

export interface MovimientoCreate {
  material_id: number;
  ubicacion_id: number;
  tipo: 'ENTRADA' | 'SALIDA' | 'AJUSTE' | 'DAÑO' | 'DEVOLUCION';
  cantidad: number;
  referencia_tipo?: string;
  referencia_id?: number;
  observaciones?: string;
}

export interface MovimientoResponse {
  id: number;
  material_id: number;
  ubicacion_id: number;
  tipo: string;
  cantidad: number;
  referencia_tipo?: string;
  referencia_id?: number;
  observaciones?: string;
  fecha: string;
  created_at: string;
  updated_at: string;
}

export const inventarioService = {
  getInventario: async (params?: { material_id?: number; ubicacion_id?: number }): Promise<InventarioItem[]> => {
    const response = await api.get<InventarioItem[]>('/inventario/', { params });
    return response.data;
  },

  getAlertas: async (umbral: number = 5.0): Promise<AlertaStock[]> => {
    const response = await api.get<AlertaStock[]>('/inventario/alertas', {
      params: { umbral },
    });
    return response.data;
  },

  crearMovimiento: async (movimiento: MovimientoCreate): Promise<MovimientoResponse> => {
    const response = await api.post<MovimientoResponse>('/inventario/movimiento', movimiento);
    return response.data;
  },

  getKardex: async (materialId: number, limit: number = 100): Promise<MovimientoResponse[]> => {
    const response = await api.get<MovimientoResponse[]>(`/inventario/movimientos/material/${materialId}`, {
      params: { limit },
    });
    return response.data;
  },
};
