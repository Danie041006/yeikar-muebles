import React, { useEffect, useMemo, useState } from 'react';
import {
  produccionService,
  type EtapaProduccion,
  type OrdenProduccion,
  type Area,
  type ReferenciaReceta,
  type CostosEnVivoOrden,
  type ConsumoMaterial,
} from '../../services/produccionService';
import type { SobranteLamina } from '../../services/inventarioService';
import api from '../../services/api';
import ConfirmDialog from '../ui/ConfirmDialog';
import { SearchSelect } from '../ui';
import CostosOrdenEnVivo from '../CostosOrdenEnVivo';
import { useToast } from '../../context/ToastContext';
import { esOrdenExhibicion, fmt, type Empleado, type Material } from './tipos';
import {
  dimensionalidad,
  volumenPieza,
  convertirCapturaLineal,
  etiquetaCaptura,
  fmtNum,
  fmtNum4,
  type UnidadCaptura,
} from '../../utils/unidades';

// ── EtapaModal: estación de trabajo de una etapa del Kanban de producción.
//    Flujo de lectura = la pregunta del trabajador:
//    1. ¿Qué debo usar?      → Receta vs Registrado (widget activo, prellena)
//    2. ¿Qué he usado?       → Formularios de material y mano de obra
//    3. ¿Cuánto llevamos?    → Barra de totales consolidada (sticky)
//    4. ¿Qué sigue?          → Acciones de estado en el header (Iniciar/Pausar/…)

type TabActiva = 'registrar' | 'historial' | 'costos';

interface EtapaModalProps {
  stage: EtapaProduccion;
  orden: OrdenProduccion | null;
  areas: Area[];
  empleados: Empleado[];
  materiales: Material[];
  inventario: Record<number, number>;
  sobrantesLamina: SobranteLamina[];
  referenciaReceta: ReferenciaReceta | null;
  loadingReceta: boolean;
  costosEnVivo: CostosEnVivoOrden | null;
  costosEnVivoLoading: boolean;
  statusUpdating: boolean;
  onClose: () => void;
  onRefrescarEtapa: () => Promise<void>;
  onCambiarEstado: (stageId: number, nuevoEstado: string) => void;
  onPasarAArea: (stage: EtapaProduccion) => void;
  onAbrirHojaTrabajo: () => void;
  onRecargarSobrantes: () => void | Promise<void>;
}

/** Un material es laminar cuando tiene las dos dimensiones de lámina (cm). */
const esMaterialLaminar = (m?: Material | null) => !!m && m.largo_cm != null && m.ancho_cm != null;

const ESTADO_COLORS: Record<string, string> = {
  ASIGNADA: 'bg-blue-50 text-blue-700 border-blue-200',
  EN_PROCESO: 'bg-amber-50 text-amber-700 border-amber-200',
  PAUSADA: 'bg-red-50 text-red-700 border-red-200',
  COMPLETADA: 'bg-green-50 text-green-700 border-green-200',
};

const SECCION_COLORS: Record<string, string> = {
  EBANISTERIA: 'bg-amber-100 text-amber-800 border-amber-200',
  TAPICERIA: 'bg-purple-100 text-purple-800 border-purple-200',
  PINTURA: 'bg-sky-100 text-sky-800 border-sky-200',
  TERMINACION: 'bg-emerald-100 text-emerald-800 border-emerald-200',
  NOCHEROS: 'bg-rose-100 text-rose-800 border-rose-200',
  MANO_DE_OBRA: 'bg-blue-100 text-blue-800 border-blue-200',
};

/** Acción siguiente por estado de la etapa (el nombre habla el idioma del taller). */
const ACCIONES_ESTADO: Record<string, { destino: string; label: string; primario: boolean; icono: string[] }[]> = {
  ASIGNADA: [{
    destino: 'EN_PROCESO', label: 'Iniciar trabajo', primario: true,
    icono: ['M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z', 'M21 12a9 9 0 11-18 0 9 9 0 0118 0z'],
  }],
  EN_PROCESO: [
    { destino: 'PAUSADA', label: 'Pausar', primario: false, icono: ['M10 9v6m4-6v6m7-3a9 9 0 11-18 0 9 9 0 0118 0z'] },
    { destino: 'COMPLETADA', label: 'Completar etapa', primario: true, icono: ['M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z'] },
  ],
  PAUSADA: [{
    destino: 'EN_PROCESO', label: 'Retomar', primario: true,
    icono: ['M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z', 'M21 12a9 9 0 11-18 0 9 9 0 0118 0z'],
  }],
};

