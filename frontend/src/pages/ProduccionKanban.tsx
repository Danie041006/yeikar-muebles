import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { produccionService, OrdenProduccion, EtapaProduccion, Area, ReferenciaReceta } from '../services/produccionService';
import { inventarioService } from '../services/inventarioService';
import api from '../services/api';
import ConfirmDialog from '../components/ui/ConfirmDialog';
import { SearchSelect } from '../components/ui';
import { useToast } from '../context/ToastContext';

// Transiciones legales de etapa (mismas que la máquina de estados del backend).
const TRANSICIONES_ETAPA: Record<string, string[]> = {
  ASIGNADA: ['EN_PROCESO'],
  EN_PROCESO: ['PAUSADA', 'COMPLETADA'],
  PAUSADA: ['EN_PROCESO'],
  COMPLETADA: [],
};

// Empleado interface for selection
interface Empleado {
  id: number;
  nombre: string;
  apellido: string;
}

// Material interface for selection (extended for cost display)
interface Material {
  id: number;
  nombre: string;
  costo_base: number;
  unidad_medida?: {
    id: number;
    nombre: string;
    abreviatura: string;
  };
}

const fmt = (n: number) =>
  new Intl.NumberFormat('es-CO', { style: 'currency', currency: 'COP', maximumFractionDigits: 0 }).format(n);

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
      className="flex flex-col min-h-[500px] w-72 snap-start bg-yeikar-tertiary/40 border border-yeikar-secondary-light/10 rounded-2xl p-4 shadow-sm"
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

        <h4 className="font-headline font-bold text-yeikar-secondary text-sm group-hover:text-yeikar-primary transition-colors leading-tight">
          {stage.orden?.detalle_pedido?.producto?.nombre 
            ? stage.orden.detalle_pedido.producto.nombre 
            : stage.orden_produccion_id 
            ? `Orden de Producción #${stage.orden_produccion_id}` 
            : 'Producto en Fabricación'}
        </h4>

        {stage.orden?.detalle_pedido?.ancho && stage.orden?.detalle_pedido?.largo && (
          <p className="text-[10px] font-mono text-yeikar-neutral/50">
            {stage.orden.detalle_pedido.ancho}m × {stage.orden.detalle_pedido.largo}m
          </p>
        )}

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
              ? `${stage.empleado_responsable.nombre} ${stage.empleado_responsable.apellido}`
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
            asignado.empleado ? `${asignado.empleado.nombre} ${asignado.empleado.apellido}` : `#${asignado.empleado_id}`
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

  // Detail Modal Forms state
  const [empleados, setEmpleados] = useState<Empleado[]>([]);
  const [materiales, setMateriales] = useState<Material[]>([]);
  const [newConsumo, setNewConsumo] = useState({ material_id: '', cantidad: '', observaciones: '' });
  const [materialSearch, setMaterialSearch] = useState('');
  const [showMaterialDropdown, setShowMaterialDropdown] = useState(false);
  const [newManoObra, setNewManoObra] = useState({ empleado_id: '', monto: '', observaciones: '' });

  // Referencia receta
  const [referenciaReceta, setReferenciaReceta] = useState<ReferenciaReceta | null>(null);
  const [loadingReceta, setLoadingReceta] = useState(false);

  // Protección contra doble clic / doble submit
  const [finalizandoOrdenId, setFinalizandoOrdenId] = useState<number | null>(null);
  const [consumoSubmitting, setConsumoSubmitting] = useState(false);
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

  // Confirmaciones de borrado (acciones destructivas: revierten stock y gastos)
  const [consumoAEliminar, setConsumoAEliminar] = useState<number | null>(null);
  const [manoObraAEliminar, setManoObraAEliminar] = useState<number | null>(null);

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

      setAreas(areasData.filter(a => a.nombre !== 'Depósito'));
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
    // Cargar empleados, materiales e inventario para los modales
    api.get('/empleado/').then((r) => setEmpleados(r.data)).catch(() => {});
    api.get('/material/').then((r) => setMateriales(r.data)).catch(() => {});
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
  useEffect(() => {
    if (selectedStage?.orden?.detalle_pedido?.producto?.id) {
      setLoadingReceta(true);
      produccionService.getReferenciaReceta(selectedStage.id)
        .then(setReferenciaReceta)
        .catch(() => setReferenciaReceta(null))
        .finally(() => setLoadingReceta(false));
    } else {
      setReferenciaReceta(null);
    }
  }, [selectedStage]);

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

  const handleAddConsumo = async (e: React.FormEvent) => {
    e.preventDefault();
    if (consumoSubmitting) return; // evita doble descuento de stock
    if (!selectedStage || !newConsumo.material_id || !newConsumo.cantidad) return;
    setConsumoSubmitting(true);
    try {
      const materialId = parseInt(newConsumo.material_id);
      const cantidad = parseFloat(newConsumo.cantidad);
      const stockAntes = inventario[materialId];
      await produccionService.registrarConsumo({
        etapa_produccion_id: selectedStage.id,
        material_id: materialId,
        cantidad,
        fecha: new Date().toISOString(),
        seccion: referenciaReceta?.seccion_actual || undefined,
        observaciones: newConsumo.observaciones || undefined,
      });
      // Recargar etapa + inventario (el consumo descontó stock)
      const updated = await api.get<EtapaProduccion>(`/produccion/etapa/${selectedStage.id}`);
      setSelectedStage(updated.data);
      setNewConsumo({ material_id: '', cantidad: '', observaciones: '' });
      setMaterialSearch('');
      await cargarInventario();
      fetchKanbanData();
      toast.success(
        stockAntes !== undefined
          ? `Material registrado y descontado del inventario. Stock restante: ${Math.max(0, stockAntes - cantidad)}`
          : 'Material registrado y descontado del inventario.'
      );
    } catch (error: any) {
      toast.error(error.response?.data?.detail || 'Error al registrar consumo. Verifique el inventario.');
    } finally {
      setConsumoSubmitting(false);
    }
  };

  const ejecutarEliminarConsumo = async () => {
    const consumoId = consumoAEliminar;
    if (consumoId === null || !selectedStage) return;
    setConsumoAEliminar(null);
    try {
      await produccionService.eliminarConsumo(consumoId);
      const updated = await api.get<EtapaProduccion>(`/produccion/etapa/${selectedStage.id}`);
      setSelectedStage(updated.data);
      await cargarInventario();
      fetchKanbanData();
      toast.success('Consumo eliminado. El stock fue repuesto y el egreso revertido.');
    } catch (error: any) {
      toast.error(error.response?.data?.detail || 'Error al eliminar el consumo.');
    }
  };

  const handleAddManoObra = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedStage || !newManoObra.empleado_id || !newManoObra.monto) return;
    try {
      await produccionService.registrarManoObra({
        etapa_produccion_id: selectedStage.id,
        empleado_id: parseInt(newManoObra.empleado_id),
        monto: parseFloat(newManoObra.monto),
        porcentaje_recargo: 0.0,
        observaciones: newManoObra.observaciones || undefined,
      });
      // Recargar etapa
      const updated = await api.get<EtapaProduccion>(`/produccion/etapa/${selectedStage.id}`);
      setSelectedStage(updated.data);
      setNewManoObra({ empleado_id: '', monto: '', observaciones: '' });
      fetchKanbanData();
      toast.success('Mano de obra registrada para la etapa.');
    } catch (error: any) {
      toast.error(error.response?.data?.detail || 'Error al registrar la mano de obra. La etapa debe estar EN PROCESO.');
    }
  };

  const ejecutarEliminarManoObra = async () => {
    const manoObraId = manoObraAEliminar;
    if (manoObraId === null || !selectedStage) return;
    setManoObraAEliminar(null);
    try {
      await produccionService.eliminarManoObra(manoObraId);
      const updated = await api.get<EtapaProduccion>(`/produccion/etapa/${selectedStage.id}`);
      setSelectedStage(updated.data);
      fetchKanbanData();
      toast.success('Mano de obra eliminada.');
    } catch (error: any) {
      toast.error(error.response?.data?.detail || 'Error al eliminar la mano de obra.');
    }
  };

  const handleTogglePagoManoObra = async (manoObraId: number, currentPagado: boolean) => {
    try {
      await produccionService.marcarManoObraPagada(manoObraId, !currentPagado);
      if (selectedStage) {
        const updated = await api.get<EtapaProduccion>(`/produccion/etapa/${selectedStage.id}`);
        setSelectedStage(updated.data);
      }
      fetchKanbanData();
      toast.success(!currentPagado
        ? 'Mano de obra marcada como pagada. El egreso quedó registrado en Gastos.'
        : 'Pago revertido. El egreso de Gastos fue eliminado.');
    } catch (error) {
      console.error('Error toggling labor payment status:', error);
      toast.error('Error al actualizar el estado de pago.');
    }
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
      await api.put(`/produccion/orden/${ordenId}/estado?estado=FINALIZADA`);
      toast.success(`Orden #${ordenId} finalizada con sus costos calculados.`);
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
        ? `${stage.empleado_responsable.nombre} ${stage.empleado_responsable.apellido}`.toLowerCase().includes(term)
        : false;
    const clientMatch = stage.orden?.detalle_pedido?.pedido?.cliente?.nombre?.toLowerCase().includes(term) || false;
    const prodMatch = stage.orden?.detalle_pedido?.producto?.nombre?.toLowerCase().includes(term) || false;
    return idMatch || obsMatch || empMatch || clientMatch || prodMatch;
  });

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
        <div>
          <h1 className="text-3xl font-black font-headline text-yeikar-neutral tracking-tight">
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
                          {o.detalle_pedido?.producto?.nombre || `Producto #${o.detalle_pedido_id}`}
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

      {/* Details Modal */}
      {selectedStage && (
        (() => {
          // La etapa anidada trae el orden "mínimo"; el historial y el costo
          // salen de la orden completa cargada en el tablero.
          const ordenCompleta = ordenes.find((o) => o.id === selectedStage.orden_produccion_id);
          return (
        <div
          className="fixed inset-0 bg-yeikar-secondary/60 backdrop-blur-sm flex items-center justify-center p-4 z-50 overflow-y-auto"
          onClick={() => setSelectedStage(null)}
        >
          <div
            className="bg-white rounded-3xl shadow-xl border border-yeikar-secondary-light/10 max-w-3xl w-full p-6 space-y-6 max-h-[90vh] overflow-y-auto relative"
            role="dialog"
            aria-modal="true"
            aria-label={`Etapa ${selectedStage.id} de ${selectedStage.orden?.detalle_pedido?.producto?.nombre || 'producción'}`}
            onClick={(e) => e.stopPropagation()}
          >
            {/* Modal Header */}
            <div className="flex items-start justify-between border-b border-yeikar-secondary-light/10 pb-4">
              <div className="space-y-1">
                <span className="text-[10px] font-mono font-bold text-yeikar-neutral/40 tracking-wider uppercase block">
                  ETAPA #{selectedStage.id} — ÁREA: {selectedStage.area?.nombre} ({selectedStage.estado})
                  {selectedStage.es_retrabajo ? ' · RETRABAJO' : ''}
                </span>
                <h2 className="text-2xl font-black font-headline text-yeikar-secondary tracking-tight">
                  {selectedStage.orden?.detalle_pedido?.producto?.nombre
                    ? selectedStage.orden.detalle_pedido.producto.nombre
                    : `Orden de Producción #${selectedStage.orden_produccion_id}`}
                </h2>
                <div className="flex items-center gap-2 pt-1 flex-wrap">
                  {selectedStage.orden?.detalle_pedido?.pedido?.cliente?.nombre && (
                    <span className="bg-yeikar-primary/10 text-yeikar-primary font-bold text-xs px-2.5 py-1 rounded-lg border border-yeikar-primary/20 flex items-center gap-1">
                      <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
                      </svg>
                      Cliente: {selectedStage.orden.detalle_pedido.pedido.cliente.nombre}
                    </span>
                  )}
                  <span className="bg-yeikar-tertiary text-yeikar-secondary font-mono text-xs font-bold px-2.5 py-1 rounded-lg border border-yeikar-secondary-light/10">
                    Orden #{selectedStage.orden_produccion_id}
                  </span>
                  {selectedStage.orden?.detalle_pedido?.ancho && selectedStage.orden?.detalle_pedido?.largo && (
                    <span className="bg-stone-100 text-stone-600 font-mono text-xs font-bold px-2.5 py-1 rounded-lg border border-stone-200">
                      {selectedStage.orden.detalle_pedido.ancho}m × {selectedStage.orden.detalle_pedido.largo}m
                    </span>
                  )}
                  {/* Cantidad del detalle: cuántas unidades de este producto */}
                  {selectedStage.orden?.detalle_pedido?.cantidad != null && (
                    <span className="bg-yeikar-primary/10 text-yeikar-primary font-mono text-xs font-bold px-2.5 py-1 rounded-lg border border-yeikar-primary/20">
                      × {selectedStage.orden.detalle_pedido.cantidad} und
                    </span>
                  )}
                  {selectedStage.orden?.estado && (
                    <span className={`text-[10px] font-mono font-bold px-2 py-1 rounded-lg border ${
                      selectedStage.orden.estado === 'FINALIZADA' ? 'bg-green-50 text-green-700 border-green-200'
                      : selectedStage.orden.estado === 'PAUSADA' ? 'bg-red-50 text-red-700 border-red-200'
                      : 'bg-blue-50 text-blue-700 border-blue-200'
                    }`}>
                      ORDEN: {selectedStage.orden.estado.replace('_', ' ')}
                    </span>
                  )}
                </div>
                <div className="flex items-center gap-2 pt-2 flex-wrap text-[10px] font-mono text-yeikar-neutral/50">
                  <span className="flex items-center gap-1">
                    <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" /></svg>
                    Encargado: {selectedStage.empleado_responsable
                      ? `${selectedStage.empleado_responsable.nombre} ${selectedStage.empleado_responsable.apellido}`
                      : 'Sin asignar'}
                  </span>
                  {selectedStage.fecha_inicio && (
                    <span>Inicio: {new Date(selectedStage.fecha_inicio).toLocaleString('es-CO', { dateStyle: 'short', timeStyle: 'short' })}</span>
                  )}
                  {selectedStage.fecha_fin && (
                    <span>Fin: {new Date(selectedStage.fecha_fin).toLocaleString('es-CO', { dateStyle: 'short', timeStyle: 'short' })}</span>
                  )}
                </div>
              </div>
              {selectedStage.orden?.detalle_pedido?.pedido?.id && (
                <button
                  onClick={() => { window.location.href = `/historial?tipo=pedido&id=${selectedStage.orden!.detalle_pedido!.pedido!.id}`; }}
                  className="px-3 py-1.5 bg-yeikar-secondary text-yeikar-primary hover:bg-yeikar-secondary-light rounded-xl text-xs font-bold font-headline transition-all flex items-center gap-1.5 shadow-sm"
                  title="Ver expediente completo del pedido"
                >
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z" />
                  </svg>
                  Expediente
                </button>
              )}
              <button
                onClick={() => setSelectedStage(null)}
                className="p-2 hover:bg-yeikar-tertiary rounded-xl text-yeikar-neutral/40 hover:text-yeikar-neutral/80 transition-colors"
                title="Cerrar modal"
                aria-label="Cerrar modal"
              >
                <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>

            {/* Materials consumption (Full Width) */}
            <div className="space-y-4">
              <h3 className="text-base font-bold font-headline text-yeikar-secondary border-b border-yeikar-secondary-light/5 pb-2 flex items-center justify-between">
                <span>Materiales que se usarán en esta etapa</span>
                <span className="text-xs font-mono font-normal text-yeikar-neutral/50">
                  ({selectedStage.consumos?.length || 0} registrados)
                </span>
              </h3>

              {/* Consumption form */}
              <form onSubmit={handleAddConsumo} className="grid grid-cols-1 sm:grid-cols-12 gap-2 bg-yeikar-tertiary/30 p-3 rounded-2xl border border-yeikar-secondary-light/5">
                <div className="sm:col-span-7 relative">
                  <div className="relative">
                    <span className="absolute left-2.5 top-1/2 -translate-y-1/2 text-yeikar-neutral/30 text-xs"></span>
                    <input
                      type="text"
                      placeholder="Buscar material..."
                      value={materialSearch}
                      autoComplete="off"
                      required
                      onFocus={() => setShowMaterialDropdown(true)}
                      onChange={(e) => {
                        setMaterialSearch(e.target.value);
                        setShowMaterialDropdown(true);
                        if (!e.target.value) setNewConsumo(prev => ({ ...prev, material_id: '' }));
                      }}
                      className="w-full text-xs bg-white border border-yeikar-secondary-light/10 rounded-xl pl-7 pr-3 py-2.5 focus:outline-none focus:border-yeikar-primary"
                    />
                    {newConsumo.material_id && (
                      <span className="absolute right-2.5 top-1/2 -translate-y-1/2 text-green-500 text-xs"></span>
                    )}
                  </div>
                  {showMaterialDropdown && (
                    <div className="absolute z-50 w-full mt-1 bg-white border border-yeikar-secondary-light/15 rounded-xl shadow-lg max-h-52 overflow-y-auto">
                      {[...materiales]
                        .sort((a, b) => a.nombre.localeCompare(b.nombre, 'es'))
                        .filter(m => m.nombre.toLowerCase().includes(materialSearch.toLowerCase()))
                        .map((m) => (
                          <button
                            key={m.id}
                            type="button"
                            onClick={() => {
                              setNewConsumo(prev => ({ ...prev, material_id: String(m.id) }));
                              setMaterialSearch(m.nombre);
                              setShowMaterialDropdown(false);
                            }}
                            className={`w-full text-left px-3 py-2 text-xs hover:bg-yeikar-tertiary/40 transition-colors border-b border-yeikar-secondary-light/5 last:border-0 ${
                              newConsumo.material_id === String(m.id) ? 'bg-yeikar-primary/10 font-bold' : ''
                            }`}
                          >
                            <span className="font-medium text-yeikar-secondary">{m.nombre}</span>
                            {m.unidad_medida?.abreviatura && (
                              <span className="text-yeikar-neutral/40 ml-1">({m.unidad_medida.abreviatura})</span>
                            )}
                            {inventario[m.id] !== undefined && (
                              <span className={`ml-2 font-mono text-[10px] ${inventario[m.id] <= 0 ? 'text-red-500 font-bold' : 'text-yeikar-neutral/50'}`}>
                                Stock: {inventario[m.id]}
                              </span>
                            )}
                            {m.costo_base > 0 && (
                              <span className="text-emerald-600 font-mono ml-auto float-right">
                                {fmt(m.costo_base)}
                              </span>
                            )}
                          </button>
                        ))}
                      {materiales.filter(m => m.nombre.toLowerCase().includes(materialSearch.toLowerCase())).length === 0 && (
                        <p className="text-center text-yeikar-neutral/40 text-xs py-4">Sin resultados</p>
                      )}
                    </div>
                  )}
                  {showMaterialDropdown && (
                    <div className="fixed inset-0 z-40" onClick={() => setShowMaterialDropdown(false)} />
                  )}
                  <input type="hidden" required value={newConsumo.material_id} />
                </div>
                <div className="sm:col-span-3">
                  <input
                    type="number"
                    step="0.01"
                    placeholder="Cantidad"
                    value={newConsumo.cantidad}
                    onChange={(e) => setNewConsumo(prev => ({ ...prev, cantidad: e.target.value }))}
                    required
                    className="w-full text-xs bg-white border border-yeikar-secondary-light/10 rounded-xl p-2.5 focus:outline-none focus:border-yeikar-primary font-mono"
                  />
                </div>
                <div className="sm:col-span-2">
                  <button
                    type="submit"
                    disabled={consumoSubmitting}
                    className="w-full h-full bg-yeikar-primary text-yeikar-neutral text-xs font-bold font-headline py-2 px-3 rounded-xl hover:bg-yeikar-primary-dark disabled:opacity-50 disabled:cursor-not-allowed transition-colors shadow-sm"
                  >
                    {consumoSubmitting ? 'Guardando...' : '+ Agregar'}
                  </button>
                </div>
              </form>

              {/* Consumption List */}
              <div className="space-y-2 max-h-64 overflow-y-auto pr-1">
                {selectedStage.consumos && selectedStage.consumos.length > 0 ? (
                  selectedStage.consumos.map((c) => {
                    const costo = c.costo_unitario !== undefined && c.costo_unitario !== null ? c.costo_unitario : (c.material?.costo_base || 0);
                    const subtotal = c.cantidad * costo;
                    return (
                      <div key={c.id} className="flex items-center justify-between bg-white border border-yeikar-secondary-light/10 p-3.5 rounded-xl shadow-xs text-xs hover:border-yeikar-primary/30 transition-colors">
                        <div className="min-w-0">
                          <div className="flex items-center gap-2 flex-wrap">
                            <p className="font-bold text-yeikar-secondary text-sm">{c.material?.nombre}</p>
                            {c.seccion && (
                              <span className="text-[9px] font-bold px-1.5 py-0.5 rounded-md bg-stone-100 text-stone-500 border border-stone-200 uppercase">
                                {c.seccion}
                              </span>
                            )}
                          </div>
                          <p className="text-xs text-yeikar-neutral/60 font-mono mt-0.5">
                            Cantidad: <span className="font-bold text-yeikar-secondary">{c.cantidad}</span> | Costo unitario: <span className="font-bold">${costo.toLocaleString('es-CO')}</span>
                          </p>
                          <p className="text-[10px] text-yeikar-neutral/40 mt-0.5">
                            {c.creador_nombre ? `Registrado por ${c.creador_nombre}` : ''}
                            {' · '}
                            <span className="text-emerald-600/70 font-medium">Egreso generado en Gastos</span>
                          </p>
                        </div>
                        <div className="flex items-center gap-4 shrink-0">
                          <span className="font-mono font-bold text-sm text-yeikar-primary">
                            ${subtotal.toLocaleString('es-CO')}
                          </span>
                          <button
                            onClick={() => setConsumoAEliminar(c.id)}
                            className="text-red-500 hover:text-red-700 font-medium text-xs p-1 transition-colors"
                            title="Quitar material (repondrá el stock y revertirá el egreso)"
                          >
                            Eliminar
                          </button>
                        </div>
                      </div>
                    );
                  })
                ) : (
                  <div className="p-8 text-center border border-dashed border-yeikar-secondary-light/15 rounded-2xl text-yeikar-neutral/40 text-xs">
                    No se han registrado aún materiales consumidos para esta etapa.
                  </div>
                )}
              </div>
            </div>

            {/* Resumen de costos de la etapa */}
            {(() => {
              const totalMat = selectedStage.consumos?.reduce((acc, c) => {
                const costo = c.costo_unitario !== undefined && c.costo_unitario !== null ? c.costo_unitario : (c.material?.costo_base || 0);
                return acc + (c.cantidad * costo);
              }, 0) || 0;

              return (
                <div className="bg-yeikar-tertiary/20 border border-yeikar-secondary-light/10 rounded-2xl p-4 flex justify-between items-center text-center">
                  <div className="text-left">
                    <span className="text-[10px] font-bold text-yeikar-neutral/50 block uppercase tracking-wider">TOTAL MATERIALES EN ESTA ETAPA</span>
                    <span className="text-xl font-black text-yeikar-secondary font-mono">${totalMat.toLocaleString('es-CO')}</span>
                  </div>
                  <div className="text-right border-l border-yeikar-secondary-light/10 pl-6">
                    <span className="text-[10px] font-bold text-yeikar-primary block uppercase tracking-wider">COSTO REGISTRADO ETAPA</span>
                    <span className="text-2xl font-black text-yeikar-primary font-mono">${totalMat.toLocaleString('es-CO')}</span>
                  </div>
                </div>
              );
            })()}

            {/* Mano de obra de la etapa */}
            <div className="space-y-4">
              <h3 className="text-base font-bold font-headline text-yeikar-secondary border-b border-yeikar-secondary-light/5 pb-2 flex items-center justify-between">
                <span>Mano de obra de la etapa</span>
                <span className="text-xs font-mono font-normal text-yeikar-neutral/50">
                  ({selectedStage.mano_obras?.length || 0} registrados) · alimenta el costo de la orden
                </span>
              </h3>

              <form onSubmit={handleAddManoObra} className="grid grid-cols-1 sm:grid-cols-12 gap-2 bg-yeikar-tertiary/30 p-3 rounded-2xl border border-yeikar-secondary-light/5">
                <div className="sm:col-span-5">
                  <SearchSelect
                    value={newManoObra.empleado_id}
                    onChange={(v) => setNewManoObra(prev => ({ ...prev, empleado_id: String(v) }))}
                    options={empleados.map((e) => ({ value: e.id, label: `${e.nombre} ${e.apellido}` }))}
                    placeholder="Empleado..."
                  />
                </div>
                <div className="sm:col-span-4">
                  <input
                    type="number"
                    min="0"
                    step="1000"
                    placeholder="Monto ($)"
                    value={newManoObra.monto}
                    onChange={(e) => setNewManoObra(prev => ({ ...prev, monto: e.target.value }))}
                    required
                    className="w-full text-xs bg-white border border-yeikar-secondary-light/10 rounded-xl p-2.5 focus:outline-none focus:border-yeikar-primary font-mono"
                  />
                </div>
                <div className="sm:col-span-3">
                  <button
                    type="submit"
                    disabled={selectedStage.estado !== 'EN_PROCESO'}
                    className="w-full h-full bg-yeikar-primary text-yeikar-neutral text-xs font-bold font-headline py-2 px-3 rounded-xl hover:bg-yeikar-primary-dark disabled:opacity-50 disabled:cursor-not-allowed transition-colors shadow-sm"
                    title={selectedStage.estado !== 'EN_PROCESO' ? 'La etapa debe estar EN PROCESO para registrar mano de obra' : undefined}
                  >
                    + Agregar MO
                  </button>
                </div>
              </form>

              <div className="space-y-2 max-h-48 overflow-y-auto pr-1">
                {selectedStage.mano_obras && selectedStage.mano_obras.length > 0 ? (
                  selectedStage.mano_obras.map((mo) => (
                    <div key={mo.id} className="flex items-center justify-between bg-white border border-yeikar-secondary-light/10 p-3.5 rounded-xl shadow-xs text-xs hover:border-yeikar-primary/30 transition-colors">
                      <div className="min-w-0">
                        <p className="font-bold text-yeikar-secondary text-sm">
                          {mo.empleado ? `${mo.empleado.nombre} ${mo.empleado.apellido}` : `Empleado #${mo.empleado_id}`}
                        </p>
                        <p className="text-[10px] text-yeikar-neutral/40 mt-0.5">
                          {mo.creador_nombre ? `Registrado por ${mo.creador_nombre}` : ''}
                          {mo.pagado ? ' · Egreso generado en Gastos' : ''}
                        </p>
                      </div>
                      <div className="flex items-center gap-3 shrink-0">
                        <span className={`font-mono font-bold text-sm ${mo.pagado ? 'text-emerald-600' : 'text-yeikar-primary'}`}>
                          ${(mo.monto * (1 + (mo.porcentaje_recargo || 0) / 100)).toLocaleString('es-CO')}
                        </span>
                        <button
                          type="button"
                          onClick={() => handleTogglePagoManoObra(mo.id, !!mo.pagado)}
                          className={`px-2.5 py-1 rounded-lg text-[10px] font-bold transition-colors ${
                            mo.pagado
                              ? 'bg-emerald-100 text-emerald-700 hover:bg-emerald-200'
                              : 'bg-yeikar-tertiary text-yeikar-neutral/60 hover:bg-yeikar-secondary-light/20'
                          }`}
                          title={mo.pagado ? 'Revertir pago (elimina el egreso)' : 'Marcar como pagada (genera el egreso en Gastos)'}
                        >
                          {mo.pagado ? 'Pagada' : 'Marcar pago'}
                        </button>
                        {!mo.pagado && (
                          <button
                            type="button"
                            onClick={() => setManoObraAEliminar(mo.id)}
                            className="text-red-500 hover:text-red-700 font-medium text-xs p-1 transition-colors"
                            title="Eliminar mano de obra"
                          >
                            Eliminar
                          </button>
                        )}
                      </div>
                    </div>
                  ))
                ) : (
                  <div className="p-6 text-center border border-dashed border-yeikar-secondary-light/15 rounded-2xl text-yeikar-neutral/40 text-xs">
                    No se ha registrado mano de obra en esta etapa.
                  </div>
                )}
              </div>
            </div>

            {/* Referencia de Componentes del Producto */}
            {(() => {
              const SECCION_COLORS: Record<string, string> = {
                EBANISTERIA: 'bg-amber-100 text-amber-800 border-amber-200',
                TAPICERIA: 'bg-purple-100 text-purple-800 border-purple-200',
                PINTURA: 'bg-sky-100 text-sky-800 border-sky-200',
                TERMINACION: 'bg-emerald-100 text-emerald-800 border-emerald-200',
                NOCHEROS: 'bg-rose-100 text-rose-800 border-rose-200',
                MANO_DE_OBRA: 'bg-blue-100 text-blue-800 border-blue-200',
              };
              const badge = (s: string, activa = false) =>
                `${activa ? 'ring-2 ring-yeikar-primary/60 ' : ''}text-[10px] font-bold px-2 py-0.5 rounded-md border ${SECCION_COLORS[s] || 'bg-stone-100 text-stone-600 border-stone-200'}`;

              if (loadingReceta) {
                return (
                  <div className="border border-dashed border-yeikar-secondary-light/10 rounded-2xl p-4 text-center text-xs text-yeikar-neutral/40">
                    Cargando receta de referencia...
                  </div>
                );
              }

              if (!referenciaReceta || referenciaReceta.materiales.length === 0) {
                return (
                  <div className="border border-dashed border-yeikar-secondary-light/10 rounded-2xl p-4 text-center text-xs text-yeikar-neutral/40">
                    Este producto no tiene receta de materiales definida.
                  </div>
                );
              }

              // Agrupar por sección y resaltar la sección del área actual de la etapa
              const porSeccion: Record<string, typeof referenciaReceta.materiales> = {};
              referenciaReceta.materiales.forEach((m) => {
                (porSeccion[m.seccion] = porSeccion[m.seccion] || []).push(m);
              });

              return (
                <div className="border border-dashed border-yeikar-primary/20 bg-yeikar-primary/5 rounded-2xl p-4 space-y-3">
                  <div className="flex items-center gap-2">
                    <svg className="w-4 h-4 text-yeikar-primary/60" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
                    </svg>
                    <h3 className="text-xs font-bold font-headline text-yeikar-neutral/60 uppercase tracking-wider">
                      Componentes del producto
                    </h3>
                    <span className="text-[10px] font-mono text-yeikar-neutral/40 ml-auto">
                      {referenciaReceta.producto_nombre}
                      {referenciaReceta.dimensiones.ancho && referenciaReceta.dimensiones.largo
                        ? ` · ${referenciaReceta.dimensiones.ancho}m × ${referenciaReceta.dimensiones.largo}m`
                        : ''}
                    </span>
                  </div>
                  {referenciaReceta.seccion_actual && (
                    <p className="text-[10px] font-bold text-yeikar-primary bg-yeikar-primary/10 rounded-lg px-2.5 py-1 w-fit">
                      Esta área trabaja con la sección «{referenciaReceta.seccion_actual}» — cantidades escaladas a las medidas del pedido
                    </p>
                  )}
                  <div className="space-y-3 max-h-64 overflow-y-auto pr-1">
                    {Object.entries(porSeccion).map(([seccion, materiales]) => {
                      const activa = referenciaReceta.seccion_actual === seccion;
                      return (
                        <div key={seccion}>
                          <div className="flex items-center gap-2 mb-1.5">
                            <span className={badge(seccion, activa)}>{seccion}</span>
                            <span className="text-[10px] font-mono text-yeikar-neutral/40">
                              {materiales.length} material(es)
                            </span>
                          </div>
                          <div className="space-y-1.5">
                            {materiales.map((m, i) => (
                              <div
                                key={`${m.material_id}-${i}`}
                                className={`flex items-center justify-between bg-white/70 border border-yeikar-secondary-light/5 p-2.5 rounded-xl text-xs ${m.condicion_cumplida ? '' : 'opacity-50'}`}
                              >
                                <div className="flex items-center gap-2 min-w-0 flex-1">
                                  <span className="font-semibold text-yeikar-secondary truncate">{m.nombre}</span>
                                  <span className="text-[9px] font-mono text-yeikar-neutral/40 uppercase">{m.tipo_escala}</span>
                                  {!m.condicion_cumplida && (
                                    <span className="text-[9px] font-bold text-red-500 uppercase">No aplica para estas medidas</span>
                                  )}
                                </div>
                                <div className="flex items-center gap-3 shrink-0 ml-2">
                                  <span className="font-mono font-bold text-yeikar-neutral/80">
                                    {m.cantidad_esperada}
                                    {Math.abs(m.cantidad_esperada - m.cantidad_base) > 0.001 && (
                                      <span className="text-yeikar-neutral/40 font-normal"> (base {m.cantidad_base})</span>
                                    )}
                                  </span>
                                  <span className="text-yeikar-neutral/40 w-6 text-right">{m.unidad}</span>
                                  <span className="font-mono text-yeikar-neutral/50 w-20 text-right">
                                    ${m.costo_unitario.toLocaleString('es-CO')}
                                  </span>
                                </div>
                              </div>
                            ))}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              );
            })()}

            {/* Historial de la orden: todas las áreas por las que pasó */}
            {ordenCompleta?.etapas && ordenCompleta.etapas.length > 0 && (
              <div className="space-y-3">
                <h3 className="text-base font-bold font-headline text-yeikar-secondary border-b border-yeikar-secondary-light/5 pb-2">
                  Historial de la orden #{selectedStage.orden_produccion_id}
                </h3>
                <div className="space-y-1.5 max-h-48 overflow-y-auto pr-1">
                  {[...ordenCompleta.etapas]
                    .sort((a, b) => (a.id || 0) - (b.id || 0))
                    .map((et) => (
                      <div key={et.id} className="flex items-center justify-between bg-yeikar-tertiary/30 border border-yeikar-secondary-light/10 p-2.5 rounded-xl text-xs">
                        <div className="flex items-center gap-2 min-w-0">
                          <span className={`w-2 h-2 rounded-full shrink-0 ${
                            et.estado === 'COMPLETADA' ? 'bg-green-500' : et.estado === 'EN_PROCESO' ? 'bg-amber-400' : et.estado === 'PAUSADA' ? 'bg-red-400' : 'bg-blue-400'
                          }`} />
                          <span className="font-bold text-yeikar-secondary">{et.area?.nombre || `Área #${et.area_id}`}</span>
                          {et.es_retrabajo && (
                            <span className="text-[9px] font-bold px-1.5 py-0.5 rounded-md bg-amber-100 text-amber-700 uppercase">Retrabajo</span>
                          )}
                        </div>
                        <div className="flex items-center gap-3 shrink-0 text-[10px] font-mono text-yeikar-neutral/50">
                          {et.empleado_responsable && (
                            <span>{et.empleado_responsable.nombre} {et.empleado_responsable.apellido}</span>
                          )}
                          <span className="font-bold">{et.estado.replace('_', ' ')}</span>
                          {et.fecha_fin && <span>{new Date(et.fecha_fin).toLocaleDateString('es-CO')}</span>}
                        </div>
                      </div>
                    ))}
                </div>
              </div>
            )}

            {/* Costo calculado de la orden (si ya se finalizó o se calculó) */}
            {ordenCompleta?.costo && (
              <div className="bg-stone-50 border border-yeikar-secondary-light/10 rounded-2xl p-4">
                <h3 className="text-xs font-bold font-headline text-yeikar-neutral/60 uppercase tracking-wider mb-3">
                  Costo calculado de la orden
                </h3>
                <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 text-center">
                  <div className="bg-white rounded-xl border border-yeikar-secondary-light/10 p-2.5">
                    <span className="text-[9px] font-bold text-yeikar-neutral/50 block uppercase">Materiales</span>
                    <span className="font-mono font-bold text-sm text-yeikar-secondary">${ordenCompleta.costo.costo_material.toLocaleString('es-CO')}</span>
                  </div>
                  <div className="bg-white rounded-xl border border-yeikar-secondary-light/10 p-2.5">
                    <span className="text-[9px] font-bold text-yeikar-neutral/50 block uppercase">Mano de obra</span>
                    <span className="font-mono font-bold text-sm text-yeikar-secondary">${ordenCompleta.costo.costo_mano_obra.toLocaleString('es-CO')}</span>
                  </div>
                  <div className="bg-white rounded-xl border border-yeikar-secondary-light/10 p-2.5">
                    <span className="text-[9px] font-bold text-yeikar-neutral/50 block uppercase">Gastos</span>
                    <span className="font-mono font-bold text-sm text-yeikar-secondary">${ordenCompleta.costo.costo_gastos.toLocaleString('es-CO')}</span>
                  </div>
                  <div className="bg-yeikar-primary/10 rounded-xl border border-yeikar-primary/20 p-2.5">
                    <span className="text-[9px] font-bold text-yeikar-primary/70 block uppercase">Costo total</span>
                    <span className="font-mono font-bold text-sm text-yeikar-primary">${ordenCompleta.costo.costo_total.toLocaleString('es-CO')}</span>
                  </div>
                  <div className="bg-white rounded-xl border border-yeikar-secondary-light/10 p-2.5">
                    <span className="text-[9px] font-bold text-yeikar-neutral/50 block uppercase">Precio venta (ganancia {ordenCompleta.costo.ganancia_porcentaje}%)</span>
                    <span className="font-mono font-bold text-sm text-yeikar-secondary">${ordenCompleta.costo.precio_venta_calculado.toLocaleString('es-CO')}</span>
                  </div>
                  <div className="bg-white rounded-xl border border-yeikar-secondary-light/10 p-2.5">
                    <span className="text-[9px] font-bold text-yeikar-neutral/50 block uppercase">Impuestos base</span>
                    <span className="font-mono font-bold text-sm text-yeikar-secondary">${ordenCompleta.costo.precio_impuestos_base.toLocaleString('es-CO')}</span>
                  </div>
                </div>
              </div>
            )}

            {/* Modal Footer */}
            <div className="flex items-center justify-end pt-4 border-t border-yeikar-secondary-light/10">
              <button
                type="button"
                onClick={() => setSelectedStage(null)}
                className="bg-yeikar-primary text-yeikar-neutral hover:bg-yeikar-primary-light px-8 py-2.5 rounded-xl text-sm font-bold font-headline shadow-md transition-all"
              >
                Cerrar
              </button>
            </div>

          </div>
        </div>
          );
        })()
      )}

      {/* Modal Pasar a Area */}
      {showPasarModal && pasarStage && (
        <div
          className="fixed inset-0 bg-yeikar-secondary/60 backdrop-blur-sm flex items-center justify-center p-4 z-50"
          onClick={closePasarModal}
        >
          <div className="bg-white rounded-3xl shadow-xl border border-yeikar-secondary-light/10 max-w-lg w-full p-6 max-h-[90vh] overflow-y-auto" role="dialog" aria-modal="true" aria-label="Mover etapa a nueva área" onClick={(e) => e.stopPropagation()}>
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
                    label: `${empleado.nombre} ${empleado.apellido}`,
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
                      {empleado.nombre} {empleado.apellido}
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
          <div className="bg-white rounded-3xl shadow-xl border border-yeikar-secondary-light/10 max-w-sm w-full p-6" role="dialog" aria-modal="true" aria-label="Añadir etapa a orden" onClick={(e) => e.stopPropagation()}>
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
                  options={empleados.map(e => ({ value: e.id, label: `${e.nombre} ${e.apellido}` }))}
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
        message={`¿Estás seguro de finalizar la orden #${confirmFinalizarId ?? ''}? Esto calculará sus costos definitivos y la cerrará.`}
        confirmLabel="Sí, finalizar"
        danger={false}
        onConfirm={ejecutarFinalizarOrden}
        onCancel={() => setConfirmFinalizarId(null)}
      />
      <ConfirmDialog
        open={consumoAEliminar !== null}
        title="Eliminar consumo de material"
        message="Se repondrá el stock descontado y se revertirá el egreso generado en Gastos. ¿Continuar?"
        confirmLabel="Sí, eliminar"
        danger
        onConfirm={ejecutarEliminarConsumo}
        onCancel={() => setConsumoAEliminar(null)}
      />
      <ConfirmDialog
        open={manoObraAEliminar !== null}
        title="Eliminar mano de obra"
        message="Se quitará el registro de mano de obra de la etapa. ¿Continuar?"
        confirmLabel="Sí, eliminar"
        danger
        onConfirm={ejecutarEliminarManoObra}
        onCancel={() => setManoObraAEliminar(null)}
      />
    </div>
  );
}
