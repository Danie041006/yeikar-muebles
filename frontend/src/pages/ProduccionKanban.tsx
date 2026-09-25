import React, { useEffect, useState, useCallback } from 'react';
import { Link } from 'react-router-dom';
import { produccionService, OrdenProduccion, EtapaProduccion, Area, ReferenciaReceta, CostosEnVivoOrden } from '../services/produccionService';
import { inventarioService, SobranteLamina } from '../services/inventarioService';
import api from '../services/api';
import ConfirmDialog from '../components/ui/ConfirmDialog';
import { SearchSelect } from '../components/ui';
import DocumentoHojaTrabajo from '../components/Expediente/DocumentoHojaTrabajo';
import EtapaModal from '../components/Produccion/EtapaModal';
import { TRANSICIONES_ETAPA, esOrdenExhibicion, type Empleado, type Material } from '../components/Produccion/tipos';
import { useToast } from '../context/ToastContext';

// (Empleado, Material, TRANSICIONES_ETAPA, fmt y esOrdenExhibicion viven en
//  components/Produccion/tipos.ts, compartidos con el EtapaModal.)

// Orden del pipeline de producción: las columnas del kanban siguen el flujo
// real del taller, no el orden de creación de las áreas en la base de datos.
const ORDEN_PIPELINE = ['Ebanistería', 'Preparación', 'Pintura', 'Tapicería', 'Vidriería', 'Terminación'];

// Kanban column component
interface ColumnProps {
  area: Area;
  stages: EtapaProduccion[];
  onCardClick: (stage: EtapaProduccion) => void;
  onStatusChange: (stageId: number, newStatus: string) => void;
  onPassToArea: (stage: EtapaProduccion) => void;
  updatingStageId: number | null;
}

function KanbanColumn({ area, stages, onCardClick, onStatusChange, onPassToArea, updatingStageId }: ColumnProps) {
  return (
    <div
      className="flex flex-col min-h-[500px] w-[85vw] max-w-xs sm:max-w-none sm:w-72 snap-start bg-yeikar-tertiary/40 border border-yeikar-secondary-light/10 rounded-2xl p-3 sm:p-4 shadow-sm"
    >
      {/* Column Header */}
      <div className="flex items-center justify-between mb-4 border-b border-yeikar-secondary-light/5 pb-2">
        <h3 className="font-headline font-black text-yeikar-secondary tracking-tight">
          {area.nombre}
        </h3>
        <span className="bg-yeikar-secondary/10 text-yeikar-secondary text-xs font-bold font-mono px-2.5 py-0.5 rounded-full">
          {stages.length}
        </span>
      </div>

      {/* Card List */}
      <div className="flex-1 space-y-3 overflow-y-auto max-h-[600px] pr-1">
        {stages.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-32 border border-dashed border-yeikar-secondary-light/10 rounded-xl p-4 text-center text-xs text-yeikar-neutral/40">
            <span>No hay etapas en esta área</span>
          </div>
        ) : (
          stages.map((stage) => (
            <KanbanCard
              key={stage.id}
              stage={stage}
              onClick={() => onCardClick(stage)}
              onStatusChange={onStatusChange}
              onPassToArea={onPassToArea}
              statusUpdating={updatingStageId === stage.id}
            />
          ))
        )}
      </div>
    </div>
  );
}

// Kanban card component
interface CardProps {
  stage: EtapaProduccion;
  onClick: () => void;
  onStatusChange: (stageId: number, newStatus: string) => void;
  onPassToArea: (stage: EtapaProduccion) => void;
  statusUpdating?: boolean;
}

