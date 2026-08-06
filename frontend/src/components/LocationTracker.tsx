import { useEffect, useRef, useState } from 'react';
import { CheckCircle2, ExternalLink, MapPin, Navigation, Pause, Play, TriangleAlert } from 'lucide-react';
import { envioService, EnvioUbicacion } from '../services/envioService';

interface LocationTrackerProps {
  envioId: number;
  estado: string;
}

const UPDATE_INTERVAL_MS = 30_000;

export default function LocationTracker({ envioId, estado }: LocationTrackerProps) {
  const [active, setActive] = useState(false);
  const [latest, setLatest] = useState<EnvioUbicacion | null>(null);
  const [error, setError] = useState('');
  const watchId = useRef<number | null>(null);
  const lastSentAt = useRef(0);
  const sequence = useRef(0);

  useEffect(() => {
    let mounted = true;
    const loadLatest = async () => {
      try {
        const location = await envioService.getLatestLocation(envioId);
        if (mounted) setLatest(location);
      } catch {
        // A driver without this assignment must not learn whether another shipment exists.
      }
    };
    loadLatest();
    const interval = window.setInterval(loadLatest, UPDATE_INTERVAL_MS);
    return () => {
      mounted = false;
      window.clearInterval(interval);
    };
  }, [envioId]);

  useEffect(() => {
    if (!active || estado === 'ENTREGADO') return;
    if (!navigator.geolocation) {
      setError('Este navegador no permite ubicación.');
      setActive(false);
      return;
    }

    watchId.current = navigator.geolocation.watchPosition(
      async (position) => {
        if (Date.now() - lastSentAt.current < UPDATE_INTERVAL_MS) return;
        lastSentAt.current = Date.now();
        sequence.current += 1;
        try {
          const location = await envioService.reportLocation(envioId, {
            latitud: position.coords.latitude,
            longitud: position.coords.longitude,
            precision_m: position.coords.accuracy,
            velocidad: position.coords.speed ?? undefined,
            rumbo: position.coords.heading ?? undefined,
            capturada_en: new Date(position.timestamp).toISOString(),
            fuente: 'web',
            secuencia: sequence.current,
          });
          setLatest(location);
          setError('');
        } catch (requestError: any) {
          setError(requestError?.response?.data?.detail || 'No se pudo sincronizar la ubicación.');
        }
      },
      (positionError) => {
        setError(positionError.message || 'No se pudo obtener la ubicación.');
      },
      { enableHighAccuracy: true, maximumAge: 15_000, timeout: 20_000 },
    );

    return () => {
      if (watchId.current !== null) navigator.geolocation.clearWatch(watchId.current);
      watchId.current = null;
    };
  }, [active, envioId, estado]);

  if (estado === 'ENTREGADO') {
    return (
      <div className="flex items-center gap-2 rounded-xl border border-emerald-200/70 bg-emerald-50/60 px-3 py-2 text-[11px] font-semibold text-emerald-800">
        <CheckCircle2 className="h-3.5 w-3.5" /> Seguimiento finalizado con la entrega
      </div>
    );
  }

  const latestLabel = latest ? new Date(latest.recibida_en).toLocaleTimeString('es-CO', { hour: '2-digit', minute: '2-digit' }) : null;

  return (
    <div className="rounded-xl border border-yeikar-primary/15 bg-yeikar-primary/[0.045] p-3">
      <div className="flex items-center justify-between gap-3">
        <div className="flex min-w-0 items-center gap-2">
          <span className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-lg ${active ? 'bg-yeikar-primary text-yeikar-neutral' : 'bg-white text-yeikar-primary-dark'}`}>
            <Navigation className={`h-3.5 w-3.5 ${active ? 'animate-pulse' : ''}`} />
          </span>
          <div className="min-w-0">
            <p className="text-[11px] font-bold text-yeikar-secondary">{active ? 'Monitoreo activo' : 'Monitoreo de recorrido'}</p>
            <p className="truncate text-[10px] text-yeikar-neutral/50">
              {latestLabel ? `Última ubicación · ${latestLabel}` : 'Aún no hay ubicación recibida'}
            </p>
          </div>
        </div>
        <button
          type="button"
          onClick={() => { setError(''); setActive((value) => !value); }}
          className={`inline-flex shrink-0 items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-[10px] font-bold transition-colors ${active ? 'border border-yeikar-secondary/15 bg-white text-yeikar-secondary hover:bg-yeikar-tertiary' : 'bg-yeikar-primary text-yeikar-neutral hover:bg-yeikar-primary-light'}`}
        >
          {active ? <Pause className="h-3 w-3" /> : <Play className="h-3 w-3" />}
          {active ? 'Pausar' : 'Iniciar'}
        </button>
      </div>
      {latest && (
        <a
          className="mt-2 flex items-center gap-1 text-[10px] font-semibold text-yeikar-primary-dark hover:underline"
          href={`https://www.openstreetmap.org/?mlat=${latest.latitud}&mlon=${latest.longitud}#map=16/${latest.latitud}/${latest.longitud}`}
          target="_blank"
          rel="noreferrer"
        >
          <MapPin className="h-3 w-3" /> Ver última posición <ExternalLink className="h-3 w-3" />
        </a>
      )}
      {error && (
        <p className="mt-2 flex items-start gap-1.5 text-[10px] leading-relaxed text-rose-700">
          <TriangleAlert className="mt-0.5 h-3 w-3 shrink-0" /> {error}
        </p>
      )}
    </div>
  );
}
