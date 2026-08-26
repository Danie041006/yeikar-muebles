// Traducción de acciones de auditoría al español (para Carolina y compañía).
// Cualquier acción nueva no mapeada se muestra tal cual, sin romper la UI.

/** Etiqueta en infinitivo/tercera persona para badges y filtros: "Creó", "Cambió estado" */
export const ACCION_LABELS: Record<string, string> = {
  CREATE: 'Creó',
  UPDATE: 'Editó',
  STATE_CHANGE: 'Cambió estado',
  DELETE: 'Eliminó',
  ASSIGN: 'Asignó',
  LOCATION_UPDATE: 'Reportó ubicación',
  SYSTEM_CREATE: 'Creación automática',
  FACTURAR_CON_SALDO_PENDIENTE: 'Facturó con saldo pendiente',
};

/** Verbo en pasado para leer la línea como frase: "carolina creó Cotización #123" */
export const ACCION_VERBOS: Record<string, string> = {
  CREATE: 'creó',
  UPDATE: 'editó',
  STATE_CHANGE: 'cambió el estado de',
  DELETE: 'eliminó',
  ASSIGN: 'asignó',
  LOCATION_UPDATE: 'reportó la ubicación de',
  SYSTEM_CREATE: 'creó automáticamente',
  FACTURAR_CON_SALDO_PENDIENTE: 'facturó (con saldo pendiente)',
};

export const accionLabel = (accion: string): string => ACCION_LABELS[accion] ?? accion;

export const accionVerbo = (accion: string): string => ACCION_VERBOS[accion] ?? accionLabel(accion).toLowerCase();
