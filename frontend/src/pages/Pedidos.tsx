import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
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
} from '../components/ui';
import { pedidoService, Order } from '../services/pedidoService';

export default function Pedidos() {
  const navigate = useNavigate();
  const [orders, setOrders] = useState<Order[]>([]);
  const [search, setSearch] = useState('');
  const [soloMesActual, setSoloMesActual] = useState(true);
  const [selectedMonth, setSelectedMonth] = useState(new Date().getMonth() + 1);
  const [selectedYear, setSelectedYear] = useState(new Date().getFullYear());
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const [selectedOrder, setSelectedOrder] = useState<Order | null>(null);

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
    } catch (err) {
      console.error(err);
      alert('Error al actualizar el estado del pedido.');
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
      alert('Error al eliminar el pedido.');
    }
  };

  const estadosPedido = [
    { value: 'APROBADO', label: 'Aprobado' },
    { value: 'PRODUCCION', label: 'En producción' },
    { value: 'TERMINADO', label: 'Terminado' },
    { value: 'ENTREGADO', label: 'Entregado' },
    { value: 'CANCELADO', label: 'Cancelado' }
  ];

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
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse">
              <thead className="bg-yeikar-tertiary/20 text-yeikar-secondary font-headline font-bold text-xs uppercase tracking-wider">
                <tr>
                  <th className="table-th">Pedido ID</th>
                  <th className="table-th">Cliente</th>
                  <th className="table-th">Fecha Creación</th>
                  <th className="table-th">Entrega Estimada</th>
                  <th className="table-th">Estado</th>
                  <th className="table-th text-right">Acciones</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-yeikar-secondary-light/5 text-sm">
                {orders.map((order) => (
                  <tr key={order.id} className="hover:bg-yeikar-tertiary/10 transition-colors">
                    <td className="px-6 py-4 font-mono font-bold text-yeikar-secondary">
                      #{order.id}
                    </td>
                    <td className="px-6 py-4 font-bold text-yeikar-secondary font-headline">
                      {order.cliente?.nombre || `Cliente ID: ${order.cliente_id}`}
                    </td>
                    <td className="px-6 py-4 font-mono text-xs text-yeikar-neutral/50">
                      {order.fecha}
                    </td>
                    <td className="px-6 py-4 font-mono text-xs text-yeikar-neutral/50">
                      {order.fecha_entrega_estimada || 'Sin definir'}
                    </td>
                    <td className="px-6 py-4">
                      <select
                        value={order.estado === 'COTIZADO' ? 'APROBADO' : order.estado}
                        disabled={statusUpdatingId !== null}
                        onChange={(e) => handleUpdateStatus(order.id, order.observaciones, e.target.value)}
                        className={`px-2.5 py-1 rounded-full font-bold text-xs font-headline border focus:outline-none focus:ring-2 focus:ring-yeikar-primary/30 disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer ${estadoSelectClass(order.estado)}`}
                        aria-label={`Cambiar estado del pedido #${order.id}`}
                      >
                        {estadosPedido.map((est) => (
                          <option key={est.value} value={est.value}>
                            {est.label}
                          </option>
                        ))}
                      </select>
                    </td>
                    <td className="px-6 py-4 text-right">
                      <div className="flex items-center justify-end gap-2">
                        <button
                          onClick={() => setSelectedOrder(order)}
                          className="btn px-3 py-1.5 rounded-lg text-xs bg-yeikar-secondary text-yeikar-tertiary hover:bg-yeikar-secondary-light"
                        >
                          Ver detalles
                        </button>
                        {['APROBADO', 'PRODUCCION', 'TERMINADO', 'ENTREGADO'].includes(order.estado) && (
                          <button
                            onClick={() => navigate('/ventas')}
                            className="btn px-3 py-1.5 rounded-lg text-xs bg-yeikar-primary text-yeikar-neutral hover:bg-yeikar-primary-light flex items-center gap-1"
                            title="Ir a Facturas y Cobros"
                          >
                            <span>Factura / Cobros</span>
                          </button>
                        )}
                        <button
                          onClick={() => handleOpenDeleteConfirm(order.id)}
                          className="p-1.5 text-red-600 hover:text-red-800 transition-colors"
                          title="Eliminar"
                          aria-label="Eliminar pedido"
                        >
                          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                          </svg>
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
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
            {selectedOrder && ['APROBADO', 'PRODUCCION', 'TERMINADO', 'ENTREGADO'].includes(selectedOrder.estado) && (
              <Button
                onClick={() => { setSelectedOrder(null); navigate('/ventas'); }}
              >
                Ver / Crear Factura y Cobros →
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
              <Badge tone={estadoTone(selectedOrder.estado)} dot>
                {estadoLabel(selectedOrder.estado)}
              </Badge>
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
                        <span className="text-yeikar-secondary">
                          {det.producto?.nombre || 'Producto Personalizado'}
                        </span>
                        <span className="text-yeikar-primary-dark">
                          ${Number(det.precio).toLocaleString()} COP
                        </span>
                      </div>
                      <div className="grid grid-cols-3 text-xs text-yeikar-neutral/50 font-mono">
                        <div>Ancho: {det.ancho}m</div>
                        <div>Largo: {det.largo}m</div>
                        <div>Cantidad: {det.cantidad}</div>
                      </div>
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
          </div>
        )}
      </Modal>

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