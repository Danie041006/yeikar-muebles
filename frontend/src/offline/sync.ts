// Motor de sincronización: empuja el outbox y jala la bitácora de cambios.
//
// - Lo llama `AuthContext` al iniciar sesión (arranca listeners de red,
//   visibilidad y un temporizador) y cada módulo al encolar una operación.
// - `encolarOperacion` nunca pierde trabajo: si el push falla, la fila queda
//   en el outbox y se reintenta en la próxima sincronización.
// - Los tombstones (op='D') de la bitácora se aplican directo al espejo; los
//   altas/cambios marcan la tabla como sucia para que el módulo (F2+) la
//   refresque por su vía normal.

import api from '../services/api';
import { hayClave, uuid } from './cifrado';
import { OFFLINE_HABILITADO } from './interruptor';
import { CLAVES_META, dbOffline, escribirMeta, leerMeta, type FilaOutbox } from './db';
import { abrirPaquete, empaquetar, guardarIdLocal, marcarTablaSucia } from './repo';

export interface EstadoSync {
  sincronizando: boolean;
  pendientes: number;
  conflictos: number;
  sinConexion: boolean;
  ultimaSync: string | null;
}

interface ResultadoPushApi {
  operacion_id: string;
  estado: 'ok' | 'conflicto' | 'error' | 'en_proceso';
  detalle?: string | null;
  entidad?: { tabla?: string; id?: number | string; id_local?: string } | null;
}

interface CambioApi {
  cursor: number;
  tabla: string;
  pk: string;
  op: string;
}

let estado: EstadoSync = {
  sincronizando: false,
  pendientes: 0,
  conflictos: 0,
  sinConexion: false,
  ultimaSync: null,
};

const oyentes = new Set<() => void>();

function actualizar(parcial: Partial<EstadoSync>): void {
  estado = { ...estado, ...parcial };
  oyentes.forEach((fn) => fn());
}

export function suscribirSync(fn: () => void): () => void {
  oyentes.add(fn);
  return () => {
    oyentes.delete(fn);
  };
}

export function estadoSync(): EstadoSync {
  return estado;
}

export async function refrescarContadores(): Promise<void> {
  try {
    const filas = await dbOffline.outbox.toArray();
    const pendientes = filas.filter((f) => f.estado === 'pendiente' || f.estado === 'en_proceso').length;
    const conflictos = filas.filter((f) => f.estado === 'conflicto' || f.estado === 'error').length;
    actualizar({ pendientes, conflictos });
  } catch {
    /* IndexedDB no disponible: el indicador queda en cero */
  }
}

export async function listarConflictos(): Promise<FilaOutbox[]> {
  try {
    return (await dbOffline.outbox.where('estado').anyOf('conflicto', 'error').toArray()).sort((a, b) =>
      a.creada_en.localeCompare(b.creada_en),
    );
  } catch {
    return [];
  }
}

export async function descartarOperacion(id: string): Promise<void> {
  await dbOffline.outbox.delete(id);
  await refrescarContadores();
}

export async function encolarOperacion(tipo: string, payload: Record<string, unknown>): Promise<string> {
  if (!OFFLINE_HABILITADO) throw new Error('El modo offline está apagado en este equipo.');
  const id = uuid();
  const paquete = await empaquetar(payload);
  await dbOffline.outbox.add({
    id,
    tipo,
    estado: 'pendiente',
    creada_en: new Date().toISOString(),
    intentos: 0,
    detalle: null,
    ...paquete,
  });
  await refrescarContadores();
  void sincronizar();
  return id;
}

