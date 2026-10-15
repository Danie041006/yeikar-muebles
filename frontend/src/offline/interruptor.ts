// Interruptor del modo offline.
//
// Producción (Vercel) NO define VITE_OFFLINE_MODE → todo el modo offline queda
// apagado y el comportamiento es EXACTAMENTE el de antes (sin PIN, sin espejo,
// sin cola, sin llamadas a /sync). Se enciende en:
//   - dev:            frontend/.env.development  (VITE_OFFLINE_MODE=true)
//   - build de prueba: npm run build:offline     (usa .env.offline)
//   - VPS (cuando toque): variable VITE_OFFLINE_MODE=true en el proyecto.
export const OFFLINE_HABILITADO = (import.meta.env.VITE_OFFLINE_MODE ?? '') === 'true';
