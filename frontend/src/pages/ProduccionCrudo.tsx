import { useEffect, useState, useCallback, useMemo } from 'react';
import {
  crudoService,
  type Crudo,
  type ProduccionCrudo,
  type CrudoConsumoCreate,
  type ProduccionCrudoManoObraCreate,
} from '../services/produccionService';
import { getEmpleados, type Empleado } from '../services/empleadosService';
import api from '../services/api';
import { useToast } from '../context/ToastContext';
import SearchSelect, { type SearchSelectOption } from '../components/ui/SearchSelect';
import { dimensionalidad, volumenPieza, convertirCapturaLineal, etiquetaCaptura, fmtNum, fmtNum4, UnidadCaptura } from '../utils/unidades';
import { fmtFechaVE } from '../utils/fechas';
import { getPreciosProduccion, crearPrecioProduccion, getAreas, type PrecioProduccion, type Area } from '../services/costosProduccionService';

interface Material {
  id: number;
  nombre: string;
  costo_base: number;
  unidad_medida?: { abreviatura: string } | null;
}

interface InventarioItem {
  material_id: number;
  cantidad: number;
}

const ESTADO_CFG: Record<string, { label: string; bg: string; dot: string }> = {
  PENDIENTE: { label: 'PENDIENTE', bg: 'bg-amber-100', dot: 'bg-amber-400' },
  EN_PRODUCCION: { label: 'EN PRODUCCIÓN', bg: 'bg-blue-100', dot: 'bg-blue-500' },
  COMPLETADA: { label: 'COMPLETADA', bg: 'bg-emerald-100', dot: 'bg-emerald-500' },
  CANCELADA: { label: 'CANCELADA', bg: 'bg-red-100', dot: 'bg-red-500' },
};