function KanbanCard({ stage, onClick, onStatusChange, onPassToArea, statusUpdating = false }: CardProps) {
  const statusColors = {
    ASIGNADA: 'bg-blue-50 text-blue-700 border-blue-200',
    EN_PROCESO: 'bg-amber-50 text-amber-700 border-amber-200 animate-pulse',
    PAUSADA: 'bg-red-50 text-red-700 border-red-200',
    COMPLETADA: 'bg-green-50 text-green-700 border-green-200',
  };

  return (
    <div
      className={`border rounded-xl p-4 shadow-sm hover:shadow-md transition-shadow cursor-default group relative overflow-hidden ${stage.estado === 'COMPLETADA' ? 'bg-gray-50 border-gray-200 opacity-75' : 'bg-white border-yeikar-secondary-light/10'}`}
    >
      {/* Top accent tag based on status */}
      <div
        className={`absolute top-0 left-0 right-0 h-1 ${
          stage.estado === 'EN_PROCESO'
            ? 'bg-amber-400'
            : stage.estado === 'PAUSADA'
            ? 'bg-red-400'
            : stage.estado === 'COMPLETADA'
            ? 'bg-green-400'
            : 'bg-blue-400'
        }`}
      />

      <div className="flex items-start justify-between gap-2 mb-2">
        <span className="text-[10px] font-mono font-bold text-yeikar-neutral/40">
          ORDEN #{stage.orden_produccion_id}
        </span>
        
        {/* Status selector: solo transiciones legales (la máquina de estados
            del backend rechaza el resto; antes se ofrecían las 4 siempre y el
            400 fallaba en silencio) */}
        <select
          value={stage.estado}
          disabled={statusUpdating || TRANSICIONES_ETAPA[stage.estado]?.length === 0}
          aria-label={`Estado de la etapa ${stage.id}`}
          onChange={(e) => {
            e.stopPropagation();
            onStatusChange(stage.id, e.target.value);
          }}
          className={`text-[10px] font-bold px-2 py-0.5 rounded border disabled:opacity-50 disabled:cursor-not-allowed ${
            statusColors[stage.estado]
          } focus:outline-none focus:ring-1 focus:ring-yeikar-primary cursor-pointer`}
        >
          {[stage.estado, ...(TRANSICIONES_ETAPA[stage.estado] || [])].map((st) => (
            <option key={st} value={st}>
              {st.replace('_', ' ')}
            </option>
          ))}
        </select>
      </div>

      {/* Client Name & Product Name */}
      <div onClick={onClick} className="cursor-pointer space-y-1.5">
        {stage.orden?.detalle_pedido?.pedido?.cliente?.nombre && (
          <div className="text-[11px] font-bold text-yeikar-primary bg-yeikar-primary/10 px-2 py-0.5 rounded-md w-fit flex items-center gap-1">
            <svg className="w-3 h-3 text-yeikar-primary" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
            </svg>
            <span className="truncate max-w-[180px]">
              {stage.orden.detalle_pedido.pedido.cliente.nombre}
            </span>
          </div>
        )}
        {!stage.orden?.detalle_pedido && (
          <div className="text-[11px] font-bold text-yeikar-primary-dark bg-yeikar-primary/15 px-2 py-0.5 rounded-md w-fit flex items-center gap-1">
            <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 3l14 0 0 18-10-4-4 4z" />
            </svg>
            <span className="truncate max-w-[180px]">
              {esOrdenExhibicion(stage.orden) ? 'EXHIBICIÓN' : 'SIN PEDIDO'}
            </span>
          </div>
        )}

        <h4 className="font-headline font-bold text-yeikar-secondary text-sm group-hover:text-yeikar-primary transition-colors leading-tight">
          {stage.orden?.detalle_pedido?.producto?.nombre 
            ? stage.orden.detalle_pedido.producto.nombre 
            : stage.orden?.producto?.nombre
            ? stage.orden.producto.nombre 
            : stage.orden_produccion_id 
            ? `Orden de Producción #${stage.orden_produccion_id}` 
            : 'Producto en Fabricación'}
        </h4>

        {(stage.orden?.detalle_pedido?.ancho && stage.orden?.detalle_pedido?.largo) || (stage.orden?.ancho && stage.orden?.largo) ? (
          <p className="text-[10px] font-mono text-yeikar-neutral/50">
            {stage.orden.detalle_pedido?.ancho && stage.orden.detalle_pedido.largo
              ? `${stage.orden.detalle_pedido.ancho}m × ${stage.orden.detalle_pedido.largo}m`
              : `${stage.orden.ancho}m × ${stage.orden.largo}m`}
          </p>
        ) : null}

        {stage.observaciones && (
          <p className="text-xs text-yeikar-neutral/60 line-clamp-2 italic">
            {stage.observaciones}
          </p>
        )}
      </div>

      {/* Footer */}
      <div className="flex items-center justify-between mt-3 pt-3 border-t border-yeikar-secondary-light/5">
        <div className="flex items-center gap-1.5 text-xs text-yeikar-neutral/50">
          <svg className="w-3.5 h-3.5 text-yeikar-neutral/40" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
          </svg>
          <span className="truncate max-w-[120px] font-medium">
            {stage.empleado_responsable
              ? `${stage.empleado_responsable.nombre}`
              : 'Sin asignar'}
          </span>
        </div>

        {stage.estado !== 'COMPLETADA' && (
          <button
            type="button"
            onClick={(event) => {
              event.stopPropagation();
              onPassToArea(stage);
            }}
            className="bg-yeikar-primary/10 text-yeikar-primary hover:bg-yeikar-primary hover:text-yeikar-neutral px-2.5 py-1.5 rounded-lg text-[10px] font-bold transition-colors"
          >
            → Pasar a Área
          </button>
        )}
      </div>
      {stage.asignados_adicionales?.length > 0 && (
        <div className="mt-2 text-[10px] text-yeikar-neutral/50">
          Adicionales: {stage.asignados_adicionales.map((asignado) =>
            asignado.empleado ? `${asignado.empleado.nombre}` : `#${asignado.empleado_id}`
          ).join(', ')}
        </div>
      )}
    </div>
  );
}

