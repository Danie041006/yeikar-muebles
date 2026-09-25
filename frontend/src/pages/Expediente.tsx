import { useCallback, useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { FolderOpen, Loader2 } from 'lucide-react';
import { useDebouncedValue } from '../hooks/useDebouncedValue';
import { PageHeader, SearchInput, Spinner, EmptyState } from '../components/ui';
import BadgeEstado from '../components/BadgeEstado';
import ExpedienteFicha from '../components/Expediente/ExpedienteFicha';
import { historialService, ClienteResumen } from '../services/historialService';
import type { Expediente } from '../services/historialService';
import { cotizacionService } from '../services/cotizacionService';
import type { Quote } from '../services/cotizacionService';
import { pedidoService, Order } from '../services/pedidoService';
import { facturacionService, Factura } from '../services/facturacionService';
import { clienteService, Client } from '../services/clienteService';
import { envioService, Envio } from '../services/envioService';
import { formatCurrency } from '../utils/format';
import { fmtFechaVE } from '../utils/fechas';

type Tab = 'cotizaciones' | 'pedidos' | 'facturas' | 'clientes' | 'envios';

const TABS: { id: Tab; label: string }[] = [
  { id: 'cotizaciones', label: 'Libro de Cotizaciones' },
  { id: 'pedidos', label: 'Libro de Pedidos' },
  { id: 'facturas', label: 'Libro de Facturas' },
  { id: 'clientes', label: 'Libro de Clientes' },
  { id: 'envios', label: 'Libro de Guías de Despacho' },
];

const fmtD = (v?: string | null) => fmtFechaVE(v);

export default function Expediente() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [tab, setTab] = useState<Tab>((searchParams.get('tipo') as Tab) || 'cotizaciones');
  const [buscar, setBuscar] = useState('');
  const [loading, setLoading] = useState(true);
  const [loadingFicha, setLoadingFicha] = useState(false);

  // Listas por pestaña
  const [cotizaciones, setCotizaciones] = useState<Quote[]>([]);
  const [pedidos, setPedidos] = useState<Order[]>([]);
  const [facturas, setFacturas] = useState<Factura[]>([]);
  const [clientes, setClientes] = useState<Client[]>([]);
  const [envios, setEnvios] = useState<Envio[]>([]);

  // Ficha abierta
  const [ficha, setFicha] = useState<Expediente | null>(null);
  const [resumenCliente, setResumenCliente] = useState<ClienteResumen | null>(null);
  const [tituloFicha, setTituloFicha] = useState<string>('');

  const cargarTab = useCallback(async (q: string) => {
    setLoading(true);
    try {
      // Búsqueda server-side por pestaña: el catálogo no se baja completo al
      // cliente (clientes 1.204+ → antes solo llegaban los primeros 100).
      if (tab === 'cotizaciones') setCotizaciones(await cotizacionService.getAll(q || undefined, false));
      else if (tab === 'pedidos') setPedidos(await pedidoService.getAll(q || undefined, false));
      else if (tab === 'facturas') setFacturas((await facturacionService.getAll()).items);
      else if (tab === 'clientes') setClientes(await clienteService.getAll(q || undefined));
      else if (tab === 'envios') setEnvios(await envioService.getAll(q || undefined));
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
    const tipo = searchParams.get('tipo') as Tab | null;
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
    setResumenCliente(null);
    try {
      if (t === 'cotizaciones') {
        const f = await historialService.fichaCotizacion(id);
        setFicha(f);
        setTituloFicha(`Cotización #${id}`);
      } else if (t === 'pedidos') {
        const f = await historialService.fichaPedido(id);
        setFicha(f);
        setTituloFicha(`Pedido #${id}`);
      } else if (t === 'facturas') {
        const f = await historialService.fichaFactura(id);
        setFicha(f);
        setTituloFicha(`Factura #${id}`);
      } else if (t === 'envios') {
        const f = await historialService.fichaEnvio(id);
        setFicha(f);
        setTituloFicha(`Despacho #${id}`);
      } else if (t === 'clientes') {
        const r = await historialService.fichaCliente(id);
        setResumenCliente(r);
        setFicha(null);
        setTituloFicha(`Cliente: ${r.cliente.nombre}`);
      }
    } catch (e) {
      console.error('Error abriendo ficha:', e);
      setFicha(null);
    } finally {
      setLoadingFicha(false);
    }
  };

  const listaFiltrada: (Quote | Order | Factura | Client | Envio)[] = (() => {
    // Facturas: el endpoint no soporta búsqueda, se filtra por id en el cliente.
    if (tab === 'facturas') {
      const q = buscar.toLowerCase();
      return facturas.filter((f) => !q || String(f.id).includes(q));
    }
    // Cotizaciones, pedidos, clientes y envíos ya vienen filtrados por el
    // servidor (búsqueda con debounce en cargarTab).
    if (tab === 'cotizaciones') return cotizaciones;
    if (tab === 'pedidos') return pedidos;
    if (tab === 'clientes') return clientes;
    return envios;
  })();

  return (
    <div className="space-y-6">
      <PageHeader
        title="Libros de Control y Registro"
        subtitle="Consulta independiente por libro: Cotizaciones, Pedidos, Clientes, Facturas  y Guías de Despacho."
        icon={<FolderOpen className="h-6 w-6 text-yeikar-primary" />}
      />

      {/* Tabs */}
      <div className="flex flex-wrap gap-1 bg-yeikar-secondary/5 border border-yeikar-secondary-light/10 rounded-xl p-1">
        {TABS.map((t) => {
          const count =
            t.id === 'cotizaciones' ? cotizaciones.length
            : t.id === 'pedidos' ? pedidos.length
            : t.id === 'facturas' ? facturas.length
            : t.id === 'clientes' ? clientes.length
            : envios.length;
          return (
            <button
              key={t.id}
              onClick={() => { setTab(t.id); setFicha(null); setResumenCliente(null); }}
              className={`px-4 py-2 rounded-lg text-sm font-bold font-headline transition-all ${
                tab === t.id ? 'bg-yeikar-primary text-yeikar-neutral shadow-gold' : 'text-yeikar-secondary/70 hover:bg-yeikar-tertiary/40'
              }`}
            >
              {t.label}
              <span className={`ml-1.5 font-mono text-[10px] ${tab === t.id ? 'text-yeikar-neutral/70' : 'text-yeikar-neutral/40'}`}>
                {loading ? '…' : count}
              </span>
            </button>
          );
        })}
      </div>

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
                {tab === 'clientes' && (listaFiltrada as Client[]).map((c) => (
                  <li key={c.id}>
                    <button onClick={() => abrirFicha('clientes', c.id)} className="w-full text-left px-4 py-3 hover:bg-yeikar-tertiary/30 transition-colors">
                      <div className="flex items-center justify-between gap-2">
                        <span className="font-headline font-bold text-sm text-yeikar-secondary">{c.nombre}</span>
                        <span className="font-mono text-[10px] text-yeikar-neutral/45">#{c.id}</span>
                      </div>
                      <p className="text-[11px] font-mono text-yeikar-neutral/55 mt-1">
                        {[c.cedula && `C.I. ${c.cedula}`, c.telefono && `Tel: ${c.telefono}`, c.ciudad].filter(Boolean).join(' · ') || '—'}
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
          ) : resumenCliente ? (
            <ResumenCliente resumen={resumenCliente} onAbrirPedido={(id) => abrirFicha('pedidos', id)} />
          ) : (
            <div className="bg-white border border-dashed border-yeikar-secondary-light/15 rounded-3xl p-14 text-center text-yeikar-neutral/40">
              <FolderOpen className="w-12 h-12 mx-auto text-yeikar-neutral/20 mb-3" />
              <p className="font-semibold text-sm">Selecciona un registro del libro a la izquierda</p>
              <p className="text-xs mt-1">Verás únicamente su documento o ficha correspondiente.</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────
// Resumen por cliente: todas sus operaciones
// ─────────────────────────────────────────────────────────────────────────
function ResumenCliente({ resumen, onAbrirPedido }: { resumen: ClienteResumen; onAbrirPedido: (id: number) => void }) {
  const c = resumen.cliente;
  const r = resumen.resumen;
  return (
    <div className="space-y-4">
      <div className="bg-gradient-to-r from-yeikar-secondary to-yeikar-secondary-light rounded-2xl p-5 text-white shadow-sm">
        <p className="font-mono text-[10px] uppercase tracking-widest text-white/50">Historial del cliente</p>
        <h2 className="font-headline font-black text-xl mt-0.5">{c.nombre}</h2>
        <div className="flex flex-wrap gap-x-4 gap-y-1 mt-2 text-xs text-white/70 font-mono">
          {c.cedula && <span>C.I.: {c.cedula}</span>}
          {c.telefono && <span>Tel: {c.telefono}</span>}
          {c.ciudad && <span>Ciudad: {c.ciudad}</span>}
          {c.fecha_registro && <span>Cliente desde {fmtD(c.fecha_registro)}</span>}
        </div>
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-5 gap-2">
        {([
          ['Cotizaciones', r.cotizaciones.length],
          ['Pedidos', r.pedidos.length],
          ['Ventas', r.ventas.length],
          ['Facturas', r.facturas.length],
          ['Despachos', r.envios.length],
        ] as const).map(([label, n]) => (
          <div key={label} className="bg-white border border-yeikar-secondary-light/10 rounded-xl p-3 text-center">
            <p className="font-headline font-black text-2xl text-yeikar-primary">{n}</p>
            <p className="text-[10px] font-bold uppercase tracking-wider text-yeikar-neutral/50">{label}</p>
          </div>
        ))}
      </div>

      {r.pedidos.length > 0 && (
        <div className="bg-white border border-yeikar-secondary-light/10 rounded-2xl shadow-sm overflow-hidden">
          <div className="px-5 py-3 bg-yeikar-secondary/5 border-b border-yeikar-secondary-light/10">
            <h3 className="font-headline font-black text-sm text-yeikar-secondary">Pedidos del cliente</h3>
          </div>
          <ul className="divide-y divide-yeikar-secondary-light/5">
            {r.pedidos.map((p) => (
              <li key={p.id}>
                <button onClick={() => onAbrirPedido(p.id)} className="w-full flex items-center justify-between gap-2 px-5 py-3 hover:bg-yeikar-tertiary/30 transition-colors text-left">
                  <span className="font-headline font-bold text-sm text-yeikar-secondary">Pedido #{p.id}</span>
                  <span className="flex items-center gap-2">
                    <span className="font-mono text-[11px] text-yeikar-neutral/55">{fmtD(p.fecha)}</span>
                    <BadgeEstado dominio="pedido" estado={p.estado} />
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
      {r.pedidos.length === 0 && (
        <p className="text-xs text-yeikar-neutral/50 italic">Este cliente aún no tiene pedidos.</p>
      )}
    </div>
  );
}