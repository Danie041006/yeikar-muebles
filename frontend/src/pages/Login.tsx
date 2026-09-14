import { useEffect, useRef, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import axios from 'axios';
import { ArrowRight, Check, Eye, EyeOff, Fingerprint, LockKeyhole, ShieldCheck, Smartphone, Sparkles, TriangleAlert } from 'lucide-react';
import { motion } from 'framer-motion';
import { startAuthentication } from '@simplewebauthn/browser';

import { useAuth } from '../context/AuthContext';
import { API_URL } from '../services/api';

// Clave del sitio Turnstile (las dummy de Cloudflare en pruebas). Sin clave
// configurada no se renderiza widget nunca.
const TURNSTILE_SITE_KEY = (import.meta.env.VITE_TURNSTILE_SITE_KEY ?? '') as string;

declare global {
  interface Window {
    turnstile?: {
      render: (el: HTMLElement, opts: Record<string, unknown>) => void;
      reset: (id?: string) => void;
    };
  }
}

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

  // Captcha invisible: se activa cuando el backend lo exige tras fallos.
  const [captchaRequerido, setCaptchaRequerido] = useState(false);
  const [turnstileToken, setTurnstileToken] = useState('');
  const captchaBoxRef = useRef<HTMLDivElement>(null);
  const widgetCargado = useRef(false);

  // Paso 2 del login: código de la app autenticadora (o respaldo).
  const [ticket2FA, setTicket2FA] = useState('');
  const [codigo2FA, setCodigo2FA] = useState('');
  const [recordarEquipo, setRecordarEquipo] = useState(true);
  const [error2FA, setError2FA] = useState('');
  const [verificando, setVerificando] = useState(false);

  // Entrada con huella / Face ID / PIN del equipo (passkeys).
  const [cargandoHuella, setCargandoHuella] = useState(false);

  // Carga del script de Turnstile y render del widget solo cuando hace falta
  useEffect(() => {
    if (!captchaRequerido) return;
    const scriptId = 'cf-turnstile-script';
    if (!document.getElementById(scriptId)) {
      const script = document.createElement('script');
      script.id = scriptId;
      script.src = 'https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit';
      script.async = true;
      script.defer = true;
      document.head.appendChild(script);
    }
    const intento = setInterval(() => {
      if (window.turnstile && captchaBoxRef.current && !widgetCargado.current) {
        widgetCargado.current = true;
        window.turnstile.render(captchaBoxRef.current, {
          sitekey: TURNSTILE_SITE_KEY,
          callback: (token: string) => setTurnstileToken(token),
          'expired-callback': () => setTurnstileToken(''),
        });
        clearInterval(intento);
      }
    }, 200);
    return () => clearInterval(intento);
  }, [captchaRequerido]);

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!username.trim() || !password) {
      setError('Ingresa tu usuario y contraseña para continuar.');
      return;
    }
    if (captchaRequerido && !turnstileToken) {
      setError('Verifica que no eres un robot para continuar.');
      return;
    }

    setError('');
    setLoading(true);
    try {
      const formData = new URLSearchParams();
      formData.append('username', username.trim());
      formData.append('password', password);
      if (captchaRequerido && turnstileToken) formData.append('turnstile_token', turnstileToken);
      const response = await axios.post(`${API_URL}/api/auth/login`, formData, {
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      });

      // Contraseña correcta pero falta el segundo factor
      if (response.data.requiere_2fa && response.data.ticket) {
        setTicket2FA(response.data.ticket);
        setCodigo2FA('');
        setError2FA('');
        setError('');
        return;
      }

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
        const detalle = err.response?.data?.detail;
        if (detalle?.requiere_captcha) {
          setCaptchaRequerido(true);
          setTurnstileToken('');
          window.turnstile?.reset();
          widgetCargado.current = false;
          setError(detalle.mensaje ?? 'Verificación anti-bots requerida.');
        } else if (err.response?.status === 401) {
          setError('Usuario o contraseña incorrectos.');
        } else if (err.response?.status === 429) {
          setError(detalle ?? 'Demasiados intentos fallidos. Espera unos minutos.');
        } else if (err.code === 'ERR_NETWORK') {
          setError('No pudimos conectar con YEIKAR. Revisa tu conexión.');
        } else {
          setError('El servicio no está disponible en este momento. Inténtalo nuevamente.');
        }
      } else {
        setError('Ocurrió un error inesperado. Inténtalo nuevamente.');
      }
    } finally {
      setLoading(false);
    }
  };

  // Login biométrico: la huella del equipo sustituye contraseña y 2FA.
  // Requiere el usuario escrito (para saber qué huellas pedir) y un navegador
  // que soporte WebAuthn (Chrome/Edge/Safari, localhost cuenta como seguro).
  const handleLoginHuella = async () => {
    if (!username.trim()) {
      setError('Escribe tu usuario y luego toca huella.');
      return;
    }
    setError('');
    setCargandoHuella(true);
    try {
      const inicio = await axios.post(`${API_URL}/api/auth/webauthn/login/inicio`, {
        nombre_usuario: username.trim(),
      });
      const respuesta = await startAuthentication({ optionsJSON: inicio.data });
      const fin = await axios.post(`${API_URL}/api/auth/webauthn/login/fin`, {
        nombre_usuario: username.trim(),
        respuesta,
      });
      if (!fin.data.access_token) {
        setError('Respuesta inesperada al validar la huella. Inténtalo de nuevo.');
        return;
      }
      localStorage.setItem('token', fin.data.access_token);
      if (fin.data.refresh_token) localStorage.setItem('refresh_token', fin.data.refresh_token);
      await refresh();
      navigate(destination, { replace: true });
    } catch (err: unknown) {
      if (axios.isAxiosError(err)) {
        setError(err.response?.data?.detail ?? 'No pudimos validar la huella.');
      } else if (err instanceof Error && /NotAllowed|InvalidState|SecurityError/i.test(err.name)) {
        setError('La huella se canceló o este equipo no la tiene registrada. Usa tu contraseña.');
      } else {
        setError('Este navegador o contexto no permite huella. Usa tu contraseña.');
      }
    } finally {
      setCargandoHuella(false);
    }
  };

  // Verificación del segundo factor: el ticket prueba la contraseña; el
  // código de la app completa el login. "Recordar equipo" deja una cookie
  // firmada de 30 días para no pedir el código en cada visita.
  const handleVerificar2FA = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!codigo2FA.trim()) {
      setError2FA('Ingresa el código de tu app autenticadora.');
      return;
    }
    setError2FA('');
    setVerificando(true);
    try {
      const response = await axios.post(`${API_URL}/api/auth/2fa/verificar`, {
        ticket: ticket2FA,
        codigo: codigo2FA.trim(),
        recordar_equipo: recordarEquipo,
      });
      if (!response.data.access_token) {
        setError2FA('Respuesta inesperada del servidor. Inténtalo de nuevo.');
        return;
      }
      localStorage.setItem('token', response.data.access_token);
      if (response.data.refresh_token) localStorage.setItem('refresh_token', response.data.refresh_token);
      await refresh();
      navigate(destination, { replace: true });
    } catch (err: unknown) {
      if (axios.isAxiosError(err)) {
        const detalle = err.response?.data?.detail;
        if (typeof detalle === 'string' && detalle.includes('expirado')) {
          setTicket2FA('');
          setError2FA('');
        } else {
          setError2FA(detalle ?? 'Código incorrecto.');
        }
      } else {
        setError2FA('Ocurrió un error inesperado. Inténtalo nuevamente.');
      }
    } finally {
      setVerificando(false);
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

        <section className="relative flex min-h-screen flex-col px-5 py-8 sm:px-10 lg:items-center lg:justify-center lg:px-14 xl:px-24">
          {/* Banda de marca móvil */}
          <div className="relative -mx-5 -mt-8 mb-7 overflow-hidden bg-gradient-to-b from-yeikar-neutral via-yeikar-secondary to-yeikar-secondary-dark px-5 pb-9 pt-[calc(env(safe-area-inset-top)+1.25rem)] sm:-mx-10 sm:px-10 lg:hidden">
            <div className="pointer-events-none absolute -right-16 -top-10 h-60 w-60 rounded-full border border-yeikar-primary/25" />
            <div className="pointer-events-none absolute -right-4 top-0 h-44 w-44 rounded-full border border-yeikar-primary/20" />
            <div className="pointer-events-none absolute right-20 top-12 h-20 w-20 rounded-full border border-yeikar-primary/25" />
            <div className="pointer-events-none absolute bottom-0 right-1/3 h-px w-1/2 bg-gradient-to-r from-transparent via-yeikar-primary/30 to-transparent" />

            <div className="relative z-10 flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-yeikar-primary font-headline text-2xl font-black text-yeikar-neutral shadow-gold">Y</div>
                <div>
                  <p className="font-headline text-lg font-black tracking-[0.22em] text-white">YEIKAR</p>
                  <p className="mt-0.5 font-mono text-[8px] uppercase tracking-[0.18em] text-yeikar-primary/70">Atelier ERP</p>
                </div>
              </div>
              <span className="rounded-full border border-emerald-400/20 bg-emerald-400/10 px-3 py-1.5 text-[10px] font-bold text-emerald-300">Seguro</span>
            </div>

            <p className="relative z-10 mt-9 max-w-[260px] font-headline text-[26px] font-semibold leading-[1.05] tracking-[-0.03em] text-white">
              Cada detalle cuenta.<br />
              <span className="text-yeikar-primary">Cada entrega también.</span>
            </p>
          </div>

          <motion.div
            initial={{ opacity: 0, y: 18 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.55, ease: [0.16, 1, 0.3, 1] }}
            className="w-full max-w-[430px]"
          >
            <div className="rounded-3xl border border-yeikar-secondary-light/10 bg-white p-6 shadow-modal sm:p-8 lg:rounded-none lg:border-0 lg:bg-transparent lg:p-0 lg:shadow-none">
              {ticket2FA ? (
                <>
                  <div className="mb-7">
                    <div className="mb-5 flex h-11 w-11 items-center justify-center rounded-xl border border-yeikar-primary/20 bg-yeikar-primary/10 text-yeikar-primary-dark">
                      <Smartphone className="h-5 w-5" strokeWidth={1.8} />
                    </div>
                    <p className="eyebrow mb-2">Segundo paso</p>
                    <h2 className="font-headline text-[28px] font-semibold leading-tight tracking-[-0.045em] text-yeikar-neutral sm:text-4xl">Verifica con tu app.</h2>
                    <p className="mt-3 max-w-sm text-sm leading-relaxed text-yeikar-neutral/55">
                      Ingresa el código de 6 dígitos de tu app autenticadora (o un código de respaldo).
                    </p>
                  </div>

                  {error2FA && (
                    <div className="mb-6 flex items-start gap-3 rounded-2xl border border-rose-200/80 bg-rose-50/80 px-4 py-3.5 text-sm text-rose-800" role="alert" aria-live="polite">
                      <TriangleAlert className="mt-0.5 h-4 w-4 shrink-0" />
                      <span>{error2FA}</span>
                    </div>
                  )}

                  <form onSubmit={handleVerificar2FA} className="space-y-5" noValidate>
                    <div>
                      <label htmlFor="codigo-2fa" className="label">Código de verificación</label>
                      <input
                        id="codigo-2fa"
                        type="text"
                        inputMode="numeric"
                        autoComplete="one-time-code"
                        value={codigo2FA}
                        onChange={(event) => setCodigo2FA(event.target.value)}
                        disabled={verificando}
                        className="input h-14 bg-white/80 text-center font-mono text-2xl tracking-[0.4em] placeholder:tracking-normal placeholder:text-base lg:bg-white"
                        placeholder="Código o respaldo"
                        autoFocus
                        maxLength={10}
                      />
                    </div>

                    <label className="flex items-center gap-2.5 text-xs text-yeikar-neutral/60">
                      <input
                        type="checkbox"
                        checked={recordarEquipo}
                        onChange={(event) => setRecordarEquipo(event.target.checked)}
                        className="h-4 w-4 rounded accent-yeikar-primary"
                      />
                      Recordar este equipo por 30 días
                    </label>

                    <button
                      type="submit"
                      disabled={verificando}
                      className="group flex h-[52px] w-full items-center justify-center gap-3 rounded-xl bg-yeikar-primary px-5 font-headline text-sm font-bold text-yeikar-neutral shadow-gold transition-all duration-200 hover:bg-yeikar-primary-light hover:shadow-lift disabled:cursor-not-allowed disabled:opacity-60"
                    >
                      {verificando ? (
                        <span className="flex items-center gap-2"><span className="h-4 w-4 animate-spin rounded-full border-2 border-yeikar-neutral/25 border-t-yeikar-neutral" /> Verificando...</span>
                      ) : (
                        <>Verificar y entrar <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-1" /></>
                      )}
                    </button>

                    <button
                      type="button"
                      onClick={() => { setTicket2FA(''); setCodigo2FA(''); setError2FA(''); }}
                      className="w-full text-center text-xs font-bold text-yeikar-neutral/45 hover:text-yeikar-neutral transition-colors"
                    >
                      ← Volver a iniciar sesión
                    </button>
                  </form>
                </>
              ) : (
                <>
              <div className="mb-7">
                <div className="mb-5 flex h-11 w-11 items-center justify-center rounded-xl border border-yeikar-primary/20 bg-yeikar-primary/10 text-yeikar-primary-dark">
                  <LockKeyhole className="h-5 w-5" strokeWidth={1.8} />
                </div>
                <p className="eyebrow mb-2">Acceso privado</p>
                <h2 className="font-headline text-[28px] font-semibold leading-tight tracking-[-0.045em] text-yeikar-neutral sm:text-4xl">Bienvenido de vuelta.</h2>
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
                    className="input h-12 bg-white/80 lg:bg-white"
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
                      className="input h-12 bg-white/80 pr-12 lg:bg-white"
                      placeholder="Tu contraseña"
                      autoComplete="current-password"
                    />
                    <button
                      type="button"
                      onClick={() => setShowPassword((visible) => !visible)}
                      className="absolute right-2 top-1/2 -translate-y-1/2 rounded-lg p-2.5 text-yeikar-neutral/40 transition-colors hover:bg-yeikar-tertiary hover:text-yeikar-secondary"
                      aria-label={showPassword ? 'Ocultar contraseña' : 'Mostrar contraseña'}
                    >
                      {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                    </button>
                  </div>
                </div>

                {captchaRequerido && (
                  <div className="rounded-2xl border border-amber-200/80 bg-amber-50/70 px-4 py-3.5">
                    <p className="mb-2 text-xs font-bold text-amber-800">Verificación de seguridad</p>
                    <div ref={captchaBoxRef} className="min-h-[65px]" aria-label="Captcha de Cloudflare" />
                    {!TURNSTILE_SITE_KEY && (
                      <p className="mt-1 font-mono text-[10px] text-amber-700/70">
                        (widget no configurado: falta VITE_TURNSTILE_SITE_KEY)
                      </p>
                    )}
                  </div>
                )}

                <button
                  type="submit"
                  disabled={loading}
                  className="group flex h-[52px] w-full items-center justify-center gap-3 rounded-xl bg-yeikar-primary px-5 font-headline text-sm font-bold text-yeikar-neutral shadow-gold transition-all duration-200 hover:bg-yeikar-primary-light hover:shadow-lift disabled:cursor-not-allowed disabled:opacity-60"
                >
                  {loading ? (
                    <span className="flex items-center gap-2"><span className="h-4 w-4 animate-spin rounded-full border-2 border-yeikar-neutral/25 border-t-yeikar-neutral" /> Validando acceso...</span>
                  ) : (
                    <>Entrar al espacio de trabajo <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-1" /></>
                  )}
                </button>

                <button
                  type="button"
                  onClick={handleLoginHuella}
                  disabled={cargandoHuella || loading}
                  className="flex h-12 w-full items-center justify-center gap-2.5 rounded-xl border border-yeikar-secondary-light/20 bg-white/60 font-headline text-sm font-bold text-yeikar-neutral/70 transition-all hover:border-yeikar-primary/40 hover:text-yeikar-neutral disabled:cursor-not-allowed disabled:opacity-60"
                  title="Entrar con la huella o PIN de este equipo (si ya la registraste)"
                >
                  {cargandoHuella ? (
                    <span className="flex items-center gap-2"><span className="h-4 w-4 animate-spin rounded-full border-2 border-yeikar-neutral/25 border-t-yeikar-neutral" /> Esperando huella...</span>
                  ) : (
                    <><Fingerprint className="h-[18px] w-[18px]" strokeWidth={1.8} /> Entrar con huella</>
                  )}
                </button>
              </form>

              <div className="mt-8 flex items-center gap-3 border-t border-yeikar-secondary-light/10 pt-5 text-[11px] text-yeikar-neutral/45">
                <ShieldCheck className="h-4 w-4 text-yeikar-primary-dark" />
                <span>Tu sesión está protegida y tus datos permanecen privados.</span>
              </div>
                </>
              )}
            </div>

            <div className="mt-7 flex items-center justify-between text-[10px] text-yeikar-neutral/35 pb-safe lg:mt-8">
              <span className="flex items-center gap-1.5"><Check className="h-3.5 w-3.5 text-yeikar-primary-dark" /> Operación conectada</span>
              <span className="flex items-center gap-1.5"><Sparkles className="h-3.5 w-3.5 text-yeikar-primary-dark" /> YEIKAR {new Date().getFullYear()}</span>
            </div>
          </motion.div>
        </section>
      </div>
    </main>
  );
}
