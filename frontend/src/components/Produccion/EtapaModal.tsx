import React, { useEffect, useMemo, useState } from 'react';
import { Loader2 } from 'lucide-react';
import {
  produccionService,
  type EtapaProduccion,
  type OrdenProduccion,
  type Area,
  type ReferenciaReceta,
  type CostosEnVivoOrden,
  type ConsumoMaterial,
} from '../../services/produccionService';
import { productosService } from '../../services/productosService';
import { getEmpleados } from '../../services/empleadosService';
import { useDebouncedValue } from '../../hooks/useDebouncedValue';
import type { SobranteLamina } from '../../services/inventarioService';
import api from '../../services/api';
import ConfirmDialog from '../ui/ConfirmDialog';
import { SearchSelect } from '../ui';
import CostosOrdenEnVivo from '../CostosOrdenEnVivo';
import { useToast } from '../../context/ToastContext';
import { fmtFechaVE } from '../../utils/fechas';
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

type TabActiva = 'registrar' | 'mano-obra' | 'historial' | 'costos';

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

/**
 * Normaliza un valor digitado a número con PUNTO decimal: el navegador puede
 * estar en locale inglés y `type="number"` rechaza la coma (0,5 → vacío →
 * "Please fill out this field"). Se usa type="text" + inputMode="decimal" y
 * esta función convierte "0,5" → 0.5. Devuelve NaN si no es numérico.
 */
const parseDecimalEs = (v: string): number => parseFloat(v.trim().replace(',', '.'));

// ── Confirmación multi-uso: una línea = una cosa que se hizo con la madera.
//    BASE = unidad base del material (m³/m); PIEZA = fórmula de la casa
//    (largo m × ancho cm × espesor cm × n.º piezas ÷ 10000); CM = la cuenta
//    del ebanista en un solo campo (÷10000 en m³, ÷100 en lineales).
type ModoUso = 'BASE' | 'PIEZA' | 'CM';

interface UsoLinea {
  modo: ModoUso;
  cantidad: string;
  pieza_largo: string;
  pieza_ancho: string;
  pieza_espesor: string;
}

const lineaUsoVacia = (): UsoLinea => ({
  modo: 'BASE', cantidad: '', pieza_largo: '', pieza_ancho: '', pieza_espesor: '',
});

/** Convierte una línea de uso a la unidad base (vista previa; la conversión
 *  real la hace el backend con el mismo motor). null = línea incompleta. */
