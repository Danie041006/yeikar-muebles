import React, { createContext, useCallback, useContext, useEffect, useState } from 'react';
import { authApi } from '../services/api';
import {
  asegurarClaveDispositivo,
  configurarPin as configurarPinLocal,
  desbloquearConPin,
  guardarSesion,
  leerSesionCache,
  limpiarOffline,
  resumenSesion,
  type ResumenSesion,
} from '../offline/sesion';
import { detenerMotorSync, iniciarMotorSync } from '../offline/sync';
import { OFFLINE_HABILITADO } from '../offline/interruptor';

export interface ModuloAcceso {
  modulo: string;
  gestionar: boolean;
}

export interface UsuarioMe {
  id: number;
  empleado_id?: number | null;
  nombre_usuario: string;
  nombre?: string | null;
  email: string | null;
  activo: boolean;
  totp_habilitado?: boolean;
  roles: { id: number; nombre: string; descripcion?: string | null; activo?: boolean }[];
  modulos: ModuloAcceso[];
}

interface AuthContextValue {
  user: UsuarioMe | null;
  loading: boolean;
  modulos: ModuloAcceso[];
  esAdmin: boolean;
  hasModulo: (modulo: string, gestionar?: boolean) => boolean;
  logout: () => Promise<void>;
  refresh: () => Promise<void>;
  /** true cuando /me falló por red y se está usando la sesión cacheada. */
  sinConexion: boolean;
  /** true cuando hay sesión cacheada protegida por PIN esperando desbloqueo. */
  bloqueado: boolean;
  /** Resumen en claro (nombre) de la sesión cacheada, para la pantalla de PIN. */
  resumen: ResumenSesion | null;
  desbloquear: (pin: string) => Promise<boolean>;
  configurarPin: (pin: string) => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<UsuarioMe | null>(null);
  const [loading, setLoading] = useState(true);
  const [sinConexion, setSinConexion] = useState(false);
  const [bloqueado, setBloqueado] = useState(false);
  const [resumen, setResumen] = useState<ResumenSesion | null>(null);

  const recuperarSesionOffline = useCallback(async (): Promise<boolean> => {
    const guardado = await resumenSesion();
    if (!guardado) return false;

    setResumen(guardado);
    setSinConexion(true);

    let desbloqueada = false;
    try {
      desbloqueada = await asegurarClaveDispositivo();
    } catch {
      desbloqueada = false;
    }

    if (!desbloqueada) {
      setBloqueado(true);
      iniciarMotorSync();
      return true;
    }

    const cache = await leerSesionCache<UsuarioMe>();
    if (!cache) return false;

    setUser(cache);
    iniciarMotorSync();
    return true;
  }, []);

  const refresh = useCallback(async () => {
    const token = localStorage.getItem('token');
    if (!token) {
      setUser(null);
      setLoading(false);
      return;
    }
    try {
      const res = await authApi.get<UsuarioMe>('/me');
      setUser(res.data);
      setBloqueado(false);
      setSinConexion(false);
      if (OFFLINE_HABILITADO) {
        try {
          if (await asegurarClaveDispositivo()) await guardarSesion(res.data);
        } catch {
          /* sin IndexedDB: la sesión online sigue funcionando */
        }
      }
      iniciarMotorSync();
    } catch (error) {
      const hayRespuesta = Boolean((error as { response?: unknown })?.response);
      if (!hayRespuesta && OFFLINE_HABILITADO && (await recuperarSesionOffline())) {
        setLoading(false);
        return;
      }
      setUser(null);
    } finally {
      setLoading(false);
    }
  }, [recuperarSesionOffline]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const hasModulo = useCallback(
    (modulo: string, gestionar = false) => {
      const acceso = user?.modulos?.find((m) => m.modulo === modulo);
      if (!acceso) return false;
      return gestionar ? acceso.gestionar : true;
    },
    [user],
  );

  const esAdmin = user?.roles?.some((role) => ['Dueño', 'Administrador'].includes(role.nombre)) ?? false;

  const logout = useCallback(async () => {
    // Revoca la sesión en el servidor (apaga el refresh token); si la red
    // falla, igual limpiamos localmente para no dejar la UI atascada. La copia
    // offline se borra completa: un equipo compartido no conserva datos de
    // quien cierra sesión.
    try {
      await authApi.post('/logout');
    } catch {
      /* sesión ya inválida o sin red: la limpieza local sigue */
    }
    localStorage.removeItem('token');
    localStorage.removeItem('refresh_token');
    detenerMotorSync();
    if (OFFLINE_HABILITADO) await limpiarOffline();
    setUser(null);
    setBloqueado(false);
    setResumen(null);
    setSinConexion(false);
  }, []);

  const desbloquear = useCallback(async (pin: string) => {
    const ok = await desbloquearConPin(pin);
    if (!ok) return false;
    const cache = await leerSesionCache<UsuarioMe>();
    if (!cache) return false;
    setUser(cache);
    setBloqueado(false);
    setSinConexion(true);
    iniciarMotorSync();
    return true;
  }, []);

  const configurarPin = useCallback(
    async (pin: string) => {
      await configurarPinLocal(pin);
      if (user) await guardarSesion(user);
    },
    [user],
  );

  return (
    <AuthContext.Provider
      value={{
        user,
        loading,
        modulos: user?.modulos || [],
        esAdmin,
        hasModulo,
        logout,
        refresh,
        sinConexion,
        bloqueado,
        resumen,
        desbloquear,
        configurarPin,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth debe usarse dentro de <AuthProvider>');
  return ctx;
}
