// Sesión offline: cacheo del perfil/permisos y PIN local.
//
// - `guardarSesion` guarda el usuario de `/me` cifrado con la clave del
//   dispositivo, más un resumen en claro (nombre) para poder saludar y
//   mostrar la pantalla de PIN sin desbloquear.
// - `configurarPin` envuelve la clave del dispositivo con una llave derivada
//   del PIN y BORRA la copia clara: sin PIN no se pueden leer los datos.
// - `desbloquearConPin` verifica el PIN, desenvuelve la clave y la activa.
//   5 intentos fallidos borran toda la copia local.
// - `limpiarOffline` (logout) borra IndexedDB completo.

import {
  activarClave,
  bloquearClave,
  cifradoDisponible,
  cifrarJson,
  crearCredencialPin,
  descifrarJson,
  exportarClave,
  generarClaveDispositivo,
  hayClave,
  importarClave,
  claveActual,
  verificarPin,
  type BlobCifrado,
  type CredencialPin,
} from './cifrado';
import { CLAVES_META, dbOffline, leerMeta, escribirMeta } from './db';

export interface ResumenSesion {
  usuario_id: number;
  nombre_usuario: string;
  nombre: string | null;
}

type ClaveGuardada =
  | { modo: 'clara'; clave: string }
  | ({ modo: 'pin'; envuelta: BlobCifrado } & CredencialPin);

const MAX_INTENTOS_PIN = 5;

export async function guardarSesion(usuario: { id: number; nombre_usuario: string; nombre?: string | null }): Promise<void> {
  const resumen: ResumenSesion = {
    usuario_id: usuario.id,
    nombre_usuario: usuario.nombre_usuario,
    nombre: usuario.nombre ?? null,
  };
  await escribirMeta(CLAVES_META.sesionResumen, resumen);
  if (hayClave()) {
    await escribirMeta(CLAVES_META.sesionCache, await cifrarJson(usuario));
  }
}

export async function resumenSesion(): Promise<ResumenSesion | null> {
  return leerMeta<ResumenSesion>(CLAVES_META.sesionResumen);
}

export async function leerSesionCache<T>(): Promise<T | null> {
  const blob = await leerMeta<BlobCifrado>(CLAVES_META.sesionCache);
  if (!blob || !hayClave()) return null;
  return descifrarJson<T>(blob);
}

async function claveGuardada(): Promise<ClaveGuardada | null> {
  return leerMeta<ClaveGuardada>(CLAVES_META.claveDispositivo);
}

export async function tienePin(): Promise<boolean> {
  return (await claveGuardada())?.modo === 'pin';
}

export async function sesionBloqueada(): Promise<boolean> {
  return (await tienePin()) && !hayClave();
}

/**
 * Deja la clave del dispositivo activa si se puede sin PIN:
 *  - ya activa → true
 *  - guardada en claro (o sin crear) → la carga/crea y activa → true
 *  - envuelta con PIN → false (hace falta desbloquearConPin)
 */
export async function asegurarClaveDispositivo(): Promise<boolean> {
  if (!cifradoDisponible()) return false;
  if (hayClave()) return true;

  const guardada = await claveGuardada();
  if (!guardada) {
    const clave = await generarClaveDispositivo();
    await escribirMeta(CLAVES_META.claveDispositivo, { modo: 'clara', clave: await exportarClave(clave) });
    activarClave(clave);
    return true;
  }
  if (guardada.modo === 'clara') {
    activarClave(await importarClave(guardada.clave));
    return true;
  }
  return false;
}

export async function configurarPin(pin: string): Promise<void> {
  if (!cifradoDisponible()) throw new Error('Este navegador no soporta el modo offline seguro.');

  if (!hayClave()) {
    const activada = await asegurarClaveDispositivo();
    if (!activada) throw new Error('Desbloquea primero con tu PIN actual.');
  }

  const { credencial, clave: clavePin } = await crearCredencialPin(pin);
  const envuelta = await cifrarJson(await exportarClave(claveActual()), clavePin);
  await escribirMeta(CLAVES_META.claveDispositivo, { modo: 'pin', envuelta, ...credencial });
  await escribirMeta(CLAVES_META.pinIntentos, 0);
}

export async function desbloquearConPin(pin: string): Promise<boolean> {
  const guardada = await claveGuardada();
  if (!guardada || guardada.modo !== 'pin') return false;

  const clavePin = await verificarPin(pin, guardada);
  if (!clavePin) {
    await registrarIntentoFallido();
    return false;
  }

  const claveB64 = await descifrarJson<string>(guardada.envuelta, clavePin);
  if (!claveB64) return false;
  activarClave(await importarClave(claveB64));
  await escribirMeta(CLAVES_META.pinIntentos, 0);
  return true;
}

async function registrarIntentoFallido(): Promise<void> {
  const intentos = ((await leerMeta<number>(CLAVES_META.pinIntentos)) ?? 0) + 1;
  await escribirMeta(CLAVES_META.pinIntentos, intentos);
  if (intentos >= MAX_INTENTOS_PIN) await limpiarOffline();
}

export async function limpiarOffline(): Promise<void> {
  bloquearClave();
  try {
    await dbOffline.delete();
  } catch {
    /* IndexedDB no disponible: nada que limpiar */
  }
}
