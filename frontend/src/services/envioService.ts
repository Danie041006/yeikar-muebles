import api from './api';
import { Order } from './pedidoService';
import { Empleado } from './produccionService';
export interface Envio {
  id: number;
  pedido_id: number;
  empleado_id?: number | null;
  fecha_salida?: string | null;
  fecha_entrega?: string | null;
  estado: 'PREPARADO' | 'EN_TRANSITO' | 'ENTREGADO' | 'FALLIDO';
  direccion_entrega?: string | null;
  guia_despacho?: string | null;
  observaciones?: string | null;
  created_at?: string;
  updated_at?: string;
  creado_por_id?: number | null;
  actualizado_por_id?: number | null;
  asignado_por_usuario_id?: number | null;
  creador_nombre?: string | null;
  asignado_por_nombre?: string | null;
  pedido?: Order;
  empleado?: Empleado | null;
}

export interface EnvioUbicacion {
  id: number;
  envio_id: number;
  empleado_id?: number | null;
  reportado_por_id?: number | null;
  latitud: number;
  longitud: number;
  precision_m?: number | null;
  velocidad?: number | null;
  rumbo?: number | null;
  capturada_en?: string | null;
  recibida_en: string;
  fuente: string;
  secuencia?: number | null;
}
export interface EnvioUpdate {
  empleado_id?: number | null;
  fecha_salida?: string | null;
  fecha_entrega?: string | null;
  estado?: 'PREPARADO' | 'EN_TRANSITO' | 'ENTREGADO' | 'FALLIDO';
  direccion_entrega?: string | null;
  guia_despacho?: string | null;
  observaciones?: string | null;
}
export const envioService = {
  getAll: async (buscar?: string, estado?: string): Promise<Envio[]> => {
    const response = await api.get<Envio[]>('/envio/', {
      params: {
        ...(buscar ? { buscar } : {}),
        ...(estado ? { estado } : {}),
      },
    });
    return response.data;
  },
  getById: async (id: number): Promise<Envio> => {
    const response = await api.get<Envio>(`/envio/${id}`);
    return response.data;
  },
  update: async (id: number, data: EnvioUpdate): Promise<Envio> => {
    const response = await api.put<Envio>(`/envio/${id}`, data);
    return response.data;
  },
  updateEstado: async (id: number, estado: string): Promise<Envio> => {
    const response = await api.put<Envio>(`/envio/${id}/estado`, null, {
      params: { estado },
    });
    return response.data;
  },
  delete: async (id: number): Promise<void> => {
    await api.delete(`/envio/${id}`);
  },
  reportLocation: async (id: number, data: Omit<EnvioUbicacion, 'id' | 'envio_id' | 'empleado_id' | 'reportado_por_id' | 'recibida_en'>): Promise<EnvioUbicacion> => {
    const response = await api.post<EnvioUbicacion>(`/envio/${id}/ubicaciones`, data);
    return response.data;
  },
  getLatestLocation: async (id: number): Promise<EnvioUbicacion | null> => {
    const response = await api.get<EnvioUbicacion | null>(`/envio/${id}/ubicacion-actual`);
    return response.data;
  },
  getLocationHistory: async (id: number): Promise<EnvioUbicacion[]> => {
    const response = await api.get<EnvioUbicacion[]>(`/envio/${id}/ubicaciones`);
    return response.data;
  },
};
