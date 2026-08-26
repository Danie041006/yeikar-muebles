import api from './api';

export interface Area {
  id: number;
  nombre: string;
}

export interface NominaAreaConfig {
  id: number;
  area_id: number;
  porcentaje_aguinaldo: number;
  area?: Area;
}

export interface NominaLinea {
  id: number;
  detalle_id: number;
  origen: 'ETAPA' | 'MANUAL';
  etapa_id?: number | null;
  descripcion: string;
  area_id?: number | null;
  cliente_nombre?: string | null;
  cantidad: number;
  precio_unitario: number;
  total: number;
  area?: Area | null;
}

export interface ConceptoVario {
  id: number;
  descripcion: string;
  monto: number;
}

export interface NominaDetalle {
  id: number;
  nomina_id: number;
  empleado_id: number;
  empleado_nombre: string;
  cargo_nombre?: string | null;
  tipo_pago: 'DESTAJO' | 'FIJO';
  total_produccion: number;
  bono_aguinaldo: number;
  monto_a_pagar: number;
  metodo_caja_id?: number | null;
  metodo_caja_nombre?: string | null;
  gasto_id?: number | null;
  observaciones?: string | null;
  lineas: NominaLinea[];
}

export interface Nomina {
  id: number;
  periodo_desde: string;
  periodo_hasta: string;
  estado: 'BORRADOR' | 'PAGADA' | 'ANULADA';
  descripcion?: string | null;
  total_nomina: number;
  creador_nombre?: string | null;
  created_at?: string;
  detalles: NominaDetalle[];
  conceptos_varios: ConceptoVario[];
}

export interface LineaDraft {
  origen: 'ETAPA' | 'MANUAL';
  etapa_id?: number | null;
  descripcion: string;
  area_id?: number | null;
  area_nombre?: string | null;
  cliente_nombre?: string | null;
  cantidad: number;
  precio_unitario: number;
  total: number;
}

export interface DetalleDraft {
  empleado_id: number;
  empleado_nombre: string;
  cargo_nombre?: string | null;
  tipo_pago: 'DESTAJO' | 'FIJO';
  total_produccion: number;
  bono_aguinaldo: number;
  monto_a_pagar: number;
  lineas: LineaDraft[];
}

export interface NominaDraft {
  periodo_desde: string;
  periodo_hasta: string;
  detalles: DetalleDraft[];
  total_nomina: number;
}

export interface SaldoAguinaldo {
  empleado_id: number;
  empleado_nombre: string;
  cargo_nombre?: string | null;
  saldo_aguinaldo: number;
}

export interface PagoAguinaldo {
  empleado_id: number;
  empleado_nombre: string;
  monto: number;
  gasto_id: number;
  saldo_restante: number;
}

export interface EmpleadoNomina {
  id: number;
  nombre: string;
  cargo_id: number;
  activo: boolean;
  en_nomina: boolean;
  tipo_pago?: string | null;
  sueldo_semanal?: number | null;
  saldo_aguinaldo?: number | null;
  porcentaje_aguinaldo?: number | null;
  cargo?: { id: number; nombre: string } | null;
}

export const nominaService = {
  // Áreas (aguinaldo %)
  getAreaConfig: async (): Promise<NominaAreaConfig[]> => {
    const res = await api.get('/nomina/area-config');
    return res.data;
  },
  actualizarAreaConfig: async (areaId: number, porcentaje_aguinaldo: number): Promise<NominaAreaConfig> => {
    const res = await api.put(`/nomina/area-config/${areaId}`, { area_id: areaId, porcentaje_aguinaldo });
    return res.data;
  },

  // Nóminas
  generar: async (periodo_desde: string, periodo_hasta: string): Promise<NominaDraft> => {
    const res = await api.post('/nomina/generar', { periodo_desde, periodo_hasta });
    return res.data;
  },
  resumenSemanal: async (desde: string, hasta: string): Promise<ResumenSemanal> => {
    const res = await api.get<ResumenSemanal>('/nomina/resumen-semanal', { params: { desde, hasta } });
    return res.data;
  },
  crear: async (periodo_desde: string, periodo_hasta: string, descripcion?: string): Promise<Nomina> => {
    const res = await api.post('/nomina/', { periodo_desde, periodo_hasta, descripcion });
    return res.data;
  },
  listar: async (): Promise<Nomina[]> => {
    const res = await api.get('/nomina/');
    return res.data;
  },
  obtener: async (id: number): Promise<Nomina> => {
    const res = await api.get(`/nomina/${id}`);
    return res.data;
  },
  saldosAguinaldo: async (): Promise<SaldoAguinaldo[]> => {
    const res = await api.get('/nomina/saldos-aguinaldo');
    return res.data;
  },
  pagarAguinaldo: async (empleado_id: number, metodo_caja_id: number, observaciones?: string): Promise<PagoAguinaldo> => {
    const res = await api.post('/nomina/aguinaldo/pagar', { empleado_id, metodo_caja_id, observaciones });
    return res.data;
  },

  // Edición borrador
  actualizarDetalle: async (detalleId: number, data: { monto_a_pagar?: number; metodo_caja_id?: number | null; observaciones?: string }): Promise<NominaDetalle> => {
    const res = await api.put(`/nomina/detalle/${detalleId}`, data);
    return res.data;
  },
  agregarLinea: async (detalleId: number, data: { descripcion: string; cantidad: number; precio_unitario: number }): Promise<NominaLinea> => {
    const res = await api.post(`/nomina/detalle/${detalleId}/linea`, data);
    return res.data;
  },
  eliminarLinea: async (lineaId: number): Promise<void> => {
    await api.delete(`/nomina/linea/${lineaId}`);
  },
  agregarConceptoVario: async (nominaId: number, data: { descripcion: string; monto: number }): Promise<ConceptoVario> => {
    const res = await api.post(`/nomina/${nominaId}/concepto-vario`, data);
    return res.data;
  },
  eliminarConceptoVario: async (conceptoId: number): Promise<void> => {
    await api.delete(`/nomina/concepto-vario/${conceptoId}`);
  },

  // Pago / anulación
  pagar: async (nominaId: number): Promise<Nomina> => {
    const res = await api.post(`/nomina/${nominaId}/pagar`);
    return res.data;
  },
  anular: async (nominaId: number): Promise<Nomina> => {
    const res = await api.post(`/nomina/${nominaId}/anular`);
    return res.data;
  },
};

// ---------------- Producción de la semana (vista previa) ----------------
export interface PiezaSemana {
  producto: string;
  area: string | null;
  cliente: string | null;
  cantidad: number;
  precio_unitario: number | null;
  total: number | null;
  fecha_fin?: string | null;
}

export interface ManoObraSemana {
  total: number;
  pagado: number;
  pendiente: number;
  lineas: { descripcion: string; monto: number; pagado: boolean }[];
}

export interface EmpleadoSemana {
  empleado_id: number;
  nombre: string;
  cargo?: string | null;
  tipo_pago?: 'DESTAJO' | 'FIJO' | null;
  en_nomina: boolean;
  piezas: PiezaSemana[];
  piezas_sin_precio: number;
  total_destajo: number;
  aguinaldo_estimado: number;
  mano_obra: ManoObraSemana;
}

export interface ResumenSemanal {
  desde: string;
  hasta: string;
  empleados: EmpleadoSemana[];
}
