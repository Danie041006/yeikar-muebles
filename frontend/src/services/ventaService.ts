import api from './api';

// ─── Types ────────────────────────────────────────────────────────────────────

export interface MonedaInfo {
  id: number;
  nombre: string;
  codigo: string;
  simbolo: string;
}

export interface ClienteInfo {
  id: number;
  nombre: string;
}

export interface ProductoInfo {
  id: number;
  nombre: string;
}

export interface DetalleVenta {
  id: number;
  venta_id: number;
  producto_id: number;
  cantidad: number;
  precio: number;
  producto?: ProductoInfo;
}

export interface Pago {
  id: number;
  venta_id: number;
  moneda_id: number;
  fecha: string;
  monto: number;
  metodo_pago: string;
  referencia?: string;
  observaciones?: string;
  moneda?: MonedaInfo;
}

export interface Venta {
  id: number;
  pedido_id: number;
  cliente_id: number;
  moneda_id: number;
  fecha: string;
  total: number;
  estado: 'PENDIENTE' | 'ABONADA' | 'PAGADA' | 'CANCELADA';
  observaciones?: string;
  cliente?: ClienteInfo;
  moneda?: MonedaInfo;
}

export interface VentaDetalle extends Venta {
  detalles: DetalleVenta[];
  pagos: Pago[];
  total_pagado: number;
  saldo_pendiente: number;
}

export interface CuentaPorCobrar {
  venta_id: number;
  cliente_nombre: string;
  fecha: string;
  total: number;
  total_pagado: number;
  saldo_pendiente: number;
  moneda_codigo: string;
}

export interface VentaCreate {
  pedido_id: number;
  moneda_id: number;
  fecha?: string;
  observaciones?: string;
}

export interface PagoCreate {
  venta_id: number;
  moneda_id: number;
  fecha: string;
  monto: number;
  metodo_pago: string;
  referencia?: string;
  observaciones?: string;
}

// Métodos de pago disponibles
export const METODOS_PAGO = [
  { value: 'EFECTIVO_COP', label: 'Efectivo COP 🇨🇴', moneda: 'COP' },
  { value: 'EFECTIVO_USD', label: 'Efectivo USD 🇺🇸', moneda: 'USD' },
  { value: 'EFECTIVO_VES', label: 'Efectivo Bs 🇻🇪', moneda: 'VES' },
  { value: 'BANCOLOMBIA', label: 'Bancolombia', moneda: 'COP' },
  { value: 'BANCARIBE', label: 'Bancaribe', moneda: 'VES' },
  { value: 'ZELLE', label: 'Zelle', moneda: 'USD' },
] as const;

// ─── Service ──────────────────────────────────────────────────────────────────

export const ventaService = {
  /** Listar todas las ventas */
  getAll: async (params?: { buscar?: string; salto?: number; limite?: number }): Promise<Venta[]> => {
    const res = await api.get<Venta[]>('/venta/', { params });
    return res.data;
  },

  /** Detalle de una venta con pagos */
  getById: async (id: number): Promise<VentaDetalle> => {
    const res = await api.get<VentaDetalle>(`/venta/${id}`);
    return res.data;
  },

  /** Crear factura desde un pedido */
  create: async (data: VentaCreate): Promise<Venta> => {
    const res = await api.post<Venta>('/venta/', data);
    return res.data;
  },

  /** Cuentas por cobrar (ventas PENDIENTE o ABONADA) */
  getCuentasPorCobrar: async (): Promise<CuentaPorCobrar[]> => {
    const res = await api.get<CuentaPorCobrar[]>('/venta/cuentas-por-cobrar/');
    return res.data;
  },

  /** Eliminar una venta (solo si no tiene pagos) */
  delete: async (id: number): Promise<void> => {
    await api.delete(`/venta/${id}`);
  },
};

export const pagoService = {
  /** Registrar un abono/pago */
  registrar: async (data: PagoCreate): Promise<Pago> => {
    const res = await api.post<Pago>('/pago/', data);
    return res.data;
  },
};
