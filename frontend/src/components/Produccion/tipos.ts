import type { OrdenProduccion } from '../../services/produccionService';

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
