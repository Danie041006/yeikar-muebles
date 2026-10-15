// Repositorio del espejo local: lecturas/escrituras cifradas y mapa de IDs.
//
// Este es el punto único que usarán los services de cada módulo (F2+) para
// leer/escribir sin red. Si la clave del dispositivo está bloqueada (PIN
// pendiente), las lecturas cifradas devuelven null y las escrituras lanzan:
// la UI debe desbloquear primero.

import { cifrarJson, descifrarJson, hayClave, type BlobCifrado } from './cifrado';
import { CLAVES_META, claveEspejo, dbOffline, leerMeta, escribirMeta, type FilaEspejo } from './db';

export interface PaqueteDato {
  blob: BlobCifrado | null;
  dato: unknown;
}

export async function empaquetar(dato: unknown): Promise<PaqueteDato> {
  if (hayClave()) return { blob: await cifrarJson(dato), dato: null };
  return { blob: null, dato };
}

export async function abrirPaquete<T>(fila: { blob: BlobCifrado | null; dato: unknown }): Promise<T | null> {
  if (fila.blob) return descifrarJson<T>(fila.blob);
  return (fila.dato as T | undefined) ?? null;
}

export async function guardarEnEspejo(tabla: string, pk: string | number, dato: unknown): Promise<void> {
  const paquete = await empaquetar(dato);
  await dbOffline.espejo.put({
    clave: claveEspejo(tabla, pk),
    tabla,
    pk: String(pk),
    actualizado_en: new Date().toISOString(),
    ...paquete,
  });
}

export async function obtenerDeEspejo<T>(tabla: string, pk: string | number): Promise<T | null> {
  const fila = await dbOffline.espejo.get(claveEspejo(tabla, pk));
  if (!fila) return null;
  return abrirPaquete<T>(fila);
}

export async function listarEspejo<T>(tabla: string): Promise<T[]> {
  const filas = await dbOffline.espejo.where('tabla').equals(tabla).toArray();
  const datos: T[] = [];
  for (const fila of filas) {
    const dato = await abrirPaquete<T>(fila);
    if (dato !== null) datos.push(dato);
  }
  return datos;
}

export async function eliminarDeEspejo(tabla: string, pk: string | number): Promise<void> {
  await dbOffline.espejo.delete(claveEspejo(tabla, pk));
}

export async function vaciarEspejo(tabla?: string): Promise<void> {
  if (!tabla) {
    await dbOffline.espejo.clear();
    return;
  }
  const claves = (await dbOffline.espejo.where('tabla').equals(tabla).toArray()).map((f) => f.clave);
  await dbOffline.espejo.bulkDelete(claves);
}

export async function guardarIdLocal(tabla: string, idLocal: string, idServidor: number | string): Promise<void> {
  await dbOffline.ids.put({ id_local: idLocal, tabla, id_servidor: idServidor });
}

export async function resolverIdServidor(idLocal: string): Promise<number | string | null> {
  const fila = await dbOffline.ids.get(idLocal);
  return fila?.id_servidor ?? null;
}

export async function marcarTablaSucia(tabla: string): Promise<void> {
  const sucias = (await leerMeta<string[]>(CLAVES_META.tablasSucias)) ?? [];
  if (!sucias.includes(tabla)) {
    sucias.push(tabla);
    await escribirMeta(CLAVES_META.tablasSucias, sucias);
  }
}

export async function consumirTablasSucias(): Promise<string[]> {
  const sucias = (await leerMeta<string[]>(CLAVES_META.tablasSucias)) ?? [];
  if (sucias.length) await escribirMeta(CLAVES_META.tablasSucias, []);
  return sucias;
}

export function filaEspejoVacia(clave: string, tabla: string, pk: string): FilaEspejo {
  return { clave, tabla, pk, blob: null, dato: null, actualizado_en: new Date().toISOString() };
}
