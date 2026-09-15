import { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Fingerprint, KeyRound, MonitorSmartphone, ShieldCheck, Smartphone, Trash2, X } from 'lucide-react';
import { startRegistration } from '@simplewebauthn/browser';
import { authApi } from '../services/api';
import { useAuth } from '../context/AuthContext';
import { extractErrorMessage } from '../utils/format';

interface Sesion {
  id: number;
  ip: string | null;
  user_agent: string | null;
  revocada: boolean;
  creado_en: string;
  ultimo_uso: string;
  actual: boolean;
}

// Etiqueta amable del dispositivo a partir del user-agent (sin librerías).
function nombreDispositivo(userAgent: string | null): string {
  if (!userAgent) return 'Navegador';
  const es = (...claves: string[]) => claves.some((k) => userAgent.toLowerCase().includes(k));
  const navegador = es('edg/') ? 'Edge'
    : es('chrome', 'crios') ? 'Chrome'
    : es('firefox', 'fxios') ? 'Firefox'
    : es('safari') ? 'Safari'
    : 'Navegador';
  const equipo = es('mobile', 'android', 'iphone') ? 'móvil' : 'computador';
  return `${navegador} · ${equipo}`;
}

function fechaCorta(iso: string): string {
  return new Date(iso).toLocaleString('es-ES', { dateStyle: 'medium', timeStyle: 'short' });
}

interface Huella {
  id: number;
  dispositivo: string | null;
  creado_en: string;
  ultimo_uso: string | null;
}

