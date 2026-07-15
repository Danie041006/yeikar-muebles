import React, { useEffect, useState } from 'react';
import {
  DndContext,
  useSensor,
  useSensors,
  PointerSensor,
  KeyboardSensor,
  DragEndEvent,
  useDroppable,
  useDraggable,
} from '@dnd-kit/core';
import { sortableKeyboardCoordinates } from '@dnd-kit/sortable';
import { produccionService, OrdenProduccion, EtapaProduccion, Area } from '../services/produccionService';
import api from '../services/api';

// Empleado interface for selection
interface Empleado {
  id: number;
  nombre: string;
  apellido: string;
}

// Material interface for selection
interface Material {
  id: number;
  nombre: string;
}

// Droppable Column Component
interface ColumnProps {
  area: Area;
  stages: EtapaProduccion[];
  onCardClick: (stage: EtapaProduccion) => void;
  onStatusChange: (stageId: number, newStatus: string) => void;
}

function KanbanColumn({ area, stages, onCardClick, onStatusChange }: ColumnProps) {
  const { setNodeRef, isOver } = useDroppable({
    id: `column-${area.id}`,
  });

  return (
    <div
      ref={setNodeRef}
      className={`flex flex-col min-h-[500px] w-72 bg-yeikar-tertiary/40 border rounded-2xl p-4 transition-all duration-200 ${
        isOver
          ? 'border-yeikar-primary bg-yeikar-primary/5 shadow-inner scale-[1.01]'
          : 'border-yeikar-secondary-light/10 shadow-sm'
      }`}
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
            <span>Arrastra el producto aquí</span>
          </div>
        ) : (
          stages.map((stage) => (
            <KanbanCard
              key={stage.id}
              stage={stage}
              onClick={() => onCardClick(stage)}
              onStatusChange={onStatusChange}
            />
          ))
        )}
      </div>
    </div>
  );
}

// Draggable Card Component
interface CardProps {
  stage: EtapaProduccion;
  onClick: () => void;
  onStatusChange: (stageId: number, newStatus: string) => void;
}

function KanbanCard({ stage, onClick, onStatusChange }: CardProps) {
  const { attributes, listeners, setNodeRef, transform, isDragging } = useDraggable({
    id: `card-${stage.id}`,
  });

  const style = transform
    ? {
        transform: `translate3d(${transform.x}px, ${transform.y}px, 0)`,
        zIndex: 50,
      }
    : undefined;

  const statusColors = {
    ASIGNADA: 'bg-blue-50 text-blue-700 border-blue-200',
    EN_PROCESO: 'bg-amber-50 text-amber-700 border-amber-200 animate-pulse',
    PAUSADA: 'bg-red-50 text-red-700 border-red-200',
    COMPLETADA: 'bg-green-50 text-green-700 border-green-200',
  };

  return (
    <div
      ref={setNodeRef}
      style={style}
      className={`border rounded-xl p-4 shadow-sm hover:shadow-md transition-shadow cursor-default group relative overflow-hidden ${
        isDragging ? 'opacity-40 border-yeikar-primary' : ''
      } ${stage.estado === 'COMPLETADA' ? 'bg-gray-50 border-gray-200 opacity-75' : 'bg-white border-yeikar-secondary-light/10'}`}
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
        
        {/* Status selector */}
        <select
          value={stage.estado}
          onChange={(e) => {
            e.stopPropagation();
            onStatusChange(stage.id, e.target.value);
          }}
          className={`text-[10px] font-bold px-2 py-0.5 rounded border ${
            statusColors[stage.estado]
          } focus:outline-none focus:ring-1 focus:ring-yeikar-primary cursor-pointer`}
        >
          <option value="ASIGNADA">ASIGNADA</option>
          <option value="EN_PROCESO">EN PROCESO</option>
          <option value="PAUSADA">PAUSADA</option>
          <option value="COMPLETADA">COMPLETADA</option>
        </select>
      </div>

      {/* Product Name & Description */}
      <div onClick={onClick} className="cursor-pointer space-y-1">
        <h4 className="font-headline font-bold text-yeikar-secondary text-sm group-hover:text-yeikar-primary transition-colors">
          {stage.orden?.detalle_pedido?.producto?.nombre 
            ? stage.orden.detalle_pedido.producto.nombre 
            : stage.orden_produccion_id 
            ? `Orden de Producción #${stage.orden_produccion_id}` 
            : 'Producto en Fabricación'}
        </h4>
        {stage.observaciones && (
          <p className="text-xs text-yeikar-neutral/60 line-clamp-2">
            {stage.observaciones}
          </p>
        )}
      </div>

      {/* Drag handle area & Footer */}
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

        {/* Drag handle icon */}
        <div
          {...attributes}
          {...listeners}
          className="cursor-grab active:cursor-grabbing p-1 hover:bg-yeikar-tertiary rounded text-yeikar-neutral/30 hover:text-yeikar-neutral/60 transition-colors"
          title="Arrastrar para mover de área"
        >
          <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
            <path d="M7 2a2 2 0 10.001 4.001A2 2 0 007 2zm0 6a2 2 0 10.001 4.001A2 2 0 007 8zm0 6a2 2 0 10.001 4.001A2 2 0 007 14zm6-12a2 2 0 10.001 4.001A2 2 0 0013 2zm0 6a2 2 0 10.001 4.001A2 2 0 0013 8zm0 6a2 2 0 10.001 4.001A2 2 0 0013 14z" />
          </svg>
        </div>
      </div>
    </div>
  );
}