async function pushPendientes(): Promise<void> {
  for (let vuelta = 0; vuelta < 10; vuelta += 1) {
    const pendientes = (
      await dbOffline.outbox.where('estado').anyOf('pendiente', 'error').sortBy('creada_en')
    ).slice(0, 50);
    if (!pendientes.length) return;

    const operaciones = [];
    for (const fila of pendientes) {
      const payload = (await abrirPaquete<Record<string, unknown>>(fila)) ?? {};
      operaciones.push({ operacion_id: fila.id, tipo: fila.tipo, payload, ocurrida_en: fila.creada_en });
    }

    const { data } = await api.post('/sync/push', { operaciones });
    for (const resultado of data.resultados as ResultadoPushApi[]) {
      const fila = pendientes.find((f) => f.id === resultado.operacion_id);
      if (!fila) continue;

      if (resultado.estado === 'ok') {
        await dbOffline.outbox.delete(fila.id);
        const entidad = resultado.entidad;
        if (entidad?.id_local && entidad.id !== undefined && entidad.id !== null) {
          await guardarIdLocal(entidad.tabla ?? fila.tipo, String(entidad.id_local), entidad.id);
        }
      } else if (resultado.estado === 'en_proceso') {
        await dbOffline.outbox.update(fila.id, {
          intentos: fila.intentos + 1,
          detalle: resultado.detalle ?? 'El servidor no confirmó; se reintentará.',
        });
      } else {
        await dbOffline.outbox.update(fila.id, {
          estado: resultado.estado,
          intentos: fila.intentos + 1,
          detalle: resultado.detalle ?? null,
        });
      }
    }

    if (pendientes.length < 50) return;
  }
}

async function pullCambios(): Promise<void> {
  let cursor = (await leerMeta<number>(CLAVES_META.cursor)) ?? 0;
  for (let pagina = 0; pagina < 20; pagina += 1) {
    const { data } = await api.get('/sync/cambios', { params: { desde: cursor, limite: 500 } });
    const cambios = (data.cambios ?? []) as CambioApi[];
    for (const cambio of cambios) {
      if (cambio.op === 'D') {
        await dbOffline.espejo.delete(`${cambio.tabla}:${cambio.pk}`);
      } else {
        await marcarTablaSucia(cambio.tabla);
      }
    }
    cursor = data.cursor as number;
    await escribirMeta(CLAVES_META.cursor, cursor);
    if (!data.hay_mas) break;
  }
}

let corriendo = false;
let reintento: number | null = null;

function programarReintento(): void {
  if (reintento !== null) return;
  reintento = window.setTimeout(() => {
    reintento = null;
    void sincronizar();
  }, 15_000);
}

function limpiarReintento(): void {
  if (reintento !== null) {
    window.clearTimeout(reintento);
    reintento = null;
  }
}

export async function sincronizar(): Promise<void> {
  if (corriendo) return;
  if (!localStorage.getItem('token')) return;
  if (!hayClave()) return;
  if (typeof navigator !== 'undefined' && !navigator.onLine) {
    actualizar({ sinConexion: true });
    programarReintento();
    return;
  }

  corriendo = true;
  actualizar({ sincronizando: true });
  try {
    await pushPendientes();
    await pullCambios();
    await escribirMeta(CLAVES_META.ultimaSync, new Date().toISOString());
    actualizar({ sinConexion: false });
    limpiarReintento();
  } catch (error) {
    if (!(error as { response?: unknown })?.response) {
      actualizar({ sinConexion: true });
      programarReintento();
    }
  } finally {
    corriendo = false;
    actualizar({ sincronizando: false, ultimaSync: await leerMeta<string>(CLAVES_META.ultimaSync) });
    await refrescarContadores();
  }
}

// ---------------------------------------------------------------------------
// Ciclo de vida del motor
// ---------------------------------------------------------------------------
let iniciado = false;
let intervalo: number | null = null;
let ultimaSyncDisparada = 0;

function alVolverRed(): void {
  void sincronizar();
}

function alCambiarVisibilidad(): void {
  if (document.visibilityState !== 'visible') return;
  const ahora = Date.now();
  if (ahora - ultimaSyncDisparada > 2 * 60 * 1000) {
    ultimaSyncDisparada = ahora;
    void sincronizar();
  }
}

export function iniciarMotorSync(): void {
  if (!OFFLINE_HABILITADO) return;
  void refrescarContadores();
  // Aunque el motor ya esté andando, un arranque nuevo (p. ej. desbloqueo con
  // PIN) dispara un intento inmediato: si quedó bloqueado antes, no sincronizó.
  void sincronizar();
  if (iniciado) return;
  iniciado = true;
  window.addEventListener('online', alVolverRed);
  document.addEventListener('visibilitychange', alCambiarVisibilidad);
  intervalo = window.setInterval(() => void sincronizar(), 60_000);
}

export function detenerMotorSync(): void {
  if (!iniciado) return;
  iniciado = false;
  limpiarReintento();
  window.removeEventListener('online', alVolverRed);
  document.removeEventListener('visibilitychange', alCambiarVisibilidad);
  if (intervalo !== null) {
    window.clearInterval(intervalo);
    intervalo = null;
  }
}
