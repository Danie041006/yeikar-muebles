import api from './api';

export interface Proveedor {
  id: number;
  nombre: string;
  telefono?: string | null;
  email?: string | null;
  direccion?: string | null;
}

export interface Abono {
  id: number;
  fecha: string;
  monto: number;
  metodo_caja_id: number;
  metodo_caja_nombre?: string | null;
  tasa_cambio: number;
  monto_en_moneda_base: number;
  creado_por_id?: number | null;
  created_at: string;
}

export interface DetalleCuentaPorPagar {
  id: number;
  orden: number;
  descripcion?: string | null;
  material_id?: number | null;
  material?: { id: number; nombre: string } | null;
  cantidad: number;
  precio_unitario: number;
  cliente_nombre?: string | null;
  cliente_id?: number | null;
  cliente?: { id: number; nombre: string } | null;
  observaciones?: string | null;
  total: number;
}

export interface CuentaPorPagar {
  id: number;
  proveedor_id: number;
  gasto_id?: number | null;
  tipo_gasto_id: number;
  moneda_id: number;
  fecha: string;
  descripcion?: string | null;
  monto: number;
  tasa_cambio: number;
  monto_en_moneda_base: number;
  monto_pagado: number;
  saldo: number;
  estado: 'PENDIENTE' | 'PAGADA';
  origen_tipo?: string | null;
  origen_id?: number | null;
  creado_por_id?: number | null;
  created_at: string;
  updated_at?: string | null;
  proveedor?: Proveedor | null;
  moneda?: { id: number; codigo: string; simbolo: string; nombre: string } | null;
  tipo_gasto?: { id: number; nombre: string; categoria: string } | null;
  detalles?: DetalleCuentaPorPagar[];
  pagos?: Abono[];
}

export interface DetalleCuentaPorPagarCreate {
  descripcion?: string | null;
  material_id?: number | null;
  cantidad: number;
  precio_unitario: number;
  cliente_nombre?: string | null;
  cliente_id?: number | null;
  observaciones?: string | null;
}

export interface CuentaPorPagarCreate {
  proveedor_id: number;
  tipo_gasto_id: number;
  moneda_id?: number;
  fecha: string;
  descripcion?: string | null;
  monto: number;
  tasa_cambio?: number;
  detalles?: DetalleCuentaPorPagarCreate[];
}

export interface AbonoCreate {
  fecha: string;
  monto: number;
  metodo_caja_id: number;
  tasa_cambio?: number;
}

export interface LineaSaldoProveedor {
  proveedor_id: number;
  proveedor_nombre: string;
  saldo: number;
}

export interface ResumenCuentasPorPagar {
  total_pendiente: number;
  total_pagado: number;
  total_deudas: number;
  por_proveedor: LineaSaldoProveedor[];
}

export const cuentasPorPagarService = {
  getAll: async (params?: { estado?: string; proveedor_id?: number }): Promise<CuentaPorPagar[]> => {
    const response = await api.get<CuentaPorPagar[]>('/cuentas-por-pagar/', { params });
    return response.data;
  },

  getResumen: async (): Promise<ResumenCuentasPorPagar> => {
    const response = await api.get<ResumenCuentasPorPagar>('/cuentas-por-pagar/resumen');
    return response.data;
  },

  create: async (datos: CuentaPorPagarCreate): Promise<CuentaPorPagar> => {
    const response = await api.post<CuentaPorPagar>('/cuentas-por-pagar/', datos);
    return response.data;
  },

  abonar: async (cxpId: number, abono: AbonoCreate): Promise<Abono> => {
    const response = await api.post<Abono>(`/cuentas-por-pagar/${cxpId}/abonos`, abono);
    return response.data;
  },

  eliminarAbono: async (abonoId: number): Promise<void> => {
    await api.delete(`/cuentas-por-pagar/abonos/${abonoId}`);
  },

  eliminar: async (cxpId: number): Promise<void> => {
    await api.delete(`/cuentas-por-pagar/${cxpId}`);
  },

  getProveedores: async (): Promise<Proveedor[]> => {
    const response = await api.get<Proveedor[]>('/proveedor/');
    return response.data;
  },
};