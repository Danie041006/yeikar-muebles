import React, { useEffect, useState, useCallback } from 'react';
import { inventarioService, InventarioItem, AlertaStock, MovimientoResponse, ProductoInventarioItem, AlertaStockProducto, MovimientoProductoResponse } from '../services/inventarioService';
import { productosService, type MonedaInfo } from '../services/productosService';
import { subirAdjunto, TIPO_ADJUNTO } from '../services/adjuntosService';
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
}

interface Product {
  id: number;
  nombre: string;
  codigo?: string;
  stock_minimo?: number;
  es_reventa?: boolean;
  moneda_id?: number | null;
  moneda?: MonedaInfo | null;
}

type Tab = 'insumos' | 'productos';

const TIPOS_MOVIMIENTO = ['ENTRADA', 'SALIDA', 'AJUSTE', 'DAÑO', 'DEVOLUCION'];

export default function Inventario() {
  const toast = useToast();
  interface UnidadMedida {
    id: number;
    nombre: string;
    abreviatura: string;
  }

  const [tab, setTab] = useState<Tab>('insumos');

  // ---- Estado compartido ----
  const [ubicaciones, setUbicaciones] = useState<Ubicacion[]>([]);
  const [unidades, setUnidades] = useState<UnidadMedida[]>([]);
  const [monedas, setMonedas] = useState<MonedaInfo[]>([]);
  const [loading, setLoading] = useState(true);

  // ---- Insumos ----
  const [inventario, setInventario] = useState<InventarioItem[]>([]);
  const [alertas, setAlertas] = useState<AlertaStock[]>([]);
  const [materiales, setMateriales] = useState<Material[]>([]);
  const [search, setSearch] = useState('');
  const [selectedMaterialId, setSelectedMaterialId] = useState<number | null>(null);
  const [kardex, setKardex] = useState<MovimientoResponse[]>([]);
  const [loadingKardex, setLoadingKardex] = useState(false);

  // Formulario de movimiento de MATERIAL (dentro del panel)
  const [movMaterial, setMovMaterial] = useState({
    ubicacion_id: '',
    tipo: 'ENTRADA',
    cantidad: '',
    costo_unitario: '',
    observaciones: '',
  });
  const [savingMov, setSavingMov] = useState(false);

  // Edición de insumo (dentro del panel)
  const [editMaterial, setEditMaterial] = useState({ nombre: '', costo_base: '', stock_minimo: '8' });
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
    observaciones: '',
  });
  const [savingMovProd, setSavingMovProd] = useState(false);

  const [showMaterialModal, setShowMaterialModal] = useState(false);
  const [newMaterial, setNewMaterial] = useState({
    nombre: '',
    costo_base: '',
    unidad_medida_id: '',
    stock_minimo: '8',
  });

  // Modal "Nuevo Producto de Reventa"
  const [showProductoModal, setShowProductoModal] = useState(false);
  const [newProducto, setNewProducto] = useState({
    nombre: '',
    codigo: '',
    costo_base: '',
    precio_venta: '',
    stock_minimo: '8',
    cantidad_inicial: '1',
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
      const [ubiData, uniData, monData] = await Promise.all([
        api.get<Ubicacion[]>('/catalogos/ubicacion/'),
        api.get<UnidadMedida[]>('/catalogos/unidad-medida/'),
        api.get<MonedaInfo[]>('/catalogos/moneda/'),
      ]);
      setUbicaciones(ubiData.data);
      setUnidades(uniData.data);
      setMonedas(monData.data.filter(m => m.activo !== false));
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
      const [invData, alertsData, prodData] = await Promise.all([
        inventarioService.getInventarioProductos({ solo_reventa: true }),
        inventarioService.getAlertasProductos(8.0),
        productosService.getProductos(),
      ]);
      setInvProductos(invData);
      setAlertasProductos(alertsData);
      setProductos(prodData);
    } catch (error) {
      console.error('Error fetching product inventory:', error);
    }
  }, []);

  useEffect(() => {
    fetchData();
    fetchInsumos();
    fetchProductos();
  }, [fetchData, fetchInsumos, fetchProductos]);

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
      });

      setShowMaterialModal(false);
      setNewMaterial({ nombre: '', costo_base: '', unidad_medida_id: '', stock_minimo: '8' });
      fetchInsumos();
    } catch (error: any) {
      toast.error(error.response?.data?.detail || 'Error al crear el insumo.');
    }
  };

  // ---- Crear producto de REVENTA (comprado para revender) ----
  const handleCreateProducto = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newProducto.nombre.trim()) return;
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
        precio_costo_base: newProducto.costo_base ? parseFloat(newProducto.costo_base) : undefined,
        precio_venta_base: newProducto.precio_venta ? parseFloat(newProducto.precio_venta) : undefined,
      });
      // Foto de referencia (opcional): se sube y el servidor la optimiza
      if (fotoProducto && creado.id) {
        await subirAdjunto(fotoProducto, TIPO_ADJUNTO.PRODUCTO, creado.id);
        setFotoProducto(null);
        if (fotoProductoPreview) URL.revokeObjectURL(fotoProductoPreview);
        setFotoProductoPreview(null);
      }
      setShowProductoModal(false);
      setNewProducto({ nombre: '', codigo: '', costo_base: '', precio_venta: '', stock_minimo: '8', cantidad_inicial: '1', moneda_id: idMonedaPorDefecto() });

      // Entrada inicial al inventario: la cantidad la decide el usuario
      // (default 1); el costo es opcional.
      const cantInicial = parseFloat(newProducto.cantidad_inicial || '0') || 0;
      if (cantInicial > 0 && creado.id) {
        const ubi = ubicaciones[0];
        if (ubi) {
          await inventarioService.crearMovimientoProducto({
            producto_id: creado.id,
            ubicacion_id: ubi.id,
            tipo: 'ENTRADA',
            cantidad: cantInicial,
            costo_unitario: newProducto.costo_base ? parseFloat(newProducto.costo_base) : undefined,
            observaciones: 'Carga inicial de producto de reventa',
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
    });
    setMovMaterial({ ubicacion_id: '', tipo: 'ENTRADA', cantidad: '', costo_unitario: mat.costo_base ? String(mat.costo_base) : '', observaciones: '' });
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
      });
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
    try {
      setSavingMov(true);
      await inventarioService.crearMovimiento({
        material_id: selectedMaterialId,
        ubicacion_id: parseInt(movMaterial.ubicacion_id),
        tipo: movMaterial.tipo as any,
        cantidad: parseFloat(movMaterial.cantidad),
        costo_unitario: esEntrada && movMaterial.costo_unitario ? parseFloat(movMaterial.costo_unitario) : undefined,
        observaciones: movMaterial.observaciones || undefined,
      });

      setMovMaterial({ ubicacion_id: '', tipo: 'ENTRADA', cantidad: '', costo_unitario: '', observaciones: '' });
      fetchInsumos();
      const mat = materiales.find(m => m.id === selectedMaterialId);
      if (mat) handleOpenMaterial(mat);
    } catch (error: any) {
      toast.error(error.response?.data?.detail || 'Error al registrar el movimiento.');
    } finally {
      setSavingMov(false);
    }
  };

  // ---- Abrir panel de producto ----
  const handleOpenProducto = async (p: Product) => {
    setSelectedProductoId(p.id);
    setMovProducto({ ubicacion_id: '', tipo: 'ENTRADA', cantidad: '', costo_unitario: '', observaciones: '' });
    try {
      setLoadingKardexProducto(true);
      const data = await inventarioService.getKardexProducto(p.id);
      setKardexProducto(data);
    } catch (error) {
      console.error('Error fetching product kardex:', error);
    } finally {
      setLoadingKardexProducto(false);
    }
  };

  // ---- Registrar movimiento de producto (desde el panel) ----
  const handleRegisterMovementProducto = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedProductoId || !movProducto.ubicacion_id || !movProducto.cantidad) return;

    const esEntrada = movProducto.tipo === 'ENTRADA' || movProducto.tipo === 'DEVOLUCION';
    try {
      setSavingMovProd(true);
      await inventarioService.crearMovimientoProducto({
        producto_id: selectedProductoId,
        ubicacion_id: parseInt(movProducto.ubicacion_id),
        tipo: movProducto.tipo as any,
        cantidad: parseFloat(movProducto.cantidad),
        costo_unitario: esEntrada && movProducto.costo_unitario ? parseFloat(movProducto.costo_unitario) : undefined,
        observaciones: movProducto.observaciones || undefined,
      });

      setMovProducto({ ubicacion_id: '', tipo: 'ENTRADA', cantidad: '', costo_unitario: '', observaciones: '' });
      fetchProductos();
      const p = productos.find(x => x.id === selectedProductoId);
      if (p) handleOpenProducto(p);
    } catch (error: any) {
      toast.error(error.response?.data?.detail || 'Error al registrar el movimiento.');
    } finally {
      setSavingMovProd(false);
    }
  };

  // ---- Vistas derivadas ----
  const stockMap = new Map<number, InventarioItem>();
  inventario.forEach(item => {
    if (!stockMap.has(item.material_id)) stockMap.set(item.material_id, item);
  });

  const filteredInv = [...materiales]
    .sort((a, b) => a.nombre.localeCompare(b.nombre, 'es'))
    .filter((mat) => mat.nombre.toLowerCase().includes(search.toLowerCase()));

  const stockMapProducto = new Map<number, ProductoInventarioItem>();
  invProductos.forEach(item => {
    if (!stockMapProducto.has(item.producto_id)) stockMapProducto.set(item.producto_id, item);
  });

  // Productos de REVENTA (colchones, neveras, etc.) — no los muebles fabricados
  const productosReventa = productos.filter(p => p.es_reventa);
  const filteredProductos = [...productosReventa]
    .sort((a, b) => a.nombre.localeCompare(b.nombre, 'es'))
    .filter((p) => p.nombre.toLowerCase().includes(searchProducto.toLowerCase()));

  const materialSeleccionado = materiales.find(m => m.id === selectedMaterialId);
  const productoSeleccionado = productos.find(p => p.id === selectedProductoId);

  const inputCls = "w-full bg-yeikar-tertiary/20 border border-yeikar-secondary-light/10 rounded-xl p-2.5 text-sm text-yeikar-neutral focus:outline-none focus:border-yeikar-primary font-mono";
  const selectCls = "w-full bg-yeikar-tertiary/20 border border-yeikar-secondary-light/10 rounded-xl p-2.5 text-sm text-yeikar-neutral focus:outline-none focus:border-yeikar-primary";

  const stockPill = (tieneStock: boolean, cantidad: number, isLowStock: boolean) => (
    <span
      className={`px-2.5 py-0.5 rounded-full text-xs font-bold whitespace-nowrap ${
        !tieneStock || isLowStock
          ? 'bg-red-50 text-red-700 border border-red-200'
          : 'bg-green-50 text-green-700 border border-green-200'
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

  const insumoColumns: DataColumn<Material>[] = [
    {
      key: 'nombre',
      header: 'Material',
      render: (m) => <span className="font-semibold text-yeikar-secondary">{m.nombre}</span>,
      mobilePrimary: true,
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

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
        <div>
          <h1 className="text-3xl font-black font-headline text-yeikar-neutral tracking-tight">
            Inventario
          </h1>
          <p className="text-yeikar-neutral/60 mt-1">
            Controla existencias de insumos y productos de reventa, con alertas de stock crítico.
          </p>
        </div>

        <div className="flex items-center gap-3">
          {tab === 'insumos' && (
            <button
              onClick={() => setShowMaterialModal(true)}
              className="bg-emerald-600 hover:bg-emerald-700 text-white px-5 py-2.5 rounded-xl font-bold font-headline shadow-sm hover:shadow transition-all flex items-center gap-2 text-sm"
            >
               Nuevo Material
            </button>
          )}
          {tab === 'productos' && (
            <button
              onClick={() => setShowProductoModal(true)}
              className="bg-emerald-600 hover:bg-emerald-700 text-white px-5 py-2.5 rounded-xl font-bold font-headline shadow-sm hover:shadow transition-all flex items-center gap-2 text-sm"
            >
               Nuevo Producto de Reventa
            </button>
          )}
        </div>
      </div>

      {/* Tabs */}
      <div className="flex gap-2 border-b border-yeikar-secondary-light/10 overflow-x-auto scroll-touch whitespace-nowrap">
        <button
          onClick={() => setTab('insumos')}
          className={`px-5 py-2.5 rounded-t-xl font-headline font-bold text-sm transition-colors ${
            tab === 'insumos'
              ? 'bg-yeikar-primary/10 text-yeikar-primary border-b-2 border-yeikar-primary'
              : 'text-yeikar-neutral/50 hover:text-yeikar-neutral'
          }`}
        >
          Insumos (Materiales)
          {alertas.length > 0 && (
            <span className="ml-2 bg-red-500 text-white text-[10px] font-bold px-1.5 py-0.5 rounded-full">{alertas.length}</span>
          )}
        </button>
        <button
          onClick={() => setTab('productos')}
          className={`px-5 py-2.5 rounded-t-xl font-headline font-bold text-sm transition-colors ${
            tab === 'productos'
              ? 'bg-yeikar-primary/10 text-yeikar-primary border-b-2 border-yeikar-primary'
              : 'text-yeikar-neutral/50 hover:text-yeikar-neutral'
          }`}
        >
          Productos de Reventa
          {alertasProductos.length > 0 && (
            <span className="ml-2 bg-red-500 text-white text-[10px] font-bold px-1.5 py-0.5 rounded-full">{alertasProductos.length}</span>
          )}
        </button>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
        <div className="bg-white border border-yeikar-secondary-light/10 rounded-2xl p-5 shadow-sm relative overflow-hidden">
          <div className="absolute top-0 left-0 right-0 h-1 bg-amber-400" />
          <p className="text-xs font-mono uppercase tracking-widest text-yeikar-neutral/50 mb-1">
            {tab === 'insumos' ? 'Materiales Registrados' : 'Productos Registrados'}
          </p>
          <p className="text-3xl font-black font-headline text-yeikar-secondary">
            {tab === 'insumos' ? materiales.length : productosReventa.length}
          </p>
        </div>

        <div className="bg-white border border-yeikar-secondary-light/10 rounded-2xl p-5 shadow-sm relative overflow-hidden">
          <div className="absolute top-0 left-0 right-0 h-1 bg-red-400" />
          <p className="text-xs font-mono uppercase tracking-widest text-yeikar-neutral/50 mb-1">Alertas de Stock Bajo</p>
          <p className="text-3xl font-black font-headline text-red-500">
            {tab === 'insumos' ? alertas.length : alertasProductos.length}
          </p>
        </div>

        <div className="bg-white border border-yeikar-secondary-light/10 rounded-2xl p-5 shadow-sm relative overflow-hidden">
          <div className="absolute top-0 left-0 right-0 h-1 bg-green-400" />
          <p className="text-xs font-mono uppercase tracking-widest text-yeikar-neutral/50 mb-1">Bodegas Activas</p>
          <p className="text-3xl font-black font-headline text-green-600">{ubicaciones.length}</p>
        </div>
      </div>

      {/* Main Layout */}
      <div className="flex flex-col lg:flex-row gap-6">

        <div className="flex-1 bg-white border border-yeikar-secondary-light/10 rounded-3xl shadow-sm overflow-hidden">
          <div className="p-5 border-b border-yeikar-secondary-light/5 flex items-center justify-between">
            <div className="relative w-full sm:w-72">
              <input
                type="text"
                placeholder={tab === 'insumos' ? 'Buscar material...' : 'Buscar producto...'}
                value={tab === 'insumos' ? search : searchProducto}
                onChange={(e) => tab === 'insumos' ? setSearch(e.target.value) : setSearchProducto(e.target.value)}
                className="w-full bg-yeikar-tertiary/30 border border-yeikar-secondary-light/10 rounded-xl pl-10 pr-4 py-2 text-sm text-yeikar-neutral placeholder-yeikar-neutral/40 focus:outline-none focus:border-yeikar-primary"
              />
              <svg className="absolute left-3 top-3 w-4 h-4 text-yeikar-neutral/40" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
              </svg>
            </div>
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
                  <div className="space-y-1">
                    <label className="text-xs font-bold text-yeikar-secondary">Precio Unitario <span className="text-yeikar-neutral/40 font-normal">(Actualiza el precio al instante)</span></label>
                    <input type="number" step="0.01" min="0" placeholder="0.00" value={movMaterial.costo_unitario} onChange={(e) => setMovMaterial(p => ({ ...p, costo_unitario: e.target.value }))} className={inputCls} />
                  </div>
                )}
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
        {tab === 'productos' && selectedProductoId && productoSeleccionado && (
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
                  <div className="space-y-1">
                    <label className="text-xs font-bold text-yeikar-secondary">Precio Unitario <span className="text-yeikar-neutral/40 font-normal">(en {productoSeleccionado?.moneda?.codigo ?? 'COP'} · actualiza el precio al instante)</span></label>
                    <input type="number" step="0.01" min="0" placeholder="0.00" value={movProducto.costo_unitario} onChange={(e) => setMovProducto(p => ({ ...p, costo_unitario: e.target.value }))} className={inputCls} />
                  </div>
                )}
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
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs font-bold text-yeikar-secondary mb-1">Costo de Compra <span className="text-yeikar-neutral/40 font-normal">(Opcional)</span></label>
                  <div className="relative">
                    <span className="absolute left-3 top-1/2 -translate-y-1/2 text-xs font-mono font-bold text-yeikar-neutral/40">{simboloPrecio}</span>
                    <input type="number" min="0" step="0.01" placeholder="0.00" value={newProducto.costo_base} onChange={(e) => setNewProducto(prev => ({ ...prev, costo_base: e.target.value }))} className="w-full pl-8 pr-3 py-2.5 bg-yeikar-tertiary/20 border border-yeikar-secondary-light/10 rounded-xl text-sm text-yeikar-neutral focus:outline-none focus:border-yeikar-primary font-mono" />
                  </div>
                </div>
                <div>
                  <label className="block text-xs font-bold text-yeikar-secondary mb-1">Precio de Venta <span className="text-yeikar-neutral/40 font-normal">(Opcional)</span></label>
                  <div className="relative">
                    <span className="absolute left-3 top-1/2 -translate-y-1/2 text-xs font-mono font-bold text-yeikar-neutral/40">{simboloPrecio}</span>
                    <input type="number" min="0" step="0.01" placeholder="0.00" value={newProducto.precio_venta} onChange={(e) => setNewProducto(prev => ({ ...prev, precio_venta: e.target.value }))} className="w-full pl-8 pr-3 py-2.5 bg-yeikar-tertiary/20 border border-yeikar-secondary-light/10 rounded-xl text-sm text-yeikar-neutral focus:outline-none focus:border-yeikar-primary font-mono" />
                  </div>
                </div>
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
    </div>
  );
}
