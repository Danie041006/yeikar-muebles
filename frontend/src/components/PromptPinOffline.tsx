import { useEffect, useState } from 'react';
import { ShieldCheck, TriangleAlert, X } from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import { cifradoDisponible } from '../offline/cifrado';
import { tienePin } from '../offline/sesion';
import { OFFLINE_HABILITADO } from '../offline/interruptor';

/**
 * Invita a configurar el PIN local tras iniciar sesión (una vez por usuario).
 * El PIN es lo que permite entrar y leer los datos cuando no hay internet.
 */
export default function PromptPinOffline() {
  const { user, configurarPin } = useAuth();
  const [visible, setVisible] = useState(false);
  const [pin, setPin] = useState('');
  const [pin2, setPin2] = useState('');
  const [error, setError] = useState('');
  const [guardando, setGuardando] = useState(false);
  const [listo, setListo] = useState(false);

  useEffect(() => {
    let cancelado = false;
    (async () => {
      try {
        if (!user || !cifradoDisponible()) return;
        if (await tienePin()) return;
        if (localStorage.getItem(`yeikar_pin_omitido_${user.id}`)) return;
        if (!cancelado) setVisible(true);
      } catch {
        /* sin IndexedDB no hay modo offline que ofrecer */
      }
    })();
    return () => {
      cancelado = true;
    };
  }, [user]);

  if (!OFFLINE_HABILITADO) return null;
  if (!visible) return null;

  const guardar = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!/^\d{4,8}$/.test(pin)) {
      setError('El PIN debe tener entre 4 y 8 dígitos.');
      return;
    }
    if (pin !== pin2) {
      setError('Los PIN no coinciden.');
      return;
    }
    setError('');
    setGuardando(true);
    try {
      await configurarPin(pin);
      setListo(true);
      setTimeout(() => setVisible(false), 1600);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'No se pudo guardar el PIN.');
    } finally {
      setGuardando(false);
    }
  };

  const omitir = () => {
    if (user) localStorage.setItem(`yeikar_pin_omitido_${user.id}`, '1');
    setVisible(false);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-yeikar-neutral/45 p-4 backdrop-blur-sm" role="dialog" aria-modal="true">
      <form onSubmit={guardar} className="w-full max-w-sm rounded-3xl border border-yeikar-secondary-light/10 bg-white p-7 shadow-modal">
        <div className="mb-4 flex items-start justify-between">
          <div className="flex h-11 w-11 items-center justify-center rounded-xl border border-yeikar-primary/20 bg-yeikar-primary/10 text-yeikar-primary-dark">
            <ShieldCheck className="h-5 w-5" strokeWidth={1.8} />
          </div>
          <button type="button" onClick={omitir} aria-label="Cerrar" className="rounded-lg p-2 text-yeikar-neutral/35 transition-colors hover:bg-yeikar-tertiary hover:text-yeikar-neutral">
            <X className="h-4 w-4" />
          </button>
        </div>

        <p className="eyebrow mb-1.5">Modo sin conexión</p>
        <h2 className="font-headline text-xl font-semibold tracking-[-0.03em] text-yeikar-neutral">
          Configura tu PIN para trabajar si se va la luz
        </h2>
        <p className="mt-2 text-xs leading-relaxed text-yeikar-neutral/55">
          Con tu PIN entras y sigues registrando producción, pedidos y cobros sin internet en este equipo.
          Tus datos locales quedan cifrados con él.
        </p>

        {listo ? (
          <div className="mt-5 rounded-2xl border border-emerald-200/80 bg-emerald-50/80 px-4 py-3 text-sm font-bold text-emerald-800">
            PIN activado. Ya puedes trabajar sin conexión.
          </div>
        ) : (
          <>
            {error && (
              <div className="mt-4 flex items-start gap-2.5 rounded-2xl border border-rose-200/80 bg-rose-50/80 px-4 py-3 text-xs text-rose-800" role="alert">
                <TriangleAlert className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                <span>{error}</span>
              </div>
            )}

            <label className="label mt-4" htmlFor="pin-nuevo">PIN (4 a 8 dígitos)</label>
            <input
              id="pin-nuevo"
              type="password"
              inputMode="numeric"
              autoComplete="new-password"
              value={pin}
              onChange={(e) => setPin(e.target.value.replace(/\D/g, '').slice(0, 8))}
              className="input h-12 text-center font-mono text-xl tracking-[0.4em]"
            />

            <label className="label mt-3" htmlFor="pin-confirma">Repite el PIN</label>
            <input
              id="pin-confirma"
              type="password"
              inputMode="numeric"
              autoComplete="new-password"
              value={pin2}
              onChange={(e) => setPin2(e.target.value.replace(/\D/g, '').slice(0, 8))}
              className="input h-12 text-center font-mono text-xl tracking-[0.4em]"
            />

            <div className="mt-5 flex gap-2">
              <button
                type="button"
                onClick={omitir}
                className="h-11 shrink-0 rounded-xl border border-yeikar-secondary-light/20 px-4 font-headline text-xs font-bold text-yeikar-neutral/60 transition-colors hover:text-yeikar-neutral"
              >
                Ahora no
              </button>
              <button
                type="submit"
                disabled={guardando || pin.length < 4}
                className="h-11 flex-1 rounded-xl bg-yeikar-primary font-headline text-sm font-bold text-yeikar-neutral shadow-gold transition-all hover:bg-yeikar-primary-light disabled:cursor-not-allowed disabled:opacity-60"
              >
                {guardando ? 'Guardando…' : 'Activar PIN'}
              </button>
            </div>
          </>
        )}
      </form>
    </div>
  );
}
