// Utilidades local-first del módulo Producción (F2).
//
// Los GET del Kanban se cachean en el espejo cifrado (helpers de `cache.ts`)
// y, si no hay red, se sirven de la copia. Las mutaciones intentan el servidor
// primero; si fallan por red, se encolan en el outbox y se aplican de forma
// optimista sobre las copias cacheadas, con IDs locales negativos.

import { dbOffline } from './db';
import { abrirPaquete } from './repo';
import { TABLA_CACHE, parchearCache } from './cache';

export {
  cancelarOperacionLocal,
  conCache,
  esErrorDeRed,
  esIdLocal,
  leerCache,
  mutarOEncolar,
  siguienteIdLocal,
} from './cache';

// ---------------------------------------------------------------------------
// Parches optimistas sobre las copias cacheadas
// ---------------------------------------------------------------------------
async function mutarEtapaEnCaches(etapaId: number, mutar: (etapa: any) => any): Promise<void> {
  await parchearCache('etapa:', (etapa) => (etapa?.id === etapaId ? mutar(etapa) : undefined));
  await parchearCache('orden', (orden) => {
    if (!orden?.etapas) return undefined;
    let tocado = false;
    const etapas = orden.etapas.map((etapa: any) => {
      if (etapa.id !== etapaId) return etapa;
      tocado = true;
      return mutar(etapa);
    });
    return tocado ? { ...orden, etapas } : undefined;
  });
}

export async function parchearEtapa(etapaId: number, cambios: Record<string, unknown>): Promise<void> {
  await mutarEtapaEnCaches(etapaId, (etapa) => ({ ...etapa, ...cambios }));
}

export async function insertarEtapaEnCaches(etapaReferenciaId: number, nuevaEtapa: any): Promise<void> {
  await parchearCache('orden', (orden) => {
    if (!orden?.etapas?.some((etapa: any) => etapa.id === etapaReferenciaId)) return undefined;
    return { ...orden, etapas: [...orden.etapas, nuevaEtapa] };
  });
}

export async function insertarConsumoEnCaches(etapaId: number, consumo: any): Promise<void> {
  await mutarEtapaEnCaches(etapaId, (etapa) => ({
    ...etapa,
    consumos: [...(etapa.consumos ?? []), consumo],
  }));
}

export async function parchearConsumoEnCaches(etapaId: number, consumoId: number, cambios: Record<string, unknown>): Promise<void> {
  await mutarEtapaEnCaches(etapaId, (etapa) => ({
    ...etapa,
    consumos: (etapa.consumos ?? []).map((consumo: any) => (consumo.id === consumoId ? { ...consumo, ...cambios } : consumo)),
  }));
}

export async function eliminarConsumoDeCaches(etapaId: number, consumoId: number): Promise<void> {
  await mutarEtapaEnCaches(etapaId, (etapa) => ({
    ...etapa,
    consumos: (etapa.consumos ?? []).filter((consumo: any) => consumo.id !== consumoId),
  }));
}

export async function insertarManoObraEnCaches(etapaId: number, manoObra: any): Promise<void> {
  await mutarEtapaEnCaches(etapaId, (etapa) => ({
    ...etapa,
    mano_obras: [...(etapa.mano_obras ?? []), manoObra],
  }));
}

export async function eliminarManoObraDeCaches(etapaId: number, manoObraId: number): Promise<void> {
  await mutarEtapaEnCaches(etapaId, (etapa) => ({
    ...etapa,
    mano_obras: (etapa.mano_obras ?? []).filter((mano: any) => mano.id !== manoObraId),
  }));
}

export async function insertarAsignadoEnCaches(etapaId: number, asignado: any): Promise<void> {
  await mutarEtapaEnCaches(etapaId, (etapa) => ({
    ...etapa,
    asignados_adicionales: [...(etapa.asignados_adicionales ?? []), asignado],
  }));
}

export async function quitarAsignadoDeCaches(etapaId: number, empleadoId: number): Promise<void> {
  await mutarEtapaEnCaches(etapaId, (etapa) => ({
    ...etapa,
    asignados_adicionales: (etapa.asignados_adicionales ?? []).filter((a: any) => a.empleado_id !== empleadoId),
  }));
}

export async function parchearPiezaEnCaches(piezaId: number, cambios: Record<string, unknown>): Promise<void> {
  const aplicar = (pieza: any) => (pieza.id === piezaId ? { ...pieza, ...cambios } : pieza);
  await parchearCache('orden', (orden) => {
    if (!orden?.piezas) return undefined;
    return { ...orden, piezas: orden.piezas.map(aplicar) };
  });
  await parchearCache('receta:', (receta) => {
    if (!receta?.piezas_mueble) return undefined;
    return { ...receta, piezas_mueble: receta.piezas_mueble.map(aplicar) };
  });
}

export async function leerPiezaDeCaches(piezaId: number): Promise<any | null> {
  const filas = await dbOffline.espejo.where('tabla').equals(TABLA_CACHE).toArray();
  for (const fila of filas) {
    if (!fila.pk.startsWith('orden') && !fila.pk.startsWith('receta:')) continue;
    const dato = await abrirPaquete<any>(fila);
    if (!dato) continue;
    const piezas = [...(dato.piezas ?? []), ...(dato.piezas_mueble ?? [])];
    const encontrada = piezas.find((pieza: any) => pieza.id === piezaId);
    if (encontrada) return encontrada;
  }
  return null;
}

async function buscarEtapaConItem(enEtapa: (etapa: any) => boolean): Promise<number | null> {
  const filas = await dbOffline.espejo.where('tabla').equals(TABLA_CACHE).toArray();
  for (const fila of filas) {
    if (!fila.pk.startsWith('etapa:') && !fila.pk.startsWith('orden')) continue;
    const dato = await abrirPaquete<any>(fila);
    if (!dato) continue;
    const etapas = dato.etapas ?? (dato.id ? [dato] : []);
    const encontrada = etapas.find((etapa: any) => enEtapa(etapa));
    if (encontrada) return encontrada.id as number;
  }
  return null;
}

export function etapaDeConsumo(consumoId: number): Promise<number | null> {
  return buscarEtapaConItem((etapa) => (etapa.consumos ?? []).some((c: any) => c.id === consumoId));
}

export function etapaDeManoObra(manoObraId: number): Promise<number | null> {
  return buscarEtapaConItem((etapa) => (etapa.mano_obras ?? []).some((m: any) => m.id === manoObraId));
}
