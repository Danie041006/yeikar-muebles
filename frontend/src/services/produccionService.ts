import api from './api';
import {
  cancelarOperacionLocal,
  conCache,
  eliminarConsumoDeCaches,
  eliminarManoObraDeCaches,
  esIdLocal,
  etapaDeConsumo,
  etapaDeManoObra,
  insertarAsignadoEnCaches,
  insertarConsumoEnCaches,
  insertarEtapaEnCaches,
  insertarManoObraEnCaches,
  leerCache,
  leerPiezaDeCaches,
  mutarOEncolar,
  parchearConsumoEnCaches,
  parchearEtapa,
  parchearPiezaEnCaches,
  quitarAsignadoDeCaches,
} from '../offline/produccionOffline';
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

export interface MaterialUnidadUso {
  id?: number;
  nombre: string;
  /** 1 [nombre] = factor_base unidades base del material (factor PRÁCTICO). */
  factor_base: number;
  activo?: boolean;
}

export interface Material {
  id: number;
  nombre: string;
  costo_base: number;
  // Dimensiones de la lámina completa (cm) si el material es laminar
  largo_cm?: number | null;
  ancho_cm?: number | null;
  // Unidades de uso (líquidos/densos: galón, pistolada, litro…)
  unidades_uso?: MaterialUnidadUso[];
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
  // --- Unidad de uso (galón, pistolada, litro…): lo digitado tal cual ---
  unidad_uso_id?: number | null;
  cantidad_uso?: number | null;
  unidad_uso?: MaterialUnidadUso | null;
  detalle_uso?: string | null;
  // --- Componente y consumo extra (estructura de costes desde producción) ---
  componente?: string | null;
  es_excedente?: boolean;
  motivo_exceso?: string | null;
  // --- Consumo por corte (materiales laminares) ---
  ancho_corte_cm?: number | null;
  largo_corte_cm?: number | null;
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
  /** Costo de las piezas en crudo asignadas al pedido (congelado al asignar). */
  costo_crudo?: number;
  costo_mano_obra: number;
  costo_gastos: number;
  precio_impuestos_base: number;
  ganancia_porcentaje: number;
  precio_venta_calculado: number;
  costo_total: number;
  costo_estimado?: number | null;
}

/** Pieza que compone un mueble (sofá, poltrona…): checklist de armado. */
export interface PiezaOrden {
  id: number;
  orden_produccion_id: number;
  posicion: number;
  nombre: string;
  cantidad: number;
  area_id?: number | null;
  area?: { id: number; nombre: string } | null;
  notas?: string | null;
  completada: boolean;
  completada_por_id?: number | null;
  fecha_completada?: string | null;
}

export interface OrdenProduccion {
  id: number;
  detalle_pedido_id: number | null;
  /** Pieza interna del juego (Mesa, Sillas…); null en un mueble suelto. */
  detalle_pieza_id?: number | null;
  pieza_nombre?: string | null;
  /** Unidades físicas de esta orden (pieza × juegos del renglón). */
  cantidad?: number | null;
  producto_id?: number | null;
  detalle_pedido?:DetallePedidoBasico;
  producto?: ProductoBasico;
  es_stock?: boolean;
  /** Destino de lo fabricado: PEDIDO | EXHIBICION | STOCK | RETRABAJO. */
  tipo?: 'PEDIDO' | 'EXHIBICION' | 'STOCK' | 'RETRABAJO';
  estado: 'PENDIENTE' | 'EN_PRODUCCION' | 'PAUSADA' | 'FINALIZADA' | 'CANCELADA';
  creado_por_id?: number | null;
  creador_nombre?: string | null;
  fecha_inicio?: string;
  fecha_fin?: string;
  ancho?: number;
  largo?: number;
  alto?: number;
  /** RETRABAJO: fila de inventario (pieza del showroom) que se retrabaja. */
  producto_inventario_id?: number | null;
  /** Motivo/contexto libre (el retrabajo guarda qué se cambia y para quién). */
  observaciones?: string | null;
  etapas: EtapaProduccion[];
  /** Checklist de piezas del mueble (auto-detectado de la descripción). */
  piezas?: PiezaOrden[];
  costo?: CostoProduccion;
  // True si al finalizar se generó la estructura de costes del producto.
  estructura_generada?: boolean | null;
  // Detalle del producto (opcional, para visualización)
  producto_nombre?: string;
}

