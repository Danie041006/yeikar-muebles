import type { OrdenProduccion, MaterialUnidadUso } from '../../services/produccionService';

// ── Tipos y constantes compartidos entre el Kanban de producción y el
//    modal de etapa (única fuente de verdad, sin imports circulares). ──

export interface Empleado {
  id: number;
  nombre: string;
}

export interface Material {
  id: number;
  nombre: string;
  costo_base: number;
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

/** Transiciones legales de etapa (mismas que la máquina de estados del backend). */
export const TRANSICIONES_ETAPA: Record<string, string[]> = {
  ASIGNADA: ['EN_PROCESO'],
  EN_PROCESO: ['PAUSADA', 'COMPLETADA'],
  PAUSADA: ['EN_PROCESO'],
  COMPLETADA: [],
};

export const fmt = (n: number) =>
  new Intl.NumberFormat('es-CO', { style: 'currency', currency: 'COP', maximumFractionDigits: 0 }).format(n);

/** La orden fabrica una pieza de EXHIBICIÓN: al finalizar entra al stock del
 *  showroom con su costo real; nunca se envía a un cliente. */
export const esOrdenExhibicion = (orden?: OrdenProduccion | null) =>
  orden?.tipo === 'EXHIBICION' || (!orden?.detalle_pedido && !!orden?.producto?.es_exhibicion);

/** La orden RETRABAJA una pieza de exhibición ya fabricada: al finalizar la
 *  pieza vuelve al showroom con su costo X + el costo real del retoque. */
export const esOrdenRetrabajo = (orden?: OrdenProduccion | null) =>
  orden?.tipo === 'RETRABAJO';

/** Etiqueta corta del destino de la orden (tarjetas del Kanban). */
export const etiquetaOrden = (orden?: OrdenProduccion | null): string =>
  esOrdenRetrabajo(orden) ? 'RETRABAJO' : esOrdenExhibicion(orden) ? 'EXHIBICIÓN' : 'SIN PEDIDO';

/** Nombre visible de la orden: la pieza del juego manda; si no, el producto o
 *  la descripción del renglón. Null si la orden no tiene ninguno. */
export const nombreOrden = (orden?: OrdenProduccion | null): string | null =>
  orden?.pieza_nombre
  || orden?.detalle_pedido?.producto?.nombre
  || orden?.producto?.nombre
  || orden?.detalle_pedido?.descripcion_especifica
  || null;
