import { useEffect, useRef, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { Trash2, Truck } from 'lucide-react';
import {
  Button,
  Card,
  Badge,
  EmptyState,
  Modal,
  PageHeader,
  SearchInput,
  Spinner,
  ConfirmDialog,
  ResponsiveDataTable,
  type DataColumn,
} from '../components/ui';
import { useToast } from '../context/ToastContext';
import { useAuth } from '../context/AuthContext';
import { pedidoService, Order, RentabilidadPedido } from '../services/pedidoService';
import { envioService, Envio } from '../services/envioService';
import EntregaParcialModal from '../components/Pedidos/EntregaParcialModal';
import { formatCurrency } from '../utils/format';

export default function Pedidos() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const toast = useToast();
  const { hasModulo, esAdmin } = useAuth();
  const puedeEntregar = esAdmin && hasModulo('envios');
  const [orders, setOrders] = useState<Order[]>([]);
  const [search, setSearch] = useState('');
  const [soloMesActual, setSoloMesActual] = useState(true);
  const [selectedMonth, setSelectedMonth] = useState(new Date().getMonth() + 1);
  const [selectedYear, setSelectedYear] = useState(new Date().getFullYear());
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const [selectedOrder, setSelectedOrder] = useState<Order | null>(null);
  const [rentabilidad, setRentabilidad] = useState<RentabilidadPedido | null>(null);
  const [rentabilidadLoading, setRentabilidadLoading] = useState(false);

  useEffect(() => {
    if (!selectedOrder) { setRentabilidad(null); return; }
    let active = true;
    setRentabilidadLoading(true);
    pedidoService.getRentabilidad(selectedOrder.id)
      .then((r) => { if (active) setRentabilidad(r); })
      .catch(() => { if (active) setRentabilidad(null); })
      .finally(() => { if (active) setRentabilidadLoading(false); });
    return () => { active = false; };
  }, [selectedOrder]);

  // Deep-link ?pedido=N (desde una cotización convertida): carga la lista y
  // abre el detalle de ese pedido al llegar. Si no está en el listado visible
  // (p. ej. otro mes), lo busca directo por id.
  const pedidoParam = searchParams.get('pedido');
  const pedidoDeepLinkDone = useRef(false);
  useEffect(() => {
    if (!pedidoParam || pedidoDeepLinkDone.current || !orders.length) return;
    pedidoDeepLinkDone.current = true;
    const encontrado = orders.find((o) => String(o.id) === pedidoParam);
    if (encontrado) {
      setSelectedOrder(encontrado);
      return;
    }
    pedidoService.getById(Number(pedidoParam))
      .then((o) => setSelectedOrder(o))
      .catch(() => toast.error(`No se encontró el pedido #${pedidoParam}.`));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [orders, pedidoParam]);

  // Confirm Delete
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [pendingDeleteId, setPendingDeleteId] = useState<number | null>(null);

  const fetchOrders = async (searchTerm?: string) => {
    setLoading(true);
    setError('');
    try {
      const data = await pedidoService.getAll(
        searchTerm,
        soloMesActual,
        soloMesActual ? undefined : selectedMonth,
        soloMesActual ? undefined : selectedYear
      );
      setOrders(data);
    } catch (err: any) {
      console.error(err);
      setError('Error al cargar la lista de pedidos de producción.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    const timer = setTimeout(() => {
      fetchOrders(search);
    }, 300);
    return () => clearTimeout(timer);
  }, [search, soloMesActual, selectedMonth, selectedYear]);

  const [statusUpdatingId, setStatusUpdatingId] = useState<number | null>(null);
  const [entregaPedido, setEntregaPedido] = useState<Order | null>(null);
  const [entregas, setEntregas] = useState<Envio[]>([]);
  const [entregasLoading, setEntregasLoading] = useState(false);

  useEffect(() => {
    if (!selectedOrder || !puedeEntregar) {
      setEntregas([]);
      return;
    }
    let activo = true;
    setEntregasLoading(true);
    envioService.getAll({ pedido_id: selectedOrder.id, limite: 200 })
      .then((res) => { if (activo) setEntregas(res.items); })
      .catch(() => { if (activo) setEntregas([]); })
      .finally(() => { if (activo) setEntregasLoading(false); });
    return () => { activo = false; };
  }, [selectedOrder, puedeEntregar]);

  const handleUpdateStatus = async (orderId: number, currentObs: string | undefined, newStatus: string) => {
    if (statusUpdatingId !== null) return; // evita PUTs concurrentes del estado
    setStatusUpdatingId(orderId);
    try {
      console.log('Actualizando estado del pedido:', { orderId, estado: newStatus });
      await pedidoService.update(orderId, {
        estado: newStatus,
        observaciones: currentObs,
      });
      fetchOrders(search);
      if (selectedOrder && selectedOrder.id === orderId) {
        // Refresh details modal cache
        const updated = await pedidoService.getById(orderId);
        setSelectedOrder(updated);
      }
    } catch (err: any) {
      console.error(err);
      toast.error(err.response?.data?.detail || 'Error al actualizar el estado del pedido.');
    } finally {
      setStatusUpdatingId(null);
    }
  };

  const handleOpenDeleteConfirm = (id: number) => {
    setPendingDeleteId(id);
    setConfirmOpen(true);
  };

  const handleDelete = async () => {
    if (pendingDeleteId === null) return;
    try {
      await pedidoService.delete(pendingDeleteId);
      fetchOrders(search);
    } catch (err) {
      console.error(err);
      toast.error('Error al eliminar el pedido.');
    }
  };

  // Misma matriz de transiciones que el backend (app/core/state_machine.py):
  // el select solo ofrece los saltos válidos del flujo de negocio.
  const TRANSICIONES_PEDIDO: Record<string, string[]> = {
    COTIZADO: ['APROBADO', 'CANCELADO'],
    APROBADO: ['PRODUCCION', 'TERMINADO', 'CANCELADO'],
    PRODUCCION: ['PAUSADO', 'TERMINADO', 'CANCELADO'],
    PAUSADO: ['PRODUCCION', 'CANCELADO'],
    TERMINADO: ['ENTREGADO'],
    ENTREGADO: [],
    CANCELADO: [],
  };
  const ESTADO_LABEL: Record<string, string> = {
    COTIZADO: 'Cotizado',
    APROBADO: 'Aprobado',
    PRODUCCION: 'En producción',
    PAUSADO: 'Pausado',
    TERMINADO: 'Terminado',
    ENTREGADO: 'Entregado',
    CANCELADO: 'Cancelado',
  };

  // Un pedido "sin producción" no tiene líneas a fabricar/reparar (solo
  // reventa, insumos, servicios o piezas de exhibición): no pasa por PRODUCCION.
  const esProducible = (tipo?: string) => (tipo || 'FABRICADO') === 'FABRICADO' || (tipo || 'FABRICADO') === 'REPARACION';
  const tieneFabricables = (order: Order) =>
    (order.detalles ?? []).some((d) => esProducible(d.tipo_item));

  const opcionesEstado = (estado: string, order?: Order) => {
    const sinProduccion = order ? !tieneFabricables(order) : false;
    const actual = { value: estado, label: ESTADO_LABEL[estado] ?? estado };
    let siguientes = (TRANSICIONES_PEDIDO[estado] ?? []).map((v) => ({
      value: v,
      label: ESTADO_LABEL[v] ?? v,
    }));
    if (sinProduccion && estado === 'APROBADO') {
      // Atajo sin producción: oculta PRODUCCION/PAUSADO (no aplican) y ofrece
      // "Terminado" con etiqueta clara (el despacho se crea solo).
      siguientes = siguientes.filter((v) => !['PRODUCCION', 'PAUSADO'].includes(v.value));
      siguientes = siguientes.map((v) =>
        v.value === 'TERMINADO' ? { ...v, label: 'Terminado (listo para despacho)' } : v,
      );
    }
    // ENTREGADO no se elige a mano: se cierra cuando la última entrega sale.
    if (order?.entrega_resumen && order.entrega_resumen.pendiente > 0) {
      siguientes = siguientes.filter((v) => v.value !== 'ENTREGADO');
    }
    // Con entregas físicas ya hechas, cancelar dejaría mercancía sin documento.
    if (order?.entrega_resumen && order.entrega_resumen.entregado > 0) {
      siguientes = siguientes.filter((v) => v.value !== 'CANCELADO');
    }
    return [actual, ...siguientes];
  };

  const estadoSelectClass = (estado: string) => {
    if (estado === 'APROBADO' || estado === 'COTIZADO') {
      return 'bg-blue-50 text-blue-700 border-blue-200/60';
    }
    if (estado === 'PRODUCCION') {
      return 'bg-amber-50 text-amber-700 border-amber-200/60';
    }
    if (estado === 'TERMINADO') {
      return 'bg-green-50 text-green-700 border-green-200/60';
    }
    if (estado === 'ENTREGADO') {
      return 'bg-yeikar-secondary-light/10 text-yeikar-secondary border-yeikar-secondary-light/10';
    }
    return 'bg-red-50 text-red-700 border-red-200/60';
  };

  const estadoTone = (estado: string) => {
    if (estado === 'APROBADO' || estado === 'COTIZADO') return 'blue' as const;
    if (estado === 'PRODUCCION') return 'amber' as const;
    if (estado === 'TERMINADO') return 'green' as const;
    if (estado === 'ENTREGADO') return 'neutral' as const;
    return 'red' as const;
  };

  const estadoLabel = (estado: string) => {
    switch (estado) {
      case 'COTIZADO':
      case 'APROBADO':
        return 'Aprobado';
      case 'PRODUCCION':
        return 'En producción';
      case 'TERMINADO':
        return 'Terminado';
      case 'ENTREGADO':
        return 'Entregado';
      case 'CANCELADO':
        return 'Cancelado';
      default:
        return estado;
    }
  };

  const EstadoSelect = ({ order }: { order: Order }) => {
    const sinProduccion = !tieneFabricables(order);
    return (
      <div className="flex items-center gap-1.5">
        <select
          value={order.estado}
          disabled={statusUpdatingId !== null || (TRANSICIONES_PEDIDO[order.estado] ?? []).length === 0}
          onChange={(e) => handleUpdateStatus(order.id, order.observaciones, e.target.value)}
          className={`px-2.5 py-1.5 rounded-full font-bold text-xs font-headline border focus:outline-none focus:ring-2 focus:ring-yeikar-primary/30 disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer ${estadoSelectClass(order.estado)}`}
          aria-label={`Cambiar estado del pedido #${order.id}`}
        >
          {opcionesEstado(order.estado, order).map((est) => (
            <option key={est.value} value={est.value}>{est.label}</option>
          ))}
        </select>
        {sinProduccion && !['ENTREGADO', 'CANCELADO'].includes(order.estado) && (
          <span
            title="No requiere producción: solo reventa, insumos o piezas de exhibición"
            className="text-[9px] font-bold uppercase px-1.5 py-0.5 rounded bg-yeikar-primary/10 text-yeikar-primary-dark border border-yeikar-primary/20 whitespace-nowrap"
          >
            Sin producción
          </span>
        )}
      </div>
    );
  };

  const renderActions = (order: Order) => (
    <>
      <button
        onClick={() => setSelectedOrder(order)}
        className="btn px-3 py-2 rounded-lg text-xs bg-yeikar-secondary text-yeikar-tertiary hover:bg-yeikar-secondary-light"
      >
        Ver detalles
      </button>
      {puedeEntregar && order.entrega_resumen && order.entrega_resumen.pendiente > 0
        && ['APROBADO', 'PRODUCCION', 'PAUSADO', 'TERMINADO'].includes(order.estado) && (
        <button
          onClick={() => setEntregaPedido(order)}
          className="btn px-3 py-2 rounded-lg text-xs bg-green-600 text-white hover:bg-green-700 flex items-center gap-1"
          title="Registrar una entrega parcial de lo que ya está listo"
        >
          <Truck className="h-4 w-4" />
          <span>Entregar</span>
        </button>
      )}
      {['APROBADO', 'PRODUCCION', 'TERMINADO', 'ENTREGADO'].includes(order.estado) && (
        <button
          onClick={() => navigate('/ventas')}
          className="btn px-3 py-2 rounded-lg text-xs bg-yeikar-primary text-yeikar-neutral hover:bg-yeikar-primary-light flex items-center gap-1"
          title="Ir a Facturas y Cobros"
        >
          <span>Ver los cobros de este pedido</span>
        </button>
      )}
      <button
        onClick={() => handleOpenDeleteConfirm(order.id)}
        className="p-2 text-red-600 hover:text-red-800 transition-colors"
        title="Eliminar"
        aria-label="Eliminar pedido"
      >
        <Trash2 className="h-5 w-5" />
      </button>
    </>
  );

  const columns: DataColumn<Order>[] = [
    {
      key: 'id',
      header: 'Pedido ID',
      render: (o) => <span className="font-mono font-bold text-yeikar-secondary">#{o.id}</span>,
      mobilePrimary: true,
    },
    {
      key: 'cliente',
      header: 'Cliente',
      render: (o) => (
        <span className="font-bold text-yeikar-secondary font-headline">{o.cliente?.nombre || `Cliente ID: ${o.cliente_id}`}</span>
      ),
      mobileSecondary: true,
    },
    {
      key: 'fecha',
      header: 'Fecha Creación',
      render: (o) => <span className="font-mono text-xs text-yeikar-neutral/50">{o.fecha}</span>,
      mobileLabel: 'Creado',
    },
    {
      key: 'entrega',
      header: 'Entrega Estimada',
      render: (o) => <span className="font-mono text-xs text-yeikar-neutral/50">{o.fecha_entrega_estimada || 'Sin definir'}</span>,
      mobileLabel: 'Entrega',
    },
    {
      key: 'estado',
      header: 'Estado',
      render: (o) => <EstadoSelect order={o} />,
      mobileHidden: true,
    },
    {
      key: 'entregas',
      header: 'Entregas',
      render: (o) => {
        const resumen = o.entrega_resumen;
        if (!resumen || resumen.total <= 0) {
          return <span className="text-[11px] text-yeikar-neutral/35">—</span>;
        }
        const porcentaje = Math.min(100, Math.round((resumen.entregado / resumen.total) * 100));
        const tono = resumen.estado === 'COMPLETO'
          ? 'bg-green-100 text-green-700 border-green-200'
          : resumen.estado === 'PARCIAL'
            ? 'bg-amber-100 text-amber-800 border-amber-200'
            : 'bg-stone-100 text-stone-600 border-stone-200';
        return (
          <div className="space-y-1 min-w-[96px]">
            <span className={`inline-flex rounded-full border px-2 py-0.5 text-[10px] font-black ${tono}`}>
              {resumen.entregado} / {resumen.total}
            </span>
            <div className="h-1.5 w-24 overflow-hidden rounded-full bg-yeikar-secondary-light/15">
              <div
                className="h-full rounded-full bg-yeikar-primary transition-all"
                style={{ width: `${porcentaje}%` }}
              />
            </div>
          </div>
        );
      },
      mobileLabel: 'Entregas',
    },
  ];

  // Moneda ORIGINAL del pedido (la de su cotización). Los costos se guardan
  // en COP, pero el margen se muestra en esta moneda con la tasa congelada.
  const monedaPedido = selectedOrder?.cotizacion?.moneda?.codigo
    ?? rentabilidad?.moneda_codigo
    ?? 'COP';
  const esMonedaBase = monedaPedido === 'COP';
  const fmtPedido = (valor: number) => `${formatCurrency(valor, monedaPedido)} ${monedaPedido}`;

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Órdenes de producción"
        title="Pedidos"
        subtitle={
          <span>
            {orders.length} pedido{orders.length !== 1 && 's'} de producción
          </span>
        }
      />

      {/* Search and filter bar */}
      <div className="flex flex-col md:flex-row items-center justify-between gap-4">
        <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-3 w-full md:w-auto flex-1">
          <SearchInput
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Buscar pedidos por cliente o estado..."
            className="w-full sm:w-72"
          />

          <div className="flex items-center gap-2 bg-yeikar-tertiary/20 p-1.5 rounded-lg border border-yeikar-secondary/10 text-xs">
            <label className="flex items-center gap-1.5 cursor-pointer font-headline font-bold text-yeikar-secondary">
              <input
                type="checkbox"
                checked={!soloMesActual}
                onChange={(e) => setSoloMesActual(!e.target.checked)}
                className="rounded border-yeikar-secondary-light/30 text-yeikar-primary focus:ring-yeikar-primary h-4 w-4"
              />
              Historial Completo
            </label>

            {!soloMesActual && (
              <div className="flex items-center gap-1.5 animate-fade-in">
                <span className="text-yeikar-neutral/40">|</span>
                <select
                  value={selectedMonth}
                  onChange={(e) => setSelectedMonth(Number(e.target.value))}
                  className="bg-white border border-yeikar-secondary-light/15 rounded-lg px-2 py-1 focus:outline-none focus:ring-2 focus:ring-yeikar-primary/25 text-xs font-mono text-yeikar-neutral"
                >
                  {Array.from({ length: 12 }, (_, i) => i + 1).map(m => (
                    <option key={m} value={m}>
                      {new Date(2020, m - 1).toLocaleString('es-ES', { month: 'long' })}
                    </option>
                  ))}
                </select>
                <select
                  value={selectedYear}
                  onChange={(e) => setSelectedYear(Number(e.target.value))}
                  className="bg-white border border-yeikar-secondary-light/15 rounded-lg px-2 py-1 focus:outline-none focus:ring-2 focus:ring-yeikar-primary/25 text-xs font-mono text-yeikar-neutral"
                >
                  {Array.from({ length: 10 }, (_, i) => new Date().getFullYear() - i).map(y => (
                    <option key={y} value={y}>{y}</option>
                  ))}
                </select>
              </div>
            )}
          </div>
        </div>
      </div>

      {error && (
        <div className="bg-red-50 text-red-700 p-4 rounded-2xl border border-red-200 text-sm animate-fade-in">
          {error}
        </div>
      )}

      {/* Orders List Table */}
      <Card className="overflow-hidden" bodyClassName="p-0">
        {loading ? (
          <div className="p-10">
            <Spinner label="Cargando pedidos..." />
          </div>
        ) : orders.length === 0 ? (
          <div className="p-6">
            <EmptyState
              compact
              icon={
                <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth="2"
                    d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-3 7h3m-3 4h3m-6-4h.01M9 16h.01"
                  />
                </svg>
              }
              title="No hay pedidos registrados en producción"
              description="Cuando una cotización se convierta en pedido, aparecerá aquí."
            />
          </div>
        ) : (
          <ResponsiveDataTable
            columns={columns}
            rows={orders}
            rowKey={(o) => o.id}
            cardBadge={(o) => <EstadoSelect order={o} />}
            tableActions={renderActions}
            cardActions={renderActions}
          />
        )}
      </Card>

      {/* Order Details Modal */}
      <Modal
        open={selectedOrder !== null}
        onClose={() => setSelectedOrder(null)}
        title={selectedOrder ? `Detalle del Pedido #${selectedOrder.id}` : ''}
        size="2xl"
        footer={
          <>
            {selectedOrder && (
              <Button variant="outline" onClick={() => navigate(`/historial?tipo=pedidos&id=${selectedOrder.id}`)}>
                Ver información del Pedido
              </Button>
            )}
            {puedeEntregar && selectedOrder?.entrega_resumen && selectedOrder.entrega_resumen.pendiente > 0
              && ['APROBADO', 'PRODUCCION', 'PAUSADO', 'TERMINADO'].includes(selectedOrder.estado) && (
              <Button
                onClick={() => setEntregaPedido(selectedOrder)}
                icon={<Truck className="h-4 w-4" />}
              >
                Registrar entrega
              </Button>
            )}
            {selectedOrder && ['APROBADO', 'PRODUCCION', 'TERMINADO', 'ENTREGADO'].includes(selectedOrder.estado) && (
              <Button
                onClick={() => { setSelectedOrder(null); navigate('/ventas'); }}
              >
                Ver los Cobros 
              </Button>
            )}
            <Button variant="outline" onClick={() => setSelectedOrder(null)}>
              Cerrar
            </Button>
          </>
        }
      >
        {selectedOrder && (
          <div className="space-y-4">
            <div className="flex items-center justify-between border-b border-yeikar-secondary-light/10 pb-4">
              <div className="flex items-center gap-2">
                <Badge tone={estadoTone(selectedOrder.estado)} dot>
                  {estadoLabel(selectedOrder.estado)}
                </Badge>
                <span className="rounded-full border border-yeikar-secondary-light/20 bg-yeikar-tertiary/30 px-2 py-0.5 font-mono text-[10px] font-bold text-yeikar-secondary">
                  Moneda: {monedaPedido}
                </span>
                {!tieneFabricables(selectedOrder) && (
                  <span className="text-[10px] font-bold uppercase px-2 py-0.5 rounded bg-yeikar-primary/10 text-yeikar-primary-dark border border-yeikar-primary/20">
                    Sin producción · va directo a despacho
                  </span>
                )}
              </div>
            </div>

            <div className="grid grid-cols-2 gap-4 text-sm font-body border-b border-yeikar-secondary-light/10 pb-4">
              <div>
                <span className="text-yeikar-neutral/50 block text-xs uppercase font-bold font-headline">Cliente:</span>
                <strong className="text-yeikar-secondary">{selectedOrder.cliente?.nombre}</strong>
              </div>
              <div>
                <span className="text-yeikar-neutral/50 block text-xs uppercase font-bold font-headline">Fecha de Entrega:</span>
                <span className="font-mono text-xs text-yeikar-neutral/60">{selectedOrder.fecha_entrega_estimada || 'No definida'}</span>
              </div>
            </div>

            <div>
              <h4 className="font-headline font-bold text-sm text-yeikar-secondary mb-3 uppercase tracking-wider">
                Productos y Dimensiones
              </h4>
              <div className="space-y-3">
                {selectedOrder.detalles && selectedOrder.detalles.length > 0 ? (
                  selectedOrder.detalles.map((det) => (
                    <div key={det.id} className="p-3 bg-yeikar-tertiary/25 rounded-xl border border-yeikar-secondary-light/10 space-y-2">
                      <div className="flex justify-between font-headline font-bold text-sm">
                        <span className="flex items-center gap-2">
                          <span className="text-yeikar-secondary">
                            {(det.tipo_item === 'REPARACION' || det.tipo_item === 'SERVICIO')
                              ? (det.descripcion_especifica || det.observaciones || (det.tipo_item === 'REPARACION' ? 'Reparación' : 'Servicio'))
                              : det.tipo_item === 'INSUMO'
                                ? det.material?.nombre || `Material #${det.material_id}`
                                : det.producto?.nombre || 'Producto Personalizado'}
                          </span>
                          {det.tipo_item === 'INSUMO' ? (
                            <span
                              className="bg-emerald-50 text-emerald-700 border border-emerald-200 px-1.5 py-0.5 rounded-md text-[9px] font-black uppercase tracking-wider"
                              title="Insumo de inventario: descuenta stock, no pasa por producción"
                            >
                              Insumo
                            </span>
                          ) : det.tipo_item === 'REPARACION' ? (
                            <span
                              className="bg-amber-50 text-amber-800 border border-amber-200 px-1.5 py-0.5 rounded-md text-[9px] font-black uppercase tracking-wider"
                              title="Reparación de un mueble existente: entra al taller"
                            >
                              Reparación
                            </span>
                          ) : det.tipo_item === 'SERVICIO' ? (
                            <span
                              className="bg-stone-50 text-stone-700 border border-stone-200 px-1.5 py-0.5 rounded-md text-[9px] font-black uppercase tracking-wider"
                              title="Servicio cobrado (flete, instalación…)"
                            >
                              Servicio
                            </span>
                          ) : det.es_obsequio ? (
                            <span
                              className="bg-fuchsia-50 text-fuchsia-700 border border-fuchsia-200 px-1.5 py-0.5 rounded-md text-[9px] font-black uppercase tracking-wider"
                              title="Obsequio de promoción: va con el colchón, no se cobra"
                            >
                              Obsequio
                            </span>
                          ) : det.producto?.es_reventa ? (
                            <span
                              className="bg-sky-50 text-sky-700 border border-sky-200 px-1.5 py-0.5 rounded-md text-[9px] font-black uppercase tracking-wider"
                              title="Producto de reventa: se entrega del inventario, no pasa por producción"
                            >
                              Reventa
                            </span>
                          ) : (
                            <span
                              className="bg-amber-50 text-amber-800 border border-amber-200 px-1.5 py-0.5 rounded-md text-[9px] font-black uppercase tracking-wider"
                              title="Se fabrica a medida: genera orden de producción"
                            >
                              Fabricar
                            </span>
                          )}
                        </span>
                        <span className="text-yeikar-primary-dark">
                          {formatCurrency(Number(det.precio), monedaPedido)}
                          <span className="ml-1 text-[9px] font-black uppercase tracking-wider text-yeikar-neutral/45">
                            {monedaPedido}
                          </span>
                        </span>
                      </div>
                      {det.tipo_item !== 'SERVICIO' && (
                        <div className="grid grid-cols-3 text-xs text-yeikar-neutral/50 font-mono">
                          <div>Ancho: {det.ancho}m</div>
                          <div>Largo: {det.largo}m</div>
                          <div>
                            Cantidad: {det.cantidad}
                            {det.tipo_item === 'INSUMO' && (
                              det.unidad_captura === 'CM'
                                ? ' cm'
                                : det.unidad_captura === 'M'
                                  ? ' m'
                                  : det.material?.unidad_medida?.abreviatura
                                    ? ` ${det.material.unidad_medida.abreviatura}`
                                    : ''
                            )}
                          </div>
                        </div>
                      )}
                      {(det.piezas?.length ?? 0) > 0 && (
                        <div className="flex flex-wrap gap-1.5 pt-1">
                          <span className="text-[10px] font-bold uppercase tracking-wider text-yeikar-neutral/45">
                            Piezas:
                          </span>
                          {det.piezas!.map((pieza) => (
                            <span
                              key={pieza.id ?? pieza.nombre}
                              className="rounded-md border border-yeikar-secondary-light/20 bg-white px-1.5 py-0.5 text-[10px] font-bold text-yeikar-secondary"
                              title="Se produce y costea por separado"
                            >
                              {pieza.nombre}
                              {Number(pieza.cantidad) > 1
                                ? ` × ${Number(pieza.cantidad).toLocaleString('es-CO')}`
                                : ''}
                            </span>
                          ))}
                        </div>
                      )}
                      {det.observaciones && (
                        <p className="text-xs text-yeikar-neutral/60 italic mt-1 border-t border-yeikar-secondary-light/5 pt-1">
                          {det.observaciones}
                        </p>
                      )}
                    </div>
                  ))
                ) : (
                  <p className="text-sm text-yeikar-neutral/50">Este pedido no tiene recetas cargadas.</p>
                )}
              </div>
            </div>

            <div>
              <div className="flex flex-wrap items-center justify-between gap-2 mb-3">
                <h4 className="font-headline font-bold text-sm text-yeikar-secondary uppercase tracking-wider">
                  Entregas
                </h4>
                {selectedOrder.entrega_resumen && selectedOrder.entrega_resumen.total > 0 && (
                  <span className={`rounded-full border px-2.5 py-1 text-[10px] font-black ${
                    selectedOrder.entrega_resumen.estado === 'COMPLETO'
                      ? 'bg-green-100 text-green-700 border-green-200'
                      : selectedOrder.entrega_resumen.estado === 'PARCIAL'
                        ? 'bg-amber-100 text-amber-800 border-amber-200'
                        : 'bg-stone-100 text-stone-600 border-stone-200'
                  }`}>
                    {selectedOrder.entrega_resumen.entregado} / {selectedOrder.entrega_resumen.total} entregado
                    {selectedOrder.entrega_resumen.pendiente > 0
                      ? ` · faltan ${selectedOrder.entrega_resumen.pendiente}`
                      : ''}
                  </span>
                )}
              </div>

              {!puedeEntregar ? (
                <p className="text-sm text-yeikar-neutral/50">
                  No tienes acceso al módulo de despachos para consultar las entregas.
                </p>
              ) : entregasLoading ? (
                <Spinner label="Cargando entregas..." />
              ) : entregas.length === 0 ? (
                <p className="text-sm text-yeikar-neutral/50">
                  Todavía no hay entregas registradas. Usa “Registrar entrega” para llevar lo que ya está listo.
                </p>
              ) : (
                <div className="space-y-2">
                  {entregas.map((envio) => (
                    <div key={envio.id} className="rounded-xl border border-yeikar-secondary-light/15 bg-white p-3">
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <span className="font-mono text-xs font-bold text-yeikar-secondary">
                          Despacho #{envio.id}
                        </span>
                        <span className={`rounded-full border px-2 py-0.5 text-[9px] font-black uppercase ${
                          envio.estado === 'ENTREGADO'
                            ? 'bg-green-50 text-green-700 border-green-200'
                            : envio.estado === 'FALLIDO'
                              ? 'bg-red-50 text-red-700 border-red-200'
                              : 'bg-amber-50 text-amber-800 border-amber-200'
                        }`}>
                          {envio.estado === 'EN_TRANSITO' ? 'En tránsito' : envio.estado.toLowerCase()}
                        </span>
                      </div>
                      <div className="mt-1 text-[11px] font-mono text-yeikar-neutral/55">
                        {envio.fecha_entrega
                          ? `Entregado: ${new Date(envio.fecha_entrega).toLocaleString('es-VE')}`
                          : envio.fecha_salida
                            ? `Salió: ${new Date(envio.fecha_salida).toLocaleString('es-VE')}`
                            : 'Sin salida registrada'}
                        {envio.guia_despacho ? ` · Guía ${envio.guia_despacho}` : ''}
                      </div>
                      {envio.detalles && envio.detalles.length > 0 && (
                        <ul className="mt-2 space-y-0.5 text-xs text-yeikar-secondary/80">
                          {envio.detalles.map((item) => (
                            <li key={item.id} className="flex justify-between gap-3">
                              <span>• {item.descripcion || `Ítem #${item.detalle_pedido_id}`}</span>
                              <span className="font-mono font-bold">×{item.cantidad}</span>
                            </li>
                          ))}
                        </ul>
                      )}
                    </div>
                  ))}
                </div>
              )}

              {puedeEntregar && selectedOrder.entrega_resumen && selectedOrder.entrega_resumen.pendiente > 0
                && ['APROBADO', 'PRODUCCION', 'PAUSADO', 'TERMINADO'].includes(selectedOrder.estado) && (
                <Button
                  className="mt-3"
                  size="sm"
                  onClick={() => setEntregaPedido(selectedOrder)}
                  icon={<Truck className="h-4 w-4" />}
                >
                  Registrar entrega parcial
                </Button>
              )}
            </div>

            {rentabilidad && (
              <div className="rounded-2xl border border-yeikar-secondary-light/15 bg-yeikar-tertiary/20 p-4 space-y-2">
                <h4 className="font-headline font-bold text-sm text-yeikar-secondary uppercase tracking-wider flex items-center gap-2">
                  Margen del Pedido
                  {rentabilidad.tiene_produccion && (
                    <span className="text-[9px] font-bold uppercase px-2 py-0.5 rounded bg-amber-100 text-amber-800">real vs estimado</span>
                  )}
                  <span className="ml-auto rounded-full border border-yeikar-secondary-light/20 bg-white/60 px-2 py-0.5 text-[9px] font-black text-yeikar-secondary">
                    {monedaPedido}
                  </span>
                </h4>
                <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 text-xs font-mono">
                  <div>
                    <span className="text-yeikar-neutral/50 block text-[10px] uppercase font-bold">Total cobrado</span>
                    <b className="text-yeikar-secondary">{fmtPedido(rentabilidad.total_cobrado)}</b>
                  </div>
                  <div>
                    <span className="text-yeikar-neutral/50 block text-[10px] uppercase font-bold">Costo estimado</span>
                    <b className="text-yeikar-primary-dark">{fmtPedido(rentabilidad.costo_estimado_moneda)}</b>
                  </div>
                  <div>
                    <span className="text-yeikar-neutral/50 block text-[10px] uppercase font-bold">Costo real (producción)</span>
                    <b className="text-yeikar-primary-dark">{fmtPedido(rentabilidad.costo_real_moneda)}</b>
                  </div>
                  {rentabilidad.flete_real_moneda > 0 && (
                    <div>
                      <span className="text-yeikar-neutral/50 block text-[10px] uppercase font-bold">Flete real</span>
                      <b className="text-yeikar-primary-dark">{fmtPedido(rentabilidad.flete_real_moneda)}</b>
                    </div>
                  )}
                  <div>
                    <span className="text-yeikar-neutral/50 block text-[10px] uppercase font-bold">Margen estimado</span>
                    <b className={rentabilidad.margen_estimado_moneda >= 0 ? 'text-emerald-600' : 'text-red-600'}>
                      {fmtPedido(rentabilidad.margen_estimado_moneda)}
                    </b>
                  </div>
                  <div>
                    <span className="text-yeikar-neutral/50 block text-[10px] uppercase font-bold">Margen real</span>
                    <b className={rentabilidad.margen_real_moneda >= 0 ? 'text-emerald-600' : 'text-red-600'}>
                      {fmtPedido(rentabilidad.margen_real_moneda)}
                    </b>
                  </div>
                </div>
                {!esMonedaBase && (
                  <p className="text-[10px] text-yeikar-neutral/45">
                    Cifras en {monedaPedido} a la tasa congelada del pedido.
                  </p>
                )}
                {(rentabilidad.por_pieza ?? []).some((p) => p.pieza_nombre) && (
                  <details className="rounded-xl border border-yeikar-secondary-light/15 bg-white/60 px-3 py-2">
                    <summary className="cursor-pointer select-none text-[10px] font-bold uppercase tracking-wider text-yeikar-neutral/55">
                      Costo por pieza del juego
                    </summary>
                    <div className="mt-2 space-y-1">
                      {(rentabilidad.por_pieza ?? [])
                        .filter((p) => p.pieza_nombre)
                        .map((p) => (
                          <div key={p.orden_id} className="flex items-center justify-between gap-2 text-[11px] font-mono">
                            <span className="min-w-0 truncate text-yeikar-secondary" title={p.producto_nombre || ''}>
                              {p.pieza_nombre}
                              {p.cantidad && p.cantidad > 1
                                ? ` × ${p.cantidad.toLocaleString('es-CO')}`
                                : ''}
                              <span className="ml-1 text-[9px] font-sans uppercase text-yeikar-neutral/40">
                                {p.estado.replace('_', ' ')}
                              </span>
                            </span>
                            <b className="shrink-0 text-right text-yeikar-primary-dark">
                              {fmtPedido(p.costo_real / (rentabilidad.tasa_cambio || 1))}
                            </b>
                          </div>
                        ))}
                    </div>
                    <p className="mt-1.5 text-[10px] text-yeikar-neutral/45">
                      El precio de venta es del renglón completo; aquí solo se reparte el costo real.
                    </p>
                  </details>
                )}
                {rentabilidad.diferencia_costo_moneda !== 0 && (
                  <p className={`text-[11px] ${rentabilidad.diferencia_costo_moneda > 0 ? 'text-red-600' : 'text-emerald-600'}`}>
                    El costo real difiere del estimado en{' '}
                    {rentabilidad.diferencia_costo_moneda > 0 ? '+' : ''}
                    {fmtPedido(rentabilidad.diferencia_costo_moneda)}.
                  </p>
                )}
              </div>
            )}
            {rentabilidadLoading && (
              <div className="text-xs text-yeikar-neutral/50 animate-pulse">Calculando margen…</div>
            )}
          </div>
        )}
      </Modal>

      <EntregaParcialModal
        open={entregaPedido !== null}
        pedido={entregaPedido}
        onClose={() => setEntregaPedido(null)}
        onCreated={() => {
          fetchOrders(search);
          if (selectedOrder) {
            pedidoService.getById(selectedOrder.id)
              .then(setSelectedOrder)
              .catch(() => {});
          }
        }}
      />

      {/* Confirm Delete */}
      <ConfirmDialog
        open={confirmOpen}
        title="Eliminar pedido"
        message="¿Estás seguro de que deseas eliminar este pedido?"
        confirmLabel="Eliminar"
        onCancel={() => setConfirmOpen(false)}
        onConfirm={async () => {
          await handleDelete();
          setConfirmOpen(false);
        }}
      />
    </div>
  );
}