export default function MiSeguridad() {
  const navigate = useNavigate();
  const { user, refresh: refreshUser } = useAuth();
  const [sesiones, setSesiones] = useState<Sesion[]>([]);
  const [loading, setLoading] = useState(true);
  const [cargandoId, setCargandoId] = useState<number | null>(null);
  const [confirmarOtras, setConfirmarOtras] = useState(false);
  const [mensajeGeneral, setMensajeGeneral] = useState('');

  // Cambio de contraseña
  const [actual, setActual] = useState('');
  const [nueva, setNueva] = useState('');
  const [repetir, setRepetir] = useState('');
  const [mostrarClaves, setMostrarClaves] = useState(false);
  const [errorClave, setErrorClave] = useState('');
  const [guardandoClave, setGuardandoClave] = useState(false);

  // 2FA con app
  const [qrActivo, setQrActivo] = useState(false);
  const [qrBase64, setQrBase64] = useState('');
  const [codigo2FA, setCodigo2FA] = useState('');
  const [codigosRespaldo, setCodigosRespaldo] = useState<string[]>([]);
  const [procesando2FA, setProcesando2FA] = useState(false);
  const [error2FA, setError2FA] = useState('');
  const [confirmarDesactivar, setConfirmarDesactivar] = useState(false);

  // Huella / passkeys de este usuario
  const [huellas, setHuellas] = useState<Huella[]>([]);
  const [nombreHuella, setNombreHuella] = useState('Este equipo');
  const [registrandoHuella, setRegistrandoHuella] = useState(false);
  const [borrandoHuellaId, setBorrandoHuellaId] = useState<number | null>(null);

  const cargarSesiones = useCallback(async () => {
    try {
      setLoading(true);
      const res = await authApi.get<Sesion[]>('/sesiones');
      setSesiones(res.data.filter((s) => !s.revocada));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    cargarSesiones();
    authApi.get<Huella[]>('/webauthn/huellas')
      .then((res) => setHuellas(res.data))
      .catch(() => setHuellas([]));
  }, [cargarSesiones]);

  const cerrarSesion = async (id: number) => {
    setCargandoId(id);
    try {
      await authApi.delete(`/sesiones/${id}`);
      await cargarSesiones();
    } catch (err) {
      setErrorClave(extractErrorMessage(err, 'No se pudo cerrar esa sesión.'));
    } finally {
      setCargandoId(null);
    }
  };

  const cerrarOtras = async () => {
    setConfirmarOtras(false);
    try {
      await authApi.post('/sesiones/cerrar-otras');
      await cargarSesiones();
    } catch (err) {
      setErrorClave(extractErrorMessage(err, 'No se pudieron cerrar las demás sesiones.'));
    }
  };

  const cambiarPassword = async () => {
    setErrorClave('');
    if (nueva.length < 8) {
      setErrorClave('La nueva contraseña debe tener al menos 8 caracteres.');
      return;
    }
    if (nueva !== repetir) {
      setErrorClave('Las contraseñas nuevas no coinciden.');
      return;
    }
    try {
      setGuardandoClave(true);
      await authApi.put('/me/password', { password_actual: actual, password_nueva: nueva });
      // El backend revocó todas las sesiones: fuera de aquí.
      localStorage.removeItem('token');
      localStorage.removeItem('refresh_token');
      navigate('/login', { replace: true });
    } catch (err) {
      setErrorClave(extractErrorMessage(err, 'No se pudo cambiar la contraseña.'));
      setGuardandoClave(false);
    }
  };

  const inputClave = 'w-full rounded-xl border border-yeikar-secondary-light/20 px-3.5 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-yeikar-primary bg-white';

  return (
    <div className="space-y-6">
      <div>
        <h1 className="flex items-center gap-2.5 text-3xl font-black font-headline text-yeikar-neutral tracking-tight">
          <ShieldCheck className="h-7 w-7 text-yeikar-primary" />
          Mi seguridad
        </h1>
        <p className="text-yeikar-neutral/60 mt-1 text-sm">
          Sesiones abiertas y contraseña: el control de tus accesos en un solo lugar.
        </p>
      </div>

      {/* ── Sesiones activas ── */}
      <section className="rounded-2xl border border-yeikar-secondary-light/10 bg-white shadow-card overflow-hidden">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-yeikar-secondary-light/10 px-5 py-4">
          <div className="flex items-center gap-3">
            <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-yeikar-tertiary/40 text-yeikar-secondary">
              <MonitorSmartphone className="h-[18px] w-[18px]" />
            </span>
            <div>
              <h2 className="font-headline text-[15px] font-black text-yeikar-neutral tracking-tight">Sesiones activas</h2>
              <p className="text-xs text-yeikar-neutral/50">Cada inicio de sesión es una fila. Cierra las que no reconozcas.</p>
            </div>
          </div>
          {sesiones.length > 1 && (
            <button
              onClick={() => (confirmarOtras ? cerrarOtras() : setConfirmarOtras(true))}
              className="self-start rounded-xl border border-amber-200 bg-amber-50 px-3.5 py-2 text-xs font-bold text-amber-800 hover:bg-amber-100 transition-colors"
            >
              {confirmarOtras ? '¿Seguro? Cierra las demás' : 'Cerrar las demás sesiones'}
            </button>
          )}
        </div>

        {loading ? (
          <p className="px-5 py-10 text-center font-mono text-xs text-yeikar-neutral/40">Cargando sesiones...</p>
        ) : (
          <ul className="divide-y divide-yeikar-secondary-light/10">
            {sesiones.map((s) => (
              <li key={s.id} className="flex flex-col gap-2 px-5 py-3.5 sm:flex-row sm:items-center sm:justify-between">
                <div className="min-w-0">
                  <p className="flex items-center gap-2 font-headline text-sm font-bold text-yeikar-neutral">
                    {nombreDispositivo(s.user_agent)}
                    {s.actual && (
                      <span className="rounded-full border border-emerald-200 bg-emerald-50 px-2 py-0.5 font-mono text-[10px] font-bold text-emerald-700">
                        ESTA SESIÓN
                      </span>
                    )}
                  </p>
                  <p className="mt-0.5 truncate font-mono text-[11px] text-yeikar-neutral/50">
                    IP {s.ip ?? '—'} · iniciada {fechaCorta(s.creado_en)} · último uso {fechaCorta(s.ultimo_uso)}
                  </p>
                </div>
                {!s.actual && (
                  <button
                    onClick={() => cerrarSesion(s.id)}
                    disabled={cargandoId === s.id}
                    className="self-start flex items-center gap-1.5 rounded-lg border border-rose-200 px-3 py-1.5 text-[11px] font-bold text-rose-600 hover:bg-rose-50 transition-colors disabled:opacity-50"
                  >
                    <X className="h-3.5 w-3.5" />
                    {cargandoId === s.id ? 'Cerrando...' : 'Cerrar'}
                  </button>
                )}
              </li>
            ))}
          </ul>
        )}
      </section>

      {/* ── Cambio de contraseña ── */}
      <section className="rounded-2xl border border-yeikar-secondary-light/10 bg-white shadow-card overflow-hidden">
        <div className="flex items-center gap-3 border-b border-yeikar-secondary-light/10 px-5 py-4">
          <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-yeikar-tertiary/40 text-yeikar-secondary">
            <KeyRound className="h-[18px] w-[18px]" />
          </span>
          <div>
            <h2 className="font-headline text-[15px] font-black text-yeikar-neutral tracking-tight">Cambiar contraseña</h2>
            <p className="text-xs text-yeikar-neutral/50">Al cambiarla se cierran TODAS las sesiones: tendrás que entrar de nuevo en cada equipo.</p>
          </div>
        </div>

        <div className="space-y-3 px-5 py-5">
          <div className="grid gap-3 sm:grid-cols-2">
            <div>
              <label htmlFor="pass-actual" className="mb-1 block text-xs font-bold text-yeikar-neutral/60">Contraseña actual</label>
              <input id="pass-actual" type={mostrarClaves ? 'text' : 'password'} value={actual}
                onChange={(e) => setActual(e.target.value)} autoComplete="current-password" className={inputClave} />
            </div>
            <div>
              <label htmlFor="pass-nueva" className="mb-1 block text-xs font-bold text-yeikar-neutral/60">Nueva contraseña (mínimo 8)</label>
              <input id="pass-nueva" type={mostrarClaves ? 'text' : 'password'} value={nueva}
                onChange={(e) => setNueva(e.target.value)} autoComplete="new-password" className={inputClave} />
            </div>
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            <div>
              <label htmlFor="pass-repetir" className="mb-1 block text-xs font-bold text-yeikar-neutral/60">Repetir nueva contraseña</label>
              <input id="pass-repetir" type={mostrarClaves ? 'text' : 'password'} value={repetir}
                onChange={(e) => setRepetir(e.target.value)} autoComplete="new-password" className={inputClave} />
            </div>
            <label className="flex items-end gap-2 pb-1.5 text-xs font-bold text-yeikar-neutral/60">
              <input type="checkbox" checked={mostrarClaves} onChange={(e) => setMostrarClaves(e.target.checked)}
                className="h-4 w-4 rounded accent-yeikar-primary" />
              Mostrar contraseñas
            </label>
          </div>

          {errorClave && (
            <p className="rounded-xl border border-rose-200 bg-rose-50 px-3.5 py-2.5 text-xs text-rose-700" role="alert">
              {errorClave}
            </p>
          )}

          <button
            onClick={cambiarPassword}
            disabled={guardandoClave || !actual || !nueva || !repetir}
            className="rounded-xl bg-yeikar-primary px-5 py-2.5 text-sm font-bold font-headline text-yeikar-neutral transition-colors hover:bg-yeikar-primary/90 disabled:opacity-50"
          >
            {guardandoClave ? 'Guardando...' : 'Guardar nueva contraseña'}
          </button>
        </div>
      </section>

      {/* ── 2FA con app ── */}
      <section className="rounded-2xl border border-yeikar-secondary-light/10 bg-white shadow-card overflow-hidden">
        <div className="flex items-center gap-3 border-b border-yeikar-secondary-light/10 px-5 py-4">
          <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-yeikar-tertiary/40 text-yeikar-secondary">
            <Smartphone className="h-[18px] w-[18px]" />
          </span>
          <div className="flex-1">
            <h2 className="font-headline text-[15px] font-black text-yeikar-neutral tracking-tight">
              2FA con app autenticadora
            </h2>
            <p className="text-xs text-yeikar-neutral/50">
              Tras la contraseña, un código de 6 dígitos que cambia cada 30 segundos.
            </p>
          </div>
          {user?.totp_habilitado && (
            <span className="rounded-full border border-emerald-200 bg-emerald-50 px-2.5 py-0.5 text-[11px] font-bold text-emerald-700">ACTIVO</span>
          )}
        </div>

        <div className="space-y-3 px-5 py-5">
          {error2FA && (
            <p className="rounded-xl border border-rose-200 bg-rose-50 px-3.5 py-2.5 text-xs text-rose-700" role="alert">{error2FA}</p>
          )}

          {user?.totp_habilitado ? (
            <div>
              <p className="text-sm text-yeikar-neutral/70">
                Tu cuenta pide un código de la app en cada equipo nuevo. Los equipos recordados no lo piden por 30 días.
              </p>
              {!confirmarDesactivar ? (
                <button
                  onClick={() => setConfirmarDesactivar(true)}
                  className="mt-3 rounded-xl border border-amber-200 bg-amber-50 px-4 py-2 text-xs font-bold text-amber-800 hover:bg-amber-100 transition-colors"
                >
                  Desactivar 2FA
                </button>
              ) : (
                <div className="mt-3 flex flex-col gap-2 sm:flex-row sm:items-end">
                  <div className="flex-1">
                    <label htmlFor="off-2fa" className="mb-1 block text-xs font-bold text-yeikar-neutral/60">
                      Código actual de la app (o respaldo) para desactivar
                    </label>
                    <input id="off-2fa" type="text" value={codigo2FA}
                      onChange={(e) => setCodigo2FA(e.target.value)} className={inputClave} placeholder="000000" />
                  </div>
                  <button
                    onClick={async () => {
                      setProcesando2FA(true);
                      setError2FA('');
                      try {
                        await authApi.post('/2fa/desactivar', { codigo: codigo2FA.trim() });
                        setConfirmarDesactivar(false);
                        setCodigo2FA('');
                        setMensajeGeneral('2FA desactivado.');
                        await refreshUser();
                      } catch (err) {
                        setError2FA(extractErrorMessage(err, 'Código inválido: el 2FA sigue activo.'));
                      } finally {
                        setProcesando2FA(false);
                      }
                    }}
                    disabled={procesando2FA || !codigo2FA.trim()}
                    className="rounded-xl bg-rose-600 px-4 py-2.5 text-xs font-bold text-white hover:bg-rose-700 transition-colors disabled:opacity-50"
                  >
                    {procesando2FA ? 'Apagando...' : 'Confirmar desactivar'}
                  </button>
                  <button
                    onClick={() => { setConfirmarDesactivar(false); setCodigo2FA(''); }}
                    className="rounded-xl border border-yeikar-secondary-light/20 px-4 py-2.5 text-xs font-bold text-yeikar-neutral/60 hover:bg-yeikar-tertiary/20 transition-colors"
                  >
                    Cancelar
                  </button>
                </div>
              )}
            </div>
          ) : qrActivo ? (
            <div className="space-y-3">
              <div className="flex flex-col items-center gap-3 sm:flex-row sm:items-start">
                <img src={`data:image/png;base64,${qrBase64}`} alt="QR del 2FA" className="h-44 w-44 rounded-xl border border-yeikar-secondary-light/20 bg-white p-2" />
                <div className="flex-1 text-sm text-yeikar-neutral/70">
                  <p className="font-bold text-yeikar-neutral">1. Escanea este QR</p>
                  <p className="mt-1">Con Google Authenticator, Authy o el que prefieras.</p>
                  <p className="mt-2 font-bold text-yeikar-neutral">2. Confirma el código</p>
                  <p className="mt-1">Ingresa el código de 6 dígitos que te muestra la app.</p>
                </div>
              </div>
              <div className="flex flex-col gap-2 sm:flex-row sm:items-end">
                <div className="flex-1">
                  <label htmlFor="on-2fa" className="mb-1 block text-xs font-bold text-yeikar-neutral/60">Código de la app</label>
                  <input id="on-2fa" type="text" inputMode="numeric" value={codigo2FA}
                    onChange={(e) => setCodigo2FA(e.target.value)} className={inputClave} placeholder="000000" maxLength={8} />
                </div>
                <button
                  onClick={async () => {
                    setProcesando2FA(true);
                    setError2FA('');
                    try {
                      const res = await authApi.post('/2fa/activar', { codigo: codigo2FA.trim() });
                      setCodigosRespaldo(res.data.codigos_respaldo ?? []);
                      setQrActivo(false);
                      setCodigo2FA('');
                      await refreshUser();
                    } catch (err) {
                      setError2FA(extractErrorMessage(err, 'El código no coincide. Reintenta.'));
                    } finally {
                      setProcesando2FA(false);
                    }
                  }}
                  disabled={procesando2FA || !codigo2FA.trim()}
                  className="rounded-xl bg-yeikar-primary px-4 py-2.5 text-sm font-bold font-headline text-yeikar-neutral hover:bg-yeikar-primary/90 transition-colors disabled:opacity-50"
                >
                  {procesando2FA ? 'Confirmando...' : 'Activar 2FA'}
                </button>
              </div>
            </div>
          ) : (
            <div>
              <p className="text-sm text-yeikar-neutral/70">
                Añade una segunda barrera: aunque alguien robe tu contraseña, necesitará tu teléfono.
              </p>
              <button
                onClick={async () => {
                  setProcesando2FA(true);
                  setError2FA('');
                  try {
                    const res = await authApi.post('/2fa/generar');
                    setQrBase64(res.data.qr_base64);
                    setQrActivo(true);
                    setCodigo2FA('');
                  } catch (err) {
                    setError2FA(extractErrorMessage(err, 'No se pudo generar el código QR.'));
                  } finally {
                    setProcesando2FA(false);
                  }
                }}
                disabled={procesando2FA}
                className="mt-3 rounded-xl bg-yeikar-primary px-4 py-2.5 text-sm font-bold font-headline text-yeikar-neutral hover:bg-yeikar-primary/90 transition-colors disabled:opacity-50"
              >
                {procesando2FA ? 'Generando QR...' : 'Activar 2FA'}
              </button>
            </div>
          )}

          {codigosRespaldo.length > 0 && (
            <div className="rounded-2xl border border-amber-200 bg-amber-50 p-4">
              <p className="font-headline text-sm font-black text-amber-800">Guarda tus códigos de respaldo AHORA</p>
              <p className="mt-1 text-xs text-amber-700/80">
                Se muestran una sola vez. Cada uno entra una vez, si pierdes el teléfono.
              </p>
              <div className="mt-3 grid grid-cols-2 gap-1.5 sm:grid-cols-5">
                {codigosRespaldo.map((codigo) => (
                  <span key={codigo} className="rounded-lg bg-white px-2 py-1.5 text-center font-mono text-[11px] font-bold text-yeikar-neutral shadow-sm">
                    {codigo}
                  </span>
                ))}
              </div>
              <button
                onClick={() => { setCodigosRespaldo([]); setMensajeGeneral('Códigos guardados.'); }}
                className="mt-3 rounded-lg bg-amber-600 px-3.5 py-2 text-xs font-bold text-white hover:bg-amber-700 transition-colors"
              >
                Ya los guardé
              </button>
            </div>
          )}

          {mensajeGeneral && (
            <p className="rounded-xl border border-emerald-200 bg-emerald-50 px-3.5 py-2.5 text-xs text-emerald-700">
              {mensajeGeneral}
            </p>
          )}
        </div>
      </section>

      {/* ── Huella / Face ID (passkeys) ── */}
      <section className="rounded-2xl border border-yeikar-secondary-light/10 bg-white shadow-card overflow-hidden">
        <div className="flex items-center gap-3 border-b border-yeikar-secondary-light/10 px-5 py-4">
          <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-yeikar-tertiary/40 text-yeikar-secondary">
            <Fingerprint className="h-[18px] w-[18px]" />
          </span>
          <div className="flex-1">
            <h2 className="font-headline text-[15px] font-black text-yeikar-neutral tracking-tight">
              Huella / Face ID / PIN del equipo
            </h2>
            <p className="text-xs text-yeikar-neutral/50">
              Entra con tu biometría: sustituye contraseña y código de la app en este equipo. Sin escribir nada en el login, eliges tu cuenta ahí mismo.
              Las huellas registradas antes de este cambio siguen pidiendo tu usuario: quítalas y vuelve a registrarlas para entrar sin escribir nada.
            </p>
          </div>
        </div>

        <div className="space-y-3 px-5 py-5">
          {error2FA && (
            <p className="rounded-xl border border-rose-200 bg-rose-50 px-3.5 py-2.5 text-xs text-rose-700" role="alert">{error2FA}</p>
          )}
          <div className="flex flex-col gap-2 sm:flex-row sm:items-end">
            <div className="flex-1">
              <label htmlFor="nombre-huella" className="mb-1 block text-xs font-bold text-yeikar-neutral/60">
                Nombre para reconocerla
              </label>
              <input id="nombre-huella" type="text" value={nombreHuella}
                onChange={(e) => setNombreHuella(e.target.value)} className={inputClave} />
            </div>
            <button
              onClick={async () => {
                setRegistrandoHuella(true);
                setError2FA('');
                try {
                  const inicio = await authApi.post('/webauthn/registro/inicio');
                  const respuesta = await startRegistration({ optionsJSON: inicio.data });
                  await authApi.post('/webauthn/registro/fin', {
                    dispositivo: nombreHuella.trim() || 'Este equipo',
                    respuesta,
                  });
                  setMensajeGeneral('Huella registrada: ya puedes entrar con ella desde este equipo.');
                  const res = await authApi.get<Huella[]>('/webauthn/huellas');
                  setHuellas(res.data);
                } catch (err) {
                  setError2FA(extractErrorMessage(err, 'No se pudo registrar la huella en este equipo.'));
                } finally {
                  setRegistrandoHuella(false);
                }
              }}
              disabled={registrandoHuella}
              className="rounded-xl bg-yeikar-primary px-4 py-2.5 text-sm font-bold font-headline text-yeikar-neutral hover:bg-yeikar-primary/90 transition-colors disabled:opacity-50"
            >
              {registrandoHuella ? 'Esperando huella...' : 'Registrar huella en este equipo'}
            </button>
          </div>

          {huellas.length > 0 && (
            <ul className="divide-y divide-yeikar-secondary-light/10 rounded-2xl border border-yeikar-secondary-light/10">
              {huellas.map((huella) => (
                <li key={huella.id} className="flex items-center justify-between gap-3 px-4 py-3">
                  <div className="min-w-0">
                    <p className="truncate font-headline text-sm font-bold text-yeikar-neutral">
                      {huella.dispositivo ?? 'Huella'}
                    </p>
                    <p className="mt-0.5 truncate font-mono text-[11px] text-yeikar-neutral/50">
                      registrada {fechaCorta(huella.creado_en)}
                      {huella.ultimo_uso ? ` · último uso ${fechaCorta(huella.ultimo_uso)}` : ' · sin usos aún'}
                    </p>
                  </div>
                  <button
                    onClick={async () => {
                      setBorrandoHuellaId(huella.id);
                      try {
                        await authApi.delete(`/webauthn/huellas/${huella.id}`);
                        setHuellas((prev) => prev.filter((h) => h.id !== huella.id));
                      } finally {
                        setBorrandoHuellaId(null);
                      }
                    }}
                    disabled={borrandoHuellaId === huella.id}
                    className="flex items-center gap-1.5 rounded-lg border border-rose-200 px-3 py-1.5 text-[11px] font-bold text-rose-600 hover:bg-rose-50 transition-colors disabled:opacity-50"
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                    {borrandoHuellaId === huella.id ? 'Quitando...' : 'Quitar'}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      </section>
    </div>
  );
}
