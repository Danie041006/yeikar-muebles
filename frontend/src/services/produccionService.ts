import api from './api';
export interface Area {
  id: number;
  nombre: string;
}

export interface Empleado {
  id: number;
  nombre: string;
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
  // Dimensiones de la lámina completa (cm) si el material es laminar
  largo_cm?: number | null;
  ancho_cm?: number | null;
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
  seccion?: string;
  /** PENDIENTE = pedido sin confirmar uso (lámina o general); CONFIRMADO = costo final. */
  estado?: 'PENDIENTE' | 'CONFIRMADO';
  /** Lo que se ENTREGÓ al pedir (unidad base). NULL = uso directo sin pedido. */
  cantidad_pedida?: number | null;
  // --- Captura flexible de madera (cantidad ya está en la unidad base) ---
  unidad_captura?: 'M' | 'CM' | null;
  pieza_largo?: number | null;
  pieza_ancho?: number | null;
  pieza_espesor?: number | null;
  // --- Componente y consumo extra (estructura de costes desde producción) ---
  componente?: string | null;
  es_excedente?: boolean;
  motivo_exceso?: string | null;
  // --- Consumo por corte (materiales laminares) ---
  ancho_corte_cm?: number | null;
  largo_corte_cm?: number | null;
  origen_sobrante_id?: number | null;
  laminas_consumidas?: number | null;
  solicitante_empleado_id?: number;
  solicitante_nombre?: string;
  creado_por_id?: number;
  creador_nombre?: string;
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
  listo_nomina?: boolean;
  observaciones?: string;
  precio_produccion_id?: number | null;
  precio_produccion_descripcion?: string | null;
  creado_por_id?: number;
  creador_nombre?: string;
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
  empleado_responsable_id: number | null;
  estado: 'ASIGNADA' | 'EN_PROCESO' | 'PAUSADA' | 'COMPLETADA';
  es_retrabajo?: boolean;
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
  costo_estimado?: number | null;
}

export interface OrdenProduccion {
  id: number;
  detalle_pedido_id: number | null;
  producto_id?: number | null;
  detalle_pedido?:DetallePedidoBasico;
  producto?: ProductoBasico;
  es_stock?: boolean;
  /** Destino de lo fabricado: PEDIDO | EXHIBICION | STOCK. */
  tipo?: 'PEDIDO' | 'EXHIBICION' | 'STOCK';
  estado: 'PENDIENTE' | 'EN_PRODUCCION' | 'PAUSADA' | 'FINALIZADA' | 'CANCELADA';
  creado_por_id?: number | null;
  creador_nombre?: string | null;
  fecha_inicio?: string;
  fecha_fin?: string;
  ancho?: number;
  largo?: number;
  alto?: number;
  etapas: EtapaProduccion[];
  costo?: CostoProduccion;
  // True si al finalizar se generó la estructura de costes del producto.
  estructura_generada?: boolean | null;
  // Detalle del producto (opcional, para visualización)
  producto_nombre?: string;
}

export interface ProductoBasico {
  id: number;
  nombre: string;
  codigo?: string;
  descripcion?: string;
  activo?: boolean;
  /** True = se revende (colchón, nevera): nunca entra a producción. */
  es_reventa?: boolean;
  /** True = pieza de exhibición (se fabrica una vez, se vende del stock). */
  es_exhibicion?: boolean;
}

export interface ClienteBasico {
  id: number;
  nombre: string;
  telefono?: string;
}

export interface PedidoBasico {
  id: number;
  cliente?: ClienteBasico;
  fecha_entrega_estimada?: string;
}

export interface DetallePedidoBasico {
  id: number;
  cantidad?: number;
  ancho?: number;
  largo?: number;
  producto?: ProductoBasico;
  pedido?: PedidoBasico;
}

export interface MaterialReferencia {
  material_id: number;
  nombre: string;
  seccion: string;
  tipo_escala: string;
  condicion_cumplida: boolean;
  cantidad_base: number;
  cantidad_esperada: number;
  unidad: string;
  costo_unitario: number;
  // Solo para tipo_escala=CORTE (materiales laminares)
  es_corte?: boolean;
  ancho_corte_cm?: number;
  largo_corte_cm?: number;
  cortes_por_lamina?: number;
  laminas_equivalentes?: number;
  costo_por_corte?: number;
}

