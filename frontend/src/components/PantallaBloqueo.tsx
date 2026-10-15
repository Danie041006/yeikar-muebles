import { useState } from 'react';
import { LockKeyhole, TriangleAlert, WifiOff } from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import { resumenSesion } from '../offline/sesion';

/**
 * Pantalla de bloqueo del modo offline: hay sesión cacheada protegida con PIN
 * y no se pudo leer la copia local (sin red o app reabierta).
 */
export default function PantallaBloqueo() {
  const { resumen, desbloquear, logout } = useAuth();
  const [pin, setPin] = useState('');
  const [error, setError] = useState('');
  const [verificando, setVerificando] = useState(false);

  const confirmar = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!pin.trim()) return;
    setError('');
    setVerificando(true);
    const ok = await desbloquear(pin);
    if (!ok) {
      setPin('');
      const sigue = await resumenSesion();
      setError(
        sigue
          ? 'PIN incorrecto. Inténtalo de nuevo.'
          : 'Demasiados intentos: la copia local se borró. Entra con conexión.',
      );
    }
    setVerificando(false);
  };

  return (
    <main className="premium-grid flex min-h-[100dvh] items-center justify-center bg-yeikar-tertiary p-6">
      <form
        onSubmit={confirmar}
        className="w-full max-w-sm rounded-3xl border border-yeikar-secondary-light/10 bg-white/85 p-8 text-center shadow-modal backdrop-blur-xl"
      >
        <div className="mx-auto mb-5 flex h-12 w-12 items-center justify-center rounded-xl border border-yeikar-primary/20 bg-yeikar-primary/10 text-yeikar-primary-dark">
          <LockKeyhole className="h-5 w-5" strokeWidth={1.8} />
        </div>
        <p className="eyebrow mb-2">Modo sin conexión</p>
        <h1 className="font-headline text-2xl font-semibold tracking-[-0.03em] text-yeikar-neutral">
          {resumen?.nombre || resumen?.nombre_usuario || 'Tu sesión'}
        </h1>
        <p className="mt-2 flex items-center justify-center gap-1.5 text-xs text-yeikar-neutral/50">
          <WifiOff className="h-3.5 w-3.5" /> Sin internet — entra con tu PIN para trabajar
        </p>

        {error && (
          <div className="mt-5 flex items-start gap-2.5 rounded-2xl border border-rose-200/80 bg-rose-50/80 px-4 py-3 text-left text-xs text-rose-800" role="alert">
            <TriangleAlert className="mt-0.5 h-3.5 w-3.5 shrink-0" />
            <span>{error}</span>
          </div>
        )}

        <input
          type="password"
          inputMode="numeric"
          autoComplete="off"
          autoFocus
          value={pin}
          onChange={(event) => setPin(event.target.value.replace(/\D/g, '').slice(0, 8))}
          disabled={verificando}
          placeholder="PIN"
          aria-label="PIN local"
          className="input mt-5 h-14 text-center font-mono text-2xl tracking-[0.5em]"
        />

        <button
          type="submit"
          disabled={verificando || pin.length < 4}
          className="mt-4 flex h-12 w-full items-center justify-center rounded-xl bg-yeikar-primary px-5 font-headline text-sm font-bold text-yeikar-neutral shadow-gold transition-all hover:bg-yeikar-primary-light disabled:cursor-not-allowed disabled:opacity-60"
        >
          {verificando ? 'Verificando…' : 'Desbloquear y trabajar'}
        </button>

        <button
          type="button"
          onClick={() => void logout()}
          className="mt-4 w-full text-center text-xs font-bold text-yeikar-neutral/45 transition-colors hover:text-yeikar-neutral"
        >
          Usar otra cuenta
        </button>
      </form>
    </main>
  );
}