// Main Production Kanban Page
export default function ProduccionKanban() {
  const toast = useToast();
  const [confirmFinalizarId, setConfirmFinalizarId] = useState<number | null>(null);
  const [areas, setAreas] = useState<Area[]>([]);
  const [stages, setStages] = useState<EtapaProduccion[]>([]);
  const [ordenesSinEtapaActiva, setOrdenesSinEtapaActiva] = useState<OrdenProduccion[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [showCompleted, setShowCompleted] = useState(false);
  const [selectedStage, setSelectedStage] = useState<EtapaProduccion | null>(null);

  // Controlled area transition modal state
  const [showPasarModal, setShowPasarModal] = useState(false);
  const [pasarStage, setPasarStage] = useState<EtapaProduccion | null>(null);
  const [pasarAreaId, setPasarAreaId] = useState('');
  const [pasarEmpleadoPrincipal, setPasarEmpleadoPrincipal] = useState('');
  const [pasarEmpleadosAdicionales, setPasarEmpleadosAdicionales] = useState<number[]>([]);
  const [pasarObservaciones, setPasarObservaciones] = useState('');
  const [pasarSubmitting, setPasarSubmitting] = useState(false);

  // New stage modal state
  const [ordenParaNuevaEtapa, setOrdenParaNuevaEtapa] = useState<number | null>(null);
  const [nuevaEtapaForm, setNuevaEtapaForm] = useState({ area_id: '', empleado_id: '', observaciones: '' });

  // Detail Modal Forms state (datos que consume el EtapaModal)
  const [empleados, setEmpleados] = useState<Empleado[]>([]);
  const [materiales, setMateriales] = useState<Material[]>([]);

  // Sobrantes disponibles del material seleccionado (para origen del corte)
  const [sobrantesLamina, setSobrantesLamina] = useState<SobranteLamina[]>([]);
  const cargarSobrantes = useCallback(async () => {
    try {
      const data = await inventarioService.getSobrantes({ estado: 'DISPONIBLE' });
      setSobrantesLamina(data);
    } catch {
      setSobrantesLamina([]);
    }
  }, []);
  useEffect(() => {
    cargarSobrantes();
  }, [cargarSobrantes]);

  // Referencia receta
  const [referenciaReceta, setReferenciaReceta] = useState<ReferenciaReceta | null>(null);
  const [loadingReceta, setLoadingReceta] = useState(false);

  // Hoja de Trabajo (documento imprimible por etapa)
  const [hojaAbierta, setHojaAbierta] = useState(false);
  const [hojaData, setHojaData] = useState<ReferenciaReceta | null>(null);
  const [hojaCargando, setHojaCargando] = useState(false);
  const [generandoHoja, setGenerandoHoja] = useState(false);

  // Protección contra doble clic / doble submit
  const [finalizandoOrdenId, setFinalizandoOrdenId] = useState<number | null>(null);
  const [nuevaEtapaSubmitting, setNuevaEtapaSubmitting] = useState(false);
  const [statusUpdatingId, setStatusUpdatingId] = useState<number | null>(null);

  // Paginación del listado de órdenes (antes solo se cargaban ~100 y las
  // órdenes antiguas desaparecían del tablero en silencio)
  const [ordenes, setOrdenes] = useState<OrdenProduccion[]>([]);
  const [salto, setSalto] = useState(0);
  const [hasMore, setHasMore] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const LIMITE = 100;

  // Stock disponible por material (para mostrarlo al registrar consumos)
  const [inventario, setInventario] = useState<Record<number, number>>({});

  // Costos EN VIVO de la orden de la etapa abierta (desglose estilo Excel)
  const [costosEnVivo, setCostosEnVivo] = useState<CostosEnVivoOrden | null>(null);
  const [costosEnVivoLoading, setCostosEnVivoLoading] = useState(false);
  const [refreshVivo, setRefreshVivo] = useState(0);

  useEffect(() => {
    const ordenId = selectedStage?.orden_produccion_id;
    if (ordenId == null) {
      setCostosEnVivo(null);
      return;
    }
    let activo = true;
    setCostosEnVivoLoading(true);
    produccionService.getCostosEnVivo(ordenId)
      .then((data) => { if (activo) setCostosEnVivo(data); })
      .catch(() => { if (activo) setCostosEnVivo(null); })
      .finally(() => { if (activo) setCostosEnVivoLoading(false); });
    return () => { activo = false; };
  }, [selectedStage?.orden_produccion_id, refreshVivo]);

  const cargarInventario = async () => {
    try {
      const data = await inventarioService.getInventario();
      const mapa: Record<number, number> = {};
      data.forEach((inv) => {
        mapa[inv.material_id] = inv.cantidad;
      });
      setInventario(mapa);
    } catch {
      // El inventario es informativo: no romper el kanban si falla
    }
  };

  const procesarOrdenes = (ordenesData: OrdenProduccion[]) => {
    // Extraer TODAS las etapas (incluidas completadas, se filtran en la UI)
    const allStages: EtapaProduccion[] = [];
    const sinActiva: OrdenProduccion[] = [];

    ordenesData.forEach((orden) => {
      // Los productos de REVENTA no se fabrican: sus órdenes (legacy o creadas
      // por error) no se muestran en el tablero.
      if (orden.detalle_pedido?.producto?.es_reventa) return;
      if (orden.etapas && orden.etapas.length > 0) {
        orden.etapas.forEach((etapa) => allStages.push(etapa));
        // Órdenes activas sin ninguna etapa activa
        const tieneActiva = orden.etapas.some(
          (e) => e.estado !== 'COMPLETADA'
        );
        if (!tieneActiva && ['PENDIENTE', 'EN_PRODUCCION', 'PAUSADA'].includes(orden.estado)) {
          sinActiva.push(orden);
        }
      } else if (['PENDIENTE', 'EN_PRODUCCION', 'PAUSADA'].includes(orden.estado)) {
        // Órdenes sin etapas en absoluto
        sinActiva.push(orden);
      }
    });

    setStages(allStages);
    setOrdenesSinEtapaActiva(sinActiva);
  };

  const fetchKanbanData = async () => {
    try {
      setLoading(true);
      const [areasData, ordenesData] = await Promise.all([
        produccionService.getAreas(),
        produccionService.getOrdenes(search || undefined, 0, LIMITE),
      ]);

      setAreas(
        areasData
          .filter(a => a.nombre !== 'Depósito')
          .sort((a, b) => {
            const ia = ORDEN_PIPELINE.indexOf(a.nombre);
            const ib = ORDEN_PIPELINE.indexOf(b.nombre);
            if (ia === -1 && ib === -1) return a.nombre.localeCompare(b.nombre);
            if (ia === -1) return 1;
            if (ib === -1) return -1;
            return ia - ib;
          }),
      );
      setOrdenes(ordenesData);
      setSalto(ordenesData.length);
      setHasMore(ordenesData.length === LIMITE);
      procesarOrdenes(ordenesData);
    } catch (error) {
      console.error('Error fetching production kanban data:', error);
      toast.error('No fue posible cargar el taller de producción. Reintenta en un momento.');
    } finally {
      setLoading(false);
    }
  };

  const cargarMasOrdenes = async () => {
    if (loadingMore || !hasMore) return;
    setLoadingMore(true);
    try {
      const data = await produccionService.getOrdenes(search || undefined, salto, LIMITE);
      setOrdenes((prev) => [...prev, ...data]);
      setSalto((prev) => prev + data.length);
      setHasMore(data.length === LIMITE);
      procesarOrdenes([...ordenes, ...data]);
    } catch (error) {
      console.error('Error loading more orders:', error);
      toast.error('Error al cargar más órdenes.');
    } finally {
      setLoadingMore(false);
    }
  };

  // Carga inicial + búsqueda con debounce (la búsqueda ahora es server-side)
  useEffect(() => {
    const t = setTimeout(() => {
      fetchKanbanData();
    }, 400);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [search]);

  useEffect(() => {
    // Empleados (con límite alto) para los modales de pasar a área / nueva
    // etapa. Los materiales ya NO se precargan: el selector de insumo de la
    // estación de trabajo busca server-side (autocomplete) en EtapaModal.
    api.get('/empleado/', { params: { limite: 1000 } }).then((r) => setEmpleados(r.data)).catch(() => {});
    cargarInventario();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Cerrar modales con ESC
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setSelectedStage(null);
        setShowPasarModal(false);
        setOrdenParaNuevaEtapa(null);
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  // Receta de referencia del producto de la etapa (escalada a las dimensiones)
  // Funciona para órdenes con pedido Y para EXHIBICION/STOCK (producto de la orden)
  useEffect(() => {
    if (selectedStage?.orden?.detalle_pedido?.producto?.id || selectedStage?.orden?.producto_id) {
      setLoadingReceta(true);
      produccionService.getReferenciaReceta(selectedStage.id)        .then(setReferenciaReceta)
        .catch(() => setReferenciaReceta(null))
        .finally(() => setLoadingReceta(false));
    } else {
      setReferenciaReceta(null);
    }
  }, [selectedStage]);

  // ── Hoja de Trabajo: preview y descarga del documento por etapa ──
  const abrirHojaTrabajo = async () => {
    if (!selectedStage) return;
    setHojaAbierta(true);
    setHojaData(null);
    setHojaCargando(true);
    try {
      const data = await produccionService.getReferenciaReceta(selectedStage.id);
      setHojaData(data);
    } catch {
      setHojaData(null);
    } finally {
      setHojaCargando(false);
    }
  };

  const descargarHojaTrabajo = async () => {
    const el = document.getElementById('hoja-trabajo-container');
    if (!el || !hojaData) return;
    setGenerandoHoja(true);
    try {
      const { capturarElementoAPdf } = await import('../utils/pdfCaptura');
      const nombreSeccion = (hojaData.seccion_actual || hojaData.area_nombre || 'Taller').replace(/\s+/g, '_');
      await capturarElementoAPdf(el, {
        nombreArchivo: `Hoja_Trabajo_${nombreSeccion}_Orden_${String(hojaData.orden_id ?? 0).padStart(5, '0')}.pdf`,
        scale: 5,
        margenMm: 8,
      });
      toast.success('Hoja de trabajo descargada.');
    } catch {
      toast.error('No se pudo generar el PDF de la hoja de trabajo.');
    } finally {
      setGenerandoHoja(false);
    }
  };

  // (La pre-selección de solicitante y el tarifario de costos de producción
  //  viven ahora dentro de EtapaModal.)

  const handleStatusChange = async (stageId: number, newStatus: string) => {
    if (statusUpdatingId !== null) return; // evita PUTs concurrentes sobre estados
    setStatusUpdatingId(stageId);
    try {
      await produccionService.updateEstadoEtapa(stageId, newStatus);
      fetchKanbanData();
      if (selectedStage && selectedStage.id === stageId) {
        // Actualizar modal si está abierto
        const updated = await api.get<EtapaProduccion>(`/produccion/etapa/${stageId}`);
        setSelectedStage(updated.data);
      }
    } catch (error: any) {
      console.error('Error changing stage status:', error);
      toast.error(error.response?.data?.detail || 'No fue posible cambiar el estado de la etapa.');
    } finally {
      setStatusUpdatingId(null);
    }
  };

  const openPasarModal = (stage: EtapaProduccion) => {
    setPasarStage(stage);
    setPasarAreaId('');
    setPasarEmpleadoPrincipal('');
    setPasarEmpleadosAdicionales([]);
    setPasarObservaciones('');
    setShowPasarModal(true);
  };

  const closePasarModal = () => {
    setShowPasarModal(false);
    setPasarStage(null);
  };

  const handlePasarAArea = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!pasarStage || !pasarAreaId || !pasarEmpleadoPrincipal) return;

    setPasarSubmitting(true);
    try {
      await produccionService.pasarAArea(pasarStage.id, {
        area_id: Number(pasarAreaId),
        empleado_responsable_id: Number(pasarEmpleadoPrincipal),
        empleados_adicionales_ids: pasarEmpleadosAdicionales,
        observaciones: pasarObservaciones || undefined,
      });
      closePasarModal();
      // La etapa actual quedó detrás de la nueva: cerrar la estación de trabajo.
      setSelectedStage(null);
      await fetchKanbanData();
    } catch (error: any) {
      console.error('Error pasando etapa a otra area:', error);
      toast.error(error.response?.data?.detail || 'No fue posible pasar la etapa al area seleccionada.');
    } finally {
      setPasarSubmitting(false);
    }
  };

  const togglePasarEmpleadoAdicional = (empleadoId: number) => {
    setPasarEmpleadosAdicionales((actuales) =>
      actuales.includes(empleadoId)
        ? actuales.filter((id) => id !== empleadoId)
        : [...actuales, empleadoId],
    );
  };

  // ── Refrescar la etapa abierta tras registrar/eliminar algo en el modal ──
  // Recarga la etapa (con sus consumos/MO), los costos en vivo, el inventario,
  // los sobrantes y el tablero completo.
  const refrescarEtapa = async () => {
    if (!selectedStage) return;
    try {
      const updated = await api.get<EtapaProduccion>(`/produccion/etapa/${selectedStage.id}`);
      setSelectedStage(updated.data);
    } catch {
      // si falla la recarga puntual, el tablero sigue refrescando abajo
    }
    setRefreshVivo(v => v + 1);
    await cargarInventario();
    cargarSobrantes();
    fetchKanbanData();
  };

  const handleFinalizarOrden = (ordenId: number) => {
    setConfirmFinalizarId(ordenId);
  };
  const ejecutarFinalizarOrden = async () => {
    const ordenId = confirmFinalizarId;
    if (ordenId === null || finalizandoOrdenId !== null) return; // evita doble finalización
    setConfirmFinalizarId(null);
    setFinalizandoOrdenId(ordenId);
    try {
      // Una sola petición: el backend calcula costos al pasar a FINALIZADA.
      // Si el cálculo falla, el backend devuelve 400 y la orden NO se cierra.
      const res = await api.put(`/produccion/orden/${ordenId}/estado?estado=FINALIZADA`);
      const estructuraGenerada = res.data?.estructura_generada;
      toast.success(
        estructuraGenerada
          ? `Orden #${ordenId} finalizada. Estructura de costes generada y costo base del producto actualizado.`
          : `Orden #${ordenId} finalizada con sus costos calculados.`,
      );
      setRefreshVivo(v => v + 1);
      fetchKanbanData();
    } catch (error: any) {
      console.error('Error finalizing order:', error);
      toast.error(error.response?.data?.detail || 'Error al finalizar la orden.');
    } finally {
      setFinalizandoOrdenId(null);
    }
  };


  const handleSubmitNuevaEtapa = async (e: React.FormEvent) => {
    e.preventDefault();
    if (nuevaEtapaSubmitting) return;
    if (!ordenParaNuevaEtapa || !nuevaEtapaForm.area_id || !nuevaEtapaForm.empleado_id) return;
    setNuevaEtapaSubmitting(true);
    try {
      await api.post('/produccion/etapa/', {
        orden_produccion_id: ordenParaNuevaEtapa,
        area_id: parseInt(nuevaEtapaForm.area_id),
        empleado_responsable_id: parseInt(nuevaEtapaForm.empleado_id),
        estado: 'ASIGNADA',
        observaciones: nuevaEtapaForm.observaciones || 'Creado manualmente desde Kanban',
        fecha_inicio: new Date().toISOString(),
      });
      setOrdenParaNuevaEtapa(null);
      setNuevaEtapaForm({ area_id: '', empleado_id: '', observaciones: '' });
      fetchKanbanData();
      toast.success('Etapa creada.');
    } catch (error: any) {
      console.error('Error creating stage:', error);
      toast.error(error.response?.data?.detail || 'Error al crear la etapa.');
    } finally {
      setNuevaEtapaSubmitting(false);
    }
  };

  // Filtrar etapas por búsqueda y toggle de completadas
  const filteredStages = stages.filter((stage) => {
    // Filtrar por completadas según toggle
    if (!showCompleted && stage.estado === 'COMPLETADA') return false;
    
    const term = search.toLowerCase();
    if (!term) return true;
    const idMatch = stage.orden_produccion_id.toString().includes(term);
    const obsMatch = stage.observaciones?.toLowerCase().includes(term) || false;
    const empMatch =
      stage.empleado_responsable
        ? `${stage.empleado_responsable.nombre}`.toLowerCase().includes(term)
        : false;
    const clientMatch = stage.orden?.detalle_pedido?.pedido?.cliente?.nombre?.toLowerCase().includes(term) || false;
    const prodMatch =
      stage.orden?.detalle_pedido?.producto?.nombre?.toLowerCase().includes(term) ||
      stage.orden?.producto?.nombre?.toLowerCase().includes(term) ||
      false;
    return idMatch || obsMatch || empMatch || clientMatch || prodMatch;
  });

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
        <div>
          <h1 className="text-2xl sm:text-3xl font-black font-headline text-yeikar-neutral tracking-tight">
            Apartado de Producción
          </h1>
          <p className="text-yeikar-neutral/60 mt-1">
            Supervisa y actualiza el estado de las etapas de fabricación en tiempo real.
          </p>
        </div>

        <div className="flex items-center gap-3 flex-wrap justify-end">
          {/* Toggle completadas */}
          <button
            onClick={() => setShowCompleted((v) => !v)}
            className={`flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-bold font-headline border transition-all ${
              showCompleted
                ? 'bg-green-50 text-green-700 border-green-200 shadow-sm'
                : 'bg-white text-yeikar-neutral/60 border-yeikar-secondary-light/10 hover:border-yeikar-primary'
            }`}
          >
            <span className={`w-2 h-2 rounded-full ${showCompleted ? 'bg-green-500' : 'bg-yeikar-neutral/30'}`} />
            {showCompleted ? 'Ocultar completadas' : 'Ver completadas'}
          </button>

          {/* Ir a Producción de Crudos */}
          <Link
            to="/produccion-crudo"
            className="flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-bold font-headline bg-yeikar-secondary text-white shadow-sm hover:bg-yeikar-secondary/90 transition-all"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" /></svg>
            Producción de Crudos
          </Link>

          {/* Search Input */}
          <div className="relative w-full md:w-72">
            <input
              type="text"
              placeholder="Buscar por cliente, producto, orden o responsable..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="w-full bg-white border border-yeikar-secondary-light/10 rounded-xl pl-10 pr-4 py-2 text-sm text-yeikar-neutral placeholder-yeikar-neutral/40 focus:outline-none focus:border-yeikar-primary shadow-sm"
            />
            <svg
              className="absolute left-3.5 top-3.5 w-4 h-4 text-yeikar-neutral/40"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
            </svg>
          </div>
        </div>
      </div>

      {/* Banner: Órdenes EN_PRODUCCION sin etapa activa */}
      {!loading && ordenesSinEtapaActiva.length > 0 && (
        <div className="bg-amber-50 border border-amber-200 rounded-2xl p-4">
          <div className="flex items-start gap-3">
            <div className="w-8 h-8 flex-shrink-0 bg-amber-100 rounded-xl flex items-center justify-center">
              <svg className="w-4 h-4 text-amber-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
              </svg>
            </div>
            <div className="flex-1">
              <p className="text-sm font-bold text-amber-800">
                {ordenesSinEtapaActiva.length === 1
                  ? '1 orden activa sin etapa de trabajo'
                  : `${ordenesSinEtapaActiva.length} órdenes activas sin etapa de trabajo`}
              </p>
              <p className="text-xs text-amber-700 mt-0.5">
                Las siguientes órdenes están pendientes, pausadas o en producción pero no tienen ninguna etapa activa.
                Puedes añadir una etapa para iniciarla/continuarla o finalizar la orden.
              </p>

              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3 mt-3">
                {ordenesSinEtapaActiva.map((o) => (
                  <div key={o.id} className="bg-white border border-amber-200 rounded-xl p-3 shadow-sm hover:shadow-md transition-shadow">
                    <div className="flex items-start justify-between mb-2">
                      <div className="space-y-0.5">
                        <span className="text-[10px] font-mono text-amber-700 font-bold">ORDEN #{o.id}</span>
                        <p className="text-sm font-bold text-amber-900 leading-tight">
                          {o.producto?.nombre || o.detalle_pedido?.producto?.nombre || `Producto #${o.detalle_pedido_id ?? o.producto_id}`}
                        </p>
                      </div>
                      <span className={`text-[10px] px-2 py-0.5 rounded font-bold ${
                        o.estado === 'PENDIENTE' ? 'bg-blue-100 text-blue-700' :
                        o.estado === 'EN_PRODUCCION' ? 'bg-amber-100 text-amber-700' :
                        'bg-red-100 text-red-700'
                      }`}>
                        {o.estado.replace('_', ' ')}
                      </span>
                    </div>
                    <div className="flex flex-wrap gap-x-3 gap-y-0.5 text-[10px] text-amber-700/70 font-medium mb-2">
                      {o.detalle_pedido?.pedido?.cliente?.nombre && (
                        <span className="flex items-center gap-1">
                          <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" /></svg>
                          {o.detalle_pedido.pedido.cliente.nombre}
                        </span>
                      )}
                      {o.detalle_pedido?.ancho && o.detalle_pedido?.largo && (
                        <span className="font-mono">
                          {o.detalle_pedido.ancho}m × {o.detalle_pedido.largo}m
                        </span>
                      )}
                    </div>
                    <div className="flex items-center gap-2 pt-2 border-t border-amber-100">
                      <button
                        onClick={() => setOrdenParaNuevaEtapa(o.id)}
                        className="flex-1 text-center px-2 py-1.5 bg-amber-100 hover:bg-amber-200 text-amber-800 rounded-lg text-[10px] font-bold transition-colors"
                      >
                        + Añadir Etapa
                      </button>
                      <button
                        onClick={() => handleFinalizarOrden(o.id)}
                        disabled={finalizandoOrdenId !== null}
                        className="flex-1 text-center px-2 py-1.5 bg-green-500 hover:bg-green-600 disabled:opacity-50 disabled:cursor-not-allowed text-white rounded-lg text-[10px] font-bold transition-colors"
                      >
                        {finalizandoOrdenId === o.id ? 'Finalizando...' : 'Finalizar'}
                      </button>
                    </div>
                  </div>
                ))}
              </div>
              <p className="text-xs text-amber-600 mt-2 italic">
                Activa "Ver completadas" para revisar el trabajo realizado en estas órdenes.
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Loading state */}
      {loading ? (
        <div className="flex flex-col items-center justify-center py-20 space-y-4">
          <div className="w-12 h-12 border-4 border-yeikar-primary border-t-transparent rounded-full animate-spin"></div>
          <p className="text-sm font-mono text-yeikar-neutral/60">Cargando datos de fábrica...</p>
        </div>
      ) : ordenes.length === 0 && !search ? (
        /* Estado vacío global: el flujo principal arranca en Pedidos */
        <div className="flex flex-col items-center justify-center py-20 border-2 border-dashed border-yeikar-secondary-light/15 rounded-3xl text-center px-6">
          <div className="w-14 h-14 bg-yeikar-tertiary/40 rounded-2xl flex items-center justify-center mb-4">
            <svg className="w-7 h-7 text-yeikar-primary" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" />
            </svg>
          </div>
          <h2 className="text-lg font-black font-headline text-yeikar-neutral">Aún no hay órdenes de producción</h2>
          <p className="text-sm text-yeikar-neutral/60 mt-1 max-w-md">
            Las órdenes se generan desde los pedidos aprobados. Cuando un pedido entre a producción,
            sus órdenes y etapas aparecerán aquí por área.
          </p>
          <Link
            to="/pedidos"
            className="mt-5 bg-yeikar-primary text-yeikar-neutral px-6 py-2.5 rounded-xl text-sm font-bold font-headline shadow-sm hover:bg-yeikar-primary-dark transition-colors"
          >
            Ir a Pedidos
          </Link>
        </div>
      ) : ordenes.length === 0 && search ? (
        <div className="flex flex-col items-center justify-center py-16 border border-dashed border-yeikar-secondary-light/15 rounded-3xl text-center">
          <p className="text-sm text-yeikar-neutral/60">Sin resultados para «{search}».</p>
          <p className="text-xs text-yeikar-neutral/40 mt-1">Prueba con otro cliente, producto, orden o responsable.</p>
        </div>
      ) : (
        <>
          <div className="scroll-edge-r flex gap-5 overflow-x-auto pb-4 pt-1 scroll-touch [scroll-snap-type:x_proximity]">
            {areas.map((area) => {
              const areaStages = filteredStages.filter((s) => s.area_id === area.id);
              return (
                <KanbanColumn
                  key={area.id}
                  area={area}
                  stages={areaStages}
                  onCardClick={setSelectedStage}
                  onStatusChange={handleStatusChange}
                  onPassToArea={openPasarModal}
                  updatingStageId={statusUpdatingId}
                />
              );
            })}
          </div>

          {hasMore && (
            <div className="flex justify-center pt-2">
              <button
                type="button"
                onClick={cargarMasOrdenes}
                disabled={loadingMore}
                className="bg-white border border-yeikar-secondary-light/15 text-yeikar-primary px-6 py-2.5 rounded-xl text-sm font-bold font-headline hover:border-yeikar-primary disabled:opacity-50 transition-colors"
              >
                {loadingMore ? 'Cargando...' : 'Cargar más órdenes'}
              </button>
            </div>
          )}
        </>
      )}

      {/* ── ESTACIÓN DE TRABAJO: modal de etapa (rediseño UX) ── */}
      {selectedStage && (
        <EtapaModal
          key={selectedStage.id}
          stage={selectedStage}
          orden={ordenes.find((o) => o.id === selectedStage.orden_produccion_id) ?? null}
          areas={areas}
          empleados={empleados}
          materiales={materiales}
          inventario={inventario}
          sobrantesLamina={sobrantesLamina}
          referenciaReceta={referenciaReceta}
          loadingReceta={loadingReceta}
          costosEnVivo={costosEnVivo}
          costosEnVivoLoading={costosEnVivoLoading}
          statusUpdating={statusUpdatingId === selectedStage.id}
          onClose={() => setSelectedStage(null)}
          onRefrescarEtapa={refrescarEtapa}
          onCambiarEstado={handleStatusChange}
          onPasarAArea={openPasarModal}
          onAbrirHojaTrabajo={abrirHojaTrabajo}
          onRecargarSobrantes={cargarSobrantes}
        />
      )}

      {/* Modal Pasar a Area */}
      {showPasarModal && pasarStage && (
        <div
          className="fixed inset-0 bg-yeikar-secondary/60 backdrop-blur-sm flex items-center justify-center p-4 z-50"
          onClick={closePasarModal}
        >
          <div className="bg-white rounded-3xl shadow-xl border border-yeikar-secondary-light/10 max-w-lg w-full p-4 sm:p-6 max-h-[90vh] overflow-y-auto" role="dialog" aria-modal="true" aria-label="Mover etapa a nueva área" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-start justify-between mb-5">
              <div>
                <p className="text-[10px] font-mono font-bold text-yeikar-neutral/40 uppercase">
                  Etapa #{pasarStage.id} · Área actual: {pasarStage.area?.nombre || 'Sin área'}
                </p>
                <h2 className="text-xl font-black font-headline text-yeikar-secondary tracking-tight mt-1">
                  Mover a Nueva Área
                </h2>
                <p className="text-sm text-yeikar-neutral/60 mt-1">
                  {pasarStage.orden?.detalle_pedido?.producto?.nombre || `Orden #${pasarStage.orden_produccion_id}`}
                  {pasarStage.orden?.detalle_pedido?.pedido?.cliente?.nombre
                    ? ` / ${pasarStage.orden.detalle_pedido.pedido.cliente.nombre}`
                    : ''}
                </p>
              </div>
              <button
                type="button"
                onClick={closePasarModal}
                className="p-2 hover:bg-yeikar-tertiary rounded-xl text-yeikar-neutral/40"
                title="Cerrar modal"
                aria-label="Cerrar modal"
              >
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>

            <form onSubmit={handlePasarAArea} className="space-y-4">
              <div>
                <label className="block text-xs font-bold text-yeikar-neutral/60 mb-1">Área destino</label>
                <SearchSelect
                  value={pasarAreaId}
                  onChange={(v) => setPasarAreaId(String(v))}
                  options={areas.filter((area) => area.id !== pasarStage.area_id).map((area) => ({
                    value: area.id,
                    label: area.nombre,
                  }))}
                  placeholder="Seleccione área..."
                />
              </div>

              <div>
                <label className="block text-xs font-bold text-yeikar-neutral/60 mb-1">Responsable principal</label>
                <SearchSelect
                  value={pasarEmpleadoPrincipal}
                  onChange={(v) => {
                    const empleadoId = Number(v);
                    setPasarEmpleadoPrincipal(String(v));
                    setPasarEmpleadosAdicionales((actuales) => actuales.filter((id) => id !== empleadoId));
                  }}
                  options={empleados.filter((empleado) => empleado.id !== pasarStage.empleado_responsable_id).map((empleado) => ({
                    value: empleado.id,
                    label: `${empleado.nombre}`,
                  }))}
                  placeholder="Seleccione empleado..."
                />
              </div>

              <div>
                <label className="block text-xs font-bold text-yeikar-neutral/60 mb-2">
                  Empleados adicionales <span className="font-normal">(opcional)</span>
                </label>
                <div className="border border-yeikar-secondary-light/10 rounded-xl p-3 max-h-40 overflow-y-auto space-y-2">
                  {empleados.filter((empleado) => empleado.id.toString() !== pasarEmpleadoPrincipal).map((empleado) => (
                    <label key={empleado.id} className="flex items-center gap-2 text-sm text-yeikar-neutral cursor-pointer">
                      <input
                        type="checkbox"
                        checked={pasarEmpleadosAdicionales.includes(empleado.id)}
                        onChange={() => togglePasarEmpleadoAdicional(empleado.id)}
                        className="rounded border-yeikar-secondary-light/30 text-yeikar-primary focus:ring-yeikar-primary"
                      />
                      {empleado.nombre}
                    </label>
                  ))}
                  {empleados.length === 0 && <span className="text-xs text-yeikar-neutral/40">No hay empleados disponibles.</span>}
                </div>
                {pasarEmpleadosAdicionales.length > 0 && (
                  <p className="text-[11px] text-yeikar-primary mt-1">
                    {pasarEmpleadosAdicionales.length} empleado(s) adicional(es) seleccionado(s)
                  </p>
                )}
              </div>

              <div>
                <label className="block text-xs font-bold text-yeikar-neutral/60 mb-1">Observaciones</label>
                <textarea
                  value={pasarObservaciones}
                  onChange={(event) => setPasarObservaciones(event.target.value)}
                  rows={3}
                  placeholder="Indicaciones para la nueva etapa..."
                  className="w-full bg-yeikar-tertiary/30 border border-yeikar-secondary-light/10 rounded-xl p-2.5 text-sm focus:outline-none focus:border-yeikar-primary"
                />
              </div>

              <div className="flex justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={closePasarModal}
                  disabled={pasarSubmitting}
                  className="px-4 py-2 rounded-xl text-sm font-bold text-yeikar-neutral/60 hover:bg-yeikar-tertiary transition-colors disabled:opacity-50"
                >
                  Cancelar
                </button>
                <button
                  type="submit"
                  disabled={pasarSubmitting}
                  className="bg-yeikar-primary text-yeikar-neutral px-4 py-2 rounded-xl text-sm font-bold shadow-sm hover:shadow transition-all disabled:opacity-50"
                >
                  {pasarSubmitting ? 'Pasando...' : 'Confirmar y pasar'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Modal Nueva Etapa */}
      {ordenParaNuevaEtapa && (
        <div
          className="fixed inset-0 bg-yeikar-secondary/60 backdrop-blur-sm flex items-center justify-center p-4 z-50"
          onClick={() => setOrdenParaNuevaEtapa(null)}
        >
          <div className="bg-white rounded-3xl shadow-xl border border-yeikar-secondary-light/10 max-w-sm w-full p-4 sm:p-6" role="dialog" aria-modal="true" aria-label="Añadir etapa a orden" onClick={(e) => e.stopPropagation()}>
            <h2 className="text-xl font-black font-headline text-yeikar-secondary tracking-tight mb-4">
              Añadir Etapa a Orden #{ordenParaNuevaEtapa}
            </h2>
            <form onSubmit={handleSubmitNuevaEtapa} className="space-y-4">
              <div>
                <label className="block text-xs font-bold text-yeikar-neutral/60 mb-1">Área de Producción</label>
                <SearchSelect
                  value={nuevaEtapaForm.area_id}
                  onChange={(v) => setNuevaEtapaForm(prev => ({ ...prev, area_id: String(v) }))}
                  options={areas.map(a => ({ value: a.id, label: a.nombre }))}
                  placeholder="Seleccione Área..."
                />
              </div>
              
              <div>
                <label className="block text-xs font-bold text-yeikar-neutral/60 mb-1">Responsable</label>
                <SearchSelect
                  value={nuevaEtapaForm.empleado_id}
                  onChange={(v) => setNuevaEtapaForm(prev => ({ ...prev, empleado_id: String(v) }))}
                  options={empleados.map(e => ({ value: e.id, label: `${e.nombre}` }))}
                  placeholder="Seleccione Empleado..."
                />
              </div>

              <div>
                <label className="block text-xs font-bold text-yeikar-neutral/60 mb-1">Observaciones</label>
                <textarea
                  value={nuevaEtapaForm.observaciones}
                  onChange={(e) => setNuevaEtapaForm(prev => ({ ...prev, observaciones: e.target.value }))}
                  className="w-full bg-yeikar-tertiary/30 border border-yeikar-secondary-light/10 rounded-xl p-2.5 text-sm focus:outline-none focus:border-yeikar-primary"
                  rows={2}
                />
              </div>

              <div className="flex justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setOrdenParaNuevaEtapa(null)}
                  className="px-4 py-2 rounded-xl text-sm font-bold text-yeikar-neutral/60 hover:bg-yeikar-tertiary transition-colors"
                >
                  Cancelar
                </button>
                <button
                  type="submit"
                  disabled={nuevaEtapaSubmitting}
                  className="bg-yeikar-primary text-yeikar-neutral px-4 py-2 rounded-xl text-sm font-bold shadow-sm hover:shadow disabled:opacity-50 disabled:cursor-not-allowed transition-all"
                >
                  {nuevaEtapaSubmitting ? 'Creando...' : 'Crear Etapa'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
      <ConfirmDialog
        open={confirmFinalizarId !== null}
        title="Finalizar orden de producción"
        message={
          ordenes.some((o) => o.id === confirmFinalizarId && esOrdenExhibicion(o))
            ? `¿Finalizar la orden #${confirmFinalizarId ?? ''}? Se calcularán los costos y la pieza de EXHIBICIÓN entrará al stock del showroom (no se genera envío a cliente).`
            : `¿Estás seguro de finalizar la orden #${confirmFinalizarId ?? ''}? Esto calculará sus costos definitivos y la cerrará.`
        }
        confirmLabel="Sí, finalizar"
        danger={false}
        onConfirm={ejecutarFinalizarOrden}
        onCancel={() => setConfirmFinalizarId(null)}
      />
      {/* ── MODAL: Hoja de Trabajo (preview + descarga PDF) ── */}
      {hojaAbierta && (
        <div
          className="fixed inset-0 bg-yeikar-secondary/60 backdrop-blur-sm z-[70] flex items-center justify-center p-3 sm:p-6"
          onClick={() => setHojaAbierta(false)}
        >
          <div
            className="bg-white rounded-3xl shadow-xl max-w-5xl w-full max-h-[94vh] flex flex-col overflow-hidden border border-yeikar-secondary-light/10"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between gap-3 px-5 py-3.5 border-b border-yeikar-secondary-light/10">
              <div className="min-w-0">
                <span className="text-[10px] font-mono font-bold text-yeikar-neutral/40 uppercase tracking-wider">
                  Hoja de Trabajo — {hojaData?.seccion_actual || hojaData?.area_nombre || 'Taller'}
                </span>
                <h3 className="font-headline font-black text-yeikar-secondary text-base truncate">
                  {hojaData?.producto_nombre || 'Documento del taller'}
                </h3>
              </div>
              <div className="flex items-center gap-2 flex-shrink-0">
                <button
                  onClick={descargarHojaTrabajo}
                  disabled={!hojaData || generandoHoja}
                  className="px-4 py-2 bg-yeikar-primary hover:bg-yeikar-primary-dark text-yeikar-neutral rounded-xl text-xs font-bold font-headline transition-all disabled:opacity-50 shadow-gold flex items-center gap-1.5"
                >
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                  </svg>
                  {generandoHoja ? 'Generando…' : 'Descargar PDF'}
                </button>
                <button
                  onClick={() => setHojaAbierta(false)}
                  className="p-2 hover:bg-yeikar-tertiary rounded-xl text-yeikar-neutral/40 hover:text-yeikar-neutral/80 transition-colors"
                  aria-label="Cerrar"
                >
                  <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
              </div>
            </div>
            <div className="flex-1 overflow-auto bg-stone-200/70 p-4">
              {hojaCargando ? (
                <div className="flex flex-col items-center justify-center py-16 space-y-3">
                  <div className="w-8 h-8 border-4 border-yeikar-primary border-t-transparent rounded-full animate-spin" />
                  <p className="text-xs text-yeikar-neutral/50 font-mono">Preparando la hoja de trabajo…</p>
                </div>
              ) : hojaData ? (
                <DocumentoHojaTrabajo hoja={hojaData} containerId="hoja-trabajo-container" />
              ) : (
                <div className="text-center py-16">
                  <p className="text-sm text-yeikar-neutral/50">
                    Esta etapa no tiene producto con receta asociada (¿orden sin producto?). No se puede generar la hoja.
                  </p>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
