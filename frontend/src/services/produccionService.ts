import api from './api';
export interface Area {
  id: number;
  nombre: string;
}

export interface Empleado {
  id: number;
  nombre: string;
  apellido: string;
  cedula: string;
  email?: string;
  telefono?: string;
  activo?: boolean;
  cargo?: {
    id: number;
    nombre: string;
  };
}

export interface Material {
  id: number;
  nombre: string;
  costo_base: number;
  unidad_medida?: {
    id: number;
    nombre: string;
    abreviatura: string;
  };
}

export interface ConsumoMaterial {
  id: number;
  etapa_produccion_id: number;
  material_id: number;
  cantidad: number;
  costo_unitario?: number;
  fecha: string;
  observaciones?: string;
  material?: Material;
}

export interface ManoObra {
  id: number;
  etapa_produccion_id: number;
  empleado_id: number;
  monto: number;
  porcentaje_recargo: number;
  pagado?: boolean;
  observaciones?: string;
  empleado?: Empleado;
}

export interface AsignadoAdicional {
  id: number;
  etapa_produccion_id: number;
  empleado_id: number;
  empleado?: Empleado;
}

export interface EtapaProduccion {
  id: number;
  orden_produccion_id: number;
  area_id: number;
  empleado_responsable_id: number;
  estado: 'ASIGNADA' | 'EN_PROCESO' | 'PAUSADA' | 'COMPLETADA';
  observaciones?: string;
  fecha_inicio?: string;
  fecha_fin?: string;
  area?: Area;
  empleado_responsable?: Empleado;
  consumos: ConsumoMaterial[];
  mano_obras: ManoObra[];
  asignados_adicionales: AsignadoAdicional[];
  orden?: OrdenProduccion;
}

export interface CostoProduccion {
  id: number;
  orden_produccion_id: number;
  costo_material: number;
  costo_mano_obra: number;
  costo_gastos: number;
  precio_impuestos_base: number;
  ganancia_porcentaje: number;
  precio_venta_calculado: number;
  costo_total: number;
}

export interface OrdenProduccion {
  id: number;
  detalle_pedido_id: number;
  detalle_pedido?:DetallePedidoBasico;
  estado: 'PENDIENTE' | 'EN_PRODUCCION' | 'PAUSADA' | 'FINALIZADA' | 'CANCELADA';
  fecha_inicio?: string;
  fecha_fin?: string;
  etapas: EtapaProduccion[];
  costo?: CostoProduccion;
  // Detalle del producto (opcional, para visualización)
  producto_nombre?: string;
}

export interface ProductoBasico {
  id: number;
  nombre: string;
  codigo?: string;
  descripcion?: string;
  activo?: boolean;
}

export interface ClienteBasico {
  id: number;
  nombre: string;
  telefono?: string;
}

export interface PedidoBasico {
  id: number;
  cliente?: ClienteBasico;
}

export interface DetallePedidoBasico {
  id: number;
  ancho?: number;
  largo?: number;
  producto?: ProductoBasico;
  pedido?: PedidoBasico;
}

export interface MaterialReferencia {
  material_id: number;
  nombre: string;
  seccion: string;
  cantidad_base: number;
  cantidad_esperada: number;
  unidad: string;
  costo_unitario: number;
}

export interface ReferenciaReceta {
  producto_id: number;
  producto_nombre: string;
  dimensiones: { ancho: number | null; largo: number | null };
  materiales: MaterialReferencia[];
}

export const produccionService = {
  getOrdenes: async (buscar?: string): Promise<OrdenProduccion[]> => {
    const response = await api.get<OrdenProduccion[]>('/produccion/orden/', {
      params: buscar ? { buscar } : {},
    });
    return response.data;
  },

  getOrdenById: async (id: number): Promise<OrdenProduccion> => {
    const response = await api.get<OrdenProduccion>(`/produccion/orden/${id}`);
    return response.data;
  },

  getAreas: async (): Promise<Area[]> => {
    const response = await api.get<Area[]>('/catalogos/area/');
    return response.data;
  },

  getReferenciaReceta: async (etapaId: number): Promise<ReferenciaReceta> => {
    const response = await api.get<ReferenciaReceta>(`/produccion/etapa/${etapaId}/referencia-receta`);
    return response.data;
  },

  updateEstadoEtapa: async (id: number, estado: string): Promise<EtapaProduccion> => {
    const response = await api.put<EtapaProduccion>(`/produccion/etapa/${id}/estado`, null, {
      params: { estado },
    });
    return response.data;
  },

  pasarAArea: async (
    etapaId: number,
    payload: {
      area_id: number;
      empleado_responsable_id: number;
      empleados_adicionales_ids: number[];
      observaciones?: string;
    },
  ): Promise<EtapaProduccion> => {
    const response = await api.post<EtapaProduccion>(
      `/produccion/etapa/${etapaId}/pasar-a-area`,
      payload,
    );
    return response.data;
  },

  agregarAsignadoAdicional: async (etapaId: number, empleadoId: number): Promise<AsignadoAdicional> => {
    const response = await api.post<AsignadoAdicional>(`/produccion/etapa/${etapaId}/asignados`, {
      empleado_id: empleadoId,
    });
    return response.data;
  },

  quitarAsignadoAdicional: async (etapaId: number, empleadoId: number): Promise<void> => {
    await api.delete(`/produccion/etapa/${etapaId}/asignados/${empleadoId}`);
  },

  registrarConsumo: async (consumo: {
    etapa_produccion_id: number;
    material_id: number;
    cantidad: number;
    fecha: string;
    observaciones?: string;
  }): Promise<ConsumoMaterial> => {
    const response = await api.post<ConsumoMaterial>('/produccion/consumo/', consumo);
    return response.data;
  },

  eliminarConsumo: async (id: number): Promise<void> => {
    await api.delete(`/produccion/consumo/${id}`);
  },

  registrarManoObra: async (manoObra: {
    etapa_produccion_id: number;
    empleado_id: number;
    monto: number;
    porcentaje_recargo?: number;
    observaciones?: string;
  }): Promise<ManoObra> => {
    const response = await api.post<ManoObra>('/produccion/mano-obra/', manoObra);
    return response.data;
  },

  eliminarManoObra: async (id: number): Promise<void> => {
    await api.delete(`/produccion/mano-obra/${id}`);
  },

  marcarManoObraPagada: async (id: number, pagado: boolean): Promise<ManoObra> => {
    const response = await api.put<ManoObra>(`/produccion/mano-obra/${id}/pagar`, null, {
      params: { pagado },
    });
    return response.data;
  },
};