export default function ProduccionCrudo() {
  const toast = useToast();

  const [crudo, setCrudo] = useState<Crudo[]>([]);
  const [producciones, setProducciones] = useState<ProduccionCrudo[]>([]);
  const [materiales, setMateriales] = useState<Material[]>([]);
  const [empleados, setEmpleados] = useState<Empleado[]>([]);
  const [stockMap, setStockMap] = useState<Record<number, number>>({});
  const [loadingProd, setLoadingProd] = useState(false);

  const [showProdModal, setShowProdModal] = useState(false);
  const [newProduccion, setNewProduccion] = useState({ crudo_id: '' as string | number, cantidad: '1', observaciones: '' });
  const [savingProd, setSavingProd] = useState(false);

  const [consumoForm, setConsumoForm] = useState({
    material_id: '' as string | number, cantidad: '1', solicitante_empleado_id: '' as string | number, seccion: 'EBANISTERIA', observaciones: '',
    // --- Captura flexible de madera (cm/mts, pieza volumétrica m³) ---
    unidad_captura: '' as '' | UnidadCaptura,
    modo_pieza: false,
    pieza_largo: '',
    pieza_ancho: '',
    pieza_espesor: '',
    // --- Componente y consumo extra ---
    componente: '',
    es_excedente: false,
    motivo_exceso: '',
  });
  // Unidad del material del form de consumo → modo de captura disponible.
  const materialConsumoCrudo = materiales.find((m) => String(m.id) === String(consumoForm.material_id));
  const dimConsumoCrudo = dimensionalidad(materialConsumoCrudo?.unidad_medida?.abreviatura);
  const [savingConsumo, setSavingConsumo] = useState(false);

  const [moForm, setMoForm] = useState({
    empleado_id: '' as string | number, costo_id: '', monto: '', cantidad: '', observaciones: '',
  });
  const [savingMo, setSavingMo] = useState(false);

  // Tarifas / costos de producción
  const [opcionesCosto, setOpcionesCosto] = useState<{ id: number; descripcion: string; precio: number; area_id: number }[]>([]);
  const [areas, setAreas] = useState<Area[]>([]);
  const [mostrarNuevoCosto, setMostrarNuevoCosto] = useState(false);
  const [nuevoCosto, setNuevoCosto] = useState({ descripcion: '', precio: '', area_id: '' });
  const [creandoCosto, setCreandoCosto] = useState(false);

  const fetchCrudo = useCallback(async () => {
    try {
      const data = await crudoService.getCrudo();
      setCrudo(data);
    } catch (error) {
      console.error('Error fetching crudo inventory:', error);
    }
  }, []);

  const fetchProducciones = useCallback(async () => {
    setLoadingProd(true);
    try {
      const data = await crudoService.getProducciones();
      setProducciones(data);
    } catch (error) {
      console.error('Error fetching producciones de crudo:', error);
    } finally {
      setLoadingProd(false);
    }
  }, []);

  const fetchBase = useCallback(async () => {
    try {
      const [_, matData, emps, costos, areasData, invData] = await Promise.all([
        crudoService.getCrudo(),
        api.get<Material[]>('/material/?limite=1000'),
        getEmpleados({ limite: 1000 }),
        getPreciosProduccion({ activo: true }),
        getAreas(),
        api.get<InventarioItem[]>('/inventario/'),
      ]);
      setMateriales(matData.data);
      setEmpleados(emps);
      setOpcionesCosto(costos);
      setAreas(areasData);
      // Build stock map: material_id → total stock across all locations
      const sm: Record<number, number> = {};
      for (const inv of invData.data) {
        sm[inv.material_id] = (sm[inv.material_id] || 0) + Number(inv.cantidad);
      }
      setStockMap(sm);
    } catch (error) {
      console.error('Error fetching base data:', error);
    }
  }, []);

  useEffect(() => {
    fetchCrudo();
    fetchProducciones();
    fetchBase();
  }, [fetchCrudo, fetchProducciones, fetchBase]);

  // Options para SearchSelect
  const crudoOptions: SearchSelectOption[] = useMemo(
    () => crudo.map((c) => ({ value: c.id, label: `${c.nombre} (stock ${c.cantidad.toLocaleString('es-ES')})` })),
    [crudo],
  );

  const materialOptions: SearchSelectOption[] = useMemo(
    () => materiales.map((m) => ({ value: m.id, label: `${m.nombre} — $${m.costo_base.toLocaleString('es-ES')}` })),
    [materiales],
  );

  const empleadoOptions: SearchSelectOption[] = useMemo(
    () => empleados.map((e) => ({ value: e.id, label: e.nombre })),
    [empleados],
  );

  const costoOptions: SearchSelectOption[] = useMemo(
    () => [
      { value: '', label: '— Sin tarifa (monto manual) —' },
      ...opcionesCosto.map((o) => ({
        value: String(o.id),
        label: `${o.descripcion} · $${o.precio.toLocaleString('es-CO')}`,
      })),
    ],
    [opcionesCosto],
  );

  const seleccionarCostoMo = (costoId: string) => {
    setMoForm((prev) => {
      const opcion = opcionesCosto.find((o) => String(o.id) === String(costoId));
      return { ...prev, costo_id: costoId, monto: opcion ? String(opcion.precio) : prev.monto };
    });
  };

  const crearCostoAlVuelo = async () => {
    const areaFinal = Number(nuevoCosto.area_id) || 1;
    if (!nuevoCosto.descripcion.trim() || !nuevoCosto.precio || !areaFinal) {
      toast.error('Descripción, precio y área son obligatorios para el nuevo costo.');
      return;
    }
    setCreandoCosto(true);
    try {
      const resp = await crearPrecioProduccion({
        area_id: areaFinal,
        descripcion: nuevoCosto.descripcion.trim(),
        precio: parseFloat(nuevoCosto.precio),
      });
      setOpcionesCosto((prev) => [...prev, resp].sort((a, b) => a.descripcion.localeCompare(b.descripcion)));
      setMoForm((prev) => ({ ...prev, costo_id: String(resp.id), monto: String(resp.precio) }));
      setNuevoCosto({ descripcion: '', precio: '', area_id: '' });
      setMostrarNuevoCosto(false);
      toast.success(`Costo "${resp.descripcion}" creado. Monto auto-rellenado.`);
    } catch (error: any) {
      toast.error(error.response?.data?.detail || 'Error al crear el costo de producción.');
    } finally {
      setCreandoCosto(false);
    }
  };

  const abrirNuevaProduccion = (crudoId?: number) => {
    setNewProduccion({
      crudo_id: crudoId ?? '',
      cantidad: '1',
      observaciones: '',
    });
    setConsumoForm({
      material_id: '', cantidad: '1', solicitante_empleado_id: '', seccion: 'EBANISTERIA', observaciones: '',
      unidad_captura: '', modo_pieza: false, pieza_largo: '', pieza_ancho: '', pieza_espesor: '',
      componente: '', es_excedente: false, motivo_exceso: '',
    });
    setMoForm({ empleado_id: '', costo_id: '', monto: '', cantidad: '', observaciones: '' });
    setShowProdModal(true);
  };

  const handleCrearProduccion = async (e: React.FormEvent) => {
    e.preventDefault();
    const crudoId = Number(newProduccion.crudo_id);
    if (!crudoId) return;
    setSavingProd(true);
    try {
      const prod = await crudoService.crearProduccion({
        crudo_id: crudoId,
        cantidad: parseFloat(newProduccion.cantidad) || 1,
        observaciones: newProduccion.observaciones || undefined,
      });
      setProducciones((prev) => [prod, ...prev]);
      fetchProducciones();
      toast.success(`Producción #${prod.id} creada.`);
      setShowProdModal(false);
    } catch (error: any) {
      toast.error(error.response?.data?.detail || 'Error al crear la producción.');
    } finally {
      setSavingProd(false);
    }
  };

  const handleRegistrarConsumo = async (produccionId: number, e: React.FormEvent) => {
    e.preventDefault();
    const materialId = Number(consumoForm.material_id);
    const solicitanteId = Number(consumoForm.solicitante_empleado_id);
    const cantidad = parseFloat(consumoForm.cantidad);
    if (!materialId || !solicitanteId || !cantidad || cantidad <= 0) {
      toast.error('Completa material, cantidad y quién solicita.');
      return;
    }
    const esPieza = dimConsumoCrudo === 'VOLUMEN' && consumoForm.modo_pieza;
    if (esPieza && (!consumoForm.pieza_largo || !consumoForm.pieza_ancho || !consumoForm.pieza_espesor)) {
      toast.error('Completa las medidas de la pieza (largo × ancho × espesor).');
      return;
    }
    setSavingConsumo(true);
    try {
      // Vista previa de lo que el backend descontará (unidad base del material).
      const cantidadConvertida = esPieza
        ? volumenPieza(
            { largo: parseFloat(consumoForm.pieza_largo), ancho: parseFloat(consumoForm.pieza_ancho), espesor: parseFloat(consumoForm.pieza_espesor) },
            cantidad,
          )
        : consumoForm.unidad_captura === 'CM'
          ? convertirCapturaLineal(cantidad, 'CM')
          : cantidad;
      const payload: CrudoConsumoCreate = {
        material_id: materialId,
        cantidad,
        solicitante_empleado_id: solicitanteId,
        seccion: consumoForm.seccion || undefined,
        observaciones: consumoForm.observaciones || undefined,
        // Captura flexible: el backend convierte antes de descontar.
        ...(esPieza
          ? {
              pieza_largo: parseFloat(consumoForm.pieza_largo),
              pieza_ancho: parseFloat(consumoForm.pieza_ancho),
              pieza_espesor: parseFloat(consumoForm.pieza_espesor),
            }
          : consumoForm.unidad_captura
            ? { unidad_captura: consumoForm.unidad_captura }
            : {}),
        // Componente y consumo extra.
        ...(consumoForm.componente.trim() ? { componente: consumoForm.componente.trim() } : {}),
        ...(consumoForm.es_excedente
          ? { es_excedente: true, motivo_exceso: consumoForm.motivo_exceso || 'OTRO' }
          : {}),
      };
      await crudoService.registrarConsumo(produccionId, payload);
      setConsumoForm({
        material_id: '', cantidad: '1', solicitante_empleado_id: '', seccion: 'EBANISTERIA', observaciones: '',
        unidad_captura: '', modo_pieza: false, pieza_largo: '', pieza_ancho: '', pieza_espesor: '',
        componente: '', es_excedente: false, motivo_exceso: '',
      });
      fetchProducciones();
      // Refrescar stock en tiempo real
      try {
        const invData = await api.get<InventarioItem[]>('/inventario/');
        const sm: Record<number, number> = {};
        for (const inv of invData.data) {
          sm[inv.material_id] = (sm[inv.material_id] || 0) + Number(inv.cantidad);
        }
        setStockMap(sm);
      } catch { /* noop */ }
      toast.success(`Consumo registrado. Descontado: ${fmtNum(cantidadConvertida)} ${materialConsumoCrudo?.unidad_medida?.abreviatura || ''}.`);
    } catch (error: any) {
      toast.error(error.response?.data?.detail || 'Error al registrar el consumo.');
    } finally {
      setSavingConsumo(false);
    }
  };

  const handleRegistrarManoObra = async (produccionId: number, e: React.FormEvent, prodCantidadDefault: number = 1) => {
    e.preventDefault();
    const empleadoId = Number(moForm.empleado_id);
    const monto = parseFloat(moForm.monto);
    const cant = parseFloat(moForm.cantidad !== '' ? moForm.cantidad : String(prodCantidadDefault)) || 1;
    if (!empleadoId || isNaN(monto) || monto < 0) {
      toast.error('Completa empleado y monto.');
      return;
    }
    if (cant <= 0) {
      toast.error('La cantidad de unidades debe ser mayor a 0.');
      return;
    }
    setSavingMo(true);
    try {
      const payload: ProduccionCrudoManoObraCreate = {
        empleado_id: empleadoId,
        monto,
        cantidad: cant,
        observaciones: moForm.observaciones || undefined,
      };
      await crudoService.crearManoObra(produccionId, payload);
      setMoForm({ empleado_id: '', costo_id: '', monto: '', cantidad: '', observaciones: '' });
      fetchProducciones();
      toast.success('Mano de obra registrada.');
    } catch (error: any) {
      toast.error(error.response?.data?.detail || 'Error al registrar la mano de obra.');
    } finally {
      setSavingMo(false);
    }
  };

  const handleEliminarManoObra = async (moId: number) => {
    if (!confirm('¿Eliminar este registro de mano de obra?')) return;
    try {
      await crudoService.eliminarManoObra(moId);
      fetchProducciones();
      toast.success('Mano de obra eliminada.');
    } catch (error: any) {
      toast.error(error.response?.data?.detail || 'No se pudo eliminar la mano de obra.');
    }
  };

  const handleIniciarProduccion = async (prod: ProduccionCrudo) => {
    if (prod.estado !== 'PENDIENTE') return;
    try {
      await crudoService.cambiarEstado(prod.id, 'EN_PRODUCCION');
      fetchProducciones();
    } catch (error: any) {
      toast.error(error.response?.data?.detail || 'No se pudo iniciar la producción.');
    }
  };

  const handleFinalizarProduccion = async (prod: ProduccionCrudo) => {
    if (prod.estado !== 'PENDIENTE' && prod.estado !== 'EN_PRODUCCION') return;
    if (!confirm('¿Finalizar esta producción? Se sumará stock y se materializarán los egresos de mano de obra.')) return;
    try {
      await crudoService.cambiarEstado(prod.id, 'COMPLETADA');
      toast.success('Producción finalizada. Stock sumado al ítem en crudo.');
      fetchProducciones();
      fetchCrudo();
    } catch (error: any) {
      toast.error(error.response?.data?.detail || 'No se pudo finalizar la producción.');
    }
  };

  const totalMateriales = (prod: ProduccionCrudo) =>
    (prod.consumos || []).reduce((acc, c) => acc + (c.costo_unitario || 0) * c.cantidad, 0);

  const totalMo = (prod: ProduccionCrudo) =>
    prod.costo_mano_obra || 0;

  const nombreEmpleado = (id?: number | null) =>
    empleados.find((e) => e.id === id)?.nombre || '—';

  const fmtMoney = (n: number | null | undefined) =>
    (Number(n) || 0).toLocaleString('es-ES', { minimumFractionDigits: 0, maximumFractionDigits: 2 });

  const inputCls = "w-full bg-yeikar-tertiary/20 border border-yeikar-secondary-light/10 rounded-xl px-3 py-2 text-sm text-yeikar-neutral focus:outline-none focus:border-yeikar-primary font-mono";
  const inputClsWhite = "w-full text-xs bg-white border border-yeikar-secondary-light/10 rounded-xl p-2.5 focus:outline-none focus:border-yeikar-primary font-mono";

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-black font-headline text-yeikar-neutral tracking-tight">
            Producción de Productos en Crudo
          </h1>
          <p className="text-yeikar-neutral/60 mt-1 text-sm">
            Fabrica ítems en crudo: registra consumos, mano de obra y al finalizar suma stock al ítem.
          </p>
        </div>
        <button
          onClick={() => abrirNuevaProduccion()}
          className="flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-bold font-headline bg-yeikar-primary text-yeikar-neutral shadow-sm hover:bg-yeikar-primary-dark transition-all"
        >
          + Nueva Producción
        </button>
      </div>

      {/* Lista de producciones */}
      {loadingProd ? (
        <div className="flex items-center justify-center py-16">
          <div className="w-8 h-8 border-4 border-yeikar-primary border-t-transparent rounded-full animate-spin"></div>
        </div>
      ) : producciones.length === 0 ? (
        <div className="bg-white border border-yeikar-secondary-light/10 rounded-3xl p-8 text-center text-sm italic text-yeikar-neutral/40">
          No hay producciones de crudo registradas.
        </div>
      ) : (
        <div className="space-y-4">
          {producciones.map((prod) => {
            const cfg = ESTADO_CFG[prod.estado] || ESTADO_CFG.PENDIENTE;
            const finalizable = prod.estado === 'PENDIENTE' || prod.estado === 'EN_PRODUCCION';
            const totalMat = totalMateriales(prod);
            const totalMano = totalMo(prod);
            const costoRegistrado = totalMat + totalMano;
            return (
              <div key={prod.id} className="bg-white border border-yeikar-secondary-light/10 rounded-2xl shadow-sm overflow-hidden">

                {/* Encabezado de ficha */}
                <div className="bg-gradient-to-r from-yeikar-tertiary/40 to-white px-5 py-4 border-b border-yeikar-secondary-light/10">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div className="flex items-center gap-3">
                      <span className={`inline-flex items-center gap-1.5 text-[11px] font-mono font-bold px-2.5 py-1 rounded-full ${cfg.bg} text-yeikar-secondary`}>
                        <span className={`w-1.5 h-1.5 rounded-full ${cfg.dot}`}></span>
                        {cfg.label}
                      </span>
                      <div>
                        <p className="font-headline font-bold text-yeikar-secondary text-sm">
                          Ítem: {prod.crudo?.nombre || `#${prod.crudo_id}`}
                          <span className="ml-2 font-mono text-yeikar-neutral/40">#{prod.id}</span>
                        </p>
                        <p className="text-[11px] text-yeikar-neutral/50 mt-0.5">
                          × {prod.cantidad.toLocaleString('es-ES')} und
                          {prod.fecha_inicio && ` · Inicio: ${fmtFechaVE(prod.fecha_inicio)}`}
                          {prod.fecha_fin && ` · Fin: ${fmtFechaVE(prod.fecha_fin)}`}
                        </p>
                      </div>
                    </div>
                    {finalizable && (
                      <div className="flex gap-2">
                        {prod.estado === 'PENDIENTE' && (
                          <button
                            onClick={() => handleIniciarProduccion(prod)}
                            className="bg-blue-600 hover:bg-blue-700 text-white px-3 py-1.5 rounded-xl font-bold font-headline text-xs transition-colors"
                          >
                            Iniciar
                          </button>
                        )}
                        <button
                          onClick={() => handleFinalizarProduccion(prod)}
                          className="bg-emerald-600 hover:bg-emerald-700 text-white px-3 py-1.5 rounded-xl font-bold font-headline text-xs transition-colors"
                        >
                          Finalizar (sumar stock)
                        </button>
                      </div>
                    )}
                  </div>
                  {prod.observaciones && (
                    <p className="text-[11px] text-yeikar-neutral/40 mt-1 italic">{prod.observaciones}</p>
                  )}
                </div>

                {/* Contenido de ficha */}
                <div className="p-5 space-y-5">

                  {/* Registrar Material */}
                  {finalizable && (
                    <form onSubmit={(e) => handleRegistrarConsumo(prod.id, e)} className="space-y-3">
                      <span className="text-xs font-headline font-black uppercase tracking-wider text-yeikar-primary">
                        Registrar Material
                      </span>
                      <div className="grid grid-cols-12 gap-2 items-end">
                        <div className="col-span-12 md:col-span-4">
                          <label className="block text-[10px] font-bold text-yeikar-secondary mb-1">Solicitante *</label>
                          <SearchSelect
                            value={consumoForm.solicitante_empleado_id}
                            onChange={(v) => setConsumoForm((p) => ({ ...p, solicitante_empleado_id: v }))}
                            options={empleadoOptions}
                            placeholder="Selecciona quién solicita..."
                            searchPlaceholder="Buscar empleado..."
                          />
                        </div>
                        <div className="col-span-12 md:col-span-4">
                          <label className="block text-[10px] font-bold text-yeikar-secondary mb-1">Material *</label>
                          <SearchSelect
                            value={consumoForm.material_id}
                            onChange={(v) => setConsumoForm((p) => ({
                              ...p,
                              material_id: v,
                              // El material define el modo de captura: reset.
                              unidad_captura: '', modo_pieza: false,
                              pieza_largo: '', pieza_ancho: '', pieza_espesor: '',
                            }))}
                            options={materialOptions}
                            placeholder="Buscar material..."
                            renderLabel={(opt) => {
                              const mat = materiales.find((m) => m.id === opt.value);
                              if (!mat) return opt.label;
                              const stock = stockMap[mat.id] ?? 0;
                              return (
                                <span className="flex items-center gap-2 min-w-0">
                                  <span className="truncate">{mat.nombre}</span>
                                  <span className="shrink-0 text-xs font-bold text-emerald-600">${mat.costo_base.toLocaleString('es-ES')}</span>
                                  <span className="shrink-0 text-[10px] text-yeikar-neutral/50">Stock: {stock}</span>
                                </span>
                              );
                            }}
                            searchPlaceholder="Escribe para filtrar..."
                          />
                        </div>
                        <div className="col-span-6 md:col-span-2">
                          <label className="block text-[10px] font-bold text-yeikar-secondary mb-1">
                            {dimConsumoCrudo === 'VOLUMEN' && consumoForm.modo_pieza ? 'Piezas *' : 'Cantidad *'}
                          </label>
                          <input
                            type="number" min="0.01" step="0.01" required
                            value={consumoForm.cantidad}
                            onChange={(e) => setConsumoForm((p) => ({ ...p, cantidad: e.target.value }))}
                            className={inputCls}
                          />
                        </div>
                        <div className="col-span-6 md:col-span-2">
                          <button
                            type="submit" disabled={savingConsumo}
                            className="w-full py-2 bg-yeikar-secondary hover:bg-yeikar-secondary-light text-white rounded-xl font-bold font-headline text-xs transition-colors disabled:opacity-50"
                          >
                            {savingConsumo ? '...' : '+ Agregar'}
                          </button>
                        </div>
                      </div>

                      {/* Captura flexible de madera (igual que producción por pedidos) */}
                      {materialConsumoCrudo && dimConsumoCrudo === 'LONGITUD' && (
                        <div className="flex items-center gap-2 flex-wrap">
                          <span className="text-[10px] font-semibold text-yeikar-neutral/50 uppercase">Digitar en:</span>
                          {([['M', 'mts'], ['CM', 'cm']] as const).map(([valor, etiqueta]) => (
                            <button
                              key={valor}
                              type="button"
                              onClick={() => setConsumoForm((p) => ({ ...p, unidad_captura: valor === 'M' ? '' : valor }))}
                              className={`text-[10px] font-bold px-2 py-1 rounded-lg border transition-colors ${
                                (consumoForm.unidad_captura || 'M') === valor
                                  ? 'bg-yeikar-primary text-yeikar-neutral border-yeikar-primary'
                                  : 'bg-white text-yeikar-neutral/60 border-yeikar-secondary-light/15 hover:border-yeikar-primary/40'
                              }`}
                            >
                              {etiqueta}
                            </button>
                          ))}
                          {parseFloat(consumoForm.cantidad) > 0 && (
                            <span className="text-[10px] font-mono text-emerald-700 bg-emerald-50 border border-emerald-200 rounded-lg px-2 py-0.5">
                              Descontará: {fmtNum(convertirCapturaLineal(parseFloat(consumoForm.cantidad), (consumoForm.unidad_captura || 'M') as UnidadCaptura))} m
                            </span>
                          )}
                        </div>
                      )}
                      {materialConsumoCrudo && dimConsumoCrudo === 'VOLUMEN' && (
                        <div className="flex items-center gap-2 flex-wrap">
                          <span className="text-[10px] font-semibold text-yeikar-neutral/50 uppercase">Como:</span>
                          {([['M3', 'm³'], ['PIEZA', 'Por pieza']] as const).map(([valor, etiqueta]) => (
                            <button
                              key={valor}
                              type="button"
                              onClick={() => setConsumoForm((p) => ({ ...p, modo_pieza: valor === 'PIEZA' }))}
                              className={`text-[10px] font-bold px-2 py-1 rounded-lg border transition-colors ${
                                (consumoForm.modo_pieza ? 'PIEZA' : 'M3') === valor
                                  ? 'bg-yeikar-primary text-yeikar-neutral border-yeikar-primary'
                                  : 'bg-white text-yeikar-neutral/60 border-yeikar-secondary-light/15 hover:border-yeikar-primary/40'
                              }`}
                            >
                              {etiqueta}
                            </button>
                          ))}
                        </div>
                      )}
                      {materialConsumoCrudo && dimConsumoCrudo === 'VOLUMEN' && consumoForm.modo_pieza && (
                        <div className="space-y-2">
                          <div className="grid grid-cols-3 gap-2">
                            {([['pieza_largo', 'Largo'], ['pieza_ancho', 'Ancho'], ['pieza_espesor', 'Espesor']] as const).map(([campo, etiqueta]) => (
                              <div key={campo}>
                                <label className="block text-[10px] font-bold text-yeikar-secondary mb-1">{etiqueta} *</label>
                                <input
                                  type="number" min="0.01" step="0.01" required
                                  value={consumoForm[campo]}
                                  onChange={(e) => setConsumoForm((p) => ({ ...p, [campo]: e.target.value }))}
                                  className={inputCls}
                                />
                              </div>
                            ))}
                          </div>
                          {consumoForm.pieza_largo && consumoForm.pieza_ancho && consumoForm.pieza_espesor && parseFloat(consumoForm.cantidad) > 0 && (
                            <p className="text-[10px] font-mono text-emerald-700 bg-emerald-50 border border-emerald-200 rounded-lg px-2 py-1">
                              Fórmula de la casa: ({consumoForm.pieza_largo}×{consumoForm.pieza_ancho}×{consumoForm.pieza_espesor}) × {consumoForm.cantidad} ÷ 10000 ={' '}
                              <span className="font-bold">
                                {fmtNum4(volumenPieza(
                                  { largo: parseFloat(consumoForm.pieza_largo), ancho: parseFloat(consumoForm.pieza_ancho), espesor: parseFloat(consumoForm.pieza_espesor) },
                                  parseFloat(consumoForm.cantidad) || 0,
                                ))} m³
                              </span>{' '}a descontar
                            </p>
                          )}
                        </div>
                      )}

                      {/* Componente y consumo extra (estructura de costes) */}
                      <div className="flex items-center gap-2 flex-wrap">
                        <input
                          list="componentes-sugeridos-crudo"
                          placeholder="Componente (ej. CAMA, NOCHERO...)"
                          value={consumoForm.componente}
                          onChange={(e) => setConsumoForm((p) => ({ ...p, componente: e.target.value }))}
                          className="w-40 text-[10px] bg-white border border-yeikar-secondary-light/10 rounded-lg px-2 py-1.5 focus:outline-none focus:border-yeikar-primary font-mono"
                        />
                        <datalist id="componentes-sugeridos-crudo">
                          {['CAMA', 'NOCHERO', 'CABECERA', 'ESTRUCTURA', 'REPISA', 'PUERTA', 'GAVETA', 'TAPA', 'BASE'].map((c) => (
                            <option key={c} value={c} />
                          ))}
                        </datalist>
                        <label className="flex items-center gap-1.5 text-[10px] font-semibold text-yeikar-neutral/60 cursor-pointer select-none">
                          <input
                            type="checkbox"
                            checked={consumoForm.es_excedente}
                            onChange={(e) => setConsumoForm((p) => ({ ...p, es_excedente: e.target.checked }))}
                            className="accent-red-600"
                          />
                          <span className={consumoForm.es_excedente ? 'text-red-600 font-bold' : ''}>
                            Consumo extra (daño/desperdicio)
                          </span>
                        </label>
                        {consumoForm.es_excedente && (
                          <select
                            value={consumoForm.motivo_exceso}
                            onChange={(e) => setConsumoForm((p) => ({ ...p, motivo_exceso: e.target.value }))}
                            className="text-[10px] bg-white border border-red-200 rounded-lg px-2 py-1.5 focus:outline-none focus:border-red-500 font-mono"
                          >
                            <option value="">Motivo...</option>
                            {['DAÑO', 'RETRABAJO', 'DESPERDICIO', 'PRUEBA', 'OTRO'].map((m) => (
                              <option key={m} value={m}>{m}</option>
                            ))}
                          </select>
                        )}
                      </div>
                    </form>
                  )}

                  {/* Materiales usados */}
                  <div>
                    <div className="flex items-center gap-2 mb-2">
                      <span className="text-xs font-headline font-black uppercase tracking-wider text-yeikar-secondary">
                        Materiales usados
                      </span>
                      <span className="text-[10px] font-mono text-yeikar-neutral/40">
                        ({(prod.consumos || []).length} registrados)
                      </span>
                    </div>
                    {(prod.consumos || []).length === 0 ? (
                      <p className="text-xs italic text-yeikar-neutral/40 pl-1">No se han registrado materiales para esta etapa.</p>
                    ) : (
                      <div className="space-y-1.5">
                        {(prod.consumos || []).map((c) => (
                          <div key={c.id} className="flex items-center justify-between gap-2 bg-yeikar-tertiary/10 border border-yeikar-secondary-light/5 rounded-xl px-3 py-2">
                            <div className="flex items-center gap-2 text-sm min-w-0">
                              <span className="font-semibold text-yeikar-secondary truncate">
                                {c.material_nombre || c.material?.nombre || `Material #${c.material_id}`}
                              </span>
                              {c.es_excedente && (
                                <span className="text-[9px] font-bold px-1.5 py-0.5 rounded-md bg-red-100 text-red-600 border border-red-200 uppercase shrink-0">
                                  EXTRA {c.motivo_exceso || 'OTRO'}
                                </span>
                              )}
                              {c.componente && (
                                <span className="text-[9px] font-bold px-1.5 py-0.5 rounded-md bg-indigo-50 text-indigo-600 border border-indigo-200 uppercase shrink-0">
                                  {c.componente}
                                </span>
                              )}
                              <span className="font-mono text-xs text-yeikar-neutral/50 shrink-0">
                                × {c.cantidad.toLocaleString('es-ES')}
                                {etiquetaCaptura(c) && <span className="text-yeikar-neutral/40"> · {etiquetaCaptura(c)}</span>}
                              </span>
                            </div>
                            <div className="flex items-center gap-3 text-[11px] text-yeikar-neutral/50 shrink-0">
                              <span>Pide: <span className="font-semibold text-yeikar-neutral/70">{c.solicitante_nombre || nombreEmpleado(c.solicitante_empleado_id)}</span></span>
                              {c.seccion && <span className="font-mono">{c.seccion}</span>}
                              {c.costo_unitario != null && (
                                <span className="font-mono font-bold">${fmtMoney(c.costo_unitario * c.cantidad)}</span>
                              )}
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>

                  {/* Totales */}
                  <div className="flex flex-wrap gap-4 text-xs font-headline border-t border-yeikar-secondary-light/10 pt-3">
                    <span className="text-yeikar-neutral/50">
                      TOTAL MATERIALES: <span className="font-bold text-yeikar-secondary font-mono">${fmtMoney(totalMat)}</span>
                    </span>
                    <span className="text-yeikar-neutral/50">
                      COSTO REGISTRADO: <span className="font-bold text-yeikar-secondary font-mono">${fmtMoney(costoRegistrado)}</span>
                    </span>
                  </div>

                  {/* Mano de obra de la etapa */}
                  {finalizable && (
                    <div className="space-y-4">
                      <h3 className="text-base font-bold font-headline text-yeikar-secondary border-b border-yeikar-secondary-light/5 pb-2 flex items-center justify-between">
                        <span>Mano de obra de la etapa</span>
                        <span className="text-xs font-mono font-normal text-yeikar-neutral/50">
                          ({(prod.mano_obras || []).length} registrados) · alimenta el costo de la orden
                        </span>
                      </h3>

                      <form onSubmit={(e) => handleRegistrarManoObra(prod.id, e, prod.cantidad || 1)} className="space-y-2 bg-yeikar-tertiary/30 p-3 rounded-2xl border border-yeikar-secondary-light/5">
                        <div className="grid grid-cols-1 sm:grid-cols-12 gap-2">
                          <div className="sm:col-span-4">
                            <SearchSelect
                              value={moForm.empleado_id}
                              onChange={(v) => setMoForm((p) => ({ ...p, empleado_id: v }))}
                              options={empleadoOptions}
                              placeholder="Empleado..."
                              searchPlaceholder="Buscar empleado..."
                            />
                          </div>
                          <div className="sm:col-span-4">
                            <SearchSelect
                              value={moForm.costo_id}
                              onChange={(v) => seleccionarCostoMo(String(v))}
                              options={costoOptions}
                              placeholder="Costo de producción (tarifa)"
                              searchPlaceholder="Buscar tarifa..."
                            />
                          </div>
                          <div className="sm:col-span-2">
                            <input
                              type="number" min="0.1" step="0.5" required
                              placeholder={`Cant. (máx ${prod.cantidad})`}
                              value={moForm.cantidad !== '' ? moForm.cantidad : String(prod.cantidad || 1)}
                              onChange={(e) => setMoForm((p) => ({ ...p, cantidad: e.target.value }))}
                              className={inputClsWhite}
                              title="Cantidad de unidades trabajadas por este empleado"
                            />
                            <p className="text-[9px] text-yeikar-neutral/40 mt-0.5 text-center">
                              {moForm.cantidad !== '' ? moForm.cantidad : (prod.cantidad || 1)} de {prod.cantidad} und
                            </p>
                          </div>
                          <div className="sm:col-span-2">
                            <input
                              type="number" min="0" step="1000" required
                              placeholder="Monto unit. ($)"
                              value={moForm.monto}
                              onChange={(e) => setMoForm((p) => ({ ...p, monto: e.target.value }))}
                              className={inputClsWhite}
                              title="Monto por cada unidad"
                            />
                            <p className="text-[9px] text-yeikar-neutral/40 mt-0.5 text-right font-mono font-bold text-yeikar-secondary">
                              = ${fmtMoney((Number(moForm.monto) || 0) * (Number(moForm.cantidad !== '' ? moForm.cantidad : prod.cantidad) || 1))}
                            </p>
                          </div>
                        </div>

                        {/* Crear nuevo costo al vuelo */}
                        {mostrarNuevoCosto && (
                          <div className="grid grid-cols-1 sm:grid-cols-12 gap-2 bg-white border border-dashed border-yeikar-primary/40 rounded-xl p-2 items-center">
                            <div className="sm:col-span-6">
                              <input
                                type="text"
                                value={nuevoCosto.descripcion}
                                onChange={(e) => setNuevoCosto((p) => ({ ...p, descripcion: e.target.value }))}
                                placeholder="Tipo de costo (ej. HECHURA EXTRA)"
                                className="w-full text-xs bg-white border border-yeikar-secondary-light/10 rounded-xl p-2.5 focus:outline-none focus:border-yeikar-primary"
                              />
                            </div>
                            <div className="sm:col-span-2">
                              <input
                                type="number" min="0" step="1000"
                                value={nuevoCosto.precio}
                                onChange={(e) => setNuevoCosto((p) => ({ ...p, precio: e.target.value }))}
                                placeholder="Precio ($)"
                                className="w-full text-xs bg-white border border-yeikar-secondary-light/10 rounded-xl p-2.5 focus:outline-none focus:border-yeikar-primary font-mono"
                              />
                            </div>
                            <div className="sm:col-span-2">
                              <select
                                value={nuevoCosto.area_id}
                                onChange={(e) => setNuevoCosto((p) => ({ ...p, area_id: e.target.value }))}
                                className="w-full text-xs bg-white border border-yeikar-secondary-light/10 rounded-xl p-2.5 focus:outline-none focus:border-yeikar-primary"
                              >
                                <option value="">Área</option>
                                {areas.map((a) => (
                                  <option key={a.id} value={a.id}>{a.nombre}</option>
                                ))}
                              </select>
                            </div>
                            <div className="sm:col-span-2 flex gap-1">
                              <button
                                type="button" disabled={creandoCosto}
                                onClick={crearCostoAlVuelo}
                                className="flex-1 py-2 bg-yeikar-primary hover:bg-yeikar-primary-dark text-white rounded-xl text-[10px] font-bold transition-colors disabled:opacity-50"
                              >
                                {creandoCosto ? '...' : 'Crear'}
                              </button>
                              <button
                                type="button"
                                onClick={() => setMostrarNuevoCosto(false)}
                                className="py-2 px-2 bg-yeikar-tertiary hover:bg-yeikar-secondary-light/15 text-yeikar-secondary rounded-xl text-[10px] font-bold transition-colors"
                              >
                                ×
                              </button>
                            </div>
                          </div>
                        )}

                        <div className="flex items-center gap-2">
                          <button
                            type="submit" disabled={savingMo}
                            className="py-2 px-4 bg-yeikar-secondary hover:bg-yeikar-secondary-light text-white rounded-xl font-bold font-headline text-xs transition-colors disabled:opacity-50"
                          >
                            {savingMo ? '...' : '+ Registrar costo de producción'}
                          </button>
                          {!mostrarNuevoCosto && (
                            <button
                              type="button"
                              onClick={() => setMostrarNuevoCosto(true)}
                              className="text-[10px] font-bold text-yeikar-primary hover:text-yeikar-primary-dark transition-colors"
                            >
                              + Crear tarifa al vuelo
                            </button>
                          )}
                        </div>
                      </form>

                      {/* Lista de mano de obra */}
                      <div className="space-y-1.5">
                        {(prod.mano_obras || []).length === 0 ? (
                          <p className="text-xs italic text-yeikar-neutral/40 pl-1">No se ha registrado mano de obra en esta etapa.</p>
                        ) : (
                          (prod.mano_obras || []).map((mo) => (
                            <div key={mo.id} className="flex items-center justify-between gap-2 bg-yeikar-tertiary/10 border border-yeikar-secondary-light/5 rounded-xl px-3 py-2">
                              <div className="flex items-center gap-2 text-sm min-w-0">
                                <span className="font-semibold text-yeikar-secondary truncate">{mo.empleado_nombre || `Empleado #${mo.empleado_id}`}</span>
                                <span className="font-mono text-xs text-yeikar-neutral/50 shrink-0">
                                  ${fmtMoney(mo.monto)}
                                  {mo.observaciones?.includes('MO unitaria') && (
                                    <span className="text-yeikar-neutral/40 ml-1">
                                      ({mo.observaciones})
                                    </span>
                                  )}
                                </span>
                              </div>
                              <div className="flex items-center gap-2 shrink-0">
                                {mo.pagado ? (
                                  <span className="text-[10px] font-bold text-emerald-600 uppercase">Pagada</span>
                                ) : mo.listo_nomina ? (
                                  <span className="text-[10px] font-bold text-amber-600 uppercase">Listo nómina</span>
                                ) : null}
                                {!mo.pagado && (
                                  <button
                                    onClick={() => handleEliminarManoObra(mo.id)}
                                    className="text-red-400 hover:text-red-600 text-xs transition-colors"
                                    title="Eliminar"
                                  >
                                    ×
                                  </button>
                                )}
                              </div>
                            </div>
                          ))
                        )}
                      </div>
                    </div>
                  )}

                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Modal de Nueva Producción */}
      {showProdModal && (
        <div className="fixed inset-0 bg-yeikar-secondary/60 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-3xl shadow-xl max-w-md w-full overflow-hidden border border-yeikar-secondary-light/10 max-h-[90vh] overflow-y-auto">
            <div className="bg-gradient-to-r from-yeikar-primary to-yeikar-primary-dark text-yeikar-neutral px-6 py-5">
              <h3 className="font-headline font-black text-lg">Nueva Producción</h3>
              <p className="text-xs text-yeikar-neutral/70">Elige el ítem a fabricar y la cantidad.</p>
            </div>
            <form onSubmit={handleCrearProduccion} className="p-6 space-y-4 font-body">
              <div className="space-y-3">
                <div>
                  <label className="block text-xs font-bold text-yeikar-secondary mb-1">Ítem en Crudo *</label>
                  <SearchSelect
                    value={newProduccion.crudo_id}
                    onChange={(v) => setNewProduccion((p) => ({ ...p, crudo_id: v }))}
                    options={crudoOptions}
                    placeholder="Selecciona un ítem..."
                    searchPlaceholder="Buscar ítem en crudo..."
                  />
                </div>
                <div className="grid grid-cols-3 gap-3">
                  <div className="col-span-2">
                    <label className="block text-xs font-bold text-yeikar-secondary mb-1">Cantidad *</label>
                    <input
                      type="number" min="1" step="1" required
                      value={newProduccion.cantidad}
                      onChange={(e) => setNewProduccion((p) => ({ ...p, cantidad: e.target.value }))}
                      className={inputCls}
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-bold text-yeikar-secondary mb-1">Observaciones</label>
                    <input
                      type="text"
                      value={newProduccion.observaciones}
                      onChange={(e) => setNewProduccion((p) => ({ ...p, observaciones: e.target.value }))}
                      className={inputCls.replace('font-mono', '')}
                      placeholder="Ej: Lote 1"
                    />
                  </div>
                </div>
              </div>
              <div className="flex gap-3">
                <button
                  type="button" onClick={() => setShowProdModal(false)}
                  className="flex-1 py-2.5 bg-yeikar-tertiary hover:bg-yeikar-secondary-light/15 text-yeikar-secondary rounded-xl font-bold font-headline text-sm transition-colors"
                >
                  Cancelar
                </button>
                <button
                  type="submit" disabled={savingProd}
                  className="flex-1 py-2.5 bg-yeikar-primary hover:bg-yeikar-primary-dark text-yeikar-neutral rounded-xl font-bold font-headline text-sm transition-all disabled:opacity-50"
                >
                  {savingProd ? 'Creando...' : 'Crear Producción'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