/** Retrabajo vivo sobre una pieza de exhibición (para marcar EN RETRABAJO). */
export interface RetrabajoAbierto {
  id: number;
  producto_id: number | null;
  producto_inventario_id: number | null;
  estado: 'PENDIENTE' | 'EN_PRODUCCION' | 'PAUSADA';
  observaciones: string | null;
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
  descripcion_especifica?: string | null;
  observaciones?: string | null;
  tipo_item?: string | null;
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
  /** Receta POR UNIDAD (costo individual). */
  cantidad_esperada: number;
  /** Receta × n.º de piezas de la línea (total del lote que sale del depósito). */
  cantidad_total: number;
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
  /** None en muebles a la medida (sin producto de catálogo). */
  producto_id: number | null;
  producto_nombre: string;
  /** En una orden de pieza: nombre de la pieza y del juego padre. */
  pieza_nombre?: string | null;
  juego_nombre?: string | null;
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
  /** N.º de piezas idénticas de la línea (1 si la orden no tiene pedido). */
  piezas?: number | null;
  /** Checklist de piezas del mueble (sofá, poltronas…): se imprime en la hoja. */
  piezas_mueble?: PiezaOrden[];
  producto_fotos?: FotoReferencia[];
}

export const produccionService = {
  getOrdenes: async (buscar?: string, salto = 0, limite = 100): Promise<OrdenProduccion[]> => {
    return conCache(`ordenes:${buscar ?? ''}:${salto}:${limite}`, async () => {
      const response = await api.get<OrdenProduccion[]>('/produccion/orden/', {
        params: { buscar, salto, limite },
      });
      return response.data;
    });
  },

  getOrdenById: async (id: number): Promise<OrdenProduccion> => {
    return conCache(`orden:${id}`, async () => {
      const response = await api.get<OrdenProduccion>(`/produccion/orden/${id}`);
      return response.data;
    });
  },

  getEtapa: async (id: number): Promise<EtapaProduccion> => {
    return conCache(`etapa:${id}`, async () => {
      const response = await api.get<EtapaProduccion>(`/produccion/etapa/${id}`);
      return response.data;
    });
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

  /** Abre un retrabajo sobre una pieza de exhibición EN STOCK: sale del
   *  showroom (apartada) y al finalizar vuelve con su costo X + el retoque. */
  crearRetrabajo: async (payload: {
    producto_id: number;
    motivo?: string;
    cliente_nombre?: string;
  }): Promise<OrdenProduccion> => {
    const response = await api.post<OrdenProduccion>('/produccion/orden/retrabajo', payload);
    return response.data;
  },

  /** Retrabajos vivos (para marcar las piezas EN RETRABAJO en Inventario). */
  getRetrabajosAbiertos: async (): Promise<RetrabajoAbierto[]> => {
    return conCache('retrabajos-abiertos', async () => {
      const response = await api.get<RetrabajoAbierto[]>('/produccion/orden/retrabajos-abiertos');
      return response.data;
    });
  },

  getAreas: async (): Promise<Area[]> => {
    return conCache('areas', async () => {
      const response = await api.get<Area[]>('/catalogos/area/');
      return response.data;
    });
  },

  getReferenciaReceta: async (etapaId: number): Promise<ReferenciaReceta> => {
    return conCache(`receta:${etapaId}`, async () => {
      const response = await api.get<ReferenciaReceta>(`/produccion/etapa/${etapaId}/referencia-receta`);
      return response.data;
    });
  },

  updateEstadoEtapa: async (id: number, estado: string): Promise<EtapaProduccion> => {
    return mutarOEncolar<EtapaProduccion>('produccion.etapa.estado', { etapa_id: id, estado }, {
      enLinea: async () => {
        const response = await api.put<EtapaProduccion>(`/produccion/etapa/${id}/estado`, null, {
          params: { estado },
        });
        return response.data;
      },
      fabricarLocal: () => ({ id, estado } as EtapaProduccion),
      optimista: async () => {
        await parchearEtapa(id, {
          estado,
          ...(estado === 'EN_PROCESO' ? { fecha_inicio: new Date().toISOString() } : {}),
          ...(estado === 'COMPLETADA' ? { fecha_fin: new Date().toISOString() } : {}),
        });
      },
    });
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
    return mutarOEncolar<EtapaProduccion>('produccion.etapa.pasar-area', { etapa_id: etapaId, ...payload }, {
      enLinea: async () => {
        const response = await api.post<EtapaProduccion>(
          `/produccion/etapa/${etapaId}/pasar-a-area`,
          payload,
        );
        return response.data;
      },
      fabricarLocal: (idLocal) => ({
        id: idLocal,
        area_id: payload.area_id,
        empleado_responsable_id: payload.empleado_responsable_id,
        estado: 'ASIGNADA',
        consumos: [],
        mano_obras: [],
        asignados_adicionales: [],
        observaciones: payload.observaciones,
      }) as unknown as EtapaProduccion,
      optimista: async (idLocal) => {
        const actual = await leerCache<EtapaProduccion>(`etapa:${etapaId}`);
        await parchearEtapa(etapaId, { estado: 'COMPLETADA', fecha_fin: new Date().toISOString() });
        await insertarEtapaEnCaches(etapaId, {
          id: idLocal,
          orden_produccion_id: actual?.orden_produccion_id ?? 0,
          area_id: payload.area_id,
          empleado_responsable_id: payload.empleado_responsable_id,
          estado: 'ASIGNADA',
          fecha_inicio: new Date().toISOString(),
          observaciones: payload.observaciones,
          consumos: [],
          mano_obras: [],
          asignados_adicionales: [],
        });
      },
    });
  },

  agregarAsignadoAdicional: async (etapaId: number, empleadoId: number): Promise<AsignadoAdicional> => {
    return mutarOEncolar<AsignadoAdicional>('produccion.etapa.asignado.agregar', { etapa_id: etapaId, empleado_id: empleadoId }, {
      enLinea: async () => {
        const response = await api.post<AsignadoAdicional>(`/produccion/etapa/${etapaId}/asignados`, {
          empleado_id: empleadoId,
        });
        return response.data;
      },
      fabricarLocal: (idLocal) => ({
        id: idLocal,
        etapa_produccion_id: etapaId,
        empleado_id: empleadoId,
      }) as AsignadoAdicional,
      optimista: async (idLocal) => {
        await insertarAsignadoEnCaches(etapaId, { id: idLocal, etapa_produccion_id: etapaId, empleado_id: empleadoId });
      },
    });
  },

  quitarAsignadoAdicional: async (etapaId: number, empleadoId: number): Promise<void> => {
    await mutarOEncolar<void>('produccion.etapa.asignado.quitar', { etapa_id: etapaId, empleado_id: empleadoId }, {
      enLinea: async () => {
        await api.delete(`/produccion/etapa/${etapaId}/asignados/${empleadoId}`);
      },
      optimista: async () => {
        await quitarAsignadoDeCaches(etapaId, empleadoId);
      },
    });
  },

  /** Marca/desmarca una pieza del mueble (checklist de armado). */
  actualizarPieza: async (
    piezaId: number,
    cambios: { completada?: boolean; nombre?: string; cantidad?: number; area_id?: number | null; notas?: string | null },
  ): Promise<PiezaOrden> => {
    return mutarOEncolar<PiezaOrden>('produccion.pieza.actualizar', { pieza_id: piezaId, ...cambios }, {
      enLinea: async () => {
        const response = await api.put<PiezaOrden>(`/produccion/pieza/${piezaId}`, cambios);
        return response.data;
      },
      fabricarLocal: async () => {
        const actual = await leerPiezaDeCaches(piezaId);
        return { ...(actual ?? {}), id: piezaId, ...cambios } as PiezaOrden;
      },
      optimista: async () => {
        await parchearPiezaEnCaches(piezaId, cambios as Record<string, unknown>);
      },
    });
  },

  registrarConsumo: async (consumo: {
    etapa_produccion_id: number;
    material_id: number;
    /** Número digitado por el operario (en modo pieza: N.º de piezas).
     *  null/undefined + es_pedido = pedido ABIERTO: piden sin cantidad y el
     *  descuento/costo real ocurre al confirmar el uso. */
    cantidad?: number | null;
    fecha: string;
    seccion?: string;
    observaciones?: string;
    solicitante_empleado_id: number;
    // --- Captura flexible: el backend convierte a la unidad base ---
    unidad_captura?: 'M' | 'CM';
    pieza_largo?: number;
    pieza_ancho?: number;
    pieza_espesor?: number;
    /** Unidad de uso (galón, pistolada, litro…): `cantidad` va digitada en ella. */
    unidad_uso_id?: number;
    // --- Componente y consumo extra ---
    componente?: string;
    es_excedente?: boolean;
    motivo_exceso?: string;
    // --- Pedido de LÁMINA COMPLETA (confirmar uso después) ---
    // True + material laminar: `cantidad` = N.º de láminas enteras que salen
    // hoy; el consumo queda PENDIENTE hasta confirmar los cortes reales.
    es_lamina_completa?: boolean;
    // --- PEDIDO general (madera y demás: confirmar uso después) ---
    // True: `cantidad` = cantidad ENTREGADA hoy (opcional: si va vacía es un
    // pedido ABIERTO que no toca stock hasta confirmar); el consumo queda
    // PENDIENTE hasta confirmar cuánto se usó.
    // Híbrido: si es False se registra el uso directo (CONFIRMADO inmediato).
    es_pedido?: boolean;
    // --- Consumo por corte (materiales laminares) ---
    ancho_corte_cm?: number;
    largo_corte_cm?: number;
  }): Promise<ConsumoMaterial> => {
    const estadoLocal = consumo.es_pedido || consumo.es_lamina_completa ? 'PENDIENTE' as const : 'CONFIRMADO' as const;
    const fabricar = (idLocal: number): ConsumoMaterial => ({
      id: idLocal,
      etapa_produccion_id: consumo.etapa_produccion_id,
      material_id: consumo.material_id,
      cantidad: consumo.cantidad ?? 0,
      fecha: consumo.fecha,
      estado: estadoLocal,
      observaciones: consumo.observaciones,
      solicitante_empleado_id: consumo.solicitante_empleado_id,
      unidad_captura: consumo.unidad_captura ?? null,
      pieza_largo: consumo.pieza_largo ?? null,
      pieza_ancho: consumo.pieza_ancho ?? null,
      pieza_espesor: consumo.pieza_espesor ?? null,
    }) as unknown as ConsumoMaterial;

    return mutarOEncolar<ConsumoMaterial>('produccion.consumo.registrar', { ...consumo }, {
      enLinea: async () => {
        const response = await api.post<ConsumoMaterial>('/produccion/consumo/', consumo);
        return response.data;
      },
      fabricarLocal: fabricar,
      optimista: async (idLocal) => {
        await insertarConsumoEnCaches(consumo.etapa_produccion_id, fabricar(idLocal));
      },
    });
  },

  /** Confirma el uso real de un pedido (PENDIENTE → CONFIRMADO).
   *  Dos modos excluyentes: por cortes (láminas) o por usos (madera y demás).
   *  Los usos admiten captura flexible: unidad_captura (cm para la cuenta del
   *  taller, cm/mts lineal) o medidas de pieza (fórmula de la casa) — el
   *  backend convierte a la unidad base y guarda un consumo por uso (renglón
   *  aislado en la tablita de costos). */
  confirmarConsumo: async (
    id: number,
    payload: {
      cantidad_cortes?: number;
      largo_corte_cm?: number;
      ancho_corte_cm?: number;
      /** Legacy: un solo uso en unidad base (o con captura flexible). */
      cantidad_usada?: number;
      unidad_captura?: 'M' | 'CM';
      pieza_largo?: number;
      pieza_ancho?: number;
      pieza_espesor?: number;
      /** Unidad de uso del modo legacy (galón, pistolada, litro…). */
      unidad_uso_id?: number;
      /** Varios usos en una sola confirmación (uno por renglón de costo). */
      usos?: {
        cantidad: number;
        unidad_captura?: 'M' | 'CM';
        pieza_largo?: number;
        pieza_ancho?: number;
        pieza_espesor?: number;
        /** Unidad de uso (galón, pistolada, litro…): `cantidad` va en ella. */
        unidad_uso_id?: number;
      }[];
    },
  ): Promise<ConsumoMaterial> => {
    if (esIdLocal(id)) {
      throw Object.assign(new Error('Consumo pendiente de sincronizar'), {
        response: {
          data: {
            detail: 'Sin conexión: este consumo aún no existe en el servidor. Confírmalo cuando vuelva la red.',
          },
        },
      });
    }
    return mutarOEncolar<ConsumoMaterial>('produccion.consumo.confirmar', { consumo_id: id, ...payload }, {
      enLinea: async () => {
        const response = await api.put<ConsumoMaterial>(`/produccion/consumo/${id}/confirmar`, payload);
        return response.data;
      },
      optimista: async () => {
        const etapaId = await etapaDeConsumo(id);
        if (etapaId !== null) await parchearConsumoEnCaches(etapaId, id, { estado: 'CONFIRMADO' });
      },
    });
  },

  eliminarConsumo: async (id: number): Promise<void> => {
    if (esIdLocal(id)) {
      await cancelarOperacionLocal('produccion.consumo.registrar', id);
      const etapaId = await etapaDeConsumo(id);
      if (etapaId !== null) await eliminarConsumoDeCaches(etapaId, id);
      return;
    }
    await mutarOEncolar<void>('produccion.consumo.eliminar', { consumo_id: id }, {
      enLinea: async () => {
        await api.delete(`/produccion/consumo/${id}`);
      },
      optimista: async () => {
        const etapaId = await etapaDeConsumo(id);
        if (etapaId !== null) await eliminarConsumoDeCaches(etapaId, id);
      },
    });
  },

  registrarManoObra: async (manoObra: {
    etapa_produccion_id: number;
    empleado_id: number;
    monto: number;
    porcentaje_recargo?: number;
    observaciones?: string;
    precio_produccion_id?: number;
  }): Promise<ManoObra> => {
    const fabricar = (idLocal: number): ManoObra => ({
      id: idLocal,
      etapa_produccion_id: manoObra.etapa_produccion_id,
      empleado_id: manoObra.empleado_id,
      monto: manoObra.monto,
      porcentaje_recargo: manoObra.porcentaje_recargo ?? 0,
      observaciones: manoObra.observaciones,
      precio_produccion_id: manoObra.precio_produccion_id ?? null,
    }) as unknown as ManoObra;

    return mutarOEncolar<ManoObra>('produccion.mano-obra.registrar', { ...manoObra }, {
      enLinea: async () => {
        const response = await api.post<ManoObra>('/produccion/mano-obra/', manoObra);
        return response.data;
      },
      fabricarLocal: fabricar,
      optimista: async (idLocal) => {
        await insertarManoObraEnCaches(manoObra.etapa_produccion_id, fabricar(idLocal));
      },
    });
  },

  eliminarManoObra: async (id: number): Promise<void> => {
    if (esIdLocal(id)) {
      await cancelarOperacionLocal('produccion.mano-obra.registrar', id);
      const etapaId = await etapaDeManoObra(id);
      if (etapaId !== null) await eliminarManoObraDeCaches(etapaId, id);
      return;
    }
    await mutarOEncolar<void>('produccion.mano-obra.eliminar', { mano_obra_id: id }, {
      enLinea: async () => {
        await api.delete(`/produccion/mano-obra/${id}`);
      },
      optimista: async () => {
        const etapaId = await etapaDeManoObra(id);
        if (etapaId !== null) await eliminarManoObraDeCaches(etapaId, id);
      },
    });
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
    return conCache(`costos:${ordenId}`, async () => {
      const response = await api.get<CostosEnVivoOrden>(`/produccion/orden/${ordenId}/costos-en-vivo`);
      return response.data;
    });
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
  /** Costo unitario de referencia de lo ya hecho (base del futuro egreso). */
  costo_unitario?: number | null;
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
  /** Costo unitario de referencia (opcional, solo para lo ya hecho). */
  costo_unitario?: number | null;
}

export interface CrudoMovimiento {
  id: number;
  crudo_id: number;
  tipo: 'ENTRADA' | 'SALIDA' | 'AJUSTE' | 'DAÑO' | 'DEVOLUCION';
  cantidad: number;
  referencia_tipo?: string | null;
  referencia_id?: number | null;
  observaciones?: string | null;
  creado_por_id?: number | null;
  creador_nombre?: string | null;
  fecha?: string | null;
  created_at?: string | null;
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
  crudo_nombre?: string | null;
  detalle_pedido_id: number;
  cantidad: number;
  /** Costo real del crudo congelado al asignar (materiales + mano de obra). */
  costo_unitario?: number | null;
  costo_total?: number | null;
  seccion?: string | null;
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
  /** Kardex del ítem en crudo (misma UI de movimientos que insumos). */
  getKardex: async (id: number): Promise<CrudoMovimiento[]> => {
    const response = await api.get<CrudoMovimiento[]>(`/produccion/crudo/${id}/kardex`);
    return response.data;
  },
  /** Registrar movimiento manual (ENTRADA/SALIDA/AJUSTE/DAÑO/DEVOLUCION). */
  registrarMovimiento: async (
    id: number,
    payload: { tipo: string; cantidad: number; observaciones?: string; fecha?: string },
  ): Promise<CrudoMovimiento> => {
    const response = await api.post<CrudoMovimiento>(`/produccion/crudo/${id}/movimiento`, payload);
    return response.data;
  },
  /** Editar nombre, ubicación o estado del ítem en crudo. */
  actualizarCrudo: async (
    id: number,
    payload: { nombre?: string; area_id?: number | null; ubicacion_id?: number; activo?: boolean },
  ): Promise<Crudo> => {
    const response = await api.put<Crudo>(`/produccion/crudo/${id}`, payload);
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
  /** En una orden de pieza: nombre de la pieza y del juego padre. */
  pieza_nombre?: string | null;
  juego_nombre?: string | null;
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
    /** Etiqueta legible del uso ("Pieza 2×10×5", "1.500 cm (cuenta del taller)"). */
    captura?: string | null;
    es_excedente: boolean;
    es_retrabajo: boolean;
    motivo: string | null;
    /** Pedido sin confirmar uso: el costo es provisional (entregado, no usado). */
    es_pendiente?: boolean;
    cantidad_pedida?: number | null;
    /** Pieza en crudo asignada al pedido: su costo real entra al mueble. */
    es_crudo?: boolean;
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
