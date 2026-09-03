import React, { useEffect, useState, useCallback, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { inventarioService, InventarioItem, AlertaStock, MovimientoResponse, ProductoInventarioItem, AlertaStockProducto, MovimientoProductoResponse, SobranteLamina, CategoriaInventario } from '../services/inventarioService';
import { productosService, type MonedaInfo } from '../services/productosService';
import { crudoService, produccionService, type Crudo } from '../services/produccionService';
import { subirAdjunto, TIPO_ADJUNTO } from '../services/adjuntosService';
import { cuentasService } from '../services/cuentasService';
import api from '../services/api';
import { useToast } from '../context/ToastContext';
import { SearchSelect, ResponsiveDataTable, type DataColumn } from '../components/ui';

interface Ubicacion {
  id: number;
  nombre: string;
}

interface Material {
  id: number;
  nombre: string;
  unidad_medida_id: number;
  unidad_medida?: {
    abreviatura: string;
    nombre: string;
  };
  costo_base: number;
  stock_minimo?: number;
  largo_cm?: number | null;
  ancho_cm?: number | null;
  categoria_inventario_id?: number | null;
  departamento?: string | null;
}

  interface Product {
  id: number;
  nombre: string;
  codigo?: string;
  stock_minimo?: number;
  es_reventa?: boolean;
  es_exhibicion?: boolean;
  moneda_id?: number | null;
  moneda?: MonedaInfo | null;
  categoria_inventario_id?: number | null;
  precio_costo_base?: number | null;
  precio_venta_base?: number | null;
  fotos?: { url?: string }[];
}

type Tab = 'insumos' | 'sobrantes' | 'productos' | 'exhibicion' | 'crudo';

const TIPOS_MOVIMIENTO = ['ENTRADA', 'SALIDA', 'AJUSTE', 'DAÑO', 'DEVOLUCION'];

/** Quita acentos y pasa a mayúsculas: compara "Exhibición" con "EXHIBICION". */
const quitarAcentos = (s: string) => s.normalize('NFD').replace(/[\u0300-\u036f]/g, '');
const esNombreExhibicion = (nombre?: string | null) =>
  !!nombre && quitarAcentos(nombre).toUpperCase().includes('EXHIBIC');

const MONEDA_BASE_ID = 1; // COP

// Departamentos del taller para el inventario de insumos. Tendido no es
// departamento propio: sus insumos se marcan EBANISTERIA. Sin departamento
// = insumo transversal/general.
const DEPARTAMENTOS: { valor: string; label: string }[] = [
  { valor: 'EBANISTERIA', label: 'Ebanistería' },
  { valor: 'PREPARACION', label: 'Preparación' },
  { valor: 'PINTURA', label: 'Pintura' },
  { valor: 'TAPICERIA', label: 'Tapicería' },
  { valor: 'VIDRIERIA', label: 'Vidriería' },
  { valor: 'TERMINACION', label: 'Terminación' },
];
const labelDepartamento = (d: string | null | undefined) =>
  DEPARTAMENTOS.find((x) => x.valor === d)?.label ?? (d || null);

function parsePagoKey(key: string): { cuentaId: number | null; monedaId: number | null } {
  const [cuentaId, monedaId] = (key || '').split(':');
  return {
    cuentaId: cuentaId ? Number(cuentaId) : null,
    monedaId: monedaId ? Number(monedaId) : null,
  };
}

export default function Inventario() {
  const toast = useToast();
  const navigate = useNavigate();
  interface UnidadMedida {
    id: number;
    nombre: string;
    abreviatura: string;
  }

  const [tab, setTab] = useState<Tab>('insumos');

  // ── Estado compartido ----
  const [ubicaciones, setUbicaciones] = useState<Ubicacion[]>([]);
  const [unidades, setUnidades] = useState<UnidadMedida[]>([]);
  const [monedas, setMonedas] = useState<MonedaInfo[]>([]);
  // Métodos de caja (Efectivo, Nequi, Bancolombia...): para el egreso
  // automático al comprar reventa de contado.
  const [metodosCaja, setMetodosCaja] = useState<{ id: number; nombre: string }[]>([]);
  const [loading, setLoading] = useState(true);

  // ---- Insumos ----
  const [inventario, setInventario] = useState<InventarioItem[]>([]);
  const [alertas, setAlertas] = useState<AlertaStock[]>([]);
  const [materiales, setMateriales] = useState<Material[]>([]);
  const [search, setSearch] = useState('');
  const [selectedMaterialId, setSelectedMaterialId] = useState<number | null>(null);
  const [kardex, setKardex] = useState<MovimientoResponse[]>([]);
  const [loadingKardex, setLoadingKardex] = useState(false);
  // Categorías de inventario (desglose: LÁMINAS MDF, ESPUMA, PINTURA...)
  const [categoriasMaterial, setCategoriasMaterial] = useState<CategoriaInventario[]>([]);
  const [categoriasProducto, setCategoriasProducto] = useState<CategoriaInventario[]>([]);
  const [filtroCatMaterial, setFiltroCatMaterial] = useState<number | null>(null);
  const [filtroCatProducto, setFiltroCatProducto] = useState<number | null>(null);
  // Departamento del taller activo en el tab Insumos (null = todos, 'GENERAL' = sin departamento)
  const [filtroDepto, setFiltroDepto] = useState<string | null>(null);

  // ---- Sobrantes de láminas (retazos reutilizables) ----
  const [sobrantes, setSobrantes] = useState<SobranteLamina[]>([]);
  const [showSobranteModal, setShowSobranteModal] = useState(false);
  const [newSobrante, setNewSobrante] = useState({ material_id: '', largo_cm: '', ancho_cm: '', observaciones: '' });
  const [savingSobrante, setSavingSobrante] = useState(false);

  // Formulario de movimiento de MATERIAL (dentro del panel)
  const [movMaterial, setMovMaterial] = useState({
    ubicacion_id: '',
    tipo: 'ENTRADA',
    cantidad: '',
    costo_unitario: '',
    descuento_porcentaje: '',
    observaciones: '',
    pago_key: '',   // "cuentaId:monedaId" — vacío = a crédito
    tasa_pago: '',
    llevada: '',    // "la llevada": flete/aduana (opcional)
    proveedor_nombre: '', // dónde se compró (texto libre, opcional, solo entradas)
    cliente_nombre: '',  // comprado para un cliente específico (texto libre, opcional)
  });
  const [savingMov, setSavingMov] = useState(false);

  // Cuentas con su moneda para pagos de contado (una cuenta puede tener varias)
  interface CuentaMonedaOpcion { key: string; cuentaId: number; nombre: string; monedaId: number; codigo: string; }
  const [cuentasPago, setCuentasPago] = useState<CuentaMonedaOpcion[]>([]);

  // ── Pago de contado en entradas ──
  const parsePagoKeyLocal = parsePagoKey;
  const codMonedaDe = (mid: number | null | undefined) =>
    monedas.find((m) => m.id === Number(mid))?.codigo ?? 'COP';

  // Edición de insumo (dentro del panel)
  const [editMaterial, setEditMaterial] = useState({
    nombre: '', costo_base: '', stock_minimo: '8',
    largo_cm: '', ancho_cm: '', categoria_inventario_id: '',
    departamento: null as string | null,
  });
  const [savingEdit, setSavingEdit] = useState(false);

  // ---- Productos (terminados / reventa) ----
  const [invProductos, setInvProductos] = useState<ProductoInventarioItem[]>([]);
  const [alertasProductos, setAlertasProductos] = useState<AlertaStockProducto[]>([]);
  const [productos, setProductos] = useState<Product[]>([]);
  const [searchProducto, setSearchProducto] = useState('');
  const [selectedProductoId, setSelectedProductoId] = useState<number | null>(null);
  const [kardexProducto, setKardexProducto] = useState<MovimientoProductoResponse[]>([]);
  const [loadingKardexProducto, setLoadingKardexProducto] = useState(false);

  // Formulario de movimiento de PRODUCTO (dentro del panel)
  const [movProducto, setMovProducto] = useState({
    ubicacion_id: '',
    tipo: 'ENTRADA',
    cantidad: '',
    costo_unitario: '',
    descuento_porcentaje: '',
    pagado_desde_metodo_caja_id: '',   // key "cuentaId:monedaId"
    moneda_pago_id: '',
    tasa_pago: '',
    observaciones: '',
    llevada: '',    // "la llevada": flete/aduana (opcional)
    proveedor_nombre: '', // dónde se compró (texto libre, opcional, solo entradas)
    cliente_nombre: '',  // comprado para un cliente específico (texto libre, opcional)
  });
  const [savingMovProd, setSavingMovProd] = useState(false);

  // ---- Exhibición (piezas mostradas, no rotan como venta normal) ----
  // Todas las filas de producto_inventario se filtran por ubicación con
  // nombre tipo "EXHIBIC..." (client-side: la ubicación es dato, no código).
  const [productosTodos, setProductosTodos] = useState<Product[]>([]);
  const [tiposProducto, setTiposProducto] = useState<{ id: number; nombre: string }[]>([]);
  const [searchExhibicion, setSearchExhibicion] = useState('');
  // Modal "Nueva Pieza": alta de una pieza de exhibición con solo nombre,
  // precio en dólares y cantidad. El resto (producción, nómina, costos) se
  // gestiona desde Producción.
  const [showPiezaModal, setShowPiezaModal] = useState(false);
  const [newPieza, setNewPieza] = useState({ nombre: '', precio_usd: '', cantidad: '1' });
  const [fotoPieza, setFotoPieza] = useState<File | null>(null);
  const [fotoPiezaPreview, setFotoPiezaPreview] = useState<string | null>(null);
  const [savingPieza, setSavingPieza] = useState(false);
  // Modal "Orden de Producción": fabricar la pieza (etapas, consumos, nómina).
  const [producirPieza, setProducirPieza] = useState<{ producto_id: number; nombre: string } | null>(null);
  const [savingProducir, setSavingProducir] = useState(false);

  // ---- Productos en Crudo (ítem libre de inventario) ----
  const [crudo, setCrudo] = useState<Crudo[]>([]);
  const [loadingCrudo, setLoadingCrudo] = useState(false);
  // Alta manual de ítem en crudo.
  const [showCrudoModal, setShowCrudoModal] = useState(false);
  const [newCrudo, setNewCrudo] = useState({ nombre: '' });
  const [fotoCrudo, setFotoCrudo] = useState<File | null>(null);
  const [savingCrudo, setSavingCrudo] = useState(false);
  // Modal "Asignar a pedido"
  const [asignarCrudoTarget, setAsignarCrudoTarget] = useState<Crudo | null>(null);
  const [detallePedidoInput, setDetallePedidoInput] = useState('');
  const [asignando, setAsignando] = useState(false);

  const [showMaterialModal, setShowMaterialModal] = useState(false);
  const [newMaterial, setNewMaterial] = useState({
    nombre: '',
    costo_base: '',
    unidad_medida_id: '',
    stock_minimo: '8',
    largo_cm: '',   // dimensiones de lámina (cm) — solo materiales laminares
    ancho_cm: '',
    categoria_inventario_id: '',
    departamento: null as string | null,
  });

  // Modal "Nuevo Producto de Reventa"
  const [showProductoModal, setShowProductoModal] = useState(false);
  const [newProducto, setNewProducto] = useState({
    nombre: '',
    codigo: '',
    costo_base: '',             // Precio lista del proveedor (opcional)
    descuento_porcentaje: '',   // % Descuento por pronto pago / al mayor (opcional)
    stock_minimo: '8',
    cantidad_inicial: '1',
    cuenta_pago_id: '', // key "cuentaId:monedaId" — de qué caja salió el dinero (opcional)
    tasa_pago: '',      // 1 [moneda_pago] = X COP (manual, obligatoria si aplica)
    moneda_id: '', // string para SearchSelect; default USD cuando cargan las monedas
  });
  const [savingProducto, setSavingProducto] = useState(false);
  const [fotoProducto, setFotoProducto] = useState<File | null>(null);
  const [fotoProductoPreview, setFotoProductoPreview] = useState<string | null>(null);

  /** Los productos de reventa se compran en USD; si no existe, primera moneda o COP. */
  const idMonedaPorDefecto = () => {
    const usd = monedas.find(m => m.codigo === 'USD');
    return String(usd?.id ?? monedas[0]?.id ?? 1);
  };

  // Al cargar el catálogo de monedas, preseleccionar la moneda por defecto.
  useEffect(() => {
    if (monedas.length && !newProducto.moneda_id) {
      setNewProducto(prev => ({ ...prev, moneda_id: idMonedaPorDefecto() }));
    }
  }, [monedas]); // eslint-disable-line react-hooks/exhaustive-deps

  const monedaSeleccionada = monedas.find(m => String(m.id) === newProducto.moneda_id);
  const simboloPrecio = monedaSeleccionada?.simbolo || '$';

  const fetchData = useCallback(async () => {
    try {
      setLoading(true);
      const [ubiData, uniData, monData, metodosData, catsMat, catsProd, tiposData] = await Promise.all([
        api.get<Ubicacion[]>('/catalogos/ubicacion/'),
        api.get<UnidadMedida[]>('/catalogos/unidad-medida/'),
        api.get<MonedaInfo[]>('/catalogos/moneda/'),
        cuentasService.getResumen().catch(() => []),
        inventarioService.getCategorias('MATERIAL').catch(() => []),
        inventarioService.getCategorias('PRODUCTO').catch(() => []),
        api.get<{ id: number; nombre: string }[]>('/catalogos/tipo-producto/').catch(() => null),
      ]);
      setUbicaciones(ubiData.data);
      setUnidades(uniData.data);
      setMonedas(monData.data.filter(m => m.activo !== false));
      setCategoriasMaterial(catsMat);
      setCategoriasProducto(catsProd);
      setTiposProducto(Array.isArray(tiposData) ? tiposData : (tiposData?.data ?? []));
      // Métodos únicos de caja (el resumen trae una fila por cuenta)
      const vistos = new Set<number>();
      const metodos: { id: number; nombre: string }[] = [];
      // Opciones cuenta+moneda para pagos de contado: UNA opción por cuenta,
      // SIEMPRE en la moneda propia de la cuenta (la que dice su ficha). No se
      // ofrecen otras monedas aunque tengan movimientos: evita pagar un insumo
      // "Efectivo en Pesos" en dólares por error.
      const opciones: CuentaMonedaOpcion[] = [];
      for (const r of metodosData) {
        if (!vistos.has(r.metodo_caja.id)) {
          vistos.add(r.metodo_caja.id);
          metodos.push({ id: r.metodo_caja.id, nombre: r.metodo_caja.nombre });
        }
        const propia = r.saldo_por_moneda.find((l) => l.moneda_id === r.metodo_caja.moneda_id) ?? {
          moneda_id: r.metodo_caja.moneda_id || 1,
          codigo: r.metodo_caja.moneda_codigo || 'COP',
          simbolo: r.metodo_caja.moneda_simbolo || '$',
          monto: 0,
        };
        opciones.push({
          key: `${r.metodo_caja.id}:${propia.moneda_id}`,
          cuentaId: r.metodo_caja.id,
          nombre: r.metodo_caja.nombre,
          monedaId: propia.moneda_id,
          codigo: propia.codigo,
        });
      }
      setMetodosCaja(metodos);
      setCuentasPago(opciones);
    } catch (error) {
      console.error('Error fetching catalog data:', error);
    } finally {
      setLoading(false);
    }
  }, []);

  const fetchInsumos = useCallback(async () => {
    try {
      const [invData, alertsData, matData] = await Promise.all([
        inventarioService.getInventario(),
        inventarioService.getAlertas(8.0),
        api.get<Material[]>('/material/?limite=1000'),
      ]);

      const matMap = new Map(matData.data.map(m => [m.id, m]));
      const enrichedInv = invData.map((item) => ({
        ...item,
        material: matMap.get(item.material_id),
      }));

      setInventario(enrichedInv);
      setAlertas(alertsData);
      setMateriales(matData.data);
    } catch (error) {
      console.error('Error fetching inventory data:', error);
    }
  }, []);

  const fetchProductos = useCallback(async () => {
    try {
      // Stock COMPLETO (todas las ubicaciones): la tab de reventa agrupa por
      // producto y la de exhibición filtra por ubicación "EXHIBIC...".
      const [invData, alertsData, prodData, todosData] = await Promise.all([
        inventarioService.getInventarioProductos(),
        inventarioService.getAlertasProductos(8.0),
        productosService.getProductos(undefined, { es_reventa: true, limite: 1000 }),
        productosService.getProductos(undefined, { limite: 1000 }),
      ]);
      setInvProductos(invData);
      setAlertasProductos(alertsData);
      setProductos(prodData);
      setProductosTodos(todosData);
    } catch (error) {
      console.error('Error fetching product inventory:', error);
    }
  }, []);

  const fetchCrudo = useCallback(async () => {
    setLoadingCrudo(true);
    try {
      const data = await crudoService.getCrudo();
      setCrudo(data);
    } catch (error) {
      console.error('Error fetching crudo inventory:', error);
    } finally {
      setLoadingCrudo(false);
    }
  }, []);

  const fetchSobrantes = useCallback(async () => {
    try {
      const data = await inventarioService.getSobrantes({ estado: 'DISPONIBLE' });
      setSobrantes(data);
    } catch (error) {
      console.error('Error fetching sobrantes:', error);
    }
  }, []);

  useEffect(() => {
    fetchData();
    fetchInsumos();
    fetchProductos();
    fetchCrudo();
    fetchSobrantes();
  }, [fetchData, fetchInsumos, fetchProductos, fetchCrudo, fetchSobrantes]);

  const handleCreateCrudo = async (e: React.FormEvent) => {
    e.preventDefault();
    const nombre = newCrudo.nombre.trim();
    if (!nombre) return;
    setSavingCrudo(true);
    try {
      const creado = await crudoService.crearCrudo({ nombre });
      if (fotoCrudo) {
        try {
          await subirAdjunto(fotoCrudo, TIPO_ADJUNTO.CRUDO, creado.id);
        } catch {
          /* la foto es opcional */
        }
      }
      setShowCrudoModal(false);
      setNewCrudo({ nombre: '' });
      setFotoCrudo(null);
      toast.success('Ítem en crudo registrado.');
      fetchCrudo();
    } catch (error: any) {
      toast.error(error.response?.data?.detail || 'Error al registrar el ítem en crudo.');
    } finally {
      setSavingCrudo(false);
    }
  };

  const handleAsignarCrudo = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!asignarCrudoTarget) return;
    const detalleId = Number(detallePedidoInput);
    if (!detalleId) {
      toast.error('Indica el ID del detalle de pedido.');
      return;
    }
    setAsignando(true);
    try {
      await crudoService.asignarCrudo(asignarCrudoTarget.id, detalleId);
      setAsignarCrudoTarget(null);
      setDetallePedidoInput('');
      toast.success('Pieza de crudo asignada al pedido. Se descontó del stock.');
      fetchCrudo();
    } catch (error: any) {
      toast.error(error.response?.data?.detail || 'No se pudo asignar el crudo al pedido.');
    } finally {
      setAsignando(false);
    }
  };

  const handleCreateMaterial = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newMaterial.nombre.trim() || !newMaterial.unidad_medida_id) return;

    try {
      await api.post('/material/', {
        nombre: newMaterial.nombre.toUpperCase().trim(),
        costo_base: newMaterial.costo_base ? parseFloat(newMaterial.costo_base) : 0.0,
        unidad_medida_id: parseInt(newMaterial.unidad_medida_id),
        stock_minimo: newMaterial.stock_minimo ? parseFloat(newMaterial.stock_minimo) : 8.0,
        activo: true,
        // Dimensiones de lámina (cm): solo si se llenan ambas → material laminar
        largo_cm: newMaterial.largo_cm ? parseFloat(newMaterial.largo_cm) : null,
        ancho_cm: newMaterial.ancho_cm ? parseFloat(newMaterial.ancho_cm) : null,
        categoria_inventario_id: newMaterial.categoria_inventario_id ? parseInt(newMaterial.categoria_inventario_id) : null,
        departamento: newMaterial.departamento || null,
      });

      setShowMaterialModal(false);
      setNewMaterial({ nombre: '', costo_base: '', unidad_medida_id: '', stock_minimo: '8', largo_cm: '', ancho_cm: '', categoria_inventario_id: '', departamento: null });
      fetchInsumos();
      toast.success('Insumo registrado.');
    } catch (error: any) {
      toast.error(error.response?.data?.detail || 'Error al crear el insumo.');
    }
  };

  // ---- Registrar sobrante manual (retazo) ----
  const handleCreateSobrante = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newSobrante.material_id || !newSobrante.largo_cm || !newSobrante.ancho_cm) return;
    setSavingSobrante(true);
    try {
      await inventarioService.crearSobrante({
        material_id: parseInt(newSobrante.material_id),
        ubicacion_id: 1,
        largo_cm: parseFloat(newSobrante.largo_cm),
        ancho_cm: parseFloat(newSobrante.ancho_cm),
        observaciones: newSobrante.observaciones.trim() || 'Registro manual',
      });
      setShowSobranteModal(false);
      setNewSobrante({ material_id: '', largo_cm: '', ancho_cm: '', observaciones: '' });
      toast.success('Sobrante registrado. Ya puede usarse en cortes.');
      fetchSobrantes();
    } catch (error: any) {
      toast.error(error.response?.data?.detail || 'Error al registrar el sobrante.');
    } finally {
      setSavingSobrante(false);
    }
  };

  const handleDeshecharSobrante = async (s: SobranteLamina) => {
    try {
      await inventarioService.actualizarSobrante(s.id, { estado: 'DESECHADO' });
      toast.success('Sobrante marcado como desechado.');
      fetchSobrantes();
    } catch (error: any) {
      toast.error(error.response?.data?.detail || 'Error al deshechar.');
    }
  };

  const handleEliminarSobrante = async (s: SobranteLamina) => {
    if (!window.confirm(`¿Eliminar el retazo ${s.largo_cm}×${s.ancho_cm} cm del listado?`)) return;
    try {
      await inventarioService.eliminarSobrante(s.id);
      toast.success('Sobrante eliminado.');
      fetchSobrantes();
    } catch (error: any) {
      toast.error(error.response?.data?.detail || 'Error al eliminar.');
    }
  };

  // ---- Crear producto de REVENTA (comprado para revender) ----
  const handleCreateProducto = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newProducto.nombre.trim()) return;
    const pagoModal = parsePagoKey(newProducto.cuenta_pago_id);
    const prodMonedaNueva = parseInt(newProducto.moneda_id || String(MONEDA_BASE_ID)) || MONEDA_BASE_ID;
    if (
      pagoModal.cuentaId &&
      (pagoModal.monedaId !== MONEDA_BASE_ID || prodMonedaNueva !== MONEDA_BASE_ID) &&
      !(parseFloat(newProducto.tasa_pago || '0') > 0)
    ) {
      toast.error(
        `Indica la tasa de cambio: 1 ${codMonedaDe(pagoModal.monedaId ?? prodMonedaNueva)} = ? COP.`
      );
      return;
    }

    const costoBruto = parseFloat(newProducto.costo_base || '0') || 0;
    const pctDesc = parseFloat(newProducto.descuento_porcentaje || '0') || 0;
    const costoNeto = costoBruto > 0 && pctDesc > 0
      ? parseFloat((costoBruto * (1 - pctDesc / 100)).toFixed(2))
      : (costoBruto > 0 ? costoBruto : undefined);
    const detalleDesc = costoBruto > 0 && pctDesc > 0
      ? `Descuento pronto pago/mayor: ${pctDesc}% (Lista: ${simboloPrecio}${costoBruto.toFixed(2)} → Neto: ${simboloPrecio}${costoNeto?.toFixed(2)})`
      : '';

    try {
      setSavingProducto(true);
      const creado = await productosService.crearProducto({
        nombre: newProducto.nombre.toUpperCase().trim(),
        codigo: newProducto.codigo ? newProducto.codigo.trim() : undefined,
        tipo_producto_id: 2, // Revendido
        descripcion: 'Producto de reventa',
        activo: true,
        // Un reventa no tiene dimensiones de mueble: se omiten (null en BD)
        ancho_base: undefined,
        largo_base: undefined,
        stock_minimo: newProducto.stock_minimo ? parseFloat(newProducto.stock_minimo) : 8.0,
        es_reventa: true,
        // Precios de referencia en la moneda elegida (USD por defecto)
        moneda_id: parseInt(newProducto.moneda_id || '1') || 1,
        precio_costo_base: costoNeto,
        precio_venta_base: undefined,
      });
      // Foto de referencia (opcional): se sube y el servidor la optimiza
      if (fotoProducto && creado.id) {
        await subirAdjunto(fotoProducto, TIPO_ADJUNTO.PRODUCTO, creado.id);
        setFotoProducto(null);
        if (fotoProductoPreview) URL.revokeObjectURL(fotoProductoPreview);
        setFotoProductoPreview(null);
      }
      setShowProductoModal(false);
      setNewProducto({
        nombre: '',
        codigo: '',
        costo_base: '',
        descuento_porcentaje: '',
        stock_minimo: '8',
        cantidad_inicial: '1',
        cuenta_pago_id: '',
        tasa_pago: '',
        moneda_id: idMonedaPorDefecto(),
      });

      // Entrada inicial al inventario: la cantidad la decide el usuario
      // (default 1); el costo es opcional. Si indica cuenta de pago, se
      // genera el egreso automático (gasto + salida de caja).
      const cantInicial = parseFloat(newProducto.cantidad_inicial || '0') || 0;
      if (cantInicial > 0 && creado.id) {
        const ubi = ubicaciones[0];
        if (ubi) {
          await inventarioService.crearMovimientoProducto({
            producto_id: creado.id,
            ubicacion_id: ubi.id,
            tipo: 'ENTRADA',
            cantidad: cantInicial,
            costo_unitario: costoNeto,
            pagado_desde_metodo_caja_id: pagoModal.cuentaId ?? undefined,
            moneda_pago_id: pagoModal.monedaId ?? undefined,
            tasa_pago: pagoModal.cuentaId && parseFloat(newProducto.tasa_pago || '0') > 0 ? parseFloat(newProducto.tasa_pago) : undefined,
            observaciones: ['Carga inicial de producto de reventa', detalleDesc].filter(Boolean).join(' · '),
          });
        }
      }
      fetchProductos();
    } catch (error: any) {
      toast.error(error.response?.data?.detail || 'Error al crear el producto.');
    } finally {
      setSavingProducto(false);
    }
  };

  // ---- Abrir panel de material (kardex + edición + movimiento) ----
  const handleOpenMaterial = async (mat: Material) => {
    setSelectedMaterialId(mat.id);
    setEditMaterial({
      nombre: mat.nombre,
      costo_base: mat.costo_base != null ? String(mat.costo_base) : '',
      stock_minimo: mat.stock_minimo != null ? String(mat.stock_minimo) : '8',
      largo_cm: mat.largo_cm != null ? String(mat.largo_cm) : '',
      ancho_cm: mat.ancho_cm != null ? String(mat.ancho_cm) : '',
      categoria_inventario_id: mat.categoria_inventario_id != null ? String(mat.categoria_inventario_id) : '',
      departamento: mat.departamento ?? null,
    });
    setMovMaterial({ ubicacion_id: '', tipo: 'ENTRADA', cantidad: '', costo_unitario: mat.costo_base ? String(mat.costo_base) : '', descuento_porcentaje: '', observaciones: '', pago_key: '', tasa_pago: '', llevada: '', proveedor_nombre: '', cliente_nombre: '' });
    try {
      setLoadingKardex(true);
      const data = await inventarioService.getKardex(mat.id);
      setKardex(data);
    } catch (error) {
      console.error('Error fetching kardex:', error);
    } finally {
      setLoadingKardex(false);
    }
  };

  // ---- Guardar edición del insumo ----
  const handleSaveMaterial = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedMaterialId) return;
    try {
      setSavingEdit(true);
      await api.put(`/material/${selectedMaterialId}`, {
        nombre: editMaterial.nombre.toUpperCase().trim(),
        costo_base: editMaterial.costo_base ? parseFloat(editMaterial.costo_base) : 0.0,
        stock_minimo: editMaterial.stock_minimo ? parseFloat(editMaterial.stock_minimo) : 8.0,
        largo_cm: editMaterial.largo_cm ? parseFloat(editMaterial.largo_cm) : null,
        ancho_cm: editMaterial.ancho_cm ? parseFloat(editMaterial.ancho_cm) : null,
        categoria_inventario_id: editMaterial.categoria_inventario_id ? parseInt(editMaterial.categoria_inventario_id) : null,
        departamento: editMaterial.departamento || null,
      });
      toast.success('Insumo actualizado.');
      fetchInsumos();
    } catch (error: any) {
      toast.error(error.response?.data?.detail || 'Error al guardar el insumo.');
    } finally {
      setSavingEdit(false);
    }
  };

  // ---- Registrar movimiento de material (desde el panel) ----
  const handleRegisterMovement = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedMaterialId || !movMaterial.ubicacion_id || !movMaterial.cantidad) return;

    const esEntrada = movMaterial.tipo === 'ENTRADA' || movMaterial.tipo === 'DEVOLUCION';
    const pago = esEntrada ? parsePagoKey(movMaterial.pago_key) : { cuentaId: null, monedaId: null };
    const tasaNum = parseFloat(movMaterial.tasa_pago || '0');
    if (pago.cuentaId && pago.monedaId !== MONEDA_BASE_ID && !(tasaNum > 0)) {
      toast.error(`Indica la tasa de cambio: 1 ${codMonedaDe(pago.monedaId)} = ? COP.`);
      return;
    }
    // "Fiar": entrada sin cuenta de pago → la deuda queda registrada con el
    // proveedor (obligatorio). Sin proveedor, no se puede fiar.
    const fiando = movMaterial.tipo === 'ENTRADA' && !pago.cuentaId;
    if (fiando && !movMaterial.proveedor_nombre) {
      toast.error('Al fiar debes indicar el proveedor (campo Proveedor del movimiento).');
      return;
    }

    const costoBruto = esEntrada && movMaterial.costo_unitario ? parseFloat(movMaterial.costo_unitario) : undefined;
    const pctDesc = esEntrada && movMaterial.descuento_porcentaje ? parseFloat(movMaterial.descuento_porcentaje) : 0;
    const costoNeto = costoBruto !== undefined && pctDesc > 0
      ? parseFloat((costoBruto * (1 - pctDesc / 100)).toFixed(2))
      : costoBruto;
    const notaDesc = costoBruto !== undefined && pctDesc > 0
      ? `Descuento pronto pago/mayor: ${pctDesc}% (Lista: $${costoBruto.toLocaleString('es-CO')} → Neto: $${costoNeto?.toLocaleString('es-CO')})`
      : '';

    try {
      setSavingMov(true);
      await inventarioService.crearMovimiento({
        material_id: selectedMaterialId,
        ubicacion_id: parseInt(movMaterial.ubicacion_id),
        tipo: movMaterial.tipo as any,
        cantidad: parseFloat(movMaterial.cantidad),
        costo_unitario: costoNeto,
        pagado_desde_metodo_caja_id: esEntrada && pago.cuentaId ? pago.cuentaId : undefined,
        moneda_pago_id: esEntrada && pago.cuentaId ? pago.monedaId ?? undefined : undefined,
        tasa_pago: esEntrada && pago.cuentaId && pago.monedaId !== MONEDA_BASE_ID ? tasaNum : undefined,
        // "La llevada": flete/aduana (solo tiene sentido en compras de contado)
        llevada: esEntrada && movMaterial.llevada ? parseFloat(movMaterial.llevada) : undefined,
        proveedor_nombre: esEntrada && movMaterial.proveedor_nombre ? movMaterial.proveedor_nombre.trim() : undefined,
        cliente_nombre: esEntrada && movMaterial.cliente_nombre ? movMaterial.cliente_nombre.trim() : undefined,
        fiar: fiando || undefined,
        observaciones: [movMaterial.observaciones, notaDesc].filter(Boolean).join(' · ') || undefined,
      });

      setMovMaterial({ ubicacion_id: '', tipo: 'ENTRADA', cantidad: '', costo_unitario: '', descuento_porcentaje: '', observaciones: '', pago_key: '', tasa_pago: '', llevada: '', proveedor_nombre: '', cliente_nombre: '' });
      fetchInsumos();
      const mat = materiales.find(m => m.id === selectedMaterialId);
      if (mat) handleOpenMaterial(mat);
    } catch (error: any) {
      toast.error(error.response?.data?.detail || 'Error al registrar el movimiento.');
    } finally {
      setSavingMov(false);
    }
  };

  // ---- Kardex de producto (compartido por tabs reventa y exhibición) ----
  const refrescarKardexProducto = useCallback(async (id: number) => {
    try {
      setLoadingKardexProducto(true);
      const data = await inventarioService.getKardexProducto(id);
      setKardexProducto(data);
    } catch (error) {
      console.error('Error fetching product kardex:', error);
    } finally {
      setLoadingKardexProducto(false);
    }
  }, []);

  // ---- Abrir panel de producto ----
  const handleOpenProducto = (p: { id: number }) => {
    setSelectedProductoId(p.id);
    // En exhibición, el movimiento típico es ENTRADA a la ubicación de exhibición.
    const ubiExh = tab === 'exhibicion' ? ubicaciones.find(u => esNombreExhibicion(u.nombre)) : undefined;
    setMovProducto({ ubicacion_id: ubiExh ? String(ubiExh.id) : '', tipo: 'ENTRADA', cantidad: '', costo_unitario: '', descuento_porcentaje: '', pagado_desde_metodo_caja_id: '', moneda_pago_id: '', tasa_pago: '', observaciones: '', llevada: '', proveedor_nombre: '', cliente_nombre: '' });
    refrescarKardexProducto(p.id);
  };

  // ---- Registrar movimiento de producto (desde el panel) ----
  const handleRegisterMovementProducto = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedProductoId || !movProducto.ubicacion_id || !movProducto.cantidad) return;

    const esEntrada = movProducto.tipo === 'ENTRADA' || movProducto.tipo === 'DEVOLUCION';
    const pago = esEntrada ? parsePagoKey(movProducto.pagado_desde_metodo_caja_id) : { cuentaId: null as number | null, monedaId: null as number | null };
    const refMid = Number(productoSeleccionado?.moneda_id ?? MONEDA_BASE_ID);
    const tasaNum = parseFloat(movProducto.tasa_pago || '0');
    if (pago.cuentaId && (pago.monedaId !== MONEDA_BASE_ID || refMid !== MONEDA_BASE_ID) && !(tasaNum > 0)) {
      toast.error(`Indica la tasa de cambio: 1 ${codMonedaDe(pago.monedaId ?? refMid)} = ? COP.`);
      return;
    }

    const costoBruto = esEntrada && movProducto.costo_unitario ? parseFloat(movProducto.costo_unitario) : undefined;
    const pctDesc = esEntrada && movProducto.descuento_porcentaje ? parseFloat(movProducto.descuento_porcentaje) : 0;
    const costoNeto = costoBruto !== undefined && pctDesc > 0
      ? parseFloat((costoBruto * (1 - pctDesc / 100)).toFixed(2))
      : costoBruto;
    const notaDesc = costoBruto !== undefined && pctDesc > 0
      ? `Descuento pronto pago/mayor: ${pctDesc}% (Lista: ${codMonedaDe(productoSeleccionado?.moneda_id)} ${costoBruto.toLocaleString('es-CO')} → Neto: ${costoNeto?.toLocaleString('es-CO')})`
      : '';

    try {
      setSavingMovProd(true);
      await inventarioService.crearMovimientoProducto({
        producto_id: selectedProductoId,
        ubicacion_id: parseInt(movProducto.ubicacion_id),
        tipo: movProducto.tipo as any,
        cantidad: parseFloat(movProducto.cantidad),
        costo_unitario: costoNeto,
        pagado_desde_metodo_caja_id:
          movProducto.tipo === 'ENTRADA' && pago.cuentaId ? pago.cuentaId : undefined,
        moneda_pago_id:
          movProducto.tipo === 'ENTRADA' && pago.cuentaId ? (pago.monedaId ?? undefined) : undefined,
        tasa_pago:
          movProducto.tipo === 'ENTRADA' && pago.cuentaId && tasaNum > 0 ? tasaNum : undefined,
        // "La llevada": flete/aduana (solo en compras de contado)
        llevada: movProducto.tipo === 'ENTRADA' && movProducto.llevada ? parseFloat(movProducto.llevada) : undefined,
        proveedor_nombre: movProducto.tipo === 'ENTRADA' && movProducto.proveedor_nombre ? movProducto.proveedor_nombre.trim() : undefined,
        cliente_nombre: movProducto.tipo === 'ENTRADA' && movProducto.cliente_nombre ? movProducto.cliente_nombre.trim() : undefined,
        observaciones: [movProducto.observaciones, notaDesc].filter(Boolean).join(' · ') || undefined,
      });

      setMovProducto({ ubicacion_id: '', tipo: 'ENTRADA', cantidad: '', costo_unitario: '', descuento_porcentaje: '', pagado_desde_metodo_caja_id: '', moneda_pago_id: '', tasa_pago: '', observaciones: '', llevada: '', proveedor_nombre: '', cliente_nombre: '' });
      fetchProductos();
      refrescarKardexProducto(selectedProductoId);
    } catch (error: any) {
      toast.error(error.response?.data?.detail || 'Error al registrar el movimiento.');
    } finally {
      setSavingMovProd(false);
    }
  };

  // ---- Nueva Pieza de Exhibición: nombre + precio (USD) + cantidad ----
  const handleCreatePieza = async (e: React.FormEvent) => {
    e.preventDefault();
    const nombre = newPieza.nombre.trim();
    if (!nombre) return;
    const precioUsd = parseFloat(newPieza.precio_usd || '0');
    if (!(precioUsd > 0)) {
      toast.error('Indica el precio de la pieza en dólares.');
      return;
    }
    const idTipo = tiposProducto.find(t => quitarAcentos(t.nombre).toUpperCase().includes('PIEZA UNICA'))?.id;
    if (!idTipo) {
      toast.error('No existe el tipo de producto "PIEZA ÚNICA". Ejecuta las migraciones de Alembic.');
      return;
    }
    const ubi = ubicacionesExhibicion[0];
    if (!ubi) {
      toast.error('Primero crea la ubicación "EXHIBICIÓN" en Catálogos (o ejecuta las migraciones).');
      return;
    }
    const usd = monedas.find(m => m.codigo === 'USD');
    setSavingPieza(true);
    try {
      const creado = await productosService.crearProducto({
        nombre: nombre.toUpperCase().trim(),
        tipo_producto_id: idTipo,
        descripcion: 'Pieza de exhibición',
        activo: true,
        // Pieza única de muestra: sin mínimo, no revende, precio en USD
        stock_minimo: 0,
        es_reventa: false,
        es_exhibicion: true,
        moneda_id: usd?.id ?? 1,
        // El precio en dólares ES el de venta (se sugiere en el cotizador)
        precio_costo_base: precioUsd,
        precio_venta_base: precioUsd,
      });
      const cant = parseFloat(newPieza.cantidad || '0') || 0;
      if (cant > 0 && creado.id) {
        await inventarioService.crearMovimientoProducto({
          producto_id: creado.id,
          ubicacion_id: ubi.id,
          tipo: 'ENTRADA',
          cantidad: cant,
          costo_unitario: precioUsd,
          observaciones: 'Alta de pieza de exhibición',
        });
      }
      if (fotoPieza && creado.id) {
        await subirAdjunto(fotoPieza, TIPO_ADJUNTO.PRODUCTO, creado.id);
      }
      setShowPiezaModal(false);
      setNewPieza({ nombre: '', precio_usd: '', cantidad: '1' });
      setFotoPieza(null);
      if (fotoPiezaPreview) URL.revokeObjectURL(fotoPiezaPreview);
      setFotoPiezaPreview(null);
      toast.success('Pieza de exhibición registrada.');
      fetchProductos();
    } catch (error: any) {
      toast.error(error.response?.data?.detail || 'Error al crear la pieza.');
    } finally {
      setSavingPieza(false);
    }
  };

  // ---- Orden de Producción de la pieza (fabricación real) ----
  const handleProducirPieza = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!producirPieza) return;
    setSavingProducir(true);
    try {
      const orden = await produccionService.crearOrden({
        estado: 'PENDIENTE',
        es_stock: true,
        producto_id: producirPieza.producto_id,
        fecha_inicio: new Date().toISOString().slice(0, 10),
      });
      setProducirPieza(null);
      toast.success(`Orden #${orden.id} creada. Gestiona sus etapas en Producción.`);
      navigate('/produccion');
    } catch (error: any) {
      toast.error(error.response?.data?.detail || 'Error al crear la orden de producción.');
    } finally {
      setSavingProducir(false);
    }
  };

  // ---- Vender la pieza: abre el cotizador con la pieza pre-cargada ----
  const venderPieza = (productoId: number) => {
    navigate(`/cotizaciones?pieza=${productoId}`);
  };

  // ---- Foto de la pieza (cámara o galería) ----
  const cameraInputRef = useRef<HTMLInputElement>(null);
  const galleryInputRef = useRef<HTMLInputElement>(null);
  const handleFotoPieza = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0] || null;
    if (fotoPiezaPreview) URL.revokeObjectURL(fotoPiezaPreview);
    setFotoPieza(file);
    setFotoPiezaPreview(file ? URL.createObjectURL(file) : null);
    e.target.value = '';
  };
  const quitarFotoPieza = () => {
    if (fotoPiezaPreview) URL.revokeObjectURL(fotoPiezaPreview);
    setFotoPieza(null);
    setFotoPiezaPreview(null);
  };

  // ---- Vistas derivadas ----
  const stockMap = new Map<number, InventarioItem>();
  inventario.forEach(item => {
    if (!stockMap.has(item.material_id)) stockMap.set(item.material_id, item);
  });

  // Mapa material → categoría (desde el stock o desde el catálogo de materiales)
  const categoriaDeMaterial = (m: Material) =>
    categoriasMaterial.find(c => c.id === m.categoria_inventario_id)?.nombre ?? null;

  const filteredInv = [...materiales]
    .sort((a, b) => a.nombre.localeCompare(b.nombre, 'es'))
    .filter((mat) => mat.nombre.toLowerCase().includes(search.toLowerCase()))
    .filter((mat) => !filtroCatMaterial || mat.categoria_inventario_id === filtroCatMaterial)
    .filter((mat) =>
      !filtroDepto
        ? true
        : filtroDepto === 'GENERAL'
          ? !mat.departamento
          : mat.departamento === filtroDepto,
    );

  const stockMapProducto = new Map<number, ProductoInventarioItem>();
  invProductos.forEach(item => {
    if (!stockMapProducto.has(item.producto_id)) stockMapProducto.set(item.producto_id, item);
  });

  // Productos de REVENTA (colchones, neveras, etc.) — no los muebles fabricados
  const productosReventa = productos.filter(p => p.es_reventa);
  const filteredProductos = [...productosReventa]
    .sort((a, b) => a.nombre.localeCompare(b.nombre, 'es'))
    .filter((p) => p.nombre.toLowerCase().includes(searchProducto.toLowerCase()))
    .filter((p) => !filtroCatProducto || p.categoria_inventario_id === filtroCatProducto);

  // ---- Exhibición: piezas del showroom ----
  // Fuente: productos marcados es_exhibicion (aunque aún no tengan stock) +
  // productos del catálogo con stock en ubicaciones tipo "EXHIBIC...".
  const ubicacionesExhibicion = ubicaciones.filter(u => esNombreExhibicion(u.nombre));
  const stockExhPorProducto = new Map<number, ProductoInventarioItem[]>();
  invProductos.forEach(item => {
    if (esNombreExhibicion(item.ubicacion_nombre)) {
      const arr = stockExhPorProducto.get(item.producto_id) ?? [];
      arr.push(item);
      stockExhPorProducto.set(item.producto_id, arr);
    }
  });
  interface FilaExhibicion {
    producto_id: number;
    nombre: string;
    codigo?: string;
    fotoUrl?: string;
    precioUsd: number;
    stock: number;
    esExhibicion: boolean;
  }
  const buildFilaExhibicion = (p: Product, stock: number): FilaExhibicion => ({
    producto_id: p.id,
    nombre: p.nombre,
    codigo: p.codigo,
    fotoUrl: p.fotos?.[0]?.url,
    precioUsd: Number(p.precio_venta_base ?? p.precio_costo_base ?? 0),
    stock,
    esExhibicion: !!p.es_exhibicion,
  });
  const filasExhibicion: FilaExhibicion[] = [];
  const vistosExh = new Set<number>();
  for (const p of productosTodos) {
    if (!p.es_exhibicion) continue;
    const filas = stockExhPorProducto.get(p.id) ?? [];
    filasExhibicion.push(buildFilaExhibicion(p, filas.reduce((a, f) => a + (parseFloat(String(f.cantidad)) || 0), 0)));
    vistosExh.add(p.id);
  }
  for (const [pid, filas] of stockExhPorProducto) {
    if (vistosExh.has(pid)) continue;
    const p = productosTodos.find(x => x.id === pid);
    if (!p) continue;
    filasExhibicion.push(buildFilaExhibicion(p, filas.reduce((a, f) => a + (parseFloat(String(f.cantidad)) || 0), 0)));
  }
  const filasExhibicionFiltradas = filasExhibicion
    .filter(f => f.nombre.toLowerCase().includes(searchExhibicion.toLowerCase()))
    .sort((a, b) => a.nombre.localeCompare(b.nombre, 'es'));
  const piezasEnExhibicion = filasExhibicionFiltradas.reduce((a, f) => a + f.stock, 0);
  const valorExhibicion = filasExhibicionFiltradas.reduce((a, f) => a + f.stock * f.precioUsd, 0);

  const materialSeleccionado = materiales.find(m => m.id === selectedMaterialId);
  const productoSeleccionado =
    productosTodos.find(p => p.id === selectedProductoId) ??
    productos.find(p => p.id === selectedProductoId);

  const inputCls = "w-full bg-yeikar-tertiary/20 border border-yeikar-secondary-light/10 rounded-xl p-2.5 text-sm text-yeikar-neutral focus:outline-none focus:border-yeikar-primary font-mono";
  const selectCls = "w-full bg-yeikar-tertiary/20 border border-yeikar-secondary-light/10 rounded-xl p-2.5 text-sm text-yeikar-neutral focus:outline-none focus:border-yeikar-primary";

  const stockPill = (tieneStock: boolean, cantidad: number, isLowStock: boolean) => (
    <span
      className={`px-2.5 py-0.5 rounded-full text-xs font-bold whitespace-nowrap ${
        !tieneStock || isLowStock
          ? 'bg-red-50 text-red-700 border border-red-200'
          : 'bg-yeikar-tertiary text-yeikar-secondary border border-yeikar-secondary-light/15'
      }`}
    >
      {tieneStock ? cantidad.toLocaleString('es-ES') : '0'}
    </span>
  );

  const insumoStock = (m: Material) => {
    const s = stockMap.get(m.id);
    const c = s ? parseFloat(s.cantidad.toString()) : 0;
    return { s, c, low: c <= (m.stock_minimo ?? 8) };
  };

  const crudoColumns: DataColumn<Crudo>[] = [
    {
      key: 'nombre',
      header: 'Ítem',
      render: (c) => (
        <div className="flex items-center gap-2.5">
          {c.foto_url ? (
            <img src={c.foto_url} alt={c.nombre} className="w-9 h-9 rounded-lg object-cover border border-yeikar-secondary-light/15" />
          ) : (
            <span className="w-9 h-9 rounded-lg bg-yeikar-tertiary flex items-center justify-center text-yeikar-secondary/40 font-black">N</span>
          )}
          <span className="font-semibold text-yeikar-secondary">{c.nombre}</span>
        </div>
      ),
      mobilePrimary: true,
    },
    {
      key: 'cantidad',
      header: 'Stock',
      render: (c) => <span className="font-mono text-xs font-bold text-yeikar-secondary">{c.cantidad.toLocaleString('es-ES')}</span>,
      mobileLabel: 'Stock',
    },
    {
      key: 'acciones',
      header: '',
      render: (c) => (
        <div className="flex items-center gap-3 whitespace-nowrap">
          <button
            onClick={(e) => {
              e.stopPropagation();
              setAsignarCrudoTarget(c);
              setDetallePedidoInput('');
            }}
            className="text-xs font-bold text-yeikar-secondary hover:underline"
          >
            Asignar a pedido
          </button>
        </div>
      ),
    },
  ];

  const filteredCrudo = [...crudo].sort((a, b) =>
    a.nombre.toLowerCase().localeCompare(b.nombre.toLowerCase(), 'es'),
  );

  const insumoColumns: DataColumn<Material>[] = [
    {
      key: 'nombre',
      header: 'Material',
      render: (m) => (
        <div className="min-w-0">
          <span className="font-semibold text-yeikar-secondary block truncate">{m.nombre}</span>
          {m.largo_cm != null && m.ancho_cm != null && (
            <span className="text-[10px] font-mono text-yeikar-neutral/40">{m.largo_cm}×{m.ancho_cm} cm</span>
          )}
        </div>
      ),
      mobilePrimary: true,
    },
    {
      key: 'categoria',
      header: 'Categoría',
      render: (m) => {
        const nombre = categoriaDeMaterial(m);
        return nombre ? (
          <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-yeikar-tertiary text-yeikar-secondary/70 border border-yeikar-secondary-light/10 whitespace-nowrap">{nombre}</span>
        ) : (
          <span className="text-xs italic text-yeikar-neutral/30">—</span>
        );
      },
      mobileLabel: 'Categoría',
    },
    {
      key: 'departamento',
      header: 'Departamento',
      render: (m) => {
        const label = labelDepartamento(m.departamento);
        return label ? (
          <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-yeikar-primary/10 text-yeikar-primary border border-yeikar-primary/20 whitespace-nowrap">{label}</span>
        ) : (
          <span className="text-xs italic text-yeikar-neutral/30">General</span>
        );
      },
      mobileLabel: 'Departamento',
    },
    {
      key: 'ubicacion',
      header: 'Ubicación',
      render: (m) =>
        insumoStock(m).s?.ubicacion_nombre || (
          <span className="text-xs italic text-yeikar-neutral/30">Sin stock</span>
        ),
      mobileLabel: 'Ubicación',
    },
    {
      key: 'stock',
      header: 'Stock Actual',
      render: (m) => {
        const { s, c, low } = insumoStock(m);
        return stockPill(!!s, c, low);
      },
      mobileHidden: true,
    },
    {
      key: 'min',
      header: 'Stock Mín.',
      render: (m) => (
        <span className="font-mono text-xs text-yeikar-neutral/60">{(m.stock_minimo ?? 8).toLocaleString('es-ES')}</span>
      ),
      mobileLabel: 'Mínimo',
    },
    {
      key: 'unidad',
      header: 'Unidad',
      render: (m) => <span className="font-mono text-xs text-yeikar-neutral/60">{m.unidad_medida?.abreviatura || 'Unid'}</span>,
      mobileLabel: 'Unidad',
    },
    {
      key: 'precio',
      header: 'Precio Unitario',
      render: (m) => (
        <span className="font-mono text-xs text-yeikar-neutral/60">
          {m.costo_base > 0 ? m.costo_base.toLocaleString('es-ES') : <span className="italic text-yeikar-neutral/30">Sin precio</span>}
        </span>
      ),
      mobileLabel: 'Precio',
    },
  ];

  const productoStock = (p: Product) => {
    const s = stockMapProducto.get(p.id);
    const c = s ? parseFloat(s.cantidad.toString()) : 0;
    return { s, c, low: c <= (p.stock_minimo ?? 8) };
  };

  /** Prefijo del precio según la moneda declarada del producto ($ para COP). */
  const simboloMonedaProducto = (p: Product) =>
    p.moneda && p.moneda.codigo !== 'COP' ? `${p.moneda.simbolo} ` : '$';

  const productoColumns: DataColumn<Product>[] = [
    {
      key: 'nombre',
      header: 'Producto',
      render: (p) => <span className="font-semibold text-yeikar-secondary">{p.nombre}</span>,
      mobilePrimary: true,
    },
    {
      key: 'codigo',
      header: 'Código',
      render: (p) => <span className="font-mono text-xs text-yeikar-neutral/60">{p.codigo || '—'}</span>,
      mobileLabel: 'Código',
    },
    {
      key: 'ubicacion',
      header: 'Ubicación',
      render: (p) =>
        productoStock(p).s?.ubicacion_nombre || (
          <span className="text-xs italic text-yeikar-neutral/30">Sin stock</span>
        ),
      mobileLabel: 'Ubicación',
    },
    {
      key: 'stock',
      header: 'Stock Actual',
      render: (p) => {
        const { s, c, low } = productoStock(p);
        return stockPill(!!s, c, low);
      },
      mobileHidden: true,
    },
    {
      key: 'min',
      header: 'Stock Mín.',
      render: (p) => (
        <span className="font-mono text-xs text-yeikar-neutral/60">{(p.stock_minimo ?? 8).toLocaleString('es-ES')}</span>
      ),
      mobileLabel: 'Mínimo',
    },
    {
      key: 'precio',
      header: 'Último Precio',
      render: (p) => {
        const { s } = productoStock(p);
        return s?.costo_promedio ? (
          <span className="font-mono text-xs text-yeikar-neutral/60">{simboloMonedaProducto(p)}{Number(s.costo_promedio).toLocaleString('es-ES')}</span>
        ) : (
          <span className="italic text-yeikar-neutral/30">—</span>
        );
      },
      mobileLabel: 'Último precio',
    },
  ];

  /** Valor de una pieza de exhibición (cantidad × precio USD de referencia). */
  const valorFilaExhibicion = (f: FilaExhibicion) => f.stock * f.precioUsd;

  const exhibicionColumns: DataColumn<FilaExhibicion>[] = [
    {
      key: 'pieza',
      header: 'Pieza',
      render: (f) => (
        <div className="flex items-center gap-2.5 min-w-0">
          {f.fotoUrl ? (
            <img src={f.fotoUrl} alt={f.nombre} className="w-9 h-9 rounded-lg object-cover border border-yeikar-secondary-light/15" />
          ) : (
            <span className="w-9 h-9 rounded-lg bg-yeikar-tertiary flex items-center justify-center text-yeikar-secondary/40 font-black shrink-0">P</span>
          )}
          <div className="min-w-0">
            <span className="font-semibold text-yeikar-secondary block truncate">{f.nombre}</span>
            {f.codigo && <span className="text-[10px] font-mono text-yeikar-neutral/40">{f.codigo}</span>}
          </div>
        </div>
      ),
      mobilePrimary: true,
    },
    {
      key: 'precio',
      header: 'Precio (USD)',
      render: (f) =>
        f.precioUsd > 0 ? (
          <span className="font-mono text-xs text-yeikar-neutral/60">US$ {f.precioUsd.toLocaleString('es-ES')}</span>
        ) : (
          <span className="text-xs italic text-yeikar-neutral/30">—</span>
        ),
      mobileLabel: 'Precio',
    },
    {
      key: 'cantidad',
      header: 'Cantidad',
      render: (f) =>
        f.stock > 0 ? (
          <span className="font-mono text-xs font-bold text-yeikar-secondary">{f.stock.toLocaleString('es-ES')}</span>
        ) : (
          <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-red-50 text-red-700 border border-red-200 whitespace-nowrap">Sin stock</span>
        ),
      mobileLabel: 'Cantidad',
    },
    {
      key: 'valor',
      header: 'Valor',
      render: (f) => (
        <span className="font-mono text-xs font-bold text-yeikar-secondary">US$ {valorFilaExhibicion(f).toLocaleString('es-ES')}</span>
      ),
      mobileLabel: 'Valor',
    },
  ];

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
        <div>
          <h1 className="text-2xl sm:text-3xl font-black font-headline text-yeikar-neutral tracking-tight">
            Inventario
          </h1>
          <p className="text-yeikar-neutral/60 mt-1">
            Controla existencias de insumos, productos de reventa y piezas de exhibición, con alertas de stock crítico.
          </p>
        </div>

        <div className="flex items-center gap-3">
          {tab === 'insumos' && (
            <button
              onClick={() => setShowMaterialModal(true)}
              className="bg-yeikar-primary hover:bg-yeikar-primary-dark text-yeikar-neutral px-5 py-2.5 rounded-xl font-bold font-headline shadow-sm hover:shadow transition-all flex items-center gap-2 text-sm"
            >
               Nuevo Material
            </button>
          )}
          {tab === 'sobrantes' && (
            <button
              onClick={() => setShowSobranteModal(true)}
              className="bg-yeikar-primary hover:bg-yeikar-primary-dark text-yeikar-neutral px-5 py-2.5 rounded-xl font-bold font-headline shadow-sm hover:shadow transition-all flex items-center gap-2 text-sm"
            >
               Registrar Sobrante
            </button>
          )}
          {tab === 'productos' && (
            <button
              onClick={() => setShowProductoModal(true)}
              className="bg-yeikar-primary hover:bg-yeikar-primary-dark text-yeikar-neutral px-5 py-2.5 rounded-xl font-bold font-headline shadow-sm hover:shadow transition-all flex items-center gap-2 text-sm"
            >
               Nuevo Producto de Reventa
            </button>
          )}
          {tab === 'exhibicion' && (
            <button
              onClick={() => setShowPiezaModal(true)}
              className="bg-yeikar-primary hover:bg-yeikar-primary-dark text-yeikar-neutral px-5 py-2.5 rounded-xl font-bold font-headline shadow-sm hover:shadow transition-all flex items-center gap-2 text-sm"
            >
              Nueva Pieza
            </button>
          )}
          {tab === 'crudo' && (
            <div className="flex items-center gap-2">
              <button
                onClick={() => setShowCrudoModal(true)}
                className="bg-yeikar-secondary hover:bg-yeikar-secondary/90 text-white px-5 py-2.5 rounded-xl font-bold font-headline shadow-sm hover:shadow transition-all flex items-center gap-2 text-sm"
              >
                Nuevo en Crudo
              </button>
            </div>
          )}
        </div>
      </div>

      {/* Tabs */}
      <div className="flex gap-2 border-b border-yeikar-secondary-light/10 overflow-x-auto scroll-touch whitespace-nowrap">
        {([
          ['insumos', 'Insumos (Materiales)'],
          ['sobrantes', 'Sobrantes de Láminas'],
          ['productos', 'Productos de Reventa'],
          ['exhibicion', 'Productos terminados'],
          ['crudo', 'Productos en Crudo'],
        ] as [Tab, string][]).map(([key, label]) => (
          <button
            key={key}
            onClick={() => setTab(key)}
            className={`px-5 py-2.5 rounded-t-xl font-headline font-bold text-sm transition-colors ${
              tab === key
                ? 'bg-yeikar-primary/10 text-yeikar-primary border-b-2 border-yeikar-primary'
                : 'text-yeikar-neutral/50 hover:text-yeikar-neutral'
            }`}
          >
            {label}
            {key === 'insumos' && alertas.length > 0 && (
              <span className="ml-2 bg-red-500 text-white text-[10px] font-bold px-1.5 py-0.5 rounded-full">{alertas.length}</span>
            )}
            {key === 'productos' && alertasProductos.length > 0 && (
              <span className="ml-2 bg-red-500 text-white text-[10px] font-bold px-1.5 py-0.5 rounded-full">{alertasProductos.length}</span>
            )}
            {key === 'exhibicion' && filasExhibicion.length > 0 && (
              <span className="ml-2 bg-yeikar-secondary/10 text-yeikar-secondary text-[10px] font-bold px-1.5 py-0.5 rounded-full">{filasExhibicion.length}</span>
            )}
            {key === 'sobrantes' && sobrantes.length > 0 && (
              <span className="ml-2 bg-yeikar-secondary/10 text-yeikar-secondary text-[10px] font-bold px-1.5 py-0.5 rounded-full">{sobrantes.length}</span>
            )}
          </button>
        ))}
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
        <div className="bg-white border border-yeikar-secondary-light/10 rounded-2xl p-5 shadow-sm relative overflow-hidden">
          <div className="absolute top-0 left-0 right-0 h-1 bg-yeikar-secondary-light/20" />
          <p className="text-xs font-mono uppercase tracking-widest text-yeikar-neutral/50 mb-1">
            {tab === 'insumos'
              ? 'Materiales Registrados'
              : tab === 'sobrantes'
                ? 'Sobrantes Disponibles'
                : tab === 'crudo'
                  ? 'Productos en Crudo'
                  : tab === 'exhibicion'
                    ? 'Piezas en Exhibición'
                    : 'Productos Registrados'}
          </p>
          <p className="text-3xl font-black font-headline text-yeikar-secondary">
            {tab === 'insumos' ? materiales.length : tab === 'sobrantes' ? sobrantes.length : tab === 'crudo' ? crudo.length : tab === 'exhibicion' ? piezasEnExhibicion.toLocaleString('es-ES') : productosReventa.length}
          </p>
        </div>

        <div className="bg-white border border-yeikar-secondary-light/10 rounded-2xl p-5 shadow-sm relative overflow-hidden">
          <div className={`absolute top-0 left-0 right-0 h-1 ${tab === 'exhibicion' ? 'bg-yeikar-primary' : 'bg-red-300'}`} />
          {tab === 'exhibicion' ? (
            <>
              <p className="text-xs font-mono uppercase tracking-widest text-yeikar-neutral/50 mb-1">Valor del Inventario en Exhibición</p>
              <p className="text-3xl font-black font-headline text-yeikar-primary">${valorExhibicion.toLocaleString('es-ES')}</p>
            </>
          ) : (
            <>
              <p className="text-xs font-mono uppercase tracking-widest text-yeikar-neutral/50 mb-1">Alertas de Stock Bajo</p>
              <p className="text-3xl font-black font-headline text-red-500">
                {tab === 'insumos' ? alertas.length : tab === 'crudo' ? 0 : tab === 'sobrantes' ? 0 : alertasProductos.length}
              </p>
            </>
          )}
        </div>

        <div className="bg-white border border-yeikar-secondary-light/10 rounded-2xl p-5 shadow-sm relative overflow-hidden">
          <div className="absolute top-0 left-0 right-0 h-1 bg-yeikar-secondary-light/20" />
          <p className="text-xs font-mono uppercase tracking-widest text-yeikar-neutral/50 mb-1">Bodegas Activas</p>
          <p className="text-3xl font-black font-headline text-yeikar-secondary">{ubicaciones.length}</p>
        </div>
      </div>

      {/* Main Layout */}
      <div className="flex flex-col lg:flex-row gap-6">

        <div className="flex-1 bg-white border border-yeikar-secondary-light/10 rounded-3xl shadow-sm overflow-hidden">
          <div className="p-5 border-b border-yeikar-secondary-light/5 space-y-3">
            <div className="relative w-full sm:w-72">
              <input
                type="text"
                placeholder={tab === 'insumos' ? 'Buscar material...' : tab === 'sobrantes' ? 'Buscar sobrante...' : tab === 'exhibicion' ? 'Buscar pieza...' : 'Buscar producto...'}
                value={tab === 'productos' ? searchProducto : tab === 'exhibicion' ? searchExhibicion : search}
                onChange={(e) => tab === 'productos' ? setSearchProducto(e.target.value) : tab === 'exhibicion' ? setSearchExhibicion(e.target.value) : setSearch(e.target.value)}
                className="w-full bg-yeikar-tertiary/30 border border-yeikar-secondary-light/10 rounded-xl pl-10 pr-4 py-2 text-sm text-yeikar-neutral placeholder-yeikar-neutral/40 focus:outline-none focus:border-yeikar-primary"
              />
              <svg className="absolute left-3 top-3 w-4 h-4 text-yeikar-neutral/40" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
              </svg>
            </div>

            {/* Filtro por departamento del taller (insumos) */}
            {tab === 'insumos' && (
              <div className="flex flex-wrap gap-1.5">
                <button
                  onClick={() => setFiltroDepto(null)}
                  className={`text-[11px] font-bold px-3 py-1 rounded-full border transition-colors ${
                    !filtroDepto
                      ? 'bg-yeikar-primary text-white border-yeikar-primary'
                      : 'bg-white text-yeikar-neutral/60 border-yeikar-secondary-light/15 hover:border-yeikar-primary/30'
                  }`}
                >
                  Todos
                </button>
                {DEPARTAMENTOS.map((d) => (
                  <button
                    key={d.valor}
                    onClick={() => setFiltroDepto(filtroDepto === d.valor ? null : d.valor)}
                    className={`text-[11px] font-bold px-3 py-1 rounded-full border transition-colors ${
                      filtroDepto === d.valor
                        ? 'bg-yeikar-primary text-white border-yeikar-primary'
                        : 'bg-white text-yeikar-neutral/60 border-yeikar-secondary-light/15 hover:border-yeikar-primary/30'
                    }`}
                  >
                    {d.label}
                  </button>
                ))}
                <button
                  onClick={() => setFiltroDepto(filtroDepto === 'GENERAL' ? null : 'GENERAL')}
                  className={`text-[11px] font-bold px-3 py-1 rounded-full border transition-colors ${
                    filtroDepto === 'GENERAL'
                      ? 'bg-yeikar-primary text-white border-yeikar-primary'
                      : 'bg-white text-yeikar-neutral/60 border-yeikar-secondary-light/15 hover:border-yeikar-primary/30'
                  }`}
                >
                  General
                </button>
              </div>
            )}

            {/* Filtro por categoría (desglose del inventario) */}
            {tab === 'insumos' && categoriasMaterial.length > 0 && (
              <div className="flex flex-wrap gap-1.5">
                <button
                  onClick={() => setFiltroCatMaterial(null)}
                  className={`text-[11px] font-bold px-3 py-1 rounded-full border transition-colors ${
                    !filtroCatMaterial
                      ? 'bg-yeikar-secondary text-yeikar-tertiary border-yeikar-secondary'
                      : 'bg-white text-yeikar-neutral/60 border-yeikar-secondary-light/15 hover:border-yeikar-secondary/30'
                  }`}
                >
                  Todos
                </button>
                {categoriasMaterial.map((c) => (
                  <button
                    key={c.id}
                    onClick={() => setFiltroCatMaterial(filtroCatMaterial === c.id ? null : c.id)}
                    className={`text-[11px] font-bold px-3 py-1 rounded-full border transition-colors ${
                      filtroCatMaterial === c.id
                        ? 'bg-yeikar-secondary text-yeikar-tertiary border-yeikar-secondary'
                        : 'bg-white text-yeikar-neutral/60 border-yeikar-secondary-light/15 hover:border-yeikar-secondary/30'
                    }`}
                  >
                    {c.nombre}
                  </button>
                ))}
              </div>
            )}
            {tab === 'productos' && categoriasProducto.length > 0 && (
              <div className="flex flex-wrap gap-1.5">
                <button
                  onClick={() => setFiltroCatProducto(null)}
                  className={`text-[11px] font-bold px-3 py-1 rounded-full border transition-colors ${
                    !filtroCatProducto
                      ? 'bg-yeikar-secondary text-yeikar-tertiary border-yeikar-secondary'
                      : 'bg-white text-yeikar-neutral/60 border-yeikar-secondary-light/15 hover:border-yeikar-secondary/30'
                  }`}
                >
                  Todos
                </button>
                {categoriasProducto.map((c) => (
                  <button
                    key={c.id}
                    onClick={() => setFiltroCatProducto(filtroCatProducto === c.id ? null : c.id)}
                    className={`text-[11px] font-bold px-3 py-1 rounded-full border transition-colors ${
                      filtroCatProducto === c.id
                        ? 'bg-yeikar-secondary text-yeikar-tertiary border-yeikar-secondary'
                        : 'bg-white text-yeikar-neutral/60 border-yeikar-secondary-light/15 hover:border-yeikar-secondary/30'
                    }`}
                  >
                    {c.nombre}
                  </button>
                ))}
              </div>
            )}
          </div>

          {loading ? (
            <div className="flex flex-col items-center justify-center py-20 space-y-4">
              <div className="w-10 h-10 border-4 border-yeikar-primary border-t-transparent rounded-full animate-spin"></div>
              <p className="text-xs font-mono text-yeikar-neutral/60">Cargando existencias...</p>
            </div>
          ) : tab === 'insumos' ? (
            <ResponsiveDataTable
              columns={insumoColumns}
              rows={filteredInv}
              rowKey={(m) => m.id}
              cardBadge={(m) => {
                const { s, c, low } = insumoStock(m);
                return stockPill(!!s, c, low);
              }}
              onRowClick={(m) => handleOpenMaterial(m)}
              empty={
                <div className="p-8 text-center text-sm italic text-yeikar-neutral/40">
                  {search ? `Sin resultados para "${search}"` : 'No hay materiales registrados. Haz clic en "Nuevo Material" para comenzar.'}
                </div>
              }
            />
          ) : tab === 'sobrantes' ? (
            <div className="p-5">
              <p className="text-xs text-yeikar-neutral/50 mb-4">
                Retazos de láminas (MDF, melamina, espuma...) que pueden usarse en cortes futuros.
                Al abrir una lámina nueva para un corte, el pedazo restante se registra aquí automáticamente.
              </p>
              {sobrantes.length === 0 ? (
                <div className="p-8 text-center text-sm italic text-yeikar-neutral/40">
                  No hay sobrantes disponibles. Se generan al consumir cortes de láminas nuevas o regístralos con "Registrar Sobrante".
                </div>
              ) : (
                <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
                  {sobrantes
                    .filter(s => (s.material_nombre || '').toLowerCase().includes(search.toLowerCase()))
                    .map((s) => (
                      <div key={s.id} className="border border-yeikar-secondary-light/10 rounded-2xl p-4 space-y-2 bg-white">
                        <div className="flex items-start justify-between gap-2">
                          <div className="min-w-0">
                            <p className="font-semibold text-sm text-yeikar-secondary truncate" title={s.material_nombre || ''}>{s.material_nombre}</p>
                            <p className="text-[10px] font-mono text-yeikar-neutral/40">{s.ubicacion_nombre}</p>
                          </div>
                          <span className="shrink-0 text-[10px] font-bold px-2 py-0.5 rounded-full bg-emerald-50 text-emerald-700 border border-emerald-200">DISPONIBLE</span>
                        </div>
                        <p className="font-mono font-black text-lg text-yeikar-secondary">{s.largo_cm} × {s.ancho_cm} <span className="text-xs font-bold text-yeikar-neutral/40">cm</span></p>
                        <p className="text-[10px] font-mono text-yeikar-neutral/40">Área: {(s.area_cm2 / 10000).toFixed(2)} m²</p>
                        {s.observaciones && <p className="text-[11px] text-yeikar-neutral/50 italic truncate" title={s.observaciones}>{s.observaciones}</p>}
                        <div className="flex gap-2 pt-1">
                          <button
                            onClick={() => handleDeshecharSobrante(s)}
                            className="flex-1 text-[11px] font-bold py-1.5 rounded-lg bg-yeikar-tertiary text-yeikar-secondary hover:bg-yeikar-secondary-light/20 transition-colors"
                          >
                            Deshechar
                          </button>
                          <button
                            onClick={() => handleEliminarSobrante(s)}
                            className="flex-1 text-[11px] font-bold py-1.5 rounded-lg bg-yeikar-tertiary text-red-600 hover:bg-red-50 transition-colors"
                          >
                            Eliminar
                          </button>
                        </div>
                      </div>
                    ))}
                </div>
              )}
            </div>
          ) : tab === 'exhibicion' ? (
            <>
              {ubicacionesExhibicion.length === 0 && (
                <div className="m-5 mb-0 rounded-xl bg-amber-50 border border-amber-200 text-amber-800 text-xs px-4 py-3">
                  No existe una ubicación de exhibición. Créala en Catálogos → Ubicaciones con el nombre <b>EXHIBICIÓN</b> (o ejecuta las migraciones de Alembic).
                </div>
              )}
              <ResponsiveDataTable
                columns={exhibicionColumns}
                rows={filasExhibicionFiltradas}
                rowKey={(f) => f.producto_id}
                cardBadge={(f) =>
                  f.stock > 0 ? (
                    <span className="font-mono text-xs font-bold text-yeikar-secondary">×{f.stock.toLocaleString('es-ES')}</span>
                  ) : (
                    <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-red-50 text-red-700 border border-red-200">Sin stock</span>
                  )
                }
                onRowClick={(f) => handleOpenProducto({ id: f.producto_id })}
                empty={
                  <div className="p-8 text-center text-sm italic text-yeikar-neutral/40">
                    {searchExhibicion
                      ? `Sin resultados para "${searchExhibicion}"`
                      : 'No hay piezas en exhibición. Usa "Nueva Pieza" para registrar una (nombre, precio en dólares y cantidad).'}
                  </div>
                }
              />
            </>
          ) : tab === 'crudo' ? (
            <ResponsiveDataTable
              columns={crudoColumns}
              rows={filteredCrudo}
              rowKey={(c) => c.id}
              cardBadge={(c) => (
                <span className="font-mono text-xs font-bold text-yeikar-secondary">{c.cantidad.toLocaleString('es-ES')}</span>
              )}
              empty={
                <div className="p-8 text-center text-sm italic text-yeikar-neutral/40">
                  No hay ítems en crudo. Crea uno con "Nuevo en Crudo"". Luego usa "Nueva Producción" para registrar su fabricación y consumos.
                </div>
              }
            />
          ) : (
            <ResponsiveDataTable
              columns={productoColumns}
              rows={filteredProductos}
              rowKey={(p) => p.id}
              cardBadge={(p) => {
                const { s, c, low } = productoStock(p);
                return stockPill(!!s, c, low);
              }}
              onRowClick={(p) => handleOpenProducto(p)}
              empty={
                <div className="p-8 text-center text-sm italic text-yeikar-neutral/40">
                  {searchProducto ? `Sin resultados para "${searchProducto}"` : 'No hay productos de reventa (colchones, neveras, etc.). Marca un producto como "Reventa" en Productos.'}
                </div>
              }
            />
          )}
        </div>

        {/* ================= PANEL LATERAL (Insumo: editar + movimiento + historial) ================= */}
        {tab === 'insumos' && selectedMaterialId && materialSeleccionado && (
          <div className="w-full lg:w-[28rem] bg-white border border-yeikar-secondary-light/10 rounded-3xl p-5 shadow-sm space-y-5 flex flex-col max-h-[800px] overflow-hidden">
            <div className="flex items-start justify-between border-b border-yeikar-secondary-light/5 pb-3">
              <div>
                <span className="text-[10px] font-mono font-bold text-yeikar-neutral/40">DETALLE DE INSUMO</span>
                <h3 className="font-headline font-black text-yeikar-secondary text-base truncate max-w-[240px]" title={materialSeleccionado.nombre}>
                  {materialSeleccionado.nombre}
                </h3>
              </div>
              <button
                onClick={() => setSelectedMaterialId(null)}
                className="p-1 hover:bg-yeikar-tertiary rounded-lg text-yeikar-neutral/40 hover:text-yeikar-neutral/70 transition-colors"
              >
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>

            <div className="flex-1 overflow-y-auto space-y-5 pr-1">
              {/* Editar insumo */}
              <form onSubmit={handleSaveMaterial} className="space-y-3 bg-yeikar-tertiary/10 border border-yeikar-secondary-light/5 rounded-2xl p-4">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-headline font-black uppercase tracking-wider text-yeikar-secondary">Editar Insumo</span>
                  <span className="text-[10px] font-mono text-yeikar-neutral/40">{materialSeleccionado.unidad_medida?.nombre || ''}</span>
                </div>
                <div className="space-y-1">
                  <label className="text-xs font-bold text-yeikar-secondary">Nombre</label>
                  <input type="text" required value={editMaterial.nombre} onChange={(e) => setEditMaterial(p => ({ ...p, nombre: e.target.value }))} className={inputCls.replace('font-mono', '').replace(' uppercase', '')} />
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <div className="space-y-1">
                    <label className="text-xs font-bold text-yeikar-secondary">Precio Unitario</label>
                    <input type="number" min="0" step="0.01" value={editMaterial.costo_base} onChange={(e) => setEditMaterial(p => ({ ...p, costo_base: e.target.value }))} className={inputCls} />
                  </div>
                  <div className="space-y-1">
                    <label className="text-xs font-bold text-yeikar-secondary">Stock Mínimo</label>
                    <input type="number" min="0" step="0.5" value={editMaterial.stock_minimo} onChange={(e) => setEditMaterial(p => ({ ...p, stock_minimo: e.target.value }))} className={inputCls} />
                  </div>
                </div>
                <div className="space-y-1">
                  <label className="text-xs font-bold text-yeikar-secondary">Categoría de Inventario</label>
                  <SearchSelect
                    value={editMaterial.categoria_inventario_id}
                    onChange={(v) => setEditMaterial(p => ({ ...p, categoria_inventario_id: String(v) }))}
                    options={[{ value: '', label: 'Sin categoría' }, ...categoriasMaterial.map((c) => ({ value: c.id, label: c.nombre }))]}
                    placeholder="Sin categoría..."
                  />
                </div>
                <div className="space-y-1">
                  <label className="text-xs font-bold text-yeikar-secondary">Departamento</label>
                  <SearchSelect
                    value={editMaterial.departamento ?? ''}
                    onChange={(v) => setEditMaterial(p => ({ ...p, departamento: v ? String(v) : null }))}
                    options={[
                      { value: '', label: 'General (sin departamento)' },
                      ...DEPARTAMENTOS.map((d) => ({ value: d.valor, label: d.label })),
                    ]}
                    placeholder="General..."
                  />
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <div className="space-y-1">
                    <label className="text-xs font-bold text-yeikar-secondary">Largo Lámina (cm)</label>
                    <input type="number" min="0" step="0.01" placeholder="—" value={editMaterial.largo_cm} onChange={(e) => setEditMaterial(p => ({ ...p, largo_cm: e.target.value }))} className={inputCls} />
                  </div>
                  <div className="space-y-1">
                    <label className="text-xs font-bold text-yeikar-secondary">Ancho Lámina (cm)</label>
                    <input type="number" min="0" step="0.01" placeholder="—" value={editMaterial.ancho_cm} onChange={(e) => setEditMaterial(p => ({ ...p, ancho_cm: e.target.value }))} className={inputCls} />
                  </div>
                </div>
                {editMaterial.largo_cm && editMaterial.ancho_cm ? (
                  <p className="text-[10px] text-yeikar-neutral/50">
                    Material laminar: admite consumos por cortes y sobrantes ({(parseFloat(editMaterial.largo_cm) * parseFloat(editMaterial.ancho_cm) / 10000).toFixed(2)} m² por lámina).
                  </p>
                ) : (
                  <p className="text-[10px] font-semibold text-amber-700 bg-amber-50 border border-amber-200 rounded-lg px-2.5 py-1.5">
                    Sin dimensiones: no podrá pedirse por láminas completas ni cortarse en producción. Llena largo × ancho para habilitarlo.
                  </p>
                )}
                <button
                  type="submit"
                  disabled={savingEdit}
                  className="w-full py-2 bg-yeikar-secondary hover:bg-yeikar-secondary-light text-white rounded-xl font-bold font-headline text-sm transition-colors disabled:opacity-50"
                >
                  {savingEdit ? 'Guardando...' : 'Guardar Cambios'}
                </button>
              </form>

              {/* Registrar movimiento */}
              <form onSubmit={handleRegisterMovement} className="space-y-3 bg-yeikar-tertiary/10 border border-yeikar-secondary-light/5 rounded-2xl p-4">
                <span className="text-xs font-headline font-black uppercase tracking-wider text-yeikar-primary">Registrar Movimiento</span>
                <div className="space-y-1">
                  <label className="text-xs font-bold text-yeikar-secondary">Tipo Movimiento</label>
                  <select value={movMaterial.tipo} onChange={(e) => setMovMaterial(p => ({ ...p, tipo: e.target.value }))} className={selectCls}>
                    {TIPOS_MOVIMIENTO.map(t => (
                      <option key={t} value={t}>
                        {t === 'ENTRADA' ? 'ENTRADA (Compra/Carga)' : t === 'SALIDA' ? 'SALIDA (Consumo/Despacho)' : t === 'AJUSTE' ? 'AJUSTE (Inventario físico)' : t === 'DAÑO' ? 'DAÑO (Mermas)' : 'DEVOLUCION'}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="space-y-1">
                  <label className="text-xs font-bold text-yeikar-secondary">Ubicación / Almacén</label>
                  <SearchSelect
                    value={movMaterial.ubicacion_id}
                    onChange={(v) => setMovMaterial(p => ({ ...p, ubicacion_id: String(v) }))}
                    options={ubicaciones.map((u) => ({ value: u.id, label: u.nombre }))}
                    placeholder="Seleccione una ubicación"
                  />
                </div>
                <div className="space-y-1">
                  <label className="text-xs font-bold text-yeikar-secondary">Cantidad</label>
                  <input type="number" step="0.01" min="0.01" required placeholder="0.00" value={movMaterial.cantidad} onChange={(e) => setMovMaterial(p => ({ ...p, cantidad: e.target.value }))} className={inputCls} />
                </div>
                {(movMaterial.tipo === 'ENTRADA' || movMaterial.tipo === 'DEVOLUCION') && (
                  <div className="space-y-3 bg-white/40 p-3 rounded-xl border border-yeikar-secondary-light/10">
                    <div className="space-y-1">
                      <label className="text-xs font-bold text-yeikar-secondary">
                        Precio Unitario (Lista) <span className="text-yeikar-neutral/40 font-normal">(Actualiza el precio al instante)</span>
                      </label>
                      <input type="number" step="0.01" min="0" placeholder="0.00" value={movMaterial.costo_unitario} onChange={(e) => setMovMaterial(p => ({ ...p, costo_unitario: e.target.value }))} className={inputCls} />
                    </div>

                    {/* "La llevada" */}
                    <div className="space-y-1">
                      <label className="text-xs font-bold text-yeikar-secondary">
                        La Llevada<span className="text-yeikar-neutral/40 font-normal">(opcional — genera gasto desde la cuenta)</span>
                      </label>
                      <input type="number" step="0.01" min="0" placeholder="0.00" value={movMaterial.llevada} onChange={(e) => setMovMaterial(p => ({ ...p, llevada: e.target.value }))} className={inputCls} />
                    </div>

                    {/* Proveedor: dónde se compró (opcional, texto libre) */}
                    <div className="space-y-1">
                      <label className="text-xs font-bold text-yeikar-secondary">
                        Proveedor <span className="text-yeikar-neutral/40 font-normal">(dónde se compró — opcional)</span>
                      </label>
                      <input
                        type="text"
                        value={movMaterial.proveedor_nombre}
                        onChange={(e) => setMovMaterial(p => ({ ...p, proveedor_nombre: e.target.value }))}
                        placeholder="Ej. Distribuidora Maderas C.A."
                        className={inputCls}
                      />
                    </div>

                    {/* Cliente: material comprado para un cliente específico (opcional, texto libre) */}
                    <div className="space-y-1">
                      <label className="text-xs font-bold text-yeikar-secondary">
                        Cliente <span className="text-yeikar-neutral/40 font-normal">(comprado para un cliente — opcional)</span>
                      </label>
                      <input
                        type="text"
                        value={movMaterial.cliente_nombre}
                        onChange={(e) => setMovMaterial(p => ({ ...p, cliente_nombre: e.target.value }))}
                        placeholder="Ej. Cliente sin registrar"
                        className={inputCls}
                      />
                    </div>

                    {movMaterial.tipo === 'ENTRADA' && parseFloat(movMaterial.costo_unitario || '0') > 0 && (
                      <div className="space-y-2 pt-1 border-t border-yeikar-secondary-light/10">
                        <div className="flex items-center justify-between">
                          <label className="text-xs font-bold text-yeikar-secondary">
                            % Descuento por pago de contado / al mayor
                          </label>
                          <span className="text-[10px] text-yeikar-neutral/40">Opcional</span>
                        </div>
                        <div className="relative">
                          <input
                            type="number"
                            min="0"
                            max="100"
                            step="0.1"
                            placeholder="Ej: 10"
                            value={movMaterial.descuento_porcentaje}
                            onChange={(e) => setMovMaterial(p => ({ ...p, descuento_porcentaje: e.target.value }))}
                            className={`${inputCls} pr-8`}
                          />
                          <span className="absolute right-3 top-1/2 -translate-y-1/2 text-xs font-bold text-yeikar-neutral/40">%</span>
                        </div>

                        {parseFloat(movMaterial.descuento_porcentaje || '0') > 0 && (() => {
                          const bruto = parseFloat(movMaterial.costo_unitario || '0') || 0;
                          const desc = parseFloat(movMaterial.descuento_porcentaje || '0') || 0;
                          const montoDesc = (bruto * desc) / 100;
                          const neto = Math.max(0, bruto - montoDesc);
                          return (
                            <div className="bg-emerald-50 border border-emerald-200 rounded-lg p-2 text-[11px] space-y-1 text-emerald-900">
                              <div className="flex justify-between">
                                <span>Precio lista:</span>
                                <span className="font-mono">${bruto.toLocaleString('es-CO', { minimumFractionDigits: 2 })}</span>
                              </div>
                              <div className="flex justify-between text-emerald-700 font-semibold">
                                <span>Descuento ({desc}%):</span>
                                <span className="font-mono">-${montoDesc.toLocaleString('es-CO', { minimumFractionDigits: 2 })}</span>
                              </div>
                              <div className="flex justify-between font-bold border-t border-emerald-200 pt-1 text-emerald-950">
                                <span>Costo neto a registrar:</span>
                                <span className="font-mono">${neto.toLocaleString('es-CO', { minimumFractionDigits: 2 })}</span>
                              </div>
                            </div>
                          );
                        })()}
                      </div>
                    )}
                  </div>
                )}
                {movMaterial.tipo === 'ENTRADA' && parseFloat(movMaterial.costo_unitario || '0') > 0 && cuentasPago.length > 0 && (() => {
                  const { cuentaId, monedaId } = parsePagoKey(movMaterial.pago_key);
                  const brutoRef = parseFloat(movMaterial.costo_unitario || '0') || 0;
                  const descPct = parseFloat(movMaterial.descuento_porcentaje || '0') || 0;
                  const netoUnit = descPct > 0 ? Math.max(0, brutoRef * (1 - descPct / 100)) : brutoRef;
                  const totalRef = netoUnit * (parseFloat(movMaterial.cantidad || '0') || 0);
                  const pagoCod = codMonedaDe(monedaId);
                  const necesitaTasa = !!cuentaId && monedaId !== MONEDA_BASE_ID;
                  const tasaNum = parseFloat(movMaterial.tasa_pago || '0') || 0;
                  const deduc = cuentaId ? (necesitaTasa && tasaNum > 0 ? totalRef / tasaNum : totalRef) : 0;
                  return (
                    <>
                      <div className="space-y-1">
                        <label className="text-xs font-bold text-yeikar-secondary">
                          ¿Desde qué cuenta pagaste? <span className="text-yeikar-neutral/40 font-normal">(Opcional — vacío = a crédito)</span>
                        </label>
                        <SearchSelect
                          value={movMaterial.pago_key}
                          onChange={(v) => setMovMaterial(p => ({ ...p, pago_key: String(v), tasa_pago: parsePagoKey(String(v)).monedaId === MONEDA_BASE_ID ? '' : p.tasa_pago }))}
                          options={[
                            { value: '', label: 'Fiar (registrar deuda)' },
                            ...cuentasPago.map((c) => ({ value: c.key, label: `${c.nombre} · ${c.codigo}` })),
                          ]}
                          placeholder="Contado desde..."
                        />
                      </div>
                      {!cuentaId && (
                        <div className="space-y-1.5">
                          <p className="text-[11px] text-red-600/80 bg-red-50/70 border border-red-100 rounded-lg px-3 py-2">
                            Se registrará una deuda de ≈ <b>${(totalRef + (parseFloat(movMaterial.llevada || '0') || 0)).toLocaleString('es-CO')} COP</b>
                            {' '}(compra + pasada) en <b>Egresos y Gastos → Por Pagar</b>.
                          </p>
                          {!movMaterial.proveedor_nombre && (
                            <p className="text-[11px] font-bold text-red-600">
                              Al fiar es obligatorio indicar el proveedor (campo de arriba).
                            </p>
                          )}
                        </div>
                      )}
                      {necesitaTasa && (
                        <div className="space-y-1">
                          <label className="text-xs font-bold text-yeikar-secondary">
                            Tasa de cambio * <span className="text-yeikar-neutral/40 font-normal">(1 {pagoCod} = ? COP · se ingresa manualmente)</span>
                          </label>
                          <input type="number" step="0.01" min="0" required value={movMaterial.tasa_pago} onChange={(e) => setMovMaterial(p => ({ ...p, tasa_pago: e.target.value }))} placeholder="Ej: 4000" className={inputCls} />
                        </div>
                      )}
                      {!!cuentaId && (
                        <p className="text-[11px] text-yeikar-neutral/70 bg-emerald-50/70 border border-emerald-100 rounded-lg px-3 py-2">
                          Se descontarán ≈ <b>${deduc.toLocaleString('es-CO')} {pagoCod}</b> desde <b>{cuentasPago.find((c) => c.key === movMaterial.pago_key)?.nombre}</b>
                          {necesitaTasa && tasaNum <= 0 ? ' · falta la tasa' : ''}
                        </p>
                      )}
                    </>
                  );
                })()}
                <div className="space-y-1">
                  <label className="text-xs font-bold text-yeikar-secondary">Observaciones</label>
                  <textarea rows={2} placeholder="Detalle o referencia..." value={movMaterial.observaciones} onChange={(e) => setMovMaterial(p => ({ ...p, observaciones: e.target.value }))} className="w-full bg-yeikar-tertiary/20 border border-yeikar-secondary-light/10 rounded-xl p-2.5 text-sm text-yeikar-neutral focus:outline-none focus:border-yeikar-primary" />
                </div>
                <button
                  type="submit"
                  disabled={savingMov}
                  className="w-full py-2 bg-yeikar-primary hover:bg-yeikar-primary-dark text-yeikar-neutral rounded-xl font-bold font-headline text-sm transition-colors disabled:opacity-50"
                >
                  {savingMov ? 'Registrando...' : 'Registrar Movimiento'}
                </button>
              </form>

              {/* Historial */}
              <div>
                <span className="text-xs font-headline font-black uppercase tracking-wider text-yeikar-secondary">Historial</span>
                {loadingKardex ? (
                  <div className="flex flex-col items-center justify-center py-8 space-y-3">
                    <div className="w-8 h-8 border-4 border-yeikar-primary border-t-transparent rounded-full animate-spin"></div>
                    <p className="text-xs text-yeikar-neutral/50 font-mono">Cargando historial...</p>
                  </div>
                ) : (
                  <div className="mt-3 space-y-3">
                    {kardex.length === 0 ? (
                      <p className="text-xs text-yeikar-neutral/40 italic text-center py-4">No se registran movimientos para este material.</p>
                    ) : (
                      kardex.map((mov) => {
                        const isEntry = mov.tipo === 'ENTRADA' || mov.tipo === 'DEVOLUCION';
                        const isAdjustment = mov.tipo === 'AJUSTE';
                        return (
                          <div key={mov.id} className="bg-yeikar-tertiary/10 border border-yeikar-secondary-light/5 rounded-xl p-3 text-xs space-y-1">
                            <div className="flex items-center justify-between">
                              <span className={`font-bold uppercase tracking-wider text-[10px] px-2 py-0.5 rounded border ${
                                isAdjustment ? 'bg-slate-50 text-slate-700 border-slate-200' : isEntry ? 'bg-green-50 text-green-700 border-green-200' : 'bg-red-50 text-red-700 border-red-200'
                              }`}>
                                {mov.tipo}
                              </span>
                              <span className="font-mono text-[10px] text-yeikar-neutral/40">
                                {new Date(mov.fecha).toLocaleDateString('es-ES', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' })}
                              </span>
                            </div>
                            <div className="flex items-baseline justify-between mt-1.5">
                              <span className="text-yeikar-neutral/60 font-medium">Cantidad:</span>
                              <span className={`font-mono font-bold text-sm ${isEntry ? 'text-green-600' : 'text-yeikar-secondary'}`}>
                                {isEntry ? '+' : isAdjustment ? '' : '-'}{parseFloat(mov.cantidad.toString()).toLocaleString('es-ES')}
                              </span>
                            </div>
                            {mov.costo_unitario != null && isEntry && (
                              <p className="text-[11px] text-yeikar-neutral/50 mt-0.5">
                                Precio: <span className="font-mono font-semibold">${Number(mov.costo_unitario).toLocaleString('es-ES')}</span>
                              </p>
                            )}
                            {mov.llevada != null && Number(mov.llevada) > 0 && (
                              <p className="text-[11px] text-yeikar-neutral/50 mt-0.5">
                                Llevada (flete): <span className="font-mono font-semibold text-amber-700">${Number(mov.llevada).toLocaleString('es-ES')}</span>
                              </p>
                            )}
                            {(mov.proveedor_nombre || mov.cliente_nombre) && (
                              <p className="text-[11px] text-yeikar-neutral/50 mt-0.5">
                                {mov.proveedor_nombre && <>Proveedor: <span className="font-semibold text-yeikar-secondary">{mov.proveedor_nombre}</span></>}
                                {mov.proveedor_nombre && mov.cliente_nombre && ' · '}
                                {mov.cliente_nombre && <>Cliente: <span className="font-semibold text-yeikar-secondary">{mov.cliente_nombre}</span></>}
                              </p>
                            )}
                            {mov.observaciones && (
                              <p className="text-[11px] text-yeikar-neutral/50 italic mt-1 bg-white/40 p-1.5 rounded border border-yeikar-secondary-light/5">
                                {mov.observaciones}
                              </p>
                            )}
                          </div>
                        );
                      })
                    )}
                  </div>
                )}
              </div>
            </div>
          </div>
        )}

        {/* ================= PANEL LATERAL (Producto: movimiento + historial) ================= */}
        {(tab === 'productos' || tab === 'exhibicion') && selectedProductoId && productoSeleccionado && (
          <div className="w-full lg:w-[28rem] bg-white border border-yeikar-secondary-light/10 rounded-3xl p-5 shadow-sm space-y-5 flex flex-col max-h-[800px] overflow-hidden">
            <div className="flex items-start justify-between border-b border-yeikar-secondary-light/5 pb-3">
              <div>
                <span className="text-[10px] font-mono font-bold text-yeikar-neutral/40">DETALLE DE PRODUCTO</span>
                <h3 className="font-headline font-black text-yeikar-secondary text-base truncate max-w-[240px]" title={productoSeleccionado.nombre}>
                  {productoSeleccionado.nombre}
                </h3>
              </div>
              <button
                onClick={() => setSelectedProductoId(null)}
                className="p-1 hover:bg-yeikar-tertiary rounded-lg text-yeikar-neutral/40 hover:text-yeikar-neutral/70 transition-colors"
              >
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>

            {tab === 'exhibicion' && (
              <div className="flex gap-2">
                <button
                  onClick={() => setProducirPieza({ producto_id: productoSeleccionado.id, nombre: productoSeleccionado.nombre })}
                  className="flex-1 py-2 bg-yeikar-primary hover:bg-yeikar-primary-dark text-yeikar-neutral rounded-xl font-bold font-headline text-xs transition-colors"
                >
                  Orden de Producción
                </button>
                <button
                  onClick={() => venderPieza(productoSeleccionado.id)}
                  className="flex-1 py-2 bg-white hover:bg-yeikar-tertiary/40 text-yeikar-secondary border border-yeikar-secondary-light/20 rounded-xl font-bold font-headline text-xs transition-colors"
                >
                  Vender
                </button>
              </div>
            )}

            <div className="flex-1 overflow-y-auto space-y-5 pr-1">
              <form onSubmit={handleRegisterMovementProducto} className="space-y-3 bg-yeikar-tertiary/10 border border-yeikar-secondary-light/5 rounded-2xl p-4">
                <span className="text-xs font-headline font-black uppercase tracking-wider text-yeikar-primary">Registrar Movimiento</span>
                <div className="space-y-1">
                  <label className="text-xs font-bold text-yeikar-secondary">Tipo Movimiento</label>
                  <select value={movProducto.tipo} onChange={(e) => setMovProducto(p => ({ ...p, tipo: e.target.value }))} className={selectCls}>
                    {TIPOS_MOVIMIENTO.map(t => (
                      <option key={t} value={t}>
                        {t === 'ENTRADA' ? 'ENTRADA (Compra/Carga)' : t === 'SALIDA' ? 'SALIDA (Despacho)' : t === 'AJUSTE' ? 'AJUSTE (Inventario físico)' : t === 'DAÑO' ? 'DAÑO (Mermas)' : 'DEVOLUCION'}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="space-y-1">
                  <label className="text-xs font-bold text-yeikar-secondary">Ubicación / Almacén</label>
                  <SearchSelect
                    value={movProducto.ubicacion_id}
                    onChange={(v) => setMovProducto(p => ({ ...p, ubicacion_id: String(v) }))}
                    options={ubicaciones.map((u) => ({ value: u.id, label: u.nombre }))}
                    placeholder="Seleccione una ubicación"
                  />
                </div>
                <div className="space-y-1">
                  <label className="text-xs font-bold text-yeikar-secondary">Cantidad</label>
                  <input type="number" step="0.01" min="0.01" required placeholder="0.00" value={movProducto.cantidad} onChange={(e) => setMovProducto(p => ({ ...p, cantidad: e.target.value }))} className={inputCls} />
                </div>
                {(movProducto.tipo === 'ENTRADA' || movProducto.tipo === 'DEVOLUCION') && (
                  <div className="space-y-3 bg-white/40 p-3 rounded-xl border border-yeikar-secondary-light/10">
                    <div className="space-y-1">
                      <label className="text-xs font-bold text-yeikar-secondary">
                        {productoSeleccionado?.es_reventa
                          ? <>Precio Unitario (Lista) <span className="text-yeikar-neutral/40 font-normal">(en {productoSeleccionado?.moneda?.codigo ?? 'COP'} · actualiza el precio al instante)</span></>
                          : <>Costo Unitario <span className="text-yeikar-neutral/40 font-normal">(valoriza el stock; no toca el costo del catálogo)</span></>}
                      </label>
                      <input type="number" step="0.01" min="0" placeholder="0.00" value={movProducto.costo_unitario} onChange={(e) => setMovProducto(p => ({ ...p, costo_unitario: e.target.value }))} className={inputCls} />
                    </div>

                    {/* "La llevada": flete/aduana */}
                    <div className="space-y-1">
                      <label className="text-xs font-bold text-yeikar-secondary">
                        La Llevada (flete/aduana) <span className="text-yeikar-neutral/40 font-normal">(opcional — genera gasto desde la cuenta)</span>
                      </label>
                      <input type="number" step="0.01" min="0" placeholder="0.00" value={movProducto.llevada} onChange={(e) => setMovProducto(p => ({ ...p, llevada: e.target.value }))} className={inputCls} />
                    </div>

                    {/* Proveedor: dónde se compró (opcional, texto libre) */}
                    <div className="space-y-1">
                      <label className="text-xs font-bold text-yeikar-secondary">
                        Proveedor <span className="text-yeikar-neutral/40 font-normal">(dónde se compró — opcional)</span>
                      </label>
                      <input
                        type="text"
                        value={movProducto.proveedor_nombre}
                        onChange={(e) => setMovProducto(p => ({ ...p, proveedor_nombre: e.target.value }))}
                        placeholder="Ej. Distribuidora Maderas C.A."
                        className={inputCls}
                      />
                    </div>

                    {/* Cliente: producto comprado para un cliente específico (opcional, texto libre) */}
                    <div className="space-y-1">
                      <label className="text-xs font-bold text-yeikar-secondary">
                        Cliente <span className="text-yeikar-neutral/40 font-normal">(comprado para un cliente — opcional)</span>
                      </label>
                      <input
                        type="text"
                        value={movProducto.cliente_nombre}
                        onChange={(e) => setMovProducto(p => ({ ...p, cliente_nombre: e.target.value }))}
                        placeholder="Ej. Cliente sin registrar"
                        className={inputCls}
                      />
                    </div>

                    {movProducto.tipo === 'ENTRADA' && parseFloat(movProducto.costo_unitario || '0') > 0 && (
                      <div className="space-y-2 pt-1 border-t border-yeikar-secondary-light/10">
                        <div className="flex items-center justify-between">
                          <label className="text-xs font-bold text-yeikar-secondary">
                            % Descuento por pago completo / al mayor
                          </label>
                          <span className="text-[10px] text-yeikar-neutral/40">Opcional</span>
                        </div>
                        <div className="relative">
                          <input
                            type="number"
                            min="0"
                            max="100"
                            step="0.1"
                            placeholder="Ej: 10"
                            value={movProducto.descuento_porcentaje}
                            onChange={(e) => setMovProducto(p => ({ ...p, descuento_porcentaje: e.target.value }))}
                            className={`${inputCls} pr-8`}
                          />
                          <span className="absolute right-3 top-1/2 -translate-y-1/2 text-xs font-bold text-yeikar-neutral/40">%</span>
                        </div>

                        {parseFloat(movProducto.descuento_porcentaje || '0') > 0 && (() => {
                          const bruto = parseFloat(movProducto.costo_unitario || '0') || 0;
                          const desc = parseFloat(movProducto.descuento_porcentaje || '0') || 0;
                          const montoDesc = (bruto * desc) / 100;
                          const neto = Math.max(0, bruto - montoDesc);
                          const cod = productoSeleccionado?.moneda?.codigo ?? 'COP';
                          return (
                            <div className="bg-emerald-50 border border-emerald-200 rounded-lg p-2 text-[11px] space-y-1 text-emerald-900">
                              <div className="flex justify-between">
                                <span>Precio lista:</span>
                                <span className="font-mono">${bruto.toLocaleString('es-CO', { minimumFractionDigits: 2 })} {cod}</span>
                              </div>
                              <div className="flex justify-between text-emerald-700 font-semibold">
                                <span>Descuento ({desc}%):</span>
                                <span className="font-mono">-${montoDesc.toLocaleString('es-CO', { minimumFractionDigits: 2 })} {cod}</span>
                              </div>
                              <div className="flex justify-between font-bold border-t border-emerald-200 pt-1 text-emerald-950">
                                <span>Costo neto a registrar:</span>
                                <span className="font-mono">${neto.toLocaleString('es-CO', { minimumFractionDigits: 2 })} {cod}</span>
                              </div>
                            </div>
                          );
                        })()}
                      </div>
                    )}
                  </div>
                )}
                {movProducto.tipo === 'ENTRADA' && movProducto.costo_unitario && parseFloat(movProducto.costo_unitario) > 0 && cuentasPago.length > 0 && (() => {
                  const refMid = Number(productoSeleccionado?.moneda_id ?? MONEDA_BASE_ID);
                  const { cuentaId, monedaId } = parsePagoKey(movProducto.pagado_desde_metodo_caja_id);
                  const pagoMid = monedaId ?? refMid;
                  const pagoCod = codMonedaDe(pagoMid);
                  const refCod = codMonedaDe(refMid);
                  // Tasa manual obligatoria si el pago o la referencia no son COP
                  const necesitaTasa = !!cuentaId && (pagoMid !== MONEDA_BASE_ID || refMid !== MONEDA_BASE_ID);
                  const tasaNum = parseFloat(movProducto.tasa_pago || '0') || 0;
                  const bruto = parseFloat(movProducto.costo_unitario || '0') || 0;
                  const desc = parseFloat(movProducto.descuento_porcentaje || '0') || 0;
                  const costoNetoUnit = desc > 0 ? Math.max(0, bruto * (1 - desc / 100)) : bruto;
                  const totalRef = costoNetoUnit * (parseFloat(movProducto.cantidad || '0') || 0);
                  const deduc = !cuentaId ? 0
                    : pagoMid === refMid ? totalRef
                    : pagoMid === MONEDA_BASE_ID ? totalRef * tasaNum
                    : totalRef / tasaNum;
                  return (
                    <>
                      <div className="space-y-1">
                        <label className="text-xs font-bold text-yeikar-secondary">
                          ¿Desde qué cuenta pagaste? <span className="text-yeikar-neutral/40 font-normal">(Opcional — genera el egreso)</span>
                        </label>
                        <SearchSelect
                          value={movProducto.pagado_desde_metodo_caja_id}
                          onChange={(v) => setMovProducto(p => ({ ...p, pagado_desde_metodo_caja_id: String(v), tasa_pago: '' }))}
                          options={[
                            { value: '', label: 'A crédito (no descuenta caja)' },
                            ...cuentasPago.map((c) => ({ value: c.key, label: `${c.nombre} · ${c.codigo}` })),
                          ]}
                          placeholder="Contado desde... (vacío = a crédito)"
                        />
                      </div>
                      {cuentaId && necesitaTasa && (
                        <div className="space-y-1">
                          <label className="text-xs font-bold text-yeikar-secondary">
                            Tasa de cambio * <span className="text-yeikar-neutral/40 font-normal">(1 {pagoCod === 'COP' ? refCod : pagoCod} = ? COP)</span>
                          </label>
                          <input type="number" step="0.01" min="0" required value={movProducto.tasa_pago} onChange={(e) => setMovProducto(p => ({ ...p, tasa_pago: e.target.value }))} placeholder="Ej: 4000" className={inputCls} />
                        </div>
                      )}
                      {!!cuentaId && (
                        <p className="text-[11px] text-yeikar-neutral/70 bg-emerald-50/70 border border-emerald-100 rounded-lg px-3 py-2">
                          Se descontarán ≈ <b>${deduc.toLocaleString('es-CO')} {pagoCod}</b> desde <b>{cuentasPago.find((c) => c.key === movProducto.pagado_desde_metodo_caja_id)?.nombre}</b>
                          {necesitaTasa && tasaNum <= 0 ? ' · falta la tasa' : ''}
                        </p>
                      )}
                    </>
                  );
                })()}
                <div className="space-y-1">
                  <label className="text-xs font-bold text-yeikar-secondary">Observaciones</label>
                  <textarea rows={2} placeholder="Detalle o referencia..." value={movProducto.observaciones} onChange={(e) => setMovProducto(p => ({ ...p, observaciones: e.target.value }))} className="w-full bg-yeikar-tertiary/20 border border-yeikar-secondary-light/10 rounded-xl p-2.5 text-sm text-yeikar-neutral focus:outline-none focus:border-yeikar-primary" />
                </div>
                <button
                  type="submit"
                  disabled={savingMovProd}
                  className="w-full py-2 bg-yeikar-primary hover:bg-yeikar-primary-dark text-yeikar-neutral rounded-xl font-bold font-headline text-sm transition-colors disabled:opacity-50"
                >
                  {savingMovProd ? 'Registrando...' : 'Registrar Movimiento'}
                </button>
              </form>

              <div>
                <span className="text-xs font-headline font-black uppercase tracking-wider text-yeikar-secondary">Historial</span>
                {loadingKardexProducto ? (
                  <div className="flex flex-col items-center justify-center py-8 space-y-3">
                    <div className="w-8 h-8 border-4 border-yeikar-primary border-t-transparent rounded-full animate-spin"></div>
                    <p className="text-xs text-yeikar-neutral/50 font-mono">Cargando historial...</p>
                  </div>
                ) : (
                  <div className="mt-3 space-y-3">
                    {kardexProducto.length === 0 ? (
                      <p className="text-xs text-yeikar-neutral/40 italic text-center py-4">No se registran movimientos para este producto.</p>
                    ) : (
                      kardexProducto.map((mov) => {
                        const isEntry = mov.tipo === 'ENTRADA' || mov.tipo === 'DEVOLUCION';
                        const isAdjustment = mov.tipo === 'AJUSTE';
                        return (
                          <div key={mov.id} className="bg-yeikar-tertiary/10 border border-yeikar-secondary-light/5 rounded-xl p-3 text-xs space-y-1">
                            <div className="flex items-center justify-between">
                              <span className={`font-bold uppercase tracking-wider text-[10px] px-2 py-0.5 rounded border ${
                                isAdjustment ? 'bg-slate-50 text-slate-700 border-slate-200' : isEntry ? 'bg-green-50 text-green-700 border-green-200' : 'bg-red-50 text-red-700 border-red-200'
                              }`}>
                                {mov.tipo}
                              </span>
                              <span className="font-mono text-[10px] text-yeikar-neutral/40">
                                {new Date(mov.fecha).toLocaleDateString('es-ES', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' })}
                              </span>
                            </div>
                            <div className="flex items-baseline justify-between mt-1.5">
                              <span className="text-yeikar-neutral/60 font-medium">Cantidad:</span>
                              <span className={`font-mono font-bold text-sm ${isEntry ? 'text-green-600' : 'text-yeikar-secondary'}`}>
                                {isEntry ? '+' : isAdjustment ? '' : '-'}{parseFloat(mov.cantidad.toString()).toLocaleString('es-ES')}
                              </span>
                            </div>
                            {mov.costo_unitario != null && isEntry && (
                              <p className="text-[11px] text-yeikar-neutral/50 mt-0.5">
                                Precio: <span className="font-mono font-semibold">${Number(mov.costo_unitario).toLocaleString('es-ES')}</span>
                              </p>
                            )}
                            {mov.llevada != null && Number(mov.llevada) > 0 && (
                              <p className="text-[11px] text-yeikar-neutral/50 mt-0.5">
                                Llevada (flete): <span className="font-mono font-semibold text-amber-700">${Number(mov.llevada).toLocaleString('es-ES')}</span>
                              </p>
                            )}
                            {(mov.proveedor_nombre || mov.cliente_nombre) && (
                              <p className="text-[11px] text-yeikar-neutral/50 mt-0.5">
                                {mov.proveedor_nombre && <>Proveedor: <span className="font-semibold text-yeikar-secondary">{mov.proveedor_nombre}</span></>}
                                {mov.proveedor_nombre && mov.cliente_nombre && ' · '}
                                {mov.cliente_nombre && <>Cliente: <span className="font-semibold text-yeikar-secondary">{mov.cliente_nombre}</span></>}
                              </p>
                            )}
                            {mov.observaciones && (
                              <p className="text-[11px] text-yeikar-neutral/50 italic mt-1 bg-white/40 p-1.5 rounded border border-yeikar-secondary-light/5">
                                {mov.observaciones}
                              </p>
                            )}
                          </div>
                        );
                      })
                    )}
                  </div>
                )}
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Modal para Crear Material/Insumo */}
      {showMaterialModal && (
        <div className="fixed inset-0 bg-yeikar-secondary/60 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-3xl shadow-xl max-w-md w-full overflow-hidden border border-yeikar-secondary-light/10">
            <div className="bg-gradient-to-r from-yeikar-secondary to-yeikar-secondary-light text-white px-6 py-5">
              <h3 className="font-headline font-black text-lg">Nuevo Insumo</h3>
              <p className="text-xs text-white/70">Registra un material en el inventario</p>
            </div>
            <form onSubmit={handleCreateMaterial} className="p-6 space-y-4 font-body">
              <div>
                <label className="block text-xs font-bold text-yeikar-secondary mb-1">Nombre del Material *</label>
                <input type="text" required placeholder="Ej. MADERA APAMATE, TELA, etc." value={newMaterial.nombre} onChange={(e) => setNewMaterial(prev => ({ ...prev, nombre: e.target.value }))} className="w-full bg-yeikar-tertiary/20 border border-yeikar-secondary-light/10 rounded-xl px-4 py-2.5 text-sm text-yeikar-neutral focus:outline-none focus:border-yeikar-primary uppercase" />
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs font-bold text-yeikar-secondary mb-1">Precio Unitario <span className="text-yeikar-neutral/40 font-normal">(Opcional)</span></label>
                  <input type="number" min="0" step="0.01" placeholder="0.00" value={newMaterial.costo_base} onChange={(e) => setNewMaterial(prev => ({ ...prev, costo_base: e.target.value }))} className="w-full bg-yeikar-tertiary/20 border border-yeikar-secondary-light/10 rounded-xl px-4 py-2.5 text-sm text-yeikar-neutral focus:outline-none focus:border-yeikar-primary font-mono" />
                </div>
                <div>
                  <label className="block text-xs font-bold text-yeikar-secondary mb-1">Stock Mínimo <span className="text-yeikar-neutral/40 font-normal">(Alerta)</span></label>
                  <input type="number" min="0" step="0.5" value={newMaterial.stock_minimo} onChange={(e) => setNewMaterial(prev => ({ ...prev, stock_minimo: e.target.value }))} className="w-full bg-yeikar-tertiary/20 border border-yeikar-secondary-light/10 rounded-xl px-4 py-2.5 text-sm text-yeikar-neutral focus:outline-none focus:border-yeikar-primary font-mono" />
                </div>
              </div>
              <div>
                <label className="block text-xs font-bold text-yeikar-secondary mb-1">Unidad de Medida *</label>
                <SearchSelect
                  value={newMaterial.unidad_medida_id}
                  onChange={(v) => setNewMaterial(prev => ({ ...prev, unidad_medida_id: String(v) }))}
                  options={unidades.map((u) => ({ value: u.id, label: `${u.nombre} (${u.abreviatura})` }))}
                  placeholder="Seleccionar..."
                />
              </div>
              <div>
                <label className="block text-xs font-bold text-yeikar-secondary mb-1">Categoría de Inventario <span className="text-yeikar-neutral/40 font-normal">(desglose en la UI)</span></label>
                <SearchSelect
                  value={newMaterial.categoria_inventario_id}
                  onChange={(v) => setNewMaterial(prev => ({ ...prev, categoria_inventario_id: String(v) }))}
                  options={categoriasMaterial.map((c) => ({ value: c.id, label: c.nombre }))}
                  placeholder="Sin categoría..."
                />
              </div>
              <div>
                <label className="block text-xs font-bold text-yeikar-secondary mb-1">Departamento <span className="text-yeikar-neutral/40 font-normal">(del taller)</span></label>
                <SearchSelect
                  value={newMaterial.departamento ?? ''}
                  onChange={(v) => setNewMaterial(prev => ({ ...prev, departamento: v ? String(v) : null }))}
                  options={[
                    { value: '', label: 'General (sin departamento)' },
                    ...DEPARTAMENTOS.map((d) => ({ value: d.valor, label: d.label })),
                  ]}
                  placeholder="General..."
                />
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs font-bold text-yeikar-secondary mb-1">Largo de Lámina (cm)</label>
                  <input type="number" min="0" step="0.01" placeholder="Ej. 244" value={newMaterial.largo_cm} onChange={(e) => setNewMaterial(prev => ({ ...prev, largo_cm: e.target.value }))} className="w-full bg-yeikar-tertiary/20 border border-yeikar-secondary-light/10 rounded-xl px-4 py-2.5 text-sm text-yeikar-neutral focus:outline-none focus:border-yeikar-primary font-mono" />
                </div>
                <div>
                  <label className="block text-xs font-bold text-yeikar-secondary mb-1">Ancho de Lámina (cm)</label>
                  <input type="number" min="0" step="0.01" placeholder="Ej. 183" value={newMaterial.ancho_cm} onChange={(e) => setNewMaterial(prev => ({ ...prev, ancho_cm: e.target.value }))} className="w-full bg-yeikar-tertiary/20 border border-yeikar-secondary-light/10 rounded-xl px-4 py-2.5 text-sm text-yeikar-neutral focus:outline-none focus:border-yeikar-primary font-mono" />
                </div>
              </div>
              <p className="text-[11px] text-yeikar-neutral/50 -mt-2">
                Solo para láminas (MDF, melamina, espuma...): permite consumir por <b>cortes</b> y registrar sobrantes.
              </p>
              {(!newMaterial.largo_cm || !newMaterial.ancho_cm) && (
                <p className="text-[11px] font-semibold text-amber-700 bg-amber-50 border border-amber-200 rounded-lg px-2.5 py-1.5">
                  Sin dimensiones: este material no podrá pedirse por láminas completas ni cortarse en producción. Llena largo × ancho para habilitarlo.
                </p>
              )}
              <div className="flex gap-3 pt-3 border-t border-yeikar-secondary-light/5">
                <button type="button" onClick={() => setShowMaterialModal(false)} className="flex-1 py-2.5 bg-yeikar-tertiary hover:bg-yeikar-secondary-light/15 text-yeikar-secondary rounded-xl font-bold font-headline text-sm transition-colors">Cancelar</button>
                <button type="submit" className="flex-1 py-2.5 bg-yeikar-primary hover:bg-yeikar-primary-dark text-yeikar-neutral rounded-xl font-bold font-headline text-sm transition-all">Crear Insumo</button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Modal para Crear Producto de Reventa */}
      {showProductoModal && (
        <div className="fixed inset-0 bg-yeikar-secondary/60 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-3xl shadow-xl max-w-md w-full overflow-hidden border border-yeikar-secondary-light/10">
            <div className="bg-gradient-to-r from-yeikar-secondary to-yeikar-secondary-light text-white px-6 py-5">
              <h3 className="font-headline font-black text-lg">Nuevo Producto de Reventa</h3>
              <p className="text-xs text-white/70">Producto que se compra y revende (colchón, nevera, electrodoméstico...)</p>
            </div>
            <form onSubmit={handleCreateProducto} className="p-6 space-y-4 font-body">
              <div>
                <label className="block text-xs font-bold text-yeikar-secondary mb-1">Nombre del Producto *</label>
                <input type="text" required placeholder="Ej. COLCHON QUEEN, NEVERA 12 PIES..." value={newProducto.nombre} onChange={(e) => setNewProducto(prev => ({ ...prev, nombre: e.target.value }))} className="w-full bg-yeikar-tertiary/20 border border-yeikar-secondary-light/10 rounded-xl px-4 py-2.5 text-sm text-yeikar-neutral focus:outline-none focus:border-yeikar-primary uppercase" />
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs font-bold text-yeikar-secondary mb-1">Código <span className="text-yeikar-neutral/40 font-normal">(Opcional)</span></label>
                  <input type="text" placeholder="Ej. COL-Q, NV-12" value={newProducto.codigo} onChange={(e) => setNewProducto(prev => ({ ...prev, codigo: e.target.value }))} className="w-full bg-yeikar-tertiary/20 border border-yeikar-secondary-light/10 rounded-xl px-4 py-2.5 text-sm text-yeikar-neutral focus:outline-none focus:border-yeikar-primary" />
                </div>
                <div>
                  <label className="block text-xs font-bold text-yeikar-secondary mb-1">Stock Mínimo <span className="text-yeikar-neutral/40 font-normal">(Alerta)</span></label>
                  <input type="number" min="0" step="0.5" value={newProducto.stock_minimo} onChange={(e) => setNewProducto(prev => ({ ...prev, stock_minimo: e.target.value }))} className="w-full bg-yeikar-tertiary/20 border border-yeikar-secondary-light/10 rounded-xl px-4 py-2.5 text-sm text-yeikar-neutral focus:outline-none focus:border-yeikar-primary font-mono" />
                </div>
              </div>
              <div>
                <label className="block text-xs font-bold text-yeikar-secondary mb-1">Moneda de los Precios *</label>
                <SearchSelect
                  value={newProducto.moneda_id}
                  onChange={(v) => setNewProducto(prev => ({ ...prev, moneda_id: String(v) }))}
                  options={monedas.map((m) => ({ value: m.id, label: `${m.codigo} (${m.simbolo})` }))}
                  placeholder="Seleccionar..."
                />
                <p className="text-[10px] text-yeikar-neutral/40 mt-1">En qué moneda compraste este producto (p. ej. USD para importados).</p>
              </div>
              {/* Costo de Compra y Descuento Opcional */}
              <div className="bg-yeikar-tertiary/15 border border-yeikar-secondary-light/10 rounded-2xl p-4 space-y-3">
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="block text-xs font-bold text-yeikar-secondary mb-1">
                      Costo de Compra (Lista) <span className="text-yeikar-neutral/40 font-normal">(Opcional)</span>
                    </label>
                    <div className="relative">
                      <span className="absolute left-3 top-1/2 -translate-y-1/2 text-xs font-mono font-bold text-yeikar-neutral/40">{simboloPrecio}</span>
                      <input
                        type="number"
                        min="0"
                        step="0.01"
                        placeholder="0.00"
                        value={newProducto.costo_base}
                        onChange={(e) => setNewProducto(prev => ({ ...prev, costo_base: e.target.value }))}
                        className="w-full pl-8 pr-3 py-2.5 bg-white border border-yeikar-secondary-light/15 rounded-xl text-sm text-yeikar-neutral focus:outline-none focus:border-yeikar-primary font-mono"
                      />
                    </div>
                  </div>

                  <div>
                    <label className="block text-xs font-bold text-yeikar-secondary mb-1">
                      % Descuento por pago completo / mayor
                    </label>
                    <div className="relative">
                      <input
                        type="number"
                        min="0"
                        max="100"
                        step="0.1"
                        placeholder="Ej: 10"
                        value={newProducto.descuento_porcentaje}
                        onChange={(e) => setNewProducto(prev => ({ ...prev, descuento_porcentaje: e.target.value }))}
                        className="w-full pr-8 pl-3 py-2.5 bg-white border border-yeikar-secondary-light/15 rounded-xl text-sm text-yeikar-neutral focus:outline-none focus:border-yeikar-primary font-mono"
                      />
                      <span className="absolute right-3 top-1/2 -translate-y-1/2 text-xs font-bold text-yeikar-neutral/40">%</span>
                    </div>
                  </div>
                </div>

                {/* Desglose de Descuento si aplica */}
                {parseFloat(newProducto.costo_base || '0') > 0 && parseFloat(newProducto.descuento_porcentaje || '0') > 0 && (() => {
                  const bruto = parseFloat(newProducto.costo_base || '0') || 0;
                  const desc = parseFloat(newProducto.descuento_porcentaje || '0') || 0;
                  const montoDesc = (bruto * desc) / 100;
                  const neto = Math.max(0, bruto - montoDesc);
                  return (
                    <div className="bg-emerald-50 border border-emerald-200 rounded-xl p-2.5 text-xs space-y-1 text-emerald-900">
                      <div className="flex justify-between">
                        <span className="text-emerald-700">Precio lista de compra:</span>
                        <span className="font-mono">{simboloPrecio}{bruto.toFixed(2)}</span>
                      </div>
                      <div className="flex justify-between text-emerald-700 font-semibold">
                        <span>Descuento aplicado ({desc}%):</span>
                        <span className="font-mono">-{simboloPrecio}{montoDesc.toFixed(2)}</span>
                      </div>
                      <div className="flex justify-between font-bold border-t border-emerald-200 pt-1 text-emerald-950">
                        <span>Costo neto real de inventario:</span>
                        <span className="font-mono">{simboloPrecio}{neto.toFixed(2)}</span>
                      </div>
                    </div>
                  );
                })()}
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs font-bold text-yeikar-secondary mb-1">Cantidad Inicial</label>
                  <input type="number" min="0" step="1" placeholder="1" value={newProducto.cantidad_inicial} onChange={(e) => setNewProducto(prev => ({ ...prev, cantidad_inicial: e.target.value }))} className="w-full bg-yeikar-tertiary/20 border border-yeikar-secondary-light/10 rounded-xl px-4 py-2.5 text-sm text-yeikar-neutral focus:outline-none focus:border-yeikar-primary font-mono" />
                </div>
                <div className="flex items-end">
                  <p className="text-[10px] text-yeikar-neutral/40 leading-tight pb-1">
                    Unidades que entran al inventario al crear el producto. Después puedes agregar más o descontar con movimientos.
                  </p>
                </div>
              </div>
              {/* Foto de referencia (opcional) */}
              <div>
                <label className="block text-xs font-bold text-yeikar-secondary mb-1">Foto de Referencia <span className="text-yeikar-neutral/40 font-normal">(Opcional)</span></label>
                <div className="flex items-center gap-3">
                  {fotoProductoPreview && (
                    <img src={fotoProductoPreview} alt="Vista previa de la foto de referencia" className="h-16 w-16 rounded-xl object-cover border border-yeikar-primary/40" />
                  )}
                  <label className={`flex items-center justify-center gap-1.5 h-16 flex-1 px-3 rounded-xl border-2 border-dashed border-yeikar-secondary-light/20 hover:border-yeikar-primary/50 cursor-pointer text-[11px] font-bold text-yeikar-neutral/50 transition-colors ${fotoProductoPreview ? '' : 'border-solid bg-yeikar-tertiary/20'}`}>
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
                    </svg>
                    {fotoProducto ? 'Cambiar foto' : 'Subir foto'}
                    <input
                      type="file"
                      accept="image/jpeg,image/png,image/webp,image/heic"
                      className="hidden"
                      onChange={(e) => {
                        const f = e.target.files?.[0];
                        if (!f) return;
                        setFotoProducto(f);
                        if (fotoProductoPreview) URL.revokeObjectURL(fotoProductoPreview);
                        setFotoProductoPreview(URL.createObjectURL(f));
                      }}
                    />
                  </label>
                </div>
                <p className="text-[10px] text-yeikar-neutral/40 mt-1.5">
                  La imagen se optimiza al subirla (máx. 15 MB; se redimensiona y comprime para no ocupar espacio).
                </p>
              </div>
              {parseFloat(newProducto.costo_base || '0') > 0 && cuentasPago.length > 0 && (() => {
                const refMid = Number(newProducto.moneda_id || MONEDA_BASE_ID);
                const { cuentaId, monedaId } = parsePagoKey(newProducto.cuenta_pago_id);
                const pagoMid = monedaId ?? refMid;
                const pagoCod = codMonedaDe(pagoMid);
                const refCod = codMonedaDe(refMid);
                const necesitaTasa = !!cuentaId && (pagoMid !== MONEDA_BASE_ID || refMid !== MONEDA_BASE_ID);
                return (
                  <div className="space-y-2">
                    <div>
                      <label className="block text-xs font-bold text-yeikar-secondary mb-1">
                        ¿Desde qué cuenta pagaste? <span className="text-yeikar-neutral/40 font-normal">(Opcional)</span>
                      </label>
                      <SearchSelect
                        value={newProducto.cuenta_pago_id}
                        onChange={(v) => setNewProducto(prev => ({ ...prev, cuenta_pago_id: String(v), tasa_pago: '' }))}
                        options={[
                          { value: '', label: 'A crédito (no descuenta caja)' },
                          ...cuentasPago.map((c) => ({ value: c.key, label: `${c.nombre} · ${c.codigo}` })),
                        ]}
                        placeholder="Contado desde... (vacío = a crédito)"
                      />
                      <p className="text-[10px] text-yeikar-neutral/40 mt-1">
                        Si eliges una, se registra el egreso de la compra y sale de esa caja automáticamente.
                      </p>
                    </div>
                    {cuentaId && necesitaTasa && (
                      <div>
                        <label className="block text-xs font-bold text-yeikar-secondary mb-1">
                          Tasa de cambio * <span className="text-yeikar-neutral/40 font-normal">(1 {pagoCod === 'COP' ? refCod : pagoCod} = ? COP · manual)</span>
                        </label>
                        <input
                          type="number" step="0.01" min="0" required
                          value={newProducto.tasa_pago}
                          onChange={(e) => setNewProducto(prev => ({ ...prev, tasa_pago: e.target.value }))}
                          placeholder="Ej: 4000"
                          className="w-full bg-yeikar-tertiary/20 border border-yeikar-secondary-light/10 rounded-xl p-2.5 text-sm font-mono text-yeikar-neutral focus:outline-none focus:border-yeikar-primary"
                        />
                      </div>
                    )}
                  </div>
                );
              })()}
              {parseFloat(newProducto.cantidad_inicial || '0') > 0 && (
                <p className="text-[11px] text-yeikar-neutral/50 italic bg-yeikar-tertiary/30 border border-yeikar-secondary-light/5 rounded-lg px-3 py-2">
                  Se registrará una entrada inicial de {newProducto.cantidad_inicial || 1} unidad(es) en {ubicaciones[0]?.nombre || 'Depósito Principal'}{parseFloat(newProducto.costo_base || '0') > 0 ? ` con ese costo (${simboloPrecio}${newProducto.costo_base} c/u)` : ''}.
                </p>
              )}
              <div className="flex gap-3 pt-3 border-t border-yeikar-secondary-light/5">
                <button type="button" onClick={() => setShowProductoModal(false)} className="flex-1 py-2.5 bg-yeikar-tertiary hover:bg-yeikar-secondary-light/15 text-yeikar-secondary rounded-xl font-bold font-headline text-sm transition-colors">Cancelar</button>
                <button type="submit" disabled={savingProducto} className="flex-1 py-2.5 bg-yeikar-primary hover:bg-yeikar-primary-dark text-yeikar-neutral rounded-xl font-bold font-headline text-sm transition-all disabled:opacity-50">{savingProducto ? 'Creando...' : 'Crear Producto'}</button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Modal para Alta de Ítem en Crudo */}
      {showCrudoModal && (
        <div className="fixed inset-0 bg-yeikar-secondary/60 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-3xl shadow-xl max-w-md w-full overflow-hidden border border-yeikar-secondary-light/10">
            <div className="bg-gradient-to-r from-yeikar-secondary to-yeikar-secondary-light text-white px-6 py-5">
              <h3 className="font-headline font-black text-lg">Nuevo Ítem en Crudo</h3>
              <p className="text-xs text-white/70">Ítem libre de inventario intermedio (generalmente ebanistería).</p>
            </div>
            <form onSubmit={handleCreateCrudo} className="p-6 space-y-4 font-body">
              <div>
                <label className="block text-xs font-bold text-yeikar-secondary mb-1">Nombre *</label>
                <input
                  type="text" required maxLength={200}
                  placeholder="Ej: Marco de cama en nogal"
                  value={newCrudo.nombre}
                  onChange={(e) => setNewCrudo(prev => ({ ...prev, nombre: e.target.value }))}
                  className={inputCls.replace('font-mono', '').replace(' uppercase', '')}
                />
              </div>
              <div>
                <label className="block text-xs font-bold text-yeikar-secondary mb-1">Foto de referencia (opcional)</label>
                <input
                  type="file"
                  accept="image/*"
                  onChange={(e) => setFotoCrudo(e.target.files?.[0] || null)}
                  className="w-full text-sm text-yeikar-neutral/70 file:mr-3 file:rounded-lg file:border-0 file:bg-yeikar-tertiary file:px-4 file:py-2 file:text-xs file:font-bold file:text-yeikar-secondary hover:file:bg-yeikar-secondary-light/20"
                />
                {fotoCrudo && (
                  <p className="text-[11px] text-yeikar-neutral/50 mt-1">{fotoCrudo.name}</p>
                )}
              </div>
              <div className="flex gap-3 pt-3 border-t border-yeikar-secondary-light/5">
                <button type="button" onClick={() => setShowCrudoModal(false)} className="flex-1 py-2.5 bg-yeikar-tertiary hover:bg-yeikar-secondary-light/15 text-yeikar-secondary rounded-xl font-bold font-headline text-sm transition-colors">Cancelar</button>
                <button type="submit" disabled={savingCrudo} className="flex-1 py-2.5 bg-yeikar-primary hover:bg-yeikar-primary-dark text-yeikar-neutral rounded-xl font-bold font-headline text-sm transition-all disabled:opacity-50">{savingCrudo ? 'Guardando...' : 'Guardar Ítem'}</button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Modal para Asignar Crudo a un Detalle de Pedido */}
      {asignarCrudoTarget && (
        <div className="fixed inset-0 bg-yeikar-secondary/60 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-3xl shadow-xl max-w-md w-full overflow-hidden border border-yeikar-secondary-light/10">
            <div className="bg-gradient-to-r from-yeikar-secondary to-yeikar-secondary-light text-white px-6 py-5">
              <h3 className="font-headline font-black text-lg">Asignar a Pedido</h3>
              <p className="text-xs text-white/70">
                {asignarCrudoTarget.nombre} · Stock: {asignarCrudoTarget.cantidad.toLocaleString('es-ES')}
              </p>
            </div>
            <form onSubmit={handleAsignarCrudo} className="p-6 space-y-4 font-body">
              <div>
                <label className="block text-xs font-bold text-yeikar-secondary mb-1">ID del Detalle de Pedido *</label>
                <input
                  type="number" min="1" required
                  placeholder="Ej: 123"
                  value={detallePedidoInput}
                  onChange={(e) => setDetallePedidoInput(e.target.value)}
                  className={inputCls}
                />
                <p className="text-[11px] text-yeikar-neutral/50 mt-1">
                  Se descuenta 1 pieza del stock del ítem. No auto-marca etapas: el supervisor cierra las áreas manualmente en el flujo normal de producción.
                </p>
              </div>
              <div className="flex gap-3 pt-3 border-t border-yeikar-secondary-light/5">
                <button type="button" onClick={() => setAsignarCrudoTarget(null)} className="flex-1 py-2.5 bg-yeikar-tertiary hover:bg-yeikar-secondary-light/15 text-yeikar-secondary rounded-xl font-bold font-headline text-sm transition-colors">Cancelar</button>
                <button type="submit" disabled={asignando} className="flex-1 py-2.5 bg-yeikar-primary hover:bg-yeikar-primary-dark text-yeikar-neutral rounded-xl font-bold font-headline text-sm transition-all disabled:opacity-50">{asignando ? 'Asignando...' : 'Asignar'}</button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Modal para Registrar Sobrante (retazo manual) */}
      {showSobranteModal && (
        <div className="fixed inset-0 bg-yeikar-secondary/60 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-3xl shadow-xl max-w-md w-full overflow-hidden border border-yeikar-secondary-light/10">
            <div className="bg-gradient-to-r from-yeikar-secondary to-yeikar-secondary-light text-white px-6 py-5">
              <h3 className="font-headline font-black text-lg">Registrar Sobrante</h3>
              <p className="text-xs text-white/70">Retazo de lámina reutilizable para cortes futuros</p>
            </div>
            <form onSubmit={handleCreateSobrante} className="p-6 space-y-4 font-body">
              <div>
                <label className="block text-xs font-bold text-yeikar-secondary mb-1">Material Laminar *</label>
                <SearchSelect
                  value={newSobrante.material_id}
                  onChange={(v) => setNewSobrante(prev => ({ ...prev, material_id: String(v) }))}
                  options={materiales
                    .filter(m => m.largo_cm != null && m.ancho_cm != null)
                    .map(m => ({ value: m.id, label: m.nombre }))}
                  placeholder="Seleccionar lámina..."
                />
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs font-bold text-yeikar-secondary mb-1">Largo (cm) *</label>
                  <input type="number" min="0" step="0.01" required placeholder="Ej. 120" value={newSobrante.largo_cm} onChange={(e) => setNewSobrante(prev => ({ ...prev, largo_cm: e.target.value }))} className="w-full bg-yeikar-tertiary/20 border border-yeikar-secondary-light/10 rounded-xl px-4 py-2.5 text-sm text-yeikar-neutral focus:outline-none focus:border-yeikar-primary font-mono" />
                </div>
                <div>
                  <label className="block text-xs font-bold text-yeikar-secondary mb-1">Ancho (cm) *</label>
                  <input type="number" min="0" step="0.01" required placeholder="Ej. 45" value={newSobrante.ancho_cm} onChange={(e) => setNewSobrante(prev => ({ ...prev, ancho_cm: e.target.value }))} className="w-full bg-yeikar-tertiary/20 border border-yeikar-secondary-light/10 rounded-xl px-4 py-2.5 text-sm text-yeikar-neutral focus:outline-none focus:border-yeikar-primary font-mono" />
                </div>
              </div>
              <div>
                <label className="block text-xs font-bold text-yeikar-secondary mb-1">Observaciones</label>
                <input type="text" placeholder="Ej. retazo del taller, quedó del pedido #123" value={newSobrante.observaciones} onChange={(e) => setNewSobrante(prev => ({ ...prev, observaciones: e.target.value }))} className="w-full bg-yeikar-tertiary/20 border border-yeikar-secondary-light/10 rounded-xl px-4 py-2.5 text-sm text-yeikar-neutral focus:outline-none focus:border-yeikar-primary" />
              </div>
              <div className="flex gap-3 pt-3 border-t border-yeikar-secondary-light/5">
                <button type="button" onClick={() => setShowSobranteModal(false)} className="flex-1 py-2.5 bg-yeikar-tertiary hover:bg-yeikar-secondary-light/15 text-yeikar-secondary rounded-xl font-bold font-headline text-sm transition-colors">Cancelar</button>
                <button type="submit" disabled={savingSobrante} className="flex-1 py-2.5 bg-yeikar-primary hover:bg-yeikar-primary-dark text-yeikar-neutral rounded-xl font-bold font-headline text-sm transition-all disabled:opacity-50">{savingSobrante ? 'Guardando...' : 'Registrar Sobrante'}</button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Modal Nueva Pieza de Exhibición */}
      {showPiezaModal && (
        <div className="fixed inset-0 bg-yeikar-secondary/60 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-3xl shadow-xl max-w-md w-full overflow-hidden border border-yeikar-secondary-light/10">
            <div className="bg-gradient-to-r from-yeikar-secondary to-yeikar-secondary-light text-white px-6 py-5">
              <h3 className="font-headline font-black text-lg">Nueva Pieza de Exhibición</h3>
              <p className="text-xs text-white/70">Solo nombre, precio en dólares y cuántas hay. La producción (inventario, costos, nómina) se gestiona desde Producción.</p>
            </div>
            <form onSubmit={handleCreatePieza} className="p-6 space-y-4 font-body">
              <div>
                <label className="block text-xs font-bold text-yeikar-secondary mb-1">Nombre de la pieza *</label>
                <input type="text" required placeholder="Ej. CAMA MODELO ORBE MUESTRARIO" value={newPieza.nombre} onChange={(e) => setNewPieza(prev => ({ ...prev, nombre: e.target.value }))} className="w-full bg-yeikar-tertiary/20 border border-yeikar-secondary-light/10 rounded-xl px-4 py-2.5 text-sm text-yeikar-neutral focus:outline-none focus:border-yeikar-primary uppercase" />
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs font-bold text-yeikar-secondary mb-1">Precio (USD) *</label>
                  <input type="number" min="0" step="0.01" required placeholder="Ej. 1500" value={newPieza.precio_usd} onChange={(e) => setNewPieza(prev => ({ ...prev, precio_usd: e.target.value }))} className="w-full bg-yeikar-tertiary/20 border border-yeikar-secondary-light/10 rounded-xl px-4 py-2.5 text-sm text-yeikar-neutral focus:outline-none focus:border-yeikar-primary font-mono" />
                </div>
                <div>
                  <label className="block text-xs font-bold text-yeikar-secondary mb-1">Cantidad</label>
                  <input type="number" min="0" step="1" placeholder="Ej. 1 (0 si aún no existe y la vas a fabricar)" value={newPieza.cantidad} onChange={(e) => setNewPieza(prev => ({ ...prev, cantidad: e.target.value }))} className="w-full bg-yeikar-tertiary/20 border border-yeikar-secondary-light/10 rounded-xl px-4 py-2.5 text-sm text-yeikar-neutral focus:outline-none focus:border-yeikar-primary font-mono" />
                </div>
              </div>
              <div>
                <label className="block text-xs font-bold text-yeikar-secondary mb-1">Foto de la pieza <span className="text-yeikar-neutral/40 font-normal">(opcional · se comprime sola)</span></label>
                <div className="flex items-center gap-3">
                  {fotoPiezaPreview ? (
                    <img src={fotoPiezaPreview} alt="Vista previa" className="w-16 h-16 rounded-lg object-cover border border-yeikar-secondary-light/15" />
                  ) : (
                    <span className="w-16 h-16 rounded-lg bg-yeikar-tertiary flex items-center justify-center text-yeikar-secondary/40 text-[10px] font-bold">SIN FOTO</span>
                  )}
                  <div className="flex flex-col gap-2 flex-1">
                    <button
                      type="button"
                      onClick={() => cameraInputRef.current?.click()}
                      className="py-2 bg-yeikar-tertiary hover:bg-yeikar-secondary-light/15 text-yeikar-secondary rounded-xl font-bold text-xs transition-colors flex items-center justify-center gap-1.5"
                    >
                      <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 9a2 2 0 012-2h2l1-2h8l1 2h2a2 2 0 012 2v8a2 2 0 01-2 2H5a2 2 0 01-2-2V9z" /><circle cx="12" cy="13" r="3" /></svg>
                      Tomar foto
                    </button>
                    <button
                      type="button"
                      onClick={() => galleryInputRef.current?.click()}
                      className="py-2 bg-yeikar-tertiary hover:bg-yeikar-secondary-light/15 text-yeikar-secondary rounded-xl font-bold text-xs transition-colors flex items-center justify-center gap-1.5"
                    >
                      <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" /></svg>
                      Desde galería
                    </button>
                  </div>
                  <input ref={cameraInputRef} type="file" accept="image/*" capture="environment" className="hidden" onChange={handleFotoPieza} />
                  <input ref={galleryInputRef} type="file" accept="image/*" className="hidden" onChange={handleFotoPieza} />
                </div>
                {fotoPieza && (
                  <button type="button" onClick={quitarFotoPieza} className="mt-1.5 text-[10px] font-bold text-red-600 hover:underline">
                    Quitar foto
                  </button>
                )}
              </div>
              <p className="text-[11px] text-yeikar-neutral/50">
                Se registrará en {ubicacionesExhibicion[0]?.nombre || 'la ubicación de exhibición'} como pieza única. El precio en dólares es el de venta (lo sugiere el cotizador).
              </p>
              <div className="flex gap-3 pt-3 border-t border-yeikar-secondary-light/5">
                <button type="button" onClick={() => setShowPiezaModal(false)} className="flex-1 py-2.5 bg-yeikar-tertiary hover:bg-yeikar-secondary-light/15 text-yeikar-secondary rounded-xl font-bold font-headline text-sm transition-colors">Cancelar</button>
                <button type="submit" disabled={savingPieza} className="flex-1 py-2.5 bg-yeikar-primary hover:bg-yeikar-primary-dark text-yeikar-neutral rounded-xl font-bold font-headline text-sm transition-all disabled:opacity-50">{savingPieza ? 'Registrando...' : 'Registrar'}</button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Modal Orden de Producción (pieza de exhibición) */}
      {producirPieza && (
        <div className="fixed inset-0 bg-yeikar-secondary/60 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-3xl shadow-xl max-w-md w-full overflow-hidden border border-yeikar-secondary-light/10">
            <div className="bg-gradient-to-r from-yeikar-secondary to-yeikar-secondary-light text-white px-6 py-5">
              <h3 className="font-headline font-black text-lg">Orden de Producción</h3>
              <p className="text-xs text-white/70">Fabricar la pieza sin pedido de cliente</p>
            </div>
            <form onSubmit={handleProducirPieza} className="p-6 space-y-4 font-body">
              <div className="bg-yeikar-tertiary/10 border border-yeikar-secondary-light/10 rounded-xl px-4 py-3">
                <p className="text-xs text-yeikar-neutral/50">Se creará una orden de producción para</p>
                <p className="font-headline font-black text-yeikar-secondary text-sm mt-0.5">{producirPieza.nombre}</p>
              </div>
              <div className="space-y-1.5">
                <p className="text-xs text-yeikar-neutral/60">
                  La orden entra al <b>Kanban de Producción</b> como una tarjeta sin cliente (marcada "EXHIBICIÓN"):
                </p>
                <ul className="text-[11px] text-yeikar-neutral/50 list-disc pl-4 space-y-1">
                  <li>Etapas por área (Ebanistería, Tapicería, Pintura...)</li>
                  <li>Consumos de materiales → descuentan inventario de insumos</li>
                  <li>Mano de obra → nómina destajo</li>
                  <li>Al finalizar: costos calculados y la pieza entra sola al showroom con su costo real</li>
                </ul>
              </div>
              <div className="flex gap-3 pt-3 border-t border-yeikar-secondary-light/5">
                <button type="button" onClick={() => setProducirPieza(null)} className="flex-1 py-2.5 bg-yeikar-tertiary hover:bg-yeikar-secondary-light/15 text-yeikar-secondary rounded-xl font-bold font-headline text-sm transition-colors">Cancelar</button>
                <button type="submit" disabled={savingProducir} className="flex-1 py-2.5 bg-yeikar-primary hover:bg-yeikar-primary-dark text-yeikar-neutral rounded-xl font-bold font-headline text-sm transition-all disabled:opacity-50">{savingProducir ? 'Creando...' : 'Crear Orden'}</button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
