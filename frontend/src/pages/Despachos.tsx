import React, { useEffect, useState } from 'react';
import { jsPDF } from 'jspdf';
import html2canvas from 'html2canvas';
import { envioService, Envio, EnvioUpdate } from '../services/envioService';
import { OrderDetail } from '../services/pedidoService';
import { getEmpleados } from '../services/empleadosService';
import { esperarImagenesCargadas } from '../utils/pdfImagenes';
import LocationTracker from '../components/LocationTracker';
import ConfirmDialog from '../components/ui/ConfirmDialog';
import { SearchSelect } from '../components/ui';
import { useToast } from '../context/ToastContext';
export default function Despachos() {
  const toast = useToast();  const [envios, setEnvios] = useState<Envio[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [activeTab, setActiveTab] = useState<'activos' | 'historicos'>('activos');
  // Modal / Assign Form state
  const [assigningEnvio, setAssigningEnvio] = useState<Envio | null>(null);
  const [selectedEmpleadoId, setSelectedEmpleadoId] = useState('');
  const [direccionEntrega, setDireccionEntrega] = useState('');
  const [guiaDespacho, setGuiaDespacho] = useState('');
  const [observaciones, setObservaciones] = useState('');
  // Fallido Form state
  const [failingEnvio, setFailingEnvio] = useState<Envio | null>(null);
  const [fallaObservaciones, setFallaObservaciones] = useState('');
  
  // Guía de Despacho PDF state
  const [selectedEnvioForGuia, setSelectedEnvioForGuia] = useState<Envio | null>(null);
  const [isGeneratingGuia, setIsGeneratingGuia] = useState(false);
  // Modal previo al PDF: tasa Bs, forma de pago, placas
  const [showGuiaModal, setShowGuiaModal] = useState<Envio | null>(null);
  const [ventaLinkedGuia, setVentaLinkedGuia] = useState<import('../services/ventaService').VentaDetalle | null>(null);
  const [tasaBsGuia, setTasaBsGuia] = useState('1');
  const [formaPagoGuia, setFormaPagoGuia] = useState('Crédito');
  const [placasGuia, setPlacasGuia] = useState('');
  const [loadingVenta, setLoadingVenta] = useState(false);
  const [entregandoId, setEntregandoId] = useState<number | null>(null);
  const [confirmEntregaId, setConfirmEntregaId] = useState<number | null>(null);
  const [confirmReprogramarId, setConfirmReprogramarId] = useState<number | null>(null);

  const handleOpenGuiaModal = async (envio: Envio) => {
    setShowGuiaModal(envio);
    setPlacasGuia('');
    setFormaPagoGuia('Crédito');
    setLoadingVenta(true);
    setVentaLinkedGuia(null);
    try {
      // Buscar la venta vinculada al pedido de este envío
      const { ventaService } = await import('../services/ventaService');
      const ventas = await ventaService.getAll();
      const ventaMatch = ventas.find(v => v.pedido_id === envio.pedido_id);
      if (ventaMatch) {
        const detalle = await ventaService.getById(ventaMatch.id);
        setVentaLinkedGuia(detalle);
        // Auto tasa según moneda de la venta
        if (detalle.moneda?.codigo === 'VES') setTasaBsGuia('1');
        else if (detalle.moneda?.codigo === 'USD') setTasaBsGuia('50');
        else if (detalle.moneda?.codigo === 'COP') setTasaBsGuia('0.0125');
        else if (detalle.moneda?.codigo === 'EUR') setTasaBsGuia('55');
        else setTasaBsGuia('1');
      } else {
        setTasaBsGuia('1');
      }
    } catch (e) {
      console.error('No se pudo cargar la venta vinculada:', e);
    } finally {
      setLoadingVenta(false);
    }
  };

  const handleConfirmGuiaPdf = () => {
    if (!showGuiaModal) return;
    setSelectedEnvioForGuia(showGuiaModal);
    setShowGuiaModal(null);
    setIsGeneratingGuia(true);
    setTimeout(async () => {
      const element = document.getElementById(`pdf-guia-container-${showGuiaModal.id}`);
      if (!element) { setIsGeneratingGuia(false); return; }
      try {
        // Las fotos de producto deben estar cargadas antes de capturar.
        await esperarImagenesCargadas(element);
        const html2canvas = (await import('html2canvas')).default;
        const { jsPDF } = await import('jspdf');
        const canvas = await html2canvas(element, { scale: 2, useCORS: true });
        const pdf = new jsPDF({ orientation: 'portrait', unit: 'mm', format: 'letter' });
        const pdfW = pdf.internal.pageSize.getWidth();
        const pdfH = pdf.internal.pageSize.getHeight();
        const totalH = (canvas.height * pdfW) / canvas.width;
        if (totalH <= pdfH) {
          pdf.addImage(canvas.toDataURL('image/jpeg', 0.98), 'JPEG', 0, 0, pdfW, totalH);
        } else {
          const pxPerMm = canvas.width / pdfW;
          const pageHpx = Math.floor(pdfH * pxPerMm);
          const totalPages = Math.ceil(canvas.height / pageHpx);
          for (let pg = 0; pg < totalPages; pg++) {
            const sliceY = pg * pageHpx;
            const slicePx = Math.min(pageHpx, canvas.height - sliceY);
            const sc = document.createElement('canvas');
            sc.width = canvas.width; sc.height = slicePx;
            const ctx = sc.getContext('2d');
            if (ctx) ctx.drawImage(canvas, 0, sliceY, canvas.width, slicePx, 0, 0, canvas.width, slicePx);
            if (pg > 0) pdf.addPage('letter', 'portrait');
            pdf.addImage(sc.toDataURL('image/jpeg', 0.98), 'JPEG', 0, 0, pdfW, (slicePx / canvas.width) * pdfW);
          }
        }
        pdf.save(`Guia_Despacho_Yeikar_${showGuiaModal.guia_despacho || showGuiaModal.id}.pdf`);
      } catch (err) {
        console.error('Error al generar la Guía de Despacho:', err);
        toast.error('Hubo un error al generar la Guía de Despacho en PDF.');
      } finally {
        setIsGeneratingGuia(false);
      }
    }, 150);
  };

  const handleGenerateGuiaPdf = (envio: Envio) => {
    handleOpenGuiaModal(envio);
  };
  const fetchEnvios = async () => {
    try {
      setLoading(true);
      // Activos = pendientes + en ruta; Históricos = entregados + fallidos.
      const estados = activeTab === 'activos' ? ['PREPARADO', 'EN_TRANSITO'] : ['ENTREGADO', 'FALLIDO'];
      const [a, b] = await Promise.all(estados.map((e) => envioService.getAll(search || undefined, e)));
      const data = [...a, ...b];
      setEnvios(data);
    } catch (error) {
      console.error('Error fetching delivery shipments:', error);
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => {
    fetchEnvios();
  }, [activeTab, search]);
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
      toast.success('¡Envío asignado y puesto en tránsito con éxito!');
      setAssigningEnvio(null);
      fetchEnvios();
    } catch (error) {
      console.error('Error dispatching shipment:', error);
      toast.error('Ocurrió un error al registrar el despacho.');
    }
  };
  const handleConfirmEntrega = (envioId: number) => {
    setConfirmEntregaId(envioId);
  };
  const ejecutarConfirmarEntrega = async () => {
    const envioId = confirmEntregaId;
    if (envioId === null || entregandoId !== null) return;
    setConfirmEntregaId(null);
    setEntregandoId(envioId);
    try {
      await envioService.updateEstado(envioId, 'ENTREGADO');
      toast.success('¡Envío marcado como ENTREGADO y Pedido actualizado!');
      fetchEnvios();
    } catch (error) {
      console.error('Error delivering shipment:', error);
      toast.error('Error al confirmar la entrega.');
    } finally {
      setEntregandoId(null);
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
      toast.success('Envío reportado como fallido.');
      setFailingEnvio(null);
      fetchEnvios();
    } catch (error) {
      console.error('Error failing shipment:', error);
      toast.error('Error al reportar la falla.');
    }
  };
  const handleReProgramar = (envioId: number) => {
    setConfirmReprogramarId(envioId);
  };
  const ejecutarReProgramar = async () => {
    const envioId = confirmReprogramarId;
    if (envioId === null) return;
    setConfirmReprogramarId(null);
    try {
      await envioService.update(envioId, {
        estado: 'PREPARADO',
        fecha_salida: null,
        fecha_entrega: null
      });
      toast.success('Envío re-programado con éxito.');
      fetchEnvios();
    } catch (error) {
      console.error('Error reprogramming shipment:', error);
      toast.error('Error al re-programar.');
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
          <h1 className="text-2xl sm:text-3xl font-black font-headline text-yeikar-secondary tracking-tight">
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
        {(['activos', 'historicos'] as const).map((tab) => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className={`px-5 py-3 text-sm font-headline font-bold border-b-2 transition-all ${
              activeTab === tab
                ? 'border-yeikar-primary text-yeikar-primary'
                : 'border-transparent text-yeikar-neutral/65 hover:text-yeikar-primary'
            }`}
          >
            {tab === 'activos' ? 'Activos (Pendientes + En ruta)' : 'Históricos (Entregados + Fallidos)'}
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
                        <span>• {det.tipo_item === 'INSUMO' ? det.material?.nombre || 'Insumo' : det.producto?.nombre || 'Producto'}</span>
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
                      {envio.empleado.nombre}
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
                <LocationTracker envioId={envio.id} estado={envio.estado} />
                {envio.observaciones && (
                  <p className="text-xs text-yeikar-neutral/60 bg-yellow-50/50 p-2 rounded border border-yellow-100 text-[11px]">
                    Obs: {envio.observaciones}
                  </p>
                )}
              </div>
              {/* Action Buttons */}
              <div className="mt-5 pt-3 border-t border-yeikar-secondary-light/5 flex flex-col gap-2">
                <button
                  onClick={() => { window.location.href = `/historial?tipo=envio&id=${envio.id}`; }}
                  className="w-full bg-yeikar-tertiary/60 hover:bg-yeikar-tertiary text-yeikar-secondary text-xs font-headline font-bold py-2 px-3 rounded-xl transition-all flex items-center justify-center gap-1.5"
                >
                  📂 Expediente completo
                </button>
                <div className="flex gap-2">
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
                        disabled={entregandoId !== null}
                        className="flex-1 bg-green-500 hover:bg-green-600 disabled:opacity-50 disabled:cursor-not-allowed text-white text-xs font-headline font-bold py-2 px-3 rounded-xl shadow-sm transition-colors"
                      >
                        {entregandoId === envio.id ? 'Confirmando...' : 'Confirmar Entrega'}
                      </button>
                      <button
                        onClick={() => handleOpenFalla(envio)}
                        className="bg-red-50 hover:bg-red-100 text-red-600 text-xs font-headline font-bold py-2 px-3 rounded-xl border border-red-200 transition-colors"
                      >
                        Falla
                      </button>
                    </>
                  )}
                  {envio.estado === 'FALLIDO' && (
                    <button
                      onClick={() => handleReProgramar(envio.id)}
                      className="flex-1 bg-amber-500 hover:bg-amber-600 text-white text-xs font-headline font-bold py-2 px-3 rounded-xl shadow-sm transition-colors"
                    >
                      Re-Programar Despacho
                    </button>
                  )}
                </div>
                <button
                  onClick={() => handleGenerateGuiaPdf(envio)}
                  disabled={isGeneratingGuia && selectedEnvioForGuia?.id === envio.id}
                  className="w-full bg-yeikar-secondary text-yeikar-tertiary hover:bg-yeikar-secondary-light text-xs font-headline font-bold py-2 px-3 rounded-xl transition-all flex items-center justify-center gap-1.5 shadow-sm disabled:opacity-50"
                >
                  <svg className="w-4 h-4 text-amber-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M17 17h2a2 2 0 002-2v-4a2 2 0 00-2-2H5a2 2 0 00-2 2v4a2 2 0 002 2h2m2 4h6a2 2 0 002-2v-4a2 2 0 00-2-2H9a2 2 0 00-2 2v4a2 2 0 002 2zm8-12V5a2 2 0 00-2-2H9a2 2 0 00-2 2v4h10z" />
                  </svg>
                  {isGeneratingGuia && selectedEnvioForGuia?.id === envio.id ? 'Generando Guía...' : 'Imprimir Guía de Despacho PDF'}
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
      {/* Assign Driver Modal */}
      {assigningEnvio && (
        <div className="fixed inset-0 bg-yeikar-secondary/60 backdrop-blur-sm flex items-center justify-center p-4 z-50 animate-fade-in">
          <div className="bg-white rounded-3xl shadow-xl border border-yeikar-secondary-light/10 max-w-md w-full p-4 sm:p-6 space-y-4">
            <h3 className="text-xl font-headline font-black text-yeikar-secondary tracking-tight">
              Asignar Envío para Pedido #{assigningEnvio.pedido_id}
            </h3>
            <p className="text-xs text-yeikar-neutral/60">
              Registra los datos del vehículo y conductor para poner la orden en ruta.
            </p>
            <form onSubmit={handleAssignSubmit} className="space-y-4">
              <div>
                <label className="block text-xs font-bold text-yeikar-neutral/60 mb-1">Chofer/Conductor *</label>
                <SearchSelect
                  value={selectedEmpleadoId}
                  onChange={(v) => setSelectedEmpleadoId(String(v))}
                  loadOptions={async (q) =>
                    (await getEmpleados({ buscar: q || undefined, limite: 20 }))
                      .filter((e) => e.activo)
                      .map((emp) => ({
                        value: emp.id,
                        label: `${emp.nombre} (${emp.cargo?.nombre || 'Empleado'})`,
                      }))
                  }
                  minChars={0}
                  placeholder="Selecciona Conductor..."
                />
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
                  Despachar y Salir 
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
      {/* Falla Modal */}
      {failingEnvio && (
        <div className="fixed inset-0 bg-yeikar-secondary/60 backdrop-blur-sm flex items-center justify-center p-4 z-50 animate-fade-in">
          <div className="bg-white rounded-3xl shadow-xl border border-yeikar-secondary-light/10 max-w-sm w-full p-4 sm:p-6 space-y-4">
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
      
      {/* ── Modal previo: Tasa Bs + Forma de Pago + Placas (antes de generar Guía PDF) ── */}
      {showGuiaModal && (
        <div className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center p-4 z-[60]">
          <div className="bg-white rounded-3xl shadow-2xl border border-yeikar-secondary-light/10 max-w-md w-full p-4 sm:p-6 space-y-5">
            <div>
              <h3 className="text-lg font-headline font-black text-yeikar-secondary tracking-tight">
                Configurar Guía de Despacho PDF
              </h3>
              <p className="text-xs text-yeikar-neutral/60 mt-1">
                Pedido #{showGuiaModal.pedido_id} · {showGuiaModal.pedido?.cliente?.nombre}
              </p>
            </div>

            {loadingVenta ? (
              <div className="flex items-center gap-2 text-sm text-yeikar-neutral/60 py-4 justify-center">
                <div className="w-5 h-5 border-2 border-yeikar-primary border-t-transparent rounded-full animate-spin" />
                Buscando factura vinculada...
              </div>
            ) : ventaLinkedGuia ? (
              <div className="bg-green-50 border border-green-200 rounded-xl p-3 text-xs space-y-1">
                <p className="font-bold text-green-800">Factura vinculada encontrada</p>
                <p className="text-green-700 font-mono">Factura #{ventaLinkedGuia.id} · {ventaLinkedGuia.moneda?.codigo} {Number(ventaLinkedGuia.total).toLocaleString('es-VE', { minimumFractionDigits: 2 })}</p>
              </div>
            ) : (
              <div className="bg-amber-50 border border-amber-200 rounded-xl p-3 text-xs">
                <p className="text-amber-800"> No se encontró factura vinculada para este pedido. Los montos en el PDF estarán vacíos.</p>
              </div>
            )}

            <div className="space-y-4">
              {/* Forma de Pago */}
              <div>
                <label className="block text-xs font-bold text-yeikar-neutral/60 mb-1.5">Forma de Pago (para el PDF)</label>
                <div className="grid grid-cols-2 gap-2">
                  {['Efectivo', 'Crédito', 'Débito', 'Transferencia', 'Zelle', 'Mixto'].map(fp => (
                    <button
                      key={fp}
                      onClick={() => setFormaPagoGuia(fp)}
                      className={`py-2 px-3 rounded-xl text-xs font-bold border transition-all ${
                        formaPagoGuia === fp
                          ? 'bg-yeikar-primary text-yeikar-neutral border-yeikar-primary shadow-sm'
                          : 'bg-white text-yeikar-neutral/70 border-yeikar-secondary-light/20 hover:border-yeikar-primary/40'
                      }`}
                    >
                      {fp}
                    </button>
                  ))}
                </div>
              </div>

              {/* Tasa de Cambio Bs. */}
              {ventaLinkedGuia && ventaLinkedGuia.moneda?.codigo !== 'VES' && (
                <div>
                  <label className="block text-xs font-bold text-yeikar-neutral/60 mb-1.5">
                    Tasa de Cambio Oficial Bs.
                    <span className="ml-2 font-normal text-yeikar-neutral/40">1 {ventaLinkedGuia.moneda?.codigo} = ? Bs.</span>
                  </label>
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-bold text-yeikar-neutral/50">1 {ventaLinkedGuia.moneda?.codigo} =</span>
                    <input
                      type="number"
                      step="any"
                      min="0"
                      value={tasaBsGuia}
                      onChange={(e) => setTasaBsGuia(e.target.value)}
                      className="flex-1 px-3 py-2 text-sm border border-yeikar-secondary-light/20 rounded-xl focus:outline-none focus:ring-2 focus:ring-yeikar-primary font-mono"
                      placeholder="Ej: 50.00"
                    />
                    <span className="text-sm font-bold text-yeikar-neutral/50">Bs.</span>
                  </div>
                  <p className="text-[10px] text-yeikar-neutral/40 mt-1">Esta tasa convierte los precios a Bolívares en el bloque fiscal del PDF.</p>
                </div>
              )}

              {/* Placas del vehículo */}
              <div>
                <label className="block text-xs font-bold text-yeikar-neutral/60 mb-1.5">Placas del vehículo (opcional)</label>
                <input
                  type="text"
                  value={placasGuia}
                  onChange={(e) => setPlacasGuia(e.target.value.toUpperCase())}
                  placeholder="Ej: AAW1 · AB123C"
                  className="w-full px-3 py-2 text-sm border border-yeikar-secondary-light/20 rounded-xl focus:outline-none focus:ring-2 focus:ring-yeikar-primary font-mono uppercase"
                />
              </div>
            </div>

            <div className="flex gap-2 pt-1">
              <button
                onClick={() => { setShowGuiaModal(null); setVentaLinkedGuia(null); }}
                className="flex-1 py-2.5 text-sm font-bold text-yeikar-neutral/60 border border-yeikar-secondary-light/20 rounded-xl hover:bg-yeikar-tertiary/20 transition-all"
              >
                Cancelar
              </button>
              <button
                onClick={handleConfirmGuiaPdf}
                className="flex-1 py-2.5 text-sm font-bold bg-yeikar-secondary text-yeikar-tertiary rounded-xl hover:bg-yeikar-secondary-light transition-all flex items-center justify-center gap-2"
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M17 17h2a2 2 0 002-2v-4a2 2 0 00-2-2H5a2 2 0 00-2 2v4a2 2 0 002 2h2m2 4h6a2 2 0 002-2v-4a2 2 0 00-2-2H9a2 2 0 00-2 2v4a2 2 0 002 2zm8-12V5a2 2 0 00-2-2H9a2 2 0 00-2 2v4h10z" />
                </svg>
                Generar PDF
              </button>
            </div>
          </div>
        </div>
      )}
      {/* ── Plantilla Oculta para PDF de Guía de Despacho (Estructura oficial Yeikar) ── */}
      {selectedEnvioForGuia && (() => {
        const tasaBs = parseFloat(tasaBsGuia) || 1;
        const venta = ventaLinkedGuia;
        const totalBs = venta ? Number(venta.total) * tasaBs : 0;
        const baseImponibleBs = totalBs / 1.16;
        const iva16Bs = totalBs - baseImponibleBs;
        const totalVentaBs = totalBs;
        const igtf3Bs = totalVentaBs * 0.03;
        const totalAPagarBs = totalVentaBs + igtf3Bs;
        return (
          <div className="fixed -left-[9999px] top-0 pointer-events-none z-[-100]">
            <div
              id={`pdf-guia-container-${selectedEnvioForGuia.id}`}
              className="bg-white text-stone-900 font-sans p-7 relative"
              style={{ width: '215.9mm', minHeight: '279.4mm', boxSizing: 'border-box' }}
            >
              {/* Marca de agua */}
              <div className="absolute inset-0 flex items-center justify-center pointer-events-none opacity-[0.03] select-none z-0">
                <img src="/logo-marca-de-agua.PNG" alt="" className="w-[400px] h-auto" />
              </div>

              <div className="relative z-10 flex flex-col justify-between min-h-[255mm]">
                <div>
                  {/* Encabezado */}
                  <div className="flex justify-between items-start pb-3 border-b-2 border-stone-800">
                    <div className="space-y-0.5 max-w-[60%]">
                      <img src="/Logo-yeikar.png" alt="Yeikar" className="h-10 object-contain mb-1" />
                      <h1 className="font-serif font-black text-stone-900 text-sm tracking-widest uppercase">Comercializadora Yeikar</h1>
                      <p className="text-[9px] font-bold text-stone-700">RIF. V-18969838-7 · Lilia Carolina Bautista (Propietaria)</p>
                      <p className="text-[8px] text-stone-600 leading-tight">Fabricación, Compra, Venta, Importación, Comercialización al Mayor y Detal de todo tipo de Muebles.</p>
                      <p className="text-[8px] text-stone-600"><strong>Dirección:</strong> Av. Intercomunal con Calle 16 Local N° 15-205 B. Simón Bolívar, Ureña, Edo. Táchira</p>
                      <p className="text-[8px] text-stone-600 font-mono"><strong>Tel:</strong> (0276) 7874095 · Cel: 0414-7393699 / 0414-7398817</p>
                      <p className="text-[8px] text-stone-600 font-mono"><strong>Instagram:</strong> @mueblesyeikar.fabricantes · <strong>Facebook:</strong> Muebles Yeikar</p>
                    </div>
                    {/* Recuadro Guía de Despacho */}
                    <div className="text-right border-2 border-stone-800 rounded-lg p-3 bg-stone-50/80 min-w-[175px] shadow-sm">
                      <div className="text-[8px] font-black text-red-700 uppercase tracking-widest">Guía de Despacho</div>
                      <div className="text-sm font-black text-red-800 font-mono tracking-widest mt-0.5">
                        N° {(selectedEnvioForGuia.guia_despacho || selectedEnvioForGuia.id.toString()).padStart(6, '0')}
                      </div>
                      <div className="text-[8px] font-mono text-stone-700 font-bold mt-1">FECHA DE EMISIÓN: {new Date().toLocaleDateString('es-ES')}</div>
                      <div className="text-[8px] font-mono text-stone-700 font-bold mt-0.5">N° DE CONTROL: 00 – {selectedEnvioForGuia.id.toString().padStart(6, '0')}</div>
                    </div>
                  </div>

                  {/* Datos del Destinatario — conforme al físico */}
                  <div className="border border-stone-300 rounded-sm mt-2 mb-1 text-[9px]">
                    <div className="grid grid-cols-3 border-b border-stone-200">
                      <div className="col-span-2 px-2 py-1 border-r border-stone-200">
                        <span className="font-bold text-stone-500 uppercase text-[7px] block">Nombre y Apellido o Razón Social</span>
                        <span className="font-extrabold text-stone-950">{selectedEnvioForGuia.pedido?.cliente?.nombre ?? '—'}</span>
                      </div>
                      <div className="px-2 py-1">
                        <span className="font-bold text-stone-500 uppercase text-[7px] block">Teléfono</span>
                        <span className="font-bold text-stone-900 font-mono">{selectedEnvioForGuia.pedido?.cliente?.telefono || '—'}</span>
                      </div>
                    </div>
                    <div className="grid grid-cols-2 border-b border-stone-200">
                      <div className="px-2 py-1 border-r border-stone-200">
                        <span className="font-bold text-stone-500 uppercase text-[7px] block">N° de Registro Único de Información Fiscal (RIF) / C.I.</span>
                        <span className="font-bold text-stone-900 font-mono">{selectedEnvioForGuia.pedido?.cliente?.cedula || '—'}</span>
                      </div>
                      <div className="px-2 py-1">
                        <span className="font-bold text-stone-500 uppercase text-[7px] block">Domicilio Fiscal</span>
                        <span className="font-semibold text-stone-900 italic">{selectedEnvioForGuia.pedido?.cliente?.direccion || '—'}</span>
                      </div>
                    </div>
                    <div className="grid grid-cols-3 border-b border-stone-200">
                      <div className="px-2 py-1 border-r border-stone-200">
                        <span className="font-bold text-stone-500 uppercase text-[7px] block">FACTURA N°</span>
                        <span className="font-black text-red-700 font-mono text-sm">{venta ? venta.id.toString().padStart(6, '0') : '—'}</span>
                      </div>
                      <div className="px-2 py-1 border-r border-stone-200">
                        <span className="font-bold text-stone-500 uppercase text-[7px] block">Forma de Pago</span>
                        <span className="font-bold text-stone-900">{formaPagoGuia}</span>
                      </div>
                      <div className="px-2 py-1">
                        <span className="font-bold text-stone-500 uppercase text-[7px] block">Domicilio / Dirección de Entrega</span>
                        <span className="font-semibold text-stone-900 italic text-[8px]">{selectedEnvioForGuia.direccion_entrega || selectedEnvioForGuia.pedido?.cliente?.direccion || '—'}</span>
                      </div>
                    </div>
                  </div>

                  {/* Tabla de Productos con Precio Unitario y Monto */}
                  <div className="mb-2 border border-stone-300 overflow-hidden">
                    <table className="w-full border-collapse text-[9px]">
                      <thead>
                        <tr className="bg-stone-800 text-stone-100 uppercase text-[7.5px] tracking-wider">
                          <th className="px-2 py-1.5 text-center w-[10%] border-r border-stone-600">Cant.</th>
                          <th className="px-2 py-1.5 text-left border-r border-stone-600">Concepto o Descripción</th>
                          <th className="px-2 py-1.5 text-right w-[20%] border-r border-stone-600">Precio Unitario</th>
                          <th className="px-2 py-1.5 text-right w-[20%]">Monto</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-stone-200">
                        {selectedEnvioForGuia.pedido?.detalles?.map((det: OrderDetail, i: number) => {
                          // Buscar precio en la venta: INSUMO se empareja por
                          // material_id; producto, por producto_id (nunca null==null).
                          const detVenta = venta?.detalles?.find(dv =>
                            det.tipo_item === 'INSUMO'
                              ? dv.material_id != null && dv.material_id === det.material_id
                              : dv.producto_id != null && dv.producto_id === det.producto_id
                          );
                          const precio = detVenta ? Number(detVenta.precio) : 0;
                          const monto = precio * det.cantidad;
                          const foto = det.producto?.fotos?.[0]?.url ?? null;
                          const nombreDet = det.tipo_item === 'INSUMO'
                            ? det.material?.nombre || 'Insumo'
                            : det.producto?.nombre || 'Mueble Yeikar';
                          return (
                            <tr key={det.id || i} className={i % 2 === 0 ? 'bg-white' : 'bg-stone-50/60'}>
                              <td className="px-2 py-1.5 text-center font-mono font-bold border-r border-stone-200">{det.cantidad}</td>
                              <td className="px-2 py-1.5 font-bold border-r border-stone-200">
                                <div className="flex items-center gap-2">
                                  {foto && (
                                    <img
                                      src={foto}
                                      alt={det.producto?.nombre ?? ''}
                                      className="h-14 w-14 rounded object-cover border border-stone-300 shrink-0"
                                    />
                                  )}
                                  <span>
                                    {nombreDet}
                                    {det.tipo_item !== 'INSUMO' && det.ancho && det.largo ? <span className="font-normal text-stone-500"> ({det.ancho}×{det.largo}m)</span> : ''}
                                  </span>
                                </div>
                                {det.observaciones && <span className="block text-[7.5px] text-stone-400 font-normal italic">{det.observaciones}</span>}
                              </td>
                              <td className="px-2 py-1.5 text-right font-mono border-r border-stone-200">
                                {venta ? `${venta.moneda?.simbolo || ''}${precio.toLocaleString('es-VE', { minimumFractionDigits: 2 })}` : '—'}
                              </td>
                              <td className="px-2 py-1.5 text-right font-mono font-bold">
                                {venta ? `${venta.moneda?.simbolo || ''}${monto.toLocaleString('es-VE', { minimumFractionDigits: 2 })}` : '—'}
                              </td>
                            </tr>
                          );
                        })}
                        {/* Filas vacías para dar aspecto de formulario */}
                        {Array.from({ length: Math.max(0, 5 - (selectedEnvioForGuia.pedido?.detalles?.length || 0)) }).map((_, i) => (
                          <tr key={`empty-${i}`} className={((selectedEnvioForGuia.pedido?.detalles?.length || 0) + i) % 2 === 0 ? 'bg-white' : 'bg-stone-50/30'}>
                            <td className="px-2 py-2.5 border-r border-stone-200">&nbsp;</td>
                            <td className="px-2 py-2.5 border-r border-stone-200">&nbsp;</td>
                            <td className="px-2 py-2.5 border-r border-stone-200">&nbsp;</td>
                            <td className="px-2 py-2.5">&nbsp;</td>
                          </tr>
                        ))}
                      </tbody>
                      {/* Fila TOTAL */}
                      <tfoot>
                        <tr className="bg-stone-100 border-t-2 border-stone-800">
                          <td colSpan={3} className="px-2 py-1.5 text-right font-serif font-black text-stone-900 uppercase tracking-widest text-[8.5px] border-r border-stone-300">TOTAL</td>
                          <td className="px-2 py-1.5 text-right font-mono font-black text-stone-950">
                            {venta ? `${venta.moneda?.simbolo || ''}${Number(venta.total).toLocaleString('es-VE', { minimumFractionDigits: 2 })}` : '—'}
                          </td>
                        </tr>
                      </tfoot>
                    </table>
                  </div>
                </div>

                {/* Sección Inferior: Transporte + Desglose Fiscal + Firmas */}
                <div>
                  {/* Transporte — conforme al físico */}
                  <div className="border border-stone-300 text-[8.5px] font-mono mb-2">
                    <div className="grid grid-cols-3 border-b border-stone-200">
                      <div className="px-2 py-1 border-r border-stone-200">
                        <span className="font-bold text-stone-500 uppercase text-[7px] block">Transportado en:</span>
                        <span className="font-bold text-stone-900">Camión / Suburban Yeikar</span>
                      </div>
                      <div className="px-2 py-1 border-r border-stone-200">
                        <span className="font-bold text-stone-500 uppercase text-[7px] block">Conductor:</span>
                        <span className="font-bold text-stone-900">
                          {selectedEnvioForGuia.empleado
                            ? `${selectedEnvioForGuia.empleado.nombre}`
                            : 'Por Asignar'}
                        </span>
                      </div>
                      <div className="px-2 py-1">
                        <span className="font-bold text-stone-500 uppercase text-[7px] block">C.I.:</span>
                        <span className="font-bold text-stone-900">
                          {selectedEnvioForGuia.empleado?.cedula || '—'}
                        </span>
                      </div>
                    </div>
                    <div className="px-2 py-1">
                      <span className="font-bold text-stone-500 uppercase text-[7px]">Placas N°: </span>
                      <span className="font-bold text-stone-900">{placasGuia || 'S/N'}</span>
                    </div>
                  </div>

                  {/* Pie: Leyenda Legal (izq) + Desglose Fiscal SENIAT (der) */}
                  <div className="grid grid-cols-2 gap-3 mb-3">
                    <div className="text-[7.5px] text-stone-600 space-y-0.5">
                      <p className="font-bold text-stone-800 uppercase tracking-wider">Esta Guía de Despacho va sin enmienda ni tachadura.</p>
                      <p className="italic">ORIGINAL · Documento legal habilitado para amparar el traslado de bienes y mercancías Comercializadora Yeikar.</p>
                      {venta && venta.moneda?.codigo !== 'VES' && (
                        <p className="text-[7px] text-stone-500 font-mono mt-1">Tasa de Cambio: 1 {venta.moneda?.codigo} = {parseFloat(tasaBsGuia).toLocaleString('es-VE')} Bs.</p>
                      )}
                    </div>

                    {/* Bloque Fiscal SENIAT igual que en la Factura */}
                    <div className="border border-stone-400 rounded-sm overflow-hidden font-mono text-[8px]">
                      <div className="bg-stone-900 text-stone-100 px-2 py-0.5 font-serif font-bold uppercase tracking-wider text-[7px] flex justify-between">
                        <span>Resumen Fiscal</span>
                        <span className="text-[6.5px] text-amber-300">Valores en Bs.</span>
                      </div>
                      <div className="p-2 space-y-0.5 bg-stone-50">
                        <div className="flex justify-between text-stone-700">
                          <span>Monto Total Base Imponible al Valor Agregado % Bs:</span>
                          <span className="font-bold">{baseImponibleBs > 0 ? baseImponibleBs.toLocaleString('es-VE', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : '—'}</span>
                        </div>
                        <div className="flex justify-between text-stone-700">
                          <span>Monto Total Impuesto al Valor Agregado — Alícuota 16% Bs:</span>
                          <span className="font-bold">{iva16Bs > 0 ? iva16Bs.toLocaleString('es-VE', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : '—'}</span>
                        </div>
                        <div className="flex justify-between text-stone-800 font-bold border-t border-stone-300 pt-0.5">
                          <span>Monto Total Venta Bienes / Servicios Bs:</span>
                          <span>{totalVentaBs > 0 ? totalVentaBs.toLocaleString('es-VE', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : '—'}</span>
                        </div>
                        <div className="flex justify-between text-stone-700">
                          <span>Monto Total Base Imponible IGTF / IGTF 3% Bs:</span>
                          <span className="font-bold">{igtf3Bs > 0 ? igtf3Bs.toLocaleString('es-VE', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : '—'}</span>
                        </div>
                      </div>
                      <div className="bg-amber-100 border-t-2 border-stone-800 px-2 py-1 flex justify-between items-center">
                        <span className="font-serif font-black text-stone-950 uppercase text-[7.5px] tracking-wider">TOTAL A PAGAR</span>
                        <span className="font-black text-amber-950 font-mono">
                          Bs. {totalAPagarBs > 0 ? totalAPagarBs.toLocaleString('es-VE', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : '—'}
                        </span>
                      </div>
                    </div>
                  </div>

                  {/* Firmas */}
                  <div className="grid grid-cols-3 gap-6 pt-2 border-t border-stone-300">
                    <div className="text-center">
                      <div className="w-28 border-t border-stone-400 mx-auto mb-1" />
                      <div className="text-[7.5px] font-serif font-bold uppercase tracking-wider text-stone-800">FIRMA DEL CONDUCTOR</div>
                      <div className="text-[7px] text-stone-500">Transportista</div>
                    </div>
                    <div className="text-center">
                      <div className="w-28 border-t border-stone-400 mx-auto mb-1" />
                      <div className="text-[7.5px] font-serif font-bold uppercase tracking-wider text-stone-800">CLIENTE / CONFORME</div>
                      <div className="text-[7px] text-stone-500">Recibido Conforme</div>
                    </div>
                    <div className="text-center">
                      <div className="w-28 border-t border-stone-400 mx-auto mb-1" />
                      <div className="text-[7.5px] font-serif font-bold uppercase tracking-wider text-stone-800">COMERCIALIZADORA YEIKAR</div>
                      <div className="text-[7px] text-stone-500">Firma del Emisor</div>
                    </div>
                  </div>

                  {/* Sello Original */}
                  <div className="text-right mt-1">
                    <span className="text-[9px] font-black text-red-700 border border-red-400 px-2 py-0.5 rounded font-serif uppercase tracking-widest">Original</span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        );
      })()}
      <ConfirmDialog
        open={confirmEntregaId !== null}
        title="Confirmar entrega"
        message="¿Confirmar que el pedido ha sido entregado exitosamente al cliente? El envío pasará a ENTREGADO y el pedido se actualizará."
        confirmLabel="Sí, entregado"
        danger={false}
        onConfirm={ejecutarConfirmarEntrega}
        onCancel={() => setConfirmEntregaId(null)}
      />
      <ConfirmDialog
        open={confirmReprogramarId !== null}
        title="Re-programar despacho"
        message="¿Desea re-programar este despacho? Volverá al estado PENDIENTE de asignación."
        confirmLabel="Sí, re-programar"
        danger={false}
        onConfirm={ejecutarReProgramar}
        onCancel={() => setConfirmReprogramarId(null)}
      />
    </div>
  );
}
