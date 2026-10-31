import { useCallback, useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { FolderOpen, Loader2 } from 'lucide-react';
import { useToast } from '../context/ToastContext';
import { useDebouncedValue } from '../hooks/useDebouncedValue';
import { PageHeader, SearchInput, Spinner, EmptyState } from '../components/ui';
import BadgeEstado from '../components/BadgeEstado';
import ExpedienteFicha from '../components/Expediente/ExpedienteFicha';
import LibroEntradasSalidas from '../components/Expediente/LibroEntradasSalidas';
import { historialService } from '../services/historialService';
import type { Expediente } from '../services/historialService';
import { cotizacionService } from '../services/cotizacionService';
import type { Quote } from '../services/cotizacionService';
import { pedidoService, Order } from '../services/pedidoService';
import { facturacionService, Factura } from '../services/facturacionService';
import { envioService, Envio } from '../services/envioService';
import { formatCurrency, extractErrorMessage } from '../utils/format';
import { fmtFechaVE } from '../utils/fechas';

type Tab = 'cotizaciones' | 'pedidos' | 'facturas' | 'envios' | 'entradas-salidas';

// Los enlaces desde otras secciones llegan con el tipo en singular
// (?tipo=pedido&id=5): se normaliza aquí para que abran la pestaña y la ficha.
const TIPO_ALIAS: Record<string, Tab> = {
  cotizacion: 'cotizaciones', cotizaciones: 'cotizaciones',
  pedido: 'pedidos', pedidos: 'pedidos',
  factura: 'facturas', facturas: 'facturas',
  envio: 'envios', envios: 'envios',
  'entradas-salidas': 'entradas-salidas',
};

const TABS: { id: Tab; label: string }[] = [
  { id: 'cotizaciones', label: 'Libro de Cotizaciones' },
  { id: 'pedidos', label: 'Libro de Pedidos' },
  { id: 'facturas', label: 'Libro de Facturas' },
  { id: 'envios', label: 'Libro de Guías de Despacho' },
  { id: 'entradas-salidas', label: 'Libro de Entradas y Salidas' },
];

const fmtD = (v?: string | null) => fmtFechaVE(v);

export default function Expediente() {
  const [searchParams, setSearchParams] = useSearchParams();
  const toast = useToast();
  const [tab, setTab] = useState<Tab>(TIPO_ALIAS[searchParams.get('tipo') ?? ''] ?? 'cotizaciones');
  const [buscar, setBuscar] = useState('');
  const [loading, setLoading] = useState(true);
  const [loadingFicha, setLoadingFicha] = useState(false);

  // Listas por pestaña
  const [cotizaciones, setCotizaciones] = useState<Quote[]>([]);
  const [pedidos, setPedidos] = useState<Order[]>([]);
  const [facturas, setFacturas] = useState<Factura[]>([]);
  const [envios, setEnvios] = useState<Envio[]>([]);

  // Ficha abierta
  const [ficha, setFicha] = useState<Expediente | null>(null);

  const cargarTab = useCallback(async (q: string) => {
    setLoading(true);
    try {
      // Búsqueda server-side por pestaña: el catálogo no se baja completo al
      // cliente (con miles de registros antes solo llegaban los primeros 100).
      if (tab === 'cotizaciones') setCotizaciones(await cotizacionService.getAll(q || undefined, false));
      else if (tab === 'pedidos') setPedidos(await pedidoService.getAll(q || undefined, false));
      else if (tab === 'facturas') setFacturas((await facturacionService.getAll()).items);
      else if (tab === 'envios') setEnvios((await envioService.getAll({ buscar: q || undefined })).items);
    } catch (e) {
      console.error('Error cargando expedientes:', e);
    } finally {
      setLoading(false);
    }
  }, [tab]);

  const buscarDeb = useDebouncedValue(buscar, 400);

  useEffect(() => {
    cargarTab(buscarDeb);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tab, buscarDeb, cargarTab]);

  // Apertura directa desde otras secciones: /historial?tipo=pedido&id=5
  useEffect(() => {
    const tipo = TIPO_ALIAS[searchParams.get('tipo') ?? ''];
    const id = searchParams.get('id');
    if (tipo && id) {
      setTab(tipo);
      abrirFicha(tipo, Number(id));
      setSearchParams({}, { replace: true });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const abrirFicha = async (t: Tab, id: number) => {
    setLoadingFicha(true);
    try {
      if (t === 'cotizaciones') {
        const f = await historialService.fichaCotizacion(id);
        setFicha(f);
      } else if (t === 'pedidos') {
        const f = await historialService.fichaPedido(id);
        setFicha(f);
      } else if (t === 'facturas') {
        const f = await historialService.fichaFactura(id);
        setFicha(f);
      } else if (t === 'envios') {
        const f = await historialService.fichaEnvio(id);
        setFicha(f);
      }
    } catch (e) {
      console.error('Error abriendo ficha:', e);
      setFicha(null);
      toast.error(extractErrorMessage(e, 'No se pudo abrir la ficha del registro.'));
    } finally {
      setLoadingFicha(false);
    }
  };

  const listaFiltrada: (Quote | Order | Factura | Envio)[] = (() => {
    // Facturas: el endpoint no soporta búsqueda, se filtra por id en el cliente.
    if (tab === 'facturas') {
      const q = buscar.toLowerCase();
      return facturas.filter((f) => !q || String(f.id).includes(q));
    }
    // Cotizaciones, pedidos y envíos ya vienen filtrados por el servidor
    // (búsqueda con debounce en cargarTab).
    if (tab === 'cotizaciones') return cotizaciones;
    if (tab === 'pedidos') return pedidos;
    return envios;
  })();

  return (
    <div className="space-y-6">
      <PageHeader
        title="Libros de Control y Registro"
        subtitle="Consulta independiente por libro: Cotizaciones, Pedidos, Facturas, Guías de Despacho y Entradas y Salidas."
        icon={<FolderOpen className="h-6 w-6 text-yeikar-primary" />}
      />

      {/* Tabs */}
      <div className="flex flex-wrap gap-1 bg-yeikar-secondary/5 border border-yeikar-secondary-light/10 rounded-xl p-1">
        {TABS.map((t) => {
          const count =
            t.id === 'cotizaciones' ? cotizaciones.length
            : t.id === 'pedidos' ? pedidos.length
            : t.id === 'facturas' ? facturas.length
            : t.id === 'entradas-salidas' ? null
            : envios.length;
          return (
            <button
              key={t.id}
              onClick={() => { setTab(t.id); setFicha(null); }}
              className={`px-4 py-2 rounded-lg text-sm font-bold font-headline transition-all ${
                tab === t.id ? 'bg-yeikar-primary text-yeikar-neutral shadow-gold' : 'text-yeikar-secondary/70 hover:bg-yeikar-tertiary/40'
              }`}
            >
              {t.label}
              {typeof count === 'number' && (
                <span className={`ml-1.5 font-mono text-[10px] ${tab === t.id ? 'text-yeikar-neutral/70' : 'text-yeikar-neutral/40'}`}>
                  {loading ? '…' : count}
                </span>
              )}
            </button>
          );
        })}
      </div>

      {tab === 'entradas-salidas' && <LibroEntradasSalidas />}

      {tab !== 'entradas-salidas' && (
      <div className="flex flex-col xl:flex-row gap-6">
        {/* ── Listado ── */}
        <div className="w-full xl:w-[360px] shrink-0 space-y-3">
          <SearchInput value={buscar} onChange={(e) => setBuscar(e.target.value)} placeholder="Buscar en esta pestaña..." />

          <div className="bg-white border border-yeikar-secondary-light/10 rounded-2xl shadow-sm overflow-hidden max-h-[75vh] overflow-y-auto">
            {loading ? (
              <div className="flex justify-center py-16"><Spinner /></div>
            ) : listaFiltrada.length === 0 ? (
              <EmptyState title="Sin registros" description="No hay documentos en esta pestaña." />
            ) : (
              <ul className="divide-y divide-yeikar-secondary-light/5">
                {tab === 'cotizaciones' && (listaFiltrada as Quote[]).map((c) => (
                  <li key={c.id}>
                    <button onClick={() => abrirFicha('cotizaciones', c.id)} className="w-full text-left px-4 py-3 hover:bg-yeikar-tertiary/30 transition-colors">
                      <div className="flex items-center justify-between gap-2">
                        <span className="font-headline font-bold text-sm text-yeikar-secondary">#{c.id} · {c.cliente?.nombre || 'Cliente'}</span>
                        <BadgeEstado dominio="cotizacion" estado={c.estado} />
                      </div>
                      <p className="text-[11px] font-mono text-yeikar-neutral/55 mt-1">
                        {fmtD(c.fecha)} · {formatCurrency(c.total_estimado, c.moneda?.codigo)}
                      </p>
                    </button>
                  </li>
                ))}
                {tab === 'pedidos' && (listaFiltrada as Order[]).map((p) => (
                  <li key={p.id}>
                    <button onClick={() => abrirFicha('pedidos', p.id)} className="w-full text-left px-4 py-3 hover:bg-yeikar-tertiary/30 transition-colors">
                      <div className="flex items-center justify-between gap-2">
                        <span className="font-headline font-bold text-sm text-yeikar-secondary">#{p.id} · {p.cliente?.nombre || 'Cliente'}</span>
                        <BadgeEstado dominio="pedido" estado={p.estado} />
                      </div>
                      <p className="text-[11px] font-mono text-yeikar-neutral/55 mt-1">{fmtD(p.fecha)} · {p.detalles?.length ?? 0} mueble(s)</p>
                    </button>
                  </li>
                ))}
                {tab === 'facturas' && (listaFiltrada as Factura[]).map((f) => (
                  <li key={f.id}>
                    <button onClick={() => abrirFicha('facturas', f.id)} className="w-full text-left px-4 py-3 hover:bg-yeikar-tertiary/30 transition-colors">
                      <div className="flex items-center justify-between gap-2">
                        <span className="font-headline font-bold text-sm text-yeikar-secondary">#{f.id}</span>
                        <BadgeEstado dominio="factura" estado={f.estado} />
                      </div>
                      <p className="text-[11px] font-mono text-yeikar-neutral/55 mt-1">
                        {fmtD(f.fecha_emision)} · {Number(f.total_bs || 0).toLocaleString('es-VE')} Bs
                      </p>
                    </button>
                  </li>
                ))}
                {tab === 'envios' && (listaFiltrada as Envio[]).map((e) => (
                  <li key={e.id}>
                    <button onClick={() => abrirFicha('envios', e.id)} className="w-full text-left px-4 py-3 hover:bg-yeikar-tertiary/30 transition-colors">
                      <div className="flex items-center justify-between gap-2">
                        <span className="font-headline font-bold text-sm text-yeikar-secondary">
                          #{e.id}{e.guia_despacho ? ` · ${e.guia_despacho}` : ''}
                        </span>
                        <BadgeEstado dominio="envio" estado={e.estado} />
                      </div>
                      <p className="text-[11px] font-mono text-yeikar-neutral/55 mt-1">
                        Pedido #{e.pedido_id} · {e.pedido?.cliente?.nombre || ''} · {e.empleado?.nombre || 'sin chofer'}
                      </p>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>

        {/* ── Ficha ── */}
        <div className="flex-1 min-w-0">
          {loadingFicha ? (
            <div className="flex flex-col items-center justify-center py-24 text-yeikar-neutral/50 gap-3">
              <Loader2 className="h-8 w-8 animate-spin text-yeikar-primary" />
              <p className="text-sm font-mono">Cargando documento del libro...</p>
            </div>
          ) : ficha ? (
            <ExpedienteFicha ficha={ficha} modoLibro={tab} />
          ) : (
            <div className="bg-white border border-dashed border-yeikar-secondary-light/15 rounded-3xl p-14 text-center text-yeikar-neutral/40">
              <FolderOpen className="w-12 h-12 mx-auto text-yeikar-neutral/20 mb-3" />
              <p className="font-semibold text-sm">Selecciona un registro del libro a la izquierda</p>
              <p className="text-xs mt-1">Verás únicamente su documento o ficha correspondiente.</p>
            </div>
          )}
        </div>
      </div>
      )}
    </div>
  );
}
