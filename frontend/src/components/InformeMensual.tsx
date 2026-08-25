import React, { useEffect, useMemo, useState } from 'react';
import {
  reportesService,
  InformeMensualResponse,
  ConceptoReporte,
  ValorConceptoMensual,
  MetodoCaja,
  MovimientoCaja,
  DevolucionVenta,
} from '../services/reportesService';
import { ventaService, Venta } from '../services/ventaService';
import { getMonedas, Moneda } from '../services/gastoService';
import { buildInformePrintHtml } from '../utils/informePrintHtml';
import { SearchSelect } from './ui';

const fmtCop = (n: number | null | undefined): string =>
  `$${Math.round(Number(n) || 0).toLocaleString('es-CO')}`;

const NOMBRES_MESES = [
  'Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio',
  'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre',
];

function nombreMes(mes: string): string {
  const [year, month] = mes.split('-').map(Number);
  if (!year || !month) return mes;
  return `${NOMBRES_MESES[month - 1]} ${year}`;
}

type CajaForm = {
  metodo_caja_id: number;
  fecha: string;
  tipo: 'APERTURA' | 'ENTRADA' | 'SALIDA' | 'AJUSTE';
  monto: string;
  moneda_id: number;
  tasa_cambio: string;
  referencia: string;
  observaciones: string;
};

type DevolucionForm = {
  venta_id: number;
  fecha: string;
  cantidad: string;
  motivo: string;
  monto_devuelto: string;
  moneda_id: number;
  tasa_cambio: string;
};

const emptyCajaForm = (monedaCopId?: number): CajaForm => ({
  metodo_caja_id: 0,
  fecha: new Date().toISOString().slice(0, 10),
  tipo: 'ENTRADA',
  monto: '',
  moneda_id: monedaCopId ?? 1,
  tasa_cambio: '',
  referencia: '',
  observaciones: '',
});

const emptyDevolucionForm = (monedaCopId?: number): DevolucionForm => ({
  venta_id: 0,
  fecha: new Date().toISOString().slice(0, 10),
  cantidad: '1',
  motivo: '',
  monto_devuelto: '',
  moneda_id: monedaCopId ?? 1,
  tasa_cambio: '',
});

