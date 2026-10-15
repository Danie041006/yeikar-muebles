import { useEffect, useState, useSyncExternalStore } from 'react';
import { CloudOff, RefreshCw, TriangleAlert, X } from 'lucide-react';
import { useOnline } from '../hooks/useOnline';
import type { FilaOutbox } from '../offline/db';
import { OFFLINE_HABILITADO } from '../offline/interruptor';
import {
  descartarOperacion,
  estadoSync,
  listarConflictos,
  sincronizar,
  suscribirSync,
} from '../offline/sync';

/**
 * Barra de estado de sincronización: aparece solo cuando hay algo que contar
 * (sin conexión, pendientes, conflictos o sincronizando).
 */
export default function OfflineIndicator() {
  const online = useOnline();
  const estado = useSyncExternalStore(suscribirSync, estadoSync);
  const [abierto, setAbierto] = useState(false);
  const [conflictos, setConflictos] = useState<FilaOutbox[]>([]);

  useEffect(() => {
    if (abierto) void listarConflictos().then(setConflictos);
  }, [abierto, estado.conflictos]);

  if (!OFFLINE_HABILITADO) return null;

  const sinRed = !online || estado.sinConexion;
  const total = estado.pendientes + estado.conflictos;
  if (!sinRed && total === 0 && !estado.sincronizando) return null;

  const color = sinRed
    ? 'border-amber-300/60 bg-amber-50/90 text-amber-900'
    : estado.conflictos > 0
      ? 'border-rose-300/60 bg-rose-50/90 text-rose-900'
      : 'border-sky-300/50 bg-sky-50/90 text-sky-900';

  return (
    <div className={`border-b px-4 py-2 text-xs sm:px-6 lg:px-8 ${color}`} role="status" aria-live="polite">
      <div className="mx-auto flex max-w-[1480px] flex-wrap items-center gap-x-3 gap-y-1.5">
        <span className="flex items-center gap-1.5 font-bold">
          {sinRed ? <CloudOff className="h-3.5 w-3.5" /> : <RefreshCw className={`h-3.5 w-3.5 ${estado.sincronizando ? 'animate-spin' : ''}`} />}
          {sinRed
            ? 'Sin conexión — trabajando local'
            : estado.sincronizando
              ? 'Sincronizando…'
              : 'Conectado'}
        </span>

        {estado.pendientes > 0 && (
          <span className="font-mono">{estado.pendientes} por sincronizar</span>
        )}

        {estado.conflictos > 0 && (
          <button type="button" onClick={() => setAbierto((v) => !v)} className="flex items-center gap-1 font-bold underline-offset-2 hover:underline">
            <TriangleAlert className="h-3.5 w-3.5" />
            {estado.conflictos} con problema
          </button>
        )}

        {estado.ultimaSync && !sinRed && total === 0 && (
          <span className="text-current/60">
            Última: {new Date(estado.ultimaSync).toLocaleTimeString('es-VE', { hour: '2-digit', minute: '2-digit' })}
          </span>
        )}

        {online && (
          <button
            type="button"
            onClick={() => void sincronizar()}
            disabled={estado.sincronizando}
            className="ml-auto rounded-full border border-current/20 px-2.5 py-0.5 font-bold transition-opacity hover:opacity-75 disabled:opacity-40"
          >
            Sincronizar ahora
          </button>
        )}
      </div>

      {abierto && conflictos.length > 0 && (
        <ul className="mx-auto mt-2 max-w-[1480px] space-y-1.5">
          {conflictos.map((fila) => (
            <li key={fila.id} className="flex items-start gap-2 rounded-xl border border-current/15 bg-white/60 px-3 py-2">
              <div className="min-w-0 flex-1">
                <p className="font-mono text-[11px] font-bold">{fila.tipo}</p>
                <p className="text-[11px] opacity-80">{fila.detalle || 'El servidor rechazó la operación.'}</p>
              </div>
              <button
                type="button"
                onClick={() => void descartarOperacion(fila.id).then(() => listarConflictos().then(setConflictos))}
                title="Descartar esta operación"
                className="rounded-lg p-1 transition-colors hover:bg-current/10"
                aria-label="Descartar operación"
              >
                <X className="h-3.5 w-3.5" />
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