const convertirUso = (u: UsoLinea, dim: string): number | null => {
  const v = parseDecimalEs(u.cantidad);
  if (!(v > 0)) return null;
  if (u.modo === 'CM') return dim === 'VOLUMEN' ? v / 10000 : v / 100;
  if (u.modo === 'PIEZA') {
    const l = parseDecimalEs(u.pieza_largo);
    const a = parseDecimalEs(u.pieza_ancho);
    const e = parseDecimalEs(u.pieza_espesor);
    if (!(l > 0 && a > 0 && e > 0)) return null;
    return volumenPieza({ largo: l, ancho: a, espesor: e }, v);
  }
  return v;
};

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
    // Captura flexible de madera: el modo depende de la unidad del material.
    unidad_captura: '' as '' | UnidadCaptura,
    modo_pieza: false,
    // Modo "Medidas en cm" (volumétricos): lo mismo que Por pieza pero con
    // TODAS las medidas en cm → (L×A×E) × piezas ÷ 1000000 = m³.
    modo_cm: false,
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
    // Pedido general (madera y demás): entrega hoy, uso se confirma después.
    es_pedido: false,
  });
  const [materialSearch, setMaterialSearch] = useState('');
  const [showMaterialDropdown, setShowMaterialDropdown] = useState(false);
  // Búsqueda server-side de materiales (autocomplete): el catálogo completo no
  // se carga en el cliente, se consulta por nombre/sinónimo al escribir.
  const [materialesBusqueda, setMaterialesBusqueda] = useState<Material[]>([]);
  const [materialesCargando, setMaterialesCargando] = useState(false);
  // Objeto del material elegido en el dropdown async: antes se derivaba de
  // `materiales.find(...)`, pero con catálogos grandes ese material ya no está
  // en la lista precargada.
  const [materialSeleccionado, setMaterialSeleccionado] = useState<Material | null>(null);
  const [consumoSubmitting, setConsumoSubmitting] = useState(false);
  const [consumoAEliminar, setConsumoAEliminar] = useState<number | null>(null);
  const [manoObraAEliminar, setManoObraAEliminar] = useState<number | null>(null);
  const [consumoAConfirmar, setConsumoAConfirmar] = useState<ConsumoMaterial | null>(null);
  const [confirmarForm, setConfirmarForm] = useState({
    cantidad_cortes: '', largo_corte_cm: '', ancho_corte_cm: '',
    sobrante_largo_cm: '', sobrante_ancho_cm: '',
  });
  // Confirmación MULTI-USO (madera y demás): varias líneas en un solo
  // confirmar; cada línea queda como un renglón aislado de costo.
  const [usos, setUsos] = useState<UsoLinea[]>([lineaUsoVacia()]);
  const [confirmarSubmitting, setConfirmarSubmitting] = useState(false);

  const [newManoObra, setNewManoObra] = useState({ empleado_id: '', costo_id: '', monto: '', observaciones: '' });
  const [opcionesCosto, setOpcionesCosto] = useState<{ id: number; descripcion: string; precio: number }[]>([]);
  const [mostrarNuevoCosto, setMostrarNuevoCosto] = useState(false);
  const [nuevoCosto, setNuevoCosto] = useState({ descripcion: '', precio: '', area_id: '' });
  const [creandoCosto, setCreandoCosto] = useState(false);

  const consumos = stage.consumos ?? [];
  const manoObras = stage.mano_obras ?? [];

  // ── Derivados del formulario de consumo ──
  const materialConsumo = materialSeleccionado ?? materiales.find((m) => String(m.id) === newConsumo.material_id);
  const dimConsumo = dimensionalidad(materialConsumo?.unidad_medida?.abreviatura);
  // Dimensionalidad del material que se está CONFIRMANDO (mismo motor que el
  // registro: captura flexible al confirmar el uso).
  const dimConfirmar = dimensionalidad(consumoAConfirmar?.material?.unidad_medida?.abreviatura);

  // Sobrantes del material actual que le caben al corte digitado (ambas orientaciones)
  const sobrantesQueCaben = (() => {
    if (!materialConsumo || !newConsumo.ancho_corte_cm || !newConsumo.largo_corte_cm) return [];
    const lc = parseDecimalEs(newConsumo.largo_corte_cm);
    const ac = parseDecimalEs(newConsumo.ancho_corte_cm);
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
      // PENDIENTE sin cantidad_pedida = pedido abierto (cantidad desconocida):
      // cuenta como pendiente aunque la cantidad sea 0.
      if (c.estado === 'PENDIENTE') entry.pendientes += c.cantidad_pedida == null ? 1 : c.cantidad;
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

  // ── Búsqueda async de materiales (autocomplete server-side) ──
  // El catálogo completo no se baja al cliente (con cientos de materiales solo
  // se veían los primeros 100 y en orden arbitrario). Se consulta por nombre o
  // sinónimo al escribir, con debounce.
  const materialSearchDebounced = useDebouncedValue(materialSearch, 250);
  useEffect(() => {
    if (!showMaterialDropdown) return;
    let active = true;
    setMaterialesCargando(true);
    productosService
      .getMateriales(materialSearchDebounced.trim() || undefined)
      .then((r) => { if (active) setMaterialesBusqueda(r); })
      .catch(() => { if (active) setMaterialesBusqueda([]); })
      .finally(() => { if (active) setMaterialesCargando(false); });
    return () => { active = false; };
  }, [showMaterialDropdown, materialSearchDebounced]);

  // El solicitante arranca como el responsable de la etapa (se puede cambiar):
  // en el taller quien pide el material es quien tiene la etapa asignada.
  useEffect(() => {
    const responsableId = stage.empleado_responsable?.id;
    if (!responsableId) return;
    setNewConsumo((prev) => (prev.solicitante_id ? prev : { ...prev, solicitante_id: String(responsableId) }));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [stage.id]);

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
      unidad_captura: '', modo_pieza: false, modo_cm: false,
      pieza_largo: '', pieza_ancho: '', pieza_espesor: '',
      ancho_corte_cm: '', largo_corte_cm: '', origen_sobrante_id: '',
      es_lamina_completa: false, es_pedido: false,
    }));
    setMaterialSeleccionado(null);
    // La receta puede referenciar un material que no está en la lista async;
    // lo traemos por id para conocer su unidad/dimensionalidad.
    productosService.getMaterial(materialId)
      .then((mat) => {
        setMaterialSeleccionado(mat);
        setMaterialSearch(mat.nombre || '');
      })
      .catch(() => setMaterialSearch(''));
    setShowMaterialDropdown(false);
    setTab('registrar');
  };

  // ── Registrar consumo de material ──
  const handleAddConsumo = async (e: React.FormEvent) => {
    e.preventDefault();
    if (consumoSubmitting) return;
    if (!newConsumo.material_id) return;
    // Pedido general SIN cantidad = pedido ABIERTO (piden "madera" a secas y
    // la cantidad se confirma después). Uso directo sí exige cantidad.
    const esPedidoAbierto = newConsumo.es_pedido && newConsumo.cantidad.trim() === '';
    if (!newConsumo.es_pedido && !newConsumo.cantidad) return;
    if (!newConsumo.solicitante_id) {
      toast.error('Selecciona quién solicita el material.');
      return;
    }
    const esPieza = dimConsumo === 'VOLUMEN' && newConsumo.modo_pieza;
    // Modo cm: UN solo campo con la cuenta del ebanista (ej. 832); la regla
    // de los 10000 la lleva a m³. El backend resuelve con unidad_captura='CM'.
    const esCm = dimConsumo === 'VOLUMEN' && newConsumo.modo_cm;
    if (esPieza && (!newConsumo.pieza_largo || !newConsumo.pieza_ancho || !newConsumo.pieza_espesor)) {
      toast.error('Completa las medidas de la pieza (largo × ancho × espesor).');
      return;
    }
    const esCorte = esMaterialLaminar(materialConsumo) && !!newConsumo.ancho_corte_cm && !!newConsumo.largo_corte_cm;
    const esLaminaCompleta = esMaterialLaminar(materialConsumo) && newConsumo.es_lamina_completa;
    // Pedido general: solo no-laminares (las láminas ya tienen su modo de
    // pedido) y sin cortes. Híbrido: o pedido o uso directo.
    const esPedido = newConsumo.es_pedido && !esCorte && !esLaminaCompleta;
    if (esPedidoAbierto && (esPieza || esCm)) {
      toast.error('El pedido abierto no admite captura por pieza ni en cm: la cantidad se confirma después.');
      return;
    }
    if (newConsumo.es_pedido && (esCorte || esLaminaCompleta)) {
      toast.error('El pedido general no aplica a láminas ni cortes: usa lámina completa o corte directo.');
      return;
    }
    if (esLaminaCompleta && esCorte) {
      toast.error('Elige un modo: lámina completa (confirmar después) o corte directo.');
      return;
    }
    if (esLaminaCompleta && newConsumo.origen_sobrante_id) {
      toast.error('El pedido de lámina completa no sale de sobrantes: se pide lámina nueva del depósito.');
      return;
    }
    if (esCorte && (esPieza || esCm)) {
      toast.error('El consumo por corte no admite captura por pieza volumétrica.');
      return;
    }
    if (esLaminaCompleta && (esPieza || esCm)) {
      toast.error('El pedido de lámina completa no admite captura por pieza volumétrica.');
      return;
    }
    setConsumoSubmitting(true);
    try {
      const materialId = parseInt(newConsumo.material_id);
      const cantidad = esPedidoAbierto ? null : parseDecimalEs(newConsumo.cantidad);
      const cantidadConvertida = esPedidoAbierto
        ? 0
        : esCorte
          ? cantidad!
          : esPieza
            ? volumenPieza(
                { largo: parseDecimalEs(newConsumo.pieza_largo), ancho: parseDecimalEs(newConsumo.pieza_ancho), espesor: parseDecimalEs(newConsumo.pieza_espesor) },
                cantidad!,
              )
            : esCm
              ? cantidad! / 10000
              : newConsumo.unidad_captura === 'CM'
                ? convertirCapturaLineal(cantidad!, 'CM')
                : cantidad!;
      const stockAntes = inventario[materialId];
      await produccionService.registrarConsumo({
        etapa_produccion_id: stage.id,
        material_id: materialId,
        cantidad: cantidad as unknown as number,
        fecha: new Date().toISOString(),
        seccion: referenciaReceta?.seccion_actual || undefined,
        observaciones: newConsumo.observaciones || undefined,
        solicitante_empleado_id: parseInt(newConsumo.solicitante_id),
        ...(esLaminaCompleta
          ? { es_lamina_completa: true }
          : esCorte
            ? {
                ancho_corte_cm: parseDecimalEs(newConsumo.ancho_corte_cm),
                largo_corte_cm: parseDecimalEs(newConsumo.largo_corte_cm),
                origen_sobrante_id: newConsumo.origen_sobrante_id ? parseInt(newConsumo.origen_sobrante_id) : undefined,
              }
            : esPieza
              ? {
                  pieza_largo: parseDecimalEs(newConsumo.pieza_largo),
                  pieza_ancho: parseDecimalEs(newConsumo.pieza_ancho),
                  pieza_espesor: parseDecimalEs(newConsumo.pieza_espesor),
                }
              : esCm
                ? { unidad_captura: 'CM' as const }
                : newConsumo.unidad_captura
                  ? { unidad_captura: newConsumo.unidad_captura }
                  : {}),
        ...(newConsumo.componente.trim() ? { componente: newConsumo.componente.trim() } : {}),
        // Pedido general: la cantidad digitada es lo ENTREGADO; el uso real
        // se confirma después (el backend deja el consumo PENDIENTE).
        ...(esPedido ? { es_pedido: true } : {}),
        ...(newConsumo.es_excedente
          ? { es_excedente: true, motivo_exceso: newConsumo.motivo_exceso || 'OTRO' }
          : {}),
      });
      await onRefrescarEtapa();
      setNewConsumo((prev) => ({
        ...prev,
        material_id: '', cantidad: '', observaciones: '',
        unidad_captura: '', modo_pieza: false, modo_cm: false, pieza_largo: '', pieza_ancho: '', pieza_espesor: '',
        componente: '', es_excedente: false, motivo_exceso: '',
        ancho_corte_cm: '', largo_corte_cm: '', origen_sobrante_id: '',
        es_lamina_completa: false, es_pedido: false,
      }));
      setMaterialSearch('');
      await onRecargarSobrantes();
      toast.success(
        esLaminaCompleta
          ? `Lámina completa pedida: ${fmtNum(cantidad!)} lámina(s) descontada(s) del depósito. Costo provisional — confirma el uso por cortes cuando el trabajador diga cuánto se usó.`
          : esPedidoAbierto
            ? 'Pedido abierto registrado: aún no sale nada del depósito. Se descontará y costeará al confirmar cuánto se usó.'
            : esPedido
            ? `Pedido registrado: ${fmtNum(cantidadConvertida)} ${materialConsumo?.unidad_medida?.abreviatura || ''} entregadas (costo provisional). Confirma el uso cuando digan cuánto se usó — lo que sobre vuelve solo al depósito.`
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
    // Pedido general (no-laminar): se confirma con la LISTA de usos (multi-línea).
    const esLaminar = !!(consumoAConfirmar.material?.largo_cm && consumoAConfirmar.material?.ancho_cm);
    let payload: Parameters<typeof produccionService.confirmarConsumo>[1];
    if (!esLaminar) {
      if (usos.length === 0) {
        toast.error('Agrega al menos un uso del material.');
        return;
      }
      const payloadUsos: NonNullable<Parameters<typeof produccionService.confirmarConsumo>[1]['usos']> = [];
      for (const [i, u] of usos.entries()) {
        const v = parseDecimalEs(u.cantidad);
        if (!(v > 0)) {
          toast.error(`Uso ${i + 1}: indica la cantidad (mayor a 0).`);
          return;
        }
        if (u.modo === 'PIEZA') {
          const l = parseDecimalEs(u.pieza_largo);
          const a = parseDecimalEs(u.pieza_ancho);
          const e = parseDecimalEs(u.pieza_espesor);
          if (!(l > 0 && a > 0 && e > 0)) {
            toast.error(`Uso ${i + 1}: completa las medidas de la pieza (largo × ancho × espesor).`);
            return;
          }
          payloadUsos.push({ cantidad: v, pieza_largo: l, pieza_ancho: a, pieza_espesor: e });
        } else if (u.modo === 'CM') {
          payloadUsos.push({ cantidad: v, unidad_captura: 'CM' });
        } else {
          payloadUsos.push({ cantidad: v });
        }
      }
      payload = { usos: payloadUsos };
    } else {
      const cortes = parseDecimalEs(confirmarForm.cantidad_cortes);
      const lc = parseDecimalEs(confirmarForm.largo_corte_cm);
      const ac = parseDecimalEs(confirmarForm.ancho_corte_cm);
      if (!(cortes > 0) || !(lc > 0) || !(ac > 0)) {
        toast.error('Indica la cantidad de cortes y sus medidas (largo × ancho en cm).');
        return;
      }
      payload = {
        cantidad_cortes: cortes,
        largo_corte_cm: lc,
        ancho_corte_cm: ac,
        ...(confirmarForm.sobrante_largo_cm && confirmarForm.sobrante_ancho_cm
          ? {
              sobrante_largo_cm: parseDecimalEs(confirmarForm.sobrante_largo_cm),
              sobrante_ancho_cm: parseDecimalEs(confirmarForm.sobrante_ancho_cm),
            }
          : {}),
      };
    }
    setConfirmarSubmitting(true);
    try {
      await produccionService.confirmarConsumo(consumoAConfirmar.id, payload);
      setConsumoAConfirmar(null);
      await onRefrescarEtapa();
      await onRecargarSobrantes();
      toast.success(esLaminar
        ? 'Uso confirmado: costo real aplicado, láminas ajustadas y sobrante registrado.'
        : usos.length > 1
          ? `Uso confirmado: ${usos.length} renglones de costo registrados; stock y egresos exactos.`
          : 'Uso confirmado: lo que sobró volvió al depósito y el costo quedó en lo usado.');
    } catch (error: any) {
      toast.error(error.response?.data?.detail || 'Error al confirmar el uso del material.');
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
        {/* ══ HEADER STICKY: identidad + datos de orden + acciones por intención ══ */}
        <div className="sticky top-0 z-20 bg-white/95 backdrop-blur rounded-t-3xl border-b border-yeikar-secondary-light/10 px-4 sm:px-6 pt-4 pb-3 space-y-2.5">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0 space-y-1.5">
            {/* Fila 1 — identidad de la etapa */}
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

            {/* Fila 2 — datos de la orden en chips agrupados */}
            <div className="flex items-center gap-1.5 flex-wrap">
              {detalle?.pedido?.cliente?.nombre && (
                <span className="text-[11px] font-bold text-yeikar-primary-dark bg-yeikar-primary/10 border border-yeikar-primary/20 rounded-lg px-2 py-1">
                  {detalle.pedido.cliente.nombre}
                </span>
              )}
              {!detalle && (
                <span className="text-[11px] font-bold text-yeikar-primary-dark bg-yeikar-primary/10 border border-yeikar-primary/20 rounded-lg px-2 py-1">
                  {esOrdenExhibicion(stage.orden) ? 'Pieza de exhibición' : 'Sin pedido'}
                </span>
              )}
              <span className="text-[11px] font-mono text-yeikar-neutral/55 bg-yeikar-tertiary/40 border border-yeikar-secondary-light/10 rounded-lg px-2 py-1">
                Orden #{stage.orden_produccion_id}
              </span>
              {medidas && (
                <span className="text-[11px] font-mono text-yeikar-neutral/55 bg-yeikar-tertiary/40 border border-yeikar-secondary-light/10 rounded-lg px-2 py-1">
                  {medidas}
                </span>
              )}
              {detalle?.cantidad != null && (
                <span className="text-[11px] font-mono text-yeikar-neutral/55 bg-yeikar-tertiary/40 border border-yeikar-secondary-light/10 rounded-lg px-2 py-1">
                  × {detalle.cantidad} und
                </span>
              )}
              {detalle?.pedido?.fecha_entrega_estimada && (
                <span className="text-[11px] font-bold text-amber-700 bg-amber-50 border border-amber-200 rounded-lg px-2 py-1" title="Fecha estimada de entrega al cliente">
                  Entrega {new Date(detalle.pedido.fecha_entrega_estimada + 'T00:00:00').toLocaleDateString('es-CO', { day: '2-digit', month: '2-digit', year: 'numeric' })}
                </span>
              )}
              {stage.orden?.estado && (
                <span className={`text-[11px] font-bold rounded-lg px-2 py-1 border ${
                  stage.orden.estado === 'FINALIZADA' ? 'text-green-700 bg-green-50 border-green-200'
                  : stage.orden.estado === 'PAUSADA' ? 'text-red-600 bg-red-50 border-red-200'
                  : 'text-blue-700 bg-blue-50 border-blue-200'
                }`}>
                  Orden {stage.orden.estado.replace('_', ' ').toLowerCase()}
                </span>
              )}
              <span className="text-[11px] font-mono text-yeikar-neutral/55 bg-yeikar-tertiary/40 border border-yeikar-secondary-light/10 rounded-lg px-2 py-1 flex items-center gap-1">
                <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" /></svg>
                {stage.empleado_responsable ? stage.empleado_responsable.nombre : 'Sin asignar'}
              </span>
              {stage.fecha_inicio && (
                <span className="text-[11px] font-mono text-yeikar-neutral/55 bg-yeikar-tertiary/40 border border-yeikar-secondary-light/10 rounded-lg px-2 py-1">
                  Inicio {new Date(stage.fecha_inicio).toLocaleString('es-CO', { dateStyle: 'short', timeStyle: 'short' })}
                </span>
              )}
              {stage.fecha_fin && (
                <span className="text-[11px] font-mono text-yeikar-neutral/55 bg-yeikar-tertiary/40 border border-yeikar-secondary-light/10 rounded-lg px-2 py-1">
                  Fin {new Date(stage.fecha_fin).toLocaleString('es-CO', { dateStyle: 'short', timeStyle: 'short' })}
                </span>
              )}
            </div>
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

        {/* Acciones: flujo de la etapa */}
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-[9px] font-headline font-black uppercase tracking-wider text-yeikar-neutral/40 mr-1">Etapa</span>
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
        </div>

        {/* Acciones: documentos */}
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-[9px] font-headline font-black uppercase tracking-wider text-yeikar-neutral/40 mr-1">Documentos</span>
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
          <div className="flex items-center gap-1 overflow-x-auto">
            {([
              ['registrar', 'Materiales', consumos.length],
              ['mano-obra', 'Mano de obra', manoObras.length],
              ['historial', 'Historial', etapasOrden.length],
              ['costos', 'Costos', null],
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
        <div className="flex-1 overflow-y-auto px-4 sm:px-6 py-4 space-y-4">
          {tab === 'registrar' && (
            <>
              {stage.estado === 'ASIGNADA' && (
                <div className="flex items-center gap-2 flex-wrap bg-amber-50 border border-amber-200 rounded-xl px-3 py-2 text-[11px] font-semibold text-amber-800">
                  <svg className="w-4 h-4 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                  </svg>
                  La etapa aún está ASIGNADA: iníciala para pedir material y registrar mano de obra.
                  <button
                    type="button"
                    onClick={() => onCambiarEstado(stage.id, 'EN_PROCESO')}
                    disabled={statusUpdating}
                    className="ml-auto bg-yeikar-primary text-yeikar-neutral text-[10px] font-bold px-2.5 py-1 rounded-lg hover:bg-yeikar-primary-dark disabled:opacity-50 transition-colors"
                  >
                    Iniciar trabajo
                  </button>
                </div>
              )}

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
                                  {reg.pendientes > 0 ? `Completo · pendiente de confirmar (${fmtNum(reg.pendientes)})` : 'Receta completa ✓'}
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

              {/* ── PASO 1: MATERIALES (form + registro en la misma tarjeta) ── */}
              <section className="bg-white border border-yeikar-secondary-light/10 rounded-2xl shadow-xs overflow-hidden">
                <header className="flex items-center gap-2.5 px-4 py-3 bg-yeikar-tertiary/40 border-b border-yeikar-secondary-light/10">
                  <div className="min-w-0">
                    <h3 className="text-sm font-bold font-headline text-yeikar-secondary leading-tight">Materiales — pedir y registrar</h3>
                    <p className="text-[10px] text-yeikar-neutral/50">Quién lo pide y cuánto sale: descuenta stock y genera el egreso</p>
                  </div>
                </header>
                <form onSubmit={handleAddConsumo} className="p-4 space-y-2.5">
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
                          {materialesCargando && (
                            <p className="flex items-center gap-2 text-center text-yeikar-neutral/40 text-xs py-4">
                              <Loader2 className="h-3.5 w-3.5 animate-spin" /> Buscando…
                            </p>
                          )}
                          {!materialesCargando &&
                            materialesBusqueda.map((m) => (
                              <button
                                key={m.id}
                                type="button"
                                onClick={() => {
                                  setNewConsumo(prev => ({
                                    ...prev,
                                    material_id: String(m.id),
                                    // El material define el modo de captura: reset.
      unidad_captura: '', modo_pieza: false, modo_cm: false,
                                    pieza_largo: '', pieza_ancho: '', pieza_espesor: '',
                                    ancho_corte_cm: '', largo_corte_cm: '', origen_sobrante_id: '',
                                    es_pedido: false,
                                  }));
                                  setMaterialSeleccionado(m);
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
                          {!materialesCargando && materialesBusqueda.length === 0 && (
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
                        {newConsumo.es_pedido && !esMaterialLaminar(materialConsumo)
                          ? 'Cantidad entregada (opcional)'
                          : esMaterialLaminar(materialConsumo) && newConsumo.es_lamina_completa
                          ? 'N.º de láminas'
                          : dimConsumo === 'VOLUMEN' && newConsumo.modo_cm
                            ? 'Cantidad (cm)'
                            : dimConsumo === 'VOLUMEN' && newConsumo.modo_pieza
                              ? 'N.º de piezas'
                              : dimConsumo === 'VOLUMEN'
                                ? 'Cantidad (m³)'
                                : 'Cantidad'}
                      </label>
                      <input
                        type="text"
                        inputMode="decimal"
                        placeholder={newConsumo.es_pedido && !esMaterialLaminar(materialConsumo) ? 'Vacío = pedido abierto' : '0'}
                        value={newConsumo.cantidad}
                        onChange={(e) => setNewConsumo(prev => ({ ...prev, cantidad: e.target.value }))}
                        required={!(newConsumo.es_pedido && !esMaterialLaminar(materialConsumo))}
                        className="w-full text-xs bg-white border border-yeikar-secondary-light/10 rounded-xl p-2.5 focus:outline-none focus:border-yeikar-primary font-mono"
                      />
                      {newConsumo.es_pedido && !esMaterialLaminar(materialConsumo) && !newConsumo.cantidad.trim() && (
                        <p className="text-[9px] font-mono text-amber-700 mt-1">
                          Piden sin cantidad: se descuenta al confirmar cuánto se usó.
                        </p>
                      )}
                    </div>
                    {/* Solicitante (prellenado con el responsable) */}
                    <div className="sm:col-span-3">
                      <label className="block text-[10px] font-headline font-bold uppercase tracking-wider text-yeikar-secondary/70 mb-1">Solicitante</label>
                      <SearchSelect
                        value={newConsumo.solicitante_id || null}
                        onChange={(v) => setNewConsumo(prev => ({ ...prev, solicitante_id: String(v) }))}
                        loadOptions={async (q) =>
                          (await getEmpleados({ buscar: q || undefined, limite: 20 }))
                            .map((e) => ({ value: e.id, label: e.nombre }))
                        }
                        minChars={0}
                        selectedOption={stage.empleado_responsable
                          ? { value: stage.empleado_responsable.id, label: stage.empleado_responsable.nombre }
                          : undefined}
                        placeholder="¿Quién pide?"
                      />
                    </div>
                    <div className="sm:col-span-12">
                      <button
                        type="submit"
                        disabled={consumoSubmitting}
                        className="w-full bg-yeikar-primary text-yeikar-neutral text-xs font-bold font-headline py-2.5 rounded-xl hover:bg-yeikar-primary-dark disabled:opacity-50 disabled:cursor-not-allowed transition-colors shadow-sm"
                      >
                        {consumoSubmitting ? 'Guardando…' : '+ Agregar material a la etapa'}
                      </button>
                    </div>
                  </div>

                  {/* Modo híbrido (no-laminares): uso directo o pedido para confirmar después */}
                  {materialConsumo && !esMaterialLaminar(materialConsumo) && (
                    <div className="space-y-1.5">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="text-[10px] font-semibold text-yeikar-neutral/50 uppercase">Modo:</span>
                        <button
                          type="button"
                          onClick={() => setNewConsumo(prev => ({ ...prev, es_pedido: false }))}
                          className={`text-[10px] font-bold px-2 py-1 rounded-lg border transition-colors ${
                            !newConsumo.es_pedido
                              ? 'bg-yeikar-primary text-yeikar-neutral border-yeikar-primary'
                              : 'bg-white text-yeikar-neutral/60 border-yeikar-secondary-light/15 hover:border-yeikar-primary/40'
                          }`}
                        >
                          Uso directo
                        </button>
                        <button
                          type="button"
                          onClick={() => setNewConsumo(prev => ({ ...prev, es_pedido: true }))}
                          className={`text-[10px] font-bold px-2 py-1 rounded-lg border transition-colors ${
                            newConsumo.es_pedido
                              ? 'bg-amber-500 text-white border-amber-500'
                              : 'bg-white text-yeikar-neutral/60 border-yeikar-secondary-light/15 hover:border-amber-400'
                          }`}
                        >
                          Pedir (confirmar uso después)
                        </button>
                      </div>
                      {newConsumo.es_pedido && (
                        <p className="text-[10px] font-mono text-amber-800 bg-amber-50 border border-amber-200 rounded-lg px-2 py-1">
                          Sale del depósito hoy con costo provisional (aparece en costos). Cuando digan cuánto
                          se usó se confirma: lo que sobre vuelve solo al depósito y el costo queda en lo usado.
                        </p>
                      )}
                    </div>
                  )}

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
                      {newConsumo.cantidad && parseDecimalEs(newConsumo.cantidad) > 0 && (
                        <span className="text-[10px] font-mono text-emerald-700 bg-emerald-50 border border-emerald-200 rounded-lg px-2 py-0.5">
                          Descontará: {fmtNum(convertirCapturaLineal(parseDecimalEs(newConsumo.cantidad), (newConsumo.unidad_captura || 'M') as UnidadCaptura))} m
                        </span>
                      )}
                    </div>
                  )}
                  {materialConsumo && dimConsumo === 'VOLUMEN' && (
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="text-[10px] font-semibold text-yeikar-neutral/50 uppercase">Como:</span>
                      {([['M3', 'm³'], ['PIEZA', 'Por pieza'], ['CM', 'cm']] as const).map(([valor, etiqueta]) => (
                        <button
                          key={valor}
                          type="button"
                          onClick={() => setNewConsumo(prev => ({
                            ...prev,
                            modo_pieza: valor === 'PIEZA',
                            modo_cm: valor === 'CM',
                          }))}
                          className={`text-[10px] font-bold px-2 py-1 rounded-lg border transition-colors ${
                            ((newConsumo.modo_cm ? 'CM' : newConsumo.modo_pieza ? 'PIEZA' : 'M3')) === valor
                              ? 'bg-yeikar-primary text-yeikar-neutral border-yeikar-primary'
                              : 'bg-white text-yeikar-neutral/60 border-yeikar-secondary-light/15 hover:border-yeikar-primary/40'
                          }`}
                        >
                          {etiqueta}
                        </button>
                      ))}
                    </div>
                  )}
                  {materialConsumo && dimConsumo === 'VOLUMEN' && newConsumo.modo_cm && (
                    <p className="text-[10px] font-mono text-yeikar-secondary bg-yeikar-primary/5 border border-yeikar-primary/20 rounded-lg px-2 py-1">
                      La cuenta del ebanista en cm (ej. 832): ÷ 10000 = m³.
                      {newConsumo.cantidad && parseDecimalEs(newConsumo.cantidad) > 0 && (
                        <>
                          {' '}Descontará:{' '}
                          <span className="font-bold">{fmtNum4(parseDecimalEs(newConsumo.cantidad) / 10000)} m³</span>
                        </>
                      )}
                    </p>
                  )}
                  {materialConsumo && dimConsumo === 'VOLUMEN' && newConsumo.modo_pieza && (
                    <div className="space-y-2">
                      <div className="grid grid-cols-3 gap-2">
                        {([['pieza_largo', 'Largo (m)'], ['pieza_ancho', 'Ancho (cm)'], ['pieza_espesor', 'Espesor (cm)']] as const).map(([campo, etiqueta]) => (
                          <input
                            key={campo}
                            type="text"
                            inputMode="decimal"
                            placeholder={etiqueta}
                            value={newConsumo[campo]}
                            onChange={(e) => setNewConsumo(prev => ({ ...prev, [campo]: e.target.value }))}
                            required
                            className="w-full text-xs bg-white border border-yeikar-secondary-light/10 rounded-xl p-2.5 focus:outline-none focus:border-yeikar-primary font-mono"
                          />
                        ))}
                      </div>
                      {newConsumo.pieza_largo && newConsumo.pieza_ancho && newConsumo.pieza_espesor && parseDecimalEs(newConsumo.cantidad || '0') > 0 && (
                        <p className="text-[10px] font-mono text-emerald-700 bg-emerald-50 border border-emerald-200 rounded-lg px-2 py-1">
                          Fórmula de la casa: ({newConsumo.pieza_largo}×{newConsumo.pieza_ancho}×{newConsumo.pieza_espesor}) × {newConsumo.cantidad} ÷ 10000 ={' '}
                          <span className="font-bold">
                            {fmtNum4(volumenPieza(
                              { largo: parseDecimalEs(newConsumo.pieza_largo), ancho: parseDecimalEs(newConsumo.pieza_ancho), espesor: parseDecimalEs(newConsumo.pieza_espesor) },
                              parseDecimalEs(newConsumo.cantidad) || 0,
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
                              type="text"
                              inputMode="decimal"
                              placeholder="Ancho cm (ej. 80)"
                              value={newConsumo.ancho_corte_cm}
                              onChange={(e) => setNewConsumo(prev => ({ ...prev, ancho_corte_cm: e.target.value }))}
                              className="w-full text-xs bg-white border border-yeikar-secondary-light/10 rounded-xl p-2.5 focus:outline-none focus:border-yeikar-primary font-mono"
                            />
                            <input
                              type="text"
                              inputMode="decimal"
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
                            const ac = parseDecimalEs(newConsumo.ancho_corte_cm);
                            const lc = parseDecimalEs(newConsumo.largo_corte_cm);
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
                            const cantidad = parseDecimalEs(newConsumo.cantidad || '0');
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

                {/* Registro del paso: qué ha salido ya del depósito */}
                <div className="flex items-center justify-between gap-2 px-4 py-2 bg-yeikar-tertiary/25 border-y border-yeikar-secondary-light/10">
                  <span className="text-[10px] font-headline font-black uppercase tracking-wider text-yeikar-neutral/50">Registrado en esta etapa</span>
                  <span className="text-[10px] font-mono font-bold text-yeikar-secondary">{consumos.length} · ${totalMateriales.toLocaleString('es-CO')}</span>
                </div>
                {consumos.length > 0 ? (
                  <div className="divide-y divide-yeikar-secondary-light/5 max-h-72 overflow-y-auto">
                    {consumos.map((c) => {
                      const costo = c.costo_unitario !== undefined && c.costo_unitario !== null ? c.costo_unitario : (c.material?.costo_base || 0);
                      const subtotal = c.cantidad * costo;
                      return (
                        <div key={c.id} className="flex items-center justify-between gap-3 px-4 py-2.5 text-xs hover:bg-yeikar-tertiary/20 transition-colors">
                          <div className="min-w-0">
                            <div className="flex items-center gap-1.5 flex-wrap">
                              <p className="font-bold text-yeikar-secondary text-sm">{c.material?.nombre}</p>
                              {c.estado === 'PENDIENTE' && (
                                <span className="text-[9px] font-bold px-1.5 py-0.5 rounded-md bg-amber-100 text-amber-700 border border-amber-300 uppercase">
                                  {c.material?.largo_cm && c.material?.ancho_cm
                                    ? `PENDIENTE · ${c.cantidad} lámina(s)`
                                    : c.cantidad_pedida == null
                                      ? 'PEDIDO ABIERTO · por confirmar'
                                      : `PEDIDO · ${c.cantidad} ${c.material?.unidad_medida?.abreviatura ?? ''} por confirmar`}
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
                              Cant:{' '}
                              {c.estado === 'PENDIENTE' && c.cantidad_pedida == null && !(c.material?.largo_cm && c.material?.ancho_cm) ? (
                                <span className="font-bold text-amber-700">por confirmar</span>
                              ) : (
                                <span className="font-bold text-yeikar-secondary">{c.cantidad}</span>
                              )}
                              {etiquetaCaptura(c) && <span className="text-yeikar-neutral/40"> · {etiquetaCaptura(c)}</span>}
                              {' '}| Unit: <span className="font-bold">${costo.toLocaleString('es-CO')}</span>
                              {c.estado === 'PENDIENTE' && <span className="text-amber-600/80"> · provisional</span>}
                              {c.estado === 'CONFIRMADO' && c.cantidad_pedida != null && Number(c.cantidad_pedida) !== Number(c.cantidad) && (
                                <span className="text-amber-600/80"> · pedidas {c.cantidad_pedida}</span>
                              )}
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
                                  setUsos([lineaUsoVacia()]);
                                  setConsumoAConfirmar(c);
                                }}
                                className="text-amber-700 hover:text-amber-900 font-bold text-xs p-1 transition-colors bg-amber-50 border border-amber-200 rounded-lg px-2"
                                title={c.material?.largo_cm && c.material?.ancho_cm
                                  ? 'Confirmar cuánto se usó de la lámina (por cortes)'
                                  : 'Confirmar cuánto se usó de verdad'}
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
                ) : (
                  <p className="px-4 py-6 text-center text-[11px] text-yeikar-neutral/40 italic">
                    Aún no hay materiales registrados: lo que pidas en el formulario de arriba aparecerá aquí.
                  </p>
                )}
              </section>
            </>
          )}

          {tab === 'mano-obra' && (
            <>
              {/* ── MANO DE OBRA (form + registro en la misma tarjeta) ── */}
              <section className="bg-white border border-yeikar-secondary-light/10 rounded-2xl shadow-xs overflow-hidden">
                <header className="flex items-center gap-2.5 px-4 py-3 bg-yeikar-tertiary/40 border-b border-yeikar-secondary-light/10">
                  <div className="min-w-0">
                    <h3 className="text-sm font-bold font-headline text-yeikar-secondary leading-tight">Mano de obra — quién y cuánto</h3>
                    <p className="text-[10px] text-yeikar-neutral/50">Alimenta el costo de la etapa y la nómina del trabajador</p>
                  </div>
                </header>
                <div className="p-4 space-y-2.5">
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
                <form onSubmit={handleAddManoObra} className="space-y-2.5">
                  <div className="grid grid-cols-1 sm:grid-cols-12 gap-2">
                    <div className="sm:col-span-4">
                      <label className="block text-[10px] font-headline font-bold uppercase tracking-wider text-yeikar-secondary/70 mb-1">Empleado</label>
                      <SearchSelect
                        value={newManoObra.empleado_id}
                        onChange={(v) => setNewManoObra(prev => ({ ...prev, empleado_id: String(v) }))}
                        loadOptions={async (q) =>
                          (await getEmpleados({ buscar: q || undefined, limite: 20 }))
                            .map((e) => ({ value: e.id, label: e.nombre }))
                        }
                        minChars={0}
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

                  <button
                    type="button"
                    onClick={() => setMostrarNuevoCosto(v => !v)}
                    className="text-[11px] font-bold text-yeikar-primary-dark hover:underline"
                  >
                    {mostrarNuevoCosto ? '× Cancelar nuevo costo' : '+ Nuevo costo de producción'}
                  </button>
                  <button
                    type="submit"
                    disabled={stage.estado !== 'EN_PROCESO'}
                    className="w-full bg-yeikar-primary text-yeikar-neutral text-xs font-bold font-headline py-2.5 rounded-xl hover:bg-yeikar-primary-dark disabled:opacity-50 disabled:cursor-not-allowed transition-colors shadow-sm"
                  >
                    + Agregar mano de obra a la etapa
                  </button>
                </form>
                </div>

                {/* Registro del paso: quién trabajó y cuánto */}
                <div className="flex items-center justify-between gap-2 px-4 py-2 bg-yeikar-tertiary/25 border-y border-yeikar-secondary-light/10">
                  <span className="text-[10px] font-headline font-black uppercase tracking-wider text-yeikar-neutral/50">Registrado en esta etapa</span>
                  <span className="text-[10px] font-mono font-bold text-yeikar-secondary">{manoObras.length} · ${totalManoObra.toLocaleString('es-CO')}</span>
                </div>
                {manoObras.length > 0 ? (
                  <div className="divide-y divide-yeikar-secondary-light/5 max-h-64 overflow-y-auto">
                    {manoObras.map((mo) => (
                      <div key={mo.id} className="flex items-center justify-between gap-3 px-4 py-2.5 text-xs hover:bg-yeikar-tertiary/20 transition-colors">
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
                ) : (
                  <p className="px-4 py-6 text-center text-[11px] text-yeikar-neutral/40 italic">
                    Sin mano de obra registrada en esta etapa todavía.
                  </p>
                )}
              </section>
            </>
          )}

          {tab === 'historial' && (
            <div className="bg-white border border-yeikar-secondary-light/10 rounded-2xl shadow-xs p-4 sm:p-5">
              <h3 className="text-sm font-bold font-headline text-yeikar-secondary mb-4">Ruta de la orden por áreas</h3>
              {etapasOrden.length === 0 ? (
                <p className="text-xs text-yeikar-neutral/40 text-center py-8">Sin historial de etapas para esta orden.</p>
              ) : (
                <ol className="relative space-y-4 before:absolute before:left-[7px] before:top-2 before:bottom-2 before:w-px before:bg-yeikar-secondary-light/25">
                  {etapasOrden.map((et, idx) => (
                    <li key={et.id} className="relative pl-6">
                      <span className={`absolute left-0 top-1.5 w-[15px] h-[15px] rounded-full border-2 ${
                        et.id === stage.id
                          ? 'bg-yeikar-primary border-yeikar-primary'
                          : et.estado === 'COMPLETADA' ? 'bg-green-500 border-green-500'
                          : et.estado === 'EN_PROCESO' ? 'bg-amber-400 border-amber-400'
                          : et.estado === 'PAUSADA' ? 'bg-red-400 border-red-400'
                          : 'bg-white border-blue-400'
                      }`} />
                      <div className={`rounded-xl border px-3 py-2 text-xs ${
                        et.id === stage.id
                          ? 'bg-yeikar-primary/10 border-yeikar-primary/30'
                          : 'bg-yeikar-tertiary/30 border-yeikar-secondary-light/10'
                      }`}>
                        <div className="flex items-center justify-between gap-2 flex-wrap">
                          <span className="font-bold text-yeikar-secondary">
                            {idx + 1}. {et.area?.nombre || `Área #${et.area_id}`}
                          </span>
                          <span className={`text-[10px] font-mono font-bold px-2 py-0.5 rounded-lg border ${ESTADO_COLORS[et.estado] || 'bg-stone-100 text-stone-600 border-stone-200'}`}>
                            {et.estado.replace('_', ' ')}
                          </span>
                        </div>
                        <div className="flex items-center gap-3 flex-wrap mt-1 text-[10px] font-mono text-yeikar-neutral/50">
                          {et.empleado_responsable && <span>Encargado: {et.empleado_responsable.nombre}</span>}
                          {et.fecha_inicio && <span>Inicio {fmtFechaVE(et.fecha_inicio)}</span>}
                          {et.fecha_fin && <span>Fin {fmtFechaVE(et.fecha_fin)}</span>}
                          {et.es_retrabajo && <span className="font-bold text-amber-700">RETRABAJO</span>}
                          {et.id === stage.id && <span className="font-bold text-yeikar-primary-dark">Estás aquí</span>}
                        </div>
                      </div>
                    </li>
                  ))}
                </ol>
              )}
            </div>
          )}

          {tab === 'costos' && (
            <div className="bg-white border border-yeikar-secondary-light/10 rounded-2xl shadow-xs overflow-hidden">
              <header className="flex items-center justify-between gap-2 px-4 py-3 bg-yeikar-tertiary/40 border-b border-yeikar-secondary-light/10">
                <div>
                  <h3 className="text-sm font-bold font-headline text-yeikar-secondary leading-tight">Estructura de costos de la orden</h3>
                  <p className="text-[10px] text-yeikar-neutral/50">Desglose por sección, como la hoja de Excel</p>
                </div>
                <span className="text-[10px] font-mono font-bold text-yeikar-neutral/50 shrink-0">Orden #{stage.orden_produccion_id}</span>
              </header>
              <div className="p-4">
                <CostosOrdenEnVivo data={costosEnVivo} loading={costosEnVivoLoading} compacto />
              </div>
            </div>
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
            <span className="text-[10px] font-mono text-yeikar-neutral/40 hidden sm:block">
              {consumos.length} materiales · {manoObras.length} mano de obra
            </span>
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
        // Pedido general (madera y demás): modal simple de cantidad usada.
        const esLaminar = !!(mat?.largo_cm && mat?.ancho_cm);
        if (!esLaminar) {
          // Pedido abierto: cantidad_pedida NULL → nada salió del depósito al
          // pedir; lo que se use aquí es lo que se descuenta ahora.
          const esAbierto = consumoAConfirmar.cantidad_pedida == null;
          const pedidas = consumoAConfirmar.cantidad_pedida ?? 0;
          const unidad = mat?.unidad_medida?.abreviatura ?? '';
          // Modos de captura disponibles según la dimensionalidad del material.
          const opcionesModo: [ModoUso, string][] = dimConfirmar === 'VOLUMEN'
            ? [['BASE', 'm³'], ['PIEZA', 'Por pieza'], ['CM', 'cm']]
            : dimConfirmar === 'LONGITUD'
              ? [['BASE', 'mts'], ['CM', 'cm']]
              : [];
          const etiquetaCantidad = (u: UsoLinea) =>
            u.modo === 'PIEZA'
              ? 'N.º de piezas'
              : u.modo === 'CM'
                ? 'Cantidad (cm)'
                : `Cantidad (${unidad || 'unidad base'})`;
          // Total de la confirmación (vista previa; el backend convierte igual).
          const totalBase = usos.reduce((acc, u) => acc + (convertirUso(u, dimConfirmar) ?? 0), 0);
          const dif = totalBase > 0 ? Number(pedidas) - totalBase : null;
          const toggleBtn = (activo: boolean) =>
            `text-[10px] font-bold px-2 py-1 rounded-lg border transition-colors ${
              activo
                ? 'bg-yeikar-primary text-yeikar-neutral border-yeikar-primary'
                : 'bg-white text-yeikar-neutral/60 border-yeikar-secondary-light/15 hover:border-yeikar-primary/40'
            }`;
          const setUso = (i: number, campo: keyof UsoLinea, valor: string) =>
            setUsos(prev => prev.map((u, j) => (j === i ? { ...u, [campo]: valor } : u)));
          return (
            <div
              className="fixed inset-0 bg-yeikar-secondary/60 backdrop-blur-sm flex items-center justify-center p-4 z-[60]"
              onClick={(e) => {
                // Este modal vive DENTRO del backdrop del modal de etapa (que
                // cierra todo con onClick): sin stopPropagation, cualquier
                // clic aquí burbujea y saca al usuario de la etapa. Clic en el
                // fondo oscuro = cancelar solo este diálogo.
                e.stopPropagation();
                setConsumoAConfirmar(null);
              }}
            >
              <div
                className="bg-white rounded-3xl shadow-xl border border-yeikar-secondary-light/10 max-w-lg w-full p-4 sm:p-6 space-y-4 max-h-[92vh] overflow-y-auto"
                onClick={(e) => e.stopPropagation()}
              >
                <h3 className="text-xl font-headline font-black text-yeikar-secondary">¿Cuánto se usó?</h3>
                <p className="text-xs text-yeikar-neutral/60">
                  {esAbierto ? (
                    <>
                      Pedido <b>abierto</b> de{' '}
                      <span className="font-bold text-yeikar-secondary">{mat?.nombre}</span>
                      {consumoAConfirmar.solicitante_nombre && (
                        <> a <span className="font-bold text-yeikar-secondary">{consumoAConfirmar.solicitante_nombre}</span></>
                      )}
                      {' '}(no se especificó cuánto llevan). Agrega cada cosa que se hizo con la
                      madera — cada uso queda como su propio renglón de costo:
                    </>
                  ) : (
                    <>
                      Se entregaron <b>{pedidas} {unidad}</b> de{' '}
                      <span className="font-bold text-yeikar-secondary">{mat?.nombre}</span>
                      {consumoAConfirmar.solicitante_nombre && (
                        <> a <span className="font-bold text-yeikar-secondary">{consumoAConfirmar.solicitante_nombre}</span></>
                      )}. Agrega cada uso (cada uno queda como su renglón de costo):
                    </>
                  )}
                </p>
                <form
                  onSubmit={(e) => { e.preventDefault(); ejecutarConfirmarConsumo(); }}
                  className="space-y-3"
                >
                  {usos.map((u, i) => {
                    const baseLinea = convertirUso(u, dimConfirmar);
                    return (
                      <div key={i} className="rounded-2xl border border-yeikar-secondary-light/15 bg-yeikar-tertiary/20 p-2.5 space-y-2">
                        <div className="flex items-center gap-1.5 flex-wrap">
                          <span className="text-[9px] font-black text-yeikar-neutral/40 uppercase tracking-wider">
                            Uso {i + 1}
                          </span>
                          {opcionesModo.map(([valor, etiqueta]) => (
                            <button
                              key={valor}
                              type="button"
                              onClick={() => setUso(i, 'modo', valor)}
                              className={toggleBtn(u.modo === valor)}
                            >
                              {etiqueta}
                            </button>
                          ))}
                          {usos.length > 1 && (
                            <button
                              type="button"
                              onClick={() => setUsos(prev => prev.filter((_, j) => j !== i))}
                              className="ml-auto text-[10px] font-bold text-red-500 hover:text-red-700 px-1.5 py-0.5 rounded-lg hover:bg-red-50 transition-colors"
                            >
                              Quitar
                            </button>
                          )}
                        </div>
                        <div>
                          <label className="block text-[10px] font-semibold text-yeikar-neutral/50 uppercase mb-1">
                            {etiquetaCantidad(u)}
                          </label>
                          <input
                            type="text"
                            inputMode="decimal"
                            placeholder={u.modo === 'PIEZA' ? 'Ej. 4' : u.modo === 'CM' ? 'Ej. 832' : 'Ej. 2,5'}
                            value={u.cantidad}
                            onChange={(e) => setUso(i, 'cantidad', e.target.value)}
                            required
                            autoFocus={i === 0}
                            className="w-full text-xs bg-white border border-yeikar-secondary-light/10 rounded-xl p-2.5 focus:outline-none focus:border-yeikar-primary font-mono"
                          />
                        </div>
                        {u.modo === 'PIEZA' && (
                          <div className="grid grid-cols-3 gap-2">
                            {([['pieza_largo', 'Largo (m)'], ['pieza_ancho', 'Ancho (cm)'], ['pieza_espesor', 'Espesor (cm)']] as const).map(([campo, etiqueta]) => (
                              <input
                                key={campo}
                                type="text"
                                inputMode="decimal"
                                placeholder={etiqueta}
                                value={u[campo]}
                                onChange={(e) => setUso(i, campo, e.target.value)}
                                required
                                className="w-full text-xs bg-white border border-yeikar-secondary-light/10 rounded-xl p-2.5 focus:outline-none focus:border-yeikar-primary font-mono"
                              />
                            ))}
                          </div>
                        )}
                        {u.modo === 'PIEZA' && baseLinea !== null && (
                          <p className="text-[10px] font-mono text-emerald-700 bg-emerald-50 border border-emerald-200 rounded-lg px-2 py-1">
                            Fórmula de la casa: ({u.pieza_largo}×{u.pieza_ancho}×{u.pieza_espesor}) × {u.cantidad} ÷ 10000 ={' '}
                            <span className="font-bold">{fmtNum4(baseLinea)} {unidad}</span>
                          </p>
                        )}
                        {u.modo === 'CM' && baseLinea !== null && (
                          <p className="text-[10px] font-mono text-emerald-700 bg-emerald-50 border border-emerald-200 rounded-lg px-2 py-1">
                            {dimConfirmar === 'VOLUMEN' ? (
                              <>Cuenta del taller: {u.cantidad} ÷ 10000 = <span className="font-bold">{fmtNum4(baseLinea)} {unidad}</span></>
                            ) : (
                              <>Digitado en cm: <span className="font-bold">{fmtNum4(baseLinea)} {unidad}</span></>
                            )}
                          </p>
                        )}
                      </div>
                    );
                  })}
                  <button
                    type="button"
                    onClick={() => setUsos(prev => [...prev, lineaUsoVacia()])}
                    className="w-full border border-dashed border-yeikar-primary/40 text-yeikar-primary text-[11px] font-bold font-headline py-2 rounded-xl hover:bg-yeikar-primary/5 transition-colors"
                  >
                    + Agregar otro uso (otra pieza, otra medida en cm…)
                  </button>
                  {totalBase > 0 && (
                    <p className="text-[11px] font-mono bg-yeikar-primary/5 border border-yeikar-primary/20 rounded-lg px-2 py-1.5 text-yeikar-secondary">
                      Total a descontar: <span className="font-bold">{fmtNum4(totalBase)} {unidad}</span>
                      {!esAbierto && dif !== null && (
                        <>
                          {' '}· pediste {fmtNum(Number(pedidas))}:{' '}
                          {dif > 0 ? (
                            <span className="font-bold text-emerald-700">sobran {fmtNum(dif)} y vuelven solos al depósito</span>
                          ) : dif < 0 ? (
                            <span className="font-bold text-red-600">faltan {fmtNum(-dif)} — se descontarán del inventario</span>
                          ) : (
                            <span className="font-bold text-emerald-700">justo lo que pediste ✓</span>
                          )}
                        </>
                      )}
                    </p>
                  )}
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
                      {confirmarSubmitting ? 'Confirmando…' : usos.length > 1 ? `Confirmar ${usos.length} usos` : 'Confirmar uso'}
                    </button>
                  </div>
                </form>
              </div>
            </div>
          );
        }
        const L = parseFloat(String(mat?.largo_cm ?? 0));
        const A = parseFloat(String(mat?.ancho_cm ?? 0));
        const pedidas = consumoAConfirmar.cantidad;
        const costoBase = parseFloat(String(mat?.costo_base ?? 0));
        const lc = parseDecimalEs(confirmarForm.largo_corte_cm);
        const ac = parseDecimalEs(confirmarForm.ancho_corte_cm);
        const cortes = parseDecimalEs(confirmarForm.cantidad_cortes);
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
          <div
            className="fixed inset-0 bg-yeikar-secondary/60 backdrop-blur-sm flex items-center justify-center p-4 z-[60]"
            onClick={(e) => {
              // Igual que el modal general: sin stopPropagation, cualquier
              // clic burbujea al backdrop del modal de etapa y lo cierra todo.
              e.stopPropagation();
              setConsumoAConfirmar(null);
            }}
          >
            <div
              className="bg-white rounded-3xl shadow-xl border border-yeikar-secondary-light/10 max-w-md w-full p-4 sm:p-6 space-y-4"
              onClick={(e) => e.stopPropagation()}
            >
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
                      type="text"
                      inputMode="decimal"
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
                      type="text"
                      inputMode="decimal"
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
                      type="text"
                      inputMode="decimal"
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
                      type="text"
                      inputMode="decimal"
                      placeholder="Sobrante largo cm"
                      value={confirmarForm.sobrante_largo_cm}
                      onChange={(e) => setConfirmarForm(prev => ({ ...prev, sobrante_largo_cm: e.target.value }))}
                      className="w-full text-xs bg-white border border-yeikar-secondary-light/10 rounded-lg p-2 focus:outline-none focus:border-yeikar-primary font-mono"
                    />
                    <input
                      type="text"
                      inputMode="decimal"
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
