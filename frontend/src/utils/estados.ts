// Mapas unificados de estado → presentación (Badge) por dominio.
// Antes cada página tenía su propia copia inline; aquí vive la única fuente.

export type Tone = 'neutral' | 'gold' | 'green' | 'red' | 'blue' | 'amber' | 'purple';

export const ESTADOS: Record<string, Record<string, { tone: Tone; label: string }>> = {
  cotizacion: {
    BORRADOR: { tone: 'neutral', label: 'Borrador' },
    ENVIADA: { tone: 'blue', label: 'Enviada' },
    APROBADA: { tone: 'green', label: 'Aprobada' },
    RECHAZADA: { tone: 'red', label: 'Rechazada' },
    VENCIDA: { tone: 'amber', label: 'Vencida' },
  },
  pedido: {
    COTIZADO: { tone: 'neutral', label: 'Cotizado' },
    APROBADO: { tone: 'blue', label: 'Aprobado' },
    PRODUCCION: { tone: 'gold', label: 'En producción' },
    PAUSADO: { tone: 'amber', label: 'Pausado' },
    TERMINADO: { tone: 'green', label: 'Terminado' },
    ENTREGADO: { tone: 'purple', label: 'Entregado' },
    CANCELADO: { tone: 'red', label: 'Cancelado' },
  },
  orden: {
    PENDIENTE: { tone: 'neutral', label: 'Pendiente' },
    EN_PRODUCCION: { tone: 'gold', label: 'En producción' },
    PAUSADA: { tone: 'amber', label: 'Pausada' },
    FINALIZADA: { tone: 'green', label: 'Finalizada' },
    CANCELADA: { tone: 'red', label: 'Cancelada' },
  },
  etapa: {
    ASIGNADA: { tone: 'neutral', label: 'Asignada' },
    EN_PROCESO: { tone: 'gold', label: 'En proceso' },
    PAUSADA: { tone: 'amber', label: 'Pausada' },
    COMPLETADA: { tone: 'green', label: 'Completada' },
  },
  venta: {
    PENDIENTE: { tone: 'amber', label: 'Pendiente' },
    ABONADA: { tone: 'blue', label: 'Abonada' },
    PAGADA: { tone: 'green', label: 'Pagada' },
    CANCELADA: { tone: 'red', label: 'Cancelada' },
  },
  envio: {
    PREPARADO: { tone: 'neutral', label: 'Preparado' },
    EN_TRANSITO: { tone: 'blue', label: 'En tránsito' },
    ENTREGADO: { tone: 'green', label: 'Entregado' },
    FALLIDO: { tone: 'red', label: 'Fallido' },
  },
  factura: {
    EMITIDA: { tone: 'green', label: 'Emitida' },
    ANULADA: { tone: 'red', label: 'Anulada' },
  },
};

export function estadoInfo(dominio: keyof typeof ESTADOS | string, estado?: string | null): { tone: Tone; label: string } {
  const mapa = ESTADOS[dominio];
  if (mapa && estado && mapa[estado]) return mapa[estado];
  return { tone: 'neutral', label: estado || '—' };
}