import api from './api';

// ─── Types ────────────────────────────────────────────────────────────────────

export interface LineaPedidoFacturable {
  // Id de la línea del pedido (detalle_pedido.id) — único por línea, aún con el mismo producto.
  detalle_pedido_id: number;
  nombre: string;
  cantidad: number;
  precio_referencia: number;
  moneda_codigo?: string;
}

export interface PedidoFacturable {
  pedido_id: number;
  cliente_id: number;
  cliente_nombre: string;
  fecha: string;
  estado: string;
  venta_id: number;
  total_venta: number;
  total_pagado: number;
  saldo_pendiente: number;
  venta_estado: string;
  venta_moneda_codigo?: string;
  lineas: LineaPedidoFacturable[];
}

export interface ClienteInfo {
  id: number;
  nombre: string;
  telefono?: string;
  direccion?: string;
}

export interface ProductoInfo {
  id: number;
  nombre: string;
}

export interface DetalleFactura {
  id: number;
  factura_id: number;
  producto_id: number;
  descripcion?: string;
  cantidad: number;
  precio_usd: number;
  subtotal_usd: number;
  subtotal_bs: number;
  producto?: ProductoInfo;
}

export interface Factura {
  id: number;
  pedido_id: number;
  cliente_id: number;
  fecha_emision: string;
  total_usd: number;
  tasa_usd_ves: number;
  base_imponible_bs: number;
  iva_bs: number;
  igtf_bs: number;
  total_bs: number;
  estado: 'EMITIDA' | 'ANULADA';
  observaciones?: string;
  creador_nombre?: string;
  created_at?: string;
  cliente?: ClienteInfo;
}

export interface FacturaDetalle extends Factura {
  detalles: DetalleFactura[];
}

export interface FacturaCreate {
  pedido_id: number;
  tasa_usd_ves: number;
  fecha_emision?: string;
  lineas: { detalle_pedido_id: number; precio_usd: number }[];
  observaciones?: string;
  permitir_saldo_pendiente?: boolean;
}

export interface TasaImpuesto {
  clave: string;
  nombre: string;
  tasa: number;
  vigente: boolean;
}

// ─── Service ──────────────────────────────────────────────────────────────────

export const facturacionService = {
  /** Listar facturas emitidas */
  getAll: async (): Promise<Factura[]> => {
    const res = await api.get<Factura[]>('/factura/');
    return res.data;
  },

  /** Detalle de una factura con sus líneas */
  getById: async (id: number): Promise<FacturaDetalle> => {
    const res = await api.get<FacturaDetalle>(`/factura/${id}`);
    return res.data;
  },

  /** Pedidos sin factura (pueden tener saldo pendiente) */
  getPedidosFacturables: async (): Promise<PedidoFacturable[]> => {
    const res = await api.get<PedidoFacturable[]>('/factura/pedidos-facturables/');
    return res.data;
  },

  /** Emitir factura de un pedido (montos en USD decididos por la dueña) */
  crear: async (data: FacturaCreate): Promise<Factura> => {
    const res = await api.post<Factura>('/factura/', data);
    return res.data;
  },

  /** Anular una factura */
  anular: async (id: number): Promise<Factura> => {
    const res = await api.post<Factura>(`/factura/${id}/anular`);
    return res.data;
  },

  /** Tasas de impuestos configurables */
  getTasas: async (): Promise<TasaImpuesto[]> => {
    const res = await api.get<TasaImpuesto[]>('/factura/tasas/');
    return res.data;
  },

  /** Actualizar tasa de impuesto (IVA/IGTF) — solo admin */
  actualizarTasa: async (clave: string, tasa: number): Promise<TasaImpuesto> => {
    const res = await api.put<TasaImpuesto>(`/factura/tasas/${clave}`, { tasa });
    return res.data;
  },
};
