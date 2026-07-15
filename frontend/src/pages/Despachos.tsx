import React, { useEffect, useState } from 'react';
import { envioService, Envio, EnvioUpdate } from '../services/envioService';
import { OrderDetail } from '../services/pedidoService';
import { Empleado } from '../services/produccionService';
import api from '../services/api';
export default function Despachos() {
  const [envios, setEnvios] = useState<Envio[]>([]);
  const [empleados, setEmpleados] = useState<Empleado[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [activeTab, setActiveTab] = useState<'PREPARADO' | 'EN_TRANSITO' | 'ENTREGADO' | 'FALLIDO'>('PREPARADO');
  // Modal / Assign Form state
  const [assigningEnvio, setAssigningEnvio] = useState<Envio | null>(null);
  const [selectedEmpleadoId, setSelectedEmpleadoId] = useState('');
  const [direccionEntrega, setDireccionEntrega] = useState('');
  const [guiaDespacho, setGuiaDespacho] = useState('');
  const [observaciones, setObservaciones] = useState('');
  // Fallido Form state
  const [failingEnvio, setFailingEnvio] = useState<Envio | null>(null);
  const [fallaObservaciones, setFallaObservaciones] = useState('');
  const fetchEnvios = async () => {
    try {
      setLoading(true);
      const data = await envioService.getAll(search || undefined, activeTab);
      setEnvios(data);
    } catch (error) {
      console.error('Error fetching delivery shipments:', error);
    } finally {
      setLoading(false);
    }
  };
  const fetchEmpleados = async () => {
    try {
      const response = await api.get<Empleado[]>('/empleado/');
      setEmpleados(response.data.filter(e => e.activo));
    } catch (error) {
      console.error('Error loading employees:', error);
    }
  };
  useEffect(() => {
    fetchEnvios();
  }, [activeTab, search]);
  useEffect(() => {
    fetchEmpleados();
  }, []);
  const handleOpenAssign = (envio: Envio) => {
    setAssigningEnvio(envio);
    setSelectedEmpleadoId(envio.empleado_id ? envio.empleado_id.toString() : '');
    setDireccionEntrega(envio.direccion_entrega || envio.pedido?.cliente?.direccion || '');
    setGuiaDespacho(envio.guia_despacho || '');
    setObservaciones(envio.observaciones || '');
  };
  const handleAssignSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!assigningEnvio) return;
    const data: EnvioUpdate = {
      empleado_id: selectedEmpleadoId ? parseInt(selectedEmpleadoId) : null,
      direccion_entrega: direccionEntrega || null,
      guia_despacho: guiaDespacho || null,
      observaciones: observaciones || null,
      estado: 'EN_TRANSITO', // automatically set in transit upon assignment/dispatch
      fecha_salida: new Date().toISOString(),
    };
    try {
      await envioService.update(assigningEnvio.id, data);
      alert('¡Envío asignado y puesto en tránsito con éxito!');
      setAssigningEnvio(null);
      fetchEnvios();
    } catch (error) {
      console.error('Error dispatching shipment:', error);
      alert('Ocurrió un error al registrar el despacho.');
    }
  };
  const handleConfirmEntrega = async (envioId: number) => {
    if (!window.confirm('¿Confirmar que el pedido ha sido entregado exitosamente al cliente?')) return;
    try {
      await envioService.updateEstado(envioId, 'ENTREGADO');
      alert('¡Envío marcado como ENTREGADO y Pedido actualizado!');
      fetchEnvios();
    } catch (error) {
      console.error('Error delivering shipment:', error);
      alert('Error al confirmar la entrega.');
    }
  };
  const handleOpenFalla = (envio: Envio) => {
    setFailingEnvio(envio);
    setFallaObservaciones('');
  };
  const handleFallaSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!failingEnvio) return;
    const data: EnvioUpdate = {
      estado: 'FALLIDO',
      observaciones: fallaObservaciones || 'La entrega falló en ruta.'
    };
    try {
      await envioService.update(failingEnvio.id, data);
      alert('Envío reportado como fallido.');
      setFailingEnvio(null);
      fetchEnvios();
    } catch (error) {
      console.error('Error failing shipment:', error);
      alert('Error al reportar la falla.');
    }
  };
  const handleReProgramar = async (envioId: number) => {
    if (!window.confirm('¿Desea re-programar este despacho? Volverá al estado PENDIENTE de asignación.')) return;
    try {
      await envioService.update(envioId, {
        estado: 'PREPARADO',
        fecha_salida: null,
        fecha_entrega: null
      });
      alert('Envío re-programado con éxito.');
      fetchEnvios();
    } catch (error) {
      console.error('Error reprogramming shipment:', error);
      alert('Error al re-programar.');
    }
  };
  const getStatusBadgeClass = (status: string) => {
    switch (status) {
      case 'PREPARADO': return 'bg-blue-100 text-blue-800 border-blue-200';
      case 'EN_TRANSITO': return 'bg-amber-100 text-amber-800 border-amber-200 animate-pulse';
      case 'ENTREGADO': return 'bg-green-100 text-green-800 border-green-200';
      case 'FALLIDO': return 'bg-red-100 text-red-800 border-red-200';
      default: return 'bg-gray-100 text-gray-800 border-gray-200';
    }
  };
  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
        <div>
          <h1 className="text-3xl font-black font-headline text-yeikar-secondary tracking-tight">
            Envíos y Despachos
          </h1>
          <p className="text-yeikar-neutral/60 mt-1 text-sm font-body">
            Monitorea el estado de entrega de los pedidos finalizados en fábrica.
          </p>
        </div>
        {/* Search */}
        <div className="relative w-full md:w-80">
          <input
            type="text"
            placeholder="Buscar por cliente, guía o dirección..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full bg-white border border-yeikar-secondary-light/10 rounded-xl pl-10 pr-4 py-2.5 text-sm text-yeikar-neutral placeholder-yeikar-neutral/40 focus:outline-none focus:border-yeikar-primary shadow-sm"
          />
        </div>
      </div>
      {/* Tabs bar */}
      <div className="flex gap-2 border-b border-yeikar-secondary-light/10 pb-px flex-wrap">
        {(['PREPARADO', 'EN_TRANSITO', 'ENTREGADO', 'FALLIDO'] as const).map((tab) => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className={`px-5 py-3 text-sm font-headline font-bold border-b-2 transition-all ${
              activeTab === tab
                ? 'border-yeikar-primary text-yeikar-primary'
                : 'border-transparent text-yeikar-neutral/65 hover:text-yeikar-primary'
            }`}
          >
            {tab === 'PREPARADO' && 'Pendientes'}
            {tab === 'EN_TRANSITO' && 'En Ruta'}
            {tab === 'ENTREGADO' && 'Entregados'}
            {tab === 'FALLIDO' && 'Novedades/Fallas'}
          </button>
        ))}
      </div>
      {/* Main content grid */}
      {loading ? (
        <div className="flex flex-col items-center justify-center py-20 space-y-4">
          <div className="w-10 h-10 border-4 border-yeikar-primary border-t-transparent rounded-full animate-spin"></div>
          <p className="text-sm font-mono text-yeikar-neutral/60">Cargando despachos...</p>
        </div>
      ) : envios.length === 0 ? (
        <div className="bg-white border border-yeikar-secondary-light/10 rounded-2xl p-12 text-center text-yeikar-neutral/40">
          <svg className="w-12 h-12 mx-auto text-yeikar-neutral/20 mb-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 17a2 2 0 11-4 0 2 2 0 014 0zM19 17a2 2 0 11-4 0 2 2 0 014 0z" />
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M13 16V6a1 1 0 00-1-1H4a1 1 0 00-1 1v10M21 16V10a2 2 0 00-2-2h-3V6" />
          </svg>
          <p className="text-sm font-medium">No hay despachos en esta categoría.</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {envios.map((envio) => (
            <div
              key={envio.id}
              className="bg-white border border-yeikar-secondary-light/10 rounded-2xl p-5 shadow-sm hover:shadow-md transition-all relative overflow-hidden flex flex-col justify-between"
            >
              {/* Left colored border */}
              <div className={`absolute top-0 bottom-0 left-0 w-1.5 ${
                envio.estado === 'PREPARADO' ? 'bg-blue-400' :
                envio.estado === 'EN_TRANSITO' ? 'bg-amber-400 animate-pulse' :
                envio.estado === 'ENTREGADO' ? 'bg-green-400' : 'bg-red-400'
              }`} />
              <div className="space-y-4 pl-2">
                {/* ID & Badge */}
                <div className="flex items-center justify-between">
                  <span className="text-[10px] font-mono font-black text-yeikar-neutral/40">
                    DESPACHO #{envio.id} (PEDIDO #{envio.pedido_id})
                  </span>
                  <span className={`text-[10px] font-black font-headline px-2 py-0.5 rounded-full border ${getStatusBadgeClass(envio.estado)}`}>
                    {envio.estado}
                  </span>
                </div>
                {/* Cliente y Detalles */}
                <div>
                  <h3 className="font-headline font-bold text-yeikar-secondary text-base">
                    {envio.pedido?.cliente?.nombre || 'Cliente no registrado'}
                  </h3>
                  <p className="text-xs text-yeikar-neutral/50 font-mono mt-0.5">
                    Contacto: {envio.pedido?.cliente?.telefono || 'S/N'}
                  </p>
                </div>
                {/* Muebles en el pedido */}
                <div className="bg-yeikar-tertiary/20 p-3 rounded-xl border border-yeikar-secondary-light/5">
                  <span className="text-[10px] font-black uppercase text-yeikar-neutral/45 block mb-1">
                    Muebles a Entregar
                  </span>
                  <div className="space-y-1">
                    {envio.pedido?.detalles?.map((det: OrderDetail) => (
                      <div key={det.id} className="text-xs text-yeikar-secondary/85 flex justify-between">
                        <span>• {det.producto?.nombre || 'Producto'}</span>
                        <span className="font-mono font-bold">x{det.cantidad}</span>
                      </div>
                    ))}
                  </div>
                </div>
                {/* Dirección de Entrega */}
                <div className="text-xs text-yeikar-secondary space-y-1">
                  <span className="text-[10px] font-black uppercase text-yeikar-neutral/45 block">
                    Dirección de Entrega
                  </span>
                  <p className="italic bg-gray-550 p-2 rounded-lg border border-gray-100 text-yeikar-neutral/80">
                    {envio.direccion_entrega || 'No especificada'}
                  </p>
                </div>
                {/* Datos del Chofer asignado */}
                {envio.empleado && (
                  <div className="text-xs text-yeikar-secondary flex items-center gap-2">
                    <span className="text-[10px] font-black uppercase text-yeikar-neutral/45">Chofer:</span>
                    <span className="font-bold bg-yeikar-tertiary/40 px-2 py-0.5 rounded text-yeikar-primary">
                      {envio.empleado.nombre} {envio.empleado.apellido}
                    </span>
                  </div>
                )}
                {/* Guía Despacho */}
                {envio.guia_despacho && (
                  <div className="text-xs text-yeikar-neutral/70 font-mono">
                    Guía de Despacho: <span className="font-bold text-yeikar-secondary">#{envio.guia_despacho}</span>
                  </div>
                )}
                {/* Fechas */}
                {envio.fecha_salida && (
                  <div className="text-[10px] text-yeikar-neutral/40 font-mono">
                    Salida: {new Date(envio.fecha_salida).toLocaleString('es-CO')}
                  </div>
                )}
                {envio.fecha_entrega && (
                  <div className="text-[10px] text-yeikar-neutral/40 font-mono">
                    Entrega: {new Date(envio.fecha_entrega).toLocaleString('es-CO')}
                  </div>
                )}
                {}
                {envio.observaciones && (
                  <p className="text-xs text-yeikar-neutral/60 bg-yellow-50/50 p-2 rounded border border-yellow-100 text-[11px]">
                    Obs: {envio.observaciones}
                  </p>
                )}
              </div>
              {/* Action Buttons */}
              <div className="mt-5 pt-3 border-t border-yeikar-secondary-light/5 flex gap-2">
                {envio.estado === 'PREPARADO' && (
                  <button
                    onClick={() => handleOpenAssign(envio)}
                    className="flex-1 bg-yeikar-primary hover:bg-yeikar-primary-light text-yeikar-neutral text-xs font-headline font-bold py-2 px-3 rounded-xl shadow-sm transition-colors text-center"
                  >
                    Asignar y Enviar
                  </button>
                )}
                {envio.estado === 'EN_TRANSITO' && (
                  <>
                    <button
                      onClick={() => handleConfirmEntrega(envio.id)}
                      className="flex-1 bg-green-500 hover:bg-green-600 text-white text-xs font-headline font-bold py-2 px-3 rounded-xl shadow-sm transition-colors"
                    >
                      Confirmar Entrega ✅
                    </button>
                    <button
                      onClick={() => handleOpenFalla(envio)}
                      className="bg-red-50 hover:bg-red-100 text-red-600 text-xs font-headline font-bold py-2 px-3 rounded-xl border border-red-200 transition-colors"
                    >
                      Falla ⚠️
                    </button>
                  </>
                )}
                {envio.estado === 'FALLIDO' && (
                  <button
                    onClick={() => handleReProgramar(envio.id)}
                    className="flex-1 bg-amber-500 hover:bg-amber-600 text-white text-xs font-headline font-bold py-2 px-3 rounded-xl shadow-sm transition-colors"
                  >
                    Re-Programar Despacho 🔄
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
      {/* Assign Driver Modal */}
      {assigningEnvio && (
        <div className="fixed inset-0 bg-yeikar-secondary/60 backdrop-blur-sm flex items-center justify-center p-4 z-50 animate-fade-in">
          <div className="bg-white rounded-3xl shadow-xl border border-yeikar-secondary-light/10 max-w-md w-full p-6 space-y-4">
            <h3 className="text-xl font-headline font-black text-yeikar-secondary tracking-tight">
              Asignar Envío para Pedido #{assigningEnvio.pedido_id}
            </h3>
            <p className="text-xs text-yeikar-neutral/60">
              Registra los datos del vehículo y conductor para poner la orden en ruta.
            </p>
            <form onSubmit={handleAssignSubmit} className="space-y-4">
              <div>
                <label className="block text-xs font-bold text-yeikar-neutral/60 mb-1">Chofer/Conductor *</label>
                <select
                  value={selectedEmpleadoId}
                  onChange={(e) => setSelectedEmpleadoId(e.target.value)}
                  required
                  className="w-full bg-yeikar-tertiary/30 border border-yeikar-secondary-light/10 rounded-xl p-2.5 text-sm focus:outline-none focus:border-yeikar-primary"
                >
                  <option value="">Selecciona Conductor...</option>
                  {empleados.map((emp) => (
                    <option key={emp.id} value={emp.id}>
                      {emp.nombre} {emp.apellido} ({emp.cargo?.nombre || 'Empleado'})
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-xs font-bold text-yeikar-neutral/60 mb-1">Guía de Despacho (Opcional)</label>
                <input
                  type="text"
                  placeholder="Ej: G-90210"
                  value={guiaDespacho}
                  onChange={(e) => setGuiaDespacho(e.target.value)}
                  className="w-full bg-yeikar-tertiary/30 border border-yeikar-secondary-light/10 rounded-xl p-2.5 text-sm focus:outline-none focus:border-yeikar-primary"
                />
              </div>
              <div>
                <label className="block text-xs font-bold text-yeikar-neutral/60 mb-1">Dirección de Entrega</label>
                <textarea
                  value={direccionEntrega}
                  onChange={(e) => setDireccionEntrega(e.target.value)}
                  rows={2}
                  className="w-full bg-yeikar-tertiary/30 border border-yeikar-secondary-light/10 rounded-xl p-2.5 text-sm focus:outline-none focus:border-yeikar-primary"
                />
              </div>
              <div>
                <label className="block text-xs font-bold text-yeikar-neutral/60 mb-1">Observaciones</label>
                <textarea
                  value={observaciones}
                  onChange={(e) => setObservaciones(e.target.value)}
                  placeholder="Detalles sobre horario de entrega, indicaciones de ruta..."
                  rows={2}
                  className="w-full bg-yeikar-tertiary/30 border border-yeikar-secondary-light/10 rounded-xl p-2.5 text-sm focus:outline-none focus:border-yeikar-primary"
                />
              </div>
              <div className="flex justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setAssigningEnvio(null)}
                  className="px-4 py-2 rounded-xl text-sm font-bold text-yeikar-neutral/60 hover:bg-yeikar-tertiary transition-colors"
                >
                  Cancelar
                </button>
                <button
                  type="submit"
                  className="bg-yeikar-primary text-yeikar-neutral px-4 py-2 rounded-xl text-sm font-bold shadow-sm hover:shadow transition-all"
                >
                  Despachar y Salir 🚛
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
      {/* Falla Modal */}
      {failingEnvio && (
        <div className="fixed inset-0 bg-yeikar-secondary/60 backdrop-blur-sm flex items-center justify-center p-4 z-50 animate-fade-in">
          <div className="bg-white rounded-3xl shadow-xl border border-yeikar-secondary-light/10 max-w-sm w-full p-6 space-y-4">
            <h3 className="text-xl font-headline font-black text-yeikar-secondary tracking-tight">
              Reportar Falla en Entrega #{failingEnvio.id}
            </h3>
            <form onSubmit={handleFallaSubmit} className="space-y-4">
              <div>
                <label className="block text-xs font-bold text-yeikar-neutral/60 mb-1">Motivo de Falla / Observación *</label>
                <textarea
                  value={fallaObservaciones}
                  onChange={(e) => setFallaObservaciones(e.target.value)}
                  placeholder="Describa el motivo (Ej: Cliente ausente, dirección incorrecta, daño en vía)..."
                  required
                  rows={3}
                  className="w-full bg-yeikar-tertiary/30 border border-yeikar-secondary-light/10 rounded-xl p-2.5 text-sm focus:outline-none focus:border-yeikar-primary"
                />
              </div>
              <div className="flex justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setFailingEnvio(null)}
                  className="px-4 py-2 rounded-xl text-sm font-bold text-yeikar-neutral/60 hover:bg-yeikar-tertiary transition-colors"
                >
                  Cancelar
                </button>
                <button
                  type="submit"
                  className="bg-red-500 hover:bg-red-600 text-white px-4 py-2 rounded-xl text-sm font-bold shadow-sm transition-all"
                >
                  Registrar Falla 
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
