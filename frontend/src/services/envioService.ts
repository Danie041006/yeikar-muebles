import api from './api';
import { Order } from './pedidoService';
import { Empleado } from './produccionService';
import type { Moneda } from './cotizacionService';
export interface EnvioDetalle {
  id: number;
  detalle_pedido_id: number;
  orden_produccion_id?: number | null;
  cantidad: number;
  descripcion?: string | null;
  pieza_nombre?: string | null;
  tipo_item?: string | null;
  producto_id?: number | null;
  material_id?: number | null;
}

export interface EnvioDetalleCreate {
  detalle_pedido_id: number;
  orden_produccion_id?: number | null;
  cantidad: number;
}

export interface PendienteEntregaItem {
  detalle_pedido_id: number;
  orden_produccion_id?: number | null;
  pieza_nombre?: string | null;
  descripcion: string;
  tipo_item?: string | null;
  cantidad_total: number;
  cantidad_entregada: number;
  cantidad_reservada: number;
  cantidad_pendiente: number;
  /** Parte que ya salió de producción y se puede despachar en este viaje. */
  cantidad_lista: number;
  estado_produccion?: string | null;
}

export interface PendienteEntrega {
  pedido_id: number;
  estado: string;
  items: PendienteEntregaItem[];
}

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
  costo_flete?: number | null;
  moneda_flete_id?: number | null;
  tasa_cambio_flete?: number | null;
  costo_flete_en_moneda_base?: number | null;
  created_at?: string;
  updated_at?: string;
  creado_por_id?: number | null;
  actualizado_por_id?: number | null;
  asignado_por_usuario_id?: number | null;
  creador_nombre?: string | null;
  asignado_por_nombre?: string | null;
  pedido?: Order;
  empleado?: Empleado | null;
  moneda_flete?: Moneda | null;
  detalles?: EnvioDetalle[];
}

export interface EnvioCreate {
  pedido_id: number;
  estado?: 'PREPARADO' | 'EN_TRANSITO' | 'ENTREGADO' | 'FALLIDO';
  empleado_id?: number | null;
  direccion_entrega?: string | null;
  guia_despacho?: string | null;
  observaciones?: string | null;
  fecha_entrega?: string | null;
  costo_flete?: number | null;
  moneda_flete_id?: number | null;
  tasa_cambio_flete?: number | null;
  detalles?: EnvioDetalleCreate[];
}

export interface EnvioUbicacion {
  id: number;
  envio_id: number;
  empleado_id?: number | null;
  reportado_por_id?: number | null;
  reportado_por_nombre?: string | null;
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
  costo_flete?: number | null;
  moneda_flete_id?: number | null;
  tasa_cambio_flete?: number | null;
}

export interface ClienteReparto {
  id: number;
  nombre: string;
  telefono?: string | null;
  direccion?: string | null;
  ciudad?: string | null;
}

export interface ProductoReparto {
  id: number;
  nombre?: string | null;
}

export interface MaterialReparto {
  id: number;
  nombre?: string | null;
}

export interface DetallePedidoReparto {
  id: number;
  pedido_id: number;
  /** INSUMO vendido suelto: producto_id null, material_id presente. */
  producto_id?: number | null;
  material_id?: number | null;
  tipo_item?: 'FABRICADO' | 'REVENTA' | 'INSUMO' | 'REPARACION' | 'SERVICIO';
  cantidad: number;
  alto?: number | null;
  ancho?: number | null;
  largo?: number | null;
  color?: string | null;
  acabado?: string | null;
  descripcion_especifica?: string | null;
  observaciones?: string | null;
  producto?: ProductoReparto | null;
  material?: MaterialReparto | null;
}

export interface PedidoReparto {
  id: number;
  cliente_id: number;
  fecha?: string | null;
  estado: string;
  fecha_entrega_estimada?: string | null;
  cliente?: ClienteReparto | null;
  detalles: DetallePedidoReparto[];
}

export interface EnvioReparto {
  id: number;
  pedido_id: number;
  empleado_id?: number | null;
  fecha_salida?: string | null;
  fecha_entrega?: string | null;
  estado: 'PREPARADO' | 'EN_TRANSITO' | 'ENTREGADO' | 'FALLIDO';
  direccion_entrega?: string | null;
  guia_despacho?: string | null;
  observaciones?: string | null;
  pedido?: PedidoReparto | null;
  detalles?: EnvioDetalle[];
}
export interface ListarEnviosParams {
  buscar?: string;
  estado?: string;
  /** Varios estados a la vez (se envían como CSV al backend). */
  estados?: string[];
  /** Solo los despachos de un pedido (entrega parcial). */
  pedido_id?: number;
  salto?: number;
  limite?: number;
}

export const envioService = {
  /** Listar envíos (paginado + búsqueda server-side). Devuelve el total vía X-Total-Count. */
  getAll: async (params: ListarEnviosParams = {}): Promise<{ items: Envio[]; total: number }> => {
    const response = await api.get<Envio[]>('/envio/', {
      params: {
        ...(params.buscar ? { buscar: params.buscar } : {}),
        ...(params.estado ? { estado: params.estado } : {}),
        ...(params.estados?.length ? { estados: params.estados.join(',') } : {}),
        ...(params.pedido_id !== undefined ? { pedido_id: params.pedido_id } : {}),
        salto: params.salto ?? 0,
        limite: params.limite ?? 100,
      },
    });
    return { items: response.data, total: Number(response.headers['x-total-count']) || response.data.length };
  },
  getById: async (id: number): Promise<Envio> => {
    const response = await api.get<Envio>(`/envio/${id}`);
    return response.data;
  },
  getPendientes: async (pedidoId: number): Promise<PendienteEntrega> => {
    const response = await api.get<PendienteEntrega>(`/envio/pendientes/${pedidoId}`);
    return response.data;
  },
  create: async (data: EnvioCreate): Promise<Envio> => {
    const response = await api.post<Envio>('/envio/', data);
    return response.data;
  },
  getMisAsignaciones: async (estado?: string): Promise<EnvioReparto[]> => {
    const response = await api.get<EnvioReparto[]>('/envio/mis-asignaciones', {
      params: estado ? { estado } : undefined,
    });
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
