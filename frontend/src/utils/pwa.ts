import { registerSW } from 'virtual:pwa-register';

type Suscriptor = () => void;

let aplicarActualizacion: ((reloadPage?: boolean) => Promise<void>) | null = null;
let actualizacionPendiente = false;
let listoOffline = false;

const suscriptoresActualizacion = new Set<Suscriptor>();
const suscriptoresOffline = new Set<Suscriptor>();

export function registrarServiceWorker() {
  try {
    aplicarActualizacion = registerSW({
      immediate: true,
      onNeedRefresh() {
        if (actualizacionPendiente) return;
        actualizacionPendiente = true;
        suscriptoresActualizacion.forEach((fn) => fn());
      },
      onOfflineReady() {
        if (listoOffline) return;
        listoOffline = true;
        suscriptoresOffline.forEach((fn) => fn());
      },
    });
  } catch {
    // Navegador sin soporte de Service Worker: la app funciona igual, sin offline.
  }
}

export function suscribirActualizacion(fn: Suscriptor): () => void {
  suscriptoresActualizacion.add(fn);
  if (actualizacionPendiente) fn();
  return () => {
    suscriptoresActualizacion.delete(fn);
  };
}

export function suscribirListoOffline(fn: Suscriptor): () => void {
  suscriptoresOffline.add(fn);
  if (listoOffline) fn();
  return () => {
    suscriptoresOffline.delete(fn);
  };
}

export async function aplicarActualizacionSW() {
  if (aplicarActualizacion) {
    await aplicarActualizacion(true);
    return;
  }
  window.location.reload();
}
