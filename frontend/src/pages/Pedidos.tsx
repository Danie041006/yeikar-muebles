import { useEffect, useState } from 'react';
import { pedidoService, Order } from '../services/pedidoService';

export default function Pedidos() {
  const [orders, setOrders] = useState<Order[]>([]);
  const [search, setSearch] = useState('');
  const [soloMesActual, setSoloMesActual] = useState(true);
  const [selectedMonth, setSelectedMonth] = useState(new Date().getMonth() + 1);
  const [selectedYear, setSelectedYear] = useState(new Date().getFullYear());
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const [selectedOrder, setSelectedOrder] = useState<Order | null>(null);

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

  const handleUpdateStatus = async (orderId: number, currentObs: string | undefined, newStatus: string) => {
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
    }
  };

  const handleDelete = async (id: number) => {
    if (window.confirm('¿Estás seguro de que deseas eliminar este pedido?')) {
      try {
        await pedidoService.delete(id);
        fetchOrders(search);
      } catch (err) {
        console.error(err);
        alert('Error al eliminar el pedido.');
      }
    }
  };

  const estadosPedido = [
    { value: 'APROBADO', label: 'Aprobado' },
    { value: 'PRODUCCION', label: 'En producción' },
    { value: 'TERMINADO', label: 'Terminado' },
    { value: 'ENTREGADO', label: 'Entregado' },
    { value: 'CANCELADO', label: 'Cancelado' }
  ];

  return (
    <div className="space-y-6">
      {/* Search and filter bar */}
      <div className="flex flex-col md:flex-row items-center justify-between gap-4 bg-white p-4 rounded-xl border border-yeikar-secondary-light/10 shadow-sm">
        <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-3 w-full md:w-auto flex-1">
          <div className="relative w-full sm:w-72">
            <input
              type="text"
              placeholder="Buscar pedidos por cliente o estado..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="w-full pl-10 pr-4 py-2 border border-yeikar-secondary-light/20 rounded-lg focus:outline-none focus:ring-2 focus:ring-yeikar-primary focus:border-transparent font-body bg-yeikar-tertiary/30 text-sm"
            />
            <div className="absolute left-3.5 top-2.5 text-yeikar-neutral/40">
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
              </svg>
            </div>
          </div>
          
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
              <div className="flex items-center gap-1.5 animate-fadeIn">
                <span className="text-yeikar-neutral/40">|</span>
                <select
                  value={selectedMonth}
                  onChange={(e) => setSelectedMonth(Number(e.target.value))}
                  className="bg-white border border-yeikar-secondary-light/20 rounded px-1.5 py-0.5 focus:outline-none focus:ring-1 focus:ring-yeikar-primary text-xs font-mono"
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
                  className="bg-white border border-yeikar-secondary-light/20 rounded px-1.5 py-0.5 focus:outline-none focus:ring-1 focus:ring-yeikar-primary text-xs font-mono"
                >
                  {Array.from({ length: 10 }, (_, i) => new Date().getFullYear() - i).map(y => (
                    <option key={y} value={y}>{y}</option>
                  ))}
                </select>
              </div>
            )}
          </div>
        </div>
        <div className="text-xs text-yeikar-neutral/60 font-mono">
          Total pedidos: {orders.length}
        </div>
      </div>

      {error && (
        <div className="bg-red-50 text-red-700 p-4 rounded-xl border border-red-200 text-sm">
          {error}
        </div>
      )}

      {/* Orders List Table */}
      <div className="bg-white rounded-xl border border-yeikar-secondary-light/10 shadow-sm overflow-hidden">
        {loading ? (
          <div className="p-8 text-center text-yeikar-neutral/60 font-mono">Cargando pedidos...</div>
        ) : orders.length === 0 ? (
          <div className="p-8 text-center text-yeikar-neutral/60">No hay pedidos registrados en producción.</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse">
              <thead>
                <tr className="bg-yeikar-neutral text-yeikar-tertiary font-headline uppercase text-xs tracking-wider">
                  <th className="px-6 py-4 border-b border-yeikar-secondary/20">Pedido ID</th>
                  <th className="px-6 py-4 border-b border-yeikar-secondary/20">Cliente</th>
                  <th className="px-6 py-4 border-b border-yeikar-secondary/20">Fecha Creación</th>
                  <th className="px-6 py-4 border-b border-yeikar-secondary/20">Entrega Estimada</th>
                  <th className="px-6 py-4 border-b border-yeikar-secondary/20">Estado</th>
                  <th className="px-6 py-4 border-b border-yeikar-secondary/20 text-right">Acciones</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-yeikar-secondary-light/10 text-sm font-body">
                {orders.map((order) => (
                  <tr key={order.id} className="hover:bg-yeikar-tertiary/20 transition-colors">
                    <td className="px-6 py-4 font-mono font-bold text-yeikar-secondary">
                      #{order.id}
                    </td>
                    <td className="px-6 py-4 font-bold text-yeikar-secondary font-headline">
                      {order.cliente?.nombre || `Cliente ID: ${order.cliente_id}`}
                    </td>
                    <td className="px-6 py-4 font-mono text-yeikar-neutral/70">
                      {order.fecha}
                    </td>
                    <td className="px-6 py-4 font-mono text-yeikar-neutral/70">
                      {order.fecha_entrega_estimada || 'Sin definir'}
                    </td>
                    <td className="px-6 py-4">
                      <select
                        value={order.estado === 'COTIZADO' ? 'APROBADO' : order.estado}
                        onChange={(e) => handleUpdateStatus(order.id, order.observaciones, e.target.value)}
                        className={`px-2 py-1 rounded font-bold text-xs font-headline focus:outline-none ${
                          order.estado === 'APROBADO' || order.estado === 'COTIZADO'
                            ? 'bg-blue-100 text-blue-800'
                            : order.estado === 'PRODUCCION'
                            ? 'bg-orange-100 text-orange-800'
                            : order.estado === 'TERMINADO'
                            ? 'bg-green-100 text-green-800'
                            : order.estado === 'ENTREGADO'
                            ? 'bg-gray-200 text-gray-800'
                            : 'bg-red-100 text-red-800'
                        }`}
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
                          className="px-3 py-1 bg-yeikar-secondary text-yeikar-tertiary hover:bg-yeikar-secondary-light rounded text-xs font-bold font-headline transition-colors"
                        >
                          Ver detalles del pedido
                        </button>
                        <button
                          onClick={() => handleDelete(order.id)}
                          className="p-1 text-red-600 hover:text-red-850"
                          title="Eliminar"
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
      </div>

      {/* Order Details Modal */}
      {selectedOrder && (
        <div className="fixed inset-0 bg-yeikar-neutral/50 backdrop-blur-sm flex items-center justify-center p-4 z-50">
          <div className="bg-white rounded-xl border border-yeikar-secondary-light/10 shadow-2xl w-full max-w-2xl overflow-hidden">
            <div className="bg-yeikar-neutral p-4 text-yeikar-tertiary flex items-center justify-between">
              <h3 className="font-headline font-bold text-lg text-yeikar-primary">
                Detalle del Pedido #{selectedOrder.id}
              </h3>
              <button
                onClick={() => setSelectedOrder(null)}
                className="text-yeikar-tertiary/60 hover:text-yeikar-tertiary transition-colors"
              >
                <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
            <div className="p-6 space-y-4 max-h-[80vh] overflow-y-auto">
              <div className="grid grid-cols-2 gap-4 text-sm font-body border-b border-yeikar-secondary-light/10 pb-4">
                <div>
                  <span className="text-yeikar-neutral/50 block text-xs uppercase font-bold font-headline">Cliente:</span>
                  <strong className="text-yeikar-secondary">{selectedOrder.cliente?.nombre}</strong>
                </div>
                <div>
                  <span className="text-yeikar-neutral/50 block text-xs uppercase font-bold font-headline">Fecha de Entrega:</span>
                  <span className="font-mono">{selectedOrder.fecha_entrega_estimada || 'No definida'}</span>
                </div>
              </div>

              <div>
                <h4 className="font-headline font-bold text-sm text-yeikar-secondary mb-3 uppercase tracking-wider">
                  Productos y Dimensiones
                </h4>
                <div className="space-y-3">
                  {selectedOrder.detalles && selectedOrder.detalles.length > 0 ? (
                    selectedOrder.detalles.map((det) => (
                      <div key={det.id} className="p-3 bg-yeikar-tertiary/25 rounded-lg border border-yeikar-secondary-light/10 space-y-2">
                        <div className="flex justify-between font-headline font-bold text-sm">
                          <span className="text-yeikar-secondary">
                            {det.producto?.nombre || 'Producto Personalizado'}
                          </span>
                          <span className="text-yeikar-primary">
                            ${Number(det.precio).toLocaleString()} COP
                          </span>
                        </div>
                        <div className="grid grid-cols-3 text-xs text-yeikar-neutral/70 font-mono">
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

              <div className="flex items-center justify-end gap-3 pt-4 border-t border-yeikar-secondary-light/10">
                <button
                  onClick={() => setSelectedOrder(null)}
                  className="px-5 py-2 bg-yeikar-neutral text-yeikar-tertiary hover:bg-yeikar-neutral-light font-bold rounded-lg shadow-md transition-all text-sm font-headline"
                >
                  Cerrar
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
