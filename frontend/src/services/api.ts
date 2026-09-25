import axios, { type InternalAxiosRequestConfig } from 'axios';

export const API_URL = (import.meta.env.VITE_API_URL ?? '').replace(/\/+$/, '');

// ─── Caché SWR de catálogos estáticos ─────────────────────────────────────
// Las páginas piden una y otra vez los mismos catálogos (unidades, monedas,
// áreas, categorías, cargos, tipos…). Se cachean en memoria con stale-while-
// revalidate: la primera vez se sirven y en paralelo se refrescan en segundo
// plano; si el servidor no responde (sin internet) se sirve la última copia.
const cacheApi = new Map<string, { data: unknown; fetchedAt: number }>();
const inflightApi = new Map<string, Promise<unknown>>();
const CATALOGO_TTL_MS = 10 * 60 * 1000;

function esCatalogoCacheable(url: unknown, config?: { params?: unknown }): boolean {
  return (
    typeof url === 'string' &&
    url.startsWith('/catalogos/') &&
    !config?.params
  );
}

export function limpiarCacheApi() {
  cacheApi.clear();
}

function respuestaDesdeCache(data: unknown) {
  return {
    data,
    status: 200,
    statusText: 'OK',
    headers: {},
    config: {},
  } as never;
}

// API principal para los módulos: /api/v1/*
const api = axios.create({
  baseURL: `${API_URL}/api/v1`,
});

// Caché SWR sobre GET de catálogos (no toca el resto de endpoints).
const apiGetOriginal = api.get.bind(api);
api.get = ((url: unknown, config?: any) => {
  if (esCatalogoCacheable(url, config)) {
    const key = `GET ${url}`;
    const ahora = Date.now();
    const hit = cacheApi.get(key);
    const refrescar = () => {
      const inflight = inflightApi.get(key);
      if (inflight) return inflight;
      const p = apiGetOriginal(url as string, config)
        .then((r) => {
          cacheApi.set(key, { data: r.data, fetchedAt: Date.now() });
          return r;
        })
        .finally(() => inflightApi.delete(key));
      inflightApi.set(key, p);
      return p;
    };
    if (hit) {
      if (ahora - hit.fetchedAt < CATALOGO_TTL_MS) {
        return Promise.resolve(respuestaDesdeCache(hit.data));
      }
      // Stale-while-revalidate: sirve lo viejo ya y refresca en segundo plano.
      refrescar().catch(() => { /* queda la copia anterior (resiliente offline) */ });
      return Promise.resolve(respuestaDesdeCache(hit.data));
    }
    return refrescar();
  }
  return apiGetOriginal(url as string, config);
}) as typeof api.get;

// API de autenticación: /api/auth/*  (el backend la registra sin /v1)
export const authApi = axios.create({
  baseURL: `${API_URL}/api/auth`,
});

// ─── Utilidad para intentar renovar el token ───────────────────────────────
let isRefreshing = false;
let failedQueue: Array<{ resolve: (v: string) => void; reject: (e: unknown) => void }> = [];

function processQueue(error: unknown, token: string | null) {
  failedQueue.forEach(({ resolve, reject }) => {
    if (token) resolve(token);
    else reject(error);
  });
  failedQueue = [];
}

async function tryRefresh(): Promise<string> {
  const refreshToken = localStorage.getItem('refresh_token');
  if (!refreshToken) throw new Error('No refresh token');

  const response = await axios.post(`${API_URL}/api/auth/refresh`, {
    refresh_token: refreshToken,
  });

  const { access_token, refresh_token: newRefresh } = response.data;
  localStorage.setItem('token', access_token);
  if (newRefresh) localStorage.setItem('refresh_token', newRefresh);
  return access_token;
}

function clearSessionAndRedirect() {
  localStorage.removeItem('token');
  localStorage.removeItem('refresh_token');
  window.location.href = '/login';
}

// ─── Interceptor de request – adjunta token ────────────────────────────────
const requestInterceptor = (config: InternalAxiosRequestConfig) => {
  const token = localStorage.getItem('token');
  if (token && config.headers) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  // Los escritos sobre catálogos invalidan su caché SWR.
  if (config.method && config.method.toLowerCase() !== 'get' && config.url?.startsWith('/catalogos/')) {
    cacheApi.clear();
  }
  return config;
};

api.interceptors.request.use(requestInterceptor, (error) => Promise.reject(error));
authApi.interceptors.request.use(requestInterceptor, (error) => Promise.reject(error));

// ─── Interceptor de response – reintenta con refresh en 401 ───────────────
const responseErrorInterceptor = async (error: any) => {
  const originalRequest = error.config;

  // Si es 401 y no es una petición de refresh/login (evitar loop)
  if (
    error.response?.status === 401 &&
    !originalRequest._retry &&
    !originalRequest.url?.includes('/refresh') &&
    !originalRequest.url?.includes('/login')
  ) {
    if (isRefreshing) {
      // Ya hay un refresh en curso: encolar y esperar
      return new Promise<string>((resolve, reject) => {
        failedQueue.push({ resolve, reject });
      })
        .then((token) => {
          originalRequest.headers.Authorization = `Bearer ${token}`;
          return axios(originalRequest);
        })
        .catch((e) => Promise.reject(e));
    }

    originalRequest._retry = true;
    isRefreshing = true;

    try {
      const newToken = await tryRefresh();
      processQueue(null, newToken);
      originalRequest.headers.Authorization = `Bearer ${newToken}`;
      return axios(originalRequest);
    } catch (refreshError) {
      processQueue(refreshError, null);
      clearSessionAndRedirect();
      return Promise.reject(refreshError);
    } finally {
      isRefreshing = false;
    }
  }

  return Promise.reject(error);
};

api.interceptors.response.use((response) => response, responseErrorInterceptor);
authApi.interceptors.response.use((response) => response, (error) => {
  // Para authApi solo redirigimos si es 401 en endpoints distintos a refresh/login
  if (
    error.response?.status === 401 &&
    !error.config?.url?.includes('/refresh') &&
    !error.config?.url?.includes('/login')
  ) {
    clearSessionAndRedirect();
  }
  return Promise.reject(error);
});

export default api;