// Main Production Kanban Page
export default function ProduccionKanban() {
  const [areas, setAreas] = useState<Area[]>([]);
  const [stages, setStages] = useState<EtapaProduccion[]>([]);
  const [ordenesSinEtapaActiva, setOrdenesSinEtapaActiva] = useState<OrdenProduccion[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [showCompleted, setShowCompleted] = useState(false);
  const [selectedStage, setSelectedStage] = useState<EtapaProduccion | null>(null);

  // New stage modal state
  const [ordenParaNuevaEtapa, setOrdenParaNuevaEtapa] = useState<number | null>(null);
  const [nuevaEtapaForm, setNuevaEtapaForm] = useState({ area_id: '', empleado_id: '', observaciones: '' });

  // Detail Modal Forms state
  const [empleados, setEmpleados] = useState<Empleado[]>([]);
  const [materiales, setMateriales] = useState<Material[]>([]);
  const [newConsumo, setNewConsumo] = useState({ material_id: '', cantidad: '', observaciones: '' });
  const [newManoObra, setNewManoObra] = useState({ empleado_id: '', monto: '', observaciones: '' });

  const sensors = useSensors(
    useSensor(PointerSensor, {
      activationConstraint: {
        distance: 8,
      },
    }),
    useSensor(KeyboardSensor, {
      coordinateGetter: sortableKeyboardCoordinates,
    })
  );

  const fetchKanbanData = async () => {
    try {
      setLoading(true);
      const [areasData, ordenesData] = await Promise.all([
        produccionService.getAreas(),
        produccionService.getOrdenes(),
      ]);
      
      setAreas(areasData.filter(a => a.nombre !== 'Depósito'));

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
    } catch (error) {
      console.error('Error fetching production kanban data:', error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchKanbanData();
    // Cargar empleados y materiales para el modal
    api.get('/empleado/').then((r) => setEmpleados(r.data)).catch(() => {});
    api.get('/material/').then((r) => setMateriales(r.data)).catch(() => {});
  }, []);

  const handleDragEnd = async (event: DragEndEvent) => {
    const { active, over } = event;
    if (!over) return;

    const cardId = active.id.toString().replace('card-', '');
    const columnId = over.id.toString().replace('column-', '');

    const stageId = parseInt(cardId);
    const targetAreaId = parseInt(columnId);

    const draggedStage = stages.find((s) => s.id === stageId);
    if (!draggedStage || draggedStage.area_id === targetAreaId) return;

    try {
      // Optimistic update in frontend
      setStages((prev) =>
        prev.map((s) => (s.id === stageId ? { ...s, area_id: targetAreaId } : s))
      );

      // En el backend, actualizar la etapa actual
      // 1. Completar la etapa actual
      await produccionService.updateEstadoEtapa(stageId, 'COMPLETADA');

      // 2. Crear o actualizar la siguiente etapa en la nueva área
      // Consultar la orden de producción para ver si ya tiene etapa en esa área
      const orden = await produccionService.getOrdenById(draggedStage.orden_produccion_id);
      const existingNextStage = orden.etapas.find((e) => e.area_id === targetAreaId);

      if (existingNextStage) {
        // Si ya existe la etapa en esa área, la pasamos a EN_PROCESO
        await produccionService.updateEstadoEtapa(existingNextStage.id, 'EN_PROCESO');
      } else {
        // Si no existe, creamos una nueva etapa para esa área
        await api.post('/produccion/etapa/', {
          orden_produccion_id: draggedStage.orden_produccion_id,
          area_id: targetAreaId,
          empleado_responsable_id: draggedStage.empleado_responsable_id || 1, // Fallback
          estado: 'EN_PROCESO',
          observaciones: 'Creado por transición en Kanban',
          fecha_inicio: new Date().toISOString(),
        });
      }

      // Volver a cargar para sincronizar
      fetchKanbanData();
    } catch (error) {
      console.error('Error transitioning stage:', error);
      fetchKanbanData(); // Revert on error
    }
  };

  const handleStatusChange = async (stageId: number, newStatus: string) => {
    try {
      await produccionService.updateEstadoEtapa(stageId, newStatus);
      fetchKanbanData();
      if (selectedStage && selectedStage.id === stageId) {
        // Actualizar modal si está abierto
        const updated = await api.get<EtapaProduccion>(`/produccion/etapa/${stageId}`);
        setSelectedStage(updated.data);
      }
    } catch (error) {
      console.error('Error changing stage status:', error);
    }
  };

  const handleAddConsumo = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedStage || !newConsumo.material_id || !newConsumo.cantidad) return;
    try {
      await produccionService.registrarConsumo({
        etapa_produccion_id: selectedStage.id,
        material_id: parseInt(newConsumo.material_id),
        cantidad: parseFloat(newConsumo.cantidad),
        fecha: new Date().toISOString(),
        observaciones: newConsumo.observaciones || undefined,
      });
      // Recargar etapa
      const updated = await api.get<EtapaProduccion>(`/produccion/etapa/${selectedStage.id}`);
      setSelectedStage(updated.data);
      setNewConsumo({ material_id: '', cantidad: '', observaciones: '' });
      fetchKanbanData();
    } catch (error: any) {
      alert(error.response?.data?.detail || 'Error al registrar consumo. Verifique el inventario.');
    }
  };

  const handleDeleteConsumo = async (consumoId: number) => {
    if (!selectedStage) return;
    try {
      await produccionService.eliminarConsumo(consumoId);
      const updated = await api.get<EtapaProduccion>(`/produccion/etapa/${selectedStage.id}`);
      setSelectedStage(updated.data);
      fetchKanbanData();
    } catch (error) {
      console.error('Error deleting consumption:', error);
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
    } catch (error) {
      console.error('Error adding labor cost:', error);
    }
  };

  const handleDeleteManoObra = async (manoObraId: number) => {
    if (!selectedStage) return;
    try {
      await produccionService.eliminarManoObra(manoObraId);
      const updated = await api.get<EtapaProduccion>(`/produccion/etapa/${selectedStage.id}`);
      setSelectedStage(updated.data);
      fetchKanbanData();
    } catch (error) {
      console.error('Error deleting labor cost:', error);
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
    } catch (error) {
      console.error('Error toggling labor payment status:', error);
      alert('Error al actualizar el estado de pago.');
    }
  };

  const handleFinalizarOrden = async (ordenId: number) => {
    if (!window.confirm(`¿Estás seguro de finalizar la orden #${ordenId}? Esto calculará sus costos definitivos y la cerrará.`)) return;
    try {
      // Una sola petición: el backend calcula costos al pasar a FINALIZADA
      await api.put(`/produccion/orden/${ordenId}/estado?estado=FINALIZADA`);
      alert(`Orden #${ordenId} finalizada. Los costos se calcularon automáticamente en el servidor.`);
      fetchKanbanData();
    } catch (error) {
      console.error('Error finalizing order:', error);
      alert('Error al finalizar la orden.');
    }
  };


  const handleSubmitNuevaEtapa = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!ordenParaNuevaEtapa || !nuevaEtapaForm.area_id || !nuevaEtapaForm.empleado_id) return;
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
    } catch (error) {
      console.error('Error creating stage:', error);
      alert('Error al crear la etapa.');
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
    return idMatch || obsMatch || empMatch;
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
              placeholder="Buscar por orden o responsable..."
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

              <div className="flex flex-wrap gap-2 mt-2">
                {ordenesSinEtapaActiva.map((o) => (
                  <div key={o.id} className="bg-amber-100 text-amber-800 font-mono text-xs font-bold px-3 py-1.5 rounded-lg border border-amber-200 flex items-center gap-3">
                    <span>Orden #{o.id}</span>
                    <div className="flex items-center gap-1 border-l border-amber-300 pl-2">
                      <button
                        onClick={() => setOrdenParaNuevaEtapa(o.id)}
                        className="px-2 py-0.5 bg-amber-200 hover:bg-amber-300 rounded text-[10px] transition-colors"
                        title="Añadir Etapa"
                      >
                        Añadir Etapa
                      </button>
                      <button
                        onClick={() => handleFinalizarOrden(o.id)}
                        className="px-2 py-0.5 bg-green-500 hover:bg-green-600 text-white rounded text-[10px] transition-colors"
                        title="Finalizar Orden"
                      >
                        Finalizar
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
      ) : (
        <DndContext sensors={sensors} onDragEnd={handleDragEnd}>
          <div className="flex gap-5 overflow-x-auto pb-4 pt-1">
            {areas.map((area) => {
              const areaStages = filteredStages.filter((s) => s.area_id === area.id);
              return (
                <KanbanColumn
                  key={area.id}
                  area={area}
                  stages={areaStages}
                  onCardClick={setSelectedStage}
                  onStatusChange={handleStatusChange}
                />
              );
            })}
          </div>
        </DndContext>
      )}

      {/* Details Modal */}
      {selectedStage && (
        <div className="fixed inset-0 bg-yeikar-secondary/60 backdrop-blur-sm flex items-center justify-center p-4 z-50 overflow-y-auto">
          <div className="bg-white rounded-3xl shadow-xl border border-yeikar-secondary-light/10 max-w-4xl w-full p-6 space-y-6 max-h-[90vh] overflow-y-auto relative">
            
            {/* Modal Header */}
            <div className="flex items-start justify-between border-b border-yeikar-secondary-light/5 pb-4">
              <div>
                <span className="text-xs font-mono font-bold text-yeikar-neutral/40">
                  DETALLE DE ETAPA #{selectedStage.id}
                </span>
                <h2 className="text-2xl font-black font-headline text-yeikar-secondary tracking-tight">
                  Orden de Producción #{selectedStage.orden_produccion_id}
                </h2>
                <p className="text-sm text-yeikar-neutral/60 mt-1">
                  Área: <span className="font-bold text-yeikar-primary">{selectedStage.area?.nombre}</span> | Estado:{' '}
                  <span className="font-bold">{selectedStage.estado}</span>
                </p>
              </div>
              <button
                onClick={() => setSelectedStage(null)}
                className="p-2 hover:bg-yeikar-tertiary rounded-xl text-yeikar-neutral/40 hover:text-yeikar-neutral/80 transition-colors"
              >
                <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              {/* Left Column: Materials consumption */}
              <div className="space-y-4">
                <h3 className="text-base font-bold font-headline text-yeikar-secondary border-b border-yeikar-secondary-light/5 pb-2">
                  Materiales que se usarán en esta etapa
                </h3>
                
                {/* Consumption form */}
                <form onSubmit={handleAddConsumo} className="flex gap-2 bg-yeikar-tertiary/30 p-3 rounded-2xl border border-yeikar-secondary-light/5">
                  <div className="flex-1 space-y-2">
                    <select
                      value={newConsumo.material_id}
                      onChange={(e) => setNewConsumo(prev => ({ ...prev, material_id: e.target.value }))}
                      required
                      className="w-full text-xs bg-white border border-yeikar-secondary-light/10 rounded-lg p-2 focus:outline-none focus:border-yeikar-primary"
                    >
                      <option value="">Escoja el material a usar</option>
                      {materiales.map((m) => (
                        <option key={m.id} value={m.id}>
                          {m.nombre}
                        </option>
                      ))}
                    </select>
                    <input
                      type="number"
                      step="0.01"
                      placeholder="Cantidad"
                      value={newConsumo.cantidad}
                      onChange={(e) => setNewConsumo(prev => ({ ...prev, cantidad: e.target.value }))}
                      required
                      className="w-full text-xs bg-white border border-yeikar-secondary-light/10 rounded-lg p-2 focus:outline-none focus:border-yeikar-primary"
                    />
                  </div>
                  <button
                    type="submit"
                    className="bg-yeikar-primary text-yeikar-neutral text-xs font-bold font-headline px-4 rounded-xl hover:bg-yeikar-primary-dark transition-colors"
                  >
                    Agregar
                  </button>
                </form>

                {/* Consumption List */}
                <div className="space-y-2 max-h-60 overflow-y-auto">
                  {selectedStage.consumos && selectedStage.consumos.length > 0 ? (
                    selectedStage.consumos.map((c) => {
                      const costo = c.costo_unitario !== undefined && c.costo_unitario !== null ? c.costo_unitario : (c.material?.costo_base || 0);
                      const subtotal = c.cantidad * costo;
                      return (
                        <div key={c.id} className="flex items-center justify-between bg-white border border-yeikar-secondary-light/5 p-3 rounded-xl shadow-xs text-xs">
                          <div>
                            <p className="font-bold text-yeikar-secondary">{c.material?.nombre}</p>
                            <p className="text-[10px] text-yeikar-neutral/50">
                              Cant: <span className="font-mono font-bold">{c.cantidad}</span> | Costo: <span className="font-mono">${costo.toLocaleString('es-CO')}</span> | Subtot: <span className="font-mono font-bold text-yeikar-primary">${subtotal.toLocaleString('es-CO')}</span>
                            </p>
                          </div>
                          <button
                            onClick={() => handleDeleteConsumo(c.id)}
                            className="text-red-500 hover:text-red-700 transition-colors p-1"
                          >
                            Eliminar
                          </button>
                        </div>
                      );
                    })
                  ) : (
                    <p className="text-xs text-yeikar-neutral/40 italic">No se han registrado aún materiales para esta etapa.</p>
                  )}
                </div>
              </div>

              {/* Right Column: Labor / Employees */}
              <div className="space-y-4">
                <h3 className="text-base font-bold font-headline text-yeikar-secondary border-b border-yeikar-secondary-light/5 pb-2">
                  Mano de Obra / Operarios
                </h3>

                {/* Labor form */}
                <form onSubmit={handleAddManoObra} className="flex gap-2 bg-yeikar-tertiary/30 p-3 rounded-2xl border border-yeikar-secondary-light/5">
                  <div className="flex-1 space-y-2">
                    <select
                      value={newManoObra.empleado_id}
                      onChange={(e) => setNewManoObra(prev => ({ ...prev, empleado_id: e.target.value }))}
                      required
                      className="w-full text-xs bg-white border border-yeikar-secondary-light/10 rounded-lg p-2 focus:outline-none focus:border-yeikar-primary"
                    >
                      <option value="">Seleccione Operario</option>
                      {empleados.map((emp) => (
                        <option key={emp.id} value={emp.id}>
                          {emp.nombre} {emp.apellido}
                        </option>
                      ))}
                    </select>
                    <input
                      type="number"
                      step="0.01"
                      placeholder="Monto Mano Obra ($)"
                      value={newManoObra.monto}
                      onChange={(e) => setNewManoObra(prev => ({ ...prev, monto: e.target.value }))}
                      required
                      className="w-full text-xs bg-white border border-yeikar-secondary-light/10 rounded-lg p-2 focus:outline-none focus:border-yeikar-primary"
                    />
                  </div>
                  <button
                    type="submit"
                    className="bg-yeikar-secondary text-yeikar-tertiary text-xs font-bold font-headline px-4 rounded-xl hover:bg-yeikar-secondary-light transition-colors"
                  >
                    Registrar
                  </button>
                </form>

                {/* Labor List */}
                <div className="space-y-2 max-h-60 overflow-y-auto">
                  {selectedStage.mano_obras && selectedStage.mano_obras.length > 0 ? (
                    selectedStage.mano_obras.map((mo) => (
                      <div key={mo.id} className="flex items-center justify-between bg-white border border-yeikar-secondary-light/5 p-3 rounded-xl shadow-xs text-xs">
                        <div className="flex-1">
                          <div className="flex items-center gap-2">
                            <p className="font-bold text-yeikar-secondary">
                              {mo.empleado ? `${mo.empleado.nombre} ${mo.empleado.apellido}` : 'Empleado'}
                            </p>
                            <button
                              type="button"
                              onClick={() => handleTogglePagoManoObra(mo.id, !!mo.pagado)}
                              className={`text-[9px] font-extrabold px-1.5 py-0.5 rounded transition-all ${
                                mo.pagado
                                  ? 'bg-green-100 text-green-800 hover:bg-green-200'
                                  : 'bg-red-100 text-red-800 hover:bg-red-200'
                              }`}
                            >
                              {mo.pagado ? 'PAGADA' : 'PENDIENTE'}
                            </button>
                          </div>
                          <p className="text-[10px] text-yeikar-neutral/50 font-mono mt-0.5">
                            Monto: ${mo.monto.toLocaleString('es-CO')}
                          </p>
                        </div>
                        <button
                          onClick={() => handleDeleteManoObra(mo.id)}
                          className="text-red-500 hover:text-red-700 transition-colors p-1 ml-2"
                        >
                          Eliminar
                        </button>
                      </div>
                    ))
                  ) : (
                    <p className="text-xs text-yeikar-neutral/40 italic">No se ha registrado mano de obra.</p>
                  )}
                </div>
              </div>
            </div>

            {/* Resumen de costos de la etapa */}
            {(() => {
              const totalMat = selectedStage.consumos?.reduce((acc, c) => {
                const costo = c.costo_unitario !== undefined && c.costo_unitario !== null ? c.costo_unitario : (c.material?.costo_base || 0);
                return acc + (c.cantidad * costo);
              }, 0) || 0;
              const totalMo = selectedStage.mano_obras?.reduce((acc, mo) => acc + mo.monto, 0) || 0;
              const totalMoPagada = selectedStage.mano_obras?.reduce((acc, mo) => acc + (mo.pagado ? mo.monto : 0), 0) || 0;
              const totalMoPendiente = totalMo - totalMoPagada;
              const totalEtapa = totalMat + totalMo;

              return (
                <div className="bg-yeikar-tertiary/20 border border-yeikar-secondary-light/5 rounded-2xl p-4 grid grid-cols-2 md:grid-cols-4 gap-4 text-center">
                  <div>
                    <span className="text-[10px] font-bold text-yeikar-neutral/50 block">TOTAL MATERIALES</span>
                    <span className="text-base font-black text-yeikar-secondary font-mono">${totalMat.toLocaleString('es-CO')}</span>
                  </div>
                  <div>
                    <span className="text-[10px] font-bold text-yeikar-neutral/50 block">MANO DE OBRA PAGADA</span>
                    <span className="text-base font-black text-green-700 font-mono">${totalMoPagada.toLocaleString('es-CO')}</span>
                  </div>
                  <div>
                    <span className="text-[10px] font-bold text-yeikar-neutral/50 block">MANO DE OBRA PENDIENTE</span>
                    <span className="text-base font-black text-red-700 font-mono">${totalMoPendiente.toLocaleString('es-CO')}</span>
                  </div>
                  <div className="border-l border-yeikar-secondary-light/10 pl-2">
                    <span className="text-[10px] font-bold text-yeikar-primary block">COSTO TOTAL ETAPA</span>
                    <span className="text-lg font-black text-yeikar-primary font-mono">${totalEtapa.toLocaleString('es-CO')}</span>
                  </div>
                </div>
              );
            })()}

            {/* Modal Footer */}
            <div className="flex justify-between pt-4 border-t border-yeikar-secondary-light/5">
              <button
                onClick={() => handleFinalizarOrden(selectedStage.orden_produccion_id)}
                className="bg-green-500 hover:bg-green-600 text-white px-4 py-2 rounded-xl text-sm font-bold font-headline transition-colors"
              >
                Finalizar Orden Completa
              </button>
              <button
                onClick={() => setSelectedStage(null)}
                className="bg-yeikar-tertiary hover:bg-yeikar-secondary-light/15 text-yeikar-secondary px-6 py-2.5 rounded-xl text-sm font-bold font-headline transition-colors"
              >
                Cerrar
              </button>
            </div>

          </div>
        </div>
      )}

      {/* Modal Nueva Etapa */}
      {ordenParaNuevaEtapa && (
        <div className="fixed inset-0 bg-yeikar-secondary/60 backdrop-blur-sm flex items-center justify-center p-4 z-50">
          <div className="bg-white rounded-3xl shadow-xl border border-yeikar-secondary-light/10 max-w-sm w-full p-6">
            <h2 className="text-xl font-black font-headline text-yeikar-secondary tracking-tight mb-4">
              Añadir Etapa a Orden #{ordenParaNuevaEtapa}
            </h2>
            <form onSubmit={handleSubmitNuevaEtapa} className="space-y-4">
              <div>
                <label className="block text-xs font-bold text-yeikar-neutral/60 mb-1">Área de Producción</label>
                <select
                  value={nuevaEtapaForm.area_id}
                  onChange={(e) => setNuevaEtapaForm(prev => ({ ...prev, area_id: e.target.value }))}
                  required
                  className="w-full bg-yeikar-tertiary/30 border border-yeikar-secondary-light/10 rounded-xl p-2.5 text-sm focus:outline-none focus:border-yeikar-primary"
                >
                  <option value="">Seleccione Área...</option>
                  {areas.map(a => (
                    <option key={a.id} value={a.id}>{a.nombre}</option>
                  ))}
                </select>
              </div>
              
              <div>
                <label className="block text-xs font-bold text-yeikar-neutral/60 mb-1">Responsable</label>
                <select
                  value={nuevaEtapaForm.empleado_id}
                  onChange={(e) => setNuevaEtapaForm(prev => ({ ...prev, empleado_id: e.target.value }))}
                  required
                  className="w-full bg-yeikar-tertiary/30 border border-yeikar-secondary-light/10 rounded-xl p-2.5 text-sm focus:outline-none focus:border-yeikar-primary"
                >
                  <option value="">Seleccione Empleado...</option>
                  {empleados.map(e => (
                    <option key={e.id} value={e.id}>{e.nombre} {e.apellido}</option>
                  ))}
                </select>
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
                  className="bg-yeikar-primary text-yeikar-neutral px-4 py-2 rounded-xl text-sm font-bold shadow-sm hover:shadow transition-all"
                >
                  Crear Etapa
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