export default function EtapaModal({
  stage,
  orden,
  areas,
  empleados,
  materiales,
  inventario,
  sobrantesLamina,
  referenciaReceta,
  loadingReceta,
  costosEnVivo,
  costosEnVivoLoading,
  statusUpdating,
  onClose,
  onRefrescarEtapa,
  onCambiarEstado,
  onPasarAArea,
  onAbrirHojaTrabajo,
  onRecargarSobrantes,
}: EtapaModalProps) {
  const toast = useToast();

  // ── Estado local del modal (formularios y confirmaciones) ──
  const [tab, setTab] = useState<TabActiva>('registrar');
  const [newConsumo, setNewConsumo] = useState({
    material_id: '',
    cantidad: '',
    observaciones: '',
    solicitante_id: '',
    unidad_captura: '' as '' | UnidadCaptura,
    modo_pieza: false,
    pieza_largo: '',
    pieza_ancho: '',
    pieza_espesor: '',
    componente: '',
    es_excedente: false,
    motivo_exceso: '',
    ancho_corte_cm: '',
    largo_corte_cm: '',
    origen_sobrante_id: '' as '',
    es_lamina_completa: false,
  });
  const [materialSearch, setMaterialSearch] = useState('');
  const [showMaterialDropdown, setShowMaterialDropdown] = useState(false);
  const [consumoSubmitting, setConsumoSubmitting] = useState(false);
  const [consumoAEliminar, setConsumoAEliminar] = useState<number | null>(null);
  const [manoObraAEliminar, setManoObraAEliminar] = useState<number | null>(null);
  const [consumoAConfirmar, setConsumoAConfirmar] = useState<ConsumoMaterial | null>(null);
  const [confirmarForm, setConfirmarForm] = useState({
    cantidad_cortes: '', largo_corte_cm: '', ancho_corte_cm: '',
    sobrante_largo_cm: '', sobrante_ancho_cm: '',
  });
  const [confirmarSubmitting, setConfirmarSubmitting] = useState(false);

  const [newManoObra, setNewManoObra] = useState({ empleado_id: '', costo_id: '', monto: '', observaciones: '' });
  const [opcionesCosto, setOpcionesCosto] = useState<{ id: number; descripcion: string; precio: number }[]>([]);
  const [mostrarNuevoCosto, setMostrarNuevoCosto] = useState(false);
  const [nuevoCosto, setNuevoCosto] = useState({ descripcion: '', precio: '', area_id: '' });
  const [creandoCosto, setCreandoCosto] = useState(false);

  const consumos = stage.consumos ?? [];
  const manoObras = stage.mano_obras ?? [];

  // ── Derivados del formulario de consumo ──
  const materialConsumo = materiales.find((m) => String(m.id) === newConsumo.material_id);
  const dimConsumo = dimensionalidad(materialConsumo?.unidad_medida?.abreviatura);

  // Sobrantes del material actual que le caben al corte digitado (ambas orientaciones)
  const sobrantesQueCaben = (() => {
    if (!materialConsumo || !newConsumo.ancho_corte_cm || !newConsumo.largo_corte_cm) return [];
    const lc = parseFloat(newConsumo.largo_corte_cm);
    const ac = parseFloat(newConsumo.ancho_corte_cm);
    if (!(lc > 0) || !(ac > 0)) return [];
    const cabe = (L: number, A: number) =>
      Math.max(
        lc <= L && ac <= A ? Math.floor(L / lc) * Math.floor(A / ac) : 0,
        ac <= L && lc <= A ? Math.floor(L / ac) * Math.floor(A / lc) : 0,
      );
    return sobrantesLamina
      .filter((s) => s.material_id === materialConsumo.id)
      .map((s) => ({ s, caben: cabe(parseFloat(String(s.largo_cm)), parseFloat(String(s.ancho_cm))) }))
      .filter((x) => x.caben > 0)
      .sort((a, b) => parseFloat(String(a.s.area_cm2)) - parseFloat(String(b.s.area_cm2)));
  })();

  // ── Totales consolidados (una sola verdad, no dos cajas duplicadas) ──
  const { totalMateriales, totalManoObra, totalEtapa } = useMemo(() => {
    const mat = consumos.reduce((acc, c) => {
      const costo = c.costo_unitario !== undefined && c.costo_unitario !== null ? c.costo_unitario : (c.material?.costo_base || 0);
      return acc + c.cantidad * costo;
    }, 0);
    const mo = manoObras.reduce((acc, mo) => acc + mo.monto * (1 + (mo.porcentaje_recargo || 0) / 100), 0);
    return { totalMateriales: mat, totalManoObra: mo, totalEtapa: mat + mo };
  }, [consumos, manoObras]);

  // ── Receta vs Registrado: lo esperado por la receta contra lo ya consumido ──
  const registradoPorMaterial = useMemo(() => {
    const mapa: Record<number, { cantidad: number; pendientes: number }> = {};
    consumos.forEach((c) => {
      const entry = mapa[c.material_id] || { cantidad: 0, pendientes: 0 };
      entry.cantidad += c.cantidad;
      if (c.estado === 'PENDIENTE') entry.pendientes += c.cantidad;
      mapa[c.material_id] = entry;
    });
    return mapa;
  }, [consumos]);

  // Al abrir otra etapa el modal se remonta (key={stage.id} en la página):
  // los useState iniciales ya dejan todo limpio, sin efecto de reset.

  // Precargar medidas del corte desde la receta de referencia al elegir material
  useEffect(() => {
    if (!newConsumo.material_id || !referenciaReceta) return;
    const ref = referenciaReceta.materiales.find((m) => m.material_id === parseInt(newConsumo.material_id));
    if (ref?.es_corte && ref.ancho_corte_cm && ref.largo_corte_cm) {
      setNewConsumo((prev) => ({
        ...prev,
        ancho_corte_cm: prev.ancho_corte_cm || String(ref.ancho_corte_cm),
        largo_corte_cm: prev.largo_corte_cm || String(ref.largo_corte_cm),
      }));
    }
  }, [newConsumo.material_id, referenciaReceta]);

  // Tarifario de costos de producción del área de la etapa (form de mano de obra)
  useEffect(() => {
    api.get('/produccion/opciones-costo-produccion', {
      params: stage.area_id ? { area_id: stage.area_id } : {},
    }).then((r) => setOpcionesCosto(r.data)).catch(() => setOpcionesCosto([]));
  }, [stage.id, stage.area_id]);

  const seleccionarCostoMo = (costoId: string) => {
    setNewManoObra((prev) => {
      const opcion = opcionesCosto.find((o) => String(o.id) === String(costoId));
      return { ...prev, costo_id: costoId, monto: opcion ? String(opcion.precio) : prev.monto };
    });
  };

  const crearCostoAlVuelo = async () => {
    const areaFinal = Number(nuevoCosto.area_id) || stage.area_id;
    if (!nuevoCosto.descripcion.trim() || !nuevoCosto.precio || !areaFinal) {
      toast.error('Descripción, precio y área son obligatorios para el nuevo costo.');
      return;
    }
    setCreandoCosto(true);
    try {
      const resp = await api.post('/produccion/opciones-costo-produccion', {
        area_id: areaFinal,
        descripcion: nuevoCosto.descripcion.trim(),
        precio: parseFloat(nuevoCosto.precio),
      });
      const creado = resp.data;
      setOpcionesCosto((prev) => [...prev, creado].sort((a, b) => a.descripcion.localeCompare(b.descripcion)));
      setNewManoObra((prev) => ({ ...prev, costo_id: String(creado.id), monto: String(creado.precio) }));
      setNuevoCosto({ descripcion: '', precio: '', area_id: '' });
      setMostrarNuevoCosto(false);
      toast.success('Costo de producción creado y seleccionado.');
    } catch (error: any) {
      toast.error(error?.response?.data?.detail || 'No se pudo crear el costo.');
    } finally {
      setCreandoCosto(false);
    }
  };

  /** Prellena el form de consumo con lo que falta de un material de la receta. */
  const prellenarDesdeReceta = (materialId: number, cantidadFaltante: number) => {
    setNewConsumo((prev) => ({
      ...prev,
      material_id: String(materialId),
      cantidad: cantidadFaltante > 0 ? String(Math.round(cantidadFaltante * 100) / 100) : '',
      unidad_captura: '', modo_pieza: false,
      pieza_largo: '', pieza_ancho: '', pieza_espesor: '',
      ancho_corte_cm: '', largo_corte_cm: '', origen_sobrante_id: '',
      es_lamina_completa: false,
    }));
    const mat = materiales.find((m) => m.id === materialId);
    setMaterialSearch(mat?.nombre || '');
    setShowMaterialDropdown(false);
    setTab('registrar');
  };

  // ── Registrar consumo de material ──
  const handleAddConsumo = async (e: React.FormEvent) => {
    e.preventDefault();
    if (consumoSubmitting) return;
    if (!newConsumo.material_id || !newConsumo.cantidad) return;
    if (!newConsumo.solicitante_id) {
      toast.error('Selecciona quién solicita el material.');
      return;
    }
    const esPieza = dimConsumo === 'VOLUMEN' && newConsumo.modo_pieza;
    if (esPieza && (!newConsumo.pieza_largo || !newConsumo.pieza_ancho || !newConsumo.pieza_espesor)) {
      toast.error('Completa las medidas de la pieza (largo × ancho × espesor).');
      return;
    }
    const esCorte = esMaterialLaminar(materialConsumo) && !!newConsumo.ancho_corte_cm && !!newConsumo.largo_corte_cm;
    const esLaminaCompleta = esMaterialLaminar(materialConsumo) && newConsumo.es_lamina_completa;
    if (esLaminaCompleta && esCorte) {
      toast.error('Elige un modo: lámina completa (confirmar después) o corte directo.');
      return;
    }
    if (esLaminaCompleta && newConsumo.origen_sobrante_id) {
      toast.error('El pedido de lámina completa no sale de sobrantes: se pide lámina nueva del depósito.');
      return;
    }
    if (esCorte && newConsumo.modo_pieza) {
      toast.error('El consumo por corte no admite captura por pieza volumétrica.');
      return;
    }
    if (esLaminaCompleta && newConsumo.modo_pieza) {
      toast.error('El pedido de lámina completa no admite captura por pieza volumétrica.');
      return;
    }
    setConsumoSubmitting(true);
    try {
      const materialId = parseInt(newConsumo.material_id);
      const cantidad = parseFloat(newConsumo.cantidad);
      const cantidadConvertida = esCorte
        ? cantidad
        : esPieza
          ? volumenPieza(
              { largo: parseFloat(newConsumo.pieza_largo), ancho: parseFloat(newConsumo.pieza_ancho), espesor: parseFloat(newConsumo.pieza_espesor) },
              cantidad,
            )
          : newConsumo.unidad_captura === 'CM'
            ? convertirCapturaLineal(cantidad, 'CM')
            : cantidad;
      const stockAntes = inventario[materialId];
      await produccionService.registrarConsumo({
        etapa_produccion_id: stage.id,
        material_id: materialId,
        cantidad,
        fecha: new Date().toISOString(),
        seccion: referenciaReceta?.seccion_actual || undefined,
        observaciones: newConsumo.observaciones || undefined,
        solicitante_empleado_id: parseInt(newConsumo.solicitante_id),
        ...(esLaminaCompleta
          ? { es_lamina_completa: true }
          : esCorte
            ? {
                ancho_corte_cm: parseFloat(newConsumo.ancho_corte_cm),
                largo_corte_cm: parseFloat(newConsumo.largo_corte_cm),
                origen_sobrante_id: newConsumo.origen_sobrante_id ? parseInt(newConsumo.origen_sobrante_id) : undefined,
              }
            : esPieza
              ? {
                  pieza_largo: parseFloat(newConsumo.pieza_largo),
                  pieza_ancho: parseFloat(newConsumo.pieza_ancho),
                  pieza_espesor: parseFloat(newConsumo.pieza_espesor),
                }
              : newConsumo.unidad_captura
                ? { unidad_captura: newConsumo.unidad_captura }
                : {}),
        ...(newConsumo.componente.trim() ? { componente: newConsumo.componente.trim() } : {}),
        ...(newConsumo.es_excedente
          ? { es_excedente: true, motivo_exceso: newConsumo.motivo_exceso || 'OTRO' }
          : {}),
      });
      await onRefrescarEtapa();
      setNewConsumo((prev) => ({
        ...prev,
        material_id: '', cantidad: '', observaciones: '',
        unidad_captura: '', modo_pieza: false, pieza_largo: '', pieza_ancho: '', pieza_espesor: '',
        componente: '', es_excedente: false, motivo_exceso: '',
        ancho_corte_cm: '', largo_corte_cm: '', origen_sobrante_id: '',
        es_lamina_completa: false,
      }));
      setMaterialSearch('');
      await onRecargarSobrantes();
      toast.success(
        esLaminaCompleta
          ? `Lámina completa pedida: ${fmtNum(cantidad)} lámina(s) descontada(s) del depósito. Costo provisional — confirma el uso por cortes cuando el trabajador diga cuánto se usó.`
          : esCorte
            ? `Consumo por cortes registrado${newConsumo.origen_sobrante_id ? ' desde sobrante' : ' — lámina(s) descontada(s) y sobrante actualizado'}.`
            : stockAntes !== undefined
              ? `Material registrado. Descontado: ${fmtNum(cantidadConvertida)} ${materialConsumo?.unidad_medida?.abreviatura || ''} — Stock restante: ${fmtNum(Math.max(0, stockAntes - cantidadConvertida))}`
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
    if (consumoId === null) return;
    setConsumoAEliminar(null);
    try {
      await produccionService.eliminarConsumo(consumoId);
      await onRefrescarEtapa();
      await onRecargarSobrantes();
      toast.success('Consumo eliminado. El stock fue repuesto y el egreso revertido.');
    } catch (error: any) {
      toast.error(error.response?.data?.detail || 'Error al eliminar el consumo.');
    }
  };

  const ejecutarConfirmarConsumo = async () => {
    if (!consumoAConfirmar) return;
    const cortes = parseFloat(confirmarForm.cantidad_cortes);
    const lc = parseFloat(confirmarForm.largo_corte_cm);
    const ac = parseFloat(confirmarForm.ancho_corte_cm);
    if (!(cortes > 0) || !(lc > 0) || !(ac > 0)) {
      toast.error('Indica la cantidad de cortes y sus medidas (largo × ancho en cm).');
      return;
    }
    setConfirmarSubmitting(true);
    try {
      await produccionService.confirmarConsumo(consumoAConfirmar.id, {
        cantidad_cortes: cortes,
        largo_corte_cm: lc,
        ancho_corte_cm: ac,
        ...(confirmarForm.sobrante_largo_cm && confirmarForm.sobrante_ancho_cm
          ? {
              sobrante_largo_cm: parseFloat(confirmarForm.sobrante_largo_cm),
              sobrante_ancho_cm: parseFloat(confirmarForm.sobrante_ancho_cm),
            }
          : {}),
      });
      setConsumoAConfirmar(null);
      await onRefrescarEtapa();
      await onRecargarSobrantes();
      toast.success('Uso confirmado: costo real aplicado, láminas ajustadas y sobrante registrado.');
    } catch (error: any) {
      toast.error(error.response?.data?.detail || 'Error al confirmar el uso de la lámina.');
    } finally {
      setConfirmarSubmitting(false);
    }
  };

  // ── Mano de obra ──
  const handleAddManoObra = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newManoObra.empleado_id || !newManoObra.monto) return;
    try {
      await produccionService.registrarManoObra({
        etapa_produccion_id: stage.id,
        empleado_id: parseInt(newManoObra.empleado_id),
        monto: parseFloat(newManoObra.monto),
        porcentaje_recargo: 0.0,
        observaciones: newManoObra.observaciones || undefined,
        precio_produccion_id: newManoObra.costo_id ? parseInt(newManoObra.costo_id) : undefined,
      });
      await onRefrescarEtapa();
      setNewManoObra({ empleado_id: '', costo_id: '', monto: '', observaciones: '' });
      toast.success('Mano de obra registrada para la etapa.');
    } catch (error: any) {
      toast.error(error.response?.data?.detail || 'Error al registrar la mano de obra. La etapa debe estar EN PROCESO.');
    }
  };

  const ejecutarEliminarManoObra = async () => {
    const manoObraId = manoObraAEliminar;
    if (manoObraId === null) return;
    setManoObraAEliminar(null);
    try {
      await produccionService.eliminarManoObra(manoObraId);
      await onRefrescarEtapa();
      toast.success('Mano de obra eliminada.');
    } catch (error: any) {
      toast.error(error.response?.data?.detail || 'Error al eliminar la mano de obra.');
    }
  };

  const handleToggleListoNomina = async (manoObraId: number, currentListo: boolean) => {
    try {
      await produccionService.alternarListoNomina(manoObraId, !currentListo);
      await onRefrescarEtapa();
      toast.success(!currentListo
        ? 'Trabajo marcado como listo para incluirse en nómina.'
        : 'Trabajo marcado como pendiente (no entrará en la nómina de esta semana).');
    } catch (error) {
      console.error('Error al cambiar estado de nómina:', error);
      toast.error('Error al actualizar el estado para nómina.');
    }
  };

  // ── Datos derivados del header ──
  const productoNombre =
    stage.orden?.detalle_pedido?.producto?.nombre ||
    stage.orden?.producto?.nombre ||
    `Orden de Producción #${stage.orden_produccion_id}`;
  const detalle = stage.orden?.detalle_pedido;
  const medidas = detalle?.ancho && detalle?.largo
    ? `${detalle.ancho}m × ${detalle.largo}m`
    : stage.orden?.ancho && stage.orden?.largo
      ? `${stage.orden.ancho}m × ${stage.orden.largo}m`
      : null;
  const acciones = ACCIONES_ESTADO[stage.estado] ?? [];

  // Receta: materiales de la sección activa + el resto colapsado
  const matsReceta = referenciaReceta?.materiales ?? [];
  const seccionActiva = referenciaReceta?.seccion_actual ?? null;
  const matsSeccionActiva = seccionActiva ? matsReceta.filter((m) => m.seccion === seccionActiva) : matsReceta;
  const matsOtrasSecciones = useMemo(() => {
    const resto = seccionActiva ? matsReceta.filter((m) => m.seccion !== seccionActiva) : [];
    const porSeccion: Record<string, typeof resto> = {};
    resto.forEach((m) => { (porSeccion[m.seccion] = porSeccion[m.seccion] || []).push(m); });
    return porSeccion;
  }, [matsReceta, seccionActiva]);

  const etapasOrden = [...(orden?.etapas ?? [])].sort((a, b) => (a.id || 0) - (b.id || 0));

  return (
    <div
      className="fixed inset-0 bg-yeikar-secondary/60 backdrop-blur-sm flex items-start sm:items-center justify-center p-3 sm:p-4 z-50 overflow-y-auto"
      onClick={onClose}
    >
      <div
        className="bg-white rounded-3xl shadow-xl border border-yeikar-secondary-light/10 max-w-4xl w-full max-h-[94vh] flex flex-col relative"
        role="dialog"
        aria-modal="true"
        aria-label={`Etapa ${stage.id} de ${productoNombre}`}
        onClick={(e) => e.stopPropagation()}
      >
        {/* ══ HEADER STICKY: identidad + acciones de estado ══ */}
        <div className="sticky top-0 z-20 bg-white/95 backdrop-blur rounded-t-3xl border-b border-yeikar-secondary-light/10 px-4 sm:px-6 pt-4 pb-3 space-y-3">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <div className="flex items-center gap-2 flex-wrap">
                <span className="text-[10px] font-mono font-bold text-yeikar-neutral/40 tracking-wider uppercase">
                  Etapa #{stage.id} · {stage.area?.nombre || 'Sin área'}
                </span>
                {stage.es_retrabajo && (
                  <span className="text-[9px] font-bold px-1.5 py-0.5 rounded-md bg-amber-100 text-amber-700 uppercase">Retrabajo</span>
                )}
                <span className={`text-[10px] font-mono font-bold px-2 py-0.5 rounded-lg border ${ESTADO_COLORS[stage.estado]}`}>
                  {stage.estado.replace('_', ' ')}
                </span>
              </div>
              <h2 className="text-xl sm:text-2xl font-black font-headline text-yeikar-secondary tracking-tight truncate">
                {productoNombre}
              </h2>
            </div>
            <button
              onClick={onClose}
              className="p-2 hover:bg-yeikar-tertiary rounded-xl text-yeikar-neutral/40 hover:text-yeikar-neutral/80 transition-colors shrink-0"
              title="Cerrar modal"
              aria-label="Cerrar modal"
            >
              <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>

          {/* Identidad de la orden en una sola línea de badges */}
          <div className="flex items-center gap-1.5 flex-wrap">
            {detalle?.pedido?.cliente?.nombre && (
              <span className="bg-yeikar-primary/10 text-yeikar-primary font-bold text-[11px] px-2 py-0.5 rounded-lg border border-yeikar-primary/20">
                {detalle.pedido.cliente.nombre}
              </span>
            )}
            {!detalle && (
              <span className="bg-yeikar-primary/15 text-yeikar-primary-dark font-bold text-[11px] px-2 py-0.5 rounded-lg border border-yeikar-primary/25">
                {esOrdenExhibicion(stage.orden) ? 'PIEZA DE EXHIBICIÓN' : 'SIN PEDIDO'}
              </span>
            )}
            <span className="bg-yeikar-tertiary text-yeikar-secondary font-mono text-[11px] font-bold px-2 py-0.5 rounded-lg border border-yeikar-secondary-light/10">
              Orden #{stage.orden_produccion_id}
            </span>
            {medidas && (
              <span className="bg-stone-100 text-stone-600 font-mono text-[11px] font-bold px-2 py-0.5 rounded-lg border border-stone-200">
                {medidas}
              </span>
            )}
            {detalle?.cantidad != null && (
              <span className="bg-yeikar-primary/10 text-yeikar-primary font-mono text-[11px] font-bold px-2 py-0.5 rounded-lg border border-yeikar-primary/20">
                × {detalle.cantidad} und
              </span>
            )}
            {detalle?.pedido?.fecha_entrega_estimada && (
              <span className="bg-amber-50 text-amber-800 font-bold text-[11px] px-2 py-0.5 rounded-lg border border-amber-200" title="Fecha estimada de entrega al cliente">
                Entrega: {new Date(detalle.pedido.fecha_entrega_estimada + 'T00:00:00').toLocaleDateString('es-CO', { day: '2-digit', month: '2-digit', year: 'numeric' })}
              </span>
            )}
            {stage.orden?.estado && (
              <span className={`text-[10px] font-mono font-bold px-2 py-0.5 rounded-lg border ${
                stage.orden.estado === 'FINALIZADA' ? 'bg-green-50 text-green-700 border-green-200'
                : stage.orden.estado === 'PAUSADA' ? 'bg-red-50 text-red-700 border-red-200'
                : 'bg-blue-50 text-blue-700 border-blue-200'
              }`}>
                ORDEN: {stage.orden.estado.replace('_', ' ')}
              </span>
            )}
          </div>

          {/* Responsable y fechas de la etapa */}
          <div className="flex items-center gap-3 flex-wrap text-[10px] font-mono text-yeikar-neutral/50 -mt-1">
            <span className="flex items-center gap-1">
              <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" /></svg>
              Encargado: {stage.empleado_responsable ? stage.empleado_responsable.nombre : 'Sin asignar'}
            </span>
            {stage.fecha_inicio && <span>Inicio: {new Date(stage.fecha_inicio).toLocaleString('es-CO', { dateStyle: 'short', timeStyle: 'short' })}</span>}
            {stage.fecha_fin && <span>Fin: {new Date(stage.fecha_fin).toLocaleString('es-CO', { dateStyle: 'short', timeStyle: 'short' })}</span>}
          </div>

          {/* Barra de acciones: estado + documentos */}
          <div className="flex items-center gap-2 flex-wrap">
            {acciones.map((a) => (
              <button
                key={a.destino}
                onClick={() => onCambiarEstado(stage.id, a.destino)}
                disabled={statusUpdating}
                title={
                  a.destino === 'COMPLETADA'
                    ? 'Marca la etapa como terminada'
                    : a.destino === 'EN_PROCESO'
                      ? 'El trabajo está en marcha: ya puedes registrar consumos y mano de obra'
                      : 'Pausa el trabajo de esta etapa'
                }
                className={`px-3.5 py-1.5 rounded-xl text-xs font-bold font-headline transition-all flex items-center gap-1.5 shadow-sm disabled:opacity-50 disabled:cursor-not-allowed ${
                  a.primario
                    ? 'bg-yeikar-primary text-yeikar-neutral hover:bg-yeikar-primary-dark'
                    : 'bg-white border border-yeikar-secondary-light/25 text-yeikar-neutral/70 hover:bg-yeikar-tertiary/50'
                }`}
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  {a.icono.map((d, i) => (
                    <path key={i} strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d={d} />
                  ))}
                </svg>
                {a.label}
              </button>
            ))}
            {stage.estado !== 'COMPLETADA' && (
              <button
                onClick={() => onPasarAArea(stage)}
                className="px-3.5 py-1.5 rounded-xl text-xs font-bold font-headline bg-white border border-yeikar-secondary-light/25 text-yeikar-secondary hover:bg-yeikar-tertiary/50 transition-all flex items-center gap-1.5 shadow-sm"
                title="Enviar la orden a la siguiente área del taller"
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 8l4 4m0 0l-4 4m4-4H3" />
                </svg>
                Pasar a Área
              </button>
            )}
            <span className="flex-1" />
            {(stage.orden?.detalle_pedido?.producto || stage.orden?.producto_id) && (
              <button
                onClick={onAbrirHojaTrabajo}
                className="px-3 py-1.5 bg-white border border-yeikar-secondary-light/25 text-yeikar-secondary hover:bg-yeikar-tertiary/50 rounded-xl text-xs font-bold font-headline transition-all flex items-center gap-1.5 shadow-sm"
                title="Imprimir la hoja de trabajo de esta etapa (sin montos, con foto del mueble)"
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 17h2a2 2 0 002-2v-4a2 2 0 00-2-2H5a2 2 0 00-2 2v4a2 2 0 002 2h2m2 4h6a2 2 0 002-2v-4a2 2 0 00-2-2H9a2 2 0 00-2 2v4a2 2 0 002 2zm8-12V5a2 2 0 00-2-2H9a2 2 0 00-2 2v4h10z" />
                </svg>
                Hoja de Trabajo
              </button>
            )}
            {stage.orden?.detalle_pedido?.pedido?.id && (
              <button
                onClick={() => { window.location.href = `/historial?tipo=pedido&id=${stage.orden!.detalle_pedido!.pedido!.id}`; }}
                className="px-3 py-1.5 bg-yeikar-secondary text-yeikar-primary hover:bg-yeikar-secondary-light rounded-xl text-xs font-bold font-headline transition-all flex items-center gap-1.5 shadow-sm"
                title="Ver expediente completo del pedido"
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z" />
                </svg>
                Expediente
              </button>
            )}
          </div>

          {esOrdenExhibicion(stage.orden) && (
            <div className="bg-yeikar-primary/10 border border-yeikar-primary/25 rounded-xl px-3 py-2 text-[11px] font-bold text-yeikar-primary-dark">
              PIEZA DE EXHIBICIÓN — al finalizar la orden entra al stock del showroom con su costo real (no se genera envío a cliente).
            </div>
          )}
        </div>

        {/* ══ TABS ══ */}
        <div className="px-4 sm:px-6 pt-3 border-b border-yeikar-secondary-light/10 bg-white">
          <div className="flex items-center gap-1">
            {([
              ['registrar', 'Registrar', consumos.length + manoObras.length],
              ['historial', 'Historial', etapasOrden.length],
              ['costos', 'Costos de la orden', null],
            ] as [TabActiva, string, number | null][]).map(([id, label, count]) => (
              <button
                key={id}
                onClick={() => setTab(id)}
                className={`px-4 py-2 text-xs font-bold font-headline rounded-t-xl transition-colors flex items-center gap-1.5 border-b-2 -mb-px ${
                  tab === id
                    ? 'border-yeikar-primary text-yeikar-primary bg-yeikar-primary/5'
                    : 'border-transparent text-yeikar-neutral/50 hover:text-yeikar-secondary'
                }`}
              >
                {label}
                {count != null && count > 0 && (
                  <span className={`font-mono text-[10px] px-1.5 py-0.5 rounded-full ${tab === id ? 'bg-yeikar-primary text-yeikar-neutral' : 'bg-yeikar-tertiary text-yeikar-neutral/60'}`}>
                    {count}
                  </span>
                )}
              </button>
            ))}
          </div>
        </div>

        {/* ══ CONTENIDO ══ */}
        <div className="flex-1 overflow-y-auto px-4 sm:px-6 py-4 space-y-5">
          {tab === 'registrar' && (
            <>
              {/* ── 1. RECETA VS REGISTRADO: qué debo usar y qué llevo ── */}
              {loadingReceta ? (
                <div className="text-xs font-mono text-yeikar-neutral/40 py-3 text-center">Cargando receta de referencia…</div>
              ) : matsSeccionActiva.length > 0 ? (
                <div className="rounded-2xl border border-yeikar-primary/25 bg-yeikar-primary/5 overflow-hidden">
                  <div className="flex items-center justify-between gap-2 px-4 py-2.5 border-b border-yeikar-primary/15">
                    <div className="flex items-center gap-2 min-w-0">
                      <svg className="w-4 h-4 text-yeikar-primary/70 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
                      </svg>
                      <span className="text-xs font-bold font-headline text-yeikar-secondary uppercase tracking-wider">
                        Receta de esta etapa
                      </span>
                      {seccionActiva && (
                        <span className={`text-[10px] font-bold px-2 py-0.5 rounded-md border ${SECCION_COLORS[seccionActiva] || 'bg-stone-100 text-stone-600 border-stone-200'}`}>
                          {seccionActiva}
                        </span>
                      )}
                    </div>
                    {referenciaReceta?.dimensiones.ancho && referenciaReceta?.dimensiones.largo && (
                      <span className="text-[10px] font-mono text-yeikar-neutral/40 shrink-0">
                        {referenciaReceta.dimensiones.ancho}m × {referenciaReceta.dimensiones.largo}m
                      </span>
                    )}
                  </div>
                  <div className="divide-y divide-yeikar-secondary-light/5">
                    {matsSeccionActiva.map((m, i) => {
                      const reg = registradoPorMaterial[m.material_id] || { cantidad: 0, pendientes: 0 };
                      const pct = m.cantidad_esperada > 0 ? Math.min(100, (reg.cantidad / m.cantidad_esperada) * 100) : 0;
                      const faltante = m.cantidad_esperada - reg.cantidad;
                      const unidad = m.es_corte ? 'cortes' : m.unidad;
                      return (
                        <div key={`${m.material_id}-${i}`} className={`px-4 py-2.5 ${m.condicion_cumplida ? '' : 'opacity-50'}`}>
                          <div className="flex items-center gap-2 flex-wrap">
                            <span className="font-bold text-yeikar-secondary text-sm">{m.nombre}</span>
                            {m.es_corte && m.ancho_corte_cm && m.largo_corte_cm && (
                              <span className="text-[9px] font-mono font-bold text-amber-700 bg-amber-50 border border-amber-200 rounded px-1.5 py-0.5">
                                {fmtNum(m.cantidad_esperada)} corte(s) de {m.ancho_corte_cm}×{m.largo_corte_cm} cm
                              </span>
                            )}
                            {!m.condicion_cumplida && (
                              <span className="text-[9px] font-bold text-red-500 uppercase">No aplica para estas medidas</span>
                            )}
                            <span className="flex-1" />
                            <span className="font-mono text-xs text-yeikar-neutral/60">
                              Esperado <b className="text-yeikar-secondary">{fmtNum(m.cantidad_esperada)}</b> {unidad}
                              {' · '}Registrado <b className={reg.cantidad >= m.cantidad_esperada && m.cantidad_esperada > 0 ? 'text-emerald-600' : 'text-yeikar-secondary'}>{fmtNum(reg.cantidad)}</b> {unidad}
                            </span>
                          </div>
                          {m.condicion_cumplida && m.cantidad_esperada > 0 && (
                            <div className="flex items-center gap-2 mt-1.5">
                              <div className="flex-1 h-1.5 bg-white rounded-full overflow-hidden border border-yeikar-secondary-light/10">
                                <div
                                  className={`h-full rounded-full transition-all ${pct >= 100 ? 'bg-emerald-500' : 'bg-yeikar-primary'}`}
                                  style={{ width: `${pct}%` }}
                                />
                              </div>
                              {faltante > 0.0001 ? (
                                <button
                                  type="button"
                                  onClick={() => prellenarDesdeReceta(m.material_id, faltante)}
                                  className="text-[10px] font-bold px-2 py-1 rounded-lg bg-yeikar-primary text-yeikar-neutral hover:bg-yeikar-primary-dark transition-colors shrink-0"
                                  title="Prellena el formulario con la cantidad que falta"
                                >
                                  Registrar falta: {fmtNum(faltante)} {unidad}
                                </button>
                              ) : (
                                <span className="text-[10px] font-bold text-emerald-600 shrink-0">
                                  {reg.pendientes > 0 ? `Completo · ${fmtNum(reg.pendientes)} lámina(s) por confirmar` : 'Receta completa ✓'}
                                </span>
                              )}
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                  {Object.keys(matsOtrasSecciones).length > 0 && (
                    <details className="border-t border-yeikar-primary/15">
                      <summary className="px-4 py-2 text-[10px] font-bold uppercase tracking-wider text-yeikar-neutral/50 cursor-pointer hover:text-yeikar-secondary">
                        Otras secciones del producto ({Object.values(matsOtrasSecciones).reduce((a, l) => a + l.length, 0)} materiales)
                      </summary>
                      <div className="px-4 pb-3 space-y-2">
                        {Object.entries(matsOtrasSecciones).map(([seccion, mats]) => (
                          <div key={seccion}>
                            <span className={`text-[10px] font-bold px-2 py-0.5 rounded-md border ${SECCION_COLORS[seccion] || 'bg-stone-100 text-stone-600 border-stone-200'}`}>{seccion}</span>
                            <div className="mt-1 space-y-1">
                              {mats.map((m, i) => (
                                <div key={`${m.material_id}-${i}`} className="flex items-center justify-between text-[11px] bg-white/70 border border-yeikar-secondary-light/5 px-2.5 py-1.5 rounded-lg">
                                  <span className="font-semibold text-yeikar-secondary truncate">{m.nombre}</span>
                                  <span className="font-mono text-yeikar-neutral/50 shrink-0 ml-2">
                                    {fmtNum(m.cantidad_esperada)} {m.es_corte ? 'cortes' : m.unidad}
                                  </span>
                                </div>
                              ))}
                            </div>
                          </div>
                        ))}
                      </div>
                    </details>
                  )}
                </div>
              ) : (
                <p className="text-[11px] text-yeikar-neutral/40 italic">
                  Este producto no tiene receta de referencia para esta área — registra el consumo libremente.
                </p>
              )}

              {/* ── 2. REGISTRAR MATERIAL CONSUMIDO ── */}
              <section className="space-y-3">
                <div className="flex items-baseline justify-between gap-2">
                  <h3 className="text-sm font-bold font-headline text-yeikar-secondary">Registrar material consumido</h3>
                  <span className="text-[10px] font-mono text-yeikar-neutral/40">descuenta stock y genera egreso</span>
                </div>
                <form onSubmit={handleAddConsumo} className="space-y-2 bg-yeikar-tertiary/30 p-3 rounded-2xl border border-yeikar-secondary-light/5">
                  <div className="grid grid-cols-1 sm:grid-cols-12 gap-2">
                    {/* Material */}
                    <div className="sm:col-span-6 relative">
                      <label className="block text-[10px] font-headline font-bold uppercase tracking-wider text-yeikar-secondary/70 mb-1">Material</label>
                      <input
                        type="text"
                        placeholder="Buscar material…"
                        value={materialSearch}
                        autoComplete="off"
                        required
                        onFocus={() => setShowMaterialDropdown(true)}
                        onChange={(e) => {
                          setMaterialSearch(e.target.value);
                          setShowMaterialDropdown(true);
                          if (!e.target.value) setNewConsumo(prev => ({ ...prev, material_id: '' }));
                        }}
                        className="w-full text-xs bg-white border border-yeikar-secondary-light/10 rounded-xl px-3 pr-3 py-2.5 focus:outline-none focus:border-yeikar-primary"
                      />
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
                                  setNewConsumo(prev => ({
                                    ...prev,
                                    material_id: String(m.id),
                                    // El material define el modo de captura: reset.
                                    unidad_captura: '', modo_pieza: false,
                                    pieza_largo: '', pieza_ancho: '', pieza_espesor: '',
                                    ancho_corte_cm: '', largo_corte_cm: '', origen_sobrante_id: '',
                                  }));
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
                    {/* Cantidad */}
                    <div className="sm:col-span-3">
                      <label className="block text-[10px] font-headline font-bold uppercase tracking-wider text-yeikar-secondary/70 mb-1">
                        {esMaterialLaminar(materialConsumo) && newConsumo.es_lamina_completa
                          ? 'N.º de láminas'
                          : dimConsumo === 'VOLUMEN' && newConsumo.modo_pieza
                            ? 'N.º de piezas'
                            : dimConsumo === 'VOLUMEN'
                              ? 'Cantidad (m³)'
                              : 'Cantidad'}
                      </label>
                      <input
                        type="number"
                        step="0.01"
                        min="0"
                        placeholder="0"
                        value={newConsumo.cantidad}
                        onChange={(e) => setNewConsumo(prev => ({ ...prev, cantidad: e.target.value }))}
                        required
                        className="w-full text-xs bg-white border border-yeikar-secondary-light/10 rounded-xl p-2.5 focus:outline-none focus:border-yeikar-primary font-mono"
                      />
                    </div>
                    {/* Solicitante (prellenado con el responsable) */}
                    <div className="sm:col-span-3">
                      <label className="block text-[10px] font-headline font-bold uppercase tracking-wider text-yeikar-secondary/70 mb-1">Solicitante</label>
                      <SearchSelect
                        value={newConsumo.solicitante_id || null}
                        onChange={(v) => setNewConsumo(prev => ({ ...prev, solicitante_id: String(v) }))}
                        options={empleados.map((emp) => ({ value: emp.id, label: emp.nombre }))}
                        placeholder="¿Quién pide?"
                      />
                    </div>
                    <div className="sm:col-span-12 flex justify-end">
                      <button
                        type="submit"
                        disabled={consumoSubmitting}
                        className="bg-yeikar-primary text-yeikar-neutral text-xs font-bold font-headline py-2 px-5 rounded-xl hover:bg-yeikar-primary-dark disabled:opacity-50 disabled:cursor-not-allowed transition-colors shadow-sm"
                      >
                        {consumoSubmitting ? 'Guardando…' : '+ Agregar material'}
                      </button>
                    </div>
                  </div>

                  {/* Captura flexible de madera: el modo depende de la unidad del material. */}
                  {materialConsumo && dimConsumo === 'LONGITUD' && (
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="text-[10px] font-semibold text-yeikar-neutral/50 uppercase">Digitar en:</span>
                      {([['M', 'mts'], ['CM', 'cm']] as const).map(([valor, etiqueta]) => (
                        <button
                          key={valor}
                          type="button"
                          onClick={() => setNewConsumo(prev => ({ ...prev, unidad_captura: valor === 'M' ? '' : valor }))}
                          className={`text-[10px] font-bold px-2 py-1 rounded-lg border transition-colors ${
                            (newConsumo.unidad_captura || 'M') === valor
                              ? 'bg-yeikar-primary text-yeikar-neutral border-yeikar-primary'
                              : 'bg-white text-yeikar-neutral/60 border-yeikar-secondary-light/15 hover:border-yeikar-primary/40'
                          }`}
                        >
                          {etiqueta}
                        </button>
                      ))}
                      {newConsumo.cantidad && parseFloat(newConsumo.cantidad) > 0 && (
                        <span className="text-[10px] font-mono text-emerald-700 bg-emerald-50 border border-emerald-200 rounded-lg px-2 py-0.5">
                          Descontará: {fmtNum(convertirCapturaLineal(parseFloat(newConsumo.cantidad), (newConsumo.unidad_captura || 'M') as UnidadCaptura))} m
                        </span>
                      )}
                    </div>
                  )}
                  {materialConsumo && dimConsumo === 'VOLUMEN' && (
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="text-[10px] font-semibold text-yeikar-neutral/50 uppercase">Como:</span>
                      {([['M3', 'm³'], ['PIEZA', 'Por pieza']] as const).map(([valor, etiqueta]) => (
                        <button
                          key={valor}
                          type="button"
                          onClick={() => setNewConsumo(prev => ({ ...prev, modo_pieza: valor === 'PIEZA' }))}
                          className={`text-[10px] font-bold px-2 py-1 rounded-lg border transition-colors ${
                            (newConsumo.modo_pieza ? 'PIEZA' : 'M3') === valor
                              ? 'bg-yeikar-primary text-yeikar-neutral border-yeikar-primary'
                              : 'bg-white text-yeikar-neutral/60 border-yeikar-secondary-light/15 hover:border-yeikar-primary/40'
                          }`}
                        >
                          {etiqueta}
                        </button>
                      ))}
                    </div>
                  )}
                  {materialConsumo && dimConsumo === 'VOLUMEN' && newConsumo.modo_pieza && (
                    <div className="space-y-2">
                      <div className="grid grid-cols-3 gap-2">
                        {([['pieza_largo', 'Largo'], ['pieza_ancho', 'Ancho'], ['pieza_espesor', 'Espesor']] as const).map(([campo, etiqueta]) => (
                          <input
                            key={campo}
                            type="number"
                            step="0.01"
                            min="0"
                            placeholder={etiqueta}
                            value={newConsumo[campo]}
                            onChange={(e) => setNewConsumo(prev => ({ ...prev, [campo]: e.target.value }))}
                            required
                            className="w-full text-xs bg-white border border-yeikar-secondary-light/10 rounded-xl p-2.5 focus:outline-none focus:border-yeikar-primary font-mono"
                          />
                        ))}
                      </div>
                      {newConsumo.pieza_largo && newConsumo.pieza_ancho && newConsumo.pieza_espesor && parseFloat(newConsumo.cantidad || '0') > 0 && (
                        <p className="text-[10px] font-mono text-emerald-700 bg-emerald-50 border border-emerald-200 rounded-lg px-2 py-1">
                          Fórmula de la casa: ({newConsumo.pieza_largo}×{newConsumo.pieza_ancho}×{newConsumo.pieza_espesor}) × {newConsumo.cantidad} ÷ 10000 ={' '}
                          <span className="font-bold">
                            {fmtNum4(volumenPieza(
                              { largo: parseFloat(newConsumo.pieza_largo), ancho: parseFloat(newConsumo.pieza_ancho), espesor: parseFloat(newConsumo.pieza_espesor) },
                              parseFloat(newConsumo.cantidad) || 0,
                            ))} m³
                          </span>{' '}a descontar
                        </p>
                      )}
                    </div>
                  )}

                  {/* Consumo por CORTES (materiales laminares) */}
                  {materialConsumo && esMaterialLaminar(materialConsumo) && (
                    <div className="space-y-2">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="text-[10px] font-semibold text-yeikar-neutral/50 uppercase">
                          Lámina de {materialConsumo.largo_cm}×{materialConsumo.ancho_cm} cm — modo:
                        </span>
                        <button
                          type="button"
                          onClick={() => setNewConsumo(prev => ({ ...prev, es_lamina_completa: !prev.es_lamina_completa, ancho_corte_cm: '', largo_corte_cm: '', origen_sobrante_id: '' }))}
                          className={`text-[10px] font-bold px-2 py-1 rounded-lg border transition-colors ${
                            newConsumo.es_lamina_completa
                              ? 'bg-amber-500 text-white border-amber-500'
                              : 'bg-white text-yeikar-neutral/60 border-yeikar-secondary-light/15 hover:border-amber-400'
                          }`}
                        >
                          Lámina completa (confirmar uso después)
                        </button>
                        <button
                          type="button"
                          onClick={() => setNewConsumo(prev => ({ ...prev, es_lamina_completa: false }))}
                          className={`text-[10px] font-bold px-2 py-1 rounded-lg border transition-colors ${
                            !newConsumo.es_lamina_completa
                              ? 'bg-yeikar-primary text-yeikar-neutral border-yeikar-primary'
                              : 'bg-white text-yeikar-neutral/60 border-yeikar-secondary-light/15 hover:border-yeikar-primary/40'
                          }`}
                        >
                          Corte directo
                        </button>
                      </div>

                      {newConsumo.es_lamina_completa ? (
                        <p className="text-[10px] font-mono text-amber-800 bg-amber-50 border border-amber-200 rounded-lg px-2 py-1">
                          Se descuenta(n) la(s) lámina(s) completa(s) del depósito ahora (costo provisional{' '}
                          {fmt(materialConsumo.costo_base)} c/u). Cuando el trabajador diga cuánto se usó,
                          se confirma por cortes: el costo se ajusta al área real usada, se devuelven
                          láminas sin abrir y el pedazo restante queda como sobrante reutilizable.
                        </p>
                      ) : (
                        <>
                          <div className="flex items-center gap-2 flex-wrap">
                            <span className="text-[10px] font-semibold text-yeikar-neutral/50 uppercase">
                              Corte de lámina (opcional — deja vacío para láminas/fracciones enteras):
                            </span>
                          </div>
                          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                            <input
                              type="number"
                              step="0.01"
                              min="0"
                              placeholder="Ancho cm (ej. 80)"
                              value={newConsumo.ancho_corte_cm}
                              onChange={(e) => setNewConsumo(prev => ({ ...prev, ancho_corte_cm: e.target.value }))}
                              className="w-full text-xs bg-white border border-yeikar-secondary-light/10 rounded-xl p-2.5 focus:outline-none focus:border-yeikar-primary font-mono"
                            />
                            <input
                              type="number"
                              step="0.01"
                              min="0"
                              placeholder="Largo cm (ej. 130)"
                              value={newConsumo.largo_corte_cm}
                              onChange={(e) => setNewConsumo(prev => ({ ...prev, largo_corte_cm: e.target.value }))}
                              className="w-full text-xs bg-white border border-yeikar-secondary-light/10 rounded-xl p-2.5 focus:outline-none focus:border-yeikar-primary font-mono"
                            />
                            {newConsumo.ancho_corte_cm && newConsumo.largo_corte_cm && (
                              <select
                                value={newConsumo.origen_sobrante_id}
                                onChange={(e) => setNewConsumo(prev => ({ ...prev, origen_sobrante_id: e.target.value as '' }))}
                                className="w-full text-xs bg-white border border-yeikar-secondary-light/10 rounded-xl p-2.5 focus:outline-none focus:border-yeikar-primary sm:col-span-2"
                              >
                                <option value="">Lámina nueva del depósito</option>
                                {sobrantesQueCaben.map(({ s, caben }) => (
                                  <option key={s.id} value={s.id}>
                                    Sobrante {s.largo_cm}×{s.ancho_cm} cm (caben {caben})
                                  </option>
                                ))}
                              </select>
                            )}
                          </div>
                          {newConsumo.ancho_corte_cm && newConsumo.largo_corte_cm && (() => {
                            const ac = parseFloat(newConsumo.ancho_corte_cm);
                            const lc = parseFloat(newConsumo.largo_corte_cm);
                            const L = parseFloat(String(materialConsumo.largo_cm));
                            const A = parseFloat(String(materialConsumo.ancho_cm));
                            const areaLamina = L * A;
                            if (!(ac > 0 && lc > 0) || areaLamina <= 0) return null;
                            const cabeAlgo = (lc <= L && ac <= A) || (ac <= L && lc <= A);
                            if (!cabeAlgo) {
                              return (
                                <p className="text-[10px] font-mono text-red-600 bg-red-50 border border-red-200 rounded-lg px-2 py-1">
                                  Un corte de {ac}×{lc} no cabe en la lámina de {L}×{A} cm.
                                </p>
                              );
                            }
                            const porLamina = Math.max(
                              lc <= L && ac <= A ? Math.floor(L / lc) * Math.floor(A / ac) : 0,
                              ac <= L && lc <= A ? Math.floor(L / ac) * Math.floor(A / lc) : 0,
                            );
                            const cantidad = parseFloat(newConsumo.cantidad || '0');
                            const laminasEquiv = cantidad > 0 ? (cantidad * ac * lc / areaLamina).toFixed(2) : null;
                            const laminaNecesarias = porLamina > 0 && cantidad > 0 ? Math.ceil(cantidad / porLamina) : null;
                            return (
                              <p className="text-[10px] font-mono text-yeikar-secondary bg-yeikar-primary/5 border border-yeikar-primary/20 rounded-lg px-2 py-1">
                                {cantidad > 0 ? `${cantidad} corte(s) de ${ac}×${lc} cm ≈ ` : `Corte de ${ac}×${lc} cm — `}
                                {laminasEquiv && <span className="font-bold">{laminasEquiv} lámina(s)</span>}
                                {porLamina > 0 && <span> · caben {porLamina} por lámina</span>}
                                {laminaNecesarias && !newConsumo.origen_sobrante_id && <span> · se abrirán {laminaNecesarias} lámina(s) nueva(s) y el resto queda como sobrante</span>}
                                {newConsumo.origen_sobrante_id && <span> · sin descuento de láminas (sale del sobrante)</span>}
                              </p>
                            );
                          })()}
                        </>
                      )}
                    </div>
                  )}

                  {/* Avanzado: componente y consumo extra */}
                  <details className="text-xs">
                    <summary className="cursor-pointer select-none text-[10px] font-bold uppercase tracking-wider text-yeikar-neutral/50 hover:text-yeikar-secondary w-fit">
                      Opciones avanzadas (componente · consumo extra)
                    </summary>
                    <div className="flex items-center gap-2 flex-wrap mt-2">
                      <input
                        list="componentes-sugeridos"
                        placeholder="Componente (ej. CAMA, NOCHERO…)"
                        value={newConsumo.componente}
                        onChange={(e) => setNewConsumo(prev => ({ ...prev, componente: e.target.value }))}
                        className="w-48 text-[10px] bg-white border border-yeikar-secondary-light/10 rounded-lg px-2 py-1.5 focus:outline-none focus:border-yeikar-primary font-mono"
                      />
                      <datalist id="componentes-sugeridos">
                        {['CAMA', 'NOCHERO', 'CABECERA', 'ESTRUCTURA', 'REPISA', 'PUERTA', 'GAVETA', 'TAPA', 'BASE'].map((c) => (
                          <option key={c} value={c} />
                        ))}
                      </datalist>
                      <label className="flex items-center gap-1.5 text-[10px] font-semibold text-yeikar-neutral/60 cursor-pointer select-none">
                        <input
                          type="checkbox"
                          checked={newConsumo.es_excedente}
                          onChange={(e) => setNewConsumo(prev => ({ ...prev, es_excedente: e.target.checked }))}
                          className="accent-red-600"
                        />
                        <span className={newConsumo.es_excedente ? 'text-red-600 font-bold' : ''}>
                          Consumo extra (daño/desperdicio)
                        </span>
                      </label>
                      {newConsumo.es_excedente && (
                        <select
                          value={newConsumo.motivo_exceso}
                          onChange={(e) => setNewConsumo(prev => ({ ...prev, motivo_exceso: e.target.value }))}
                          className="text-[10px] bg-white border border-red-200 rounded-lg px-2 py-1.5 focus:outline-none focus:border-red-500 font-mono"
                        >
                          <option value="">Motivo…</option>
                          {['DAÑO', 'RETRABAJO', 'DESPERDICIO', 'PRUEBA', 'OTRO'].map((m) => (
                            <option key={m} value={m}>{m}</option>
                          ))}
                        </select>
                      )}
                    </div>
                  </details>
                </form>

                {/* Lista de consumos */}
                {consumos.length > 0 && (
                  <div className="space-y-2 max-h-64 overflow-y-auto pr-1">
                    {consumos.map((c) => {
                      const costo = c.costo_unitario !== undefined && c.costo_unitario !== null ? c.costo_unitario : (c.material?.costo_base || 0);
                      const subtotal = c.cantidad * costo;
                      return (
                        <div key={c.id} className="flex items-center justify-between bg-white border border-yeikar-secondary-light/10 p-3 rounded-xl shadow-xs text-xs hover:border-yeikar-primary/30 transition-colors">
                          <div className="min-w-0">
                            <div className="flex items-center gap-1.5 flex-wrap">
                              <p className="font-bold text-yeikar-secondary text-sm">{c.material?.nombre}</p>
                              {c.estado === 'PENDIENTE' && (
                                <span className="text-[9px] font-bold px-1.5 py-0.5 rounded-md bg-amber-100 text-amber-700 border border-amber-300 uppercase">
                                  PENDIENTE · {c.cantidad} lámina(s)
                                </span>
                              )}
                              {c.es_excedente && (
                                <span className="text-[9px] font-bold px-1.5 py-0.5 rounded-md bg-red-100 text-red-600 border border-red-200 uppercase">
                                  EXTRA {c.motivo_exceso || 'OTRO'}
                                </span>
                              )}
                              {c.componente && (
                                <span className="text-[9px] font-bold px-1.5 py-0.5 rounded-md bg-indigo-50 text-indigo-600 border border-indigo-200 uppercase">
                                  {c.componente}
                                </span>
                              )}
                              {c.seccion && (
                                <span className="text-[9px] font-bold px-1.5 py-0.5 rounded-md bg-stone-100 text-stone-500 border border-stone-200 uppercase">
                                  {c.seccion}
                                </span>
                              )}
                            </div>
                            <p className="text-[11px] text-yeikar-neutral/60 font-mono mt-0.5">
                              Cant: <span className="font-bold text-yeikar-secondary">{c.cantidad}</span>
                              {etiquetaCaptura(c) && <span className="text-yeikar-neutral/40"> · {etiquetaCaptura(c)}</span>}
                              {' '}| Unit: <span className="font-bold">${costo.toLocaleString('es-CO')}</span>
                              {c.estado === 'PENDIENTE' && <span className="text-amber-600/80"> · provisional</span>}
                            </p>
                            <p className="text-[10px] text-yeikar-neutral/40 mt-0.5">
                              {c.solicitante_nombre && <span className="font-semibold text-yeikar-secondary/70">Pide: {c.solicitante_nombre}</span>}
                              {c.solicitante_nombre && c.creador_nombre ? ' · ' : ''}
                              {c.creador_nombre ? `Registrado por ${c.creador_nombre}` : ''}
                            </p>
                          </div>
                          <div className="flex items-center gap-3 shrink-0">
                            <span className="font-mono font-bold text-sm text-yeikar-primary">
                              ${subtotal.toLocaleString('es-CO')}
                            </span>
                            {c.estado === 'PENDIENTE' && (
                              <button
                                onClick={() => {
                                  setConfirmarForm({
                                    cantidad_cortes: '', largo_corte_cm: '', ancho_corte_cm: '',
                                    sobrante_largo_cm: '', sobrante_ancho_cm: '',
                                  });
                                  setConsumoAConfirmar(c);
                                }}
                                className="text-amber-700 hover:text-amber-900 font-bold text-xs p-1 transition-colors bg-amber-50 border border-amber-200 rounded-lg px-2"
                                title="Confirmar cuánto se usó de la lámina (por cortes)"
                              >
                                Confirmar uso
                              </button>
                            )}
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
                    })}
                  </div>
                )}
              </section>

              {/* ── 3. MANO DE OBRA ── */}
              <section className="space-y-3">
                <div className="flex items-baseline justify-between gap-2">
                  <h3 className="text-sm font-bold font-headline text-yeikar-secondary">Registrar mano de obra</h3>
                  <span className="text-[10px] font-mono text-yeikar-neutral/40">alimenta el costo de la orden</span>
                </div>
                {stage.estado !== 'EN_PROCESO' && (
                  <div className="flex items-center gap-2 flex-wrap bg-amber-50 border border-amber-200 rounded-xl px-3 py-2 text-[11px] font-semibold text-amber-800">
                    <svg className="w-4 h-4 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                    </svg>
                    La etapa debe estar EN PROCESO para registrar mano de obra.
                    {stage.estado === 'ASIGNADA' && (
                      <button
                        type="button"
                        onClick={() => onCambiarEstado(stage.id, 'EN_PROCESO')}
                        disabled={statusUpdating}
                        className="ml-auto bg-yeikar-primary text-yeikar-neutral text-[10px] font-bold px-2.5 py-1 rounded-lg hover:bg-yeikar-primary-dark disabled:opacity-50 transition-colors"
                      >
                        Iniciar trabajo
                      </button>
                    )}
                  </div>
                )}
                <form onSubmit={handleAddManoObra} className="space-y-2 bg-yeikar-tertiary/30 p-3 rounded-2xl border border-yeikar-secondary-light/5">
                  <div className="grid grid-cols-1 sm:grid-cols-12 gap-2">
                    <div className="sm:col-span-4">
                      <label className="block text-[10px] font-headline font-bold uppercase tracking-wider text-yeikar-secondary/70 mb-1">Empleado</label>
                      <SearchSelect
                        value={newManoObra.empleado_id}
                        onChange={(v) => setNewManoObra(prev => ({ ...prev, empleado_id: String(v) }))}
                        options={empleados.map((e) => ({ value: e.id, label: `${e.nombre}` }))}
                        placeholder="Empleado…"
                      />
                    </div>
                    <div className="sm:col-span-5">
                      <label className="block text-[10px] font-headline font-bold uppercase tracking-wider text-yeikar-secondary/70 mb-1">Tarifa</label>
                      <SearchSelect
                        value={newManoObra.costo_id}
                        onChange={(v) => seleccionarCostoMo(String(v))}
                        options={[
                          { value: '', label: '— Sin tarifa (monto manual) —' },
                          ...opcionesCosto.map((o) => ({ value: String(o.id), label: `${o.descripcion} · $${o.precio.toLocaleString('es-CO')}` })),
                        ]}
                        placeholder="Costo de producción (autocompleta el monto)"
                      />
                    </div>
                    <div className="sm:col-span-3">
                      <label className="block text-[10px] font-headline font-bold uppercase tracking-wider text-yeikar-secondary/70 mb-1">Monto</label>
                      <input
                        type="number"
                        min="0"
                        step="1000"
                        placeholder="$"
                        value={newManoObra.monto}
                        onChange={(e) => setNewManoObra(prev => ({ ...prev, monto: e.target.value }))}
                        required
                        className="w-full text-xs bg-white border border-yeikar-secondary-light/10 rounded-xl p-2.5 focus:outline-none focus:border-yeikar-primary font-mono"
                      />
                    </div>
                  </div>

                  {mostrarNuevoCosto && (
                    <div className="grid grid-cols-1 sm:grid-cols-12 gap-2 bg-white border border-dashed border-yeikar-primary/40 rounded-xl p-2 items-center">
                      <div className="sm:col-span-6">
                        <input
                          type="text"
                          value={nuevoCosto.descripcion}
                          onChange={(e) => setNuevoCosto(prev => ({ ...prev, descripcion: e.target.value }))}
                          placeholder="Tipo de costo (ej. HECHURA EXTRA)"
                          className="w-full text-xs bg-white border border-yeikar-secondary-light/10 rounded-xl p-2.5 focus:outline-none focus:border-yeikar-primary"
                        />
                      </div>
                      <div className="sm:col-span-2">
                        <input
                          type="number"
                          min="0"
                          step="1000"
                          value={nuevoCosto.precio}
                          onChange={(e) => setNuevoCosto(prev => ({ ...prev, precio: e.target.value }))}
                          placeholder="Precio ($)"
                          className="w-full text-xs bg-white border border-yeikar-secondary-light/10 rounded-xl p-2.5 focus:outline-none focus:border-yeikar-primary font-mono"
                        />
                      </div>
                      <div className="sm:col-span-2">
                        <select
                          value={nuevoCosto.area_id || String(stage.area_id ?? '')}
                          onChange={(e) => setNuevoCosto(prev => ({ ...prev, area_id: e.target.value }))}
                          className="w-full text-xs bg-white border border-yeikar-secondary-light/10 rounded-xl p-2.5 focus:outline-none focus:border-yeikar-primary"
                          title="Área del tarifario (por defecto, la de la etapa)"
                        >
                          {areas.map((a) => (
                            <option key={a.id} value={a.id}>{a.nombre}</option>
                          ))}
                        </select>
                      </div>
                      <div className="sm:col-span-2 flex gap-1">
                        <button
                          type="button"
                          onClick={crearCostoAlVuelo}
                          disabled={creandoCosto}
                          className="flex-1 bg-emerald-500 text-white text-[11px] font-bold py-2 px-2 rounded-xl hover:bg-emerald-600 disabled:opacity-50 transition-colors"
                        >
                          {creandoCosto ? '…' : 'Crear'}
                        </button>
                        <button
                          type="button"
                          onClick={() => { setMostrarNuevoCosto(false); setNuevoCosto({ descripcion: '', precio: '', area_id: '' }); }}
                          className="px-2 text-yeikar-neutral/40 hover:text-yeikar-neutral font-bold"
                          title="Cancelar"
                        >
                          ×
                        </button>
                      </div>
                    </div>
                  )}

                  <input
                    type="text"
                    value={newManoObra.observaciones}
                    onChange={(e) => setNewManoObra(prev => ({ ...prev, observaciones: e.target.value }))}
                    placeholder="Comentario (opcional): detalle de la tarea, acuerdo con el trabajador…"
                    className="w-full text-xs bg-white border border-yeikar-secondary-light/10 rounded-xl p-2.5 focus:outline-none focus:border-yeikar-primary"
                  />

                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      onClick={() => setMostrarNuevoCosto(v => !v)}
                      className="text-[11px] font-bold text-yeikar-primary-dark hover:underline"
                    >
                      {mostrarNuevoCosto ? '× Cancelar nuevo costo' : '+ Nuevo costo de producción'}
                    </button>
                    <span className="flex-1" />
                    <button
                      type="submit"
                      disabled={stage.estado !== 'EN_PROCESO'}
                      className="bg-yeikar-primary text-yeikar-neutral text-xs font-bold font-headline py-2 px-4 rounded-xl hover:bg-yeikar-primary-dark disabled:opacity-50 disabled:cursor-not-allowed transition-colors shadow-sm"
                    >
                      + Agregar mano de obra
                    </button>
                  </div>
                </form>

                {manoObras.length > 0 && (
                  <div className="space-y-2 max-h-48 overflow-y-auto pr-1">
                    {manoObras.map((mo) => (
                      <div key={mo.id} className="flex items-center justify-between bg-white border border-yeikar-secondary-light/10 p-3 rounded-xl shadow-xs text-xs hover:border-yeikar-primary/30 transition-colors">
                        <div className="min-w-0">
                          <p className="font-bold text-yeikar-secondary text-sm">
                            {mo.empleado ? `${mo.empleado.nombre}` : `Empleado #${mo.empleado_id}`}
                          </p>
                          <p className="text-[10px] text-yeikar-neutral/40 mt-0.5">
                            {mo.creador_nombre ? `Registrado por ${mo.creador_nombre}` : ''}
                            {mo.pagado ? ' · Egreso generado en Gastos' : ''}
                          </p>
                          {mo.precio_produccion_descripcion && (
                            <span className="inline-block mt-1 text-[9px] font-bold uppercase bg-yeikar-primary/10 text-yeikar-primary-dark px-1.5 py-0.5 rounded">
                              {mo.precio_produccion_descripcion}
                            </span>
                          )}
                          {mo.observaciones && (
                            <p className="text-[11px] text-yeikar-neutral/60 italic mt-0.5">{mo.observaciones}</p>
                          )}
                        </div>
                        <div className="flex items-center gap-2 shrink-0">
                          <button
                            type="button"
                            onClick={() => handleToggleListoNomina(mo.id, mo.listo_nomina !== false)}
                            className={`px-2.5 py-1 rounded-lg text-[10px] font-bold transition-colors flex items-center gap-1 ${
                              mo.listo_nomina !== false
                                ? 'bg-emerald-100 text-emerald-800 hover:bg-emerald-200 border border-emerald-300'
                                : 'bg-stone-100 text-stone-600 hover:bg-stone-200 border border-stone-300'
                            }`}
                            title={
                              mo.listo_nomina !== false
                                ? 'Trabajo terminado: entrará en la nómina de esta semana (clic para pausar)'
                                : 'Trabajo pendiente: NO entrará en la nómina de esta semana (clic para incluirlo)'
                            }
                          >
                            <span className={`w-1.5 h-1.5 rounded-full ${mo.listo_nomina !== false ? 'bg-emerald-600' : 'bg-stone-400'}`} />
                            {mo.listo_nomina !== false ? 'Listo nómina' : 'Pendiente'}
                          </button>
                          <span className={`font-mono font-bold text-sm ${mo.pagado ? 'text-emerald-600' : 'text-yeikar-primary'}`}>
                            ${(mo.monto * (1 + (mo.porcentaje_recargo || 0) / 100)).toLocaleString('es-CO')}
                          </span>
                          {!mo.pagado && (
                            <button
                              type="button"
                              onClick={() => setManoObraAEliminar(mo.id)}
                              className="text-red-500 hover:text-red-700 font-medium text-xs p-1 transition-colors ml-1"
                              title="Eliminar mano de obra"
                            >
                              Eliminar
                            </button>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </section>
            </>
          )}

          {tab === 'historial' && (
            <div className="space-y-1.5">
              {etapasOrden.length === 0 ? (
                <p className="text-xs text-yeikar-neutral/40 text-center py-8">Sin historial de etapas para esta orden.</p>
              ) : (
                etapasOrden.map((et) => (
                  <div key={et.id} className={`flex items-center justify-between p-2.5 rounded-xl text-xs border ${
                    et.id === stage.id
                      ? 'bg-yeikar-primary/10 border-yeikar-primary/30'
                      : 'bg-yeikar-tertiary/30 border-yeikar-secondary-light/10'
                  }`}>
                    <div className="flex items-center gap-2 min-w-0">
                      <span className={`w-2 h-2 rounded-full shrink-0 ${
                        et.estado === 'COMPLETADA' ? 'bg-green-500' : et.estado === 'EN_PROCESO' ? 'bg-amber-400' : et.estado === 'PAUSADA' ? 'bg-red-400' : 'bg-blue-400'
                      }`} />
                      <span className="font-bold text-yeikar-secondary">{et.area?.nombre || `Área #${et.area_id}`}</span>
                      {et.es_retrabajo && (
                        <span className="text-[9px] font-bold px-1.5 py-0.5 rounded-md bg-amber-100 text-amber-700 uppercase">Retrabajo</span>
                      )}
                      {et.id === stage.id && (
                        <span className="text-[9px] font-bold px-1.5 py-0.5 rounded-md bg-yeikar-primary text-yeikar-neutral uppercase">Esta etapa</span>
                      )}
                    </div>
                    <div className="flex items-center gap-3 shrink-0 text-[10px] font-mono text-yeikar-neutral/50">
                      {et.empleado_responsable && <span>{et.empleado_responsable.nombre}</span>}
                      <span className="font-bold">{et.estado.replace('_', ' ')}</span>
                      {et.fecha_fin && <span>{new Date(et.fecha_fin).toLocaleDateString('es-CO')}</span>}
                    </div>
                  </div>
                ))
              )}
            </div>
          )}

          {tab === 'costos' && (
            <CostosOrdenEnVivo data={costosEnVivo} loading={costosEnVivoLoading} compacto />
          )}
        </div>

        {/* ══ TOTALES CONSOLIDADOS (sticky) ══ */}
        <div className="sticky bottom-0 z-20 bg-white/95 backdrop-blur border-t border-yeikar-secondary-light/10 px-4 sm:px-6 py-3 rounded-b-3xl">
          <div className="flex items-center gap-4 sm:gap-6">
            <div>
              <span className="text-[9px] font-bold text-yeikar-neutral/50 block uppercase tracking-wider">Materiales</span>
              <span className="text-sm font-black text-yeikar-secondary font-mono">${totalMateriales.toLocaleString('es-CO')}</span>
            </div>
            <div className="border-l border-yeikar-secondary-light/10 pl-4 sm:pl-6">
              <span className="text-[9px] font-bold text-yeikar-neutral/50 block uppercase tracking-wider">Mano de obra</span>
              <span className="text-sm font-black text-yeikar-secondary font-mono">${totalManoObra.toLocaleString('es-CO')}</span>
            </div>
            <div className="border-l border-yeikar-secondary-light/10 pl-4 sm:pl-6">
              <span className="text-[9px] font-bold text-yeikar-primary block uppercase tracking-wider">Total etapa</span>
              <span className="text-lg font-black text-yeikar-primary font-mono">${totalEtapa.toLocaleString('es-CO')}</span>
            </div>
            <span className="flex-1" />
            <button
              onClick={onClose}
              className="bg-white border border-yeikar-secondary-light/15 text-yeikar-neutral/70 hover:text-yeikar-secondary hover:bg-yeikar-tertiary/50 px-4 py-2 rounded-xl text-xs font-bold font-headline transition-all"
            >
              Cerrar
            </button>
          </div>
        </div>
      </div>

      {/* ── Confirmaciones (locales a la estación de trabajo) ── */}
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
      {consumoAConfirmar && (() => {
        const mat = consumoAConfirmar.material;
        const L = parseFloat(String(mat?.largo_cm ?? 0));
        const A = parseFloat(String(mat?.ancho_cm ?? 0));
        const pedidas = consumoAConfirmar.cantidad;
        const costoBase = parseFloat(String(mat?.costo_base ?? 0));
        const lc = parseFloat(confirmarForm.largo_corte_cm);
        const ac = parseFloat(confirmarForm.ancho_corte_cm);
        const cortes = parseFloat(confirmarForm.cantidad_cortes);
        const cabeAlgo = L > 0 && A > 0 && lc > 0 && ac > 0 && ((lc <= L && ac <= A) || (ac <= L && lc <= A));
        const porLamina = cabeAlgo
          ? Math.max(
              lc <= L && ac <= A ? Math.floor(L / lc) * Math.floor(A / ac) : 0,
              ac <= L && lc <= A ? Math.floor(L / ac) * Math.floor(A / lc) : 0,
            )
          : 0;
        const necesarias = cabeAlgo && cortes > 0 ? Math.ceil(cortes / porLamina) : null;
        const diferencia = necesarias !== null ? pedidas - necesarias : null;
        const costoReal = cabeAlgo && cortes > 0 && L * A > 0 ? (costoBase * (lc * ac) / (L * A)) * cortes : null;
        return (
          <div className="fixed inset-0 bg-yeikar-secondary/60 backdrop-blur-sm flex items-center justify-center p-4 z-[60]">
            <div className="bg-white rounded-3xl shadow-xl border border-yeikar-secondary-light/10 max-w-md w-full p-4 sm:p-6 space-y-4">
              <h3 className="text-xl font-headline font-black text-yeikar-secondary">¿Cuánto se usó de la lámina?</h3>
              <p className="text-xs text-yeikar-neutral/60">
                Pediste <b>{pedidas}</b> {pedidas === 1 ? 'lámina' : 'láminas'} de{' '}
                <span className="font-bold text-yeikar-secondary">{mat?.nombre}</span> ({L}×{A} cm).
                Escribe las piezas que ya cortaste de ella:
              </p>
              <form
                onSubmit={(e) => { e.preventDefault(); ejecutarConfirmarConsumo(); }}
                className="space-y-3"
              >
                <div className="grid grid-cols-3 gap-2">
                  <div>
                    <label className="block text-[10px] font-semibold text-yeikar-neutral/50 uppercase mb-1">Piezas</label>
                    <input
                      type="number"
                      step="0.01"
                      min="0"
                      placeholder="Ej. 5"
                      value={confirmarForm.cantidad_cortes}
                      onChange={(e) => setConfirmarForm(prev => ({ ...prev, cantidad_cortes: e.target.value }))}
                      required
                      className="w-full text-xs bg-white border border-yeikar-secondary-light/10 rounded-xl p-2.5 focus:outline-none focus:border-yeikar-primary font-mono"
                    />
                  </div>
                  <div>
                    <label className="block text-[10px] font-semibold text-yeikar-neutral/50 uppercase mb-1">Largo (cm)</label>
                    <input
                      type="number"
                      step="0.01"
                      min="0"
                      placeholder="Ej. 100"
                      value={confirmarForm.largo_corte_cm}
                      onChange={(e) => setConfirmarForm(prev => ({ ...prev, largo_corte_cm: e.target.value }))}
                      required
                      className="w-full text-xs bg-white border border-yeikar-secondary-light/10 rounded-xl p-2.5 focus:outline-none focus:border-yeikar-primary font-mono"
                    />
                  </div>
                  <div>
                    <label className="block text-[10px] font-semibold text-yeikar-neutral/50 uppercase mb-1">Ancho (cm)</label>
                    <input
                      type="number"
                      step="0.01"
                      min="0"
                      placeholder="Ej. 40"
                      value={confirmarForm.ancho_corte_cm}
                      onChange={(e) => setConfirmarForm(prev => ({ ...prev, ancho_corte_cm: e.target.value }))}
                      required
                      className="w-full text-xs bg-white border border-yeikar-secondary-light/10 rounded-xl p-2.5 focus:outline-none focus:border-yeikar-primary font-mono"
                    />
                  </div>
                </div>
                {cabeAlgo && cortes > 0 ? (
                  <div className="space-y-1 text-[10px] font-mono">
                    <p className="text-yeikar-secondary bg-yeikar-primary/5 border border-yeikar-primary/20 rounded-lg px-2 py-1">
                      En cada lámina caben <b>{porLamina}</b> piezas de {ac}×{lc} cm.
                    </p>
                    <p className="text-yeikar-secondary bg-yeikar-primary/5 border border-yeikar-primary/20 rounded-lg px-2 py-1">
                      Con <b>{cortes}</b> {cortes === 1 ? 'pieza' : 'piezas'} usas <b>{necesarias}</b> {necesarias === 1 ? 'lámina' : 'láminas'} — pediste {pedidas}:{' '}
                      {diferencia === null ? '' : diferencia > 0 ? (
                        <span className="font-bold text-emerald-700">te sobraron {diferencia} y vuelven al depósito</span>
                      ) : diferencia < 0 ? (
                        <span className="font-bold text-red-600">te faltan {-diferencia} — se descontarán del inventario</span>
                      ) : (
                        <span className="font-bold text-emerald-700">justo lo que pediste ✓</span>
                      )}
                    </p>
                    {costoReal != null && (
                      <p className="text-emerald-700 bg-emerald-50 border border-emerald-200 rounded-lg px-2 py-1">
                        Se cobra <b>${Math.round(costoReal).toLocaleString('es-CO')}</b> por lo usado. El pedazo que sobró queda guardado para otro mueble.
                      </p>
                    )}
                  </div>
                ) : lc > 0 && ac > 0 && cortes > 0 ? (
                  <p className="text-[10px] font-mono text-red-600 bg-red-50 border border-red-200 rounded-lg px-2 py-1">
                    Una pieza de {ac}×{lc} no cabe en la lámina de {L}×{A} cm. Revisa las medidas.
                  </p>
                ) : null}
                <details className="text-[10px] text-yeikar-neutral/60">
                  <summary className="cursor-pointer font-semibold">¿El pedazo que sobró tiene otras medidas? (opcional)</summary>
                  <div className="grid grid-cols-2 gap-2 mt-1">
                    <input
                      type="number"
                      step="0.01"
                      min="0"
                      placeholder="Sobrante largo cm"
                      value={confirmarForm.sobrante_largo_cm}
                      onChange={(e) => setConfirmarForm(prev => ({ ...prev, sobrante_largo_cm: e.target.value }))}
                      className="w-full text-xs bg-white border border-yeikar-secondary-light/10 rounded-lg p-2 focus:outline-none focus:border-yeikar-primary font-mono"
                    />
                    <input
                      type="number"
                      step="0.01"
                      min="0"
                      placeholder="Sobrante ancho cm"
                      value={confirmarForm.sobrante_ancho_cm}
                      onChange={(e) => setConfirmarForm(prev => ({ ...prev, sobrante_ancho_cm: e.target.value }))}
                      className="w-full text-xs bg-white border border-yeikar-secondary-light/10 rounded-lg p-2 focus:outline-none focus:border-yeikar-primary font-mono"
                    />
                  </div>
                </details>
                <div className="flex justify-end gap-2 pt-2">
                  <button
                    type="button"
                    onClick={() => setConsumoAConfirmar(null)}
                    className="px-4 py-2 rounded-xl text-sm font-bold text-yeikar-neutral/60 hover:bg-yeikar-tertiary transition-colors"
                  >
                    Cancelar
                  </button>
                  <button
                    type="submit"
                    disabled={confirmarSubmitting}
                    className="bg-yeikar-secondary text-white px-5 py-2 rounded-xl text-sm font-bold shadow-sm hover:shadow transition-all disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    {confirmarSubmitting ? 'Confirmando…' : 'Confirmar uso'}
                  </button>
                </div>
              </form>
            </div>
          </div>
        );
      })()}
    </div>
  );
}