export interface FotoReferencia {
  url: string;
  nombre?: string | null;
}

export interface ReferenciaReceta {
  producto_id: number;
  producto_nombre: string;
  dimensiones: { ancho: number | null; largo: number | null };
  seccion_actual?: string | null;
  materiales: MaterialReferencia[];
  // ── Contexto para la Hoja de Trabajo (documento del taller, sin montos) ──
  orden_id?: number | null;
  pedido_id?: number | null;
  area_nombre?: string | null;
  etapa_id?: number | null;
  etapa_observaciones?: string | null;
  color?: string | null;
  acabado?: string | null;
  descripcion_especifica?: string | null;
  observaciones_detalle?: string | null;
  observaciones_pedido?: string | null;
  cliente_nombre?: string | null;
  cliente_telefono?: string | null;
  fecha_entrega_estimada?: string | null;
  cantidad?: number | null;
  producto_fotos?: FotoReferencia[];
}

export const produccionService = {
  getOrdenes: async (buscar?: string, salto = 0, limite = 100): Promise<OrdenProduccion[]> => {
    const response = await api.get<OrdenProduccion[]>('/produccion/orden/', {
      params: { buscar, salto, limite },
    });
    return response.data;
  },

  getOrdenById: async (id: number): Promise<OrdenProduccion> => {
    const response = await api.get<OrdenProduccion>(`/produccion/orden/${id}`);
    return response.data;
  },

  /** Crea una orden de producción. Con es_stock=true y producto_id fabrica
   *  una pieza de exhibición sin pedido (al finalizar entra al showroom). */
  crearOrden: async (payload: {
    estado: string;
    es_stock?: boolean;
    producto_id?: number;
    detalle_pedido_id?: number;
    fecha_inicio?: string;
  }): Promise<OrdenProduccion> => {
    const response = await api.post<OrdenProduccion>('/produccion/orden/', payload);
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
    /** Número digitado por el operario (en modo pieza: N.º de piezas). */
    cantidad: number;
    fecha: string;
    seccion?: string;
    observaciones?: string;
    solicitante_empleado_id: number;
    // --- Captura flexible: el backend convierte a la unidad base ---
    unidad_captura?: 'M' | 'CM';
    pieza_largo?: number;
    pieza_ancho?: number;
    pieza_espesor?: number;
    // --- Componente y consumo extra ---
    componente?: string;
    es_excedente?: boolean;
    motivo_exceso?: string;
    // --- Pedido de LÁMINA COMPLETA (confirmar uso después) ---
    // True + material laminar: `cantidad` = N.º de láminas enteras que salen
    // hoy; el consumo queda PENDIENTE hasta confirmar los cortes reales.
    es_lamina_completa?: boolean;
    // --- PEDIDO general (madera y demás: confirmar uso después) ---
    // True: `cantidad` = cantidad ENTREGADA hoy (sale del depósito con costo
    // provisional); el consumo queda PENDIENTE hasta confirmar cuánto se usó.
    // Híbrido: si es False se registra el uso directo (CONFIRMADO inmediato).
    es_pedido?: boolean;
    // --- Consumo por corte (materiales laminares) ---
    ancho_corte_cm?: number;
    largo_corte_cm?: number;
    origen_sobrante_id?: number;
    sobrante_largo_cm?: number;
    sobrante_ancho_cm?: number;
  }): Promise<ConsumoMaterial> => {
    const response = await api.post<ConsumoMaterial>('/produccion/consumo/', consumo);
    return response.data;
  },

  /** Confirma el uso real de un pedido (PENDIENTE → CONFIRMADO).
   *  Dos modos excluyentes: por cortes (láminas) o por cantidad usada
   *  en la unidad base del material (madera y demás). */
  confirmarConsumo: async (
    id: number,
    payload: {
      cantidad_cortes?: number;
      largo_corte_cm?: number;
      ancho_corte_cm?: number;
      sobrante_largo_cm?: number;
      sobrante_ancho_cm?: number;
      cantidad_usada?: number;
    },
  ): Promise<ConsumoMaterial> => {
    const response = await api.put<ConsumoMaterial>(`/produccion/consumo/${id}/confirmar`, payload);
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
    precio_produccion_id?: number;
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

  alternarListoNomina: async (id: number, listo: boolean): Promise<ManoObra> => {
    const response = await api.put<ManoObra>(`/produccion/mano-obra/${id}/listo-nomina`, null, {
      params: { listo },
    });
    return response.data;
  },
  getCostosEnVivo: async (ordenId: number): Promise<CostosEnVivoOrden> => {
    const response = await api.get<CostosEnVivoOrden>(`/produccion/orden/${ordenId}/costos-en-vivo`);
    return response.data;
  },
};

