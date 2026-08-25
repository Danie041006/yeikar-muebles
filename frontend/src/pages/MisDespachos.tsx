import React, { useEffect, useState } from 'react';
import { MapPin, Phone, RefreshCw, Truck } from 'lucide-react';
import { envioService, EnvioReparto } from '../services/envioService';
import LocationTracker from '../components/LocationTracker';
import ConfirmDialog from '../components/ui/ConfirmDialog';
import { useToast } from '../context/ToastContext';
import { useAuth } from '../context/AuthContext';

type Tab = 'en_ruta' | 'pendientes' | 'historicos';

export default function MisDespachos() {
  const toast = useToast();
  const { user } = useAuth();
  const [envios, setEnvios] = useState<EnvioReparto[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [activeTab, setActiveTab] = useState<Tab>('en_ruta');
  const [salirId, setSalirId] = useState<number | null>(null);
  const [entregandoId, setEntregandoId] = useState<number | null>(null);
  const [confirmEntregaId, setConfirmEntregaId] = useState<number | null>(null);
  const [failingEnvio, setFailingEnvio] = useState<EnvioReparto | null>(null);
  const [fallaObservaciones, setFallaObservaciones] = useState('');

  const fetchEnvios = async () => {
    try {
      setLoading(true);
      if (activeTab === 'historicos') {
        const [entregados, fallidos] = await Promise.all([
          envioService.getMisAsignaciones('ENTREGADO'),
          envioService.getMisAsignaciones('FALLIDO'),
        ]);
        setEnvios([...entregados, ...fallidos]);
      } else {
        const estado = activeTab === 'en_ruta' ? 'EN_TRANSITO' : 'PREPARADO';
        const data = await envioService.getMisAsignaciones(estado);
        setEnvios(data);
      }
    } catch (error) {
      console.error('Error cargando mis despachos:', error);
      toast.error('No se pudieron cargar tus despachos.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchEnvios();
  }, [activeTab]);

  const handleRefresh = async () => {
    setRefreshing(true);
    await fetchEnvios();
    setRefreshing(false);
  };

  const ejecutarSalirRuta = async () => {
    if (salirId === null) return;
    setSalirId(null);
    try {
      await envioService.updateEstado(salirId, 'EN_TRANSITO');
      toast.success('Despacho en ruta. ¡Buen viaje!');
      fetchEnvios();
    } catch (error) {
      console.error('Error al salir en ruta:', error);
      toast.error('No se pudo iniciar el recorrido.');
    }
  };

  const ejecutarConfirmarEntrega = async () => {
    if (confirmEntregaId === null || entregandoId !== null) return;
    setConfirmEntregaId(null);
    setEntregandoId(confirmEntregaId);
    try {
      await envioService.updateEstado(confirmEntregaId, 'ENTREGADO');
      toast.success('¡Entrega confirmada!');
      fetchEnvios();
    } catch (error) {
      console.error('Error confirmando entrega:', error);
      toast.error('No se pudo confirmar la entrega.');
    } finally {
      setEntregandoId(null);
    }
  };

  const handleFallaSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!failingEnvio) return;
    try {
      await envioService.update(failingEnvio.id, {
        estado: 'FALLIDO',
        observaciones: fallaObservaciones || 'La entrega falló en ruta.',
      });
      toast.success('Falla reportada. La administración la revisará.');
      setFailingEnvio(null);
      fetchEnvios();
    } catch (error) {
      console.error('Error reportando falla:', error);
      toast.error('No se pudo reportar la falla.');
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

  const tabLabel = (tab: Tab) =>
    tab === 'en_ruta' ? 'En ruta' : tab === 'pendientes' ? 'Pendientes' : 'Entregados / Fallidos';

  const tabs: Tab[] = ['en_ruta', 'pendientes', 'historicos'];

  return (
    <div className="space-y-6">
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
        <div>
          <h1 className="text-3xl font-black font-headline text-yeikar-secondary tracking-tight">
            Mis Despachos
          </h1>
          <p className="text-yeikar-neutral/60 mt-1 text-sm font-body">
            {user?.nombre_usuario
              ? `Hola ${user.nombre_usuario}, estos son tus repartos asignados.`
              : 'Tus repartos asignados para entregar.'}
          </p>
        </div>
        <button
          type="button"
          onClick={handleRefresh}
          disabled={refreshing}
          className="inline-flex items-center justify-center gap-2 rounded-xl border border-yeikar-secondary-light/10 bg-white px-4 py-2.5 text-xs font-bold text-yeikar-secondary shadow-sm transition-colors hover:border-yeikar-primary/40 disabled:opacity-50"
        >
          <RefreshCw className={`h-3.5 w-3.5 ${refreshing ? 'animate-spin' : ''}`} />
          Actualizar
        </button>
      </div>

      <div className="flex gap-2 border-b border-yeikar-secondary-light/10 pb-px flex-wrap">
        {tabs.map((tab) => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className={`px-5 py-3 text-sm font-headline font-bold border-b-2 transition-all ${
              activeTab === tab
                ? 'border-yeikar-primary text-yeikar-primary'
                : 'border-transparent text-yeikar-neutral/65 hover:text-yeikar-primary'
            }`}
          >
            {tabLabel(tab)}
          </button>
        ))}
      </div>

      {loading ? (
        <div className="flex flex-col items-center justify-center py-20 space-y-4">
          <div className="w-10 h-10 border-4 border-yeikar-primary border-t-transparent rounded-full animate-spin"></div>
          <p className="text-sm font-mono text-yeikar-neutral/60">Cargando tus despachos...</p>
        </div>
      ) : envios.length === 0 ? (
        <div className="bg-white border border-yeikar-secondary-light/10 rounded-2xl p-12 text-center text-yeikar-neutral/40">
          <Truck className="w-12 h-12 mx-auto text-yeikar-neutral/20 mb-3" strokeWidth={1.5} />
          <p className="text-sm font-medium">No tienes despachos en esta categoría.</p>
          <p className="text-xs mt-1 text-yeikar-neutral/40">Cuando te asignen un reparto aparecerá aquí.</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {envios.map((envio) => (
            <div
              key={envio.id}
              className="bg-white border border-yeikar-secondary-light/10 rounded-2xl p-5 shadow-sm hover:shadow-md transition-all relative overflow-hidden flex flex-col justify-between"
            >
              <div className={`absolute top-0 bottom-0 left-0 w-1.5 ${
                envio.estado === 'PREPARADO' ? 'bg-blue-400' :
                envio.estado === 'EN_TRANSITO' ? 'bg-amber-400 animate-pulse' :
                envio.estado === 'ENTREGADO' ? 'bg-green-400' : 'bg-red-400'
              }`} />
              <div className="space-y-4 pl-2">
                <div className="flex items-center justify-between">
                  <span className="text-[10px] font-mono font-black text-yeikar-neutral/40">
                    DESPACHO #{envio.id} (PEDIDO #{envio.pedido_id})
                  </span>
                  <span className={`text-[10px] font-black font-headline px-2 py-0.5 rounded-full border ${getStatusBadgeClass(envio.estado)}`}>
                    {envio.estado}
                  </span>
                </div>

                <div className="flex items-start justify-between gap-2">
                  <div>
                    <h3 className="font-headline font-bold text-yeikar-secondary text-base">
                      {envio.pedido?.cliente?.nombre || 'Cliente no registrado'}
                    </h3>
                    <p className="text-xs text-yeikar-neutral/50 font-mono mt-0.5">
                      {envio.pedido?.cliente?.ciudad || ''}
                    </p>
                  </div>
                  {envio.pedido?.cliente?.telefono && (
                    <a
                      href={`tel:${envio.pedido.cliente.telefono}`}
                      className="inline-flex items-center gap-1.5 rounded-xl bg-yeikar-primary/10 border border-yeikar-primary/25 px-3 py-2 text-xs font-bold text-yeikar-primary-dark hover:bg-yeikar-primary/20 transition-colors"
                      aria-label={`Llamar a ${envio.pedido.cliente.nombre}`}
                    >
                      <Phone className="h-3.5 w-3.5" />
                      Llamar
                    </a>
                  )}
                </div>

                <div className="bg-yeikar-tertiary/20 p-3 rounded-xl border border-yeikar-secondary-light/5">
                  <span className="text-[10px] font-black uppercase text-yeikar-neutral/45 block mb-1">
                    Muebles a Entregar
                  </span>
                  <div className="space-y-1.5">
                    {envio.pedido?.detalles?.map((det) => (
                      <div key={det.id} className="text-xs text-yeikar-secondary/85">
                        <div className="flex justify-between">
                          <span className="font-medium">• {det.producto?.nombre || 'Producto'}</span>
                          <span className="font-mono font-bold">x{det.cantidad}</span>
                        </div>
                        {(det.ancho || det.largo) && (
                          <p className="pl-3 text-[11px] text-yeikar-neutral/50 font-mono">
                            {det.ancho && det.largo ? `${det.ancho}×${det.largo}m` : det.ancho ? `Ancho ${det.ancho}m` : `Largo ${det.largo}m`}
                            {det.color ? ` · ${det.color}` : ''}
                            {det.acabado ? ` · ${det.acabado}` : ''}
                          </p>
                        )}
                        {det.observaciones && (
                          <p className="pl-3 text-[11px] text-yeikar-neutral/45 italic">{det.observaciones}</p>
                        )}
                      </div>
                    ))}
                  </div>
                </div>

                <div className="text-xs text-yeikar-secondary space-y-1">
                  <span className="text-[10px] font-black uppercase text-yeikar-neutral/45 block flex items-center gap-1">
                    <MapPin className="h-3 w-3" /> Dirección de Entrega
                  </span>
                  <p className="italic bg-gray-50 p-2 rounded-lg border border-gray-100 text-yeikar-neutral/80">
                    {envio.direccion_entrega || envio.pedido?.cliente?.direccion || 'No especificada'}
                  </p>
                </div>

                {envio.guia_despacho && (
                  <div className="text-xs text-yeikar-neutral/70 font-mono">
                    Guía de Despacho: <span className="font-bold text-yeikar-secondary">#{envio.guia_despacho}</span>
                  </div>
                )}

                {envio.fecha_salida && (
                  <div className="text-[10px] text-yeikar-neutral/40 font-mono">
                    Salida: {new Date(envio.fecha_salida).toLocaleString('es-CO')}
                  </div>
                )}
                {envio.fecha_entrega && (
                  <div className="text-[10px] text-yeikar-neutral/40 font-mono">
                    Entregado: {new Date(envio.fecha_entrega).toLocaleString('es-CO')}
                  </div>
                )}

                <LocationTracker envioId={envio.id} estado={envio.estado} />

                {envio.observaciones && (
                  <p className="text-xs text-yeikar-neutral/60 bg-yellow-50/50 p-2 rounded border border-yellow-100">
                    Notas: {envio.observaciones}
                  </p>
                )}
              </div>

              <div className="mt-5 pt-3 border-t border-yeikar-secondary-light/5 flex flex-col gap-2">
                {envio.estado === 'PREPARADO' && (
                  <button
                    onClick={() => setSalirId(envio.id)}
                    className="w-full bg-yeikar-primary hover:bg-yeikar-primary-light text-yeikar-neutral text-sm font-headline font-bold py-2.5 px-3 rounded-xl shadow-sm transition-colors"
                  >
                    Salir en ruta
                  </button>
                )}
                {envio.estado === 'EN_TRANSITO' && (
                  <div className="flex gap-2">
                    <button
                      onClick={() => setConfirmEntregaId(envio.id)}
                      disabled={entregandoId !== null}
                      className="flex-1 bg-green-500 hover:bg-green-600 disabled:opacity-50 disabled:cursor-not-allowed text-white text-sm font-headline font-bold py-2.5 px-3 rounded-xl shadow-sm transition-colors"
                    >
                      {entregandoId === envio.id ? 'Confirmando...' : 'Confirmar entrega'}
                    </button>
                    <button
                      onClick={() => { setFailingEnvio(envio); setFallaObservaciones(''); }}
                      className="bg-red-50 hover:bg-red-100 text-red-600 text-sm font-headline font-bold py-2.5 px-3 rounded-xl border border-red-200 transition-colors"
                    >
                      Falla
                    </button>
                  </div>
                )}
                {envio.estado === 'FALLIDO' && (
                  <p className="text-xs text-center text-yeikar-neutral/50 bg-red-50/60 border border-red-100 rounded-xl py-2.5">
                    Entrega reportada como fallida. La administración reprogramará el despacho.
                  </p>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      <ConfirmDialog
        open={salirId !== null}
        title="Salir en ruta"
        message="¿Confirmas que inicias el recorrido de este despacho? Activa el monitoreo para que la administración vea tu ubicación."
        confirmLabel="Sí, en ruta"
        danger={false}
        onConfirm={ejecutarSalirRuta}
        onCancel={() => setSalirId(null)}
      />
      <ConfirmDialog
        open={confirmEntregaId !== null}
        title="Confirmar entrega"
        message="¿Confirmas que entregaste el pedido al cliente? El despacho pasará a ENTREGADO."
        confirmLabel="Sí, entregado"
        danger={false}
        onConfirm={ejecutarConfirmarEntrega}
        onCancel={() => setConfirmEntregaId(null)}
      />

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
