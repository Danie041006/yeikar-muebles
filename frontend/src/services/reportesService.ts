import api from './api';

export interface PnLDetail {
  moneda: string;
  ingresos: number;
  gastos: number;
  balance: number;
}

export interface PnLResponse {
  mes: string;
  detalles: PnLDetail[];
}

export interface RentabilidadProductoResponse {
  producto_id: number;
  producto_nombre: string;
  cantidad_vendida: number;
  precio_promedio_venta: number;
  costo_promedio_produccion: number;
  margen_promedio: number;
  moneda: string;
}

export interface ReportAlertaStockResponse {
  material_id: number;
  material_nombre: string;
  cantidad_actual: number;
  umbral: number;
  unidad_medida: string;
  ubicacion_nombre: string;
}

export const reportesService = {
  getPnL: async (mes: string): Promise<PnLResponse> => {
    const response = await api.get<PnLResponse>('/reports/pnl', {
      params: { mes },
    });
    return response.data;
  },

  getRentabilidad: async (): Promise<RentabilidadProductoResponse[]> => {
    const response = await api.get<RentabilidadProductoResponse[]>('/reports/rentabilidad-producto');
    return response.data;
  },

  getAlertasStock: async (umbral: number = 5.0): Promise<ReportAlertaStockResponse[]> => {
    const response = await api.get<ReportAlertaStockResponse[]>('/reports/alertas-stock', {
      params: { umbral },
    });
    return response.data;
  },
};
