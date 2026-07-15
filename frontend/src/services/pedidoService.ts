import api from './api';
import { Client } from './clienteService';
import { Product } from './cotizacionService';

export interface OrderDetail {
  id: number;
  pedido_id: number;
  producto_id: number;
  cantidad: number;
  precio: number;
  alto?: number;
  ancho?: number;
  largo?: number;
  color?: string;
  acabado?: string;
  descripcion_especifica?: string;
  observaciones?: string;
  producto?: Product;
}

export interface Order {
  id: number;
  cotizacion_id: number;
  cliente_id: number;
  fecha: string;
  estado: string; // "Aprobado", "En producción", "Terminado", "Entregado", "Cancelado"
  observaciones?: string;
  fecha_entrega_estimada?: string;
  created_at?: string;
  updated_at?: string;
  cliente?: Client;
  detalles: OrderDetail[];
}

export interface OrderUpdate {
  estado?: string;
  observaciones?: string;
  fecha_entrega_estimada?: string;
}

export interface ConvertDetail {
  producto_id: number;
  cantidad: number;
  precio: number;
  alto?: number;
  ancho?: number;
  largo?: number;
  color?: string;
  acabado?: string;
  descripcion_especifica?: string;
  observaciones?: string;
}

export const pedidoService = {
  getAll: async (
    search?: string,
    soloMesActual: boolean = true,
    mes?: number,
    anio?: number
  ): Promise<Order[]> => {
    const params: any = { solo_mes_actual: soloMesActual };
    if (search) params.buscar = search;
    if (mes !== undefined) params.mes = mes;
    if (anio !== undefined) params.anio = anio;

    const response = await api.get<Order[]>('/pedido/', { params });
    return response.data;
  },

  getById: async (id: number): Promise<Order> => {
    const response = await api.get<Order>(`/pedido/${id}`);
    return response.data;
  },

  update: async (id: number, order: OrderUpdate): Promise<Order> => {
    const response = await api.put<Order>(`/pedido/${id}`, order);
    return response.data;
  },

  delete: async (id: number): Promise<void> => {
    await api.delete(`/pedido/${id}`);
  },

  convertQuote: async (
    quoteId: number,
    details: ConvertDetail[],
    estimatedDeliveryDate?: string
  ): Promise<Order> => {
    const response = await api.post<Order>(
      `/pedido/convertir/${quoteId}`,
      details,
      {
        params: estimatedDeliveryDate
          ? { fecha_entrega_estimada: estimatedDeliveryDate }
          : {},
      }
    );
    return response.data;
  },
};
