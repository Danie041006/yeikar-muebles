import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import axios from 'axios';
import { AlertTriangle, Plus, ReceiptText, Trash2, X } from 'lucide-react';
import { SearchSelect } from '../ui';
import { inventarioService, type CompraInventarioMultipleCreate, type EntradaInventarioDetalle, type CapturaEntrada } from '../../services/inventarioService';
import PagosEntradaEditor from './PagosEntradaEditor';
import EntradaCapturaResumen from './EntradaCapturaResumen';
import EntradaCambiosResumen from './EntradaCambiosResumen';
import {
  productosService,
  type MonedaInfo,
  type TipoProducto,
} from '../../services/productosService';
import { resolverParMonedas } from '../../utils/format';
import { hoyVE } from '../../utils/fechas';

interface CuentaPago {
  key: string;
  cuentaId: number;
  nombre: string;
  monedaId: number;
  codigo: string;
}

interface OpcionCatalogo {
  id: number;
  nombre: string;
  unidad?: string;
  departamento?: string | null;
  monedaId: number;
  costo?: number | null;
}

interface LineaDraft {
  key: string;
  tipo: 'MATERIAL' | 'PRODUCTO';
  modo: 'EXISTENTE' | 'NUEVO';
  itemId: string;
  item: OpcionCatalogo | null;
  nombreNuevo: string;
  codigoNuevo: string;
  unidadId: string;
  departamento: string;
  categoriaId: string;
  tipoProductoId: string;
  monedaId: string;
  precioVenta: string;
  cantidad: string;
  precio: string;
  tasaPrecio: string;
  llevada: string;
  llevadaModo?: 'UNIDAD' | 'TOTAL';
  descuento: string;
  ubicacionId: string;
  cliente: string;
  observaciones: string;
}

interface PagoDraft {
  key: string;
  cuentaKey: string;
  monto: string;
  tasa: string;
  observacion: string;
}

interface CompraDraftStorage {
  version: 2;
  operacionId: string;
  fecha: string;
  proveedor: string;
  recibidoPor: string;
  observaciones: string;
  lineas: LineaDraft[];
  pagos: PagoDraft[];
  errorCompra: string | null;
  codigoError: number | null;
  confirmacionPendiente: boolean;
  payloadPendiente: CompraInventarioMultipleCreate | null;
  motivo?: string;
  correccionId?: string;
  versionCorreccion?: number;
}

interface ErrorCompra {
  mensaje: string;
  codigo: number | null;
  confirmacionPendiente: boolean;
}

interface Props {
  open: boolean;
  userId: number | null;
  onClose: () => void;
  onCreated: (result: Awaited<ReturnType<typeof inventarioService.crearCompraMultiple>>) => void;
  unidades: { id: number; nombre: string; abreviatura: string }[];
  monedas: MonedaInfo[];
  ubicaciones: { id: number; nombre: string }[];
  cuentas: CuentaPago[];
  categoriasMaterial: { id: number; nombre: string }[];
  categoriasProducto: { id: number; nombre: string }[];
  tiposProducto: TipoProducto[];
  entrada?: EntradaInventarioDetalle;
}

const DEPARTAMENTOS = [
  ['EBANISTERIA', 'Ebanistería'],
  ['PREPARACION', 'Preparación'],
  ['PINTURA', 'Pintura'],
  ['TAPICERIA', 'Tapicería'],
  ['VIDRIERIA', 'Vidriería'],
  ['TERMINACION', 'Terminación'],
  ['OFICINA', 'Oficina'],
] as const;

const CLAVE_BORRADOR = 'yeikar:inventario:compra-multiple:v1';
const ETIQUETAS_ERROR: Record<string, string> = {
  tipo_item: 'Tipo de artículo', material_id: 'Material', producto_id: 'Producto',
  nuevo_material: 'Material nuevo', nuevo_producto: 'Producto nuevo', cantidad: 'Cantidad',
  precio_unitario: 'Precio unitario', moneda_precio_id: 'Moneda del precio',
  tasa_precio_a_cop: 'Tasa del precio', llevada_unitaria: 'Llevada por unidad',
  descuento_porcentaje: 'Descuento', departamento: 'Departamento', ubicacion_id: 'Ubicación',
  unidad_medida_id: 'Unidad de medida', tipo_producto_id: 'Tipo de producto', moneda_id: 'Moneda del producto',
  categoria_inventario_id: 'Categoría', codigo: 'Código', precio_venta_base: 'Precio de venta',
  cliente_nombre: 'Cliente o destino', recibido_por: 'Recibido por', observaciones: 'Observaciones',
  fecha: 'Fecha de factura', proveedor_id: 'Proveedor', proveedor_nombre: 'Proveedor',
  metodo_caja_id: 'Cuenta del pago', monto: 'Monto del pago', tasa_cambio: 'Tasa del pago',
};

