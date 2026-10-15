// Base local del modo offline (IndexedDB vía Dexie).
//
//   espejo → copia de las filas del servidor (dato cifrado con la clave del
//            dispositivo). Clave: `${tabla}:${pk}`.
//   outbox → operaciones capturadas sin red, pendientes de enviar al servidor.
//   meta   → cursores de sync, sesión cacheada, credencial del PIN, etc.
//   ids    → mapa id_local (UUID generado offline) → id del servidor.
//
// El esquema NO borra datos entre versiones; para limpiar todo usar
// `limpiarOffline()` (logout o PIN agotado).

import Dexie, { type Table } from 'dexie';
import type { BlobCifrado } from './cifrado';

export interface FilaEspejo {
  clave: string;
  tabla: string;
  pk: string;
  blob: BlobCifrado | null;
  dato: unknown;
  actualizado_en: string;
}

export type EstadoOperacion = 'pendiente' | 'error' | 'conflicto' | 'en_proceso';

export interface FilaOutbox {
  id: string;
  tipo: string;
  estado: EstadoOperacion;
  blob: BlobCifrado | null;
  dato: unknown;
  creada_en: string;
  intentos: number;
  detalle: string | null;
}

export interface FilaMeta {
  clave: string;
  valor: unknown;
}

export interface FilaIdLocal {
  id_local: string;
  tabla: string;
  id_servidor: number | string;
}

class DbOffline extends Dexie {
  espejo!: Table<FilaEspejo, string>;
  outbox!: Table<FilaOutbox, string>;
  meta!: Table<FilaMeta, string>;
  ids!: Table<FilaIdLocal, string>;

  constructor() {
    super('yeikar-offline');
    this.version(1).stores({
      espejo: 'clave, tabla, actualizado_en',
      outbox: 'id, estado, creada_en',
      meta: 'clave',
      ids: 'id_local, tabla',
    });
  }
}

export const dbOffline = new DbOffline();

export const CLAVES_META = {
  cursor: 'sync_cursor',
  ultimaSync: 'ultima_sync',
  tablasSucias: 'tablas_sucias',
  sesionResumen: 'sesion_resumen',
  sesionCache: 'sesion_cache',
  claveDispositivo: 'clave_dispositivo',
  pinIntentos: 'pin_intentos',
} as const;

export async function leerMeta<T>(clave: string): Promise<T | null> {
  const fila = await dbOffline.meta.get(clave);
  return (fila?.valor as T | undefined) ?? null;
}

export async function escribirMeta(clave: string, valor: unknown): Promise<void> {
  await dbOffline.meta.put({ clave, valor });
}

export function claveEspejo(tabla: string, pk: string | number): string {
  return `${tabla}:${pk}`;
}
