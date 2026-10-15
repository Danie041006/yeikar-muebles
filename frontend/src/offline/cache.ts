// Helpers genéricos local-first (caché cifrada + cola de salida) para los
// services de cada módulo. Con el modo offline apagado (producción) pasan
// directo al servidor: comportamiento idéntico al de siempre.
//
// Los GET se cachean en el espejo (`cache_api`) y, si falla la red, se sirve
// la última copia. Las mutaciones intentan el servidor; sin red se encolan en
// el outbox (`encolarOperacion`) con parches optimistas opcionales.

import { uuid } from './cifrado';
import { dbOffline } from './db';
import { OFFLINE_HABILITADO } from './interruptor';
import { abrirPaquete, empaquetar, eliminarDeEspejo, guardarEnEspejo, obtenerDeEspejo } from './repo';
import { encolarOperacion } from './sync';

export const TABLA_CACHE = 'cache_api';

export function esIdLocal(id: number): boolean {
  return id < 0;
}

export function esErrorDeRed(error: unknown): boolean {
  return !(error as { response?: unknown })?.response;
}

export function siguienteIdLocal(): number {
  contadorLocal += 1;
  return -(Date.now() + contadorLocal);
}

let contadorLocal = 0;

export async function conCache<T>(clave: string, fetcher: () => Promise<T>): Promise<T> {
  if (!OFFLINE_HABILITADO) return fetcher();
  try {
    const dato = await fetcher();
    await guardarEnEspejo(TABLA_CACHE, clave, dato);
    return dato;
  } catch (error) {
    if (esErrorDeRed(error)) {
      const copia = await obtenerDeEspejo<T>(TABLA_CACHE, clave);
      if (copia !== null) return copia;
    }
    throw error;
  }
}

export async function leerCache<T>(clave: string): Promise<T | null> {
  if (!OFFLINE_HABILITADO) return null;
  return obtenerDeEspejo<T>(TABLA_CACHE, clave);
}

export async function parchearCache(prefijo: string, mutar: (dato: any) => unknown): Promise<void> {
  if (!OFFLINE_HABILITADO) return;
  const filas = await dbOffline.espejo.where('tabla').equals(TABLA_CACHE).toArray();
  for (const fila of filas) {
    if (!fila.pk.startsWith(prefijo)) continue;
    const dato = await abrirPaquete<any>(fila);
    if (dato === null) continue;
    const nuevo = mutar(dato);
    if (nuevo !== undefined) await guardarEnEspejo(TABLA_CACHE, fila.pk, nuevo);
  }
}

export async function mutarOEncolar<T>(
  tipo: string,
  payload: Record<string, unknown>,
  opciones: {
    enLinea: () => Promise<T>;
    fabricarLocal?: (idLocal: number) => Promise<T> | T;
    optimista?: (idLocal: number) => Promise<void>;
  },
): Promise<T> {
  if (!OFFLINE_HABILITADO) return opciones.enLinea();
  try {
    return await opciones.enLinea();
  } catch (error) {
    if (!esErrorDeRed(error)) throw error;
    const idLocal = siguienteIdLocal();
    await encolarOperacion(tipo, { ...payload, _local_id: idLocal });
    if (opciones.optimista) await opciones.optimista(idLocal);
    if (opciones.fabricarLocal) return await opciones.fabricarLocal(idLocal);
    return undefined as unknown as T;
  }
}

export async function borrarCache(clave: string): Promise<void> {
  if (!OFFLINE_HABILITADO) return;
  await eliminarDeEspejo(TABLA_CACHE, clave);
}

export async function cancelarOperacionLocal(tipo: string, idLocal: number): Promise<boolean> {
  if (!OFFLINE_HABILITADO) return false;
  const pendientes = await dbOffline.outbox.where('estado').anyOf('pendiente', 'error', 'en_proceso').toArray();
  for (const fila of pendientes) {
    if (fila.tipo !== tipo) continue;
    const payload = await abrirPaquete<Record<string, unknown>>(fila);
    if (payload && payload._local_id === idLocal) {
      await dbOffline.outbox.delete(fila.id);
      return true;
    }
  }
  return false;
}

/**
 * Actualiza el payload de una operación aún no sincronizada (edición de un
 * registro creado offline): conserva la misma `operacion_id` (idempotencia) y
 * el mismo `_local_id` (las referencias internas siguen apuntando a él).
 */
export async function actualizarOperacionLocal(
  tipo: string,
  idLocal: number,
  cambios: Record<string, unknown>,
): Promise<boolean> {
  if (!OFFLINE_HABILITADO) return false;
  const pendientes = await dbOffline.outbox.where('estado').anyOf('pendiente', 'error', 'en_proceso').toArray();
  for (const fila of pendientes) {
    if (fila.tipo !== tipo) continue;
    const payload = await abrirPaquete<Record<string, unknown>>(fila);
    if (!payload || payload._local_id !== idLocal) continue;
    const nuevo = { ...payload, ...cambios };
    const paquete = await empaquetar(nuevo);
    await dbOffline.outbox.update(fila.id, paquete);
    return true;
  }
  return false;
}

export function generarIdLocal(): number {
  return siguienteIdLocal();
}

export { uuid };
