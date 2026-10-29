import { useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import html2canvas from 'html2canvas';
import { jsPDF } from 'jspdf';
import { cotizacionService, Quote, QuoteCreate, Product, CalculationResult, QuoteDetail, Moneda } from '../services/cotizacionService';
import { clienteService, Client } from '../services/clienteService';
import { pedidoService } from '../services/pedidoService';
import { ventaService, VentaDetalle, METODOS_PAGO, cargarMetodosPago, labelMetodoPago, type MetodoPagoOption } from '../services/ventaService';
import { formatCurrency, nombreMoneda, resolverParMonedas, convertirMonedaHumana, extractErrorMessage } from '../utils/format';
import { normalizarEstructuraCostos } from '../utils/estructuraCostos';
import { hoyVE } from '../utils/fechas';
import {
  dimensionalidad,
  factorCapturaABase,
  cantidadBaseDesdeCaptura,
  precioBaseDesdeCaptura,
  precioCapturaDesdeBase,
  redondear4,
  type Dimensionalidad,
  type UnidadCaptura,
} from '../utils/unidades';
import EstructuraCostos from '../components/EstructuraCostos';
import DocumentoCotizacion from '../components/Expediente/DocumentoCotizacion';

import api from '../services/api';
import { productosService, type Material, type PromocionObsequio } from '../services/productosService';
import { inventarioService } from '../services/inventarioService';
import { subirAdjunto, TIPO_ADJUNTO } from '../services/adjuntosService';
import ConfirmDialog from '../components/ui/ConfirmDialog';
import { SearchSelect, ResponsiveDataTable, MontoInput, type DataColumn } from '../components/ui';
import { useToast } from '../context/ToastContext';
import { useAuth } from '../context/AuthContext';
import AdjuntoImagen from '../components/AdjuntoImagen';
import ProductSelectorModal from '../components/ProductSelectorModal';
import PiezasJuegoEditor, { validarPiezasJuego, type PiezaJuegoForm } from '../components/Cotizaciones/PiezasJuegoEditor';
import { Package, Plus, Loader2, Wrench, Truck } from 'lucide-react';
import { useDebouncedValue } from '../hooks/useDebouncedValue';
import { produccionService } from '../services/produccionService';

interface CotizacionItemForm {
  producto_id: string;
  material_id: string;
  tipo_item: 'FABRICADO' | 'REVENTA' | 'INSUMO' | 'REPARACION' | 'SERVICIO';
  cantidad: number;
  ancho: string;
  largo: string;
  ganancia: string;
  impuesto: string;
  descripcion_especifica?: string;
  observaciones: string;
  calcResult: CalculationResult | null;
  calcLoading: boolean;
  receta_personalizada?: any[] | null;
  /** Costo real del insumo suelto (COP): compra + pasada, desde la última entrada.
   *  SIEMPRE por unidad base del material (m³/m), no por la unidad capturada. */
  insumoCosto?: { costo_compra: number; pasada_unitaria: number; costo_real: number } | null;
  /** Captura flexible de insumos: '' = unidad base; 'CM'/'M' = convertida. */
  unidadCaptura?: UnidadCaptura | '';
  /** Equivalencia en la unidad del inventario (m³/m), 4 decimales. */
  cantidadBase?: number | null;
  /** Unidad base y dimensionalidad del material seleccionado. */
  materialUnidad?: string | null;
  materialDimension?: Dimensionalidad;
  /** El precio del insumo se cargó solo desde su costo real (no lo escribió
   *  el usuario). Si el usuario lo edita, pasa a false y no se vuelve a tocar. */
  precioAuto?: boolean;
  /** Promo obsequio: renglón del plástico de regalo (precio 0, ligado al colchón). */
  es_obsequio?: boolean;
  /** Piezas del juego (opcional): se producen y costean por separado. */
  piezas?: PiezaJuegoForm[];
}

/** Piezas del juego listas para la API (el precio NO viaja: es del renglón). */
function piezasParaPayload(item: CotizacionItemForm) {
  return (item.piezas ?? []).map((p) => ({
    nombre: p.nombre.trim(),
    cantidad: p.cantidad,
    notas: p.notas.trim() || null,
  }));
}

/** Convierte los detalles de una cotización guardada al estado del formulario
 *  para poder EDITARLA. Los precios/costos almacenados ya están en la moneda de
 *  la cotización: el calcResult se construye en esa moneda (conversión
 *  identidad al guardar) y los costos vuelven a per-unidad, de modo que editar
 *  NO recalcula ni altera los montos ya cotizados. */
function itemsDesdeCotizacion(quote: Quote, monedaCodigo: string): CotizacionItemForm[] {
  return (quote.detalles || []).map((d) => {
    const cantidad = d.cantidad || 1;
    const calcResult: CalculationResult = {
      costo_materiales: (d.costo_materiales ?? 0) / cantidad,
      costo_mano_obra: (d.costo_mano_obra ?? 0) / cantidad,
      costo_gastos_indirectos: (d.costo_gastos ?? 0) / cantidad,
      costo_total: (d.costo_total ?? 0) / cantidad,
      impuesto_porcentaje: 0,
      impuestos: 0,
      base_con_impuestos: d.precio,
      precio_sugerido: d.precio,
      precio_venta: d.precio,
      materiales_detalle: [],
      moneda_codigo: monedaCodigo,
    };
    if (d.tipo_item === 'INSUMO') {
      // El costo guardado es el TOTAL del renglón; para la referencia se
      // vuelve a costo por unidad BASE del inventario (m³), no por cm.
      const cantidadBase = d.cantidad_base ?? d.cantidad;
      const unidadBase = d.material?.unidad_medida?.abreviatura ?? null;
      return {
        producto_id: '',
        material_id: d.material_id ? String(d.material_id) : '',
        tipo_item: 'INSUMO',
        cantidad: d.cantidad,
        ancho: '',
        largo: '',
        ganancia: '',
        impuesto: '',
        descripcion_especifica: '',
        observaciones: d.observaciones || '',
        calcResult,
        calcLoading: false,
        receta_personalizada: null,
        unidadCaptura: d.unidad_captura ?? '',
        cantidadBase,
        materialUnidad: unidadBase,
        materialDimension: dimensionalidad(unidadBase),
        precioAuto: false,
        insumoCosto: {
          costo_compra: 0,
          pasada_unitaria: 0,
          costo_real: (d.costo_total ?? 0) / (cantidadBase || 1),
        },
      };
    }
    return {
      producto_id: d.producto_id ? String(d.producto_id) : '',
      material_id: '',
      tipo_item: d.tipo_item || 'FABRICADO',
      cantidad: d.cantidad,
      ancho: d.ancho ? String(d.ancho) : '',
      largo: d.largo ? String(d.largo) : '',
      ganancia: '',
      impuesto: '',
      descripcion_especifica: d.descripcion_especifica || d.observaciones || '',
      observaciones: d.observaciones || '',
      calcResult,
      calcLoading: false,
      receta_personalizada: d.receta_personalizada || null,
      piezas: (d.piezas || []).map((p) => ({
        nombre: p.nombre,
        cantidad: Number(p.cantidad) || 1,
        notas: p.notas || '',
      })),
      es_obsequio: d.es_obsequio || false,
    };
  });
}

// ── Clasificaciones permitidas al crear un producto desde la cotización ──
// Son solo estas tres: el resto del catálogo (Cama, Comedor, PIEZA ÚNICA...)
// sigue existiendo para los productos ya creados, pero no se ofrece al alta
// rápida desde una cotización.
const normalizarClasificacion = (nombre: string): string =>
  nombre.normalize('NFD').replace(/[\u0300-\u036f]/g, '').trim().toUpperCase();

const esClasificacionNuevoProducto = (nombre: string): boolean => {
  const n = normalizarClasificacion(nombre);
  return n === 'FABRICADO' || n === 'REVENDIDO' || n.startsWith('PLASTIC');
};

/** Revendido y Plástico se manejan como stock (no pasan por producción). */
const esClasificacionStock = (nombre: string | undefined): boolean => {
  const n = normalizarClasificacion(nombre ?? '');
  return n === 'REVENDIDO' || n.startsWith('PLASTIC');
};

const etiquetaClasificacion = (nombre: string): string => {
  const n = normalizarClasificacion(nombre);
  if (n === 'FABRICADO') return 'FABRICADO';
  if (n === 'REVENDIDO') return 'REVENDIDO';
  if (n.startsWith('PLASTIC')) return 'PLÁSTICO';
  return nombre.toUpperCase();
};

// Ordena productos por tipo (id del catálogo) y nombre dentro de cada tipo,
// para que el selector agrupado muestre Fabricado → Revendido → Cama → ...
// (mañana: Comedor, Silla... aparecen solos al crearse en el catálogo).
const ordenarProductosPorTipo = (prods: Product[]): Product[] =>
  [...prods].sort((a, b) => {
    const ta = a.tipo_producto_id ?? Number.MAX_SAFE_INTEGER;
    const tb = b.tipo_producto_id ?? Number.MAX_SAFE_INTEGER;
    if (ta !== tb) return ta - tb;
    return a.nombre.localeCompare(b.nombre);
  });

// ── Promo obsequio (colchón → plástico) ────────────────────────────────────
// El renglón del obsequio viaja en la cotización a precio 0 y marcado
// es_obsequio: el backend lo detecta como ya presente y no lo duplica al
// convertir el pedido; al facturar descuenta el stock del plástico.

type PromosPorColchon = Map<number, PromocionObsequio>;

/** Unidades totales por obsequio según los renglones de colchón con promo. */
function totalesObsequioPorPromo(
  items: CotizacionItemForm[],
  promos: PromosPorColchon,
): Map<number, number> {
  const totales = new Map<number, number>();
  for (const it of items) {
    if (it.es_obsequio || it.tipo_item !== 'REVENTA' || !it.producto_id) continue;
    const promo = promos.get(Number(it.producto_id));
    if (!promo) continue;
    totales.set(promo.obsequio_id, (totales.get(promo.obsequio_id) || 0) + (it.cantidad || 0));
  }
  return totales;
}

/** Ajusta la cantidad de los renglones de obsequio (o los quita si el colchón
 *  ya no está). NO agrega renglones nuevos: eso ocurre al seleccionar el
 *  colchón (asegurarObsequio). Devuelve el MISMO arreglo si no hubo cambios. */
function sincronizarCantidadesObsequio(
  items: CotizacionItemForm[],
  promos: PromosPorColchon,
): CotizacionItemForm[] {
  if (promos.size === 0) return items;
  const totales = totalesObsequioPorPromo(items, promos);
  let cambio = false;
  const next: CotizacionItemForm[] = [];
  for (const it of items) {
    if (it.es_obsequio && it.producto_id) {
      const total = totales.get(Number(it.producto_id)) || 0;
      if (total <= 0) {
        cambio = true;
        continue; // el colchón ya no está: se va el regalo
      }
      if (it.cantidad !== total) {
        next.push({ ...it, cantidad: total });
        cambio = true;
        continue;
      }
    }
    next.push(it);
  }
  return cambio ? next : items;
}

/** Al seleccionar un colchón con promo, agrega su renglón de obsequio (una
 *  sola vez, justo después del colchón) y sincroniza cantidades. */
function asegurarObsequio(
  items: CotizacionItemForm[],
  colchonId: number,
  promos: PromosPorColchon,
): CotizacionItemForm[] {
  const promo = promos.get(colchonId);
  if (!promo) return sincronizarCantidadesObsequio(items, promos);
  const yaExiste = items.some(
    (it) => it.es_obsequio && Number(it.producto_id) === promo.obsequio_id,
  );
  if (yaExiste) return sincronizarCantidadesObsequio(items, promos);
  const total = totalesObsequioPorPromo(items, promos).get(promo.obsequio_id) || 0;
  if (total <= 0) return items;
  const nuevo: CotizacionItemForm = {
    producto_id: String(promo.obsequio_id),
    material_id: '',
    tipo_item: 'REVENTA',
    cantidad: total,
    ancho: '',
    largo: '',
    ganancia: '',
    impuesto: '',
    descripcion_especifica: 'OBSEQUIO PROMO',
    observaciones: '',
    calcResult: null,
    calcLoading: false,
    receta_personalizada: null,
    es_obsequio: true,
  };
  let insertAt = items.length;
  items.forEach((it, i) => {
    if (!it.es_obsequio && Number(it.producto_id) === colchonId) insertAt = i + 1;
  });
  const next = [...items.slice(0, insertAt), nuevo, ...items.slice(insertAt)];
  return sincronizarCantidadesObsequio(next, promos);
}

/** Input decimal para cantidades de insumo.
 *
 *  Un <input type="number"> controlado no deja teclear "0.1128": al escribir
 *  el punto el estado numérico vuelve a 0 y el navegador además valida el step
 *  (el famoso "0.1 o 0.2"). Este input guarda el TEXTO mientras el usuario
 *  escribe y solo publica números válidos al formulario. Al cambiar de unidad
 *  (cm ↔ m³) el padre cambia `value` y el texto se sincroniza. */
function CantidadDecimalInput({
  value,
  onChange,
  className,
}: {
  value: number;
  onChange: (n: number) => void;
  className?: string;
}) {
  const [texto, setTexto] = useState(() => (value ? String(value) : ''));
  const enfocado = useRef(false);

  useEffect(() => {
    if (!enfocado.current) setTexto(value ? String(value) : '');
  }, [value]);

  const normalizar = (t: string): number | null => {
    const n = parseFloat(t.replace(',', '.'));
    return Number.isFinite(n) && n > 0 ? n : null;
  };

  return (
    <input
      type="text"
      inputMode="decimal"
      value={texto}
      onFocus={() => { enfocado.current = true; }}
      onChange={(e) => {
        const t = e.target.value;
        setTexto(t);
        const n = normalizar(t);
        if (n !== null) onChange(n);
      }}
      onBlur={() => {
        enfocado.current = false;
        const n = normalizar(texto);
        if (n !== null) {
          onChange(n);
          setTexto(String(n));
        } else {
          setTexto(value ? String(value) : '');
        }
      }}
      className={className}
    />
  );
}

/** Resultado de cálculo de un INSUMO: el costo y el precio son POR UNIDAD
 *  DE VENTA (cm/m³), no por unidad base del inventario. */
function calcularResultadoInsumo(costoRealUnidadVenta: number, precio: number): CalculationResult {
  return {
    costo_materiales: costoRealUnidadVenta,
    costo_mano_obra: 0,
    costo_gastos_indirectos: 0,
    costo_total: costoRealUnidadVenta,
    impuesto_porcentaje: 0,
    impuestos: 0,
    base_con_impuestos: precio,
    precio_sugerido: precio,
    precio_venta: precio,
    materiales_detalle: [],
    moneda_codigo: 'COP',
  };
}

export default function Cotizaciones() {
  const toast = useToast();
  const { user, esAdmin } = useAuth();
  const lastCalcErrorRef = useRef('');
  const navigate = useNavigate();
  const [confirmDeleteId, setConfirmDeleteId] = useState<number | null>(null);
  const [quotes, setQuotes] = useState<Quote[]>([]);
  const [clients, setClients] = useState<Client[]>([]);
  const [products, setProducts] = useState<Product[]>([]);
  const [materiales, setMateriales] = useState<any[]>([]);

  // Promos activas colchón → plástico de regalo (una vez al montar)
  const [promosObsequio, setPromosObsequio] = useState<PromocionObsequio[]>([]);
  useEffect(() => {
    let active = true;
    productosService.getPromocionesObsequio(true)
      .then((r) => { if (active) setPromosObsequio(r); })
      .catch(() => { if (active) setPromosObsequio([]); });
    return () => { active = false; };
  }, []);
  const promosPorColchon = useMemo<PromosPorColchon>(() => {
    const m: PromosPorColchon = new Map();
    for (const p of promosObsequio) m.set(p.colchon_id, p);
    return m;
  }, [promosObsequio]);
  
  const [search, setSearch] = useState('');
  const [soloMesActual, setSoloMesActual] = useState(true);
  // Filtro de estado: por defecto solo cotizaciones activas (borrador/enviada/aprobada);
  // las rechazadas/vencidas quedan ocultas salvo que se pida el histórico.
  const [filtroEstadoCot, setFiltroEstadoCot] = useState<string>('ACTIVAS');
  const [selectedMonth, setSelectedMonth] = useState(new Date().getMonth() + 1);
  const [selectedYear, setSelectedYear] = useState(new Date().getFullYear());
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  // Error del formulario de cotización (y sus sub-modales): se muestra DENTRO
  // del modal; el `error` de página queda para fallos de carga/listado.
  const [errorForm, setErrorForm] = useState('');

  // Modals state
  const [isFormOpen, setIsFormOpen] = useState(false);
  const [isConvertOpen, setIsConvertOpen] = useState(false);
  const [selectedQuoteForConvert, setSelectedQuoteForConvert] = useState<Quote | null>(null);

  // Bloquea el scroll del fondo mientras el editor paramétrico está abierto
  // (mismo comportamiento que el Modal compartido; sin esto hay doble scroll).
  useEffect(() => {
    if (!isFormOpen) return;
    const prev = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => { document.body.style.overflow = prev; };
  }, [isFormOpen]);

  // States for printing
  const [isPrintModalOpen, setIsPrintModalOpen] = useState(false);
  const [selectedQuoteForPrint, setSelectedQuoteForPrint] = useState<Quote | null>(null);
  const [printDiscount, setPrintDiscount] = useState('0');
  const [printIva, setPrintIva] = useState('0');
  const [printCompanyRif, setPrintCompanyRif] = useState('J-50146039-3');
  const [printCompanyAddress, setPrintCompanyAddress] = useState('AV. INTERCOMUNAL CON CALLE 16 LOCAL Nro 15-205, BARRIO SIMÓN BOLÍVAR, UREÑA, TÁCHIRA');
  const [printCompanyPhone, setPrintCompanyPhone] = useState('+58 412-1234567');
  const [isGeneratingPdf, setIsGeneratingPdf] = useState(false);
  const [associatedVenta, setAssociatedVenta] = useState<VentaDetalle | null>(null);

  // Convert Form state
  const [deliveryDate, setDeliveryDate] = useState('');
  const [isConverting, setIsConverting] = useState(false);
  const [convertError, setConvertError] = useState('');

  // Adelanto de la conversión (opcional)
  const [adelantoModo, setAdelantoModo] = useState<'pct' | 'monto'>('pct');
  const [adelantoPct, setAdelantoPct] = useState('');
  const [adelantoMonto, setAdelantoMonto] = useState('');
  const [adelantoMonedaId, setAdelantoMonedaId] = useState<number>(1);
  const [adelantoTrm, setAdelantoTrm] = useState('');
  const [adelantoMetodo, setAdelantoMetodo] = useState('');
  // Fecha del abono inicial: el cliente pudo abonar ANTES de convertir.
  // Por defecto hoy (VE); si se deja vacía, el servidor guarda hoy.
  const [fechaAdelanto, setFechaAdelanto] = useState(hoyVE());
  // Métodos de pago: cuentas reales (metodo_caja) con fallback al estático.
  const [metodosPago, setMetodosPago] = useState<MetodoPagoOption[]>(METODOS_PAGO.map((m) => ({ ...m })));

  // Create/Edit Form state (multi-item)
  const [editingQuote, setEditingQuote] = useState<Quote | null>(null);
  const [selectedClientId, setSelectedClientId] = useState('');
  // Label del cliente actualmente seleccionado: el selector de cliente es async,
  // así que el trigger necesita saber qué mostrar cuando el valor ya está fijado
  // (cliente recién creado o cliente de una cotización en edición).
  const [clienteSeleccionado, setClienteSeleccionado] = useState<{ value: number; label: string } | null>(null);
  // Fecha de la cotización: la elige el usuario (permite fechar hacia atrás
  // al pasar cotizaciones viejas). Default: hoy en hora Venezuela.
  const [fechaCotizacion, setFechaCotizacion] = useState('');
  const [observaciones, setObservaciones] = useState('');
  const [items, setItems] = useState<CotizacionItemForm[]>([]);
  const [isProductSelectorOpen, setIsProductSelectorOpen] = useState(false);
  // Piezas de exhibición en retrabajo (chip "En retrabajo" en el selector):
  // están en el taller y no se pueden vender hasta que vuelvan al showroom.
  const [piezasEnRetrabajo, setPiezasEnRetrabajo] = useState<number[]>([]);
  const [productSelectorModo, setProductSelectorModo] = useState<'todos' | 'fabricados' | 'reventa' | 'exhibicion'>('todos');
  const [productSelectorTargetIndex, setProductSelectorTargetIndex] = useState<number | null>(null);

  // Al abrir el catálogo, refrescar qué piezas de exhibición están en retrabajo
  // (sin permiso de Producción o sin red, el chip simplemente no se muestra).
  useEffect(() => {
    if (!isProductSelectorOpen) return;
    produccionService
      .getRetrabajosAbiertos()
      .then((rs) =>
        setPiezasEnRetrabajo(rs.map((r) => r.producto_id).filter((id): id is number => id != null)),
      )
      .catch(() => setPiezasEnRetrabajo([]));
  }, [isProductSelectorOpen]);

  // ── "Producto nuevo" desde la cotización (nombre + tipo + foto + precio) ──
  const [showNuevoProductoModal, setShowNuevoProductoModal] = useState(false);
  const [tiposProducto, setTiposProducto] = useState<{ id: number; nombre: string }[]>([]);
  const [npForm, setNpForm] = useState({ nombre: '', tipo_producto_id: '', precio: '', moneda_id: '1' });
  // Varias fotos a la vez: la PRIMERA que se elija es la portada (sale en la
  // cotización; las demás como vistas adicionales en la Hoja de Trabajo).
  const [fotosNp, setFotosNp] = useState<{ file: File; url: string }[]>([]);
  const [savingNp, setSavingNp] = useState(false);
  const npCameraRef = useRef<HTMLInputElement>(null);
  const npGalleryRef = useRef<HTMLInputElement>(null);

  // ── "Definir precio" para productos existentes sin precio ──
  const [definirPrecioProd, setDefinirPrecioProd] = useState<Product | null>(null);
  const [dpPrecio, setDpPrecio] = useState('');
  const [dpMoneda, setDpMoneda] = useState('1');
  const [savingDp, setSavingDp] = useState(false);

  // ── "Cliente nuevo" desde la cotización (mismos datos que el módulo Clientes) ──
  const [showNuevoClienteModal, setShowNuevoClienteModal] = useState(false);
  const [ncForm, setNcForm] = useState({ nombre: '', telefono: '', cedula: '', direccion: '', ciudad: '', estado: '', observaciones: '' });
  const [savingNc, setSavingNc] = useState(false);

  // Modal de personalización de receta ad-hoc por renglón
  const [showPersonalizarModal, setShowPersonalizarModal] = useState(false);
  const [verEstructuraModal, setVerEstructuraModal] = useState(false);
  const [personalizarIndex, setPersonalizarIndex] = useState<number | null>(null);
  const [personalizarSecciones, setPersonalizarSecciones] = useState<any[]>([]);
  const [modalPreviewCalc, setModalPreviewCalc] = useState<CalculationResult | null>(null);
  const [modalPreviewLoading, setModalPreviewLoading] = useState(false);

  // Para agregar un insumo ad-hoc en el modal
  const [addMaterialSearch, setAddMaterialSearch] = useState('');
  const [showAddMaterialDropdown, setShowAddMaterialDropdown] = useState(false);
  const [addMaterialSeccionIndex, setAddMaterialSeccionIndex] = useState<number | null>(null);
  // Búsqueda server-side de materiales para el modal de "agregar material a
  // sección": el catálogo completo no se baja al cliente.
  const [addMaterialResultados, setAddMaterialResultados] = useState<Material[]>([]);
  const [addMaterialCargando, setAddMaterialCargando] = useState(false);
  const addMaterialSearchDeb = useDebouncedValue(addMaterialSearch, 250);

  useEffect(() => {
    if (!showAddMaterialDropdown) return;
    let active = true;
    setAddMaterialCargando(true);
    productosService
      .getMateriales(addMaterialSearchDeb.trim() || undefined)
      .then((r) => { if (active) setAddMaterialResultados(r.slice(0, 15)); })
      .catch(() => { if (active) setAddMaterialResultados([]); })
      .finally(() => { if (active) setAddMaterialCargando(false); });
    return () => { active = false; };
  }, [showAddMaterialDropdown, addMaterialSearchDeb]);

  // Para agregar un costo de producción ad-hoc
  const [showAddCostModal, setShowAddCostModal] = useState(false);
  const [addCostSeccionIndex, setAddCostSeccionIndex] = useState<number | null>(null);
  const [addCostForm, setAddCostForm] = useState({ nombre: '', porcentaje: '', costo_base: '' });

  // Rango/mueble seleccionado para ver desglose detallado de secciones en la barra lateral
  const [desgloseIndex, setDesgloseIndex] = useState<number>(0);

  // Currency state
  const [currencies, setCurrencies] = useState<Moneda[]>([]);
  const [selectedMonedaId, setSelectedMonedaId] = useState<number>(1);
  const [tasaCambio, setTasaCambio] = useState<number>(1);

  // ── Tasas del día para renglones en moneda extranjera (reventa) ──────────
  // El backend devuelve los montos de un producto de reventa EN SU MONEDA; la
  // conversión a la moneda de la cotización se hace aquí UNA sola vez con la
  // tasa que el usuario ingresa y confirma. Nunca una tasa en silencio: el
  // campo es visible, se pre-rellena con la última tasa registrada (Tasas de
  // Cambio) y es requerido para guardar.
  const [tasasDia, setTasasDia] = useState<Record<string, string>>({});
  const tasasRegistradasRef = useRef<Record<string, number>>({});

  const selectedMoneda = currencies.find(c => c.id === selectedMonedaId);
  const currencyCode = selectedMoneda?.codigo || 'COP';

  // ── Derivados del modal de conversión (adelanto) ──────────────────────────
  const quoteEnConversion = selectedQuoteForConvert;
  const quoteTotal = Number(quoteEnConversion?.total_estimado) || 0;
  const quoteMoneda = currencies.find((c) => c.id === quoteEnConversion?.moneda_id);
  const monedaAdelantoSel = currencies.find((c) => c.id === adelantoMonedaId);

  // La tasa del abono SIEMPRE la define el usuario cuando la moneda de pago
  // difiere de la moneda de la cotización. Nunca se deduce de la tasa congelada
  // de la cotización (puede pagarse días después con otra tasa).
  const quoteCod = quoteMoneda?.codigo || 'COP';
  const adelantoCod = monedaAdelantoSel?.codigo || 'COP';
  const monedasIguales = adelantoMonedaId === quoteEnConversion?.moneda_id;
  const parAdelanto = resolverParMonedas(quoteCod, adelantoCod);
  const tasaHumanaAbono = Number(adelantoTrm) || 0;
  const tasaAbonoValida = monedasIguales || tasaHumanaAbono > 0;

  const pctAbono = Number(adelantoPct) || 0;
  const montoFijoAbono = Number(adelantoMonto) || 0;
  const abonoActivo =
    (adelantoModo === 'pct' && pctAbono > 0) || (adelantoModo === 'monto' && montoFijoAbono > 0);

  // Monto del abono expresado en la moneda de la cotización (para validar el tope).
  const abonoEnMonedaCotizacion =
    adelantoModo === 'pct'
      ? (quoteTotal * pctAbono) / 100
      : (monedasIguales ? montoFijoAbono : convertirMonedaHumana(montoFijoAbono, adelantoCod, quoteCod, tasaHumanaAbono));

  // Monto que realmente se registra como pago, en la moneda que elige el cliente.
  const abonoMontoPago =
    adelantoModo === 'pct'
      ? (monedasIguales ? (quoteTotal * pctAbono) / 100 : convertirMonedaHumana((quoteTotal * pctAbono) / 100, quoteCod, adelantoCod, tasaHumanaAbono))
      : montoFijoAbono;

  const abonoExcedeTotal = abonoEnMonedaCotizacion > quoteTotal + 0.01;

  const fetchInitialData = async () => {
    try {
      const [cls, prds, mats, currs, metodos] = await Promise.all([
        clienteService.getAll(),
        cotizacionService.getProducts(),
        productosService.getMateriales(),
        cotizacionService.fetchCurrencies(),
        cargarMetodosPago().catch(() => [] as MetodoPagoOption[]),
      ]);
      setClients(cls);
      setProducts(ordenarProductosPorTipo(prds));
      setMateriales(mats);
      setCurrencies(currs);
      if (metodos.length > 0) setMetodosPago(metodos);
    } catch (err) {
      console.error('Error fetching initial data:', err);
    }
  };

  // Precargar la última tasa registrada por moneda (para prellenar "Tasas del
  // día" del formulario de cotización). Preferencia: la más reciente con fecha
  // <= hoy; si solo hay futuras, la más cercana.
  useEffect(() => {
    if (!currencies.length) return;
    api.get('/tasa/tasas-cambio/', { params: { limit: 200 } })
      .then(({ data }) => {
        const hoy = hoyVE();
        const codigoPorId = new Map(currencies.map((c) => [c.id, c.codigo]));
        const mejores: Record<string, { valor: number; fecha: string }> = {};
        for (const t of data as any[]) {
          if (Number(t.moneda_destino_id) !== 1) continue;
          const cod = codigoPorId.get(Number(t.moneda_origen_id));
          if (!cod) continue;
          const prev = mejores[cod];
          if (!prev) {
            mejores[cod] = { valor: Number(t.valor), fecha: String(t.fecha) };
            continue;
          }
          const tOk = String(t.fecha) <= hoy;
          const pOk = prev.fecha <= hoy;
          if ((tOk && pOk && String(t.fecha) > prev.fecha) || (tOk && !pOk) || (!tOk && !pOk && String(t.fecha) < prev.fecha)) {
            mejores[cod] = { valor: Number(t.valor), fecha: String(t.fecha) };
          }
        }
        tasasRegistradasRef.current = Object.fromEntries(
          Object.entries(mejores).map(([k, v]) => [k, v.valor]),
        );
      })
      .catch((err) => console.error('Error precargando tasas registradas:', err));
  }, [currencies]);

  const fetchQuotes = async (searchTerm?: string) => {
    setLoading(true);
    setError('');
    try {
      const data = await cotizacionService.getAll(
        searchTerm,
        soloMesActual,
        soloMesActual ? undefined : selectedMonth,
        soloMesActual ? undefined : selectedYear
      );
      setQuotes(data);
    } catch (err: any) {
      console.error(err);
      setError('Error al cargar cotizaciones.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchInitialData();
  }, []);

  useEffect(() => {
    const timer = setTimeout(() => {
      fetchQuotes(search);
    }, 300);
    return () => clearTimeout(timer);
  }, [search, soloMesActual, selectedMonth, selectedYear]);

  // Trigger calculation individually for each item
  const calculateItemPrice = async (index: number, pId: string, w: string, l: string, g: string, overrideReceta?: any[] | null, imp?: string) => {
    if (!pId) {
      updateItemField(index, 'calcResult', null);
      return;
    }
    
    const customRecipe: any[] | null = overrideReceta !== undefined ? overrideReceta : null;
    setItems((prevItems) => {
      const newItems = [...prevItems];
      newItems[index] = { ...newItems[index], calcLoading: true };
      return newItems;
    });

    try {
      const impuestoItem = Number(imp ?? items[index]?.impuesto ?? 0) || 0;
      let res;
      if (customRecipe && customRecipe.length > 0) {
        res = await cotizacionService.recalculateCustomRecipe(Number(g) || 0, customRecipe, impuestoItem);
      } else {
        res = await cotizacionService.calculatePrice(Number(pId), {
          ancho: Number(w) || 1.0,
          largo: Number(l) || 1.0,
          ganancia: Number(g) || 0,
          impuesto: impuestoItem,
        });
      }
      
      setItems((prevItems) => {
        const newItems = [...prevItems];
        newItems[index] = { ...newItems[index], calcResult: res, calcLoading: false };
        return newItems;
      });
      lastCalcErrorRef.current = '';
    } catch (err: any) {
      console.error('Error calculating price for item:', err);
      // Superficiar el error real (ej. falta registrar la tasa de cambio de un
      // producto en USD). Una vez por mensaje distinto para no spamear toasts
      // mientras se escribe en el formulario.
      const detail = String(err?.response?.data?.detail || err?.message || '');
      if (detail && detail !== lastCalcErrorRef.current) {
        lastCalcErrorRef.current = detail;
        toast.error(detail);
      }
      setItems((prevItems) => {
        const newItems = [...prevItems];
        newItems[index] = { ...newItems[index], calcLoading: false };
        return newItems;
      });
    }
  };

  const updateItemField = (index: number, field: keyof CotizacionItemForm, value: any) => {
    // El renglón de obsequio es de solo lectura salvo cantidad (que sigue al
    // colchón): no se le cambia producto, dimensiones, ganancia ni impuestos.
    if (items[index]?.es_obsequio && field !== 'cantidad' && field !== 'observaciones') {
      return;
    }
    setItems((prevItems) => {
      const newItems = [...prevItems];
      newItems[index] = { ...newItems[index], [field]: value };
      
      // Auto-dimensions if product changed (los reventa no tienen dimensiones)
      if (field === 'producto_id') {
        const selectedProd = products.find(p => p.id === Number(value));
        if (selectedProd) {
          newItems[index].ancho = String(selectedProd.ancho_base ?? 1);
          newItems[index].largo = String(selectedProd.largo_base ?? 1);
        }
        newItems[index].receta_personalizada = null;
        newItems[index].piezas = [];
        // Promo obsequio: si el nuevo producto es un colchón con promo, se
        // agrega el renglón del plástico; si dejó de serlo, se ajusta/quita.
        const promo = promosPorColchon.get(Number(value));
        if (promo) return asegurarObsequio(newItems, Number(value), promosPorColchon);
        return sincronizarCantidadesObsequio(newItems, promosPorColchon);
      }

      // Cambió la cantidad del colchón (o el tipo): el regalo la sigue.
      if (field === 'cantidad' || field === 'tipo_item') {
        if (field === 'tipo_item' && value !== 'FABRICADO') {
          newItems[index].piezas = [];
        }
        return sincronizarCantidadesObsequio(newItems, promosPorColchon);
      }

      return newItems;
    });

    // recalculate if relevant field changed
    if (['producto_id', 'ancho', 'largo', 'ganancia', 'impuesto'].includes(field)) {
      setItems((prevItems) => {
        const current = prevItems[index];
        calculateItemPrice(index, current.producto_id, current.ancho, current.largo, current.ganancia, current.receta_personalizada, current.impuesto);
        return prevItems;
      });
    }
  };

  const handleOpenPersonalizarReceta = async (index: number) => {
    const item = items[index];
    if (!item.producto_id) {
      toast.info('Por favor selecciona un mueble primero.');
      return;
    }
    
    setPersonalizarIndex(index);
    
    if (item.receta_personalizada) {
      setPersonalizarSecciones(JSON.parse(JSON.stringify(item.receta_personalizada)));
      setModalPreviewCalc(item.calcResult || null);
      setShowPersonalizarModal(true);
    } else {
      try {
        setItems(prev => {
          const newItems = [...prev];
          newItems[index].calcLoading = true;
          return newItems;
        });
        const res = await api.get(`/producto/${item.producto_id}/receta-estructurada`);
        setPersonalizarSecciones(res.data);
        setShowPersonalizarModal(true);
      } catch (err) {
        console.error('Error al cargar la receta estructurada:', err);
        toast.error('Error al cargar la estructura del mueble.');
      } finally {
        setItems(prev => {
          const newItems = [...prev];
          newItems[index].calcLoading = false;
          return newItems;
        });
      }
    }
  };

  const handleUpdateSeccionPolitica = (seccionIndex: number, field: string, value: string) => {
    setPersonalizarSecciones(prev => {
      const newSecs = [...prev];
      if (!newSecs[seccionIndex].politica) {
        newSecs[seccionIndex].politica = { pct_gastos_seccion: 10, pct_trabajadores: 8, costo_fabricacion: 0 };
      }
      newSecs[seccionIndex].politica[field] = value ? parseFloat(value) : 0;
      return newSecs;
    });
  };

  const handleUpdateInsumoField = (seccionIndex: number, elementoIndex: number, field: string, value: string) => {
    setPersonalizarSecciones(prev => {
      const newSecs = [...prev];
      newSecs[seccionIndex].elementos[elementoIndex][field] =
        field === 'precio_unitario'
          ? (parseFloat(value) || 0)
          : (value ? parseFloat(value) : 0);
      return newSecs;
    });
  };

  const handleRemoveInsumo = (seccionIndex: number, elementoIndex: number) => {
    setPersonalizarSecciones(prev => {
      const newSecs = [...prev];
      newSecs[seccionIndex].elementos = newSecs[seccionIndex].elementos.filter((_: any, i: number) => i !== elementoIndex);
      return newSecs;
    });
  };

  const handleOpenAddMaterial = (seccionIndex: number) => {
    setAddMaterialSeccionIndex(seccionIndex);
    setAddMaterialSearch('');
    setShowAddMaterialDropdown(true);
  };

  const handleAddMaterialToSeccion = (material: any) => {
    if (addMaterialSeccionIndex === null) return;
    setPersonalizarSecciones(prev => {
      const newSecs = [...prev];
      const newEl = {
        id: Date.now(), // ID temporal
        seccion_id: newSecs[addMaterialSeccionIndex].id,
        nombre_insumo_original: material.nombre,
        material_id_normalizado: material.id,
        cantidad: 1,
        unidad_medida: material.unidad_medida?.abreviatura || 'un',
        precio_unitario: material.costo_base,
      };
      newSecs[addMaterialSeccionIndex].elementos.push(newEl);
      return newSecs;
    });
    setShowAddMaterialDropdown(false);
    setAddMaterialSeccionIndex(null);
  };

  const handleOpenAddCost = (seccionIndex: number) => {
    setAddCostSeccionIndex(seccionIndex);
    setAddCostForm({ nombre: '', porcentaje: '', costo_base: '' });
    setShowAddCostModal(true);
  };

  const handleAddCostToSeccion = (e: React.FormEvent) => {
    e.preventDefault();
    if (addCostSeccionIndex === null || !addCostForm.nombre.trim()) return;
    setPersonalizarSecciones(prev => {
      const newSecs = [...prev];
      const newCost = {
        id: Date.now(), // ID temporal
        seccion_id: newSecs[addCostSeccionIndex].id,
        nombre: addCostForm.nombre.trim(),
        porcentaje: addCostForm.porcentaje ? parseFloat(addCostForm.porcentaje) : null,
        costo_base: parseFloat(addCostForm.costo_base) || 0,
      };
      if (!newSecs[addCostSeccionIndex].costos_produccion) {
        newSecs[addCostSeccionIndex].costos_produccion = [];
      }
      newSecs[addCostSeccionIndex].costos_produccion.push(newCost);
      return newSecs;
    });
    setShowAddCostModal(false);
    setAddCostSeccionIndex(null);
  };

  const handleRemoveCost = (seccionIndex: number, costIndex: number) => {
    setPersonalizarSecciones(prev => {
      const newSecs = [...prev];
      newSecs[seccionIndex].costos_produccion = newSecs[seccionIndex].costos_produccion.filter((_: any, i: number) => i !== costIndex);
      return newSecs;
    });
  };

  // Recalcular el preview en vivo dentro del modal cuando cambia personalizarSecciones
  useEffect(() => {
    if (!showPersonalizarModal || personalizarIndex === null || !personalizarSecciones || personalizarSecciones.length === 0) {
      return;
    }
    const item = items[personalizarIndex];
    const ganancia = Number(item?.ganancia) || 0;
    const impuesto = Number(item?.impuesto) || 0;
    
    setModalPreviewLoading(true);
    const timer = setTimeout(async () => {
      try {
        const res = await cotizacionService.recalculateCustomRecipe(ganancia, personalizarSecciones, impuesto);
        setModalPreviewCalc(res);
      } catch (err) {
        console.error('Error recalculando preview en modal:', err);
      } finally {
        setModalPreviewLoading(false);
      }
    }, 200);

    return () => clearTimeout(timer);
  }, [personalizarSecciones, showPersonalizarModal, personalizarIndex]);

  const handleSavePersonalizacion = () => {
    if (personalizarIndex === null) return;
    const index = personalizarIndex;
    const recetaNueva = JSON.parse(JSON.stringify(personalizarSecciones));
    const calcFinal = modalPreviewCalc;

    // Aplicar directamente al renglón la receta y el resultado ya calculado
    setItems(prev => {
      const newItems = [...prev];
      newItems[index] = {
        ...newItems[index],
        receta_personalizada: recetaNueva,
        calcResult: calcFinal || newItems[index].calcResult,
        calcLoading: false,
      };
      return newItems;
    });

    setShowPersonalizarModal(false);
    setPersonalizarIndex(null);
    setModalPreviewCalc(null);
  };

  /** Cambia la unidad de captura de un INSUMO (cm ↔ unidad base) sin mover
   *  el total: convierte cantidad y precio con el mismo factor. */
  const cambiarUnidadInsumo = (index: number, nueva: UnidadCaptura | '') => {
    setItems((prev) => {
      const actual = prev[index];
      if (!actual) return prev;
      const dim = actual.materialDimension ?? 'OTRA';
      const unidadBase = actual.materialUnidad ?? null;
      const factorActual = factorCapturaABase(dim, unidadBase, actual.unidadCaptura ?? '');
      const factorNuevo = factorCapturaABase(dim, unidadBase, nueva);
      const cantidadBase = actual.cantidadBase
        ?? cantidadBaseDesdeCaptura(actual.cantidad, factorActual);
      const cantidad = redondear4(cantidadBase / (factorNuevo || 1));
      const precioActual = Number(actual.calcResult?.precio_venta) || 0;
      const precioBase = precioBaseDesdeCaptura(precioActual, factorActual);
      const precio = precioCapturaDesdeBase(precioBase, factorNuevo);
      const costoVenta = actual.insumoCosto
        ? actual.insumoCosto.costo_real * factorNuevo
        : Number(actual.calcResult?.costo_total) || 0;

      const next = [...prev];
      next[index] = {
        ...actual,
        unidadCaptura: nueva,
        cantidadBase,
        cantidad,
        calcResult: calcularResultadoInsumo(costoVenta, precio),
      };
      return next;
    });
  };

  /** Actualiza la cantidad del INSUMO y su equivalencia en la unidad base. */
  const cambiarCantidadInsumo = (index: number, cantidad: number) => {
    setItems((prev) => {
      const actual = prev[index];
      if (!actual) return prev;
      const factor = factorCapturaABase(
        actual.materialDimension ?? 'OTRA',
        actual.materialUnidad ?? null,
        actual.unidadCaptura ?? '',
      );
      const next = [...prev];
      next[index] = {
        ...actual,
        cantidad,
        cantidadBase: cantidadBaseDesdeCaptura(cantidad, factor),
      };
      return next;
    });
  };

  const addItemInsumo = () => {
    setItems((prev) => [
      ...prev,
      {
        producto_id: '', material_id: '', tipo_item: 'INSUMO', cantidad: 1,
        ancho: '', largo: '', ganancia: '', impuesto: '0',
        descripcion_especifica: '', observaciones: '',
        calcResult: null, calcLoading: false, receta_personalizada: null,
        unidadCaptura: '', cantidadBase: null,
        materialUnidad: null, materialDimension: 'OTRA',
        precioAuto: true,
      }
    ]);
  };

  /** Al elegir material de un INSUMO: carga su unidad/dimensionalidad y
   *  aplica la captura por defecto. Para madera (m³) arranca en cm (cuenta
   *  del taller); para lineales arranca en la unidad base. El costo real se
   *  pide a Inventario (compra + pasada) y se usa como PRECIO POR DEFECTO por
   *  unidad vendida; si el material no tiene costo, el precio se escribe a mano. */
  const aplicarMaterialInsumo = async (index: number, matId: number) => {
    const materialAnterior = items[index]?.material_id;
    const cambioMaterial = !materialAnterior || materialAnterior !== String(matId);
    updateItemField(index, 'material_id', String(matId));
    updateItemField(index, 'insumoCosto', null);

    const mat = await productosService.getMaterial(matId).catch(() => null);
    if (!mat) return;

    const unidadBase = mat.unidad_medida?.abreviatura ?? null;
    const dim = dimensionalidad(unidadBase);
    const unidadCaptura: UnidadCaptura | '' = dim === 'VOLUMEN' ? 'CM' : '';
    const costoBase = Number(mat.costo_base) || 0;

    setItems((prev) => {
      const actual = prev[index];
      if (!actual || actual.material_id !== String(mat.id)) return prev;
      const factor = factorCapturaABase(dim, unidadBase, unidadCaptura);
      const cantidadBase = cantidadBaseDesdeCaptura(actual.cantidad, factor);
      const costoVenta = costoBase * factor;
      // Si el usuario ya escribió un precio, se respeta; si no (o si cambió de
      // material), se precarga el costo real por unidad de venta.
      const precioActual = Number(actual.calcResult?.precio_venta) || 0;
      const usarAuto = cambioMaterial || actual.precioAuto !== false || precioActual === 0;
      const next = [...prev];
      next[index] = {
        ...actual,
        materialUnidad: unidadBase,
        materialDimension: dim,
        unidadCaptura,
        cantidadBase,
        precioAuto: usarAuto,
        insumoCosto: { costo_compra: costoBase, pasada_unitaria: 0, costo_real: costoBase },
        calcResult: calcularResultadoInsumo(costoVenta, usarAuto ? costoVenta : precioActual),
      };
      return next;
    });

    inventarioService.getCostoUnitarioRealMaterial(mat.id)
      .then((c) => {
        setItems((prev) => {
          if (prev[index]?.material_id !== String(mat.id)) return prev;
          const actual = prev[index];
          const factor = factorCapturaABase(
            actual.materialDimension ?? dim,
            actual.materialUnidad ?? unidadBase,
            actual.unidadCaptura ?? '',
          );
          // Sin compras valorizadas el endpoint devuelve 0: se conserva el
          // costo del catálogo para no borrar el precio que ya se mostró.
          const costoRealBase = c.costo_real > 0 ? c.costo_real : costoBase;
          const costoVenta = costoRealBase * factor;
          const precioActual = Number(actual.calcResult?.precio_venta) || 0;
          const usarAuto = actual.precioAuto !== false || precioActual === 0;
          const next = [...prev];
          next[index] = {
            ...actual,
            precioAuto: usarAuto,
            insumoCosto: {
              costo_compra: c.costo_compra > 0 ? c.costo_compra : costoBase,
              pasada_unitaria: c.pasada_unitaria,
              costo_real: costoRealBase,
            },
            calcResult: calcularResultadoInsumo(costoVenta, usarAuto ? costoVenta : precioActual),
          };
          return next;
        });
      })
      .catch(() => {
        // Sin red o sin historial: se queda con el costo de compra sin pasada.
      });
  };

  // Reparación: la pieza ya existe (es del cliente), se describe el trabajo y
  // entra al taller (Tapicería, etc.). SERVICIO: cobro libre (flete/instalación).
  const nuevoItemLibre = (tipo_item: 'REPARACION' | 'SERVICIO', descripcion = ''): CotizacionItemForm => ({
    producto_id: '',
    material_id: '',
    tipo_item,
    cantidad: 1,
    ancho: '',
    largo: '',
    ganancia: '',
    impuesto: '0',
    descripcion_especifica: descripcion,
    observaciones: '',
    calcResult: null,
    calcLoading: false,
    receta_personalizada: null,
  });

  const addItemReparacion = () => setItems((prev) => [...prev, nuevoItemLibre('REPARACION')]);
  const addItemServicio = (descripcion = '') => setItems((prev) => [...prev, nuevoItemLibre('SERVICIO', descripcion)]);

  const handleOpenProductSelector = (index?: number, modo: 'todos' | 'fabricados' | 'reventa' | 'exhibicion' = 'fabricados') => {
    if (index !== undefined) {
      const item = items[index];
      // Reparación/Servicio no tienen producto: el selector no aplica.
      if (item && (item.tipo_item === 'REPARACION' || item.tipo_item === 'SERVICIO')) return;
      // El obsequio de promo va amarrado a su colchón: no se cambia a mano.
      if (item && item.es_obsequio) return;
      setProductSelectorTargetIndex(index);
      // Editar un renglón existente: bloquear el catálogo a SU clase de
      // producto (un renglón de reventa no se reemplaza por un mueble).
      if (item && item.tipo_item === 'INSUMO') {
        setProductSelectorModo('todos');
      } else if (item && item.tipo_item === 'REVENTA') {
        setProductSelectorModo('reventa');
      } else if (item && item.tipo_item === 'FABRICADO') {
        setProductSelectorModo('fabricados');
      } else {
        setProductSelectorModo(modo);
      }
    } else {
      setProductSelectorTargetIndex(null);
      setProductSelectorModo(modo);
    }
    setIsProductSelectorOpen(true);
  };

  const handleSelectProductFromModal = (product: Product) => {
    if (productSelectorTargetIndex !== null && productSelectorTargetIndex >= 0) {
      updateItemField(productSelectorTargetIndex, 'producto_id', String(product.id));
      updateItemField(productSelectorTargetIndex, 'tipo_item', esItemStock(product) ? 'REVENTA' : 'FABRICADO');
    } else {
      const newItem: CotizacionItemForm = {
        producto_id: String(product.id),
        material_id: '',
        tipo_item: esItemStock(product) ? 'REVENTA' : 'FABRICADO',
        cantidad: 1,
        ancho: String(product.ancho_base ?? 1),
        largo: String(product.largo_base ?? 1),
        ganancia: '',
        impuesto: '',
        observaciones: '',
        calcResult: null,
        calcLoading: false,
        receta_personalizada: null,
      };
      setItems((prev) => {
        const next = [...prev, newItem];
        const nextIdx = next.length - 1;
        calculateItemPrice(nextIdx, String(product.id), newItem.ancho, newItem.largo, newItem.ganancia, null, newItem.impuesto);
        // Colchón con promo: el plástico de regalo entra a la cotización.
        return asegurarObsequio(next, product.id, promosPorColchon);
      });
    }
    setIsProductSelectorOpen(false);
    setProductSelectorTargetIndex(null);
  };

  /** Mueble a la medida: la fila contextual del selector usa el texto
   *  escrito como descripción y el precio se digita a mano (sin catálogo). */
  const handleSelectPersonalizado = (nombre: string) => {
    const descripcion = nombre.trim();
    if (!descripcion) return;
    const aMedida: CotizacionItemForm = {
      producto_id: '',
      material_id: '',
      tipo_item: 'FABRICADO',
      cantidad: 1,
      ancho: '1',
      largo: '1',
      ganancia: '',
      impuesto: '0',
      descripcion_especifica: descripcion,
      observaciones: '',
      calcResult: null,
      calcLoading: false,
      receta_personalizada: null,
    };
    if (productSelectorTargetIndex !== null && productSelectorTargetIndex >= 0) {
      setItems((prev) => {
        const next = [...prev];
        next[productSelectorTargetIndex] = {
          ...next[productSelectorTargetIndex],
          producto_id: '',
          material_id: '',
          tipo_item: 'FABRICADO',
          descripcion_especifica: descripcion,
          calcResult: null,
          calcLoading: false,
          receta_personalizada: null,
        };
        return next;
      });
    } else {
      setItems((prev) => [...prev, aMedida]);
    }
    setIsProductSelectorOpen(false);
    setProductSelectorTargetIndex(null);
  };

  const removeItem = (index: number) => {
    setItems((prev) => {
      const next = prev.filter((_, i) => i !== index);
      setDesgloseIndex((di) => (di >= next.length ? Math.max(0, next.length - 1) : di));
      // Si se quitó el colchón, su obsequio se va; si se quitó el obsequio,
      // queda quitado (no se re-agrega solo).
      return sincronizarCantidadesObsequio(next, promosPorColchon);
    });
  };

  const handleOpenCreate = () => {
    setEditingQuote(null);
    setSelectedClientId('');
    setFechaCotizacion(hoyVE());
    setObservaciones('');
    setSelectedMonedaId(1);
    setTasaCambio(1);
    setTasasDia({});
    setItems([]);
    setErrorForm('');
    setIsFormOpen(true);
  };

  // TODOS pueden ver las cotizaciones de los demás, pero solo su autor (o un
  // admin) puede modificarlas: editar, cambiar estado, convertir o eliminar.
  // El backend valida lo mismo; aquí solo se ocultan las acciones.
  const puedeEditar = (quote: Quote) => esAdmin || quote.creado_por_id === user?.id;

  const handleOpenEdit = (quote: Quote) => {
    setEditingQuote(quote);
    setSelectedClientId(String(quote.cliente_id));
    setClienteSeleccionado(quote.cliente
      ? { value: quote.cliente_id, label: `${quote.cliente.nombre} (${quote.cliente.telefono})` }
      : null);
    setObservaciones(quote.observaciones || '');
    // Se conserva la fecha original, pero queda editable (corregir fechas mal puestas).
    setFechaCotizacion(quote.fecha ? String(quote.fecha).slice(0, 10) : hoyVE());
    setSelectedMonedaId(quote.moneda_id || 1);
    setTasaCambio(quote.tasa_cambio || 1);
    setTasasDia({});
    setItems(sincronizarCantidadesObsequio(
      itemsDesdeCotizacion(quote, quote.moneda?.codigo || 'COP'),
      promosPorColchon,
    ));
    setError('');
    setErrorForm('');
    setIsFormOpen(true);
  };

  // ── Deep-link desde Exhibición (?pieza=ID): abre el formulario con la pieza
  const [searchParams] = useSearchParams();
  const piezaParam = searchParams.get('pieza');
  const piezaDeepLinkDone = useRef(false);
  useEffect(() => {
    if (!piezaParam || piezaDeepLinkDone.current || !products.length) return;
    piezaDeepLinkDone.current = true;
    const resolverYPoner = async () => {
      let prod = products.find((p) => p.id === Number(piezaParam));
      if (!prod) {
        // Fallback: la pieza pudo no venir en el listado (límite/orden).
        try {
          const { data } = await api.get<Product>(`/producto/${piezaParam}`);
          prod = data;
          setProducts((prev) => (prev.some((p) => p.id === data.id) ? prev : [...prev, data]));
        } catch {
          toast.error('No se encontró la pieza de exhibición.');
          return;
        }
      }
      if (!prod) return;
      handleOpenCreate();
      const nuevo: CotizacionItemForm = {
        producto_id: String(prod.id),
        material_id: '',
        tipo_item: esItemStock(prod) ? 'REVENTA' : 'FABRICADO',
        cantidad: 1,
        ancho: String(prod.ancho_base ?? 1),
        largo: String(prod.largo_base ?? 1),
        ganancia: '',
        impuesto: '',
        observaciones: '',
        calcResult: null,
        calcLoading: false,
        receta_personalizada: null,
      };
      setItems((prev) => {
        const next = prev.length && prev[0].producto_id ? [...prev, nuevo] : [nuevo];
        const nextIdx = next.length - 1;
        calculateItemPrice(nextIdx, String(prod.id), nuevo.ancho, nuevo.largo, nuevo.ganancia, null, nuevo.impuesto);
        return next;
      });
    };
    resolverYPoner();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [piezaParam, products]);

  // ── Cliente nuevo desde la cotización ──
  const handleCrearClienteDesdeCotizacion = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorForm('');
    if (!ncForm.nombre.trim() || !ncForm.telefono.trim()) {
      setErrorForm('Indica el nombre y el teléfono del cliente.');
      return;
    }
    setSavingNc(true);
    try {
      const creado = await cotizacionService.crearClienteRapido({
        nombre: ncForm.nombre.trim().toUpperCase(),
        telefono: ncForm.telefono.trim(),
        cedula: ncForm.cedula.trim() || undefined,
        direccion: ncForm.direccion.trim() || undefined,
        ciudad: ncForm.ciudad.trim() || undefined,
        estado: ncForm.estado.trim() || undefined,
        observaciones: ncForm.observaciones.trim() || undefined,
      });
      setClients((prev) => (prev.some((c) => c.id === creado.id) ? prev : [...prev, creado]));
      setSelectedClientId(String(creado.id));
      setClienteSeleccionado({ value: creado.id, label: `${creado.nombre} (${creado.telefono})` });
      setShowNuevoClienteModal(false);
      setNcForm({ nombre: '', telefono: '', cedula: '', direccion: '', ciudad: '', estado: '', observaciones: '' });
      toast.success(`Cliente "${creado.nombre}" seleccionado.`);
    } catch (err: any) {
      setErrorForm(String(err?.response?.data?.detail || 'No se pudo crear el cliente.'));
    } finally {
      setSavingNc(false);
    }
  };

  // ── Producto nuevo desde la cotización ──
  const abrirNuevoProducto = () => {
    if (!tiposProducto.length) {
      api.get<{ id: number; nombre: string }[]>('/catalogos/tipo-producto/')
        .then(({ data }) => setTiposProducto(data.filter((t) => esClasificacionNuevoProducto(t.nombre))))
        .catch(() => setTiposProducto([]));
    }
    setNpForm({ nombre: '', tipo_producto_id: '', precio: '', moneda_id: '1' });
    limpiarNpFotos();
    setErrorForm('');
    setShowNuevoProductoModal(true);
  };

  const handleNpFoto = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files ?? []);
    if (files.length > 0) {
      setFotosNp((prev) => [
        ...prev,
        ...files.map((file) => ({ file, url: URL.createObjectURL(file) })),
      ]);
    }
    e.target.value = '';
  };
  const quitarNpFoto = (idx: number) => {
    setFotosNp((prev) => {
      const copia = [...prev];
      const [quitada] = copia.splice(idx, 1);
      if (quitada) URL.revokeObjectURL(quitada.url);
      return copia;
    });
  };
  const limpiarNpFotos = () => {
    setFotosNp((prev) => {
      prev.forEach((f) => URL.revokeObjectURL(f.url));
      return [];
    });
  };

  const handleCrearProductoDesdeCotizacion = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorForm('');
    if (!npForm.nombre.trim() || !npForm.tipo_producto_id) {
      setErrorForm('Indica el nombre y la clasificación del producto.');
      return;
    }
    const precio = parseFloat(npForm.precio || '0');
    if (!(precio > 0)) {
      setErrorForm('Indica el precio estimado de venta (lo cotizas tal cual).');
      return;
    }
    const tipoSeleccionado = tiposProducto.find((t) => t.id === Number(npForm.tipo_producto_id));
    setSavingNp(true);
    try {
      const creado = await productosService.crearProducto({
        nombre: npForm.nombre.toUpperCase().trim(),
        tipo_producto_id: Number(npForm.tipo_producto_id),
        descripcion: 'Creado desde la cotización',
        activo: true,
        stock_minimo: 8,
        // Revendido y Plástico viven del stock: no pasan por producción.
        es_reventa: esClasificacionStock(tipoSeleccionado?.nombre),
        moneda_id: Number(npForm.moneda_id) || 1,
        // Solo precio de venta: el motor lo cotiza TAL CUAL (no le suma margen).
        precio_costo_base: undefined,
        precio_venta_base: precio,
      });
      // Fotos (opcionales), en orden de selección: la primera es la portada.
      for (const foto of fotosNp) {
        try { await subirAdjunto(foto.file, TIPO_ADJUNTO.PRODUCTO, creado.id); } catch { /* foto opcional */ }
      }
      // Lo agrega al listado y lo auto-selecciona en el renglón objetivo
      const creadoComoProducto = creado as Product;
      setProducts((prev) => (prev.some((p) => p.id === creado.id) ? prev : [...prev, creadoComoProducto]));
      setShowNuevoProductoModal(false);
      limpiarNpFotos();
      handleSelectProductFromModal(creadoComoProducto);
      toast.success(`Producto "${creado.nombre}" creado y agregado al renglón.`);
    } catch (err: any) {
      const detail = String(err?.response?.data?.detail || err?.message || '');
      setErrorForm(detail.includes('permiso') ? 'No tienes permiso para crear productos. Pídelo a un administrador.' : detail || 'No se pudo crear el producto.');
    } finally {
      setSavingNp(false);
    }
  };

  // ── Definir precio estimado de un producto existente sin precio ──
  const abrirDefinirPrecio = (p: Product) => {
    setDefinirPrecioProd(p);
    setDpPrecio(String(p.precio_venta_base ?? ''));
    setDpMoneda(String(p.moneda_id ?? 1));
    setErrorForm('');
  };
  const guardarDefinirPrecio = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorForm('');
    if (!definirPrecioProd) return;
    const precio = parseFloat(dpPrecio || '0');
    if (!(precio > 0)) {
      setErrorForm('El precio debe ser mayor a 0.');
      return;
    }
    setSavingDp(true);
    try {
      await api.put(`/producto/${definirPrecioProd.id}`, {
        precio_venta_base: precio,
        moneda_id: Number(dpMoneda) || 1,
      });
      setProducts((prev) =>
        prev.map((p) => (p.id === definirPrecioProd.id ? { ...p, precio_venta_base: precio, moneda_id: Number(dpMoneda) || 1 } : p)),
      );
      setDefinirPrecioProd(null);
      // recalculcar el renglón que lo usa
      const idx = items.findIndex((it) => Number(it.producto_id) === definirPrecioProd.id);
      if (idx >= 0) {
        const it = items[idx];
        calculateItemPrice(idx, it.producto_id, it.ancho, it.largo, it.ganancia, it.receta_personalizada, it.impuesto);
      }
      toast.success('Precio estimado guardado. El renglón se recalculó.');
    } catch (err: any) {
      setErrorForm(String(err?.response?.data?.detail || err?.message || 'No se pudo guardar el precio.'));
    } finally {
      setSavingDp(false);
    }
  };

  const handleSaveQuote = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorForm('');
    if (!selectedClientId) {
      setErrorForm('Por favor selecciona un cliente.');
      return;
    }

    if (!items.length) {
      setErrorForm('Agrega al menos un renglón con + Mueble, + Reventa, + Exhibición, + Insumo o + Producto nuevo.');
      return;
    }

    // INSUMO exige material_id; REVENTA exige producto_id; FABRICADO exige
    // producto_id O descripción (mueble a la medida); REPARACION/SERVICIO
    // exigen descripción (no llevan producto).
    const hasInvalidItem = items.some((item) => {
      if (item.tipo_item === 'INSUMO') return !item.material_id;
      if (item.tipo_item === 'REPARACION' || item.tipo_item === 'SERVICIO')
        return !(item.descripcion_especifica && item.descripcion_especifica.trim());
      if (item.tipo_item === 'FABRICADO' && !item.producto_id)
        return !(item.descripcion_especifica && item.descripcion_especifica.trim());
      return !item.producto_id;
    });
    if (hasInvalidItem) {
      setErrorForm('Por favor selecciona el producto o material de todos los renglones, o escribe la descripción de los a medida/reparación/servicio.');
      return;
    }

    // Piezas de un juego: nombres únicos, cantidades > 0 y solo FABRICADO.
    const errorPieza = items
      .filter((item) => item.tipo_item === 'FABRICADO')
      .map((item) => validarPiezasJuego(item.piezas ?? []))
      .find((mensaje) => mensaje !== null);
    if (errorPieza) {
      setErrorForm(errorPieza);
      return;
    }

    // No permitir guardar cotizaciones sin precio real: si falta la tasa del
    // día de un producto en moneda extranjera, el precio convertido es inválido.
    // Aplica también a insumos (el precio tecleado no puede ser 0).
    const itemSinPrecio = items.find((it) => {
      // El obsequio de promo va a precio 0 por diseño.
      if (it.es_obsequio) return false;
      if (!it.calcResult) return true;
      const p = precioRenglonEnMoneda(it);
      return !(isFinite(p) && p > 0);
    });
    if (itemSinPrecio) {
      if (itemSinPrecio.tipo_item === 'INSUMO') {
        setErrorForm('Falta el precio de venta del insumo. Escríbelo manualmente en el renglón (debe ser mayor que 0).');
      } else {
        setErrorForm(
          'Hay un renglón sin precio calculado o sin tasa de cambio del día. Ingresa/confirmar la tasa en "Tasas del día" del formulario.',
        );
      }
      return;
    }

    // La TRM solo se exige cuando hay conversión REAL (renglones en moneda
    // distinta a la de la cotización). Cotizar en USD productos que ya están
    // en USD no pide tasa ninguna: el backend resuelve el valor contable con
    // la última tasa disponible sin preguntar.
    if (selectedMonedaId !== 1 && necesitaTasaCotizacion && !(tasaCambio > 0 && tasaCambio !== 1)) {
      setErrorForm(
        `Indica la tasa (1 ${currencyCode} = X COP) para convertir los renglones que no están en ${currencyCode}.`,
      );
      return;
    }

    let globalTotal = 0;
    const detalles: QuoteDetail[] = items.map((item) => {
      // Mueble a la medida: sin producto NI material; descripción libre y
      // precio manual. El costo estimado es opcional (solo referencia).
      if (item.tipo_item === 'FABRICADO' && !item.producto_id) {
        const r = item.calcResult;
        const precioMoneda = Math.round(convertirAPrecioCotizacion(Number(r?.precio_venta) || 0, r?.moneda_codigo || currencyCode) * 100) / 100;
        const subtotal = precioMoneda * item.cantidad;
        globalTotal += subtotal;
        const costoEstimado = Number(r?.costo_total) || 0;
        return {
          producto_id: null,
          material_id: null,
          tipo_item: 'FABRICADO',
          cantidad: item.cantidad,
          precio: precioMoneda,
          ancho: Number(item.ancho) || 1.0,
          largo: Number(item.largo) || 1.0,
          descripcion_especifica: item.descripcion_especifica?.trim() || null,
          observaciones: item.observaciones || null,
          costo_total: costoEstimado > 0 ? costoEstimado * item.cantidad : null,
          piezas: piezasParaPayload(item),
        };
      }
      if (item.tipo_item === 'REPARACION' || item.tipo_item === 'SERVICIO') {
        const r = item.calcResult;
        const precioMoneda = Math.round(convertirAPrecioCotizacion(Number(r?.precio_venta) || 0, r?.moneda_codigo || currencyCode) * 100) / 100;
        const subtotal = precioMoneda * item.cantidad;
        globalTotal += subtotal;
        return {
          producto_id: null,
          material_id: null,
          tipo_item: item.tipo_item,
          cantidad: item.cantidad,
          precio: precioMoneda,
          descripcion_especifica: item.descripcion_especifica?.trim() || null,
          observaciones: item.observaciones || null,
          costo_materiales: item.tipo_item === 'REPARACION' ? Number(r?.costo_materiales || 0) * item.cantidad : null,
          costo_mano_obra: item.tipo_item === 'REPARACION' ? Number(r?.costo_mano_obra || 0) * item.cantidad : null,
          costo_gastos: item.tipo_item === 'REPARACION' ? Number(r?.costo_gastos_indirectos || 0) * item.cantidad : null,
          costo_total: Number(r?.costo_total || 0) * item.cantidad,
        };
      }
      if (item.tipo_item === 'INSUMO') {
        // El material se lista en COP (moneda base); se convierte a la moneda
        // de la cotización igual que cualquier otro renglón.
        const r = item.calcResult;
        const precioUnitCop = Number(r?.precio_venta) || 0;
        const precioMoneda =
          Math.round(convertirAPrecioCotizacion(precioUnitCop, r?.moneda_codigo || 'COP') * 100) / 100;
        const subtotal = precioMoneda * item.cantidad;
        globalTotal += subtotal;
        const cantidadBase = item.cantidadBase ?? item.cantidad;
        return {
          producto_id: null,
          material_id: Number(item.material_id),
          tipo_item: 'INSUMO',
          cantidad: item.cantidad,
          precio: precioMoneda,
          // Captura flexible: el documento conserva 1128 cm × 160, pero el
          // costo y el inventario usan 0,1128 m³.
          unidad_captura: item.unidadCaptura || null,
          cantidad_base: cantidadBase,
          observaciones: item.observaciones || null,
          // Costo real en COP (compra + pasada) × cantidad BASE del
          // inventario. El backend lo divide por la cantidad vendida al
          // convertir a pedido para obtener el costo unitario real del
          // renglón (p. ej. 180.480 / 1128 = 160 COP/cm).
          costo_materiales: item.insumoCosto ? item.insumoCosto.costo_real * cantidadBase : null,
          costo_total: item.insumoCosto ? item.insumoCosto.costo_real * cantidadBase : null,
        };
      }
      const r = item.calcResult;
      const conv = (v: number) => {
        const c = convertirAPrecioCotizacion(Number(v), r?.moneda_codigo);
        return Math.round(c * 100) / 100;
      };
      const precioMoneda = conv(r ? r.precio_venta : 0.0);
      const subtotal = precioMoneda * item.cantidad;
      globalTotal += subtotal;
      const esObsequio = !!item.es_obsequio;

      return {
        producto_id: Number(item.producto_id),
        tipo_item: item.tipo_item || 'FABRICADO',
        cantidad: item.cantidad,
        precio: precioMoneda,
        ancho: Number(item.ancho) || 1.0,
        largo: Number(item.largo) || 1.0,
        observaciones: item.observaciones || null,
        // El obsequio no lleva costos propios: el backend toma el costo real
        // del inventario al facturar y su utilidad se neutraliza.
        es_obsequio: esObsequio || undefined,
        costo_materiales: esObsequio ? null : conv(r?.costo_materiales || 0.0) * item.cantidad,
        costo_mano_obra: esObsequio ? null : conv(r?.costo_mano_obra || 0.0) * item.cantidad,
        costo_gastos: esObsequio ? null : conv(r?.costo_gastos_indirectos || 0.0) * item.cantidad,
        costo_total: esObsequio ? null : conv(r?.costo_total || 0.0) * item.cantidad,
        receta_personalizada: item.receta_personalizada || null,
        piezas: item.tipo_item === 'FABRICADO' ? piezasParaPayload(item) : undefined,
      };
    });

    // Auto-generate preview description in observaciones field
    const itemsDescription = items.map((item) => {
      if (item.tipo_item === 'REPARACION' || item.tipo_item === 'SERVICIO') {
        return `${item.cantidad}x ${item.descripcion_especifica?.trim() || (item.tipo_item === 'REPARACION' ? 'Reparación' : 'Servicio')}`;
      }
      if (item.tipo_item === 'INSUMO') {
        const mat = materiales.find((m) => m.id === Number(item.material_id));
        const unidad = item.unidadCaptura === 'CM'
          ? 'cm'
          : item.unidadCaptura === 'M'
            ? 'm'
            : (item.materialUnidad || '');
        return `${item.cantidad}${unidad ? ` ${unidad}` : ''} x ${mat?.nombre || 'Insumo'}`;
      }
      const selectedProd = products.find(p => p.id === Number(item.producto_id));
      if (item.es_obsequio) {
        return `${item.cantidad}x ${selectedProd?.nombre || 'Plástico'} (obsequio)`;
      }
      if (!selectedProd && item.descripcion_especifica) {
        // Mueble a la medida: la descripción ES el nombre del renglón.
        return `${item.cantidad}x ${item.descripcion_especifica.trim().slice(0, 80)}`;
      }
      return `${item.cantidad}x ${selectedProd?.nombre || 'Mueble'} (${item.ancho}x${item.largo}m)`;
    }).join(', ');
    
    const finalObs = observaciones 
      ? `Productos: ${itemsDescription}\nNota: ${observaciones}`
      : `Productos: ${itemsDescription}`;

    // globalTotal ya está en la moneda de la cotización (conversión única por
    // renglón); no se vuelve a dividir.
    const totalEstimado = Math.round(globalTotal);

    const quoteData: QuoteCreate = {
      cliente_id: Number(selectedClientId),
      // Fecha elegida en el formulario (default hoy VE); al editar arranca con
      // la original y también puede corregirse. Vacía → hoy (America/Caracas).
      fecha: fechaCotizacion || hoyVE(),
      estado: editingQuote ? editingQuote.estado : 'BORRADOR',
      total_estimado: totalEstimado,
      moneda_id: selectedMonedaId,
      // En moneda extranjera el backend resuelve el valor contable en pesos
      // (tasa indicada → TRM registrada → última usada). En COP es 1.
      tasa_cambio: selectedMonedaId === 1 ? 1 : tasaCambio,
      observaciones: finalObs,
      detalles
    };

    try {
      if (editingQuote) {
        await cotizacionService.update(editingQuote.id, quoteData);
      } else {
        await cotizacionService.create(quoteData);
      }
      setIsFormOpen(false);
      fetchQuotes(search);
    } catch (err) {
      console.error(err);
      setErrorForm(String((err as any)?.response?.data?.detail || 'Error al guardar la cotización.'));
    }
  };

  const handleUpdateStatus = async (quote: Quote, newStatus: string) => {
    try {
      await cotizacionService.update(quote.id, {
        cliente_id: quote.cliente_id,
        fecha: quote.fecha,
        estado: newStatus,
        total_estimado: quote.total_estimado,
        observaciones: quote.observaciones,
      });
      fetchQuotes(search);
    } catch (err) {
      console.error(err);
      toast.error(String((err as any)?.response?.data?.detail || 'Error al actualizar el estado de la cotización.'));
    }
  };

  const handleDelete = (id: number) => {
    setConfirmDeleteId(id);
  };
  const ejecutarDelete = async () => {
    if (confirmDeleteId === null) return;
    const id = confirmDeleteId;
    setConfirmDeleteId(null);
    try {
      await cotizacionService.delete(id);
      fetchQuotes(search);
    } catch (err) {
      console.error(err);
      toast.error(String((err as any)?.response?.data?.detail || 'Error al eliminar.'));
    }
  };

  const handleOpenConvert = (quote: Quote) => {
    if (quote.pedido_id) {
      toast.info(`Esta cotización ya fue convertida al pedido #${quote.pedido_id}.`);
      return;
    }
    setSelectedQuoteForConvert(quote);
    setDeliveryDate('');
    setAdelantoModo('pct');
    setAdelantoPct('');
    setAdelantoMonto('');
    setAdelantoMonedaId(quote.moneda_id ?? 1);
    setAdelantoTrm('');
    setAdelantoMetodo('');
    setFechaAdelanto(hoyVE());
    setConvertError('');
    setIsConvertOpen(true);
  };

  const handleOpenPrintPreview = async (quote: Quote) => {
    setSelectedQuoteForPrint(quote);
    setAssociatedVenta(null);
    
    // Load default values or saved configurations
    setPrintCompanyRif(localStorage.getItem('print_company_rif') || 'J-50146039-3');
    setPrintCompanyAddress(localStorage.getItem('print_company_address') || 'AV. INTERCOMUNAL CON CALLE 16 LOCAL Nro 15-205, BARRIO SIMÓN BOLÍVAR, UREÑA, TÁCHIRA');
    setPrintCompanyPhone(localStorage.getItem('print_company_phone') || '+58 412-1234567');
    setPrintDiscount('0');
    setPrintIva('0');
    
    setIsPrintModalOpen(true);

    // Buscar si existe un pedido y factura/abonos asociados a esta cotización
    try {
      const ventas = await ventaService.getAll();
      const responsePedidos = await pedidoService.getAll();
      const pedidoVinculado = responsePedidos.find((p: any) => p.cotizacion_id === quote.id || p.cotizacion?.id === quote.id);
      if (pedidoVinculado) {
        const ventaVinculada = ventas.find((v: any) => v.pedido_id === pedidoVinculado.id);
        if (ventaVinculada) {
          const detalleVenta = await ventaService.getById(ventaVinculada.id);
          setAssociatedVenta(detalleVenta);
        }
      }
    } catch (err) {
      console.error('Error al cargar ventas/abonos vinculados a la cotización:', err);
    }
  };

  const handleGeneratePdf = async () => {
    if (!selectedQuoteForPrint) return;
    setIsGeneratingPdf(true);

    // Save settings in localStorage
    localStorage.setItem('print_company_rif', printCompanyRif);
    localStorage.setItem('print_company_address', printCompanyAddress);
    localStorage.setItem('print_company_phone', printCompanyPhone);

    const element = document.getElementById('pdf-preview-container');
    if (!element) { setIsGeneratingPdf(false); return; }

    try {
      const canvas = await html2canvas(element, { scale: 6, useCORS: true });
      const pdf = new jsPDF({ orientation: 'portrait', unit: 'mm', format: 'letter' });
      const pdfW = pdf.internal.pageSize.getWidth();
      const pdfH = pdf.internal.pageSize.getHeight();
      const totalH = (canvas.height * pdfW) / canvas.width;

      if (totalH <= pdfH) {
        pdf.addImage(canvas.toDataURL('image/jpeg', 0.98), 'JPEG', 0, 0, pdfW, totalH);
      } else {
        const pxPerMm = canvas.width / pdfW;
        const pageHpx = Math.floor(pdfH * pxPerMm);
        let yPx = 0; let pg = 0;
        while (yPx < canvas.height) {
          const slicePx = Math.min(pageHpx, canvas.height - yPx);
          const sc = document.createElement('canvas');
          sc.width = canvas.width; sc.height = slicePx;
          sc.getContext('2d')?.drawImage(canvas, 0, -yPx);
          if (pg > 0) pdf.addPage('letter', 'portrait');
          pdf.addImage(sc.toDataURL('image/jpeg', 0.98), 'JPEG', 0, 0, pdfW, (slicePx / canvas.width) * pdfW);
          yPx += slicePx; pg++;
        }
      }
      pdf.save(`Cotizacion_${selectedQuoteForPrint.id}.pdf`);
    } catch (err) {
      console.error('Error generating PDF:', err);
      toast.error('Hubo un error al generar el PDF.');
    } finally {
      setIsGeneratingPdf(false);
    }
  };

  const handleConvertQuote = async () => {
    if (!selectedQuoteForConvert || isConverting) return;
    setIsConverting(true);
    setConvertError('');
    try {
      if (abonoActivo) {
        if (!adelantoMetodo) {
          setConvertError('Selecciona el método de pago del abono inicial.');
          return;
        }
        if (!monedasIguales && !tasaAbonoValida) {
          setConvertError(
            `Indica la tasa de cambio del abono: ${parAdelanto.label}.`
          );
          return;
        }
        if (abonoExcedeTotal) {
          setConvertError('El abono inicial no puede exceder el total del pedido.');
          return;
        }
      }

      let convertDetails;
      if (selectedQuoteForConvert.detalles && selectedQuoteForConvert.detalles.length > 0) {
        // Copiar los renglones EXACTOS de la cotización: el backend valida cada
        // detalle contra la cotización por (tipo_item, producto_id, material_id).
        // Sin tipo_item/material_id, los renglones INSUMO y REVENTA se rechazan.
        convertDetails = selectedQuoteForConvert.detalles.map((det) => ({
          producto_id: det.producto_id ?? undefined,
          material_id: det.material_id ?? undefined,
          tipo_item: det.tipo_item || 'FABRICADO',
          cantidad: det.cantidad,
          precio: det.precio,
          ancho: det.ancho ?? undefined,
          largo: det.largo ?? undefined,
          descripcion_especifica: det.descripcion_especifica ?? det.observaciones ?? undefined,
          observaciones: det.observaciones ?? undefined,
          es_obsequio: det.es_obsequio || undefined,
          piezas: det.piezas?.map((p) => ({
            nombre: p.nombre,
            cantidad: Number(p.cantidad) || 1,
            notas: p.notas || null,
          })),
        }));
      } else {
        const match = selectedQuoteForConvert.observaciones?.match(/Producto: (.*) \((.*)x(.*)m\)/);
        let pId: number | undefined;
        let w = 1.0, l = 1.0;
        if (match) {
          const pName = match[1];
          w = Number(match[2]) || 1.0;
          l = Number(match[3]) || 1.0;
          const found = products.find(p => p.nombre === pName);
          if (found) pId = found.id;
        }
        if (!pId) {
          toast.error('No se pudo identificar el producto de esta cotización. Verifique que tenga detalles o que el producto exista en el catálogo.');
          return;
        }
        convertDetails = [
          {
            producto_id: pId,
            cantidad: 1,
            precio: selectedQuoteForConvert.total_estimado,
            ancho: w,
            largo: l,
            observaciones: selectedQuoteForConvert.observaciones,
          },
        ];
      }

      const metodoLabel = labelMetodoPago(metodosPago, adelantoMetodo);
      const monedaPagoDifiere = adelantoMonedaId !== selectedQuoteForConvert.moneda_id;
      const tasaVenta = Number(selectedQuoteForConvert.tasa_cambio) || 1;
      const factorPago = abonoMontoPago > 0 ? abonoEnMonedaCotizacion / abonoMontoPago : 1.0;
      await pedidoService.convertQuote(selectedQuoteForConvert.id, {
        detalles: convertDetails,
        fecha_entrega_estimada: deliveryDate || undefined,
        adelanto: abonoActivo ? abonoMontoPago : undefined,
        moneda_adelanto_id: adelantoMonedaId,
        tasa_cambio_adelanto:
          abonoActivo && monedaPagoDifiere ? factorPago * tasaVenta : undefined,
        metodo_pago: abonoActivo ? adelantoMetodo : undefined,
        // Fecha real del abono (pudo ser días antes); vacía → hoy (servidor).
        fecha_adelanto: abonoActivo && fechaAdelanto ? fechaAdelanto : undefined,
      });
      setIsConvertOpen(false);
      const avisoAbono =
        abonoActivo && monedaAdelantoSel
          ? ` Abono inicial registrado: ${formatCurrency(Math.round(abonoMontoPago), monedaAdelantoSel.codigo)}${metodoLabel ? ` · ${metodoLabel}` : ''}.`
          : '';
      toast.success(`¡Cotización convertida a pedido con éxito!${avisoAbono} El pedido entró directamente a producción y se creó la factura automáticamente.`);
      fetchQuotes(search);
    } catch (err) {
      console.error(err);
      setConvertError(
        extractErrorMessage(err, 'Error al convertir la cotización a pedido.')
      );
    } finally {
      setIsConverting(false);
    }
  };

  // Calculations summaries
  // Un producto es "de stock" (se vende del inventario, no se fabrica por
  // pedido) si es reventa O pieza de exhibición (fabricada y en el showroom).
  const esItemStock = (p?: { es_reventa?: boolean; es_exhibicion?: boolean } | null) =>
    !!p && (!!p.es_reventa || !!p.es_exhibicion);

  // Un renglón es de reventa cuando su producto está marcado como tal: no tiene
  // receta ni dimensiones; su precio sale del precio de referencia (convertido).
  const esItemReventa = (item: { producto_id: string | number }) =>
    esItemStock(products.find((p) => p.id === Number(item.producto_id)));

  // ── Conversión única al precio de cotización ─────────────────────────────
  // Fabricados: vienen en COP → comportamiento previo (dividir por la tasa si
  // la cotización no es COP). Reventa: viene en su moneda (`moneda_codigo`) →
  // misma moneda: sin conversión; distinta: × tasa del día ÷ tasa cotización.
  const convertirAPrecioCotizacion = (precioProducto: number, monedaCodigo?: string | null): number => {
    if (!monedaCodigo || monedaCodigo === 'COP') {
      return selectedMonedaId === 1 ? precioProducto : precioProducto / (tasaCambio || 1);
    }
    if (monedaCodigo === currencyCode) return precioProducto;
    const tasaProd = parseFloat(tasasDia[monedaCodigo] || '');
    if (!(tasaProd > 0)) return NaN;
    const precioCop = precioProducto * tasaProd;
    return selectedMonedaId === 1 ? precioCop : precioCop / (tasaCambio || 1);
  };

  /** Precio unitario del renglón ya en la moneda de la cotización (NaN si falta tasa). */
  const precioRenglonEnMoneda = (item: { calcResult: CalculationResult | null }): number =>
    item.calcResult
      ? convertirAPrecioCotizacion(Number(item.calcResult.precio_venta), item.calcResult.moneda_codigo)
      : NaN;

  // Monedas extranjeras presentes en los renglones y distintas de la moneda de
  // la cotización: para esas se requiere la tasa del día. Se detecta desde el
  // cálculo ya hecho O desde el producto seleccionado (reventa aún sin calcular).
  const monedasRequeridas = useMemo(() => {
    const set = new Set<string>();
    items.forEach((it) => {
      const code =
        it.calcResult?.moneda_codigo ||
        products.find((p) => p.id === Number(it.producto_id))?.moneda?.codigo;
      if (code && code !== 'COP' && code !== currencyCode) set.add(code);
    });
    return Array.from(set).sort();
  }, [items, products, currencyCode]);

  // La tasa de cotización (1 [moneda] = X COP) SOLO hace falta cuando algún
  // renglón llega en una moneda distinta a la de la cotización (fabricados e
  // insumos vienen en COP; reventas en la suya). Una cotización 100% en la
  // moneda de sus productos no necesita conversión: no se pide la tasa.
  const necesitaTasaCotizacion = useMemo(() => {
    if (selectedMonedaId === 1) return false;
    return items.some((it) => {
      const code =
        it.calcResult?.moneda_codigo ||
        products.find((p) => p.id === Number(it.producto_id))?.moneda?.codigo ||
        'COP';
      return code !== currencyCode;
    });
  }, [items, products, currencyCode, selectedMonedaId]);

  // TRM contable: aunque no haya conversión (todo en la misma moneda), el
  // ERP guarda el valor en pesos (total_en_moneda_base) y sin tasa real
  // fabricaría 1 USD = 1 COP. Se pre-llena con la última tasa registrada.
  useEffect(() => {
    if (selectedMonedaId === 1 || !currencyCode) return;
    if (tasaCambio && tasaCambio !== 1) return;
    const reg = tasasRegistradasRef.current[currencyCode];
    if (reg && reg !== 1) setTasaCambio(reg);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedMonedaId, currencyCode, necesitaTasaCotizacion]);

  // Prellenar cada moneda nueva con su última tasa registrada (visible y
  // editable: el usuario siempre confirma el valor).
  useEffect(() => {
    setTasasDia((prev) => {
      let cambio = false;
      const next = { ...prev };
      for (const code of monedasRequeridas) {
        if (!next[code]) {
          const reg = tasasRegistradasRef.current[code];
          if (reg > 0) {
            next[code] = String(reg);
            cambio = true;
          }
        }
      }
      return cambio ? next : prev;
    });
  }, [monedasRequeridas]);

  const globalTotalCalc = items.reduce((acc, item) => {
    const price = precioRenglonEnMoneda(item);
    return acc + (isFinite(price) ? price * item.cantidad : 0);
  }, 0);

  const globalMaterialCost = items.reduce((acc, item) => {
    const mat = item.calcResult ? convertirAPrecioCotizacion(Number(item.calcResult.costo_materiales), item.calcResult.moneda_codigo) : 0;
    return acc + (isFinite(mat) ? mat * item.cantidad : 0);
  }, 0);

  const globalManoObraCost = items.reduce((acc, item) => {
    const mo = item.calcResult ? convertirAPrecioCotizacion(Number(item.calcResult.costo_mano_obra), item.calcResult.moneda_codigo) : 0;
    return acc + (isFinite(mo) ? mo * item.cantidad : 0);
  }, 0);

  const globalGastosCost = items.reduce((acc, item) => {
    const g = item.calcResult ? convertirAPrecioCotizacion(Number(item.calcResult.costo_gastos_indirectos), item.calcResult.moneda_codigo) : 0;
    return acc + (isFinite(g) ? g * item.cantidad : 0);
  }, 0);

  const globalCostoTotal = items.reduce((acc, item) => {
    const t = item.calcResult ? convertirAPrecioCotizacion(Number(item.calcResult.costo_total), item.calcResult.moneda_codigo) : 0;
    return acc + (isFinite(t) ? t * item.cantidad : 0);
  }, 0);

  const quoteEstadoBadge = (estado: string, q?: Quote) => {
    if (q?.pedido_id) {
      return (
        <span className="px-2.5 py-1 rounded-full text-xs font-bold font-headline inline-block whitespace-nowrap bg-emerald-600 text-white">
          ✓ Convertida
        </span>
      );
    }
    return (
    <span
      className={`px-2.5 py-1 rounded-full text-xs font-bold font-headline inline-block whitespace-nowrap ${
        estado === 'APROBADA'
          ? 'bg-green-100 text-green-800'
          : estado === 'ENVIADA'
          ? 'bg-blue-100 text-blue-800'
          : estado === 'RECHAZADA'
          ? 'bg-red-100 text-red-800'
          : estado === 'VENCIDA'
          ? 'bg-orange-100 text-orange-800'
          : 'bg-gray-100 text-gray-800'
      }`}
    >
      {estado === 'BORRADOR' ? 'Borrador'
        : estado === 'ENVIADA' ? 'Enviada'
        : estado === 'APROBADA' ? 'Aprobada'
        : estado === 'RECHAZADA' ? 'Rechazada'
        : estado === 'VENCIDA' ? 'Vencida'
        : estado}
    </span>
    );
  };

  const quoteColumns: DataColumn<Quote>[] = [
    {
      key: 'id',
      header: 'Cotización ID',
      render: (q) => <span className="font-mono font-bold text-yeikar-secondary">#{q.id}</span>,
      mobilePrimary: true,
    },
    {
      key: 'cliente',
      header: 'Cliente',
      render: (q) => (
        <span className="font-bold text-yeikar-secondary font-headline">{q.cliente?.nombre || `Cliente ID: ${q.cliente_id}`}</span>
      ),
      mobileSecondary: true,
    },
    {
      key: 'fecha',
      header: 'Fecha',
      render: (q) => <span className="font-mono text-yeikar-neutral/70">{q.fecha}</span>,
      mobileLabel: 'Fecha',
    },
    {
      key: 'creador',
      header: 'Registrada por',
      render: (q) => (
        <div>
          <div className="font-semibold text-yeikar-secondary">{q.creador_nombre || 'Registro histórico'}</div>
          <div className="mt-0.5 text-[10px] font-mono text-yeikar-neutral/45">
            {q.created_at ? new Date(q.created_at).toLocaleString('es-CO') : 'Hora no disponible'}
          </div>
        </div>
      ),
      mobileLabel: 'Registrada por',
    },
    {
      key: 'detalles',
      header: 'Detalles',
      render: (q) => <span className="text-xs whitespace-pre-line text-yeikar-neutral/80">{q.observaciones}</span>,
      mobileLabel: 'Detalles',
    },
    {
      key: 'total',
      header: 'Total Estimado',
      // Moneda en palabra clara al lado del monto ("$344.00 Dólares"). El
      // "≈ equivalente en COP" se retiró del listado: la tasa varía a diario
      // y mostrarla junto al precio parecía un segundo precio (ver #207).
      render: (q) => (
        <span className="font-mono font-bold text-yeikar-secondary">
          {formatCurrency(Number(q.total_estimado), q.moneda?.codigo)}{' '}
          <span className="font-normal">{nombreMoneda(q.moneda?.codigo)}</span>
        </span>
      ),
      mobileLabel: 'Total',
    },
    {
      key: 'estado',
      header: 'Estado',
      render: (q) => quoteEstadoBadge(q.estado, q),
      mobileHidden: true,
    },
  ];

  const renderQuoteAcciones = (quote: Quote) => (
    <>
      {puedeEditar(quote) && (
        <button
          onClick={() => handleOpenEdit(quote)}
          className="p-1.5 text-yeikar-secondary hover:text-yeikar-primary transition-colors"
          title="Editar cotización (cambiar comentarios, montos o renglones)"
        >
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
          </svg>
        </button>
      )}
      {puedeEditar(quote) && quote.estado === 'BORRADOR' && (
        <button
          onClick={() => handleUpdateStatus(quote, 'ENVIADA')}
          className="text-xs bg-blue-50 text-blue-600 hover:underline font-bold py-1.5"
          title="Enviar"
        >
          Enviar
        </button>
      )}
      {puedeEditar(quote) && quote.estado === 'ENVIADA' && (
        <>
          <button
            onClick={() => handleOpenConvert(quote)}
            className="bg-yeikar-primary hover:bg-yeikar-primary-light text-yeikar-neutral px-2.5 py-1.5 rounded text-xs font-bold font-headline shadow-sm"
            title="Confirmar la cotización y crear el pedido: entra directamente a producción"
          >
            Pedido
          </button>
          <button
            onClick={() => handleUpdateStatus(quote, 'RECHAZADA')}
            className="text-xs text-red-600 hover:underline font-bold py-1.5"
            title="Rechazar"
          >
            Rechazar
          </button>
        </>
      )}
      {puedeEditar(quote) && quote.estado === 'APROBADA' && !quote.pedido_id && (
        <button
          onClick={() => handleOpenConvert(quote)}
          className="bg-yeikar-primary hover:bg-yeikar-primary-light text-yeikar-neutral px-2.5 py-1.5 rounded text-xs font-bold font-headline shadow-sm"
        >
          Pasar a Pedido
        </button>
      )}
      {quote.pedido_id && (
        <button
          onClick={() => navigate(`/pedidos?pedido=${quote.pedido_id}`)}
          className="bg-emerald-600 hover:bg-emerald-700 text-white px-2.5 py-1.5 rounded text-xs font-bold font-headline shadow-sm"
          title={`Ver el pedido #${quote.pedido_id} generado de esta cotización`}
        >
          Ver pedido
        </button>
      )}
      <button
        onClick={() => handleOpenPrintPreview(quote)}
        className="bg-yeikar-secondary hover:bg-yeikar-secondary-light text-yeikar-primary px-2.5 py-1.5 rounded text-xs font-bold font-headline shadow-sm flex items-center gap-1"
        title="Imprimir Factura Inicial"
      >
        <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M17 17h2a2 2 0 002-2v-4a2 2 0 00-2-2H5a2 2 0 00-2 2v4a2 2 0 002 2h2m2 4h6a2 2 0 002-2v-4a2 2 0 00-2-2H9a2 2 0 00-2 2v4a2 2 0 002 2zm8-12V5a2 2 0 00-2-2H9a2 2 0 00-2 2v4h10z" />
        </svg>
        Ver Cotización
      </button>
      <button
        onClick={() => navigate(`/historial?tipo=cotizaciones&id=${quote.id}`)}
        className="p-2 text-yeikar-primary hover:text-yeikar-primary-dark transition-colors"
        title="Ver ficha completa"
      >
        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z" />
        </svg>
      </button>
      {puedeEditar(quote) && (
        <button
          onClick={() => handleDelete(quote.id)}
          className="p-1.5 text-red-600 hover:text-red-800 transition-colors"
          title="Eliminar"
        >
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
          </svg>
        </button>
      )}
    </>
  );

  return (
    <div className="space-y-6">
      {/* Top Action Bar */}
      <div className="flex flex-col md:flex-row items-center justify-between gap-4 bg-white p-4 rounded-xl border border-yeikar-secondary-light/10 shadow-sm">
        <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-3 w-full md:w-auto flex-1">
          <div className="relative w-full sm:w-72">
            <input
              type="text"
              placeholder="Buscar cotizaciones..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="w-full pl-10 pr-4 py-2 border border-yeikar-secondary-light/20 rounded-lg focus:outline-none focus:ring-2 focus:ring-yeikar-primary focus:border-transparent font-body bg-yeikar-tertiary/30 text-sm"
            />
            <div className="absolute left-3.5 top-2.5 text-yeikar-neutral/40">
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
              </svg>
            </div>
          </div>
          
          <div className="flex items-center gap-2 bg-yeikar-tertiary/20 p-1.5 rounded-lg border border-yeikar-secondary/10 text-xs">
            <label className="flex items-center gap-1.5 cursor-pointer font-headline font-bold text-yeikar-secondary">
              <input
                type="checkbox"
                checked={!soloMesActual}
                onChange={(e) => setSoloMesActual(!e.target.checked)}
                className="rounded border-yeikar-secondary-light/30 text-yeikar-primary focus:ring-yeikar-primary h-4 w-4"
              />
              Historial Completo
            </label>
            
            {!soloMesActual && (
              <div className="flex items-center gap-1.5 animate-fade-in">
                <span className="text-yeikar-neutral/40">|</span>
                <select
                  value={selectedMonth}
                  onChange={(e) => setSelectedMonth(Number(e.target.value))}
                  className="bg-white border border-yeikar-secondary-light/20 rounded px-1.5 py-0.5 focus:outline-none focus:ring-1 focus:ring-yeikar-primary text-xs font-mono"
                >
                  {Array.from({ length: 12 }, (_, i) => i + 1).map(m => (
                    <option key={m} value={m}>
                      {new Date(2020, m - 1).toLocaleString('es-ES', { month: 'long' })}
                    </option>
                  ))}
                </select>
                <select
                  value={selectedYear}
                  onChange={(e) => setSelectedYear(Number(e.target.value))}
                  className="bg-white border border-yeikar-secondary-light/20 rounded px-1.5 py-0.5 focus:outline-none focus:ring-1 focus:ring-yeikar-primary text-xs font-mono"
                >
                  {Array.from({ length: 10 }, (_, i) => new Date().getFullYear() - i).map(y => (
                    <option key={y} value={y}>{y}</option>
                  ))}
                </select>
              </div>
            )}
          </div>
        </div>
        <button
          onClick={handleOpenCreate}
          className="w-full sm:w-auto bg-yeikar-primary text-yeikar-neutral font-bold px-5 py-2 rounded-lg shadow-md hover:bg-yeikar-primary-light transition-all flex items-center justify-center gap-2 font-headline"
        >
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 4v16m8-8H4" />
          </svg>
          Nueva Cotización
        </button>
      </div>

      {error && (
        <div className="bg-red-50 text-red-700 p-4 rounded-xl border border-red-200 text-sm">
          {error}
        </div>
      )}

      {/* Filtro por estado: activas por defecto, convertidas e histórico bajo demanda */}
      <div className="flex items-center gap-2 flex-wrap">
        {[['ACTIVAS', 'Activas'], ['CONVERTIDAS', 'Convertidas'], ['HISTORICAS', 'Rechazadas / Vencidas'], ['', 'Todas']].map(([valor, label]) => (
          <button
            key={valor}
            onClick={() => setFiltroEstadoCot(valor)}
            className={`px-3 py-1 rounded-full text-xs font-bold border transition-all ${
              filtroEstadoCot === valor
                ? 'bg-yeikar-primary text-yeikar-neutral border-yeikar-primary'
                : 'bg-white text-yeikar-neutral/60 border-yeikar-secondary-light/20 hover:border-yeikar-primary/40'
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {/* Main Table */}
      <div className="bg-white rounded-xl border border-yeikar-secondary-light/10 shadow-sm overflow-hidden">
        {loading ? (
          <div className="p-8 text-center text-yeikar-neutral/60 font-mono">Cargando cotizaciones...</div>
        ) : quotes.length === 0 ? (
          <div className="p-8 text-center text-yeikar-neutral/60">No hay cotizaciones registradas.</div>
        ) : (() => {
          const quotesVisibles = filtroEstadoCot === 'ACTIVAS'
            ? quotes.filter((q) => ['BORRADOR', 'ENVIADA', 'APROBADA'].includes(q.estado) && !q.pedido_id)
            : filtroEstadoCot === 'CONVERTIDAS'
              ? quotes.filter((q) => !!q.pedido_id)
              : filtroEstadoCot === 'HISTORICAS'
                ? quotes.filter((q) => ['RECHAZADA', 'VENCIDA'].includes(q.estado))
                : quotes;
          if (quotesVisibles.length === 0) {
            return <div className="p-8 text-center text-yeikar-neutral/60">No hay cotizaciones en este filtro.</div>;
          }
          return (
            <ResponsiveDataTable
              columns={quoteColumns}
              rows={quotesVisibles}
              rowKey={(q) => q.id}
              cardBadge={(q) => quoteEstadoBadge(q.estado, q)}
              tableActions={renderQuoteAcciones}
              cardActions={renderQuoteAcciones}
              darkHeader
            />
          );
        })()}
      </div>

      {/* Quote Form Modal */}
      {isFormOpen && (
        <div className="fixed inset-0 bg-yeikar-neutral/50 backdrop-blur-sm flex items-stretch sm:items-center justify-center sm:p-4 z-50">
          <div className="bg-white rounded-none sm:rounded-xl border border-yeikar-secondary-light/10 shadow-2xl w-full max-w-5xl overflow-y-auto md:overflow-hidden flex flex-col md:flex-row max-h-[100dvh] sm:max-h-[90vh]">
            {/* Form Inputs — ÚNICO contenedor de scroll en desktop */}
            <form onSubmit={handleSaveQuote} className="p-4 sm:p-6 space-y-4 flex-1 min-w-0 md:max-h-[90vh] md:overflow-y-auto">
              <div className="bg-yeikar-neutral -mx-4 sm:-mx-6 -mt-4 sm:-mt-6 p-4 text-yeikar-tertiary flex items-center justify-between mb-4 sticky top-0 z-10 sm:rounded-t-xl">
                <h3 className="font-headline font-bold text-lg text-yeikar-primary">
                  {editingQuote ? 'Editar Cotización' : 'Nueva Cotización'}
                </h3>
                <button
                  type="button"
                  onClick={() => setIsFormOpen(false)}
                  className="text-yeikar-tertiary/60 hover:text-white transition-colors p-1 -mr-1"
                  title="Cerrar sin guardar"
                  aria-label="Cerrar"
                >
                  <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs uppercase tracking-wider font-bold text-yeikar-neutral/60 font-headline mb-1">
                    Cliente *
                  </label>
                  <SearchSelect
                    value={selectedClientId}
                    onChange={(v) => setSelectedClientId(String(v))}
                    loadOptions={async (q) =>
                      (await clienteService.getAll(q || undefined))
                        .map((c) => ({ value: c.id, label: `${c.nombre} (${c.telefono})` }))
                    }
                    minChars={1}
                    selectedOption={clienteSeleccionado ?? undefined}
                    placeholder="Selecciona un cliente..."
                  />
                  <button
                    type="button"
                    onClick={() => { setErrorForm(''); setShowNuevoClienteModal(true); }}
                    title="Crear cliente nuevo"
                    className="mt-2 flex w-full items-center justify-center gap-2 rounded-xl border border-dashed border-yeikar-primary/60 bg-yeikar-primary/10 px-3 py-2 text-xs font-bold text-yeikar-primary transition-colors hover:bg-yeikar-primary hover:text-yeikar-neutral"
                  >
                    <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M12 5v14M5 12h14" />
                    </svg>
                    Nuevo cliente
                  </button>
                </div>
                <div>
                  <label className="block text-xs uppercase tracking-wider font-bold text-yeikar-neutral/60 font-headline mb-1">
                    Fecha *
                  </label>
                  <input
                    type="date"
                    value={fechaCotizacion}
                    onChange={(e) => setFechaCotizacion(e.target.value)}
                    required
                    className="w-full p-2 border border-yeikar-secondary-light/20 rounded-lg focus:ring-2 focus:ring-yeikar-primary focus:outline-none bg-yeikar-tertiary/20 text-sm font-mono"
                  />
                  <p className="mt-1 text-[11px] text-stone-500">
                    Puedes ponerle una fecha pasada (p. ej. cotizaciones viejas).
                  </p>
                </div>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs uppercase tracking-wider font-bold text-yeikar-neutral/60 font-headline mb-1">
                    Moneda de Cotización *
                  </label>
                  <SearchSelect
                    value={selectedMonedaId}
                    onChange={(v) => {
                      const mId = Number(v);
                      setSelectedMonedaId(mId);
                      if (mId === 1) setTasaCambio(1);
                    }}
                    options={currencies.map((m) => ({
                      value: m.id,
                      label: `${m.codigo} — ${m.nombre} (${m.simbolo})`,
                    }))}
                    placeholder="Seleccione moneda..."
                  />
                </div>

                {selectedMonedaId !== 1 && necesitaTasaCotizacion && (
                  <div>
                    <label className="block text-xs uppercase tracking-wider font-bold text-yeikar-neutral/60 font-headline mb-1">
                      Tasa de Cambio (1 {currencyCode} = X COP) *
                    </label>
                    <input
                      type="number"
                      step="0.000001"
                      min="0.000001"
                      value={tasaCambio}
                      onChange={(e) => setTasaCambio(Number(e.target.value) || 1)}
                      required
                      className="w-full p-2 border border-yeikar-secondary-light/20 rounded-lg focus:ring-2 focus:ring-yeikar-primary focus:outline-none bg-yeikar-tertiary/20 text-sm font-mono"
                    />
                    <p className="mt-1 text-[11px] text-stone-500 font-mono">
                      {formatCurrency(Math.round(globalTotalCalc), currencyCode)} → {(Math.round(globalTotalCalc * tasaCambio)).toLocaleString('es-CO')} COP
                    </p>
                  </div>
                )}
                {selectedMonedaId !== 1 && !necesitaTasaCotizacion && (
                  <p className="sm:col-start-2 self-end text-[11px] text-stone-400 font-mono -mt-1">
                    Todo el pedido está en {currencyCode}: no se necesita tasa de cambio.
                  </p>
                )}
              </div>

              {/* Tasas del día: requeridas cuando hay productos de reventa en
                  moneda extranjera (su precio viene en su moneda y se convierte
                  aquí con la tasa que el usuario ingresa y confirma). */}
              {monedasRequeridas.length > 0 && (
                <div className="rounded-xl border border-amber-200 bg-amber-50/60 p-3 space-y-2">
                  <div>
                    <span className="text-xs uppercase tracking-wider font-bold text-amber-800 font-headline">
                      Tasas del día *
                    </span>
                    <p className="text-[11px] text-amber-800/70 mt-0.5">
                      Confirma cuántos COP vale 1 unidad de cada moneda de tus productos de reventa (cambian a diario).
                    </p>
                  </div>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                    {monedasRequeridas.map((code) => (
                      <div key={code}>
                        <label className="block text-[11px] font-bold text-amber-900 mb-1">
                          1 {code} = ? COP
                        </label>
                        <input
                          type="number"
                          min="0.000001"
                          step="0.000001"
                          placeholder="Ej. 4000"
                          value={tasasDia[code] ?? ''}
                          onChange={(e) => setTasasDia((prev) => ({ ...prev, [code]: e.target.value }))}
                          className="w-full p-2 border border-amber-300 rounded-lg focus:ring-2 focus:ring-yeikar-primary focus:outline-none bg-white text-sm font-mono"
                        />
                      </div>
                    ))}
                  </div>
                </div>
              )}

              <div className="border-t border-yeikar-secondary-light/15 my-4 pt-4">
                <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
                  <div>
                    <h4 className="font-headline font-black text-sm text-yeikar-secondary tracking-tight">
                      Renglones / Productos Cotizados
                    </h4>
                    <p className="text-[11px] text-stone-500 font-body">
                      Seleccione los modelos del catálogo e ingrese dimensiones y condiciones
                    </p>
                  </div>
                  <div className="flex items-center gap-2 flex-wrap w-full sm:w-auto sm:justify-end">
                    <button
                      type="button"
                      onClick={() => handleOpenProductSelector(undefined, 'fabricados')}
                      className="bg-yeikar-secondary text-yeikar-tertiary text-xs font-bold px-3 py-1.5 rounded-lg hover:bg-yeikar-primary hover:text-yeikar-neutral transition-all flex items-center gap-1.5 shadow-sm"
                      title="Abrir catálogo de muebles fabricados para añadir un renglón"
                    >
                      <Package className="w-3.5 h-3.5" />
                      <span>+ Mueble</span>
                    </button>
                    <button
                      type="button"
                      onClick={() => handleOpenProductSelector(undefined, 'reventa')}
                      className="bg-sky-700 text-white text-xs font-bold px-3 py-1.5 rounded-lg hover:bg-sky-600 transition-all flex items-center gap-1.5 shadow-sm"
                      title="Agregar un producto de reventa / stock (colchones, exhibición…)"
                    >
                      <Package className="w-3.5 h-3.5" />
                      <span>+ Reventa</span>
                    </button>
                    <button
                      type="button"
                      onClick={() => handleOpenProductSelector(undefined, 'exhibicion')}
                      className="bg-violet-700 text-white text-xs font-bold px-3 py-1.5 rounded-lg hover:bg-violet-600 transition-all flex items-center gap-1.5 shadow-sm"
                      title="Agregar una pieza del showroom (se vende del stock, sin fabricarse)"
                    >
                      <Package className="w-3.5 h-3.5" />
                      <span>+ Exhibición</span>
                    </button>
                    <button
                      type="button"
                      onClick={addItemInsumo}
                      className="bg-white text-emerald-700 border border-emerald-600 text-xs font-bold px-3 py-1.5 rounded-lg hover:bg-emerald-50 transition-all flex items-center gap-1.5 shadow-sm"
                      title="Añadir insumo de inventario (lámina, tela, etc.)"
                    >
                      <Package className="w-3.5 h-3.5" />
                      <span>+ Insumo</span>
                    </button>
                    <button
                      type="button"
                      onClick={addItemReparacion}
                      className="bg-white text-amber-700 border border-amber-600 text-xs font-bold px-3 py-1.5 rounded-lg hover:bg-amber-50 transition-all flex items-center gap-1.5 shadow-sm"
                      title="Reparar/tapizar un mueble existente del cliente (entra al taller)"
                    >
                      <Wrench className="w-3.5 h-3.5" />
                      <span>+ Reparación</span>
                    </button>
                    <button
                      type="button"
                      onClick={() => addItemServicio('Flete / Envío')}
                      className="bg-white text-stone-700 border border-stone-400 text-xs font-bold px-3 py-1.5 rounded-lg hover:bg-stone-50 transition-all flex items-center gap-1.5 shadow-sm"
                      title="Cobro opcional de flete, envío, instalación u otro servicio"
                    >
                      <Truck className="w-3.5 h-3.5" />
                      <span>+ Flete / Servicio</span>
                    </button>
                    <button
                      type="button"
                      onClick={abrirNuevoProducto}
                      className="bg-yeikar-primary hover:bg-yeikar-primary-dark text-yeikar-neutral text-xs font-bold px-3 py-1.5 rounded-lg transition-all flex items-center gap-1.5 shadow-md hover:shadow"
                      title="Crear un producto nuevo (con foto y precio) y agregarlo al renglón"
                    >
                      <Plus className="w-3.5 h-3.5" />
                      <span>+ Producto nuevo</span>
                    </button>
                  </div>
                </div>

                <div className="space-y-4">
                  {items.map((item, index) => {
                    const selectedProd = item.tipo_item !== 'INSUMO' ? products.find((p) => p.id === Number(item.producto_id)) : null;
                    // Colchón con promo: el plástico que se puede llevar.
                    const promoColchon = !item.es_obsequio && item.tipo_item !== 'INSUMO' && item.producto_id
                      ? promosPorColchon.get(Number(item.producto_id))
                      : undefined;

                    // ── INSUMO: card simplificado ──
                    if (item.tipo_item === 'INSUMO') {
                      // El precio del insumo se registra en COP (moneda del
                      // material); el subtotal se muestra convertido a la
                      // moneda de la cotización. El precio de VENTA es manual
                      // (los insumos cambian de precio y se venden sueltos
                      // esporádicamente); el costo real (compra + pasada) solo
                      // sirve de referencia para calcular la utilidad.
                      const matCatalogo = materiales.find((m) => m.id === Number(item.material_id));
                      const unidadBase = item.materialUnidad
                        ?? matCatalogo?.unidad_medida?.abreviatura
                        ?? 'unidad';
                      const dim = item.materialDimension ?? dimensionalidad(unidadBase);
                      const captura = item.unidadCaptura ?? '';
                      const esConversion = !!captura;
                      const unidadVenta = captura === 'CM'
                        ? 'cm'
                        : captura === 'M'
                          ? 'm'
                          : unidadBase;
                      const factor = factorCapturaABase(dim, unidadBase, captura);
                      const cantidadBase = item.cantidadBase
                        ?? cantidadBaseDesdeCaptura(item.cantidad, factor);
                      const precioUnitCop = Number(item.calcResult?.precio_venta) || 0;
                      const precioUnitMoneda = precioRenglonEnMoneda(item);
                      const subtotal = (isFinite(precioUnitMoneda) ? precioUnitMoneda : 0) * item.cantidad;
                      const costoRealBase = item.insumoCosto?.costo_real ?? 0;
                      const costoRealVenta = costoRealBase * factor;
                      const opcionesUnidad: { valor: UnidadCaptura | ''; label: string }[] =
                        dim === 'VOLUMEN'
                          ? [{ valor: 'CM', label: 'cm' }, { valor: '', label: unidadBase }]
                          : dim === 'LONGITUD'
                            ? (unidadBase.trim().toLowerCase() === 'cm'
                              ? [{ valor: '', label: 'cm' }, { valor: 'M', label: 'm' }]
                              : [{ valor: 'CM', label: 'cm' }, { valor: '', label: unidadBase }])
                            : [];
                      return (
                        <div key={index} className="bg-white p-4 rounded-2xl border border-yeikar-secondary-light/15 border-l-4 border-l-emerald-500 relative space-y-3 shadow-sm">
                          <div className="flex items-center justify-between border-b border-yeikar-secondary-light/10 pb-2">
                            <div className="flex items-center gap-2">
                              <span className="w-5 h-5 rounded-full bg-emerald-600 text-white text-[10px] font-bold flex items-center justify-center font-mono">{index + 1}</span>
                              <span className="text-xs font-bold font-headline text-stone-700 uppercase tracking-wider">Renglón {index + 1}</span>
                              <span className="text-[9px] font-bold uppercase px-2 py-0.5 rounded-md bg-emerald-100 text-emerald-800">Insumo</span>
                            </div>
                            <button type="button" onClick={() => removeItem(index)} className="text-red-500 hover:text-red-700 text-xs font-bold hover:bg-red-50 px-2 py-0.5 rounded-md transition-colors">Eliminar</button>
                          </div>
                          <div className="grid grid-cols-1 sm:grid-cols-12 gap-3 items-end">
                            <div className="sm:col-span-5">
                              <label className="block text-[10px] uppercase tracking-wider font-bold text-yeikar-neutral/60 font-headline mb-1">Material *</label>
                              <SearchSelect
                                value={item.material_id}
                                onChange={(v) => { if (v) void aplicarMaterialInsumo(index, Number(v)); }}
                                loadOptions={async (q) =>
                                  (await productosService.getMateriales(q || undefined))
                                    .filter((m) => m.activo !== false)
                                    .map((m) => ({
                                      value: m.id,
                                      label: `${m.nombre} (${m.unidad_medida?.abreviatura || 'und'}) — COP ${m.costo_base?.toLocaleString('es-CO', { maximumFractionDigits: 2 })}`,
                                    }))
                                }
                                minChars={1}
                                placeholder="Buscar lámina, tela, tornillo..."
                              />
                            </div>
                            <div className="sm:col-span-2">
                              {opcionesUnidad.length > 0 && (
                                <div className="mb-1 flex gap-1" role="group" aria-label="Unidad de captura">
                                  {opcionesUnidad.map((op) => (
                                    <button
                                      key={op.valor || 'base'}
                                      type="button"
                                      onClick={() => cambiarUnidadInsumo(index, op.valor)}
                                      className={`flex-1 rounded-md px-1.5 py-1 text-[10px] font-bold uppercase transition-colors ${
                                        captura === op.valor
                                          ? 'bg-emerald-600 text-white'
                                          : 'bg-stone-100 text-stone-600 hover:bg-stone-200'
                                      }`}
                                      title={
                                        op.valor === 'CM' && dim === 'VOLUMEN'
                                          ? 'Cuenta del taller en cm (÷10.000 = m³)'
                                          : op.valor === 'CM'
                                            ? 'Captura en centímetros (÷100 = m)'
                                            : `Unidad base del inventario (${unidadBase})`
                                      }
                                    >
                                      {op.label}
                                    </button>
                                  ))}
                                </div>
                              )}
                              <label className="block text-[10px] uppercase tracking-wider font-bold text-yeikar-neutral/60 font-headline mb-1">Cantidad ({unidadVenta}) *</label>
                              <CantidadDecimalInput
                                value={item.cantidad}
                                onChange={(cant) => cambiarCantidadInsumo(index, cant)}
                                className="w-full p-2 border border-stone-200 rounded-lg bg-white text-sm font-mono focus:ring-2 focus:ring-yeikar-primary focus:outline-none"
                              />
                            </div>
                            <div className="sm:col-span-3">
                              <label className="block text-[10px] uppercase tracking-wider font-bold text-yeikar-neutral/60 font-headline mb-1">Precio de Venta (COP / {unidadVenta}) *</label>
                              <MontoInput min="0" value={precioUnitCop > 0 ? String(precioUnitCop) : ''} placeholder="Escribe el precio de venta"
                                onChange={(v) => {
                                  const precio = parseFloat(v) || 0;
                                  // El costo NO se pisa con el precio: la utilidad
                                  // se calcula contra el costo real (compra+pasada)
                                  // expresado en la MISMA unidad de venta.
                                  updateItemField(index, 'precioAuto', false);
                                  updateItemField(index, 'calcResult', calcularResultadoInsumo(costoRealVenta, precio));
                                }}
                                className="w-full p-2 border border-stone-200 rounded-lg bg-white text-sm font-mono focus:ring-2 focus:ring-yeikar-primary focus:outline-none"
                              />
                            </div>
                            <div className="sm:col-span-2 text-right">
                              <span className="text-[10px] uppercase tracking-wider font-bold text-yeikar-neutral/60 font-headline">Subtotal</span>
                              <div className="text-sm font-bold font-mono text-yeikar-secondary">{formatCurrency(subtotal, currencyCode)}</div>
                            </div>
                          </div>
                          {esConversion && (
                            <div className="text-[11px] text-emerald-900/80 bg-emerald-50/60 border border-emerald-100 rounded-lg px-3 py-1.5">
                              <b>{Number(item.cantidad).toLocaleString('es-CO', { maximumFractionDigits: 4 })}</b> {unidadVenta} ={' '}
                              <b>{cantidadBase.toLocaleString('es-CO', { maximumFractionDigits: 4 })} {unidadBase}</b>
                              {dim === 'VOLUMEN' && captura === 'CM' && (
                                <span className="text-emerald-700"> · cuenta del taller ÷ 10.000</span>
                              )}
                              {dim === 'LONGITUD' && captura === 'CM' && (
                                <span className="text-emerald-700"> · ÷ 100</span>
                              )}
                            </div>
                          )}
                          {item.insumoCosto && (
                            <div className="text-[11px] text-emerald-900/80 bg-emerald-50/60 border border-emerald-100 rounded-lg px-3 py-1.5 flex flex-wrap gap-x-4 gap-y-0.5">
                              <span>Compra ({unidadBase}): <b>{formatCurrency(item.insumoCosto.costo_compra, 'COP')}</b></span>
                              <span>Pasada ({unidadBase}): <b>{formatCurrency(item.insumoCosto.pasada_unitaria, 'COP')}</b></span>
                              <span>Costo real ({unidadVenta}): <b>{formatCurrency(costoRealVenta, 'COP')}</b></span>
                              {esConversion && (
                                <span className="text-emerald-700">
                                  ({formatCurrency(costoRealBase, 'COP')} / {unidadBase})
                                </span>
                              )}
                              <span className="text-emerald-700">
                                {costoRealBase > 0
                                  ? '→ Precio precargado = costo real (puedes ajustarlo)'
                                  : '→ Este material no tiene costo registrado: escribe el precio'}
                              </span>
                            </div>
                          )}
                          <div>
                            <input type="text" value={item.observaciones} placeholder="Observaciones (opcional)"
                              onChange={(e) => updateItemField(index, 'observaciones', e.target.value)}
                              className="w-full p-1.5 border border-stone-200 rounded-lg bg-white text-xs focus:ring-2 focus:ring-yeikar-primary focus:outline-none"
                            />
                          </div>
                        </div>
                      );
                    }

                    // ── REPARACION / SERVICIO: pieza del cliente o cobro libre ──
                    if (item.tipo_item === 'REPARACION' || item.tipo_item === 'SERVICIO') {
                      const esReparacion = item.tipo_item === 'REPARACION';
                      const precioManual = Number(item.calcResult?.precio_venta) || 0;
                      const subtotal = precioManual * item.cantidad;
                      const aplicarLibre = (precio: number, costo: number) => {
                        updateItemField(index, 'calcResult', {
                          costo_materiales: esReparacion ? costo : 0,
                          costo_mano_obra: esReparacion ? costo : 0,
                          costo_gastos_indirectos: 0,
                          costo_total: costo,
                          impuesto_porcentaje: 0,
                          impuestos: 0,
                          base_con_impuestos: precio,
                          precio_sugerido: precio,
                          precio_venta: precio,
                          materiales_detalle: [],
                          moneda_codigo: currencyCode,
                        });
                      };
                      return (
                        <div key={index} className="bg-white p-4 rounded-2xl border border-yeikar-secondary-light/15 relative space-y-3 shadow-sm border-l-4 border-l-amber-500">
                          <div className="flex items-center justify-between border-b border-yeikar-secondary-light/10 pb-2">
                            <div className="flex items-center gap-2">
                              <span className="w-5 h-5 rounded-full bg-amber-600 text-white text-[10px] font-bold flex items-center justify-center font-mono">{index + 1}</span>
                              <span className="text-xs font-bold font-headline text-stone-700 uppercase tracking-wider">Renglón {index + 1}</span>
                              <span className={`text-[9px] font-bold uppercase px-2 py-0.5 rounded-md ${esReparacion ? 'bg-amber-100 text-amber-800' : 'bg-stone-100 text-stone-700'}`}>
                                {esReparacion ? 'Reparación' : 'Servicio'}
                              </span>
                              {!esReparacion && (
                                <span className="text-[9px] text-stone-400">Cobro opcional (flete, instalación…)</span>
                              )}
                            </div>
                            <button type="button" onClick={() => removeItem(index)} className="text-red-500 hover:text-red-700 text-xs font-bold hover:bg-red-50 px-2 py-0.5 rounded-md transition-colors">Eliminar</button>
                          </div>
                          <div>
                            <label className="block text-[10px] uppercase tracking-wider font-bold text-yeikar-neutral/60 font-headline mb-1">
                              {esReparacion ? 'Mueble a reparar / trabajo a realizar *' : 'Descripción del servicio (p. ej. flete a zona) *'}
                            </label>
                            <textarea
                              value={item.descripcion_especifica || ''}
                              onChange={(e) => updateItemField(index, 'descripcion_especifica', e.target.value)}
                              rows={2}
                              placeholder={esReparacion ? 'Ej: Tapizar sofá de 3 puestos con tela lino beige y retapizar cojines' : 'Ej: Flete / Envío de mueble a distancia'}
                              className="w-full p-2 border border-stone-200 rounded-lg bg-white text-sm focus:ring-2 focus:ring-yeikar-primary focus:outline-none"
                            />
                          </div>
                          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5 items-end">
                            <div>
                              <label className="block text-[10px] uppercase font-bold text-yeikar-neutral/60 mb-1">Cantidad</label>
                              <input type="number" min="1" value={item.cantidad}
                                onChange={(e) => updateItemField(index, 'cantidad', parseInt(e.target.value) || 1)}
                                className="w-full p-2 border border-stone-200 rounded-lg focus:ring-2 focus:ring-yeikar-primary focus:outline-none bg-white text-xs font-mono font-bold" />
                            </div>
                            <div>
                              <label className="block text-[10px] uppercase font-bold text-yeikar-neutral/60 mb-1">Precio de venta *</label>
                              <MontoInput min="0" value={precioManual > 0 ? String(precioManual) : ''} placeholder={`${currencyCode}`}
                                onChange={(v) => aplicarLibre(parseFloat(v) || 0, Number(item.calcResult?.costo_total) || 0)}
                                className="w-full p-2 border border-stone-200 rounded-lg focus:ring-2 focus:ring-yeikar-primary focus:outline-none bg-white text-xs font-mono font-bold" />
                            </div>
                            <div>
                              <label className="block text-[10px] uppercase font-bold text-yeikar-neutral/60 mb-1">Costo estimado (COP)</label>
                              <MontoInput min="0" value={(item.calcResult?.costo_total && item.calcResult.costo_total > 0) ? String(Number(item.calcResult.costo_total)) : ''}
                                placeholder="Opcional"
                                onChange={(v) => aplicarLibre(precioManual, parseFloat(v) || 0)}
                                className="w-full p-2 border border-stone-200 rounded-lg focus:ring-2 focus:ring-yeikar-primary focus:outline-none bg-white text-xs font-mono" />
                            </div>
                            <div className="text-right">
                              <span className="text-[10px] uppercase tracking-wider font-bold text-yeikar-neutral/60 font-headline">Subtotal</span>
                              <div className="text-sm font-bold font-mono text-yeikar-secondary">{formatCurrency(subtotal, currencyCode)}</div>
                            </div>
                          </div>
                          {esReparacion && (
                            <p className="text-[11px] text-amber-800/80 bg-amber-50/60 border border-amber-100 rounded-lg px-3 py-1.5">
                              El mueble entra al taller (Tapicería, etc.): al finalizar la orden se conocerá el costo real y el margen se compara con este estimado.
                            </p>
                          )}
                        </div>
                      );
                    }

                    // ── A MEDIDA: FABRICADO sin producto (descripción + precio manual) ──
                    // Así entra un juego completo de la nota de papel: un renglón,
                    // un precio global, y el taller recibe las piezas detectadas.
                    if (item.tipo_item === 'FABRICADO' && !item.producto_id) {
                      const precioManual = Number(item.calcResult?.precio_venta) || 0;
                      const subtotal = precioManual * item.cantidad;
                      const aplicarLibre = (precio: number, costo: number) => {
                        updateItemField(index, 'calcResult', {
                          costo_materiales: costo,
                          costo_mano_obra: 0,
                          costo_gastos_indirectos: 0,
                          costo_total: costo,
                          impuesto_porcentaje: 0,
                          impuestos: 0,
                          base_con_impuestos: precio,
                          precio_sugerido: precio,
                          precio_venta: precio,
                          materiales_detalle: [],
                          moneda_codigo: currencyCode,
                        });
                      };
                      return (
                        <div key={index} className="bg-white p-4 rounded-2xl border border-yeikar-secondary-light/15 relative space-y-3 shadow-sm border-l-4 border-l-sky-500">
                          <div className="flex items-center justify-between border-b border-yeikar-secondary-light/10 pb-2">
                            <div className="flex items-center gap-2">
                              <span className="w-5 h-5 rounded-full bg-sky-600 text-white text-[10px] font-bold flex items-center justify-center font-mono">{index + 1}</span>
                              <span className="text-xs font-bold font-headline text-stone-700 uppercase tracking-wider">Renglón {index + 1}</span>
                              <span className="text-[9px] font-bold uppercase px-2 py-0.5 rounded-md bg-sky-100 text-sky-800">A medida</span>
                            </div>
                            <button type="button" onClick={() => removeItem(index)} className="text-red-500 hover:text-red-700 text-xs font-bold hover:bg-red-50 px-2 py-0.5 rounded-md transition-colors">Eliminar</button>
                          </div>
                          <div>
                            <label className="block text-[10px] uppercase tracking-wider font-bold text-yeikar-neutral/60 font-headline mb-1">
                              Descripción del mueble / juego *
                            </label>
                            <textarea
                              value={item.descripcion_especifica || ''}
                              onChange={(e) => updateItemField(index, 'descripcion_especifica', e.target.value)}
                              rows={2}
                              placeholder="Ej: Juego de sala: sofá de 3 puestos + 2 poltronas, tapizado en tela…"
                              className="w-full p-2 border border-stone-200 rounded-lg bg-white text-sm focus:ring-2 focus:ring-yeikar-primary focus:outline-none"
                            />
                          </div>
                          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5 items-end">
                            <div>
                              <label className="block text-[10px] uppercase font-bold text-yeikar-neutral/60 mb-1">Cantidad</label>
                              <input type="number" min="1" value={item.cantidad}
                                onChange={(e) => updateItemField(index, 'cantidad', parseInt(e.target.value) || 1)}
                                className="w-full p-2 border border-stone-200 rounded-lg focus:ring-2 focus:ring-yeikar-primary focus:outline-none bg-white text-xs font-mono font-bold" />
                            </div>
                            <div>
                              <label className="block text-[10px] uppercase font-bold text-yeikar-neutral/60 mb-1">Precio de venta *</label>
                              <MontoInput min="0" value={precioManual > 0 ? String(precioManual) : ''} placeholder={`${currencyCode}`}
                                onChange={(v) => aplicarLibre(parseFloat(v) || 0, Number(item.calcResult?.costo_total) || 0)}
                                className="w-full p-2 border border-stone-200 rounded-lg focus:ring-2 focus:ring-yeikar-primary focus:outline-none bg-white text-xs font-mono font-bold" />
                            </div>
                            <div>
                              <label className="block text-[10px] uppercase font-bold text-yeikar-neutral/60 mb-1">Costo estimado (COP)</label>
                              <MontoInput min="0" value={(item.calcResult?.costo_total && item.calcResult.costo_total > 0) ? String(Number(item.calcResult.costo_total)) : ''}
                                placeholder="Opcional"
                                onChange={(v) => aplicarLibre(precioManual, parseFloat(v) || 0)}
                                className="w-full p-2 border border-stone-200 rounded-lg focus:ring-2 focus:ring-yeikar-primary focus:outline-none bg-white text-xs font-mono" />
                            </div>
                            <div className="text-right">
                              <span className="text-[10px] uppercase tracking-wider font-bold text-yeikar-neutral/60 font-headline">Subtotal</span>
                              <div className="text-sm font-bold font-mono text-yeikar-secondary">{formatCurrency(subtotal, currencyCode)}</div>
                            </div>
                          </div>
                          <PiezasJuegoEditor
                            piezas={item.piezas ?? []}
                            onChange={(piezas) => updateItemField(index, 'piezas', piezas)}
                          />
                          <p className="text-[11px] text-sky-900/80 bg-sky-50/60 border border-sky-100 rounded-lg px-3 py-1.5">
                            Se fabrica a medida. Si agregas las piezas del juego, cada una se produce y
                            costea por separado; si no, el taller verá las piezas detectadas de la
                            descripción y registrará los materiales y la mano de obra reales.
                          </p>
                        </div>
                      );
                    }

                    // ── FABRICADO / REVENTA ──
                    const basePrecio = Number(selectedProd?.precio_venta_base ?? selectedProd?.precio_costo_base ?? 0);
                    const monedaExtranjera = selectedProd?.moneda && selectedProd.moneda.codigo !== 'COP' ? selectedProd.moneda.codigo : null;
                    const baseMostrar = isFinite(basePrecio) && basePrecio > 0
                      ? (monedaExtranjera
                        ? `${formatCurrency(basePrecio, monedaExtranjera)} ${monedaExtranjera}`
                        : `${formatCurrency(basePrecio / (selectedMonedaId === 1 ? 1 : tasaCambio), currencyCode)} ${currencyCode}`)
                      : null;
                    const firstPhoto = selectedProd?.fotos && selectedProd.fotos.length > 0 ? selectedProd.fotos[0] : null;

                    return (
                      <div key={index} className="bg-white p-4 rounded-2xl border border-yeikar-secondary-light/15 relative space-y-3.5 shadow-sm">
                        {/* Row Header */}
                        <div className="flex items-center justify-between border-b border-yeikar-secondary-light/10 pb-2">
                          <div className="flex items-center gap-2">
                            <span className="w-5 h-5 rounded-full bg-yeikar-secondary text-yeikar-tertiary text-[10px] font-bold flex items-center justify-center font-mono">
                              {index + 1}
                            </span>
                            <span className="text-xs font-bold font-headline text-stone-700 uppercase tracking-wider">
                              Renglón {index + 1}
                            </span>
                            <span className="text-[9px] font-bold uppercase px-2 py-0.5 rounded-md bg-yeikar-tertiary text-yeikar-secondary border border-yeikar-secondary-light/10">
                                {esItemStock(selectedProd) ? 'De stock' : 'Fabricado'}
                            </span>
                            {item.es_obsequio && (
                              <span className="text-[9px] font-bold uppercase px-2 py-0.5 rounded-md bg-fuchsia-50 text-fuchsia-700 border border-fuchsia-200">
                                Obsequio promo
                              </span>
                            )}
                            {promoColchon && (
                              <span
                                className="text-[9px] font-bold uppercase px-2 py-0.5 rounded-md bg-fuchsia-50 text-fuchsia-700 border border-fuchsia-200"
                                title="Promoción: por este colchón el cliente se lleva el plástico sin costo"
                              >
                                Incluye obsequio: {promoColchon.obsequio_nombre}
                              </span>
                            )}
                              {item.calcResult?.fuente_precio === 'estimado_sin_estructura' && (
                                <span
                                  className="text-[9px] font-bold uppercase px-2 py-0.5 rounded-md bg-yeikar-primary/10 text-yeikar-primary-dark border border-yeikar-primary/25"
                                  title="Precio ESTIMADO: este mueble aún no tiene estructura de costos. Cuando la tengas, el precio se recalcula solo."
                                >
                                  Precio estimado
                                </span>
                              )}
                              {item.calcResult?.fuente_precio === 'sin_definir' && selectedProd && (
                                <button
                                  type="button"
                                  onClick={() => abrirDefinirPrecio(selectedProd)}
                                  className="text-[9px] font-bold uppercase px-2 py-0.5 rounded-md bg-red-50 text-red-700 border border-red-200 hover:bg-red-100 transition-colors"
                                  title="Sin estructura de costos NI precio estimado. Haz clic para definir el precio de venta y cotizarlo ahora."
                                >
                                  Sin precio — definir
                                </button>
                              )}
                          </div>

                          <button
                              type="button"
                              onClick={() => removeItem(index)}
                              className="text-red-500 hover:text-red-700 text-xs font-bold font-headline hover:bg-red-50 px-2 py-0.5 rounded-md transition-colors"
                              title="Eliminar este renglón"
                            >
                              Eliminar
                            </button>
                        </div>

                        {/* Product Summary (producto siempre seleccionado vía + Mueble / + Producto nuevo) */}
                        {selectedProd ? (
                          <div className="flex items-center justify-between gap-3 rounded-xl bg-yeikar-tertiary/40 border border-yeikar-secondary-light/10 px-3 py-2.5">
                            <div className="flex items-center gap-2.5 min-w-0">
                              {firstPhoto ? (
                                <div className="relative w-10 h-10 rounded-lg overflow-hidden border border-stone-200 shrink-0 bg-stone-100">
                                  <AdjuntoImagen adjunto={firstPhoto} alt={selectedProd.nombre} className="w-full h-full object-cover" />
                                  {(selectedProd.fotos?.length ?? 0) > 1 && (
                                    <span
                                      className="absolute bottom-0 right-0 bg-yeikar-secondary/90 text-yeikar-tertiary text-[8px] font-mono font-bold px-1 leading-3 rounded-tl-md"
                                      title={`${selectedProd.fotos?.length} fotos del producto`}
                                    >
                                      +{(selectedProd.fotos?.length ?? 0) - 1}
                                    </span>
                                  )}
                                </div>
                              ) : (
                                <div className="w-10 h-10 rounded-lg bg-yeikar-tertiary/60 border border-yeikar-secondary-light/10 flex items-center justify-center text-yeikar-secondary/60 shrink-0">
                                  <Package className="w-4 h-4" />
                                </div>
                              )}
                              <div className="min-w-0">
                                <div className="font-headline font-bold text-sm text-yeikar-secondary truncate">
                                  {selectedProd.nombre}
                                </div>
                                <div className="text-[11px] text-stone-500 font-mono truncate">
                                  {[selectedProd.tipo_producto?.nombre, baseMostrar, !esItemStock(selectedProd) && (selectedProd.ancho_base || selectedProd.largo_base) ? `Base ${Number(selectedProd.ancho_base || 1).toFixed(2)}m × ${Number(selectedProd.largo_base || 1).toFixed(2)}m` : null]
                                    .filter(Boolean)
                                    .join(' · ') || '—'}
                                </div>
                              </div>
                            </div>
                            <button
                              type="button"
                              onClick={() => handleOpenProductSelector(index)}
                              className="text-xs font-bold text-yeikar-primary hover:underline shrink-0 whitespace-nowrap"
                              title="Cambiar el producto seleccionado"
                            >
                              Cambiar
                            </button>
                          </div>
                        ) : (
                          <div className="flex items-center justify-between gap-3 rounded-xl border border-dashed border-stone-300 px-3 py-2.5 text-stone-500">
                            <span className="text-xs font-body">
                              Producto no disponible
                            </span>
                            <button
                              type="button"
                              onClick={() => handleOpenProductSelector(index)}
                              className="text-xs font-bold text-yeikar-primary hover:underline shrink-0 whitespace-nowrap"
                              title="Seleccionar otro producto del catálogo"
                            >
                              Cambiar
                            </button>
                          </div>
                        )}

                        {/* Cantidad y parámetros comerciales. Las medidas del
                            mueble salen de su ficha (base del producto): no se
                            piden una por una en cada cotización. */}
                        {item.es_obsequio && (
                          <p className="text-[11px] text-fuchsia-800 bg-fuchsia-50/60 border border-fuchsia-100 rounded-lg px-3 py-1.5">
                            Obsequio de promoción: va incluido con el colchón, no se cobra.
                            Al facturar sale del inventario de plásticos.
                          </p>
                        )}
                        <div className="grid grid-cols-1 sm:grid-cols-3 gap-2.5 pt-1">
                          <div>
                            <label className="block text-[10px] uppercase font-bold text-yeikar-neutral/60 mb-1">
                              Cantidad
                            </label>
                            <input
                              type="number"
                              min="1"
                              value={item.cantidad}
                              onChange={(e) => updateItemField(index, 'cantidad', parseInt(e.target.value) || 1)}
                              required
                              className="w-full p-2 border border-stone-200 rounded-lg focus:ring-2 focus:ring-yeikar-primary focus:outline-none bg-white text-xs font-mono font-bold"
                            />
                          </div>

                          <div className="sm:col-span-2">
                            <label className="block text-[10px] uppercase font-bold text-yeikar-neutral/60 mb-1">
                              Observación / Especificaciones de este mueble
                            </label>
                            <input
                              type="text"
                              placeholder="Ej: Tela lino gris perla, patas en roble..."
                              value={item.observaciones}
                              onChange={(e) => updateItemField(index, 'observaciones', e.target.value)}
                              className="w-full p-2 border border-stone-200 rounded-lg focus:ring-2 focus:ring-yeikar-primary focus:outline-none bg-white text-xs"
                            />
                          </div>
                        </div>

                        {esItemReventa(item) && (
                          <span className="block text-[10px] text-yeikar-secondary bg-yeikar-tertiary border border-yeikar-secondary-light/15 rounded-lg px-2.5 py-2 w-full font-medium">
                            Reventa comercial {baseMostrar ? `· Costo ref: ${baseMostrar}` : ''}
                          </span>
                        )}
                        {item.tipo_item === 'FABRICADO' && (
                          <PiezasJuegoEditor
                            piezas={item.piezas ?? []}
                            onChange={(piezas) => updateItemField(index, 'piezas', piezas)}
                          />
                        )}
                      </div>
                    );
                  })}

                  {items.length === 0 && (
                    <div className="rounded-2xl border-2 border-dashed border-yeikar-secondary-light/25 bg-yeikar-tertiary/30 px-6 py-10 text-center">
                      <div className="w-12 h-12 rounded-2xl bg-yeikar-primary/15 text-yeikar-secondary flex items-center justify-center mx-auto mb-3">
                        <Package className="w-6 h-6" />
                      </div>
                      <h5 className="font-headline font-bold text-sm text-yeikar-secondary mb-1">
                        No hay productos aún
                      </h5>
                      <p className="text-xs text-stone-500 max-w-sm mx-auto leading-relaxed">
                        Usá los botones de arriba para armar la cotización:{' '}
                        <b>+ Mueble</b> (catálogo), <b>+ Reventa</b> (stock), <b>+ Exhibición</b> (showroom),{' '}
                        <b>+ Insumo</b> (material suelto), <b>+ Reparación</b>, <b>+ Flete/Servicio</b> o{' '}
                        <b>+ Producto nuevo</b> (crear y cotizar al instante).
                      </p>
                    </div>
                  )}
                </div>
              </div>

              <div>
                <label className="block text-xs uppercase tracking-wider font-bold text-yeikar-neutral/60 font-headline mb-1">
                  Nota global de la cotización
                </label>
                <textarea
                  value={observaciones}
                  onChange={(e) => setObservaciones(e.target.value)}
                  rows={2}
                  className="w-full p-2 border border-yeikar-secondary-light/20 rounded-lg focus:ring-2 focus:ring-yeikar-primary focus:outline-none bg-yeikar-tertiary/20 text-sm"
                  placeholder="Observaciones generales para toda la cotización/orden..."
                />
              </div>

              {errorForm && (
                <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700" role="alert">
                  {errorForm}
                </div>
              )}

              <div className="flex items-center justify-end gap-3 pt-4 border-t border-yeikar-secondary-light/10">
                <button
                  type="button"
                  onClick={() => setIsFormOpen(false)}
                  className="px-4 py-2 border border-yeikar-secondary-light/20 hover:bg-yeikar-tertiary/20 rounded-lg text-sm font-headline"
                >
                  Cancelar
                </button>
                <button
                  type="submit"
                  className="px-5 py-2 bg-yeikar-primary text-yeikar-neutral font-bold rounded-lg shadow-md hover:bg-yeikar-primary-light transition-all text-sm font-headline"
                >
                  {editingQuote ? 'Actualizar' : 'Guardar Cotización'}
                </button>
              </div>
            </form>

            {/* Calculations Breakdown — en móvil queda dentro del scroll del modal;
                en desktop es columna propia con su propio scroll acotado */}
            <div className="w-full md:w-72 xl:w-80 bg-yeikar-neutral text-yeikar-tertiary p-4 sm:p-6 flex flex-col justify-between border-t md:border-t-0 md:border-l border-yeikar-secondary/20 shrink-0 md:max-h-[90vh] md:overflow-y-auto">
              <div className="space-y-6">
                <div>
                  <h4 className="font-headline font-bold text-sm text-yeikar-primary tracking-wider uppercase mb-3">
                    Totales de Cotización
                  </h4>
                  <div className="space-y-2">
                    <div className="flex justify-between text-xs text-yeikar-tertiary/60">
                      <span>{items.some(esItemReventa) ? 'Costo de Compra:' : 'Costo Total Fábrica:'}</span>
                      <span className="font-mono font-bold">{formatCurrency(Math.round(globalCostoTotal), currencyCode)}</span>
                    </div>
                    <div className="flex justify-between text-xs text-green-500">
                      <span>Ganancia Estimada:</span>
                      <span className="font-mono font-bold">+ {formatCurrency(Math.round(globalTotalCalc - globalCostoTotal), currencyCode)}</span>
                    </div>
                  </div>
                </div>

                {/* Selector de renglón si hay múltiples */}
                {items.length > 1 && (
                  <div className="border-t border-yeikar-secondary-light/10 pt-3">
                    <label className="block text-[10px] font-bold text-yeikar-tertiary/50 uppercase mb-1">
                      Ver Desglose de:
                    </label>
                    <select
                      value={desgloseIndex}
                      onChange={(e) => setDesgloseIndex(Number(e.target.value))}
                      className="w-full p-1.5 bg-yeikar-secondary/20 border border-yeikar-secondary-light/20 rounded-lg text-xs text-yeikar-tertiary focus:outline-none"
                    >
                      {items.map((item, idx) => {
                        const prod = products.find(p => p.id === Number(item.producto_id));
                        const mat = item.tipo_item === 'INSUMO'
                          ? materiales.find(m => m.id === Number(item.material_id))
                          : null;
                        const libre = (item.tipo_item === 'REPARACION' || item.tipo_item === 'SERVICIO') ? item.descripcion_especifica?.trim() : null;
                        const label = libre || mat?.nombre || prod?.nombre || 'Renglón';
                        return (
                          <option key={idx} value={idx} className="bg-yeikar-neutral text-yeikar-tertiary">
                            Renglón {idx + 1}: {label}{item.tipo_item === 'INSUMO' ? ' (Insumo)' : (item.tipo_item === 'REPARACION' || item.tipo_item === 'SERVICIO') ? ` (${item.tipo_item === 'REPARACION' ? 'Reparación' : 'Servicio'})` : ` (${item.ancho}x${item.largo}m)`}
                          </option>
                        );
                      })}
                    </select>
                  </div>
                )}

                {/* Desglose Detallado de Secciones de ese Renglón */}
                {items[desgloseIndex] && (
                <div className="border-t border-yeikar-secondary-light/10 pt-3 space-y-3">
                  <h5 className="text-[10px] font-bold text-yeikar-primary uppercase tracking-widest">
                    {esItemReventa(items[desgloseIndex]) ? 'Detalle de Reventa' : `Desglose de Secciones (Renglón ${desgloseIndex + 1})`}
                  </h5>
                  {esItemReventa(items[desgloseIndex]) && items[desgloseIndex]?.calcResult ? (
                    <div className="bg-yeikar-secondary/10 rounded-lg p-2.5 space-y-1.5 border border-yeikar-secondary-light/5 text-[10px] text-yeikar-tertiary/75 font-mono">
                      <div className="flex justify-between">
                        <span>Costo de compra</span>
                        <span className="font-bold">{formatCurrency(convertirAPrecioCotizacion(Number(items[desgloseIndex].calcResult?.costo_total), items[desgloseIndex].calcResult?.moneda_codigo), currencyCode)}</span>
                      </div>
                      <div className="flex justify-between">
                        <span>Precio de lista</span>
                        <span className="font-bold">{formatCurrency(convertirAPrecioCotizacion(Number(items[desgloseIndex].calcResult?.precio_venta), items[desgloseIndex].calcResult?.moneda_codigo), currencyCode)}</span>
                      </div>
                      <div className="flex justify-between text-green-500 border-t border-yeikar-secondary-light/15 pt-1.5">
                        <span>Margen</span>
                        <span className="font-bold">+ {formatCurrency(
                          convertirAPrecioCotizacion(Number(items[desgloseIndex].calcResult?.precio_venta), items[desgloseIndex].calcResult?.moneda_codigo)
                          - convertirAPrecioCotizacion(Number(items[desgloseIndex].calcResult?.costo_total), items[desgloseIndex].calcResult?.moneda_codigo),
                          currencyCode
                        )}</span>
                      </div>
                    </div>
                  ) : items[desgloseIndex]?.calcResult?.desglose_por_seccion ? (
                    <div className="space-y-3">
                      {Object.entries(items[desgloseIndex].calcResult.desglose_por_seccion).map(([seccionNombre, datosSec]: [string, any]) => (
                        <div key={seccionNombre} className="bg-yeikar-secondary/10 rounded-lg p-2.5 space-y-1.5 border border-yeikar-secondary-light/5">
                          <div className="flex justify-between font-bold text-[11px] text-yeikar-primary border-b border-yeikar-secondary-light/15 pb-1">
                            <span className="uppercase truncate pr-1">{seccionNombre}</span>
                            <span className="font-mono text-yeikar-primary-light">{formatCurrency(Number(datosSec.total_seccion) / (selectedMonedaId === 1 ? 1 : tasaCambio), currencyCode)}</span>
                          </div>
                          <div className="space-y-0.5 text-[10px] text-yeikar-tertiary/75 font-mono">
                            {datosSec.costo_insumos > 0 && (
                              <div className="flex justify-between">
                                <span>Insumos</span>
                                <span>{formatCurrency(Number(datosSec.costo_insumos) / (selectedMonedaId === 1 ? 1 : tasaCambio), currencyCode)}</span>
                              </div>
                            )}
                            {datosSec.total_costos_produccion > 0 && (
                              <div className="flex justify-between text-amber-500 font-medium">
                                <span>C. Producción</span>
                                <span>+{formatCurrency(Number(datosSec.total_costos_produccion) / (selectedMonedaId === 1 ? 1 : tasaCambio), currencyCode)}</span>
                              </div>
                            )}
                            {datosSec.gasto_seccion > 0 && (
                              <div className="flex justify-between">
                                <span>Gastos ({datosSec.pct_gastos_seccion}%)</span>
                                <span>+{formatCurrency(Number(datosSec.gasto_seccion) / (selectedMonedaId === 1 ? 1 : tasaCambio), currencyCode)}</span>
                              </div>
                            )}
                          </div>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <p className="text-[10px] text-yeikar-tertiary/40 italic">
                      Selecciona un mueble válido para ver su desglose.
                    </p>
                  )}
                </div>
                )}
              </div>

              <div className="border-t border-yeikar-secondary/40 pt-4 mt-6">
                <span className="text-[10px] text-yeikar-tertiary/40 uppercase tracking-widest block mb-1">
                  PRECIO TOTAL SUGERIDO:
                </span>
                <div className="text-2xl font-black text-yeikar-primary font-mono">
                  {formatCurrency(Math.round(globalTotalCalc), currencyCode)}
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Convert Quote to Order Modal */}
      {isConvertOpen && (
        <div className="fixed inset-0 bg-yeikar-neutral/50 backdrop-blur-sm flex items-center justify-center p-4 z-50 animate-fade-in">
          <div className="bg-white rounded-xl border border-yeikar-secondary-light/10 shadow-2xl w-full max-w-lg overflow-hidden">
            <div className="bg-yeikar-neutral p-4 text-yeikar-tertiary flex items-center justify-between">
              <h3 className="font-headline font-bold text-lg text-yeikar-primary">
                Convertir a Pedido de Fábrica
              </h3>
            </div>
            <div className="p-6 space-y-4">
              <p className="text-sm text-yeikar-neutral/80 font-body">
                Vas a generar un nuevo pedido para <strong>{selectedQuoteForConvert?.cliente?.nombre}</strong>.
                El pedido entrará directamente a producción y la factura se creará automáticamente
                en la moneda de la cotización.
              </p>

              {/* Info de la cotización (bloqueada) */}
              <div className="bg-yeikar-tertiary/30 border border-yeikar-secondary-light/10 rounded-lg p-3 text-xs text-yeikar-neutral/80 space-y-0.5">
                <div className="flex justify-between">
                  <span className="font-bold text-yeikar-neutral/50">Cotización</span>
                  <span className="font-mono">{quoteMoneda?.nombre} ({quoteMoneda?.codigo} {quoteMoneda?.simbolo})</span>
                </div>
                <div className="flex justify-between">
                  <span className="font-bold text-yeikar-neutral/50">Total</span>
                  <span className="font-mono font-bold text-yeikar-secondary">
                    {formatCurrency(Math.round(quoteTotal), quoteMoneda?.codigo ?? 'COP')}
                  </span>
                </div>
                {Number(selectedQuoteForConvert?.tasa_cambio) && quoteMoneda?.codigo !== 'COP' && (
                  <div className="flex justify-between">
                    <span className="font-bold text-yeikar-neutral/50">Tasa fijada al cotizar</span>
                    <span className="font-mono">
                      1 {quoteMoneda?.codigo} = {formatCurrency(Number(selectedQuoteForConvert?.tasa_cambio), 'COP')}
                    </span>
                  </div>
                )}
              </div>

              <div>
                <label className="block text-xs uppercase tracking-wider font-bold text-yeikar-neutral/60 font-headline mb-1">
                  Fecha Estimada de Entrega
                </label>
                <input
                  type="date"
                  value={deliveryDate}
                  onChange={(e) => setDeliveryDate(e.target.value)}
                  className="w-full p-2 border border-yeikar-secondary-light/20 rounded-lg focus:ring-2 focus:ring-yeikar-primary focus:outline-none bg-yeikar-tertiary/20 font-mono text-sm"
                />
              </div>

              {/* Abono inicial (opcional) */}
              <div className="border-t border-yeikar-secondary-light/10 pt-4">
                <div className="flex items-center justify-between mb-2">
                  <label className="block text-xs uppercase tracking-wider font-bold text-yeikar-neutral/60 font-headline">
                    Abono inicial <span className="normal-case font-normal text-yeikar-neutral/40">(opcional)</span>
                  </label>
                  <span className="text-xs font-mono font-bold text-yeikar-primary">
                    {abonoActivo && tasaAbonoValida
                      ? `= ${formatCurrency(Math.round(abonoEnMonedaCotizacion), quoteMoneda?.codigo ?? 'COP')}`
                      : abonoActivo
                      ? '— indica la tasa'
                      : 'Sin abono'}
                  </span>
                </div>

                {/* Modo: porcentaje o monto fijo */}
                <div className="mb-2 grid grid-cols-2 gap-1 rounded-lg border border-yeikar-secondary-light/10 bg-yeikar-tertiary/40 p-1">
                  <button
                    type="button"
                    onClick={() => setAdelantoModo('pct')}
                    className={`rounded-md py-1.5 text-xs font-bold transition-colors ${
                      adelantoModo === 'pct'
                        ? 'bg-yeikar-primary text-yeikar-neutral'
                        : 'text-yeikar-neutral/55 hover:text-yeikar-secondary'
                    }`}
                  >
                    Porcentaje
                  </button>
                  <button
                    type="button"
                    onClick={() => setAdelantoModo('monto')}
                    className={`rounded-md py-1.5 text-xs font-bold transition-colors ${
                      adelantoModo === 'monto'
                        ? 'bg-yeikar-primary text-yeikar-neutral'
                        : 'text-yeikar-neutral/55 hover:text-yeikar-secondary'
                    }`}
                  >
                    Monto fijo
                  </button>
                </div>

                <div className="flex flex-wrap gap-2">
                  <div className="relative flex-1 min-w-32">
                    {adelantoModo === 'pct' ? (
                      <>
                        <input
                          type="number"
                          min="0"
                          max="100"
                          placeholder="0"
                          value={adelantoPct}
                          onChange={(e) => setAdelantoPct(e.target.value)}
                          className="w-full p-2 pr-8 border border-yeikar-secondary-light/20 rounded-lg focus:ring-2 focus:ring-yeikar-primary focus:outline-none bg-yeikar-tertiary/20 font-mono text-sm"
                        />
                        <span className="absolute right-3 top-1/2 -translate-y-1/2 text-sm text-yeikar-neutral/40 font-bold">%</span>
                      </>
                    ) : (
                      <MontoInput
                        min="0"
                        placeholder={`Monto en ${monedaAdelantoSel?.codigo ?? '...'}`}
                        value={adelantoMonto}
                        onChange={(v) => setAdelantoMonto(v)}
                        className="w-full p-2 border border-yeikar-secondary-light/20 rounded-lg focus:ring-2 focus:ring-yeikar-primary focus:outline-none bg-yeikar-tertiary/20 font-mono text-sm"
                      />
                    )}
                  </div>
                  <SearchSelect
                    value={adelantoMonedaId}
                    onChange={(v) => setAdelantoMonedaId(Number(v))}
                    options={currencies.map((m) => ({
                      value: m.id,
                      label: `${m.nombre} (${m.codigo} ${m.simbolo})`,
                    }))}
                    placeholder="Seleccione moneda..."
                    className="flex-1 min-w-32"
                  />
                  <select
                    value={adelantoMetodo}
                    onChange={(e) => {
                      const valor = e.target.value;
                      setAdelantoMetodo(valor);
                      const meta = metodosPago.find((m) => m.value === valor);
                      if (meta) {
                        const mon = currencies.find((c) => c.codigo === meta.moneda);
                        if (mon) setAdelantoMonedaId(mon.id);
                      }
                    }}
                    className="flex-1 min-w-32 p-2 border border-yeikar-secondary-light/20 rounded-lg focus:ring-2 focus:ring-yeikar-primary focus:outline-none bg-yeikar-tertiary/20 font-mono text-sm"
                  >
                    <option value="">Método de pago</option>
                    {metodosPago.map((m) => (
                      <option key={m.value} value={m.value}>
                        {m.label} · {m.moneda}
                      </option>
                    ))}
                  </select>
                </div>

                {/* Fecha real del abono (a veces el cliente pagó ANTES) */}
                {abonoActivo && (
                  <div className="mt-2">
                    <label className="block text-xs uppercase tracking-wider font-bold text-yeikar-neutral/60 font-headline mb-1">
                      Fecha del abono
                    </label>
                    <input
                      type="date"
                      value={fechaAdelanto}
                      max={hoyVE()}
                      onChange={(e) => setFechaAdelanto(e.target.value)}
                      className="w-full p-2 border border-yeikar-secondary-light/20 rounded-lg focus:ring-2 focus:ring-yeikar-primary focus:outline-none bg-yeikar-tertiary/20 font-mono text-sm"
                    />
                    <p className="mt-1 text-[11px] text-stone-500">
                      Si el cliente abonó antes de este momento, pon la fecha real del pago; vacía = hoy.
                    </p>
                  </div>
                )}

                {/* Tasa SIEMPRE editable cuando la moneda de pago difiere de la cotización.
                    Nunca se deduce de la tasa congelada de la cotización. */}
                {!monedasIguales && (
                  <div className="mt-2">
                    <label className="block text-xs uppercase tracking-wider font-bold text-yeikar-neutral/60 font-headline mb-1">
                      Tasa: {parAdelanto.label}
                    </label>
                    <input
                      type="number"
                      min="0"
                      step="any"
                      value={adelantoTrm}
                      onChange={(e) => setAdelantoTrm(e.target.value)}
                      placeholder={`Ej: ${parAdelanto.placeholder}`}
                      className="w-full p-2 border border-yeikar-secondary-light/20 rounded-lg focus:ring-2 focus:ring-yeikar-primary focus:outline-none bg-yeikar-tertiary/20 font-mono text-sm"
                    />
                    {abonoActivo && !tasaAbonoValida && (
                      <p className="mt-1 text-xs font-semibold text-red-600">
                        Indica la tasa para poder registrar el abono.
                      </p>
                    )}
                    {abonoActivo && tasaAbonoValida && (
                      <p className="mt-1 text-[11px] font-mono text-yeikar-neutral/60">
                        {adelantoModo === 'pct'
                          ? `Abono de ${formatCurrency(Math.round(abonoEnMonedaCotizacion), quoteCod)} equivale a ≈ ${formatCurrency(Math.round(abonoMontoPago), adelantoCod)}`
                          : `Abono de ${formatCurrency(Math.round(abonoMontoPago), adelantoCod)} equivale a ≈ ${formatCurrency(Math.round(abonoEnMonedaCotizacion), quoteCod)}`}
                      </p>
                    )}
                  </div>
                )}

                {abonoActivo && monedasIguales && (
                  <p className="mt-2 text-xs font-mono text-yeikar-neutral/50">
                    Abono en la moneda de la factura: {formatCurrency(Math.round(abonoMontoPago), monedaAdelantoSel?.codigo ?? quoteMoneda?.codigo ?? '')}.
                  </p>
                )}

                {abonoActivo && abonoExcedeTotal && (
                  <p className="mt-2 text-xs font-semibold text-red-600">
                    El abono ({formatCurrency(Math.round(abonoEnMonedaCotizacion), quoteMoneda?.codigo ?? 'COP')}) excede el total del pedido ({formatCurrency(Math.round(quoteTotal), quoteMoneda?.codigo ?? 'COP')}).
                  </p>
                )}
              </div>

              {convertError && (
                <p className="text-xs text-red-600 bg-red-50 border border-red-200 rounded-lg px-3 py-2">
                  {convertError}
                </p>
              )}

              {/* Resumen antes de confirmar */}
              <div className="bg-yeikar-tertiary/30 border border-yeikar-secondary-light/10 rounded-lg px-3 py-2 text-xs font-mono text-yeikar-secondary">
                {abonoActivo ? (
                  <>
                    Abono inicial:{' '}
                    {adelantoModo === 'pct'
                      ? `${pctAbono}%`
                      : `${formatCurrency(Math.round(abonoMontoPago), monedaAdelantoSel?.codigo ?? '')} ${monedaAdelantoSel?.codigo ?? ''}`}{' '}
                    = {formatCurrency(Math.round(abonoEnMonedaCotizacion), quoteMoneda?.codigo ?? '')}
                    {!monedasIguales && tasaAbonoValida
                      ? ` · 1 ${parAdelanto.baseCod} = ${tasaHumanaAbono.toLocaleString('es-ES')} ${parAdelanto.quoteCod}`
                      : ''}
                    {adelantoMetodo ? ` · ${labelMetodoPago(metodosPago, adelantoMetodo)}` : ''} — se registra como primer pago.
                  </>
                ) : (
                  'Sin abono inicial.'
                )}
              </div>

              <div className="flex items-center justify-end gap-3 pt-4 border-t border-yeikar-secondary-light/10">
                <button
                  onClick={() => setIsConvertOpen(false)}
                  className="px-4 py-2 border border-yeikar-secondary-light/20 hover:bg-yeikar-tertiary/20 rounded-lg text-sm font-headline"
                >
                  Cancelar
                </button>
                <button
                  onClick={handleConvertQuote}
                  disabled={isConverting}
                  className="px-5 py-2 bg-yeikar-primary text-yeikar-neutral font-bold rounded-lg shadow-md hover:bg-yeikar-primary-light disabled:opacity-50 disabled:cursor-not-allowed transition-all text-sm font-headline"
                >
                  {isConverting ? 'Convirtiendo...' : 'Confirmar Conversión'}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Print Config & Interactive Preview Modal */}
      {isPrintModalOpen && selectedQuoteForPrint && (() => {
        const subTotal    = Number(selectedQuoteForPrint.total_estimado) || 0;
        const discountVal = subTotal * (Number(printDiscount || 0) / 100);
        const netSubTotal = subTotal - discountVal;
        const ivaVal      = netSubTotal * (Number(printIva || 0) / 100);
        const grandTotal  = netSubTotal + ivaVal;

        return (
          <div className="fixed inset-0 bg-yeikar-neutral/60 backdrop-blur-sm flex items-center justify-center p-4 z-50 overflow-hidden">
            <div className="bg-white rounded-2xl border border-yeikar-secondary-light/10 shadow-2xl w-full max-w-6xl h-[92vh] flex flex-col overflow-hidden">

              {/* Modal Header */}
              <div className="bg-yeikar-neutral px-5 py-3.5 flex items-center justify-between shrink-0">
                <div>
                  <h3 className="font-headline font-bold text-base text-yeikar-primary leading-tight">
                    Cotización #{selectedQuoteForPrint.id.toString().padStart(5, '0')} — Vista Previa
                  </h3>
                  <p className="text-yeikar-tertiary/50 text-xs font-mono mt-0.5">
                    {selectedQuoteForPrint.cliente?.nombre}
                  </p>
                </div>
                <button
                  onClick={() => setIsPrintModalOpen(false)}
                  className="text-yeikar-tertiary/60 hover:text-yeikar-primary text-sm font-bold font-headline transition-colors"
                >
                   × Cerrar
                </button>
              </div>

              {/* Body */}
              <div className="flex-1 flex flex-col md:flex-row overflow-hidden">

                {/* ─── Left: Config Panel ─── */}
                <div className="w-full md:w-80 shrink-0 p-5 border-b md:border-b-0 md:border-r border-stone-100 overflow-y-auto space-y-5 bg-white">

                  <section className="space-y-2">
                    <h4 className="text-[10px] uppercase tracking-widest font-bold text-stone-400">Tasas & Ajustes</h4>
                    <div className="grid grid-cols-2 gap-2">
                      {[
                        { label: 'Descuento %',  val: printDiscount,     set: setPrintDiscount     },
                        { label: 'IVA %',         val: printIva,          set: setPrintIva          },
                      ].map(({ label, val, set }) => (
                        <div key={label}>
                          <label className="block text-[10px] uppercase font-bold text-stone-400 mb-1">{label}</label>
                          <input type="number" min="0" value={val} onChange={e => set(e.target.value)}
                            className="w-full p-2 border border-stone-200 rounded-lg text-xs font-mono focus:ring-1 focus:ring-amber-500 outline-none" />
                        </div>
                      ))}
                    </div>
                  </section>

                  <hr className="border-stone-100" />

                  <section className="space-y-2">
                    <h4 className="text-[10px] uppercase tracking-widest font-bold text-stone-400">Emisor (Yeikar)</h4>
                    <div>
                      <label className="block text-[10px] uppercase font-bold text-stone-400 mb-1">RIF</label>
                      <input type="text" value={printCompanyRif} onChange={e => setPrintCompanyRif(e.target.value)}
                        className="w-full p-2 border border-stone-200 rounded-lg text-xs focus:ring-1 focus:ring-amber-500 outline-none" />
                    </div>
                    <div>
                      <label className="block text-[10px] uppercase font-bold text-stone-400 mb-1">Dirección</label>
                      <textarea rows={2} value={printCompanyAddress} onChange={e => setPrintCompanyAddress(e.target.value)}
                        className="w-full p-2 border border-stone-200 rounded-lg text-xs focus:ring-1 focus:ring-amber-500 outline-none resize-none" />
                    </div>
                    <div>
                      <label className="block text-[10px] uppercase font-bold text-stone-400 mb-1">Teléfono</label>
                      <input type="text" value={printCompanyPhone} onChange={e => setPrintCompanyPhone(e.target.value)}
                        className="w-full p-2 border border-stone-200 rounded-lg text-xs focus:ring-1 focus:ring-amber-500 outline-none" />
                    </div>
                  </section>

                  <button
                    type="button"
                    onClick={handleGeneratePdf}
                    disabled={isGeneratingPdf}
                    className="w-full bg-stone-900 text-amber-400 font-bold py-3 rounded-xl shadow-md hover:bg-stone-800 transition-all flex items-center justify-center gap-2 font-headline disabled:opacity-50 text-sm border-t-2 border-amber-500"
                  >
                    {isGeneratingPdf ? (
                      <span className="animate-pulse">Generando PDF…</span>
                    ) : (
                      <>
                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                        </svg>
                        Descargar PDF
                      </>
                    )}
                  </button>
                </div>

                {/* ─── Right: Live Preview ─── */}
                <div className="flex-1 overflow-y-auto bg-stone-100 p-8">
                  {/*
                    IMPORTANT: min-h-[279.4mm] NOT h-[279.4mm]
                    The container grows with content — no stretching.
                    For PDFs larger than one page the canvas-slicing
                    function handles the split automatically.
                  */}
                                    <DocumentoCotizacion
                    containerId="pdf-preview-container"
                    cotizacion={{
                      id: selectedQuoteForPrint.id,
                      fecha: selectedQuoteForPrint.fecha,
                      moneda_codigo: selectedQuoteForPrint.moneda?.codigo,
                      tasa_cambio: selectedQuoteForPrint.tasa_cambio,
                      total_estimado: selectedQuoteForPrint.total_estimado,
                      cliente: selectedQuoteForPrint.cliente,
                      detalles: selectedQuoteForPrint.detalles?.map((d) => {
                        // INSUMO: el nombre sale del material, no del catálogo
                        // de productos (producto_id es null en esos renglones).
                        const prod = products.find((p) => p.id === d.producto_id);
                        const mat = d.tipo_item === 'INSUMO'
                          ? materiales.find((m) => m.id === d.material_id)
                          : null;
                        return {
                          ...d,
                          // Sin producto ni insumo (importación histórica): la
                          // descripción ES el nombre — fusionados en un solo campo.
                          producto_nombre: (d.tipo_item === 'REPARACION' || d.tipo_item === 'SERVICIO')
                          ? (d.descripcion_especifica || d.observaciones || (d.tipo_item === 'REPARACION' ? 'Reparación' : 'Servicio'))
                          : (prod?.nombre ?? mat?.nombre ?? d.observaciones ?? 'Ítem a medida'),
                          // Unidad vendida del insumo + equivalencia en la
                          // unidad del inventario (para la columna Cant.).
                          unidad_captura: d.unidad_captura ?? null,
                          cantidad_base: d.cantidad_base ?? null,
                          unidad_medida: mat?.unidad_medida?.abreviatura
                            ?? d.material?.unidad_medida?.abreviatura
                            ?? null,
                          // Fotos del producto en orden de subida (la primera
                          // es la portada); el documento muestra hasta 2.
                          fotos: (prod?.fotos ?? []).map((f) => f.url).filter((u): u is string => !!u),
                        };
                      }) ?? [],
                    }}
                    rif={printCompanyRif}
                    direccion={printCompanyAddress}
                    telefono={printCompanyPhone}
                    descuentoPct={Number(printDiscount || 0)}
                    ivaPct={Number(printIva || 0)}
                    venta={associatedVenta as any}
                  />
                </div>{/* end right panel */}
              </div>{/* end body */}
            </div>
          </div>
        );
      })()}

      {/* ═══════════════════════════════════════════════════════════ */}
      {/* Modal de Personalización de Receta Ad-Hoc */}
      {/* ═══════════════════════════════════════════════════════════ */}
      {showPersonalizarModal && personalizarIndex !== null && (
        <div className="fixed inset-0 bg-yeikar-neutral/60 backdrop-blur-sm flex items-center justify-center p-4 z-50 overflow-y-auto">
          <div className="bg-white rounded-2xl shadow-2xl border border-yeikar-secondary-light/10 max-w-4xl w-full h-[90vh] flex flex-col overflow-hidden animate-fade-in">
            {/* Header del Modal */}
            <div className="bg-yeikar-neutral p-4 text-yeikar-tertiary flex flex-col md:flex-row md:items-center justify-between shrink-0 gap-3 border-b border-yeikar-secondary/20">
              <div>
                <h3 className="font-headline font-bold text-base text-yeikar-primary flex items-center gap-2">
                  <span>Personalizar Estructura y Secciones del Mueble</span>
                  {modalPreviewLoading && (
                    <span className="text-[10px] text-amber-400 font-mono animate-pulse">
                      (Calculando nuevo precio...)
                    </span>
                  )}
                </h3>
                <p className="text-xs text-yeikar-tertiary/50">
                  Esta configuración se aplicará únicamente a este renglón de la cotización actual.
                </p>
              </div>

              {/* Banner de Precio en Tiempo Real */}
              <div className="flex items-center gap-4 bg-yeikar-secondary/40 px-3.5 py-1.5 rounded-xl border border-yeikar-secondary-light/15 shrink-0">
                <div className="text-right">
                  <span className="text-[9px] uppercase tracking-wider text-yeikar-tertiary/60 font-bold block">
                    Costo Fábrica
                  </span>
                  <span className="font-mono text-xs font-bold text-yeikar-tertiary">
                    ${modalPreviewCalc ? Number(modalPreviewCalc.costo_total).toLocaleString('es-CO', { maximumFractionDigits: 0 }) : '...'}
                  </span>
                </div>
                <div className="h-6 w-px bg-yeikar-secondary-light/20" />
                <div className="text-right">
                  <span className="text-[9px] uppercase tracking-wider text-amber-400 font-bold block">
                    Nuevo Precio Sugerido
                  </span>
                  <span className="font-mono text-base font-black text-yeikar-primary">
                    ${modalPreviewCalc ? Number(modalPreviewCalc.precio_venta).toLocaleString('es-CO', { maximumFractionDigits: 0 }) : '...'}
                  </span>
                </div>
              </div>

              <button
                onClick={() => { setShowPersonalizarModal(false); setPersonalizarIndex(null); setModalPreviewCalc(null); setVerEstructuraModal(false); }}
                className="text-yeikar-tertiary/60 hover:text-yeikar-primary text-sm font-bold font-headline self-start md:self-auto"
              >
                 × Cerrar
              </button>
            </div>

            {/* Cuerpo del Modal */}
            <div className="flex-1 overflow-y-auto p-6 space-y-6">
              <div className="flex justify-end">
                <button
                  onClick={() => setVerEstructuraModal((v) => !v)}
                  className="text-xs font-bold text-yeikar-primary hover:text-yeikar-secondary uppercase tracking-wider"
                >
                  {verEstructuraModal ? '▲ Ocultar estructura' : '▼ Ver estructura de costos (Excel)'}
                </button>
              </div>
              {verEstructuraModal && modalPreviewCalc && (
                <EstructuraCostos data={normalizarEstructuraCostos(modalPreviewCalc)} />
              )}
              {personalizarSecciones && personalizarSecciones.length > 0 ? (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                  {personalizarSecciones.map((sec, secIdx) => {
                    const secInfo = modalPreviewCalc?.desglose_por_seccion?.[sec.nombre];
                    return (
                      <div key={sec.id || secIdx} className="border border-yeikar-secondary-light/10 rounded-xl overflow-hidden bg-white shadow-sm flex flex-col">
                        {/* Cabecera Sección */}
                        <div className="bg-yeikar-secondary/5 border-b border-yeikar-secondary-light/10 px-4 py-2.5 flex items-center justify-between">
                          <span className="font-headline font-black text-xs text-yeikar-secondary uppercase tracking-wider">
                            Sección: {sec.nombre}
                          </span>
                          <div className="flex items-center gap-2">
                            {secInfo && (
                              <span className="text-[10px] font-bold font-mono bg-green-50 text-green-700 border border-green-200/80 px-2 py-0.5 rounded-full">
                                Subtotal: ${Number(secInfo.total_seccion).toLocaleString('es-CO', { maximumFractionDigits: 0 })}
                              </span>
                            )}
                            <span className="text-[10px] font-bold font-mono bg-yeikar-secondary/10 text-yeikar-secondary px-2 py-0.5 rounded-full">
                              {sec.elementos?.length || 0} insumos
                            </span>
                          </div>
                        </div>

                        {/* Política de la Sección */}
                        <div className="bg-amber-50/50 border-b border-amber-100/50 px-4 py-3 space-y-2">
                          <div className="flex items-center justify-between">
                            <span className="text-[10px] font-bold text-amber-800 uppercase tracking-wider">Política de Sección</span>
                          </div>
                          <div className="grid grid-cols-2 gap-3">
                            <div>
                              <label className="block text-[9px] font-bold text-yeikar-neutral/50 mb-1">% GASTOS SECCIÓN</label>
                              <input
                                type="number"
                                step="0.1"
                                min="0"
                                value={sec.politica?.pct_gastos_seccion ?? 10}
                                onChange={(e) => handleUpdateSeccionPolitica(secIdx, 'pct_gastos_seccion', e.target.value)}
                                className="w-full p-1.5 border border-amber-200 bg-white rounded-lg text-xs font-mono"
                              />
                            </div>
                            <div>
                              <label className="block text-[9px] font-bold text-yeikar-neutral/50 mb-1">% TRABAJADORES</label>
                              <input
                                type="number"
                                step="0.1"
                                min="0"
                                value={sec.politica?.pct_trabajadores ?? 8}
                                onChange={(e) => handleUpdateSeccionPolitica(secIdx, 'pct_trabajadores', e.target.value)}
                                className="w-full p-1.5 border border-amber-200 bg-white rounded-lg text-xs font-mono"
                              />
                            </div>
                          </div>
                        </div>

                        {/* Costos de Producción Avanzados (Pintura, etc.) */}
                        <div className="border-b border-stone-100 px-4 py-3 space-y-2">
                          <div className="flex items-center justify-between">
                            <span className="text-[10px] font-bold text-yeikar-neutral/40 uppercase tracking-wider">Costos de Producción</span>
                            <button
                              type="button"
                              onClick={() => handleOpenAddCost(secIdx)}
                              className="text-[10px] font-bold text-yeikar-primary hover:underline flex items-center gap-1"
                            >
                              + Agregar Costo
                            </button>
                          </div>

                          {sec.costos_produccion && sec.costos_produccion.length > 0 ? (
                            <div className="divide-y divide-amber-100">
                              {sec.costos_produccion.map((cp: any, cpIdx: number) => (
                                <div key={cp.id || cpIdx} className="flex items-center justify-between text-[11px] py-1.5 hover:bg-amber-50/30 px-1 -mx-1 rounded">
                                  <span className="font-semibold text-amber-900">{cp.nombre}</span>
                                  <div className="flex items-center gap-2">
                                    <span className="font-mono text-amber-800 bg-amber-100/60 px-1.5 py-0.5 rounded text-[10px]">
                                      ${Number(cp.costo_base).toLocaleString('es-CO', { maximumFractionDigits: 2 })} {cp.porcentaje ? `(+${cp.porcentaje}%)` : ''}
                                    </span>
                                    <button
                                      type="button"
                                      onClick={() => handleRemoveCost(secIdx, cpIdx)}
                                      className="text-red-500 hover:text-red-700"
                                    >
                                      ×
                                    </button>
                                  </div>
                                </div>
                              ))}
                            </div>
                          ) : (
                            <p className="text-[10px] text-yeikar-neutral/40 italic">Sin costos de producción.</p>
                          )}
                        </div>

                        {/* Insumos */}
                        <div className="p-4 flex-1 space-y-3">
                          <div className="flex items-center justify-between">
                            <span className="text-[10px] font-bold text-yeikar-neutral/40 uppercase tracking-wider">Insumos Físicos</span>
                            <button
                              type="button"
                              onClick={() => handleOpenAddMaterial(secIdx)}
                              className="text-[10px] font-bold text-yeikar-primary hover:underline"
                            >
                              + Agregar Insumo
                            </button>
                          </div>

                          {sec.elementos && sec.elementos.length > 0 ? (
                            <div className="space-y-2.5 max-h-[220px] overflow-y-auto pr-1">
                              {sec.elementos.map((el: any, elIdx: number) => (
                                <div key={el.id || elIdx} className="bg-stone-50 p-2.5 rounded-lg border border-stone-100 relative space-y-1">
                                  <button
                                    type="button"
                                    onClick={() => handleRemoveInsumo(secIdx, elIdx)}
                                    className="absolute top-1 right-2 text-stone-400 hover:text-red-700 text-xs"
                                    title="Quitar"
                                  >
                                    ×
                                  </button>
                                  <div className="font-bold text-xs text-yeikar-secondary truncate pr-4">
                                    {el.nombre_insumo_original}
                                  </div>
                                  <div className="grid grid-cols-2 gap-2 pt-1">
                                    <div>
                                      <label className="block text-[8px] font-semibold text-stone-400 mb-0.5">CANTIDAD ({el.unidad_medida})</label>
                                      <input
                                        type="number"
                                        step="0.001"
                                        min="0"
                                        value={el.cantidad}
                                        onChange={(e) => handleUpdateInsumoField(secIdx, elIdx, 'cantidad', e.target.value)}
                                        className="w-full p-1 border border-stone-200 bg-white rounded text-xs font-mono"
                                      />
                                    </div>
                                    <div>
                                      <label className="block text-[8px] font-semibold text-stone-400 mb-0.5">PRECIO UNITARIO ($)</label>
                                      <MontoInput
                                        min="0"
                                        value={el.precio_unitario ?? ''}
                                        onChange={(v) => handleUpdateInsumoField(secIdx, elIdx, 'precio_unitario', v)}
                                        className="w-full p-1 border border-stone-200 bg-white rounded text-xs font-mono"
                                      />
                                    </div>
                                  </div>
                                </div>
                              ))}
                            </div>
                          ) : (
                            <p className="text-[10px] text-yeikar-neutral/40 italic">No hay insumos agregados.</p>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>
              ) : (
                <div className="flex flex-col items-center justify-center py-12 text-yeikar-neutral/45">
                  <svg className="w-12 h-12 mb-3 animate-spin text-yeikar-primary" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M4 12a8 8 0 018-8v8H4z" />
                  </svg>
                  <span>Cargando receta estructurada...</span>
                </div>
              )}
            </div>

            {/* Footer del Modal */}
            <div className="bg-yeikar-neutral/5 p-4 border-t border-yeikar-secondary-light/10 flex items-center justify-between shrink-0">
              <div className="text-xs">
                {modalPreviewCalc ? (
                  <div className="flex items-center gap-2">
                    <span className="text-yeikar-secondary font-headline font-bold">
                      Precio Nuevo Sugerido:
                    </span>
                    <span className="text-yeikar-primary text-base font-black font-mono">
                      ${Number(modalPreviewCalc.precio_venta).toLocaleString('es-CO', { maximumFractionDigits: 0 })}
                    </span>
                  </div>
                ) : (
                  <span className="text-yeikar-tertiary/50 italic text-[11px]">Calculando precio en tiempo real...</span>
                )}
              </div>
              <div className="flex items-center gap-3">
                <button
                  type="button"
                  onClick={() => { setShowPersonalizarModal(false); setPersonalizarIndex(null); setModalPreviewCalc(null); }}
                  className="px-4 py-2 border border-yeikar-secondary-light/15 hover:bg-stone-50 rounded-xl text-xs font-bold font-headline"
                >
                  Cancelar
                </button>
                <button
                  type="button"
                  onClick={handleSavePersonalizacion}
                  disabled={modalPreviewLoading}
                  className="px-5 py-2 bg-yeikar-primary text-yeikar-neutral font-bold rounded-xl shadow-md hover:bg-yeikar-primary-light transition-all text-xs font-headline flex items-center gap-2 disabled:opacity-50"
                >
                  <span>Guardar Personalización</span>
                  {modalPreviewCalc && (
                    <span className="bg-yeikar-neutral/20 text-yeikar-neutral font-mono text-[10px] px-1.5 py-0.5 rounded">
                      ${Number(modalPreviewCalc.precio_venta).toLocaleString('es-CO', { maximumFractionDigits: 0 })}
                    </span>
                  )}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ═══════════════════════════════════════════════════════════ */}
      {/* Modal / Buscador para Agregar Insumo */}
      {/* ═══════════════════════════════════════════════════════════ */}
      {showAddMaterialDropdown && addMaterialSeccionIndex !== null && (
        <div className="fixed inset-0 bg-yeikar-secondary/60 backdrop-blur-sm flex items-center justify-center p-4 z-[60]">
          <div className="bg-white rounded-2xl shadow-2xl border border-stone-200 max-w-md w-full p-4 sm:p-6 space-y-4">
            <div className="flex items-center justify-between">
              <h4 className="font-headline font-bold text-sm text-yeikar-secondary">Buscar Material en Inventario</h4>
              <button
                type="button"
                onClick={() => { setShowAddMaterialDropdown(false); setAddMaterialSeccionIndex(null); }}
                className="text-stone-400 hover:text-stone-600 font-bold"
              >
                ×
              </button>
            </div>
            <input
              type="text"
              placeholder="Buscar madera, tela, tornillos..."
              value={addMaterialSearch}
              onChange={(e) => setAddMaterialSearch(e.target.value)}
              className="w-full p-2 border border-stone-200 rounded-lg focus:ring-2 focus:ring-yeikar-primary text-xs"
              autoFocus
            />
            <div className="max-h-[220px] overflow-y-auto divide-y divide-stone-100 pr-1 text-xs">
              {addMaterialCargando && (
                <div className="flex items-center gap-2 p-2.5 text-stone-400">
                  <Loader2 className="h-3.5 w-3.5 animate-spin" /> Buscando…
                </div>
              )}
              {!addMaterialCargando &&
                addMaterialResultados.map((m) => (
                  <button
                    key={m.id}
                    type="button"
                    onClick={() => handleAddMaterialToSeccion(m)}
                    className="w-full text-left p-2.5 hover:bg-yeikar-tertiary/20 rounded transition-colors flex justify-between items-center"
                  >
                    <span className="font-semibold text-stone-900">{m.nombre}</span>
                    <span className="font-mono text-stone-500 bg-stone-100 px-2 py-0.5 rounded text-[10px]">
                      ${Number(m.costo_base).toLocaleString('es-CO', { maximumFractionDigits: 2 })}
                    </span>
                  </button>
                ))}
              {!addMaterialCargando && addMaterialResultados.length === 0 && (
                <div className="p-2.5 text-center text-stone-400">Sin resultados</div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* ═══════════════════════════════════════════════════════════ */}
      {/* Modal Agregar Costo de Producción */}
      {/* ═══════════════════════════════════════════════════════════ */}
      {showAddCostModal && addCostSeccionIndex !== null && (
        <div className="fixed inset-0 bg-yeikar-secondary/60 backdrop-blur-sm flex items-center justify-center p-4 z-[60]">
          <div className="bg-white rounded-2xl shadow-2xl border border-stone-200 max-w-sm w-full p-4 sm:p-6 space-y-4">
            <div>
              <h4 className="font-headline font-bold text-sm text-yeikar-secondary">Agregar Costo de Producción</h4>
            </div>
            <form onSubmit={handleAddCostToSeccion} className="space-y-3 text-xs">
              <div>
                <label className="block font-bold text-stone-500 mb-1">Nombre del Costo *</label>
                <input
                  type="text"
                  required
                  placeholder="Ej: PREPARADO, PINTURA"
                  value={addCostForm.nombre}
                  onChange={(e) => setAddCostForm({ ...addCostForm, nombre: e.target.value })}
                  className="w-full p-2 border border-stone-200 rounded-lg text-xs"
                />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block font-bold text-stone-500 mb-1">Costo Base ($) *</label>
                  <MontoInput
                    min="0"
                    required
                    placeholder="0.00"
                    value={addCostForm.costo_base}
                    onChange={(v) => setAddCostForm({ ...addCostForm, costo_base: v })}
                    className="w-full p-2 border border-stone-200 rounded-lg text-xs font-mono"
                  />
                </div>
                <div>
                  <label className="block font-bold text-stone-500 mb-1">% Incremental (Opcional)</label>
                  <input
                    type="number"
                    min="0"
                    placeholder="5"
                    value={addCostForm.porcentaje}
                    onChange={(e) => setAddCostForm({ ...addCostForm, porcentaje: e.target.value })}
                    className="w-full p-2 border border-stone-200 rounded-lg text-xs font-mono"
                  />
                </div>
              </div>
              <div className="flex justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => { setShowAddCostModal(false); setAddCostSeccionIndex(null); }}
                  className="px-4 py-2 hover:bg-stone-50 rounded-lg"
                >
                  Cancelar
                </button>
                <button
                  type="submit"
                  className="px-4 py-2 bg-yeikar-primary text-yeikar-neutral font-bold rounded-lg"
                >
                  Agregar Costo
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* ═══════════════════════════════════════════════════════════ */}
      {/* Modal Selector de Productos / Catálogo Interactivo */}
      {/* ═══════════════════════════════════════════════════════════ */}
      <ProductSelectorModal
        open={isProductSelectorOpen}
        onClose={() => {
          setIsProductSelectorOpen(false);
          setProductSelectorTargetIndex(null);
        }}
        products={products}
        modo={productSelectorModo}
        selectedProductId={
          productSelectorTargetIndex !== null && items[productSelectorTargetIndex]
            ? items[productSelectorTargetIndex].producto_id
            : null
        }
        onSelectProduct={handleSelectProductFromModal}
        onSelectPersonalizado={handleSelectPersonalizado}
        currencyCode={currencyCode}
        tasaCambio={tasaCambio}
        selectedMonedaId={selectedMonedaId}
        productosEnRetrabajo={useMemo(() => new Set(piezasEnRetrabajo), [piezasEnRetrabajo])}
        title={
          productSelectorTargetIndex !== null
            ? productSelectorModo === 'reventa'
              ? `Seleccionar Producto de Reventa para Renglón ${productSelectorTargetIndex + 1}`
              : `Seleccionar Mueble para Renglón ${productSelectorTargetIndex + 1}`
            : productSelectorModo === 'reventa'
            ? 'Catálogo de Productos de Reventa'
            : productSelectorModo === 'exhibicion'
            ? 'Catálogo de Piezas de Exhibición'
            : 'Catálogo de Modelos y Muebles'
        }
      />

      {/* Modal Producto Nuevo (crear desde la cotización) */}
      {showNuevoProductoModal && (
        <div className="fixed inset-0 bg-yeikar-secondary/60 backdrop-blur-sm z-[60] flex items-center justify-center p-4">
          <div className="bg-white rounded-3xl shadow-xl max-w-md w-full max-h-[90vh] flex flex-col overflow-hidden border border-yeikar-secondary-light/10">
            <div className="bg-gradient-to-r from-yeikar-secondary to-yeikar-secondary-light text-white px-6 py-5 shrink-0">
              <h3 className="font-headline font-black text-lg">Producto Nuevo</h3>
              <p className="text-xs text-white/70">Se crea en el catálogo y se agrega al renglón. Puedes cotizarlo hoy con su precio; la estructura de costos se completa después.</p>
            </div>
            <form onSubmit={handleCrearProductoDesdeCotizacion} className="p-6 space-y-4 font-body overflow-y-auto">
              <div>
                <label className="block text-xs font-bold text-yeikar-secondary mb-1">Nombre del producto *</label>
                <input type="text" required placeholder="Ej. MESA DE COMEDOR 6 PUESTOS" value={npForm.nombre} onChange={(e) => setNpForm((f) => ({ ...f, nombre: e.target.value }))} className="w-full bg-yeikar-tertiary/20 border border-yeikar-secondary-light/10 rounded-xl px-4 py-2.5 text-sm text-yeikar-neutral focus:outline-none focus:border-yeikar-primary uppercase" />
              </div>
              <div>
                <label className="block text-xs font-bold text-yeikar-secondary mb-1">Clasificación *</label>
                <SearchSelect
                  value={npForm.tipo_producto_id}
                  onChange={(v) => setNpForm((f) => ({ ...f, tipo_producto_id: String(v) }))}
                  options={tiposProducto.map((t) => ({ value: t.id, label: etiquetaClasificacion(t.nombre) }))}
                  placeholder="Seleccionar clasificación..."
                />
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs font-bold text-yeikar-secondary mb-1">Precio estimado de venta *</label>
                  <MontoInput min="0" required placeholder="Ej. 950000" value={npForm.precio} onChange={(v) => setNpForm((f) => ({ ...f, precio: v }))} className="w-full bg-yeikar-tertiary/20 border border-yeikar-secondary-light/10 rounded-xl px-4 py-2.5 text-sm text-yeikar-neutral focus:outline-none focus:border-yeikar-primary font-mono" />
                </div>
                <div>
                  <label className="block text-xs font-bold text-yeikar-secondary mb-1">Moneda del precio</label>
                  <SearchSelect
                    value={npForm.moneda_id}
                    onChange={(v) => setNpForm((f) => ({ ...f, moneda_id: String(v) }))}
                    options={currencies.map((c) => ({ value: c.id, label: c.codigo }))}
                    placeholder="Moneda..."
                  />
                </div>
              </div>
              <p className="text-[11px] text-yeikar-neutral/50">
                El cotizador detecta la moneda sola: si no es COP, te pedirá la tasa del día al guardar.
              </p>
              <div>
                <label className="block text-xs font-bold text-yeikar-secondary mb-1">Fotos de referencia <span className="text-yeikar-neutral/40 font-normal">(opcional · se comprime sola)</span></label>
                {fotosNp.length > 0 && (
                  <div className="flex flex-wrap items-center gap-2.5 mb-2">
                    {fotosNp.map((f, i) => (
                      <div key={i} className="relative group">
                        <img
                          src={f.url}
                          alt={`Vista previa ${i + 1}`}
                          className={`w-16 h-16 rounded-lg object-cover border ${i === 0 ? 'border-yeikar-primary/60' : 'border-yeikar-secondary-light/15'}`}
                        />
                        {i === 0 && (
                          <span className="absolute -top-1.5 -left-1.5 bg-yeikar-primary text-yeikar-neutral text-[8px] font-black px-1.5 py-0.5 rounded-full shadow">
                            Principal
                          </span>
                        )}
                        <button
                          type="button"
                          title="Quitar foto"
                          onClick={() => quitarNpFoto(i)}
                          className="absolute -top-1.5 -right-1.5 bg-red-500 text-white rounded-full w-5 h-5 flex items-center justify-center text-[10px] opacity-0 group-hover:opacity-100 transition-opacity"
                        >
                          ×
                        </button>
                      </div>
                    ))}
                  </div>
                )}
                <div className="flex items-center gap-3">
                  <div className="flex flex-col gap-2 flex-1">
                    <button
                      type="button"
                      onClick={() => npCameraRef.current?.click()}
                      className="py-2 bg-yeikar-tertiary hover:bg-yeikar-secondary-light/15 text-yeikar-secondary rounded-xl font-bold text-xs transition-colors"
                    >
                      Tomar foto
                    </button>
                    <button
                      type="button"
                      onClick={() => npGalleryRef.current?.click()}
                      className="py-2 bg-yeikar-tertiary hover:bg-yeikar-secondary-light/15 text-yeikar-secondary rounded-xl font-bold text-xs transition-colors"
                    >
                      Desde galería
                    </button>
                  </div>
                  <input ref={npCameraRef} type="file" accept="image/*" capture="environment" className="hidden" onChange={handleNpFoto} />
                  <input ref={npGalleryRef} type="file" accept="image/*" multiple className="hidden" onChange={handleNpFoto} />
                </div>
                <p className="text-[10px] text-yeikar-neutral/40 mt-1">
                  Puedes subir varias: la primera es la principal y sale en la cotización; las demás se ven como vistas adicionales en la Hoja de Trabajo.
                </p>
              </div>
              {errorForm && (
                <p className="text-xs text-red-600 bg-red-50 border border-red-200 rounded-xl px-3 py-2" role="alert">{errorForm}</p>
              )}
              <div className="flex gap-3 pt-3 border-t border-yeikar-secondary-light/5">
                <button type="button" onClick={() => setShowNuevoProductoModal(false)} className="flex-1 py-2.5 bg-yeikar-tertiary hover:bg-yeikar-secondary-light/15 text-yeikar-secondary rounded-xl font-bold font-headline text-sm transition-colors">Cancelar</button>
                <button type="submit" disabled={savingNp} className="flex-1 py-2.5 bg-yeikar-primary hover:bg-yeikar-primary-dark text-yeikar-neutral rounded-xl font-bold font-headline text-sm transition-all disabled:opacity-50">{savingNp ? 'Creando...' : 'Crear y agregar'}</button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Modal Cliente Nuevo (alta completa desde la cotización, mismos campos que Clientes) */}
      {showNuevoClienteModal && (
        <div className="fixed inset-0 bg-yeikar-secondary/60 backdrop-blur-sm z-[60] flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl shadow-xl max-w-lg w-full overflow-hidden border border-yeikar-secondary-light/10 max-h-[90vh] flex flex-col">
            <div className="bg-yeikar-secondary text-white px-5 py-4">
              <h3 className="font-headline font-black text-base">Nuevo Cliente</h3>
              <p className="text-xs text-white/60 mt-0.5">Los mismos datos que el módulo Clientes</p>
            </div>
            <form onSubmit={handleCrearClienteDesdeCotizacion} className="p-5 space-y-4 font-body overflow-y-auto">
              <div>
                <label className="block text-xs font-bold text-yeikar-secondary mb-1">Nombre Completo / Razón Social *</label>
                <input
                  type="text"
                  required
                  placeholder="Ej. MARÍA PÉREZ"
                  value={ncForm.nombre}
                  onChange={(e) => setNcForm((f) => ({ ...f, nombre: e.target.value }))}
                  className="w-full bg-yeikar-tertiary/20 border border-yeikar-secondary-light/10 rounded-xl px-4 py-2 text-sm text-yeikar-neutral focus:outline-none focus:border-yeikar-primary uppercase"
                />
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs font-bold text-yeikar-secondary mb-1">Teléfono *</label>
                  <input
                    type="text"
                    required
                    placeholder="Ej. 0412-5555555"
                    value={ncForm.telefono}
                    onChange={(e) => setNcForm((f) => ({ ...f, telefono: e.target.value }))}
                    className="w-full bg-yeikar-tertiary/20 border border-yeikar-secondary-light/10 rounded-xl px-4 py-2 text-sm text-yeikar-neutral focus:outline-none focus:border-yeikar-primary font-mono"
                  />
                </div>
                <div>
                  <label className="block text-xs font-bold text-yeikar-secondary mb-1">
                    Cédula / RIF <span className="text-yeikar-neutral/40 font-normal">opcional</span>
                  </label>
                  <input
                    type="text"
                    value={ncForm.cedula}
                    onChange={(e) => setNcForm((f) => ({ ...f, cedula: e.target.value }))}
                    placeholder="V-12345678"
                    className="w-full bg-yeikar-tertiary/20 border border-yeikar-secondary-light/10 rounded-xl px-4 py-2 text-sm text-yeikar-neutral focus:outline-none focus:border-yeikar-primary font-mono"
                  />
                </div>
              </div>
              <div>
                <label className="block text-xs font-bold text-yeikar-secondary mb-1">
                  Dirección <span className="text-yeikar-neutral/40 font-normal">opcional</span>
                </label>
                <input
                  type="text"
                  value={ncForm.direccion}
                  onChange={(e) => setNcForm((f) => ({ ...f, direccion: e.target.value }))}
                  placeholder="Ej. Av. Principal, local 5"
                  className="w-full bg-yeikar-tertiary/20 border border-yeikar-secondary-light/10 rounded-xl px-4 py-2 text-sm text-yeikar-neutral focus:outline-none focus:border-yeikar-primary"
                />
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs font-bold text-yeikar-secondary mb-1">
                    Ciudad <span className="text-yeikar-neutral/40 font-normal">opcional</span>
                  </label>
                  <input
                    type="text"
                    value={ncForm.ciudad}
                    onChange={(e) => setNcForm((f) => ({ ...f, ciudad: e.target.value }))}
                    placeholder="Ej. Ureña"
                    className="w-full bg-yeikar-tertiary/20 border border-yeikar-secondary-light/10 rounded-xl px-4 py-2 text-sm text-yeikar-neutral focus:outline-none focus:border-yeikar-primary"
                  />
                </div>
                <div>
                  <label className="block text-xs font-bold text-yeikar-secondary mb-1">
                    Estado / Departamento <span className="text-yeikar-neutral/40 font-normal">opcional</span>
                  </label>
                  <input
                    type="text"
                    value={ncForm.estado}
                    onChange={(e) => setNcForm((f) => ({ ...f, estado: e.target.value }))}
                    placeholder="Ej. Táchira"
                    className="w-full bg-yeikar-tertiary/20 border border-yeikar-secondary-light/10 rounded-xl px-4 py-2 text-sm text-yeikar-neutral focus:outline-none focus:border-yeikar-primary"
                  />
                </div>
              </div>
              <div>
                <label className="block text-xs font-bold text-yeikar-secondary mb-1">
                  Observaciones <span className="text-yeikar-neutral/40 font-normal">opcional</span>
                </label>
                <textarea
                  rows={3}
                  value={ncForm.observaciones}
                  onChange={(e) => setNcForm((f) => ({ ...f, observaciones: e.target.value }))}
                  placeholder="Notas adicionales sobre el cliente"
                  className="w-full bg-yeikar-tertiary/20 border border-yeikar-secondary-light/10 rounded-xl px-4 py-2 text-sm text-yeikar-neutral focus:outline-none focus:border-yeikar-primary resize-none"
                />
              </div>
              <p className="text-[11px] text-yeikar-neutral/50">
                Si el teléfono ya existe, se selecciona el cliente actual (no se duplica).
              </p>
              {errorForm && (
                <p className="text-xs text-red-600 bg-red-50 border border-red-200 rounded-xl px-3 py-2" role="alert">{errorForm}</p>
              )}
              <div className="flex gap-3 pt-2 border-t border-yeikar-secondary-light/5">
                <button type="button" onClick={() => setShowNuevoClienteModal(false)} className="flex-1 py-2.5 bg-yeikar-tertiary hover:bg-yeikar-secondary-light/15 text-yeikar-secondary rounded-xl font-bold font-headline text-sm transition-colors">Cancelar</button>
                <button type="submit" disabled={savingNc} className="flex-1 py-2.5 bg-yeikar-primary hover:bg-yeikar-primary-dark text-yeikar-neutral rounded-xl font-bold font-headline text-sm transition-all disabled:opacity-50">{savingNc ? 'Guardando...' : 'Crear y seleccionar'}</button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Modal Definir Precio (producto existente sin precio) */}
      {definirPrecioProd && (
        <div className="fixed inset-0 bg-yeikar-secondary/60 backdrop-blur-sm z-[60] flex items-center justify-center p-4">
          <div className="bg-white rounded-3xl shadow-xl max-w-md w-full overflow-hidden border border-yeikar-secondary-light/10">
            <div className="bg-gradient-to-r from-yeikar-secondary to-yeikar-secondary-light text-white px-6 py-5">
              <h3 className="font-headline font-black text-lg">Definir Precio</h3>
              <p className="text-xs text-white/70">Le pones precio estimado de venta a este producto y el renglón se recalcula.</p>
            </div>
            <form onSubmit={guardarDefinirPrecio} className="p-6 space-y-4 font-body">
              <div className="bg-yeikar-tertiary/10 border border-yeikar-secondary-light/10 rounded-xl px-4 py-3">
                <p className="text-xs text-yeikar-neutral/50">Producto</p>
                <p className="font-headline font-black text-yeikar-secondary text-sm mt-0.5">{definirPrecioProd.nombre}</p>
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs font-bold text-yeikar-secondary mb-1">Precio estimado de venta *</label>
                  <MontoInput min="0" required value={dpPrecio} onChange={(v) => setDpPrecio(v)} className="w-full bg-yeikar-tertiary/20 border border-yeikar-secondary-light/10 rounded-xl px-4 py-2.5 text-sm text-yeikar-neutral focus:outline-none focus:border-yeikar-primary font-mono" />
                </div>
                <div>
                  <label className="block text-xs font-bold text-yeikar-secondary mb-1">Moneda</label>
                  <SearchSelect
                    value={dpMoneda}
                    onChange={(v) => setDpMoneda(String(v))}
                    options={currencies.map((c) => ({ value: c.id, label: c.codigo }))}
                    placeholder="Moneda..."
                  />
                </div>
              </div>
              {errorForm && (
                <p className="text-xs text-red-600 bg-red-50 border border-red-200 rounded-xl px-3 py-2" role="alert">{errorForm}</p>
              )}
              <div className="flex gap-3 pt-3 border-t border-yeikar-secondary-light/5">
                <button type="button" onClick={() => setDefinirPrecioProd(null)} className="flex-1 py-2.5 bg-yeikar-tertiary hover:bg-yeikar-secondary-light/15 text-yeikar-secondary rounded-xl font-bold font-headline text-sm transition-colors">Cancelar</button>
                <button type="submit" disabled={savingDp} className="flex-1 py-2.5 bg-yeikar-primary hover:bg-yeikar-primary-dark text-yeikar-neutral rounded-xl font-bold font-headline text-sm transition-all disabled:opacity-50">{savingDp ? 'Guardando...' : 'Guardar y recalcular'}</button>
              </div>
            </form>
          </div>
        </div>
      )}

      <ConfirmDialog
        open={confirmDeleteId !== null}
        title="Eliminar cotización"
        message="¿Estás seguro de que deseas eliminar esta cotización?"
        confirmLabel="Sí, eliminar"
        danger
        onConfirm={ejecutarDelete}
        onCancel={() => setConfirmDeleteId(null)}
      />
    </div>
  );
}
