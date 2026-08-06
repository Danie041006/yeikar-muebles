import { useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import axios from 'axios';
import { ArrowRight, Check, Eye, EyeOff, LockKeyhole, ShieldCheck, Sparkles, TriangleAlert } from 'lucide-react';
import { motion } from 'framer-motion';

import { useAuth } from '../context/AuthContext';
import { API_URL } from '../services/api';

export default function Login() {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();
  const location = useLocation();
  const { refresh } = useAuth();
  const destination = (location.state as { from?: { pathname?: string } } | null)?.from?.pathname || '/dashboard';

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!username.trim() || !password) {
      setError('Ingresa tu usuario y contraseña para continuar.');
      return;
    }

    setError('');
    setLoading(true);
    try {
      const formData = new URLSearchParams();
      formData.append('username', username.trim());
      formData.append('password', password);
      const response = await axios.post(`${API_URL}/api/auth/login`, formData, {
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      });

      if (!response.data.access_token) {
        setError('No pudimos validar la respuesta del servidor. Inténtalo de nuevo.');
        return;
      }

      localStorage.setItem('token', response.data.access_token);
      if (response.data.refresh_token) localStorage.setItem('refresh_token', response.data.refresh_token);
      await refresh();
      navigate(destination, { replace: true });
    } catch (err: unknown) {
      if (axios.isAxiosError(err)) {
        if (err.response?.status === 401) setError('Usuario o contraseña incorrectos.');
        else if (err.code === 'ERR_NETWORK') setError('No pudimos conectar con YEIKAR. Revisa tu conexión.');
        else setError('El servicio no está disponible en este momento. Inténtalo nuevamente.');
      } else {
        setError('Ocurrió un error inesperado. Inténtalo nuevamente.');
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <main className="relative min-h-screen overflow-hidden bg-yeikar-tertiary text-yeikar-neutral">
      <div className="pointer-events-none absolute inset-0 premium-grid opacity-60" />
      <div className="relative grid min-h-screen lg:grid-cols-[1.08fr_0.92fr]">
        <section className="relative hidden overflow-hidden bg-gradient-to-br from-yeikar-neutral via-yeikar-secondary to-yeikar-neutral-dark px-10 py-10 text-white lg:flex lg:flex-col lg:justify-between xl:px-16 xl:py-12">
          <div className="pointer-events-none absolute -right-28 top-1/2 h-[620px] w-[620px] -translate-y-1/2 rounded-full border border-yeikar-primary/10" />
          <div className="pointer-events-none absolute -right-10 top-1/2 h-[440px] w-[440px] -translate-y-1/2 rounded-full border border-yeikar-primary/10" />
          <div className="pointer-events-none absolute right-24 top-1/2 h-[260px] w-[260px] -translate-y-1/2 rounded-full border border-yeikar-primary/15" />
          <div className="pointer-events-none absolute inset-y-0 right-1/3 w-px bg-gradient-to-b from-transparent via-yeikar-primary/20 to-transparent" />

          <div className="relative z-10 flex items-center gap-3">
            <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-yeikar-primary font-headline text-2xl font-black text-yeikar-neutral shadow-gold">Y</div>
            <div>
              <p className="font-headline text-lg font-black tracking-[0.24em]">YEIKAR</p>
              <p className="mt-1 font-mono text-[9px] uppercase tracking-[0.2em] text-yeikar-primary/70">Atelier operativo</p>
            </div>
          </div>

          <div className="relative z-10 max-w-xl pb-8 xl:pb-16">
            <div className="mb-8 flex items-center gap-3 text-yeikar-primary/75">
              <span className="h-px w-10 bg-yeikar-primary/60" />
              <span className="font-mono text-[10px] font-bold uppercase tracking-[0.2em]">Control con intención</span>
            </div>
            <h1 className="max-w-2xl font-headline text-5xl font-semibold leading-[0.98] tracking-[-0.055em] text-white xl:text-7xl">
              Cada detalle cuenta.<br />
              <span className="text-yeikar-primary">Cada entrega también.</span>
            </h1>
            <p className="mt-8 max-w-md text-base leading-relaxed text-white/55">
              Una vista precisa de tu taller, tus pedidos y la salud de tu negocio. Menos ruido. Más decisiones correctas.
            </p>

            <div className="mt-12 grid max-w-md grid-cols-2 gap-3">
              {[
                { label: 'Operación', value: 'En un solo lugar' },
                { label: 'Visibilidad', value: 'De principio a fin' },
              ].map((item) => (
                <div key={item.label} className="rounded-2xl border border-white/10 bg-white/[0.045] p-4 backdrop-blur-sm">
                  <p className="font-mono text-[9px] uppercase tracking-[0.16em] text-white/35">{item.label}</p>
                  <p className="mt-2 font-headline text-sm font-semibold text-white/80">{item.value}</p>
                </div>
              ))}
            </div>
          </div>

          <div className="relative z-10 flex items-center justify-between border-t border-white/10 pt-5 text-[10px] text-white/35">
            <span className="font-mono uppercase tracking-[0.15em]">Sistema de gestión para mueblería</span>
            <span className="font-mono">01 / 04</span>
          </div>
        </section>

        <section className="relative flex min-h-screen items-center justify-center px-5 py-8 sm:px-10 lg:px-14 xl:px-24">
          <motion.div
            initial={{ opacity: 0, y: 18 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.55, ease: [0.16, 1, 0.3, 1] }}
            className="w-full max-w-[430px]"
          >
            <div className="mb-10 flex items-center justify-between lg:hidden">
              <div className="flex items-center gap-3">
                <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-yeikar-primary font-headline text-xl font-black text-yeikar-neutral shadow-gold">Y</div>
                <div>
                  <p className="font-headline text-base font-black tracking-[0.22em] text-yeikar-secondary">YEIKAR</p>
                  <p className="mt-0.5 font-mono text-[8px] uppercase tracking-[0.18em] text-yeikar-primary-dark">Atelier ERP</p>
                </div>
              </div>
              <span className="rounded-full border border-emerald-700/10 bg-emerald-50 px-3 py-1.5 text-[10px] font-bold text-emerald-800">Seguro</span>
            </div>

            <div className="mb-9">
              <div className="mb-5 flex h-11 w-11 items-center justify-center rounded-xl border border-yeikar-primary/20 bg-yeikar-primary/10 text-yeikar-primary-dark">
                <LockKeyhole className="h-5 w-5" strokeWidth={1.8} />
              </div>
              <p className="eyebrow mb-2">Acceso privado</p>
              <h2 className="font-headline text-4xl font-semibold leading-tight tracking-[-0.045em] text-yeikar-neutral sm:text-[44px]">Bienvenido de vuelta.</h2>
              <p className="mt-3 max-w-sm text-sm leading-relaxed text-yeikar-neutral/55">Ingresa a tu espacio de trabajo y mantén cada área de tu operación en movimiento.</p>
            </div>

            {error && (
              <div className="mb-6 flex items-start gap-3 rounded-2xl border border-rose-200/80 bg-rose-50/80 px-4 py-3.5 text-sm text-rose-800" role="alert" aria-live="polite">
                <TriangleAlert className="mt-0.5 h-4 w-4 shrink-0" />
                <span>{error}</span>
              </div>
            )}

            <form onSubmit={handleSubmit} className="space-y-5" noValidate>
              <div>
                <label htmlFor="username" className="label">Usuario</label>
                <input
                  id="username"
                  type="text"
                  value={username}
                  onChange={(event) => setUsername(event.target.value)}
                  disabled={loading}
                  className="input h-12 bg-white/80"
                  placeholder="Tu usuario"
                  autoComplete="username"
                  autoFocus
                />
              </div>

              <div>
                <div className="mb-1.5 flex items-center justify-between">
                  <label htmlFor="password" className="label mb-0">Contraseña</label>
                  <span className="text-[11px] text-yeikar-neutral/40">Acceso seguro</span>
                </div>
                <div className="relative">
                  <input
                    id="password"
                    type={showPassword ? 'text' : 'password'}
                    value={password}
                    onChange={(event) => setPassword(event.target.value)}
                    disabled={loading}
                    className="input h-12 bg-white/80 pr-12"
                    placeholder="Tu contraseña"
                    autoComplete="current-password"
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword((visible) => !visible)}
                    className="absolute right-2 top-1/2 -translate-y-1/2 rounded-lg p-2 text-yeikar-neutral/40 transition-colors hover:bg-yeikar-tertiary hover:text-yeikar-secondary"
                    aria-label={showPassword ? 'Ocultar contraseña' : 'Mostrar contraseña'}
                  >
                    {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                  </button>
                </div>
              </div>

              <button
                type="submit"
                disabled={loading}
                className="group flex h-12 w-full items-center justify-center gap-3 rounded-xl bg-yeikar-primary px-5 font-headline text-sm font-bold text-yeikar-neutral shadow-gold transition-all duration-200 hover:bg-yeikar-primary-light hover:shadow-lift disabled:cursor-not-allowed disabled:opacity-60"
              >
                {loading ? (
                  <span className="flex items-center gap-2"><span className="h-4 w-4 animate-spin rounded-full border-2 border-yeikar-neutral/25 border-t-yeikar-neutral" /> Validando acceso...</span>
                ) : (
                  <>Entrar al espacio de trabajo <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-1" /></>
                )}
              </button>
            </form>

            <div className="mt-9 flex items-center gap-3 border-t border-yeikar-secondary-light/10 pt-5 text-[11px] text-yeikar-neutral/45">
              <ShieldCheck className="h-4 w-4 text-yeikar-primary-dark" />
              <span>Tu sesión está protegida y tus datos permanecen privados.</span>
            </div>

            <div className="mt-8 flex items-center justify-between text-[10px] text-yeikar-neutral/35">
              <span className="flex items-center gap-1.5"><Check className="h-3.5 w-3.5 text-yeikar-primary-dark" /> Operación conectada</span>
              <span className="flex items-center gap-1.5"><Sparkles className="h-3.5 w-3.5 text-yeikar-primary-dark" /> YEIKAR {new Date().getFullYear()}</span>
            </div>
          </motion.div>
        </section>
      </div>
    </main>
  );
}
