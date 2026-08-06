import React, { useEffect, useState, useCallback } from 'react';
import { inventarioService, InventarioItem, AlertaStock, MovimientoResponse, ProductoInventarioItem, AlertaStockProducto, MovimientoProductoResponse } from '../services/inventarioService';
import { productosService } from '../services/productosService';
import api from '../services/api';

interface Ubicacion {
  id: number;
  nombre: string;
}

interface Material {
  id: number;
  nombre: string;
  unidad_medida?: {
    abreviatura: string;
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
}

type Tab = 'insumos' | 'productos';

export default function Inventario() {
  interface UnidadMedida {
    id: number;
    nombre: string;
    abreviatura: string;
  }

  const [tab, setTab] = useState<Tab>('insumos');

  // ---- Estado compartido ----
  const [ubicaciones, setUbicaciones] = useState<Ubicacion[]>([]);
  const [unidades, setUnidades] = useState<UnidadMedida[]>([]);
  const [loading, setLoading] = useState(true);

  // ---- Insumos ----
  const [inventario, setInventario] = useState<InventarioItem[]>([]);
  const [alertas, setAlertas] = useState<AlertaStock[]>([]);
  const [materiales, setMateriales] = useState<Material[]>([]);
  const [search, setSearch] = useState('');
  const [selectedMaterialId, setSelectedMaterialId] = useState<number | null>(null);
  const [selectedMaterialNombre, setSelectedMaterialNombre] = useState<string>('');
  const [kardex, setKardex] = useState<MovimientoResponse[]>([]);
  const [loadingKardex, setLoadingKardex] = useState(false);

  // ---- Productos (terminados / reventa) ----
  const [invProductos, setInvProductos] = useState<ProductoInventarioItem[]>([]);
  const [alertasProductos, setAlertasProductos] = useState<AlertaStockProducto[]>([]);
  const [productos, setProductos] = useState<Product[]>([]);
  const [searchProducto, setSearchProducto] = useState('');
  const [selectedProductoId, setSelectedProductoId] = useState<number | null>(null);
  const [selectedProductoNombre, setSelectedProductoNombre] = useState<string>('');
  const [kardexProducto, setKardexProducto] = useState<MovimientoProductoResponse[]>([]);
  const [loadingKardexProducto, setLoadingKardexProducto] = useState(false);

  // Modal State (insumos)
  const [showMoveModal, setShowMoveModal] = useState(false);
  const [newMovement, setNewMovement] = useState({
    material_id: '',
    ubicacion_id: '',
    tipo: 'ENTRADA',
    cantidad: '',
    observaciones: '',
  });

  const [showMaterialModal, setShowMaterialModal] = useState(false);
  const [newMaterial, setNewMaterial] = useState({
    nombre: '',
    costo_base: '',
    unidad_medida_id: '',
    stock_minimo: '8',
  });

  // Modal State (productos)
  const [showMoveProductoModal, setShowMoveProductoModal] = useState(false);
  const [newMovementProducto, setNewMovementProducto] = useState({
    producto_id: '',
    ubicacion_id: '',
    tipo: 'ENTRADA',
    cantidad: '',
    costo_unitario: '',
    observaciones: '',
  });

  const fetchData = useCallback(async () => {
    try {
      setLoading(true);
      const [ubiData, uniData] = await Promise.all([
        api.get<Ubicacion[]>('/catalogos/ubicacion/'),
        api.get<UnidadMedida[]>('/catalogos/unidad-medida/'),
      ]);
      setUbicaciones(ubiData.data);
      setUnidades(uniData.data);
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
      alert(error.response?.data?.detail || 'Error al crear el insumo.');
    }
  };

  const handleOpenKardex = async (materialId: number, nombre: string) => {
    setSelectedMaterialId(materialId);
    setSelectedMaterialNombre(nombre);
    try {
      setLoadingKardex(true);
      const data = await inventarioService.getKardex(materialId);
      setKardex(data);
    } catch (error) {
      console.error('Error fetching kardex:', error);
    } finally {
      setLoadingKardex(false);
    }
  };

  const handleRegisterMovement = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newMovement.material_id || !newMovement.ubicacion_id || !newMovement.cantidad) return;

    try {
      await inventarioService.crearMovimiento({
        material_id: parseInt(newMovement.material_id),
        ubicacion_id: parseInt(newMovement.ubicacion_id),
        tipo: newMovement.tipo as any,
        cantidad: parseFloat(newMovement.cantidad),
        observaciones: newMovement.observaciones || undefined,
      });

      setShowMoveModal(false);
      setNewMovement({ material_id: '', ubicacion_id: '', tipo: 'ENTRADA', cantidad: '', observaciones: '' });
      fetchInsumos();
      if (selectedMaterialId && selectedMaterialId === parseInt(newMovement.material_id)) {
        handleOpenKardex(selectedMaterialId, selectedMaterialNombre);
      }
    } catch (error: any) {
      alert(error.response?.data?.detail || 'Error al registrar el movimiento.');
    }
  };