// ---------------------------------------------------------------------------
// Productos en Crudo (ítem libre de inventario)
// ---------------------------------------------------------------------------
export interface Crudo {
  id: number;
  nombre: string;
  area_id?: number | null;
  area?: Area | null;
  ubicacion_id: number;
  cantidad: number;
  activo: boolean;
  foto_url?: string | null;
  created_at?: string;
  updated_at?: string;
}

export interface CrudoCreate {
  nombre: string;
  area_id?: number | null;
  ubicacion_id?: number;
  cantidad?: number;
}

export interface CrudoConsumo {
  id: number;
  produccion_crudo_id: number;
  material_id: number;
  material_nombre?: string;
  cantidad: number;
  costo_unitario?: number;
  seccion?: string;
  // --- Captura flexible de madera (cantidad ya está en la unidad base) ---
  unidad_captura?: 'M' | 'CM' | null;
  pieza_largo?: number | null;
  pieza_ancho?: number | null;
  pieza_espesor?: number | null;
  // --- Componente y consumo extra (estructura de costes desde producción) ---
  componente?: string | null;
  es_excedente?: boolean;
  motivo_exceso?: string | null;
  solicitante_empleado_id?: number;
  solicitante?: Empleado | null;
  solicitante_nombre?: string;
  creado_por_id?: number;
  creador?: Empleado | null;
  fecha: string;
  observaciones?: string;
  material?: Material;
}

export interface CrudoConsumoCreate {
  material_id: number;
  /** Número digitado por el operario (en modo pieza: N.º de piezas). */
  cantidad: number;
  solicitante_empleado_id: number;
  seccion?: string;
  observaciones?: string;
  // --- Captura flexible: el backend convierte a la unidad base ---
  unidad_captura?: 'M' | 'CM';
  pieza_largo?: number;
  pieza_ancho?: number;
  pieza_espesor?: number;
  // --- Componente y consumo extra ---
  componente?: string;
  es_excedente?: boolean;
  motivo_exceso?: string;
}

export interface ProduccionCrudo {
  id: number;
  crudo_id: number;
  crudo?: Crudo;
  estado: 'PENDIENTE' | 'EN_PRODUCCION' | 'COMPLETADA' | 'CANCELADA';
  cantidad: number;
  costo_total: number;
  costo_mano_obra: number;
  fecha_inicio?: string | null;
  fecha_fin?: string | null;
  observaciones?: string;
  creado_por_id?: number;
  actualizado_por_id?: number;
  created_at?: string;
  updated_at?: string;
  consumos?: CrudoConsumo[];
  mano_obras?: ProduccionCrudoManoObra[];
}

export interface ProduccionCrudoCreate {
  crudo_id: number;
  cantidad?: number;
  observaciones?: string;
}

export interface ProduccionCrudoManoObra {
  id: number;
  produccion_crudo_id: number;
  empleado_id: number;
  empleado_nombre?: string;
  monto: number;
  porcentaje_recargo: number;
  listo_nomina: boolean;
  pagado: boolean;
  observaciones?: string;
  creado_por_id?: number;
  creador_nombre?: string;
  created_at?: string;
  updated_at?: string;
}

export interface ProduccionCrudoManoObraCreate {
  empleado_id: number;
  monto: number;
  cantidad?: number;
  porcentaje_recargo?: number;
  listo_nomina?: boolean;
  observaciones?: string;
}

export interface CrudoUso {
  id: number;
  crudo_id: number;
  detalle_pedido_id: number;
  cantidad: number;
  creado_por_id?: number;
  created_at?: string;
}

