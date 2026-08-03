import React, { createContext, useCallback, useContext, useEffect, useState } from 'react';
import { authApi } from '../services/api';

export interface ModuloAcceso {
  modulo: string;
  gestionar: boolean;
}

export interface UsuarioMe {
  id: number;
  nombre_usuario: string;
  email: string | null;
  activo: boolean;
  roles: { id: number; nombre: string; descripcion?: string | null; activo?: boolean }[];
  modulos: ModuloAcceso[];
}

interface AuthContextValue {
  user: UsuarioMe | null;
  loading: boolean;
  modulos: ModuloAcceso[];
  hasModulo: (modulo: string, gestionar?: boolean) => boolean;
  logout: () => void;
  refresh: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<UsuarioMe | null>(null);
  const [loading, setLoading] = useState(true);

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
    } catch {
      setUser(null);
    } finally {
      setLoading(false);
    }
  }, []);

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

  const logout = useCallback(() => {
    localStorage.removeItem('token');
    localStorage.removeItem('refresh_token');
    setUser(null);
  }, []);

  return (
    <AuthContext.Provider value={{ user, loading, modulos: user?.modulos || [], hasModulo, logout, refresh }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth debe usarse dentro de <AuthProvider>');
  return ctx;
}