const nuevoId = () => globalThis.crypto?.randomUUID?.() ?? 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (caracter) => {
  const aleatorio = Math.floor(Math.random() * 16);
  return (caracter === 'x' ? aleatorio : (aleatorio & 0x3) | 0x8).toString(16);
});
const numero = (valor: string) => Number.parseFloat(valor || '0') || 0;
const centavos = (valor: number) => Math.round((valor + Number.EPSILON) * 100) / 100;
const tasaCOP = (valor: string) => Math.round(numero(valor) * 1_000_000) / 1_000_000;
const formato = (valor: number, moneda = 'COP') =>
  `${moneda} ${valor.toLocaleString('es-CO', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

function esRegistro(valor: unknown): valor is Record<string, unknown> {
  return typeof valor === 'object' && valor !== null && !Array.isArray(valor);
}

function esOpcionCatalogo(valor: unknown): valor is OpcionCatalogo {
  if (!esRegistro(valor)) return false;
  return typeof valor.id === 'number'
    && typeof valor.nombre === 'string'
    && typeof valor.monedaId === 'number'
    && (valor.unidad === undefined || typeof valor.unidad === 'string')
    && (valor.departamento === undefined || valor.departamento === null || typeof valor.departamento === 'string')
    && (valor.costo === undefined || valor.costo === null || typeof valor.costo === 'number');
}

function esLineaDraft(valor: unknown): valor is LineaDraft {
  if (!esRegistro(valor)) return false;
  const camposTexto = [
    'key', 'modo', 'itemId', 'nombreNuevo', 'codigoNuevo', 'unidadId', 'departamento',
    'categoriaId', 'tipoProductoId', 'monedaId', 'precioVenta', 'cantidad', 'precio',
    'tasaPrecio', 'llevada', 'descuento', 'ubicacionId', 'cliente', 'observaciones',
  ];
  return (valor.tipo === 'MATERIAL' || valor.tipo === 'PRODUCTO')
    && (valor.modo === 'EXISTENTE' || valor.modo === 'NUEVO')
    && camposTexto.every((campo) => typeof valor[campo] === 'string')
    && (valor.item === null || esOpcionCatalogo(valor.item));
}

function esPagoDraft(valor: unknown): valor is PagoDraft {
  return esRegistro(valor)
    && typeof valor.key === 'string'
    && typeof valor.cuentaKey === 'string'
    && typeof valor.monto === 'string'
    && typeof valor.tasa === 'string'
    && typeof valor.observacion === 'string';
}

/** Los borradores guardados antes del concepto por pago no traen `observacion`. */
function migrarBorradorCompra(valor: unknown): unknown {
  if (!esRegistro(valor) || valor.version !== 1) return valor;
  const pagos = Array.isArray(valor.pagos) ? valor.pagos : [];
  return {
    ...valor,
    version: 2,
    pagos: pagos.map((pago) => esRegistro(pago) ? { observacion: '', ...pago } : pago),
  };
}

function esPayloadPendiente(valor: unknown, operacionId: string): valor is CompraInventarioMultipleCreate {
  return esRegistro(valor)
    && valor.operacion_id === operacionId
    && typeof valor.fecha === 'string'
    && Array.isArray(valor.lineas)
    && Array.isArray(valor.pagos);
}

function esBorradorCompra(valor: unknown): valor is CompraDraftStorage {
  if (!esRegistro(valor)) return false;
  const operacionId = valor.operacionId;
  const payloadPendiente = valor.payloadPendiente;
  return valor.version === 2
    && typeof operacionId === 'string'
    && /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(operacionId)
    && typeof valor.fecha === 'string'
    && typeof valor.proveedor === 'string'
    && typeof valor.recibidoPor === 'string'
    && typeof valor.observaciones === 'string'
    && Array.isArray(valor.lineas) && valor.lineas.every(esLineaDraft)
    && Array.isArray(valor.pagos) && valor.pagos.every(esPagoDraft)
    && (valor.errorCompra === null || typeof valor.errorCompra === 'string')
    && (valor.codigoError === null || typeof valor.codigoError === 'number')
    && typeof valor.confirmacionPendiente === 'boolean'
    && (payloadPendiente === null || esPayloadPendiente(payloadPendiente, operacionId))
    && (!valor.confirmacionPendiente || payloadPendiente !== null);
}

function leerBorradorCompra(clave: string): { borrador: CompraDraftStorage | null; disponible: boolean } {
  try {
    const guardado = sessionStorage.getItem(clave);
    if (!guardado) return { borrador: null, disponible: true };
    const borrador: unknown = migrarBorradorCompra(JSON.parse(guardado));
    if (esBorradorCompra(borrador)) return { borrador, disponible: true };
    sessionStorage.removeItem(clave);
    return { borrador: null, disponible: true };
  } catch {
    return { borrador: null, disponible: false };
  }
}

function guardarBorradorCompra(clave: string, borrador: CompraDraftStorage): boolean {
  try {
    sessionStorage.setItem(clave, JSON.stringify(borrador));
    return true;
  } catch {
    return false;
  }
}

function limpiarBorradorCompra(clave: string): boolean {
  try {
    sessionStorage.removeItem(clave);
    return true;
  } catch {
    return false;
  }
}

function traducirErrorValidacion(detalle: unknown): string | null {
  if (!Array.isArray(detalle)) return null;
  const mensajes = detalle.flatMap((incidencia) => {
    if (!esRegistro(incidencia) || typeof incidencia.msg !== 'string') return [];
    const ubicacion = Array.isArray(incidencia.loc) ? incidencia.loc.slice(1) : [];
    const indiceLinea = ubicacion.findIndex((parte, indice) => parte === 'lineas' && typeof ubicacion[indice + 1] === 'number');
    const indicePago = ubicacion.findIndex((parte, indice) => parte === 'pagos' && typeof ubicacion[indice + 1] === 'number');
    const indice = indiceLinea >= 0 ? Number(ubicacion[indiceLinea + 1]) + 1 : indicePago >= 0 ? Number(ubicacion[indicePago + 1]) + 1 : null;
    const campo = [...ubicacion].reverse().find((parte): parte is string => typeof parte === 'string' && parte !== 'lineas' && parte !== 'pagos');
    const prefijo = indiceLinea >= 0 ? `Renglón ${indice} · ` : indicePago >= 0 ? `Pago ${indice} · ` : '';
    const etiqueta = campo ? ETIQUETAS_ERROR[campo] || campo : '';
    const mensaje = incidencia.msg.replace(/^Value error,\s*/i, '')
      .replace(/^Field required$/i, 'es obligatorio')
      .replace(/^Input should be greater than 0$/i, 'debe ser mayor que cero')
      .replace(/^Input should be greater than or equal to 0$/i, 'no puede ser negativo')
      .replace(/^Input should be a valid number$/i, 'debe ser un número válido')
      .replace(/^Input should be a valid integer$/i, 'debe ser un número entero');
    return [`${prefijo}${etiqueta ? `${etiqueta}: ` : ''}${mensaje}`];
  });
  return mensajes.length ? mensajes.join('\n') : null;
}

function explicarErrorCompra(error: unknown): ErrorCompra {
  if (!axios.isAxiosError(error)) {
    return {
      mensaje: 'Ocurrió un problema inesperado. Conservamos el formulario; vuelve a intentar antes de empezar otra compra.',
      codigo: null,
      confirmacionPendiente: true,
    };
  }

  const codigo = error.response?.status ?? null;
  if (!error.response) {
    return {
      mensaje: 'No llegó respuesta del servidor. La compra pudo haberse guardado; el formulario quedó protegido. Reintenta aquí para consultar el mismo registro sin duplicarlo.',
      codigo: null,
      confirmacionPendiente: true,
    };
  }
  const respuesta = error.response.data as { detail?: unknown } | undefined;
  const detalle = respuesta?.detail;
  const detalleConflicto = typeof detalle === 'string' ? detalle : traducirErrorValidacion(detalle);
  const detalleServidor = typeof detalle === 'string' ? detalle : null;
  if (codigo === 409 || (codigo !== null && codigo >= 500)) {
    return {
      mensaje: codigo === 409
        ? `${detalleConflicto || 'El servidor detectó un conflicto al guardar.'} Reintenta este mismo registro; no empieces otra compra.`
        : detalleServidor
          || 'El servidor no pudo confirmar el resultado. Conservamos los datos y bloqueamos cambios para que puedas reintentar sin duplicar la compra.',
      codigo,
      confirmacionPendiente: true,
    };
  }
  if (codigo === 403) {
    return {
      mensaje: 'Tu usuario no tiene permiso para registrar esta compra o crear uno de los artículos. No se registró; conserva el borrador y solicita acceso.',
      codigo,
      confirmacionPendiente: false,
    };
  }

  const mensaje = typeof detalle === 'string'
    ? detalle
    : traducirErrorValidacion(detalle)
      || (esRegistro(detalle) && typeof detalle.msg === 'string' ? detalle.msg : null)
      || 'Revisa los datos de la factura y vuelve a intentarlo.';
  return { mensaje, codigo, confirmacionPendiente: false };
}

function crearLinea(tipo: LineaDraft['tipo'] = 'MATERIAL'): LineaDraft {
  return {
    key: nuevoId(), tipo, modo: 'EXISTENTE', itemId: '', item: null,
    nombreNuevo: '', codigoNuevo: '', unidadId: '', departamento: '', categoriaId: '',
    tipoProductoId: '', monedaId: '1', precioVenta: '', cantidad: '', precio: '',
    tasaPrecio: '', llevada: '', descuento: '0', ubicacionId: '', cliente: '', observaciones: '',
  };
}

function lineasDeCaptura(captura: CapturaEntrada): LineaDraft[] {
  return captura.lineas.map((linea) => ({
    ...crearLinea(linea.tipo_item), key: linea.linea_id || nuevoId(),
    itemId: String(linea.item_id), item: { id: linea.item_id, nombre: linea.nombre,
      monedaId: linea.moneda_precio_id, unidad: linea.unidad || undefined },
    cantidad: String(linea.cantidad), precio: String(linea.precio_unitario),
    monedaId: String(linea.moneda_precio_id), tasaPrecio: String(linea.tasa_precio_a_cop || ''),
    descuento: String(linea.descuento_porcentaje || 0),
    llevada: String(linea.llevada_total ?? linea.llevada_unitaria ?? 0),
    llevadaModo: linea.llevada_total != null ? 'TOTAL' : 'UNIDAD',
    ubicacionId: String(linea.ubicacion_id || ''), departamento: linea.departamento || '',
    cliente: linea.cliente_nombre || '', observaciones: linea.observaciones || '',
  }));
}

function pagosDeCaptura(captura: CapturaEntrada): PagoDraft[] {
  return captura.pagos.map((pago) => ({ key: pago.pago_id || nuevoId(),
    cuentaKey: `${pago.metodo_caja_id}:${pago.moneda_id}`, monto: String(pago.monto),
    tasa: String(pago.tasa_cambio || ''), observacion: pago.observacion || '' }));
}

function monedaCodigo(monedas: MonedaInfo[], monedaId: string | number) {
  return monedas.find((moneda) => String(moneda.id) === String(monedaId))?.codigo ?? 'COP';
}

function costoUnitarioCOP(linea: LineaDraft, monedas: MonedaInfo[]) {
  const codigo = monedaCodigo(monedas, linea.monedaId);
  const tasa = codigo === 'COP' ? 1 : tasaCOP(linea.tasaPrecio);
  const precioNeto = numero(linea.precio) * (1 - numero(linea.descuento) / 100);
  const costo = centavos(precioNeto * (linea.tipo === 'MATERIAL' ? tasa : 1));
  const llevada = centavos(numero(linea.llevada)) / (linea.llevadaModo === 'TOTAL' ? numero(linea.cantidad) || 1 : 1);
  return centavos((costo + llevada) * (linea.tipo === 'MATERIAL' ? 1 : tasa));
}

function totalLinea(linea: LineaDraft, monedas: MonedaInfo[]) {
  const cantidad = numero(linea.cantidad);
  const precio = numero(linea.precio);
  const pasada = numero(linea.llevada);
  const descuento = numero(linea.descuento);
  const codigo = monedaCodigo(monedas, linea.monedaId);
  const tasa = codigo === 'COP' ? 1 : tasaCOP(linea.tasaPrecio);
  const neto = precio * (1 - descuento / 100);
  const costoUnitario = centavos(neto * (linea.tipo === 'MATERIAL' ? tasa : 1));
  const llevadaTotal = linea.llevadaModo === 'TOTAL' ? centavos(pasada) : centavos(centavos(pasada) * cantidad);
  const multiplicador = linea.tipo === 'MATERIAL' ? 1 : tasa;
  return centavos((centavos(costoUnitario * cantidad) + llevadaTotal) * multiplicador);
}

export default function CompraMultipleModal({
  open, userId, onClose, onCreated, unidades, monedas, ubicaciones, cuentas,
  categoriasMaterial, categoriasProducto, tiposProducto, entrada,
}: Props) {
  const [fecha, setFecha] = useState(hoyVE());
  const [proveedor, setProveedor] = useState('');
  const [recibidoPor, setRecibidoPor] = useState('');
  const [observaciones, setObservaciones] = useState('');
  const [lineas, setLineas] = useState<LineaDraft[]>([crearLinea()]);
  const [pagos, setPagos] = useState<PagoDraft[]>([]);
  const [guardando, setGuardando] = useState(false);
  const [errorCompra, setErrorCompra] = useState<string | null>(null);
  const [codigoError, setCodigoError] = useState<number | null>(null);
  const [confirmacionPendiente, setConfirmacionPendiente] = useState(false);
  const [payloadPendiente, setPayloadPendiente] = useState<CompraInventarioMultipleCreate | null>(null);
  const [borradorRestaurado, setBorradorRestaurado] = useState(false);
  const [avisoPersistencia, setAvisoPersistencia] = useState<string | null>(null);
  const [borradorListo, setBorradorListo] = useState(false);
  const [motivo, setMotivo] = useState('');
  const [revisionVisible, setRevisionVisible] = useState(false);
  const [versionCorreccion, setVersionCorreccion] = useState(entrada?.version ?? 1);
  const correccionId = useRef<string>(nuevoId());
  const revisionCaptura = useRef<CompraInventarioMultipleCreate | null>(null);
  const revisionPanel = useRef<HTMLElement | null>(null);
  const operacionId = useRef<string>(nuevoId());
  const compraExitosa = useRef(false);
  const claveBorrador = userId === null ? null : `${CLAVE_BORRADOR}:${userId}${entrada ? `:corregir:${entrada.compra_id}` : ''}`;

  useEffect(() => {
    if (revisionVisible) revisionPanel.current?.scrollIntoView({ block: 'end' });
  }, [revisionVisible]);

  useEffect(() => {
    if (!open) return;
    const alPresionarEscape = (evento: KeyboardEvent) => {
      if (evento.key === 'Escape' && !guardando) onClose();
    };
    window.addEventListener('keydown', alPresionarEscape);
    return () => window.removeEventListener('keydown', alPresionarEscape);
  }, [open, guardando, onClose]);

  useEffect(() => {
    if (!open) {
      setBorradorListo(false);
      return;
    }
    compraExitosa.current = false;
    setFecha(hoyVE());
    setProveedor('');
    setRecibidoPor('');
    setObservaciones('');
    setLineas([crearLinea()]);
    setPagos([]);
    setGuardando(false);
    setErrorCompra(null);
    setCodigoError(null);
    setConfirmacionPendiente(false);
    setPayloadPendiente(null);
    setMotivo('');
    setRevisionVisible(false);
    setVersionCorreccion(entrada?.version ?? 1);
    correccionId.current = nuevoId();
    const lectura = claveBorrador
      ? leerBorradorCompra(claveBorrador)
      : { borrador: null, disponible: true };
    const borrador = lectura.borrador;
    if (borrador) {
      operacionId.current = borrador.operacionId;
      setFecha(borrador.fecha);
      setProveedor(borrador.proveedor);
      setRecibidoPor(borrador.recibidoPor);
      setObservaciones(borrador.observaciones);
      setLineas(borrador.lineas);
      setPagos(borrador.pagos);
      setErrorCompra(borrador.errorCompra);
      setCodigoError(borrador.codigoError);
      setConfirmacionPendiente(borrador.confirmacionPendiente);
      setPayloadPendiente(borrador.payloadPendiente);
      setMotivo(borrador.motivo || '');
      setVersionCorreccion(borrador.versionCorreccion ?? entrada?.version ?? 1);
      correccionId.current = borrador.correccionId || nuevoId();
    } else if (entrada) {
      operacionId.current = entrada.datos.operacion_id;
      setFecha(entrada.datos.fecha);
      setProveedor(entrada.datos.proveedor_nombre || '');
      setRecibidoPor(entrada.datos.recibido_por || '');
      setObservaciones(entrada.datos.observaciones || '');
      setLineas(lineasDeCaptura(entrada.datos));
      setPagos(pagosDeCaptura(entrada.datos));
    } else {
      operacionId.current = nuevoId();
    }
    setBorradorRestaurado(Boolean(borrador));
    setAvisoPersistencia(lectura.disponible ? null : 'El navegador no permitió leer el borrador guardado. No cierres esta ventana hasta resolver la compra.');
    setBorradorListo(true);
  }, [open, claveBorrador, entrada]);

  useEffect(() => {
    if (!open || !borradorListo || !claveBorrador || compraExitosa.current) return;
    const guardado = guardarBorradorCompra(claveBorrador, {
      version: 2,
      operacionId: operacionId.current,
      fecha,
      proveedor,
      recibidoPor,
      observaciones,
      lineas,
      pagos,
      errorCompra,
      codigoError,
      confirmacionPendiente,
      payloadPendiente,
      motivo, correccionId: correccionId.current, versionCorreccion,
    });
    setAvisoPersistencia(guardado ? null : 'No se pudo guardar el borrador en este navegador. Mantén esta ventana abierta para no perder los datos.');
  }, [
    open, borradorListo, claveBorrador, fecha, proveedor, recibidoPor, observaciones,
    lineas, pagos, errorCompra, codigoError, confirmacionPendiente, payloadPendiente, motivo, versionCorreccion,
  ]);

  const buscarMateriales = useCallback(async (query: string) => {
    const items = await productosService.getMateriales(query || undefined, 40);
    return items.map((item) => ({ value: item.id, label: item.nombre }));
  }, []);

  const buscarReventa = useCallback(async (query: string) => {
    const items = await productosService.getProductos(query || undefined, { es_reventa: true, limite: 40 });
    return items.map((item) => ({ value: item.id, label: item.codigo ? `${item.nombre} · ${item.codigo}` : item.nombre }));
  }, []);

  const totalCOP = useMemo(
    () => centavos(lineas.reduce((total, linea) => total + totalLinea(linea, monedas), 0)),
    [lineas, monedas],
  );

  const pagosCOP = useMemo(() => centavos(pagos.reduce((total, pago) => {
    const cuenta = cuentas.find((item) => item.key === pago.cuentaKey);
    if (!cuenta || !numero(pago.monto)) return total;
    const tasa = cuenta.codigo === 'COP' ? 1 : tasaCOP(pago.tasa);
    return total + centavos(numero(pago.monto) * tasa);
  }, 0)), [pagos, cuentas]);

  const aplicadoPosterior = Number(entrada?.abonado_posterior || 0) + Number(entrada?.descontado_posterior || 0);
  const saldoCOP = centavos(totalCOP - pagosCOP - aplicadoPosterior);
  const tipoReventa = tiposProducto.find((tipo) => /revend|reventa/i.test(tipo.nombre));
  const cambiarLinea = (key: string, cambio: Partial<LineaDraft>) =>
    setLineas((actuales) => actuales.map((linea) => linea.key === key ? { ...linea, ...cambio } : linea));

  const seleccionarExistente = async (key: string, id: string) => {
    const linea = lineas.find((item) => item.key === key);
    if (!linea) return;
    if (!id) {
      cambiarLinea(key, { itemId: '', item: null, precio: '' });
      return;
    }
    try {
      if (linea.tipo === 'MATERIAL') {
        const material = await productosService.getMaterial(id);
        cambiarLinea(key, {
          itemId: id,
          item: {
            id: material.id,
            nombre: material.nombre,
            unidad: material.unidad_medida?.abreviatura || material.unidad_medida?.nombre,
            departamento: material.departamento,
            monedaId: 1,
            costo: material.costo_base,
          },
          departamento: material.departamento || '',
          monedaId: '1',
        });
      } else {
        const producto = await productosService.getById(Number(id));
        cambiarLinea(key, {
          itemId: id,
          item: {
            id: producto.id,
            nombre: producto.nombre,
            monedaId: producto.moneda_id || 1,
            costo: producto.precio_costo_base,
          },
          monedaId: String(producto.moneda_id || 1),
        });
      }
    } catch (error) {
      cambiarLinea(key, { itemId: '', item: null });
      const codigo = axios.isAxiosError(error) ? error.response?.status ?? null : null;
      setCodigoError(codigo);
      setErrorCompra('No se pudo cargar el artículo del catálogo. Revisa la conexión y vuelve a seleccionarlo; el resto del borrador sigue guardado.');
    }
  };

  const cambiarTipo = (key: string, tipo: LineaDraft['tipo']) =>
    cambiarLinea(key, { ...crearLinea(tipo), key });

  const validar = () => {
    if (!lineas.length) return 'Agrega al menos un artículo.';
    for (const [index, linea] of lineas.entries()) {
      const nombre = linea.item?.nombre || linea.nombreNuevo.trim();
      if (!nombre) return `Indica el artículo del renglón ${index + 1}.`;
      if (linea.modo === 'EXISTENTE' && !linea.itemId) return `Selecciona un artículo en el renglón ${index + 1}.`;
      if (linea.modo === 'NUEVO' && linea.tipo === 'MATERIAL' && !linea.unidadId) return `Selecciona la unidad de medida del material en el renglón ${index + 1}.`;
      if (linea.modo === 'NUEVO' && linea.tipo === 'PRODUCTO' && !(linea.tipoProductoId || tipoReventa?.id)) return `Selecciona el tipo de producto en el renglón ${index + 1}.`;
      if (!(numero(linea.cantidad) > 0)) return `La cantidad del renglón ${index + 1} debe ser mayor que cero.`;
      if (!(numero(linea.precio) > 0)) return `Indica el precio unitario del renglón ${index + 1}.`;
      if (monedaCodigo(monedas, linea.monedaId) !== 'COP' && !(tasaCOP(linea.tasaPrecio) > 0)) return `Indica la tasa del precio del renglón ${index + 1}.`;
      if (linea.tipo === 'PRODUCTO' && !linea.ubicacionId) return `Selecciona la ubicación del producto en el renglón ${index + 1}.`;
    }
    for (const [index, pago] of pagos.entries()) {
      const cuenta = cuentas.find((item) => item.key === pago.cuentaKey);
      if (!cuenta) return `Selecciona la cuenta del pago ${index + 1}.`;
      if (!(numero(pago.monto) > 0)) return `Indica el monto del pago ${index + 1}.`;
      if (cuenta.codigo !== 'COP' && !(tasaCOP(pago.tasa) > 0)) return `Indica la tasa de cambio del pago ${index + 1}.`;
    }
    if (!(totalCOP > 0)) return 'El total de la factura debe ser mayor que cero.';
    if (pagosCOP > totalCOP) return 'Los pagos superan el total de la factura.';
    if (saldoCOP < 0) return 'El total corregido no alcanza para los pagos y abonos existentes. Revisa los importes.';
    if (saldoCOP > 0 && !proveedor.trim()) return 'Indica el proveedor para registrar el saldo pendiente.';
    if (entrada && motivo.trim().length < 3) return 'Explica el motivo de la corrección.';
    return null;
  };

  const guardar = async (event: React.FormEvent) => {
    event.preventDefault();
    let payload: CompraInventarioMultipleCreate;
    if (confirmacionPendiente && payloadPendiente) {
      payload = payloadPendiente;
    } else {
      const error = validar();
      if (error) {
        setErrorCompra(error);
        setCodigoError(null);
        return;
      }

      payload = {
        operacion_id: operacionId.current,
        fecha,
        proveedor_nombre: proveedor.trim() || undefined,
        proveedor_id: entrada && proveedor.trim() === entrada.datos.proveedor_nombre ? entrada.datos.proveedor_id : undefined,
        recibido_por: recibidoPor.trim() || undefined,
        observaciones: observaciones.trim() || undefined,
        lineas: lineas.map((linea) => {
          const base = {
            linea_id: linea.key,
            tipo_item: linea.tipo,
            cantidad: numero(linea.cantidad),
            precio_unitario: numero(linea.precio),
            moneda_precio_id: Number(linea.monedaId) || 1,
            tasa_precio_a_cop: tasaCOP(linea.tasaPrecio) || undefined,
            llevada_unitaria: linea.llevadaModo === 'TOTAL' ? 0 : numero(linea.llevada),
            llevada_total: linea.llevadaModo === 'TOTAL' ? numero(linea.llevada) : undefined,
            descuento_porcentaje: numero(linea.descuento),
            cliente_nombre: linea.cliente.trim() || undefined,
            observaciones: linea.observaciones.trim() || undefined,
          };
          if (linea.tipo === 'MATERIAL') {
            return {
              ...base,
              material_id: linea.modo === 'EXISTENTE' ? Number(linea.itemId) : undefined,
              departamento: linea.departamento === 'GENERAL' ? undefined : linea.departamento || undefined,
              nuevo_material: linea.modo === 'NUEVO' ? {
                nombre: linea.nombreNuevo.trim(),
                unidad_medida_id: Number(linea.unidadId),
                departamento: linea.departamento === 'GENERAL' ? undefined : linea.departamento || undefined,
                categoria_inventario_id: Number(linea.categoriaId) || undefined,
              } : undefined,
            };
          }
          return {
            ...base,
            producto_id: linea.modo === 'EXISTENTE' ? Number(linea.itemId) : undefined,
            ubicacion_id: Number(linea.ubicacionId),
            nuevo_producto: linea.modo === 'NUEVO' ? {
              nombre: linea.nombreNuevo.trim(),
              codigo: linea.codigoNuevo.trim() || undefined,
              tipo_producto_id: Number(linea.tipoProductoId || tipoReventa?.id),
              moneda_id: Number(linea.monedaId) || 1,
              categoria_inventario_id: Number(linea.categoriaId) || undefined,
              precio_venta_base: numero(linea.precioVenta) || undefined,
            } : undefined,
          };
        }),
        pagos: pagos.map((pago) => {
          const cuenta = cuentas.find((opcion) => opcion.key === pago.cuentaKey)!;
          return {
            pago_id: pago.key,
            metodo_caja_id: cuenta.cuentaId,
            monto: numero(pago.monto),
            tasa_cambio: cuenta.codigo === 'COP' ? 1 : tasaCOP(pago.tasa),
            observacion: pago.observacion.trim() || undefined,
          };
        }),
      };
    }

    if (entrada && !confirmacionPendiente && !revisionVisible) {
      revisionCaptura.current = payload;
      setRevisionVisible(true);
      setErrorCompra(null);
      return;
    }

    setErrorCompra(null);
    setCodigoError(null);
    setConfirmacionPendiente(true);
    setPayloadPendiente(payload);
    if (claveBorrador) {
      const guardado = guardarBorradorCompra(claveBorrador, {
        version: 2,
        operacionId: payload.operacion_id,
        fecha,
        proveedor,
        recibidoPor,
        observaciones,
        lineas,
        pagos,
        errorCompra: null,
        codigoError: null,
        confirmacionPendiente: true,
        payloadPendiente: payload,
        motivo, correccionId: correccionId.current, versionCorreccion,
      });
      if (!guardado) setAvisoPersistencia('No se pudo guardar el intento en este navegador. Mantén esta ventana abierta hasta recibir confirmación.');
    }
    setGuardando(true);
    try {
      const compra = entrada
        ? await inventarioService.corregirEntrada(entrada.compra_id, {
          operacion_id: correccionId.current, version: versionCorreccion, motivo, entrada: payload,
        })
        : await inventarioService.crearCompraMultiple(payload);
      compraExitosa.current = true;
      const borradorEliminado = claveBorrador ? limpiarBorradorCompra(claveBorrador) : true;
      if (!borradorEliminado) {
        setAvisoPersistencia('La compra se guardó, pero no se pudo borrar la copia local del borrador.');
      }
      onCreated(compra);
    } catch (error: unknown) {
      const explicado = explicarErrorCompra(error);
      if (entrada && explicado.codigo === 409) {
        explicado.confirmacionPendiente = false;
        if (axios.isAxiosError(error) && typeof error.response?.data?.detail === 'string') explicado.mensaje = error.response.data.detail;
        setBorradorListo(false);
        if (claveBorrador) limpiarBorradorCompra(claveBorrador);
      }
      setErrorCompra(explicado.mensaje);
      setCodigoError(explicado.codigo);
      setConfirmacionPendiente(explicado.confirmacionPendiente);
      setPayloadPendiente(explicado.confirmacionPendiente ? payload : null);
    } finally {
      setGuardando(false);
    }
  };

  if (!open) return null;

  const campo = 'w-full rounded-xl border border-yeikar-secondary-light/20 bg-white px-3 py-2.5 text-sm text-yeikar-neutral outline-none transition focus:border-yeikar-primary focus:ring-2 focus:ring-yeikar-primary/15';
  const etiqueta = 'mb-1 block text-[11px] font-bold uppercase tracking-wide text-yeikar-neutral/55';
  const ubicacionPredeterminada = ubicaciones.find((ubicacion) => /deposito|principal/i.test(ubicacion.nombre)) || ubicaciones[0];

  return (
    <div className="fixed inset-0 z-[90] flex items-end justify-center bg-yeikar-neutral/60 p-0 backdrop-blur-sm sm:items-center sm:p-4" role="dialog" aria-modal="true" aria-labelledby="compra-multiple-titulo">
      <div className="flex h-[96dvh] max-h-[96dvh] min-h-0 w-full max-w-6xl flex-col overflow-hidden rounded-t-3xl border border-white/40 bg-[#fbf8f0] shadow-2xl sm:rounded-3xl">
        <header className="flex shrink-0 items-start justify-between gap-4 border-b border-yeikar-secondary-light/15 bg-white px-5 py-4 sm:px-7">
          <div>
            <div className="mb-1 flex items-center gap-2 text-yeikar-primary">
              <ReceiptText size={17} />
              <span className="font-mono text-[10px] font-bold uppercase tracking-[0.2em]">Entrada agrupada</span>
            </div>
            <h2 id="compra-multiple-titulo" className="font-headline text-xl font-black text-yeikar-secondary sm:text-2xl">{entrada ? 'Corregir entrada de inventario' : 'Entrada de inventario'}</h2>
            <p className="mt-1 text-xs text-yeikar-neutral/55">Una factura, varios renglones y pagos por cuenta. El saldo pendiente siempre se expresa en COP.</p>
            {borradorRestaurado && <p className="mt-1 text-xs font-bold text-yeikar-primary-dark">Borrador recuperado; puedes cambiar de sección y volver sin perderlo.</p>}
          </div>
          <button type="button" onClick={onClose} disabled={guardando} className="rounded-xl p-2 text-yeikar-neutral/50 transition hover:bg-yeikar-tertiary hover:text-yeikar-secondary" aria-label="Cerrar">
            <X size={20} />
          </button>
        </header>

        {errorCompra && (
          <div id="compra-multiple-error" role="alert" aria-live="assertive" className="flex max-h-[30dvh] shrink-0 items-start gap-3 overflow-y-auto border-b border-red-200 bg-red-50 px-5 py-3 text-red-950 sm:px-7">
            <AlertTriangle size={19} className="mt-0.5 shrink-0 text-red-700" />
            <div className="min-w-0 flex-1">
              <p className="text-sm font-black">{confirmacionPendiente ? 'Falta confirmar el resultado' : 'No se pudo completar la compra'}</p>
              <p className="mt-1 whitespace-pre-line text-sm leading-relaxed">{errorCompra}</p>
              {codigoError !== null && <p className="mt-1 font-mono text-[10px] text-red-800/70">Referencia técnica: HTTP {codigoError}</p>}
              <p className="mt-1 text-xs text-red-900/80">
                {confirmacionPendiente
                  ? 'No inicies otra compra. Reintentar enviará exactamente la misma solicitud para evitar duplicados.'
                  : 'Tus datos siguen guardados en el borrador. Corrige lo indicado y vuelve a intentar.'}
              </p>
            </div>
            {!confirmacionPendiente && <button type="button" onClick={() => { setErrorCompra(null); setCodigoError(null); }} className="shrink-0 rounded-lg p-1 text-red-800/60 hover:bg-red-100 hover:text-red-950" aria-label="Cerrar mensaje de error"><X size={17} /></button>}
          </div>
        )}
        {avisoPersistencia && <p role="status" className="shrink-0 border-b border-amber-200 bg-amber-50 px-5 py-2 text-xs font-semibold text-amber-900 sm:px-7">{avisoPersistencia}</p>}

        <form onSubmit={guardar} onChange={() => setRevisionVisible(false)} className="flex min-h-0 flex-1 flex-col overflow-hidden">
          <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain">
          <fieldset disabled={guardando || confirmacionPendiente} className="min-w-0 border-0 p-0">
          <div className="space-y-6 p-4 sm:p-7">
            {entrada && <section className="space-y-3 rounded-2xl border border-yeikar-primary/30 bg-white p-4">
              <p className="text-sm font-semibold text-yeikar-secondary">Datos guardados precargados · versión {versionCorreccion}. Corrige solo lo que se registró mal; los abonos posteriores siguen en Gastos.</p>
              <details><summary className="cursor-pointer text-sm font-bold text-yeikar-secondary">Ver registro original (primera captura)</summary><EntradaCapturaResumen captura={entrada.original} cuentas={cuentas} /></details>
              {entrada.historial.length > 0 && <details><summary className="cursor-pointer text-sm font-bold text-yeikar-secondary">Correcciones anteriores ({entrada.historial.length})</summary>
                {entrada.historial.map((correccion) => <details key={correccion.fecha} className="mt-2 border-t pt-2"><summary className="cursor-pointer text-xs">{new Date(correccion.fecha).toLocaleString('es-VE')} · {correccion.motivo}</summary><EntradaCapturaResumen captura={correccion.despues} cuentas={cuentas} /></details>)}
              </details>}
            </section>}
            <section className="grid gap-3 rounded-2xl border border-yeikar-secondary-light/15 bg-white p-4 sm:grid-cols-3 sm:p-5">
              <label>
                <span className={etiqueta}>Fecha de factura</span>
                <input className={campo} type="date" max={hoyVE()} value={fecha} onChange={(event) => setFecha(event.target.value)} required />
              </label>
              <label>
                <span className={etiqueta}>Proveedor</span>
                <input className={campo} value={proveedor} onChange={(event) => setProveedor(event.target.value)} placeholder="Nombre del proveedor" />
              </label>
              <label>
                <span className={etiqueta}>Recibido por</span>
                <input className={campo} value={recibidoPor} onChange={(event) => setRecibidoPor(event.target.value)} placeholder="Persona que recibió" />
              </label>
            </section>

            <section className="space-y-3">
              <div className="flex items-end justify-between gap-3">
                <div>
                  <p className="font-mono text-[10px] font-bold uppercase tracking-[0.18em] text-yeikar-primary">Detalle</p>
                  <h3 className="font-headline text-lg font-black text-yeikar-secondary">Artículos de la factura</h3>
                </div>
                <button type="button" onClick={() => setLineas((actuales) => [...actuales, crearLinea(actuales[actuales.length - 1]?.tipo)])} className="inline-flex items-center gap-1.5 rounded-xl border border-yeikar-secondary-light/20 bg-white px-3 py-2 text-xs font-bold text-yeikar-secondary transition hover:border-yeikar-primary/60">
                  <Plus size={15} /> Agregar renglón
                </button>
              </div>

              {lineas.map((linea, index) => {
                const monedaActual = monedaCodigo(monedas, linea.monedaId);
                const nombreItem = linea.item?.nombre || linea.nombreNuevo.trim() || `Renglón ${index + 1}`;
                const total = totalLinea(linea, monedas);
                const totalUnitario = costoUnitarioCOP(linea, monedas);
                return (
                  <article key={linea.key} className="overflow-hidden rounded-2xl border border-yeikar-secondary-light/15 bg-white shadow-sm">
                    <div className="flex items-center justify-between gap-3 border-b border-yeikar-secondary-light/10 bg-[#f7f2e6] px-4 py-3">
                      <div className="flex min-w-0 items-center gap-3">
                        <span className="grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-yeikar-secondary text-xs font-black text-white">{String(index + 1).padStart(2, '0')}</span>
                        <div className="min-w-0">
                          <p className="truncate font-headline text-sm font-black text-yeikar-secondary">{nombreItem}</p>
                          <p className="text-[10px] font-mono uppercase tracking-wide text-yeikar-neutral/45">{linea.tipo === 'MATERIAL' ? 'Material / insumo' : 'Producto de reventa'}</p>
                        </div>
                      </div>
                      <div className="flex items-center gap-2">
                        <select className="rounded-lg border border-yeikar-secondary-light/20 bg-white px-2 py-1.5 text-xs font-bold text-yeikar-secondary" value={linea.tipo} onChange={(event) => cambiarTipo(linea.key, event.target.value as LineaDraft['tipo'])} aria-label="Tipo de artículo">
                          <option value="MATERIAL">Material</option>
                          <option value="PRODUCTO">Reventa</option>
                        </select>
                        {lineas.length > 1 && <button type="button" onClick={() => setLineas((actuales) => actuales.filter((item) => item.key !== linea.key))} className="rounded-lg p-2 text-yeikar-neutral/35 hover:bg-red-50 hover:text-red-600" aria-label={`Quitar renglón ${index + 1}`}><Trash2 size={16} /></button>}
                      </div>
                    </div>

                    <div className="space-y-4 p-4">
                      <div className="flex flex-wrap gap-2">
                        <button type="button" onClick={() => cambiarLinea(linea.key, { modo: 'EXISTENTE', itemId: '', item: null, nombreNuevo: '' })} className={`rounded-lg px-3 py-1.5 text-[11px] font-bold ${linea.modo === 'EXISTENTE' ? 'bg-yeikar-secondary text-white' : 'bg-yeikar-tertiary text-yeikar-neutral/60'}`}>Elegir del catálogo</button>
                        <button type="button" onClick={() => cambiarLinea(linea.key, { modo: 'NUEVO', itemId: '', item: null, nombreNuevo: '' })} className={`rounded-lg px-3 py-1.5 text-[11px] font-bold ${linea.modo === 'NUEVO' ? 'bg-yeikar-primary text-yeikar-neutral' : 'bg-yeikar-tertiary text-yeikar-neutral/60'}`}>Crear artículo nuevo</button>
                      </div>

                      {linea.modo === 'EXISTENTE' ? (
                        <label className="block">
                          <span className={etiqueta}>{linea.tipo === 'MATERIAL' ? 'Buscar material' : 'Buscar producto de reventa'}</span>
                          <SearchSelect
                            value={linea.itemId}
                            onChange={(value) => void seleccionarExistente(linea.key, String(value))}
                            loadOptions={linea.tipo === 'MATERIAL' ? buscarMateriales : buscarReventa}
                            minChars={0}
                            placeholder="Busca por nombre o código..."
                            searchPlaceholder="Escribe para buscar..."
                            emptyText="No encontrado. Usa «Crear artículo nuevo»."
                            selectedOption={linea.item ? { value: linea.item.id, label: linea.item.nombre } : undefined}
                          />
                          {linea.item?.unidad && <span className="mt-1 block text-[10px] text-yeikar-neutral/45">Unidad del catálogo: {linea.item.unidad}</span>}
                        </label>
                      ) : (
                        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                          <label className="sm:col-span-2 lg:col-span-1">
                            <span className={etiqueta}>Nombre del artículo</span>
                            <input className={campo} value={linea.nombreNuevo} onChange={(event) => cambiarLinea(linea.key, { nombreNuevo: event.target.value })} placeholder="Nombre que quedará en el catálogo" required />
                          </label>
                          {linea.tipo === 'MATERIAL' ? (
                            <>
                              <label>
                                <span className={etiqueta}>Unidad de medida *</span>
                                <select className={campo} value={linea.unidadId} onChange={(event) => cambiarLinea(linea.key, { unidadId: event.target.value })} required>
                                  <option value="">Selecciona unidad</option>
                                  {unidades.map((unidad) => <option key={unidad.id} value={unidad.id}>{unidad.nombre} ({unidad.abreviatura})</option>)}
                                </select>
                              </label>
                              <label>
                                <span className={etiqueta}>Departamento del material</span>
                                <select className={campo} value={linea.departamento || 'GENERAL'} onChange={(event) => cambiarLinea(linea.key, { departamento: event.target.value })}>
                                  <option value="GENERAL">General / transversal</option>
                                  {DEPARTAMENTOS.map(([valor, label]) => <option key={valor} value={valor}>{label}</option>)}
                                </select>
                              </label>
                              <label>
                                <span className={etiqueta}>Categoría (opcional)</span>
                                <select className={campo} value={linea.categoriaId} onChange={(event) => cambiarLinea(linea.key, { categoriaId: event.target.value })}>
                                  <option value="">Sin categoría</option>
                                  {categoriasMaterial.map((categoria) => <option key={categoria.id} value={categoria.id}>{categoria.nombre}</option>)}
                                </select>
                              </label>
                            </>
                          ) : (
                            <>
                              <label>
                                <span className={etiqueta}>Tipo de producto *</span>
                                <select className={campo} value={linea.tipoProductoId || (tipoReventa ? String(tipoReventa.id) : '')} onChange={(event) => cambiarLinea(linea.key, { tipoProductoId: event.target.value })} required>
                                  <option value="">Selecciona tipo</option>
                                  {tiposProducto.map((tipo) => <option key={tipo.id} value={tipo.id}>{tipo.nombre}</option>)}
                                </select>
                              </label>
                              <label>
                                <span className={etiqueta}>Código (opcional)</span>
                                <input className={campo} value={linea.codigoNuevo} onChange={(event) => cambiarLinea(linea.key, { codigoNuevo: event.target.value })} placeholder="Código de referencia" />
                              </label>
                              <label>
                                <span className={etiqueta}>Categoría (opcional)</span>
                                <select className={campo} value={linea.categoriaId} onChange={(event) => cambiarLinea(linea.key, { categoriaId: event.target.value })}>
                                  <option value="">Sin categoría</option>
                                  {categoriasProducto.map((categoria) => <option key={categoria.id} value={categoria.id}>{categoria.nombre}</option>)}
                                </select>
                              </label>
                              <label>
                                <span className={etiqueta}>Moneda del producto</span>
                                <select className={campo} value={linea.monedaId} onChange={(event) => cambiarLinea(linea.key, { monedaId: event.target.value, tasaPrecio: '' })}>
                                  {monedas.map((moneda) => <option key={moneda.id} value={moneda.id}>{moneda.codigo} · {moneda.nombre}</option>)}
                                </select>
                              </label>
                              <label>
                                <span className={etiqueta}>Precio de venta (opcional)</span>
                                <input className={campo} type="number" min="0" step="0.01" value={linea.precioVenta} onChange={(event) => cambiarLinea(linea.key, { precioVenta: event.target.value })} placeholder="0.00" />
                              </label>
                              <p className="self-end rounded-xl bg-yeikar-tertiary/60 px-3 py-2 text-[10px] text-yeikar-neutral/55">Los productos de reventa ingresan por unidad.</p>
                            </>
                          )}
                        </div>
                      )}

                      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                        <label>
                          <span className={etiqueta}>Cantidad {linea.tipo === 'MATERIAL' && linea.item?.unidad ? `(${linea.item.unidad})` : '(unidades)'}</span>
                          <input className={campo} type="number" min={linea.tipo === 'MATERIAL' ? '0.0001' : '0.01'} step={linea.tipo === 'MATERIAL' ? '0.0001' : '0.01'} value={linea.cantidad} onChange={(event) => cambiarLinea(linea.key, { cantidad: event.target.value })} placeholder="0" required />
                        </label>
                        <label>
                          <span className={etiqueta}>Precio unitario</span>
                          <div className="flex gap-2">
                            <input className={`${campo} min-w-0`} type="number" min="0.01" step="0.01" value={linea.precio} onChange={(event) => cambiarLinea(linea.key, { precio: event.target.value })} placeholder="0.00" required />
                            {linea.tipo === 'MATERIAL' ? (
                              <select className="w-20 rounded-xl border border-yeikar-secondary-light/20 bg-white px-2 text-xs font-bold" value={linea.monedaId} onChange={(event) => cambiarLinea(linea.key, { monedaId: event.target.value, tasaPrecio: '' })} aria-label="Moneda del precio">
                                {monedas.map((moneda) => <option key={moneda.id} value={moneda.id}>{moneda.codigo}</option>)}
                              </select>
                            ) : <span className="flex items-center rounded-lg bg-yeikar-tertiary px-2 text-xs font-mono">{monedaActual}</span>}
                          </div>
                        </label>
                        <label>
                          <span className={etiqueta}>Descuento (%)</span>
                          <input className={campo} type="number" min="0" max="100" step="0.01" value={linea.descuento} onChange={(event) => cambiarLinea(linea.key, { descuento: event.target.value })} />
                        </label>
                        <label>
                          <span className={etiqueta}>Llevada {linea.llevadaModo === 'TOTAL' ? 'total' : 'por unidad'} ({linea.tipo === 'MATERIAL' ? 'COP' : monedaActual})</span>
                          <input className={campo} type="number" min="0" step="0.01" value={linea.llevada} onChange={(event) => cambiarLinea(linea.key, { llevada: event.target.value })} placeholder="0.00" />
                          <select aria-label={`Modo de llevada del renglón ${index + 1}`} className="mt-1 text-xs" value={linea.llevadaModo || 'UNIDAD'} onChange={(event) => cambiarLinea(linea.key, { llevadaModo: event.target.value as 'UNIDAD' | 'TOTAL' })}><option value="UNIDAD">Por unidad</option><option value="TOTAL">Total del renglón</option></select>
                        </label>
                      </div>

                      {monedaActual !== 'COP' && (
                        <label className="block max-w-sm">
                          <span className={etiqueta}>Tasa del precio · {resolverParMonedas(monedaActual, 'COP').label}</span>
                          <input className={campo} type="number" min="0.000001" step="0.000001" value={linea.tasaPrecio} onChange={(event) => cambiarLinea(linea.key, { tasaPrecio: event.target.value })} placeholder={resolverParMonedas(monedaActual, 'COP').placeholder} required />
                        </label>
                      )}

                      {linea.tipo === 'MATERIAL' ? (
                        <div className="grid gap-3 sm:grid-cols-2">
                          <label>
                            <span className={etiqueta}>Departamento destino</span>
                            <select className={campo} value={linea.departamento || 'GENERAL'} onChange={(event) => cambiarLinea(linea.key, { departamento: event.target.value })}>
                              <option value="GENERAL">General / transversal</option>
                              {DEPARTAMENTOS.map(([valor, label]) => <option key={valor} value={valor}>{label}</option>)}
                            </select>
                          </label>
                          <label>
                            <span className={etiqueta}>Cliente / destino (opcional)</span>
                            <input className={campo} value={linea.cliente} onChange={(event) => cambiarLinea(linea.key, { cliente: event.target.value })} placeholder="Para quién se compró" />
                          </label>
                        </div>
                      ) : (
                        <div className="grid gap-3 sm:grid-cols-2">
                          <label>
                            <span className={etiqueta}>Ubicación de inventario</span>
                            <select className={campo} value={linea.ubicacionId || (ubicacionPredeterminada ? String(ubicacionPredeterminada.id) : '')} onChange={(event) => cambiarLinea(linea.key, { ubicacionId: event.target.value })} required>
                              <option value="">Selecciona ubicación</option>
                              {ubicaciones.map((ubicacion) => <option key={ubicacion.id} value={ubicacion.id}>{ubicacion.nombre}</option>)}
                            </select>
                          </label>
                          <label>
                            <span className={etiqueta}>Cliente / destino (opcional)</span>
                            <input className={campo} value={linea.cliente} onChange={(event) => cambiarLinea(linea.key, { cliente: event.target.value })} placeholder="Para quién se compró" />
                          </label>
                        </div>
                      )}

                      <div className="flex flex-wrap items-center justify-between gap-3 border-t border-yeikar-secondary-light/10 pt-3">
                        <p className="text-xs text-yeikar-neutral/55">Costo unitario real estimado: <b className="font-mono text-yeikar-secondary">{formato(totalUnitario, 'COP')}</b></p>
                        <p className="rounded-xl bg-yeikar-secondary px-3 py-2 font-mono text-sm font-black text-white">Línea: {formato(total, 'COP')}</p>
                      </div>
                      <label className="block"><span className={etiqueta}>Observaciones del renglón (opcional)</span><textarea className={campo} value={linea.observaciones} onChange={(event) => cambiarLinea(linea.key, { observaciones: event.target.value })} /></label>
                    </div>
                  </article>
                );
              })}
            </section>

            <PagosEntradaEditor pagos={pagos} cuentas={cuentas} totalCOP={totalCOP} aplicadoPosterior={aplicadoPosterior} onChange={(nuevos) => { setPagos(nuevos); setRevisionVisible(false); }} />

            <label className="block">
              <span className={etiqueta}>Observaciones de la factura (opcional)</span>
              <textarea className={`${campo} min-h-20 resize-y`} value={observaciones} onChange={(event) => setObservaciones(event.target.value)} placeholder="Número de factura, nota o referencia..." />
            </label>
            {entrada && <label className="block"><span className={etiqueta}>Motivo de la corrección *</span>
              <textarea className={campo} minLength={3} maxLength={500} required value={motivo} onChange={(event) => setMotivo(event.target.value)} placeholder="Qué se registró mal y qué estás corrigiendo" />
            </label>}
            {entrada && revisionVisible && <section ref={revisionPanel} role="status" className="rounded-2xl border-2 border-yeikar-primary bg-white p-4 text-sm text-yeikar-secondary">
              <h3 className="font-headline font-black">Revisa antes de confirmar</h3>
              <p className="mt-2">Total: {formato(Number(entrada.total_en_moneda_base))} → <b>{formato(totalCOP)}</b></p>
              <p>Pagos iniciales: {formato(Number(entrada.pagado_en_moneda_base))} → <b>{formato(pagosCOP)}</b></p>
              <p>Pendiente actual: {formato(Number(entrada.saldo_actual))} → <b>{formato(saldoCOP)}</b></p>
              {revisionCaptura.current && <EntradaCambiosResumen anterior={entrada.datos} corregida={revisionCaptura.current} nombres={Object.fromEntries(lineas.map((linea) => [linea.key, linea.item?.nombre || linea.nombreNuevo]))} />}
              <p className="mt-2 text-xs">Se corregirán los renglones y pagos mostrados arriba. Los abonos de Gastos no se modificarán. Si un cambio es incompatible con el historial, no se guardará ninguna parte.</p>
            </section>}
          </div>
          </fieldset>
          </div>

          <footer className="flex shrink-0 flex-col-reverse gap-2 border-t border-yeikar-secondary-light/15 bg-white px-4 py-3 sm:flex-row sm:justify-end sm:px-7">
            <button type="button" onClick={onClose} disabled={guardando} className="rounded-xl px-5 py-3 text-sm font-bold text-yeikar-neutral/55 hover:bg-yeikar-tertiary">Cerrar · borrador guardado</button>
            <button type="submit" disabled={guardando || (confirmacionPendiente && !payloadPendiente) || (!confirmacionPendiente && saldoCOP < 0)} className="rounded-xl bg-yeikar-primary px-6 py-3 text-sm font-black text-yeikar-neutral shadow-sm transition hover:bg-yeikar-primary-dark disabled:cursor-not-allowed disabled:opacity-50">
              {guardando
                ? confirmacionPendiente ? 'Confirmando…' : 'Registrando entrada…'
                : confirmacionPendiente ? `Reintentar · ${formato(totalCOP)}` : entrada ? revisionVisible ? 'Confirmar corrección' : 'Revisar corrección' : `Registrar entrada · ${formato(totalCOP)}`}
            </button>
          </footer>
        </form>
      </div>
    </div>
  );
}
