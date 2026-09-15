import api from './api';
import type { AdjuntoInfo } from './adjuntosService';

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
  telefono?: string;
  direccion?: string;
}

export interface ProductoInfo {
  id: number;
  nombre: string;
  /** Fotos de referencia del producto (adjuntos tipo PRODUCTO). */
  fotos?: { url?: string }[];
}

export interface DetalleVenta {
  id: number;
  venta_id: number;
  producto_id?: number | null;
  material_id?: number | null;
  tipo_item?: 'FABRICADO' | 'REVENTA' | 'INSUMO';
  cantidad: number;
  precio: number;
  costo_unitario?: number;
  utilidad?: number;
  /** Descripción del ítem cuando no hay producto ni material (a medida). */
  descripcion_especifica?: string | null;
  producto?: ProductoInfo;
  material?: { id: number; nombre: string; costo_base: number; unidad_medida?: { abreviatura: string } };
}

export interface Pago {
  id: number;
  venta_id: number;
  moneda_id: number;
  fecha: string;
  monto: number;
  tasa_cambio: number;
  monto_en_moneda_base: number;
  metodo_pago: string;
  referencia?: string;
  observaciones?: string;
  moneda?: MonedaInfo;
  /** Comprobantes digitales del pago (recibos). */
  recibos?: AdjuntoInfo[];
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
  // Estado del pedido vinculado (ENTREGADO = ya recibido por el cliente):
  // la página de cobros agrupa entregados vs. en proceso con este campo.
  pedido_estado?: string | null;
}

export interface VentaDetalle extends Venta {
  detalles: DetalleVenta[];
  pagos: Pago[];
  descuentos: Descuento[];
  total_pagado: number;
  total_descontado: number;
  saldo_pendiente: number;
  total_en_moneda_base?: number;
  tasa_cambio?: number;
}

export interface CuentaPorCobrar {
  venta_id: number;
  pedido_id: number;
  cliente_nombre: string;
  fecha: string;
  total: number;
  total_pagado: number;
  total_descontado: number;
  saldo_pendiente: number;
  moneda_codigo: string;
  pedido_estado?: string | null;
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
  /** TRM / tasa de conversión. Requerido cuando moneda_id difiere de la moneda de la venta. */
  tasa_cambio?: number;
}

// ─── Descuento de cobro ───────────────────────────────────────────────────────
// Rebaja otorgada al cobrar: resta del saldo igual que un pago pero NO mueve
// dinero a ninguna cuenta de caja.
export interface Descuento {
  id: number;
  venta_id: number;
  moneda_id: number;
  fecha: string;
  monto: number;
  tasa_cambio: number;
  monto_en_moneda_base: number;
  motivo?: string | null;
  observaciones?: string | null;
  moneda?: MonedaInfo;
}

export interface DescuentoCreate {
  venta_id: number;
  moneda_id: number;
  fecha: string;
  monto: number;
  motivo?: string;
  observaciones?: string;
  /** TRM / tasa de conversión. Requerido cuando moneda_id difiere de la moneda de la venta. */
  tasa_cambio?: number;
}

// Métodos de pago disponibles (FALLBACK estático: solo para labels de pagos
// históricos y el PDF cuando la carga dinámica falla. La fuente de verdad son
// las cuentas de metodo_caja vía cargarMetodosPago()).
export const METODOS_PAGO = [
  { value: 'EFECTIVO_COP', label: 'Efectivo COP', moneda: 'COP' },
  { value: 'EFECTIVO_USD', label: 'Efectivo USD', moneda: 'USD' },
  { value: 'EFECTIVO_VES', label: 'Efectivo Bs', moneda: 'VES' },
  { value: 'BANCOLOMBIA', label: 'Bancolombia', moneda: 'COP' },
  { value: 'BANCARIBE', label: 'Bancaribe', moneda: 'VES' },
  { value: 'ZELLE', label: 'Zelle', moneda: 'USD' },
  { value: 'BINANCE', label: 'Binance', moneda: 'USD' },
  { value: 'NEQUI', label: 'Nequi', moneda: 'COP' },
  { value: 'SOFITASA', label: 'Sofitasa', moneda: 'COP' },
  { value: 'BANESCO', label: 'Banesco', moneda: 'COP' },
] as const;

export type MetodoPagoOption = { value: string; label: string; moneda: string };

// Carga las cuentas reales de metodo_caja (activas) desde el backend:
// value = codigo de la cuenta (el backend mapea metodo_pago → codigo),
// label = nombre de la cuenta, moneda = moneda propia de la cuenta.
export const cargarMetodosPago = async (): Promise<MetodoPagoOption[]> => {
  const res = await api.get<{ id: number; nombre: string; codigo: string; activo: boolean; moneda_codigo?: string | null }[]>('/reports/metodos-caja');
  return res.data
    .filter((m) => m.activo)
    .map((m) => ({
      value: m.codigo,
      label: m.nombre,
      moneda: m.moneda_codigo || 'COP',
    }));
};

// Label de un método de pago (históricos): lista dinámica con fallback estático.
export const labelMetodoPago = (metodos: MetodoPagoOption[] | undefined, valor: string | null | undefined): string => {
  if (!valor) return '—';
  return (
    metodos?.find((m) => m.value === valor)?.label ??
    METODOS_PAGO.find((m) => m.value === valor)?.label ??
    valor
  );
};

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

export const descuentoService = {
  /** Registrar una rebaja al cobrar (resta del saldo, sin mover caja) */
  registrar: async (data: DescuentoCreate): Promise<Descuento> => {
    const res = await api.post<Descuento>('/pago/descuento/', data);
    return res.data;
  },

  /** Anular un descuento (el saldo vuelve a subir) */
  anular: async (id: number): Promise<void> => {
    await api.delete(`/pago/descuento/${id}`);
  },
};