export default function InformeMensual() {
  const now = new Date();
  const [mes, setMes] = useState(() => {
    const month = String(now.getMonth() + 1).padStart(2, '0');
    return `${now.getFullYear()}-${month}`;
  });

  const [informe, setInforme] = useState<InformeMensualResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [errorStatus, setErrorStatus] = useState<number | null>(null);
  const [guardando, setGuardando] = useState(false);
  const [notificacion, setNotificacion] = useState<string | null>(null);

  // Catálogos
  const [conceptos, setConceptos] = useState<ConceptoReporte[]>([]);
  const [valores, setValores] = useState<ValorConceptoMensual[]>([]);
  const [metodosCaja, setMetodosCaja] = useState<MetodoCaja[]>([]);
  const [movimientos, setMovimientos] = useState<MovimientoCaja[]>([]);
  const [devoluciones, setDevoluciones] = useState<DevolucionVenta[]>([]);
  const [monedas, setMonedas] = useState<Moneda[]>([]);
  const [ventas, setVentas] = useState<Venta[]>([]);

  // Formularios
  const [edicionValores, setEdicionValores] = useState<Record<number, { inicial: string; final: string }>>({});
  const [cajaForm, setCajaForm] = useState<CajaForm>(() => emptyCajaForm());
  const [devForm, setDevForm] = useState<DevolucionForm>(() => emptyDevolucionForm());
  const [nuevoConcepto, setNuevoConcepto] = useState({ nombre: '', seccion: 'INVENTARIO' });
  const [nuevoMetodo, setNuevoMetodo] = useState({ nombre: '', codigo: '' });
  const [panelAbierto, setPanelAbierto] = useState<string | null>('corte');

  const monedaCop = useMemo(() => monedas.find((m) => m.codigo === 'COP'), [monedas]);

  const cargarTodo = async () => {
    setLoading(true);
    setError(null);
    setErrorStatus(null);
    try {
      const [inf, conc, val, met, mov, dev, mon] = await Promise.all([
        reportesService.getInformeMensual(mes),
        reportesService.getConceptos(),
        reportesService.getValoresMensuales(mes),
        reportesService.getMetodosCaja(),
        reportesService.getMovimientosCaja(),
        reportesService.getDevoluciones(),
        getMonedas(),
      ]);
      setInforme(inf);
      setConceptos(conc);
      setValores(val);
      setMetodosCaja(met);
      setMovimientos(mov);
      setDevoluciones(dev);
      setMonedas(mon);
      setEdicionValores(
        conc.reduce<Record<number, { inicial: string; final: string }>>((acc, c) => {
          const v = val.find((v) => v.concepto_id === c.id);
          acc[c.id] = {
            inicial: v ? String(Math.round(v.valor_inicial)) : '',
            final: v ? String(Math.round(v.valor_final)) : '',
          };
          return acc;
        }, {}),
      );
      setCajaForm((f) => (f.metodo_caja_id ? f : emptyCajaForm(mon.find((m) => m.codigo === 'COP')?.id)));
      setDevForm((f) => (f.venta_id ? f : emptyDevolucionForm(mon.find((m) => m.codigo === 'COP')?.id)));
    } catch (e: any) {
      console.error(e);
      setErrorStatus(e?.response?.status ?? null);
      setError(
        e?.response?.status === 403
          ? 'Solo los dueños y administradores pueden ver los reportes financieros.'
          : (e?.response?.data?.detail ?? 'No se pudo cargar el informe mensual.'),
      );
    } finally {
      setLoading(false);
    }
  };

  const cargarVentas = async () => {
    try {
      const vs = await ventaService.getAll({ limite: 200 });
      setVentas(vs);
    } catch (e) {
      console.error(e);
    }
  };

  useEffect(() => {
    cargarTodo();
  }, [mes]);

  useEffect(() => {
    if (panelAbierto === 'devoluciones' && ventas.length === 0) cargarVentas();
  }, [panelAbierto]);

  const avisar = (msg: string) => {
    setNotificacion(msg);
    setTimeout(() => setNotificacion(null), 3500);
  };

  // ---- Corte de inventario ----
  const guardarValores = async () => {
    setGuardando(true);
    try {
      const payload: ValorConceptoMensual[] = conceptos
        .filter((c) => c.activo)
        .map((c) => {
          const e = edicionValores[c.id] ?? { inicial: '', final: '' };
          return {
            mes,
            concepto_id: c.id,
            valor_inicial: Number(e.inicial) || 0,
            valor_final: Number(e.final) || 0,
            moneda_id: monedaCop?.id ?? 1,
          };
        });
      const guardados = await reportesService.guardarValoresMensuales(mes, payload);
      setValores(guardados);
      avisar('Corte de inventario guardado.');
      await cargarTodo();
    } catch (e: any) {
      console.error(e);
      setError(e?.response?.data?.detail ?? 'Error al guardar el corte de inventario.');
    } finally {
      setGuardando(false);
    }
  };

  // ---- Conceptos ----
  const agregarConcepto = async () => {
    if (!nuevoConcepto.nombre.trim()) return;
    try {
      await reportesService.crearConcepto({ nombre: nuevoConcepto.nombre.trim(), seccion: nuevoConcepto.seccion });
      setNuevoConcepto({ nombre: '', seccion: 'INVENTARIO' });
      avisar('Línea de inventario agregada.');
      await cargarTodo();
    } catch (e: any) {
      setError(e?.response?.data?.detail ?? 'Error al crear el concepto.');
    }
  };

  const eliminarConcepto = async (id: number) => {
    try {
      await reportesService.eliminarConcepto(id);
      avisar('Línea eliminada.');
      await cargarTodo();
    } catch (e: any) {
      setError(e?.response?.data?.detail ?? 'No se pudo eliminar (puede tener valores guardados).');
    }
  };

  // ---- Métodos de caja ----
  const agregarMetodo = async () => {
    if (!nuevoMetodo.nombre.trim() || !nuevoMetodo.codigo.trim()) return;
    try {
      await reportesService.crearMetodoCaja({ nombre: nuevoMetodo.nombre.trim(), codigo: nuevoMetodo.codigo.trim().toUpperCase() });
      setNuevoMetodo({ nombre: '', codigo: '' });
      avisar('Método de caja agregado.');
      await cargarTodo();
    } catch (e: any) {
      setError(e?.response?.data?.detail ?? 'Error al crear el método de caja.');
    }
  };

  // ---- Movimientos de caja ----
  const registrarMovimiento = async () => {
    const monto = Number(cajaForm.monto);
    if (!cajaForm.metodo_caja_id || !monto || monto <= 0) {
      setError('Selecciona el método de caja y escribe un monto válido.');
      return;
    }
    setGuardando(true);
    try {
      await reportesService.crearMovimientoCaja({
        metodo_caja_id: cajaForm.metodo_caja_id,
        fecha: cajaForm.fecha,
        tipo: cajaForm.tipo,
        monto,
        moneda_id: cajaForm.moneda_id,
        tasa_cambio: cajaForm.tasa_cambio ? Number(cajaForm.tasa_cambio) : undefined,
        referencia: cajaForm.referencia || undefined,
        observaciones: cajaForm.observaciones || undefined,
      });
      setCajaForm(emptyCajaForm(monedaCop?.id));
      avisar('Movimiento de caja registrado.');
      await cargarTodo();
    } catch (e: any) {
      setError(e?.response?.data?.detail ?? 'Error al registrar el movimiento.');
    } finally {
      setGuardando(false);
    }
  };

  const eliminarMovimiento = async (id: number) => {
    try {
      await reportesService.eliminarMovimientoCaja(id);
      avisar('Movimiento eliminado.');
      await cargarTodo();
    } catch (e: any) {
      setError(e?.response?.data?.detail ?? 'No se pudo eliminar el movimiento.');
    }
  };

  // ---- Devoluciones ----
  const registrarDevolucion = async () => {
    const monto = Number(devForm.monto_devuelto);
    if (!devForm.venta_id || !monto || monto <= 0) {
      setError('Selecciona la venta y escribe el monto devuelto.');
      return;
    }
    setGuardando(true);
    try {
      await reportesService.crearDevolucion({
        venta_id: devForm.venta_id,
        fecha: devForm.fecha,
        cantidad: Number(devForm.cantidad) || 1,
        motivo: devForm.motivo || undefined,
        monto_devuelto: monto,
        moneda_id: devForm.moneda_id,
        tasa_cambio: devForm.tasa_cambio ? Number(devForm.tasa_cambio) : undefined,
      });
      setDevForm(emptyDevolucionForm(monedaCop?.id));
      avisar('Devolución registrada.');
      await cargarTodo();
    } catch (e: any) {
      setError(e?.response?.data?.detail ?? 'Error al registrar la devolución.');
    } finally {
      setGuardando(false);
    }
  };

  const eliminarDevolucion = async (id: number) => {
    try {
      await reportesService.eliminarDevolucion(id);
      avisar('Devolución eliminada.');
      await cargarTodo();
    } catch (e: any) {
      setError(e?.response?.data?.detail ?? 'No se pudo eliminar la devolución.');
    }
  };

  // ---- Saldos de caja (por método) ----
  const saldosCaja = useMemo(() => {
    return metodosCaja.map((met) => {
      const movs = movimientos.filter((m) => m.metodo_caja_id === met.id);
      const apertura = movs.filter((m) => m.tipo === 'APERTURA').reduce((a, m) => a + m.monto_en_moneda_base, 0);
      const entradas = movs.filter((m) => m.tipo === 'ENTRADA').reduce((a, m) => a + m.monto_en_moneda_base, 0);
      const salidas = movs.filter((m) => m.tipo === 'SALIDA').reduce((a, m) => a + m.monto_en_moneda_base, 0);
      const ajustes = movs.filter((m) => m.tipo === 'AJUSTE').reduce((a, m) => a + m.monto_en_moneda_base, 0);
      return { metodo: met, apertura, entradas, salidas, ajustes, saldo: apertura + entradas - salidas + ajustes };
    });
  }, [metodosCaja, movimientos]);

  const panelBtn = (key: string, titulo: string, desc: string) => (    <button
      onClick={() => setPanelAbierto(panelAbierto === key ? null : key)}
      className={`w-full flex items-center justify-between px-5 py-4 rounded-2xl border transition-all text-left ${
        panelAbierto === key
          ? 'bg-yeikar-primary/5 border-yeikar-primary/40'
          : 'bg-white border-yeikar-secondary-light/10 hover:border-yeikar-secondary/30'
      }`}
    >
      <div>
        <p className="font-headline font-bold text-sm text-yeikar-secondary">{titulo}</p>
        <p className="text-xs text-yeikar-neutral/50 mt-0.5">{desc}</p>
      </div>
      <span className={`text-yeikar-primary text-lg font-bold transition-transform ${panelAbierto === key ? 'rotate-90' : ''}`}>›</span>
    </button>
  );

  const inputCls =
    'bg-yeikar-tertiary/40 border border-yeikar-secondary-light/10 rounded-lg px-3 py-2 text-sm text-yeikar-neutral focus:outline-none focus:border-yeikar-primary w-full';

  return (
    <div className="space-y-6 print:space-y-3">
      {/* Notificación */}
      {notificacion && (
        <div className="bg-green-50 border border-green-200 text-green-800 text-sm font-semibold px-4 py-3 rounded-xl print:hidden">
          {notificacion}
        </div>
      )}
      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 text-sm font-semibold px-4 py-3 rounded-xl print:hidden">
          {error}
        </div>
      )}

      {/* Encabezado */}
      <div className="flex flex-wrap items-center justify-between gap-4 bg-white border border-yeikar-secondary-light/10 rounded-2xl p-5 shadow-sm print:hidden">
        <div className="flex flex-wrap items-center gap-4">
          <div className="flex items-center gap-3">
            <label className="text-sm font-bold text-yeikar-secondary">Mes:</label>
            <input
              type="month"
              value={mes}
              onChange={(e) => e.target.value && setMes(e.target.value)}
              className="bg-yeikar-tertiary/40 border border-yeikar-secondary-light/10 rounded-xl px-4 py-2 text-sm text-yeikar-neutral focus:outline-none focus:border-yeikar-primary"
            />
          </div>
          <button
            onClick={() => {
              if (!informe) return;
              const w = window.open('', '_blank');
              if (!w) return;
              w.document.write(buildInformePrintHtml(informe, mes));
              w.document.close();
              w.focus();
              setTimeout(() => w.print(), 300);
            }}
            className="bg-yeikar-primary text-yeikar-neutral font-headline font-bold text-sm px-5 py-2.5 rounded-xl hover:bg-yeikar-secondary transition-colors shadow-sm"
          >
            Imprimir / PDF
          </button>
        </div>
        <div className="text-right">
          <p className="font-headline font-bold text-yeikar-secondary">Informe Mensual</p>
          <p className="text-xs font-mono text-yeikar-neutral/50">Todas las cifras en COP</p>
        </div>
      </div>

      {/* Encabezado del documento (solo impresión) */}
      <div className="hidden print:block border-b-4 border-yeikar-neutral pb-4 mb-6">
        <div className="flex items-end justify-between">
          <div>
            <p className="font-headline font-black text-3xl tracking-tight text-yeikar-neutral">YEIKAR</p>
            <p className="font-mono text-xs text-yeikar-neutral/60 uppercase tracking-widest mt-0.5">Fábrica de Muebles · C.A.</p>
          </div>
          <div className="text-right">
            <p className="font-headline font-black text-xl text-yeikar-neutral uppercase tracking-tight">Informe Mensual</p>
            <p className="text-sm font-semibold text-yeikar-neutral/80">{nombreMes(mes)}</p>
            <p className="text-xs text-yeikar-neutral/60">Generado el {new Date().toLocaleDateString('es-CO')} · Todas las cifras en COP</p>
          </div>
        </div>
      </div>

      {loading && !informe ? (
        <div className="flex flex-col items-center justify-center py-24 space-y-3">
          <div className="w-10 h-10 border-4 border-yeikar-primary border-t-transparent rounded-full animate-spin"></div>
          <p className="text-xs font-mono text-yeikar-neutral/60">Generando informe...</p>
        </div>
      ) : error && !informe ? (
        <div className="flex flex-col items-center justify-center gap-3 rounded-2xl border border-red-200/70 bg-red-50/60 px-6 py-14 text-center print:hidden">
          {errorStatus === 403 ? (
            <svg className="w-10 h-10 text-yeikar-primary-dark" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 15v2m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.964-.833-2.732 0L4.082 16.5c-.77.833.192 2.5 1.732 2.5z" />
            </svg>
          ) : (
            <svg className="w-10 h-10 text-rose-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.964-.833-2.732 0L4.082 16.5c-.77.833.192 2.5 1.732 2.5z" />
            </svg>
          )}
          <p className="font-headline text-base font-bold text-yeikar-secondary">
            {errorStatus === 403 ? 'Acceso restringido' : 'No se pudo cargar el informe'}
          </p>
          <p className="max-w-md text-sm text-yeikar-neutral/60">{error}</p>
          <button
            onClick={cargarTodo}
            className="mt-2 rounded-xl bg-yeikar-primary px-5 py-2.5 font-headline text-sm font-bold text-yeikar-neutral shadow-gold transition-colors hover:bg-yeikar-primary-light"
          >
            Reintentar
          </button>
        </div>
      ) : !informe ? null : (
          <>
            {/* ── Sección 1: Control Interno de Ingresos ── */}
            <div className="bg-white border border-yeikar-secondary-light/10 rounded-3xl shadow-sm overflow-hidden print:border-gray-400 print:rounded-none print:shadow-none">
              <div className="p-5 border-b border-yeikar-secondary-light/5 flex items-center justify-between print:px-0 print:border-b print:border-gray-400 print:bg-gray-100 print-color-adjust">
                <div>
                  <h3 className="text-lg font-black font-headline text-yeikar-neutral tracking-tight">1. CONTROL INTERNO DE INGRESOS</h3>
                  <p className="text-xs text-yeikar-neutral/50 mt-0.5">{nombreMes(mes)}</p>
                </div>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-left border-collapse text-sm">
                  <thead>
                    <tr className="bg-yeikar-tertiary/20 text-yeikar-secondary font-headline font-bold text-[11px] uppercase tracking-wider print:bg-gray-200 print:text-black print-color-adjust">
                      <th className="p-3 border-b border-yeikar-secondary-light/5 print:border-gray-400">Fecha</th>
                      <th className="p-3 border-b border-yeikar-secondary-light/5 print:border-gray-400">Cliente</th>
                      <th className="p-3 border-b border-yeikar-secondary-light/5 text-center print:border-gray-400">Cant.</th>
                      <th className="p-3 border-b border-yeikar-secondary-light/5 print:border-gray-400">Detalle Producto</th>
                      <th className="p-3 border-b border-yeikar-secondary-light/5 text-right print:border-gray-400">Precio Costo</th>
                      <th className="p-3 border-b border-yeikar-secondary-light/5 text-center print:border-gray-400">% Gan.</th>
                      <th className="p-3 border-b border-yeikar-secondary-light/5 text-right print:border-gray-400">Utilidad</th>
                      <th className="p-3 border-b border-yeikar-secondary-light/5 text-right print:border-gray-400">Precio de Venta</th>
                      <th className="p-3 border-b border-yeikar-secondary-light/5 text-center print:border-gray-400">Mon.</th>
                      <th className="p-3 border-b border-yeikar-secondary-light/5 text-right print:border-gray-400">Tasa</th>
                      <th className="p-3 border-b border-yeikar-secondary-light/5 text-right print:border-gray-400">Valor en COP</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-yeikar-secondary-light/5 print:divide-gray-300">
                    {informe.control_interno_ingresos.lineas.length === 0 ? (
                      <tr>
                        <td colSpan={11} className="p-8 text-center text-yeikar-neutral/40 italic">
                          No hay ventas registradas para este mes.
                        </td>
                      </tr>
                    ) : (
                      informe.control_interno_ingresos.lineas.map((l, i) => (
                        <tr key={i} className={`hover:bg-yeikar-tertiary/10 transition-colors ${l.es_devolucion ? 'bg-red-50/60' : ''}`}>
                          <td className="p-3 font-mono text-xs">{l.fecha.slice(0, 10)}</td>
                          <td className="p-3 font-semibold text-yeikar-secondary">{l.cliente}</td>
                          <td className="p-3 text-center font-mono">{l.cantidad}</td>
                          <td className="p-3 text-yeikar-neutral/80">{l.producto}</td>
                          <td className={`p-3 text-right font-mono ${l.es_devolucion ? 'text-red-500 line-through' : 'text-yeikar-neutral/60'}`}>{fmtCop(l.precio_costo)}</td>
                          <td className="p-3 text-center font-mono text-xs text-yeikar-neutral/50">{l.porcentaje_ganancia != null ? `${Number(l.porcentaje_ganancia).toFixed(1)}%` : '—'}</td>
                          <td className={`p-3 text-right font-mono font-semibold ${l.es_devolucion ? 'text-red-500' : 'text-green-600'}`}>{fmtCop(l.utilidad)}</td>
                          <td className="p-3 text-right font-mono font-bold text-yeikar-neutral">{fmtCop(l.precio_venta)}</td>
                          <td className="p-3 text-center font-mono text-xs text-yeikar-neutral/50">{l.moneda}</td>
                          <td className="p-3 text-right font-mono text-xs text-yeikar-neutral/50">{l.tasa_cambio ? Number(l.tasa_cambio).toLocaleString('es-CO') : '—'}</td>
                          <td className={`p-3 text-right font-mono font-bold ${l.es_devolucion ? 'text-red-500' : 'text-yeikar-primary'}`}>{fmtCop(l.precio_venta_en_base)}</td>
                        </tr>
                      ))
                    )}
                  </tbody>
                  <tfoot>
                    <tr className="bg-yeikar-tertiary/30 font-headline font-bold text-sm print:bg-gray-200 print:text-black print-color-adjust">
                      <td colSpan={4} className="p-3 text-yeikar-secondary uppercase tracking-wide print:border-t print:border-gray-400">TOTALES</td>
                      <td className="p-3 text-right font-mono text-yeikar-neutral/70 print:border-t print:border-gray-400">{fmtCop(informe.control_interno_ingresos.totales.precio_costo)}</td>
                      <td className="print:border-t print:border-gray-400"></td>
                      <td className="p-3 text-right font-mono text-green-700 print:border-t print:border-gray-400">{fmtCop(informe.control_interno_ingresos.totales.utilidad)}</td>
                      <td className="p-3 text-right font-mono text-yeikar-neutral print:border-t print:border-gray-400">{fmtCop(informe.control_interno_ingresos.totales.precio_venta)}</td>
                      <td className="print:border-t print:border-gray-400"></td>
                      <td className="print:border-t print:border-gray-400"></td>
                      <td className="p-3 text-right font-mono text-yeikar-primary text-base print:border-t print:border-gray-400">{fmtCop(informe.control_interno_ingresos.totales.precio_venta_en_base)}</td>
                    </tr>
                  </tfoot>
                </table>
              </div>
            </div>

            {/* ── Sección 2: Resumen del Mes ── */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4 print:grid-cols-3 print:gap-3 print:mt-2">
              <div className="bg-white border border-yeikar-secondary-light/10 rounded-2xl p-5 shadow-sm print:border-gray-400 print:rounded-none print:shadow-none print:p-3">
                <p className="text-xs font-headline font-bold uppercase tracking-wider text-yeikar-neutral/50 print:text-black">INGRESOS (+)</p>
                <p className="text-2xl font-black font-mono text-green-600 mt-1 print:text-xl">{fmtCop(informe.resumen.ingresos)}</p>
              </div>
              <div className="bg-white border border-yeikar-secondary-light/10 rounded-2xl p-5 shadow-sm print:border-gray-400 print:rounded-none print:shadow-none print:p-3">
                <p className="text-xs font-headline font-bold uppercase tracking-wider text-yeikar-neutral/50 print:text-black">EGRESOS (−)</p>
                <p className="text-2xl font-black font-mono text-red-500 mt-1 print:text-xl">{fmtCop(informe.resumen.egresos)}</p>
              </div>
              <div className="bg-white border border-yeikar-primary/30 rounded-2xl p-5 shadow-sm print:border-gray-400 print:rounded-none print:shadow-none print:p-3">
                <p className="text-xs font-headline font-bold uppercase tracking-wider text-yeikar-secondary print:text-black">DISPONIBLE</p>
                <p className={`text-2xl font-black font-mono mt-1 print:text-xl ${informe.resumen.disponible >= 0 ? 'text-yeikar-primary' : 'text-red-500'}`}>{fmtCop(informe.resumen.disponible)}</p>
              </div>
            </div>

            {/* ── Sección 3: Estado de Resultados ── */}
            <div className="print:break-before-page">
              <h4 className="hidden print:block font-headline font-black text-lg text-yeikar-neutral uppercase tracking-tight pb-2 mb-4 border-b-2 border-yeikar-neutral">3. Estado de Resultados</h4>
            </div>
            <div className="bg-white border border-yeikar-secondary-light/10 rounded-3xl shadow-sm overflow-hidden print:border-gray-400 print:rounded-none print:shadow-none">
              <div className="p-5 border-b border-yeikar-secondary-light/5 print:hidden">
                <h3 className="text-lg font-black font-headline text-yeikar-neutral tracking-tight">ESTADO DE RESULTADOS</h3>
              </div>
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-0 print:grid-cols-1 print:gap-4">
                {/* Columna izquierda */}
                <div className="p-5 space-y-6 border-b lg:border-b-0 lg:border-r border-yeikar-secondary-light/5 print:p-0 print:border-0">
                  {/* Ventas */}
                  <div className="space-y-1.5">
                    <p className="text-xs font-headline font-bold uppercase tracking-wider text-yeikar-secondary border-b border-yeikar-secondary-light/10 pb-1.5">Ventas</p>
                    <Row label="Contado" valor={informe.estado_resultados.ventas.contado} />
                    <Row label="Crédito" valor={informe.estado_resultados.ventas.credito} />
                    <Row label="(−) Devoluciones" valor={-informe.estado_resultados.ventas.devoluciones} negative />
                    <Row label="(−) Descuentos" valor={-informe.estado_resultados.ventas.descuentos} negative />
                    <Row label="Total Ventas Netas" valor={informe.estado_resultados.ventas.total_ventas_netas} strong />
                  </div>

                  {/* Inventario inicial */}
                  <div className="space-y-1.5">
                    <p className="text-xs font-headline font-bold uppercase tracking-wider text-yeikar-secondary border-b border-yeikar-secondary-light/10 pb-1.5">Inventario Inicial</p>
                    {informe.estado_resultados.inventarios_iniciales.map((l) => (
                      <Row key={l.concepto_id} label={l.nombre} valor={l.valor} />
                    ))}
                    <Row label="Total Inventario Inicial" valor={informe.estado_resultados.total_inventarios_iniciales} strong />
                  </div>

                  {/* Compras */}
                  <div className="space-y-1.5">
                    <p className="text-xs font-headline font-bold uppercase tracking-wider text-yeikar-secondary border-b border-yeikar-secondary-light/10 pb-1.5">Compras</p>
                    <Row label="Contado" valor={informe.estado_resultados.compras.contado} />
                    <Row label="Crédito" valor={informe.estado_resultados.compras.credito} />
                    <Row label="Total Mercancía" valor={informe.estado_resultados.compras.total_mercancia} strong />
                  </div>

                  {/* Inventario final + caja */}
                  <div className="space-y-1.5">
                    <p className="text-xs font-headline font-bold uppercase tracking-wider text-yeikar-secondary border-b border-yeikar-secondary-light/10 pb-1.5">Inventario Final</p>
                    {informe.estado_resultados.inventarios_finales.map((l) => (
                      <Row key={l.concepto_id} label={l.nombre} valor={l.valor} />
                    ))}
                    <Row label="Total Inventario Final" valor={informe.estado_resultados.total_inventarios_finales} strong />
                  </div>
                </div>

                {/* Columna derecha */}
                <div className="p-5 space-y-6 print:p-0">
                  <div className="space-y-1.5">
                    <Row label="Compras Netas" valor={informe.estado_resultados.compras_netas} strong label2="Inv. Inicial + Mercancía − Inv. Final" />
                    <Row label="Utilidad Bruta" valor={informe.estado_resultados.utilidad_bruta} strong highlight />
                  </div>

                  {/* Gastos */}
                  <div className="space-y-1.5">
                    <p className="text-xs font-headline font-bold uppercase tracking-wider text-yeikar-secondary border-b border-yeikar-secondary-light/10 pb-1.5">Gastos del Periodo</p>
                    <GastoGrupo titulo="Operativos" lineas={informe.estado_resultados.gastos.operativos} total={informe.estado_resultados.gastos.total_gastos_operativos} />
                    <GastoGrupo titulo="Administrativos" lineas={informe.estado_resultados.gastos.administrativos} total={informe.estado_resultados.gastos.total_gastos_administrativos} />
                    <GastoGrupo titulo="Financieros" lineas={informe.estado_resultados.gastos.financieros} total={informe.estado_resultados.gastos.total_financieros} />
                    <GastoGrupo titulo="Impuestos" lineas={informe.estado_resultados.gastos.impuestos} total={informe.estado_resultados.gastos.total_impuestos} />
                    <GastoGrupo titulo="Producción" lineas={informe.estado_resultados.gastos.produccion ?? []} total={informe.estado_resultados.gastos.total_gastos_produccion ?? 0} />
                    <Row label="Total Gastos" valor={informe.estado_resultados.gastos.total_gastos} strong negative />
                  </div>

                  <div className="border-t-2 border-yeikar-primary/40 pt-4">
                    <div className="flex justify-between items-end">
                      <span className="font-headline font-black text-lg text-yeikar-neutral uppercase tracking-tight">Utilidad del Periodo</span>
                      <span className={`font-mono font-black text-2xl ${informe.estado_resultados.utilidad_periodo >= 0 ? 'text-green-600' : 'text-red-500'}`}>
                        {fmtCop(informe.estado_resultados.utilidad_periodo)}
                      </span>
                    </div>
                  </div>
                </div>
              </div>
            </div>

            {/* ── Sección 4: Pendientes de Pago ── */}
            <div className="print:break-before-page">
              <h4 className="hidden print:block font-headline font-black text-lg text-yeikar-neutral uppercase tracking-tight pb-2 mb-4 border-b-2 border-yeikar-neutral">4. Pendientes de Pago al Cierre</h4>
            </div>
            <div className="bg-white border border-yeikar-secondary-light/10 rounded-3xl shadow-sm overflow-hidden print:border-gray-400 print:rounded-none print:shadow-none">
              <div className="p-5 border-b border-yeikar-secondary-light/5 print:px-0 print:bg-gray-100 print-color-adjust print:border-b print:border-gray-400">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div>
                    <h3 className="text-lg font-black font-headline text-yeikar-neutral tracking-tight">PENDIENTES DE PAGO AL CIERRE</h3>
                    <p className="text-xs text-yeikar-neutral/50 mt-0.5">Pedidos y ventas sin cobrar al cierre del mes</p>
                  </div>
                  <div className="text-right">
                    <p className="text-[11px] font-headline font-bold uppercase tracking-wider text-yeikar-neutral/50">Total pendiente</p>
                    <p className="font-mono font-black text-xl text-red-500">{fmtCop(informe.pendientes_de_pago.total_pendiente)}</p>
                  </div>
                </div>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-left border-collapse text-sm">
                  <thead>
                    <tr className="bg-yeikar-tertiary/20 text-yeikar-secondary font-headline font-bold text-[11px] uppercase tracking-wider print:bg-gray-200 print:text-black print-color-adjust">
                      <th className="p-3 border-b border-yeikar-secondary-light/5 print:border-gray-400">Pedido</th>
                      <th className="p-3 border-b border-yeikar-secondary-light/5 print:border-gray-400">Fecha</th>
                      <th className="p-3 border-b border-yeikar-secondary-light/5 print:border-gray-400">Cliente</th>
                      <th className="p-3 border-b border-yeikar-secondary-light/5 print:border-gray-400">Productos</th>
                      <th className="p-3 border-b border-yeikar-secondary-light/5 print:border-gray-400">Estado</th>
                      <th className="p-3 border-b border-yeikar-secondary-light/5 text-center print:border-gray-400">Mon.</th>
                      <th className="p-3 border-b border-yeikar-secondary-light/5 text-right print:border-gray-400">Total</th>
                      <th className="p-3 border-b border-yeikar-secondary-light/5 text-right print:border-gray-400">Pagado</th>
                      <th className="p-3 border-b border-yeikar-secondary-light/5 text-right print:border-gray-400">Saldo (COP)</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-yeikar-secondary-light/5 print:divide-gray-300">
                    {informe.pendientes_de_pago.lineas.length === 0 ? (
                      <tr>
                        <td colSpan={9} className="p-8 text-center text-green-600 font-semibold italic">
                          No hay pendientes de pago al cierre de este mes.
                        </td>
                      </tr>
                    ) : (
                      informe.pendientes_de_pago.lineas.map((l, i) => (
                        <tr key={`${l.pedido_id}-${i}`} className="hover:bg-yeikar-tertiary/10 transition-colors">
                          <td className="p-3 font-mono text-xs text-yeikar-neutral/70">#{l.pedido_id}</td>
                          <td className="p-3 font-mono text-xs">{l.fecha.slice(0, 10)}</td>
                          <td className="p-3 font-semibold text-yeikar-secondary">{l.cliente}</td>
                          <td className="p-3 text-yeikar-neutral/80">{l.producto}</td>
                          <td className="p-3">
                            {l.estado_venta ? (
                              <span
                                className={`px-2 py-0.5 rounded-full text-[10px] font-bold whitespace-nowrap ${
                                  l.estado_venta === 'PENDIENTE'
                                    ? 'bg-amber-50 text-amber-700'
                                    : l.estado_venta === 'ABONADA'
                                      ? 'bg-blue-50 text-blue-700'
                                      : 'bg-gray-50 text-gray-700'
                                }`}
                              >
                                {l.estado_venta}
                              </span>
                            ) : (
                              <div className="flex flex-col gap-0.5">
                                <span className="px-2 py-0.5 rounded-full bg-gray-100 text-gray-500 text-[10px] font-bold whitespace-nowrap self-start">SIN FACTURAR</span>
                                <span className="text-[10px] font-mono text-yeikar-neutral/40">{l.estado_pedido}</span>
                              </div>
                            )}
                          </td>
                          <td className="p-3 text-center font-mono text-xs text-yeikar-neutral/50">{l.moneda}</td>
                          <td className="p-3 text-right font-mono text-yeikar-neutral/70">{fmtCop(l.total_en_base)}</td>
                          <td className="p-3 text-right font-mono text-green-600">{fmtCop(l.pagado_en_base)}</td>
                          <td className="p-3 text-right font-mono font-bold text-red-500">{fmtCop(l.saldo_en_base)}</td>
                        </tr>
                      ))
                    )}
                  </tbody>
                  <tfoot>
                    <tr className="bg-yeikar-tertiary/30 font-headline font-bold text-sm print:bg-gray-200 print:text-black print-color-adjust">
                      <td colSpan={8} className="p-3 text-yeikar-secondary uppercase tracking-wide print:border-t print:border-gray-400">TOTAL PENDIENTE DE PAGO</td>
                      <td className="p-3 text-right font-mono text-red-500 print:border-t print:border-gray-400">{fmtCop(informe.pendientes_de_pago.total_pendiente)}</td>
                    </tr>
                  </tfoot>
                </table>
              </div>
            </div>

            {/* ── Paneles de edición ── */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 print:hidden">
              {/* Corte de inventario */}
              <div className="space-y-2">
                {panelBtn('corte', 'Corte de Inventario', 'Valores iniciales y finales del mes por línea')}
                {panelAbierto === 'corte' && (
                  <div className="bg-white border border-yeikar-secondary-light/10 rounded-2xl p-5 shadow-sm space-y-3">
                    <div className="overflow-x-auto max-h-96 overflow-y-auto">
                      <table className="w-full text-sm border-collapse">
                        <thead className="sticky top-0 bg-white">
                          <tr className="text-yeikar-secondary font-headline font-bold text-[11px] uppercase tracking-wider border-b border-yeikar-secondary-light/10">
                            <th className="p-2 text-left">Línea</th>
                            <th className="p-2 text-right">Inicial</th>
                            <th className="p-2 text-right">Final</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-yeikar-secondary-light/5">
                          {conceptos.filter((c) => c.activo).map((c) => (
                            <tr key={c.id}>
                              <td className="p-2 text-yeikar-neutral/80 font-medium">{c.nombre}</td>
                              <td className="p-2">
                                <input
                                  type="number"
                                  min="0"
                                  step="0.01"
                                  value={edicionValores[c.id]?.inicial ?? ''}
                                  placeholder="0"
                                  onChange={(e) =>
                                    setEdicionValores((prev) => ({ ...prev, [c.id]: { ...(prev[c.id] ?? { inicial: '', final: '' }), inicial: e.target.value } }))
                                  }
                                  className={inputCls}
                                />
                              </td>
                              <td className="p-2">
                                <input
                                  type="number"
                                  min="0"
                                  step="0.01"
                                  value={edicionValores[c.id]?.final ?? ''}
                                  placeholder="0"
                                  onChange={(e) =>
                                    setEdicionValores((prev) => ({ ...prev, [c.id]: { ...(prev[c.id] ?? { inicial: '', final: '' }), final: e.target.value } }))
                                  }
                                  className={inputCls}
                                />
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                    <div className="flex items-center justify-between gap-3">
                      <div className="flex gap-2 flex-wrap">
                        <input
                          value={nuevoConcepto.nombre}
                          onChange={(e) => setNuevoConcepto((p) => ({ ...p, nombre: e.target.value }))}
                          placeholder="Nueva línea de inventario..."
                          className={inputCls}
                          style={{ width: '220px' }}
                        />
                        <select
                          value={nuevoConcepto.seccion}
                          onChange={(e) => setNuevoConcepto((p) => ({ ...p, seccion: e.target.value }))}
                          className={inputCls}
                          style={{ width: 'auto' }}
                        >
                          <option value="INVENTARIO">INVENTARIO</option>
                          <option value="OTRO">OTRO</option>
                        </select>
                        <button onClick={agregarConcepto} className="bg-yeikar-tertiary text-yeikar-neutral font-bold text-xs px-3 py-2 rounded-lg hover:bg-yeikar-secondary hover:text-white transition-colors">
                          + Agregar
                        </button>
                      </div>
                      <button
                        onClick={guardarValores}
                        disabled={guardando}
                        className="bg-yeikar-primary text-yeikar-neutral font-headline font-bold text-sm px-5 py-2.5 rounded-xl hover:bg-yeikar-secondary transition-colors disabled:opacity-50"
                      >
                        {guardando ? 'Guardando...' : 'Guardar Corte'}
                      </button>
                    </div>
                  </div>
                )}
              </div>

              {/* Caja */}
              <div className="space-y-2">
                {panelBtn('caja', 'Caja', 'Movimientos y saldos por método')}
                {panelAbierto === 'caja' && (
                  <div className="bg-white border border-yeikar-secondary-light/10 rounded-2xl p-5 shadow-sm space-y-4">
                    {/* Saldos */}
                    <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
                      {saldosCaja.map((s) => (
                        <div key={s.metodo.id} className="border border-yeikar-secondary-light/10 rounded-xl p-3 bg-yeikar-tertiary/10">
                          <p className="text-[10px] font-bold uppercase tracking-wider text-yeikar-neutral/50 truncate">{s.metodo.nombre}</p>
                          <p className={`font-mono font-bold text-sm ${s.saldo >= 0 ? 'text-yeikar-primary' : 'text-red-500'}`}>{fmtCop(s.saldo)}</p>
                        </div>
                      ))}
                    </div>

                    {/* Formulario */}
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
                      <SearchSelect
                        value={cajaForm.metodo_caja_id}
                        onChange={(v) => setCajaForm((f) => ({ ...f, metodo_caja_id: Number(v) }))}
                        options={[
                          { value: 0, label: 'Método...' },
                          ...metodosCaja.map((m) => ({ value: m.id, label: m.nombre })),
                        ]}
                        placeholder="Método..."
                      />
                      <input type="date" value={cajaForm.fecha} onChange={(e) => setCajaForm((f) => ({ ...f, fecha: e.target.value }))} className={inputCls} />
                      <select value={cajaForm.tipo} onChange={(e) => setCajaForm((f) => ({ ...f, tipo: e.target.value as any }))} className={inputCls}>
                        <option value="ENTRADA">Entrada</option>
                        <option value="SALIDA">Salida</option>
                        <option value="APERTURA">Apertura</option>
                        <option value="AJUSTE">Ajuste</option>
                      </select>
                      <input type="number" min="0" step="0.01" value={cajaForm.monto} onChange={(e) => setCajaForm((f) => ({ ...f, monto: e.target.value }))} placeholder="Monto" className={inputCls} />
                      <SearchSelect
                        value={cajaForm.moneda_id}
                        onChange={(v) => setCajaForm((f) => ({ ...f, moneda_id: Number(v) }))}
                        options={monedas.map((m) => ({ value: m.id, label: m.codigo }))}
                        placeholder="Moneda..."
                      />
                      <input type="number" min="0" step="0.01" value={cajaForm.tasa_cambio} onChange={(e) => setCajaForm((f) => ({ ...f, tasa_cambio: e.target.value }))} placeholder="Tasa (COP/1) si no es COP" className={inputCls} />
                      <input value={cajaForm.referencia} onChange={(e) => setCajaForm((f) => ({ ...f, referencia: e.target.value }))} placeholder="Referencia" className={inputCls} />
                      <button onClick={registrarMovimiento} disabled={guardando} className="bg-yeikar-primary text-yeikar-neutral font-bold text-sm rounded-lg hover:bg-yeikar-secondary transition-colors disabled:opacity-50 py-2">
                        {guardando ? '...' : '+ Registrar'}
                      </button>
                    </div>

                    {/* Lista */}
                    <div className="overflow-x-auto max-h-64 overflow-y-auto">
                      <table className="w-full text-xs border-collapse">
                        <thead className="sticky top-0 bg-white">
                          <tr className="text-yeikar-secondary font-headline font-bold uppercase tracking-wider border-b border-yeikar-secondary-light/10">
                            <th className="p-2 text-left">Fecha</th>
                            <th className="p-2 text-left">Método</th>
                            <th className="p-2 text-left">Tipo</th>
                            <th className="p-2 text-right">Monto</th>
                            <th className="p-2 text-right">COP</th>
                            <th></th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-yeikar-secondary-light/5">
                          {movimientos.length === 0 ? (
                            <tr><td colSpan={6} className="p-4 text-center text-yeikar-neutral/40 italic">Sin movimientos.</td></tr>
                          ) : (
                            [...movimientos].sort((a, b) => a.fecha.localeCompare(b.fecha)).map((m) => (
                              <tr key={m.id} className={m.tipo === 'APERTURA' ? 'bg-yeikar-tertiary/20' : ''}>
                                <td className="p-2 font-mono">{m.fecha.slice(0, 10)}</td>
                                <td className="p-2">{m.metodo_caja?.nombre ?? '—'}</td>
                                <td className="p-2">
                                  <span className={`px-1.5 py-0.5 rounded-full text-[10px] font-bold ${
                                    m.tipo === 'ENTRADA' ? 'bg-green-50 text-green-700' : m.tipo === 'SALIDA' ? 'bg-red-50 text-red-600' : m.tipo === 'APERTURA' ? 'bg-blue-50 text-blue-700' : 'bg-amber-50 text-amber-700'
                                  }`}>{m.tipo}</span>
                                </td>
                                <td className="p-2 text-right font-mono">{m.moneda?.codigo ?? ''} {Math.round(m.monto).toLocaleString('es-CO')}</td>
                                <td className="p-2 text-right font-mono font-semibold">{fmtCop(m.monto_en_moneda_base)}</td>
                                <td className="p-2 text-right">
                                  <button onClick={() => eliminarMovimiento(m.id)} className="text-red-400 hover:text-red-600 text-xs font-bold">×</button>
                                </td>
                              </tr>
                            ))
                          )}
                        </tbody>
                      </table>
                    </div>

                    {/* Nuevo método */}
                    <div className="flex gap-2">
                      <input value={nuevoMetodo.nombre} onChange={(e) => setNuevoMetodo((p) => ({ ...p, nombre: e.target.value }))} placeholder="Nuevo método (ej: Mercantil)" className={inputCls} />
                      <input value={nuevoMetodo.codigo} onChange={(e) => setNuevoMetodo((p) => ({ ...p, codigo: e.target.value }))} placeholder="CÓDIGO" className={inputCls} style={{ maxWidth: '140px' }} />
                      <button onClick={agregarMetodo} className="bg-yeikar-tertiary text-yeikar-neutral font-bold text-xs px-3 py-2 rounded-lg hover:bg-yeikar-secondary hover:text-white transition-colors whitespace-nowrap">
                        + Método
                      </button>
                    </div>
                  </div>
                )}
              </div>

              {/* Devoluciones */}
              <div className="space-y-2">
                {panelBtn('devoluciones', 'Devoluciones de Ventas', 'Registra devoluciones por despacho o calidad')}
                {panelAbierto === 'devoluciones' && (
                  <div className="bg-white border border-yeikar-secondary-light/10 rounded-2xl p-5 shadow-sm space-y-4">
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
                      <SearchSelect
                        value={devForm.venta_id}
                        onChange={(v) => setDevForm((f) => ({ ...f, venta_id: Number(v) }))}
                        options={[
                          { value: 0, label: 'Venta...' },
                          ...ventas.map((v) => ({
                            value: v.id,
                            label: `#${v.id} — ${v.cliente?.nombre ?? 'Sin cliente'} (${v.fecha.slice(0, 10)})`,
                          })),
                        ]}
                        placeholder="Venta..."
                      />
                      <input type="date" value={devForm.fecha} onChange={(e) => setDevForm((f) => ({ ...f, fecha: e.target.value }))} className={inputCls} />
                      <input type="number" min="1" step="1" value={devForm.cantidad} onChange={(e) => setDevForm((f) => ({ ...f, cantidad: e.target.value }))} placeholder="Cantidad" className={inputCls} />
                      <input type="number" min="0" step="0.01" value={devForm.monto_devuelto} onChange={(e) => setDevForm((f) => ({ ...f, monto_devuelto: e.target.value }))} placeholder="Monto devuelto" className={inputCls} />
                      <SearchSelect
                        value={devForm.moneda_id}
                        onChange={(v) => setDevForm((f) => ({ ...f, moneda_id: Number(v) }))}
                        options={monedas.map((m) => ({ value: m.id, label: m.codigo }))}
                        placeholder="Moneda..."
                      />
                      <input type="number" min="0" step="0.01" value={devForm.tasa_cambio} onChange={(e) => setDevForm((f) => ({ ...f, tasa_cambio: e.target.value }))} placeholder="Tasa (COP/1)" className={inputCls} />
                      <input value={devForm.motivo} onChange={(e) => setDevForm((f) => ({ ...f, motivo: e.target.value }))} placeholder="Motivo" className={`${inputCls} col-span-2`} />
                      <button onClick={registrarDevolucion} disabled={guardando} className="bg-red-500 text-white font-bold text-sm rounded-lg hover:bg-red-600 transition-colors disabled:opacity-50 py-2 col-span-2">
                        {guardando ? '...' : '+ Registrar Devolución'}
                      </button>
                    </div>
                    <div className="overflow-x-auto max-h-56 overflow-y-auto">
                      <table className="w-full text-xs border-collapse">
                        <thead className="sticky top-0 bg-white">
                          <tr className="text-yeikar-secondary font-headline font-bold uppercase tracking-wider border-b border-yeikar-secondary-light/10">
                            <th className="p-2 text-left">Fecha</th>
                            <th className="p-2 text-left">Venta</th>
                            <th className="p-2 text-right">Cant.</th>
                            <th className="p-2 text-right">Monto</th>
                            <th className="p-2 text-right">COP</th>
                            <th className="p-2 text-left">Motivo</th>
                            <th></th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-yeikar-secondary-light/5">
                          {devoluciones.length === 0 ? (
                            <tr><td colSpan={7} className="p-4 text-center text-yeikar-neutral/40 italic">Sin devoluciones.</td></tr>
                          ) : (
                            devoluciones.map((d) => (
                              <tr key={d.id}>
                                <td className="p-2 font-mono">{d.fecha.slice(0, 10)}</td>
                                <td className="p-2">#{d.venta_id}</td>
                                <td className="p-2 text-right font-mono">{d.cantidad}</td>
                                <td className="p-2 text-right font-mono">{d.moneda?.codigo ?? ''} {Math.round(d.monto_devuelto).toLocaleString('es-CO')}</td>
                                <td className="p-2 text-right font-mono font-semibold text-red-500">−{fmtCop(d.monto_en_moneda_base ?? d.monto_devuelto)}</td>
                                <td className="p-2 text-yeikar-neutral/60 italic">{d.motivo ?? ''}</td>
                                <td className="p-2 text-right">
                                  <button onClick={() => eliminarDevolucion(d.id)} className="text-red-400 hover:text-red-600 text-xs font-bold">×</button>
                                </td>
                              </tr>
                            ))
                          )}
                        </tbody>
                      </table>
                    </div>
                  </div>
                )}
              </div>

              {/* Catálogo de líneas */}
              <div className="space-y-2">
                {panelBtn('conceptos', 'Catálogo de Líneas', 'Administra las líneas fijas del informe')}
                {panelAbierto === 'conceptos' && (
                  <div className="bg-white border border-yeikar-secondary-light/10 rounded-2xl p-5 shadow-sm space-y-3">
                    <div className="space-y-1.5">
                      {conceptos.map((c) => (
                        <div key={c.id} className="flex items-center justify-between border border-yeikar-secondary-light/5 rounded-xl px-4 py-2.5 bg-yeikar-tertiary/10">
                          <div>
                            <p className={`text-sm font-semibold ${c.activo ? 'text-yeikar-neutral' : 'text-yeikar-neutral/40 line-through'}`}>{c.nombre}</p>
                            <p className="text-[10px] font-mono text-yeikar-neutral/40 uppercase">{c.seccion} · orden {c.orden}</p>
                          </div>
                          <button onClick={() => eliminarConcepto(c.id)} className="text-red-400 hover:text-red-600 text-xs font-bold">×</button>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </div>
          </>
        )
      }
    </div>
  );
}

function Row({ label, valor, strong, negative, highlight, label2 }: { label: string; valor: number; strong?: boolean; negative?: boolean; highlight?: boolean; label2?: string }) {
  return (
    <div className={`flex justify-between items-baseline ${strong ? 'font-headline font-bold text-yeikar-neutral text-sm pt-1' : 'text-sm text-yeikar-neutral/75'}`}>
      <span>
        {label}
        {label2 && <span className="block text-[10px] text-yeikar-neutral/40 font-normal">{label2}</span>}
      </span>
      <span className={`font-mono ${strong ? 'font-bold text-yeikar-neutral' : 'font-medium'} ${highlight ? 'text-yeikar-primary text-base font-black' : negative ? 'text-red-500' : ''}`}>
        {fmtCop(valor)}
      </span>
    </div>
  );
}

function GastoGrupo({ titulo, lineas, total }: { titulo: string; lineas: { tipo_id: number; nombre: string; monto: number }[]; total: number }) {
  const [abierto, setAbierto] = useState(false);
  return (
    <div className="border border-yeikar-secondary-light/5 rounded-xl overflow-hidden print:border-gray-400 print:rounded-none">
      <div className="flex justify-between items-center px-3 py-2 print:bg-gray-200 print-color-adjust print:border-b print:border-gray-400">
        <span className="text-sm font-semibold text-yeikar-secondary print:text-black">{titulo}</span>
        <span className="flex items-center gap-2">
          <span className="font-mono font-bold text-sm text-yeikar-neutral/80 print:text-black">{fmtCop(total)}</span>
          <button
            onClick={() => setAbierto((a) => !a)}
            className={`text-yeikar-neutral/40 text-xs transition-transform print:hidden ${abierto ? 'rotate-90' : ''}`}
            aria-label={`${abierto ? 'Ocultar' : 'Mostrar'} gastos ${titulo}`}
          >
            ›
          </button>
        </span>
      </div>
      <div className={abierto ? 'px-3 pb-2 space-y-1 bg-yeikar-tertiary/5' : 'hidden print:block px-3 pb-2 space-y-1'}>
        {lineas.length === 0 ? (
          <p className="text-xs text-yeikar-neutral/40 italic py-1">Sin gastos registrados.</p>
        ) : (
          lineas.map((l) => (
            <div key={l.tipo_id} className="flex justify-between text-xs text-yeikar-neutral/70">
              <span>{l.nombre}</span>
              <span className="font-mono">{fmtCop(l.monto)}</span>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
