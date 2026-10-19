import api from './api';
import { Client } from './clienteService';
import { Product } from './cotizacionService';
import { borrarCache, conCache, mutarOEncolar, parchearCache } from '../offline/cache';

export type TipoItem = 'FABRICADO' | 'REVENTA' | 'INSUMO' | 'REPARACION' | 'SERVICIO';

export interface OrderDetail {
  id: number;
  pedido_id: number;
  producto_id?: number | null;
  material_id?: number | null;
  tipo_item?: TipoItem;
  cantidad: number;
  precio: number;
  /** Unidad vendida y equivalencia en la unidad del inventario (insumos). */
  unidad_captura?: 'M' | 'CM' | null;
  cantidad_base?: number | null;
  alto?: number;
  ancho?: number;
  largo?: number;
  color?: string;
  acabado?: string;
  descripcion_especifica?: string;
  observaciones?: string;
  es_obsequio?: boolean;
  producto?: Product;
  material?: { id: number; nombre: string; costo_base: number; unidad_medida?: { abreviatura: string } };
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
  producto_id?: number | null;
  material_id?: number | null;
  tipo_item?: TipoItem;
  cantidad: number;
  precio: number;
  alto?: number;
  ancho?: number;
  largo?: number;
  color?: string;
  acabado?: string;
  descripcion_especifica?: string;
  observaciones?: string;
  es_obsequio?: boolean;
}

export interface RentabilidadPedido {
  pedido_id: number;
  moneda_id: number;
  moneda_codigo?: string | null;
  total_cobrado: number;
  total_cobrado_base: number;
  costo_estimado_produccion: number;
  costo_real_produccion: number;
  diferencia_costo: number;
  flete_cobrado_base: number;
  flete_real_base: number;
  margen_estimado: number;
  margen_real: number;
  tiene_produccion: boolean;
}

export interface ConvertQuoteBody {
  detalles: ConvertDetail[];
  fecha_entrega_estimada?: string;
  adelanto?: number;
  moneda_adelanto_id?: number;
  tasa_cambio_adelanto?: number;
  metodo_pago?: string;
  /** Fecha del abono inicial (YYYY-MM-DD); sin ella, HOY en hora Venezuela. */
  fecha_adelanto?: string;
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

    return conCache(`pedidos:${search ?? ''}:${soloMesActual}:${mes ?? ''}:${anio ?? ''}`, async () => {
      const response = await api.get<Order[]>('/pedido/', { params });
      return response.data;
    });
  },

  getById: async (id: number): Promise<Order> => {
    return conCache(`pedido:${id}`, async () => {
      const response = await api.get<Order>(`/pedido/${id}`);
      return response.data;
    });
  },

  getRentabilidad: async (id: number): Promise<RentabilidadPedido> => {
    const response = await api.get<RentabilidadPedido>(`/pedido/${id}/rentabilidad`);
    return response.data;
  },

  update: async (id: number, order: OrderUpdate): Promise<Order> => {
    return mutarOEncolar<Order>('pedido.actualizar', { pedido_id: id, ...order }, {
      enLinea: async () => {
        const response = await api.put<Order>(`/pedido/${id}`, order);
        return response.data;
      },
      optimista: async () => {
        await parchearCache('pedido:', (p) => (p?.id === id ? { ...p, ...order } : undefined));
        await parchearCache('pedidos:', (lista) =>
          Array.isArray(lista) ? lista.map((p: any) => (p.id === id ? { ...p, ...order } : p)) : undefined,
        );
      },
    });
  },

  delete: async (id: number): Promise<void> => {
    await mutarOEncolar<void>('pedido.eliminar', { pedido_id: id }, {
      enLinea: async () => {
        await api.delete(`/pedido/${id}`);
      },
      optimista: async () => {
        await parchearCache('pedidos:', (lista) =>
          Array.isArray(lista) ? lista.filter((p: any) => p.id !== id) : undefined,
        );
        await borrarCache(`pedido:${id}`);
      },
    });
  },

  convertQuote: async (quoteId: number, body: ConvertQuoteBody): Promise<Order> => {
    const response = await api.post<Order>(`/pedido/convertir/${quoteId}`, body);
    return response.data;
  },
};
