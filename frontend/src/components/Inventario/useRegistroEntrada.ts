import { useRef, useState } from 'react';
import axios from 'axios';
import { inventarioService, type CompraInventarioMultipleCreate } from '../../services/inventarioService';
import { extractErrorMessage } from '../../utils/format';

function recuperarSolicitud(clave: string): CompraInventarioMultipleCreate | null {
  try {
    const guardada: unknown = JSON.parse(sessionStorage.getItem(clave) || 'null');
    if (typeof guardada !== 'object' || guardada === null) return null;
    const captura = guardada as Record<string, unknown>;
    if (typeof captura.operacion_id !== 'string' || typeof captura.fecha !== 'string'
      || !Array.isArray(captura.lineas) || !captura.lineas.length || !Array.isArray(captura.pagos)) return null;
    return guardada as CompraInventarioMultipleCreate;
  } catch { return null; }
}

function persistirSolicitud(clave: string, solicitud: CompraInventarioMultipleCreate | null): boolean {
  try {
    if (solicitud) sessionStorage.setItem(clave, JSON.stringify(solicitud));
    else sessionStorage.removeItem(clave);
    return true;
  } catch { return false; }
}

function nuevaOperacion(): string {
  return globalThis.crypto?.randomUUID?.() ?? 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (caracter) => {
    const aleatorio = Math.floor(Math.random() * 16);
    return (caracter === 'x' ? aleatorio : (aleatorio & 0x3) | 0x8).toString(16);
  });
}

export function useRegistroEntrada(clave: string) {
  const [inicial] = useState(() => recuperarSolicitud(clave));
  const solicitud = useRef<CompraInventarioMultipleCreate | null>(inicial);
  const ocupado = useRef(false);
  const [enviando, setEnviando] = useState(false);
  const [pendiente, setPendiente] = useState(inicial !== null);
  const [error, setError] = useState<string | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);
  const [protegida, setProtegida] = useState<CompraInventarioMultipleCreate | null>(inicial);

  const registrar = async (captura: Omit<CompraInventarioMultipleCreate, 'operacion_id'>) => {
    if (ocupado.current) return null;
    ocupado.current = true;
    setEnviando(true);
    setError(null);
    solicitud.current ??= { ...captura, operacion_id: nuevaOperacion() };
    setProtegida(solicitud.current);
    if (!persistirSolicitud(clave, solicitud.current)) setAviso('No se pudo proteger la solicitud en este navegador. Mantén la ventana abierta hasta recibir confirmación.');
    try {
      const entrada = await inventarioService.crearCompraMultiple(solicitud.current);
      solicitud.current = null;
      if (!persistirSolicitud(clave, null)) setAviso('La entrada se guardó, pero el navegador no permitió retirar la copia local. Reintentar esa copia consulta la misma entrada; no la duplica.');
      setPendiente(false);
      return entrada;
    } catch (fallo: unknown) {
      const estado = axios.isAxiosError(fallo) ? fallo.response?.status : undefined;
      const incierto = estado === undefined || estado === 409 || estado >= 500;
      setPendiente(incierto);
      setError(`${extractErrorMessage(fallo, 'No se pudo registrar la entrada.')}${incierto ? ' Conservamos la solicitud. Reintenta sin iniciar otra entrada para evitar duplicados.' : ''}`);
      if (!incierto) { solicitud.current = null; persistirSolicitud(clave, null); }
      return null;
    } finally {
      ocupado.current = false;
      setEnviando(false);
    }
  };

  const reintentar = () => {
    if (!solicitud.current) {
      setError('El navegador perdió la solicitud protegida. Vuelve a registrar la entrada desde cero; no se enviará nada a medias.');
      setPendiente(false);
      return Promise.resolve(null);
    }
    setProtegida(solicitud.current);
    return registrar(solicitud.current);
  };
  return { registrar, reintentar, enviando, pendiente, error, aviso, protegida };
}