  const handleOpenKardexProducto = async (productoId: number, nombre: string) => {
    setSelectedProductoId(productoId);
    setSelectedProductoNombre(nombre);
    try {
      setLoadingKardexProducto(true);
      const data = await inventarioService.getKardexProducto(productoId);
      setKardexProducto(data);
    } catch (error) {
      console.error('Error fetching product kardex:', error);
    } finally {
      setLoadingKardexProducto(false);
    }
  };

  const handleRegisterMovementProducto = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newMovementProducto.producto_id || !newMovementProducto.ubicacion_id || !newMovementProducto.cantidad) return;

    try {
      await inventarioService.crearMovimientoProducto({
        producto_id: parseInt(newMovementProducto.producto_id),
        ubicacion_id: parseInt(newMovementProducto.ubicacion_id),
        tipo: newMovementProducto.tipo as any,
        cantidad: parseFloat(newMovementProducto.cantidad),
        costo_unitario: newMovementProducto.costo_unitario ? parseFloat(newMovementProducto.costo_unitario) : undefined,
        observaciones: newMovementProducto.observaciones || undefined,
      });

      setShowMoveProductoModal(false);
      setNewMovementProducto({ producto_id: '', ubicacion_id: '', tipo: 'ENTRADA', cantidad: '', costo_unitario: '', observaciones: '' });
      fetchProductos();
      if (selectedProductoId && selectedProductoId === parseInt(newMovementProducto.producto_id)) {
        handleOpenKardexProducto(selectedProductoId, selectedProductoNombre);
      }
    } catch (error: any) {
      alert(error.response?.data?.detail || 'Error al registrar el movimiento.');
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

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
        <div>
          <h1 className="text-3xl font-black font-headline text-yeikar-neutral tracking-tight">
            Inventario
          </h1>
          <p className="text-yeikar-neutral/60 mt-1">
            Controla existencias de insumos y de productos terminados / de reventa, con alertas de stock crítico.
          </p>
        </div>

        <div className="flex items-center gap-3">
          {tab === 'insumos' ? (
            <>
              <button
                onClick={() => setShowMaterialModal(true)}
                className="bg-emerald-600 hover:bg-emerald-700 text-white px-5 py-2.5 rounded-xl font-bold font-headline shadow-sm hover:shadow transition-all flex items-center gap-2 text-sm"
              >
                ➕ Nuevo Material
              </button>
              <button
                onClick={() => setShowMoveModal(true)}
                className="bg-yeikar-primary hover:bg-yeikar-primary-dark text-yeikar-neutral px-5 py-2.5 rounded-xl font-bold font-headline shadow-sm hover:shadow transition-all flex items-center gap-2 text-sm"
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 7h12m0 0l-4-4m4 4l-4 4m0 6H4m0 0l4 4m-4-4l4-4" />
                </svg>
                Nuevo Movimiento
              </button>
            </>
          ) : (
            <button
              onClick={() => setShowMoveProductoModal(true)}
              className="bg-yeikar-primary hover:bg-yeikar-primary-dark text-yeikar-neutral px-5 py-2.5 rounded-xl font-bold font-headline shadow-sm hover:shadow transition-all flex items-center gap-2 text-sm"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 7h12m0 0l-4-4m4 4l-4 4m0 6H4m0 0l4 4m-4-4l4-4" />
              </svg>
              Nuevo Movimiento de Producto
            </button>
          )}
        </div>
      </div>

      {/* Tabs */}
      <div className="flex gap-2 border-b border-yeikar-secondary-light/10">
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
          Productos (Terminados / Reventa)
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
            {tab === 'insumos' ? materiales.length : productos.length}
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
            <div className="relative w-72">
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
            <div className="overflow-x-auto">
              <table className="w-full text-left border-collapse">
                <thead>
                  <tr className="bg-yeikar-tertiary/20 text-yeikar-secondary font-headline font-bold text-xs uppercase tracking-wider">
                    <th className="p-4 border-b border-yeikar-secondary-light/5">Material</th>
                    <th className="p-4 border-b border-yeikar-secondary-light/5">Ubicación</th>
                    <th className="p-4 border-b border-yeikar-secondary-light/5">Stock Actual</th>
                    <th className="p-4 border-b border-yeikar-secondary-light/5">Stock Mín.</th>
                    <th className="p-4 border-b border-yeikar-secondary-light/5">Unidad</th>
                    <th className="p-4 border-b border-yeikar-secondary-light/5">Precio Unitario</th>
                    <th className="p-4 border-b border-yeikar-secondary-light/5 text-right">Acciones</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-yeikar-secondary-light/5 text-sm">
                  {filteredInv.length === 0 ? (
                    <tr>
                      <td colSpan={7} className="p-8 text-center text-yeikar-neutral/40 italic">
                        {search ? `Sin resultados para "${search}"` : 'No hay materiales registrados. Haz clic en ➕ Nuevo Material para comenzar.'}
                      </td>
                    </tr>
                  ) : (
                    filteredInv.map((mat) => {
                      const stockItem = stockMap.get(mat.id);
                      const tieneStock = !!stockItem;
                      const cantidad = tieneStock ? parseFloat(stockItem!.cantidad.toString()) : 0;
                      const minimo = mat.stock_minimo ?? 8;
                      const isLowStock = cantidad <= minimo;
                      return (
                        <tr
                          key={mat.id}
                          className={`hover:bg-yeikar-tertiary/25 transition-colors cursor-pointer ${
                            selectedMaterialId === mat.id ? 'bg-yeikar-primary/5' : ''
                          }`}
                          onClick={() => handleOpenKardex(mat.id, mat.nombre)}
                        >
                          <td className="p-4 font-semibold text-yeikar-secondary">{mat.nombre}</td>
                          <td className="p-4 text-yeikar-neutral/75">
                            {stockItem?.ubicacion_nombre || <span className="text-yeikar-neutral/30 italic text-xs">Sin stock</span>}
                          </td>
                          <td className="p-4 font-mono font-bold">
                            <span
                              className={`px-2.5 py-0.5 rounded-full text-xs font-bold ${
                                !tieneStock
                                  ? 'bg-red-50 text-red-700 border border-red-200'
                                  : isLowStock
                                  ? 'bg-red-50 text-red-700 border border-red-200'
                                  : 'bg-green-50 text-green-700 border border-green-200'
                              }`}
                            >
                              {tieneStock ? cantidad.toLocaleString('es-ES') : '0'}
                            </span>
                          </td>
                          <td className="p-4 font-mono text-xs text-yeikar-neutral/60">
                            {minimo.toLocaleString('es-ES')}
                          </td>
                          <td className="p-4 font-mono text-xs text-yeikar-neutral/60">
                            {mat.unidad_medida?.abreviatura || 'Unid'}
                          </td>
                          <td className="p-4 font-mono text-xs text-yeikar-neutral/60">
                            {mat.costo_base > 0 ? mat.costo_base.toLocaleString('es-ES') : <span className="text-yeikar-neutral/30 italic">Sin precio</span>}
                          </td>
                          <td className="p-4 text-right">
                            <button
                              onClick={(e) => {
                                e.stopPropagation();
                                handleOpenKardex(mat.id, mat.nombre);
                              }}
                              className="text-yeikar-primary hover:text-yeikar-primary-dark font-bold font-headline text-xs bg-yeikar-primary/10 hover:bg-yeikar-primary/20 px-3 py-1.5 rounded-lg transition-colors"
                            >
                              Ver Movimientos
                            </button>
                          </td>
                        </tr>
                      );
                    })
                  )}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left border-collapse">
                <thead>
                  <tr className="bg-yeikar-tertiary/20 text-yeikar-secondary font-headline font-bold text-xs uppercase tracking-wider">
                    <th className="p-4 border-b border-yeikar-secondary-light/5">Producto</th>
                    <th className="p-4 border-b border-yeikar-secondary-light/5">Código</th>
                    <th className="p-4 border-b border-yeikar-secondary-light/5">Ubicación</th>
                    <th className="p-4 border-b border-yeikar-secondary-light/5">Stock Actual</th>
                    <th className="p-4 border-b border-yeikar-secondary-light/5">Stock Mín.</th>
                    <th className="p-4 border-b border-yeikar-secondary-light/5">Último Precio</th>
                    <th className="p-4 border-b border-yeikar-secondary-light/5 text-right">Acciones</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-yeikar-secondary-light/5 text-sm">
                  {filteredProductos.length === 0 ? (
                    <tr>
                      <td colSpan={7} className="p-8 text-center text-yeikar-neutral/40 italic">
                        {searchProducto ? `Sin resultados para "${searchProducto}"` : 'No hay productos de reventa (colchones, neveras, etc.). Marca un producto como "Reventa" en Productos o usa "Nuevo Movimiento de Producto".'}
                      </td>
                    </tr>
                  ) : (
                    filteredProductos.map((p) => {
                      const stockItem = stockMapProducto.get(p.id);
                      const tieneStock = !!stockItem;
                      const cantidad = tieneStock ? parseFloat(stockItem!.cantidad.toString()) : 0;
                      const minimo = p.stock_minimo ?? 8;
                      const isLowStock = cantidad <= minimo;
                      return (
                        <tr
                          key={p.id}
                          className={`hover:bg-yeikar-tertiary/25 transition-colors cursor-pointer ${
                            selectedProductoId === p.id ? 'bg-yeikar-primary/5' : ''
                          }`}
                          onClick={() => handleOpenKardexProducto(p.id, p.nombre)}
                        >
                          <td className="p-4 font-semibold text-yeikar-secondary">{p.nombre}</td>
                          <td className="p-4 font-mono text-xs text-yeikar-neutral/60">{p.codigo || '—'}</td>
                          <td className="p-4 text-yeikar-neutral/75">
                            {stockItem?.ubicacion_nombre || <span className="text-yeikar-neutral/30 italic text-xs">Sin stock</span>}
                          </td>
                          <td className="p-4 font-mono font-bold">
                            <span
                              className={`px-2.5 py-0.5 rounded-full text-xs font-bold ${
                                !tieneStock || isLowStock
                                  ? 'bg-red-50 text-red-700 border border-red-200'
                                  : 'bg-green-50 text-green-700 border border-green-200'
                              }`}
                            >
                              {tieneStock ? cantidad.toLocaleString('es-ES') : '0'}
                            </span>
                          </td>
                          <td className="p-4 font-mono text-xs text-yeikar-neutral/60">
                            {minimo.toLocaleString('es-ES')}
                          </td>
                          <td className="p-4 font-mono text-xs text-yeikar-neutral/60">
                            {stockItem?.costo_promedio ? `$${Number(stockItem.costo_promedio).toLocaleString('es-ES')}` : <span className="text-yeikar-neutral/30 italic">—</span>}
                          </td>
                          <td className="p-4 text-right">
                            <button
                              onClick={(e) => {
                                e.stopPropagation();
                                handleOpenKardexProducto(p.id, p.nombre);
                              }}
                              className="text-yeikar-primary hover:text-yeikar-primary-dark font-bold font-headline text-xs bg-yeikar-primary/10 hover:bg-yeikar-primary/20 px-3 py-1.5 rounded-lg transition-colors"
                            >
                              Ver Movimientos
                            </button>
                          </td>
                        </tr>
                      );
                    })
                  )}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {/* Kardex Sidebar */}
        {tab === 'insumos' && selectedMaterialId && (
          <div className="w-full lg:w-96 bg-white border border-yeikar-secondary-light/10 rounded-3xl p-5 shadow-sm space-y-5 flex flex-col h-[600px] overflow-hidden">
            <div className="flex items-start justify-between border-b border-yeikar-secondary-light/5 pb-3">
              <div>
                <span className="text-[10px] font-mono font-bold text-yeikar-neutral/40">MOVIMIENTOS DE MATERIAL</span>
                <h3 className="font-headline font-black text-yeikar-secondary text-base truncate max-w-[200px]" title={selectedMaterialNombre}>
                  {selectedMaterialNombre}
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

            {loadingKardex ? (
              <div className="flex-1 flex flex-col items-center justify-center space-y-3">
                <div className="w-8 h-8 border-4 border-yeikar-primary border-t-transparent rounded-full animate-spin"></div>
                <p className="text-xs text-yeikar-neutral/50 font-mono">Cargando historial...</p>
              </div>
            ) : (
              <div className="flex-1 overflow-y-auto space-y-3 pr-1">
                {kardex.length === 0 ? (
                  <p className="text-xs text-yeikar-neutral/40 italic text-center py-8">
                    No se registran movimientos para este material.
                  </p>
                ) : (
                  kardex.map((mov) => {
                    const isEntry = mov.tipo === 'ENTRADA' || mov.tipo === 'DEVOLUCION';
                    const isAdjustment = mov.tipo === 'AJUSTE';
                    return (
                      <div key={mov.id} className="bg-yeikar-tertiary/10 border border-yeikar-secondary-light/5 rounded-xl p-3 text-xs space-y-1 relative">
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
        )}

        {tab === 'productos' && selectedProductoId && (
          <div className="w-full lg:w-96 bg-white border border-yeikar-secondary-light/10 rounded-3xl p-5 shadow-sm space-y-5 flex flex-col h-[600px] overflow-hidden">
            <div className="flex items-start justify-between border-b border-yeikar-secondary-light/5 pb-3">
              <div>
                <span className="text-[10px] font-mono font-bold text-yeikar-neutral/40">MOVIMIENTOS DE PRODUCTO</span>
                <h3 className="font-headline font-black text-yeikar-secondary text-base truncate max-w-[200px]" title={selectedProductoNombre}>
                  {selectedProductoNombre}
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

            {loadingKardexProducto ? (
              <div className="flex-1 flex flex-col items-center justify-center space-y-3">
                <div className="w-8 h-8 border-4 border-yeikar-primary border-t-transparent rounded-full animate-spin"></div>
                <p className="text-xs text-yeikar-neutral/50 font-mono">Cargando historial...</p>
              </div>
            ) : (
              <div className="flex-1 overflow-y-auto space-y-3 pr-1">
                {kardexProducto.length === 0 ? (
                  <p className="text-xs text-yeikar-neutral/40 italic text-center py-8">
                    No se registran movimientos para este producto.
                  </p>
                ) : (
                  kardexProducto.map((mov) => {
                    const isEntry = mov.tipo === 'ENTRADA' || mov.tipo === 'DEVOLUCION';
                    const isAdjustment = mov.tipo === 'AJUSTE';
                    return (
                      <div key={mov.id} className="bg-yeikar-tertiary/10 border border-yeikar-secondary-light/5 rounded-xl p-3 text-xs space-y-1 relative">
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
                        {mov.costo_unitario != null && mov.tipo === 'ENTRADA' && (
                          <p className="text-[11px] text-yeikar-neutral/50 mt-0.5">
                            Costo unitario: <span className="font-mono font-semibold">${Number(mov.costo_unitario).toLocaleString('es-ES')}</span>
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
        )}
      </div>

      {/* Register Movement Modal (Insumos) */}
      {showMoveModal && (
        <div className="fixed inset-0 bg-yeikar-secondary/60 backdrop-blur-sm flex items-center justify-center p-4 z-50">
          <div className="bg-white rounded-3xl border border-yeikar-secondary-light/10 shadow-xl max-w-md w-full p-6 space-y-5 relative">
            <div className="flex items-start justify-between border-b border-yeikar-secondary-light/5 pb-3">
              <h2 className="text-xl font-black font-headline text-yeikar-secondary tracking-tight">Registrar Movimiento de Material</h2>
              <button onClick={() => setShowMoveModal(false)} className="p-1 hover:bg-yeikar-tertiary rounded-lg text-yeikar-neutral/40 hover:text-yeikar-neutral/70">
                <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
            <form onSubmit={handleRegisterMovement} className="space-y-4">
              <div className="space-y-1">
                <label className="text-xs font-bold text-yeikar-secondary">Material</label>
                <select required value={newMovement.material_id} onChange={(e) => setNewMovement(prev => ({ ...prev, material_id: e.target.value }))} className="w-full bg-yeikar-tertiary/20 border border-yeikar-secondary-light/10 rounded-xl p-2.5 text-sm text-yeikar-neutral focus:outline-none focus:border-yeikar-primary">
                  <option value="">Seleccione un material</option>
                  {materiales.map((m) => (<option key={m.id} value={m.id}>{m.nombre}</option>))}
                </select>
              </div>
              <div className="space-y-1">
                <label className="text-xs font-bold text-yeikar-secondary">Ubicación / Almacén</label>
                <select required value={newMovement.ubicacion_id} onChange={(e) => setNewMovement(prev => ({ ...prev, ubicacion_id: e.target.value }))} className="w-full bg-yeikar-tertiary/20 border border-yeikar-secondary-light/10 rounded-xl p-2.5 text-sm text-yeikar-neutral focus:outline-none focus:border-yeikar-primary">
                  <option value="">Seleccione una ubicación</option>
                  {ubicaciones.map((u) => (<option key={u.id} value={u.id}>{u.nombre}</option>))}
                </select>
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-1">
                  <label className="text-xs font-bold text-yeikar-secondary">Tipo Movimiento</label>
                  <select value={newMovement.tipo} onChange={(e) => setNewMovement(prev => ({ ...prev, tipo: e.target.value }))} className="w-full bg-yeikar-tertiary/20 border border-yeikar-secondary-light/10 rounded-xl p-2.5 text-sm text-yeikar-neutral focus:outline-none focus:border-yeikar-primary">
                    <option value="ENTRADA">ENTRADA (Compra/Carga)</option>
                    <option value="SALIDA">SALIDA (Consumo/Despacho)</option>
                    <option value="AJUSTE">AJUSTE (Inventario físico)</option>
                    <option value="DAÑO">DAÑO (Mermas)</option>
                    <option value="DEVOLUCION">DEVOLUCION</option>
                  </select>
                </div>
                <div className="space-y-1">
                  <label className="text-xs font-bold text-yeikar-secondary">Cantidad</label>
                  <input type="number" step="0.01" min="0.01" required placeholder="0.00" value={newMovement.cantidad} onChange={(e) => setNewMovement(prev => ({ ...prev, cantidad: e.target.value }))} className="w-full bg-yeikar-tertiary/20 border border-yeikar-secondary-light/10 rounded-xl p-2.5 text-sm text-yeikar-neutral focus:outline-none focus:border-yeikar-primary font-mono" />
                </div>
              </div>
              <div className="space-y-1">
                <label className="text-xs font-bold text-yeikar-secondary">Observaciones</label>
                <textarea rows={2} placeholder="Detalle o referencia del movimiento..." value={newMovement.observaciones} onChange={(e) => setNewMovement(prev => ({ ...prev, observaciones: e.target.value }))} className="w-full bg-yeikar-tertiary/20 border border-yeikar-secondary-light/10 rounded-xl p-2.5 text-sm text-yeikar-neutral focus:outline-none focus:border-yeikar-primary" />
              </div>
              <div className="flex justify-end gap-3 pt-3 border-t border-yeikar-secondary-light/5">
                <button type="button" onClick={() => setShowMoveModal(false)} className="bg-yeikar-tertiary hover:bg-yeikar-secondary-light/15 text-yeikar-secondary px-5 py-2.5 rounded-xl text-sm font-bold font-headline transition-colors">Cancelar</button>
                <button type="submit" className="bg-yeikar-primary hover:bg-yeikar-primary-dark text-yeikar-neutral px-5 py-2.5 rounded-xl text-sm font-bold font-headline transition-colors">Registrar</button>
              </div>
            </form>
          </div>
        </div>
      )}

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
                <select required value={newMaterial.unidad_medida_id} onChange={(e) => setNewMaterial(prev => ({ ...prev, unidad_medida_id: e.target.value }))} className="w-full bg-yeikar-tertiary/20 border border-yeikar-secondary-light/10 rounded-xl px-3 py-2.5 text-sm text-yeikar-neutral focus:outline-none focus:border-yeikar-primary bg-white">
                  <option value="">Seleccionar...</option>
                  {unidades.map((u) => (<option key={u.id} value={u.id}>{u.nombre} ({u.abreviatura})</option>))}
                </select>
              </div>
              <div className="flex gap-3 pt-3 border-t border-yeikar-secondary-light/5">
                <button type="button" onClick={() => setShowMaterialModal(false)} className="flex-1 py-2.5 bg-yeikar-tertiary hover:bg-yeikar-secondary-light/15 text-yeikar-secondary rounded-xl font-bold font-headline text-sm transition-colors">Cancelar</button>
                <button type="submit" className="flex-1 py-2.5 bg-yeikar-primary hover:bg-yeikar-primary-dark text-yeikar-neutral rounded-xl font-bold font-headline text-sm transition-all">Crear Insumo</button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Register Movement Modal (Productos) */}
      {showMoveProductoModal && (
        <div className="fixed inset-0 bg-yeikar-secondary/60 backdrop-blur-sm flex items-center justify-center p-4 z-50">
          <div className="bg-white rounded-3xl border border-yeikar-secondary-light/10 shadow-xl max-w-md w-full p-6 space-y-5 relative">
            <div className="flex items-start justify-between border-b border-yeikar-secondary-light/5 pb-3">
              <h2 className="text-xl font-black font-headline text-yeikar-secondary tracking-tight">Registrar Movimiento de Producto</h2>
              <button onClick={() => setShowMoveProductoModal(false)} className="p-1 hover:bg-yeikar-tertiary rounded-lg text-yeikar-neutral/40 hover:text-yeikar-neutral/70">
                <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
            <form onSubmit={handleRegisterMovementProducto} className="space-y-4">
              <div className="space-y-1">
                <label className="text-xs font-bold text-yeikar-secondary">Producto</label>
                <select required value={newMovementProducto.producto_id} onChange={(e) => setNewMovementProducto(prev => ({ ...prev, producto_id: e.target.value }))} className="w-full bg-yeikar-tertiary/20 border border-yeikar-secondary-light/10 rounded-xl p-2.5 text-sm text-yeikar-neutral focus:outline-none focus:border-yeikar-primary">
                  <option value="">Seleccione un producto</option>
                  {productosReventa.map((p) => (<option key={p.id} value={p.id}>{p.nombre}{p.codigo ? ` (${p.codigo})` : ''}</option>))}
                </select>
              </div>
              <div className="space-y-1">
                <label className="text-xs font-bold text-yeikar-secondary">Ubicación / Almacén</label>
                <select required value={newMovementProducto.ubicacion_id} onChange={(e) => setNewMovementProducto(prev => ({ ...prev, ubicacion_id: e.target.value }))} className="w-full bg-yeikar-tertiary/20 border border-yeikar-secondary-light/10 rounded-xl p-2.5 text-sm text-yeikar-neutral focus:outline-none focus:border-yeikar-primary">
                  <option value="">Seleccione una ubicación</option>
                  {ubicaciones.map((u) => (<option key={u.id} value={u.id}>{u.nombre}</option>))}
                </select>
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-1">
                  <label className="text-xs font-bold text-yeikar-secondary">Tipo Movimiento</label>
                  <select value={newMovementProducto.tipo} onChange={(e) => setNewMovementProducto(prev => ({ ...prev, tipo: e.target.value }))} className="w-full bg-yeikar-tertiary/20 border border-yeikar-secondary-light/10 rounded-xl p-2.5 text-sm text-yeikar-neutral focus:outline-none focus:border-yeikar-primary">
                    <option value="ENTRADA">ENTRADA (Compra/Carga)</option>
                    <option value="SALIDA">SALIDA (Despacho)</option>
                    <option value="AJUSTE">AJUSTE (Inventario físico)</option>
                    <option value="DAÑO">DAÑO (Mermas)</option>
                    <option value="DEVOLUCION">DEVOLUCION</option>
                  </select>
                </div>
                <div className="space-y-1">
                  <label className="text-xs font-bold text-yeikar-secondary">Cantidad</label>
                  <input type="number" step="0.01" min="0.01" required placeholder="0.00" value={newMovementProducto.cantidad} onChange={(e) => setNewMovementProducto(prev => ({ ...prev, cantidad: e.target.value }))} className="w-full bg-yeikar-tertiary/20 border border-yeikar-secondary-light/10 rounded-xl p-2.5 text-sm text-yeikar-neutral focus:outline-none focus:border-yeikar-primary font-mono" />
                </div>
              </div>
              <div className="space-y-1">
                <label className="text-xs font-bold text-yeikar-secondary">Costo Unitario <span className="text-yeikar-neutral/40 font-normal">(Solo entrada; actualiza el precio al instante)</span></label>
                <input type="number" step="0.01" min="0" placeholder="0.00" value={newMovementProducto.costo_unitario} onChange={(e) => setNewMovementProducto(prev => ({ ...prev, costo_unitario: e.target.value }))} className="w-full bg-yeikar-tertiary/20 border border-yeikar-secondary-light/10 rounded-xl p-2.5 text-sm text-yeikar-neutral focus:outline-none focus:border-yeikar-primary font-mono" />
              </div>
              <div className="space-y-1">
                <label className="text-xs font-bold text-yeikar-secondary">Observaciones</label>
                <textarea rows={2} placeholder="Detalle o referencia del movimiento..." value={newMovementProducto.observaciones} onChange={(e) => setNewMovementProducto(prev => ({ ...prev, observaciones: e.target.value }))} className="w-full bg-yeikar-tertiary/20 border border-yeikar-secondary-light/10 rounded-xl p-2.5 text-sm text-yeikar-neutral focus:outline-none focus:border-yeikar-primary" />
              </div>
              <div className="flex justify-end gap-3 pt-3 border-t border-yeikar-secondary-light/5">
                <button type="button" onClick={() => setShowMoveProductoModal(false)} className="bg-yeikar-tertiary hover:bg-yeikar-secondary-light/15 text-yeikar-secondary px-5 py-2.5 rounded-xl text-sm font-bold font-headline transition-colors">Cancelar</button>
                <button type="submit" className="bg-yeikar-primary hover:bg-yeikar-primary-dark text-yeikar-neutral px-5 py-2.5 rounded-xl text-sm font-bold font-headline transition-colors">Registrar</button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