export const crudoService = {
  // Ítems en crudo
  getCrudo: async (activo?: boolean): Promise<Crudo[]> => {
    const response = await api.get<Crudo[]>('/produccion/crudo/', {
      params: activo === undefined ? {} : { activo },
    });
    return response.data;
  },
  getCrudoById: async (id: number): Promise<Crudo> => {
    const response = await api.get<Crudo>(`/produccion/crudo/${id}`);
    return response.data;
  },
  crearCrudo: async (payload: CrudoCreate): Promise<Crudo> => {
    const response = await api.post<Crudo>('/produccion/crudo/', payload);
    return response.data;
  },
  // Producciones de crudo
  getProducciones: async (): Promise<ProduccionCrudo[]> => {
    const response = await api.get<ProduccionCrudo[]>('/produccion/crudo-produccion/');
    return response.data;
  },
  crearProduccion: async (payload: ProduccionCrudoCreate): Promise<ProduccionCrudo> => {
    const response = await api.post<ProduccionCrudo>('/produccion/crudo-produccion/', payload);
    return response.data;
  },
  registrarConsumo: async (
    produccionId: number,
    payload: CrudoConsumoCreate,
  ): Promise<CrudoConsumo> => {
    const response = await api.post<CrudoConsumo>(
      `/produccion/crudo-produccion/${produccionId}/consumo/`,
      payload,
    );
    return response.data;
  },
  cambiarEstado: async (
    produccionId: number,
    estado: 'PENDIENTE' | 'EN_PRODUCCION' | 'COMPLETADA' | 'CANCELADA',
  ): Promise<ProduccionCrudo> => {
    const response = await api.put<ProduccionCrudo>(
      `/produccion/crudo-produccion/${produccionId}/estado`,
      { estado },
    );
    return response.data;
  },
  // Asignar pieza de crudo a un detalle de pedido (solo descuenta stock)
  asignarCrudo: async (crudoId: number, detallePedidoId: number): Promise<CrudoUso> => {
    const response = await api.post<CrudoUso>(
      `/produccion/crudo/${crudoId}/asignar/${detallePedidoId}`,
    );
    return response.data;
  },
  // Mano de obra en producción de crudo
  crearManoObra: async (
    produccionId: number,
    payload: ProduccionCrudoManoObraCreate,
  ): Promise<ProduccionCrudoManoObra> => {
    const response = await api.post<ProduccionCrudoManoObra>(
      `/produccion/crudo-produccion/${produccionId}/mano-obra/`,
      payload,
    );
    return response.data;
  },
  actualizarManoObra: async (
    manoObraId: number,
    payload: Partial<ProduccionCrudoManoObraCreate>,
  ): Promise<ProduccionCrudoManoObra> => {
    const response = await api.put<ProduccionCrudoManoObra>(
      `/produccion/crudo-produccion/mano-obra/${manoObraId}`,
      payload,
    );
    return response.data;
  },
  eliminarManoObra: async (manoObraId: number): Promise<void> => {
    await api.delete(`/produccion/crudo-produccion/mano-obra/${manoObraId}`);
  },
  listarProducciones: async (): Promise<ProduccionCrudo[]> => {
    const response = await api.get<ProduccionCrudo[]>('/produccion/crudo-produccion/');
    return response.data;
  },
};

export interface CostosEnVivoOrden {
  orden_id: number;
  estado: string;
  producto_id: number | null;
  producto_nombre: string | null;
  dimensiones: { ancho: number | null; largo: number | null } | null;
  unidades: number;
  estimado: number | null;
  costo_estimado: number | null;
  costo_real_total: number | null;
  costo_real_precio_venta: number | null;
  costo_real_ganancia: number | null;
  secciones: CostosEnVivoSeccion[];
  total_produccion: number;
  totales: {
    materiales: number;
    mano_obra: number;
    gastos: number;
    excedentes: number;
  };
}

export interface CostosEnVivoSeccion {
  nombre: string;
  orden: number;
  insumos: {
    nombre: string;
    cantidad: number;
    unidad: string;
    v_unit: number;
    total: number;
    es_excedente: boolean;
    es_retrabajo: boolean;
    motivo: string | null;
    /** Pedido sin confirmar uso: el costo es provisional (entregado, no usado). */
    es_pendiente?: boolean;
    cantidad_pedida?: number | null;
  }[];
  produccion: {
    nombre: string;
    base: number;
    porcentaje: number;
    total: number;
    es_retrabajo: boolean;
  }[];
  subtotal: number;
  pct_gastos: number;
  gastos: number;
  total: number;
}
