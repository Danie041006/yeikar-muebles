import React, { useEffect, useState, useCallback } from 'react';
import { productosService, Product, ProductoMaterial, TipoProducto } from '../services/productosService';
import api from '../services/api';

interface Material {
  id: number;
  nombre: string;
  costo_base: number;
  unidad_medida?: { nombre: string; abreviatura: string };
}

interface PrecioSimulado {
  costo_material: number;
  costo_mano_obra: number;
  costo_gastos: number;
  costo_total: number;
  precio_venta: number;
  ganancia_monto: number;
  detalle: { nombre: string; cantidad: number; costo_unitario: number; subtotal: number }[];
}

const ESCALA_LABELS: Record<string, { label: string; color: string }> = {
  FIJO:      { label: 'Fijo',      color: 'bg-slate-100 text-slate-600' },
  LINEAL:    { label: 'Lineal',    color: 'bg-blue-100 text-blue-700' },
  AREA:      { label: 'Por Área',  color: 'bg-violet-100 text-violet-700' },
  ESPACIADO: { label: 'Espaciado', color: 'bg-amber-100 text-amber-700' },
  POR_RANGO: { label: 'Por Rango', color: 'bg-orange-100 text-orange-700' },
  FORMULA:   { label: 'Fórmula',  color: 'bg-green-100 text-green-700' },
};

const fmt = (n: number) =>
  new Intl.NumberFormat('es-CO', { style: 'currency', currency: 'COP', maximumFractionDigits: 0 }).format(n);

export default function Productos() {
  const [productos, setProductos] = useState<Product[]>([]);
  const [tiposProducto, setTiposProducto] = useState<TipoProducto[]>([]);
  const [materiales, setMateriales] = useState<Material[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');

  // Selected product and its recipe
  const [selectedProduct, setSelectedProduct] = useState<Product | null>(null);
  const [receta, setReceta] = useState<ProductoMaterial[]>([]);
  const [recetaLoading, setRecetaLoading] = useState(false);

  // Price simulator
  const [simAncho, setSimAncho] = useState('1.60');
  const [simLargo, setSimLargo] = useState('1.90');
  const [simGanancia, setSimGanancia] = useState('40');
  const [simManoObra, setSimManoObra] = useState('15');
  const [simGastos, setSimGastos] = useState('10');
  const [precioSimulado, setPrecioSimulado] = useState<PrecioSimulado | null>(null);
  const [simLoading, setSimLoading] = useState(false);

  // Modals
  const [showProductModal, setShowProductModal] = useState(false);
  const [productForm, setProductForm] = useState({
    id: null as number | null,
    nombre: '',
    codigo: '',
    tipo_producto_id: '',
    descripcion: '',
    ancho_base: '1.60',
    largo_base: '1.90',
    alto_base: '',
  });

  const [showRecipeModal, setShowRecipeModal] = useState(false);
  const [recipeForm, setRecipeForm] = useState({
    id: null as number | null,
    material_id: '',
    cantidad_base: '',
    tipo_escala: 'FIJO' as ProductoMaterial['tipo_escala'],
    distancia_pauta_cm: '',
    tornillos_por_pieza: '',
    formula_personalizada: '',
    es_fijo_override: false,
    observaciones: '',
  });

  const fetchData = async () => {
    try {
      setLoading(true);
      const [prodData, tiposData, matData] = await Promise.all([
        productosService.getProductos(),
        api.get<TipoProducto[]>('/catalogos/tipo-producto/'),
        api.get<Material[]>('/material/'),
      ]);
      setProductos(prodData);
      setTiposProducto(tiposData.data);
      setMateriales(matData.data);
    } catch (error) {
      console.error('Error loading product data:', error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchData(); }, []);

  const handleOpenRecipe = useCallback(async (product: Product) => {
    setSelectedProduct(product);
    setSimAncho(String(product.ancho_base ?? '1.60'));
    setSimLargo(String(product.largo_base ?? '1.90'));
    setPrecioSimulado(null);
    try {
      setRecetaLoading(true);
      const data = await productosService.getReceta(product.id);
      setReceta(data);
    } catch (error) {
      console.error('Error fetching recipe:', error);
    } finally {
      setRecetaLoading(false);
    }
  }, []);

  const handleSimularPrecio = async () => {
    if (!selectedProduct) return;
    try {
      setSimLoading(true);
      const res = await api.get(`/producto/${selectedProduct.id}/calcular-precio`, {
        params: {
          ancho: parseFloat(simAncho),
          largo: parseFloat(simLargo),
          ganancia: parseFloat(simGanancia),
          iva: 0,
          pct_mano_obra: parseFloat(simManoObra),
          pct_gastos: parseFloat(simGastos),
        },
      });
      
      // Adaptar respuesta del backend al esquema PrecioSimulado del frontend
      const data = res.data;
      const costo_material = data.costo_materiales !== undefined ? data.costo_materiales : 0;
      const costo_mano_obra = data.costo_mano_obra !== undefined ? data.costo_mano_obra : 0;
      const costo_gastos = data.costo_gastos !== undefined ? data.costo_gastos : 0;
      const costo_total = data.costo_total !== undefined ? data.costo_total : 0;
      const precio_venta = data.precio_venta !== undefined ? data.precio_venta : 0;
      
      setPrecioSimulado({
        costo_material,
        costo_mano_obra,
        costo_gastos,
        costo_total,
        precio_venta,
        ganancia_monto: precio_venta - costo_total,
        detalle: (data.materiales || []).map((m: any) => ({
          nombre: m.nombre || m.material_nombre || "",
          cantidad: m.cantidad_calculada || 0,
          costo_unitario: m.costo_unitario || 0,
          subtotal: m.costo_subtotal || 0
        }))
      });
    } catch (error) {
      console.error('Error simulating price:', error);
      alert('Error al calcular el precio. Verifique que el producto tenga materiales en la receta.');
    } finally {
      setSimLoading(false);
    }
  };

  const handleProductSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!productForm.nombre || !productForm.tipo_producto_id) return;
    const body = {
      nombre: productForm.nombre,
      codigo: productForm.codigo || undefined,
      tipo_producto_id: parseInt(productForm.tipo_producto_id),
      descripcion: productForm.descripcion || undefined,
      ancho_base: parseFloat(productForm.ancho_base),
      largo_base: parseFloat(productForm.largo_base),
      alto_base: productForm.alto_base ? parseFloat(productForm.alto_base) : undefined,
    };
    try {
      if (productForm.id) {
        await productosService.actualizarProducto(productForm.id, body);
      } else {
        await productosService.crearProducto(body);
      }
      setShowProductModal(false);
      fetchData();
    } catch (error) {
      console.error('Error saving product:', error);
    }
  };

  const handleDuplicar = async (p: Product) => {
    if (!window.confirm(`¿Duplicar "${p.nombre}"? Se creará una copia con la misma receta de materiales.`)) return;
    try {
      // 1. Crear el producto nuevo con los mismos datos
      const nuevo = await productosService.crearProducto({
        nombre: `${p.nombre} (Copia)`,
        codigo: p.codigo ? `${p.codigo}-COPIA` : undefined,
        tipo_producto_id: p.tipo_producto_id,
        descripcion: p.descripcion,
        ancho_base: p.ancho_base,
        largo_base: p.largo_base,
        alto_base: p.alto_base,
      });
      // 2. Copiar la receta de materiales
      const recetaOriginal = await productosService.getReceta(p.id);
      await Promise.all(
        recetaOriginal.map((item) =>
          productosService.agregarMaterialReceta(nuevo.id, {
            material_id: item.material_id,
            cantidad_base: item.cantidad_base,
            tipo_escala: item.tipo_escala,
            distancia_pauta_cm: item.distancia_pauta_cm,
            tornillos_por_pieza: item.tornillos_por_pieza,
            es_fijo_override: item.es_fijo_override,
            observaciones: item.observaciones,
          })
        )
      );
      alert(`¡Producto duplicado con éxito! Puedes editar "${nuevo.nombre}" desde el listado.`);
      await fetchData();
      handleOpenRecipe(nuevo);
    } catch (error) {
      console.error('Error duplicating product:', error);
      alert('Error al duplicar el producto.');
    }
  };

  const handleRecipeSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedProduct || !recipeForm.material_id || !recipeForm.cantidad_base) return;
    const body = {
      material_id: parseInt(recipeForm.material_id),
      cantidad_base: parseFloat(recipeForm.cantidad_base),
      tipo_escala: recipeForm.tipo_escala,
      distancia_pauta_cm: recipeForm.distancia_pauta_cm ? parseFloat(recipeForm.distancia_pauta_cm) : undefined,
      tornillos_por_pieza: recipeForm.tornillos_por_pieza ? parseInt(recipeForm.tornillos_por_pieza) : undefined,
      formula_personalizada: recipeForm.formula_personalizada || undefined,
      es_fijo_override: recipeForm.es_fijo_override,
      observaciones: recipeForm.observaciones || undefined,
    };
    try {
      if (recipeForm.id) {
        await productosService.actualizarMaterialReceta(recipeForm.id, body);
      } else {
        await productosService.agregarMaterialReceta(selectedProduct.id, body);
      }
      setShowRecipeModal(false);
      handleOpenRecipe(selectedProduct);
    } catch (error) {
      console.error('Error saving recipe item:', error);
    }
  };

  const handleDeleteProduct = async (id: number) => {
    if (!window.confirm('¿Está seguro de eliminar este producto?')) return;
    try {
      await productosService.eliminarProducto(id);
      if (selectedProduct?.id === id) setSelectedProduct(null);
      fetchData();
    } catch (error) {
      console.error('Error deleting product:', error);
    }
  };

  const handleDeleteRecipeItem = async (recetaId: number) => {
    if (!selectedProduct || !window.confirm('¿Remover este material de la receta?')) return;
    try {
      await productosService.eliminarMaterialReceta(recetaId);
      handleOpenRecipe(selectedProduct);
    } catch (error) {
      console.error('Error removing recipe item:', error);
    }
  };

  const filteredProducts = productos.filter((p) => {
    const term = search.toLowerCase();
    return p.nombre.toLowerCase().includes(term) || p.codigo?.toLowerCase().includes(term);
  });

  return (
    <div className="space-y-6">
      {/* ── Header ── */}
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
        <div>
          <h1 className="text-3xl font-black font-headline text-yeikar-secondary tracking-tight">
            Catálogo de Productos 
          </h1>
          <p className="text-yeikar-neutral/60 mt-1 text-sm font-body">
            Define los muebles del catálogo, su receta de materiales y simula precios antes de cotizar.
          </p>
        </div>

        <div className="flex items-center gap-3">
          {/* Search */}
          <div className="relative w-64">
            <input
              type="text"
              placeholder="Buscar producto..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="w-full bg-white border border-yeikar-secondary-light/10 rounded-xl pl-9 pr-4 py-2.5 text-sm focus:outline-none focus:border-yeikar-primary shadow-sm"
            />
            <svg className="absolute left-3 top-3 w-4 h-4 text-yeikar-neutral/40" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
            </svg>
          </div>

          <button
            onClick={() => {
              setProductForm({ id: null, nombre: '', codigo: '', tipo_producto_id: '', descripcion: '', ancho_base: '1.60', largo_base: '1.90', alto_base: '' });
              setShowProductModal(true);
            }}
            className="bg-yeikar-primary hover:bg-yeikar-primary-dark text-yeikar-neutral px-5 py-2.5 rounded-xl font-bold font-headline shadow-sm hover:shadow transition-all flex items-center gap-2 text-sm whitespace-nowrap"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
            </svg>
            Nuevo Mueble
          </button>
        </div>
      </div>

      {/* ── Main Layout ── */}
      <div className="flex flex-col xl:flex-row gap-6">

        {/* ── Products Grid ── */}
        <div className="flex-1 min-w-0">
          {loading ? (
            <div className="flex flex-col items-center justify-center py-24 space-y-4">
              <div className="w-10 h-10 border-4 border-yeikar-primary border-t-transparent rounded-full animate-spin" />
              <p className="text-sm font-mono text-yeikar-neutral/60">Cargando catálogo...</p>
            </div>
          ) : filteredProducts.length === 0 ? (
            <div className="bg-white border border-dashed border-yeikar-secondary-light/15 rounded-3xl p-14 text-center text-yeikar-neutral/40">
              <svg className="w-12 h-12 mx-auto text-yeikar-neutral/20 mb-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4" />
              </svg>
              <p className="font-semibold text-sm">No hay productos en el catálogo.</p>
              <p className="text-xs mt-1">Crea el primer mueble para empezar a cotizar.</p>
            </div>
          ) : (
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
              {filteredProducts.map((p) => (
                <div
                  key={p.id}
                  onClick={() => handleOpenRecipe(p)}
                  className={`relative bg-white border rounded-2xl p-5 cursor-pointer transition-all hover:shadow-md group ${
                    selectedProduct?.id === p.id
                      ? 'border-yeikar-primary shadow-md ring-2 ring-yeikar-primary/20'
                      : 'border-yeikar-secondary-light/10 hover:border-yeikar-primary/40'
                  }`}
                >
                  {/* Selected indicator */}
                  {selectedProduct?.id === p.id && (
                    <div className="absolute top-3 right-3 w-2.5 h-2.5 bg-yeikar-primary rounded-full shadow" />
                  )}

                  {/* Type badge */}
                  <span className="text-[10px] font-black font-headline uppercase tracking-wider text-yeikar-neutral/40">
                    {p.tipo_producto?.nombre || 'Producto'}
                  </span>

                  <h3 className="font-headline font-bold text-yeikar-secondary text-base mt-1 leading-tight">
                    {p.nombre}
                  </h3>

                  {p.codigo && (
                    <p className="text-[11px] font-mono text-yeikar-neutral/50 mt-0.5">#{p.codigo}</p>
                  )}

                  {/* Dimensions */}
                  <div className="mt-3 flex items-center gap-2 flex-wrap">
                    <div className="flex items-center gap-1 bg-yeikar-tertiary/40 px-2 py-1 rounded-lg text-[11px] font-mono font-bold text-yeikar-secondary">
                      <svg className="w-3 h-3 text-yeikar-neutral/50" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 8V4m0 0h4M4 4l5 5m11-1V4m0 0h-4m4 0l-5 5M4 16v4m0 0h4m-4 0l5-5m11 5l-5-5m5 5v-4m0 4h-4" />
                      </svg>
                      {p.ancho_base}m × {p.largo_base}m
                      {p.alto_base ? ` × ${p.alto_base}m` : ''}
                    </div>
                  </div>

                  {p.descripcion && (
                    <p className="mt-3 text-xs text-yeikar-neutral/55 line-clamp-2 leading-relaxed">{p.descripcion}</p>
                  )}

                  {/* Actions row */}
                  <div
                    className="mt-4 pt-3 border-t border-yeikar-secondary-light/5 flex gap-2 opacity-0 group-hover:opacity-100 transition-opacity"
                    onClick={(e) => e.stopPropagation()}
                  >
                    <button
                      onClick={() => handleDuplicar(p)}
                      title="Duplicar con su receta"
                      className="flex-1 flex items-center justify-center gap-1 bg-yeikar-tertiary/60 hover:bg-yeikar-tertiary text-yeikar-secondary px-3 py-1.5 rounded-lg text-[11px] font-bold transition-colors"
                    >
                      <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
                      </svg>
                      Duplicar
                    </button>
                    <button
                      onClick={() => {
                        setProductForm({ id: p.id, nombre: p.nombre, codigo: p.codigo || '', tipo_producto_id: String(p.tipo_producto_id), descripcion: p.descripcion || '', ancho_base: String(p.ancho_base), largo_base: String(p.largo_base), alto_base: p.alto_base ? String(p.alto_base) : '' });
                        setShowProductModal(true);
                      }}
                      className="flex-1 flex items-center justify-center gap-1 bg-yeikar-primary/10 hover:bg-yeikar-primary/20 text-yeikar-primary px-3 py-1.5 rounded-lg text-[11px] font-bold transition-colors"
                    >
                      <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
                      </svg>
                      Editar
                    </button>
                    <button
                      onClick={() => handleDeleteProduct(p.id)}
                      className="flex items-center justify-center bg-red-50 hover:bg-red-100 text-red-500 px-2.5 py-1.5 rounded-lg text-[11px] font-bold transition-colors"
                    >
                      <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                      </svg>
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* ── Right Panel: Recipe + Price Simulator ── */}
        {selectedProduct && (
          <div className="w-full xl:w-[440px] shrink-0 space-y-4">

            {/* Recipe header */}
            <div className="bg-white border border-yeikar-secondary-light/10 rounded-2xl overflow-hidden shadow-sm">
              <div className="bg-gradient-to-r from-yeikar-secondary to-yeikar-secondary-light p-5">
                <span className="text-[10px] font-mono font-bold text-white/50 uppercase tracking-widest">Receta de Materiales</span>
                <h2 className="font-headline font-black text-white text-lg mt-0.5 leading-tight">
                  {selectedProduct.nombre}
                </h2>
                <p className="text-white/60 text-xs font-mono mt-1">
                  Base: {selectedProduct.ancho_base}m × {selectedProduct.largo_base}m
                  {selectedProduct.alto_base ? ` × ${selectedProduct.alto_base}m` : ''}
                </p>
              </div>

              {/* Recipe body */}
              <div className="p-4">
                <div className="flex items-center justify-between mb-3">
                  <span className="text-xs font-bold text-yeikar-neutral/50 uppercase tracking-wider">
                    {receta.length} {receta.length === 1 ? 'material' : 'materiales'} en receta
                  </span>
                  <button
                    onClick={() => {
                      setRecipeForm({ id: null, material_id: '', cantidad_base: '', tipo_escala: 'FIJO', distancia_pauta_cm: '', tornillos_por_pieza: '', formula_personalizada: '', es_fijo_override: false, observaciones: '' });
                      setShowRecipeModal(true);
                    }}
                    className="bg-yeikar-primary text-yeikar-neutral px-3 py-1.5 rounded-lg text-xs font-bold font-headline hover:bg-yeikar-primary-dark transition-colors flex items-center gap-1"
                  >
                    <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
                    </svg>
                    Agregar
                  </button>
                </div>

                {recetaLoading ? (
                  <div className="flex justify-center py-8">
                    <div className="w-6 h-6 border-3 border-yeikar-primary border-t-transparent rounded-full animate-spin" />
                  </div>
                ) : receta.length === 0 ? (
                  <div className="border border-dashed border-yeikar-secondary-light/15 rounded-xl p-8 text-center text-yeikar-neutral/40 text-xs italic">
                    Sin materiales — haz clic en "Agregar" para definir la receta.
                  </div>
                ) : (
                  <div className="space-y-2 max-h-72 overflow-y-auto pr-1">
                    {receta.map((item) => {
                      const mat = materiales.find(m => m.id === item.material_id);
                      const subtotal = (item.cantidad_base || 0) * (mat?.costo_base || item.material?.costo_base || 0);
                      const escala = ESCALA_LABELS[item.tipo_escala] || { label: item.tipo_escala, color: 'bg-gray-100 text-gray-500' };
                      return (
                        <div
                          key={item.id}
                          className="flex items-center gap-3 bg-yeikar-tertiary/20 hover:bg-yeikar-tertiary/40 border border-yeikar-secondary-light/5 rounded-xl px-3.5 py-2.5 transition-colors group"
                        >
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-2">
                              <span className="font-bold text-yeikar-secondary text-xs truncate">
                                {item.material?.nombre || materiales.find(m => m.id === item.material_id)?.nombre || `Material #${item.material_id}`}
                              </span>
                              <span className={`text-[9px] font-black px-1.5 py-0.5 rounded-full shrink-0 ${escala.color}`}>
                                {escala.label}
                              </span>
                            </div>
                            <div className="flex items-center gap-3 mt-0.5 text-[11px] font-mono text-yeikar-neutral/55">
                              <span>×{item.cantidad_base}</span>
                              {subtotal > 0 && <span className="text-yeikar-secondary font-bold">≈ {fmt(subtotal)}</span>}
                            </div>
                          </div>
                          <div className="flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity shrink-0">
                            <button
                              onClick={() => {
                                setRecipeForm({ id: item.id, material_id: String(item.material_id), cantidad_base: String(item.cantidad_base), tipo_escala: item.tipo_escala, distancia_pauta_cm: item.distancia_pauta_cm ? String(item.distancia_pauta_cm) : '', tornillos_por_pieza: item.tornillos_por_pieza ? String(item.tornillos_por_pieza) : '', formula_personalizada: item.formula_personalizada || '', es_fijo_override: item.es_fijo_override || false, observaciones: item.observaciones || '' });
                                setShowRecipeModal(true);
                              }}
                              className="text-yeikar-primary hover:bg-yeikar-primary/10 p-1.5 rounded-lg transition-colors"
                            >
                              <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
                              </svg>
                            </button>
                            <button
                              onClick={() => handleDeleteRecipeItem(item.id)}
                              className="text-red-400 hover:bg-red-50 p-1.5 rounded-lg transition-colors"
                            >
                              <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                              </svg>
                            </button>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            </div>

            {/* Price Simulator */}
            <div className="bg-white border border-yeikar-secondary-light/10 rounded-2xl p-5 shadow-sm space-y-4">
              <div className="flex items-center justify-between">
                <div>
                  <span className="text-[10px] font-mono font-bold text-yeikar-neutral/40 uppercase tracking-widest">Simulador de Precio</span>
                  <p className="text-xs text-yeikar-neutral/55 mt-0.5">Ajusta dimensiones y márgenes para calcular el precio de venta.</p>
                </div>
                <svg className="w-8 h-8 text-yeikar-primary/30" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 7h6m0 10v-3m-3 3h.01M9 17h.01M9 11h.01M12 11h.01M15 11h.01M4 19h16a2 2 0 002-2V7a2 2 0 00-2-2H4a2 2 0 00-2 2v10a2 2 0 002 2z" />
                </svg>
              </div>

              <div className="grid grid-cols-2 gap-3">
                {[
                  { label: 'Ancho (m)', value: simAncho, setter: setSimAncho },
                  { label: 'Largo (m)', value: simLargo, setter: setSimLargo },
                  { label: '% Ganancia', value: simGanancia, setter: setSimGanancia },
                  { label: '% Mano de Obra', value: simManoObra, setter: setSimManoObra },
                  { label: '% Gastos Ind.', value: simGastos, setter: setSimGastos },
                ].map(({ label, value, setter }) => (
                  <div key={label}>
                    <label className="text-[10px] font-bold text-yeikar-neutral/50 uppercase block mb-1">{label}</label>
                    <input
                      type="number"
                      step="0.1"
                      value={value}
                      onChange={(e) => setter(e.target.value)}
                      className="w-full bg-yeikar-tertiary/30 border border-yeikar-secondary-light/10 rounded-lg px-3 py-2 text-sm font-mono focus:outline-none focus:border-yeikar-primary"
                    />
                  </div>
                ))}
              </div>

              <button
                onClick={handleSimularPrecio}
                disabled={simLoading || receta.length === 0}
                className="w-full bg-yeikar-secondary hover:bg-yeikar-secondary-light text-white py-2.5 rounded-xl text-sm font-bold font-headline transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
              >
                {simLoading ? (
                  <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                ) : (
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
                  </svg>
                )}
                Calcular Precio
              </button>

              {/* Results */}
              {precioSimulado && (
                <div className="space-y-3 animate-fade-in">
                  <div className="space-y-1.5 text-xs font-mono">
                    {[
                      { label: 'Costo Materiales', value: precioSimulado.costo_material, color: 'text-yeikar-neutral/70' },
                      { label: 'Mano de Obra', value: precioSimulado.costo_mano_obra, color: 'text-yeikar-neutral/70' },
                      { label: 'Gastos Indirectos', value: precioSimulado.costo_gastos, color: 'text-yeikar-neutral/70' },
                    ].map(({ label, value, color }) => (
                      <div key={label} className="flex justify-between">
                        <span className={color}>{label}</span>
                        <span className="font-bold text-yeikar-secondary">{fmt(value)}</span>
                      </div>
                    ))}
                    <div className="flex justify-between border-t border-yeikar-secondary-light/10 pt-1.5">
                      <span className="text-yeikar-neutral/60">Costo Total</span>
                      <span className="font-black text-yeikar-secondary">{fmt(precioSimulado.costo_total)}</span>
                    </div>
                    <div className="flex justify-between text-green-600">
                      <span>Ganancia ({simGanancia}%)</span>
                      <span className="font-bold">+ {fmt(precioSimulado.ganancia_monto)}</span>
                    </div>
                  </div>

                  {/* Price highlight */}
                  <div className="bg-gradient-to-r from-yeikar-primary to-yeikar-primary-dark rounded-xl p-4 text-center">
                    <span className="text-[10px] font-black font-mono text-yeikar-neutral/60 uppercase tracking-widest block">Precio de Venta Sugerido</span>
                    <span className="text-2xl font-black font-headline text-yeikar-secondary mt-1 block">
                      {fmt(precioSimulado.precio_venta)}
                    </span>
                    <span className="text-[11px] text-yeikar-secondary/60 font-mono">
                      Para {simAncho}m × {simLargo}m
                    </span>
                  </div>
                </div>
              )}
            </div>
          </div>
        )}
      </div>

      {/* ═══════════════════════════════════════════════════════════ */}
      {/* Product Modal */}
      {/* ═══════════════════════════════════════════════════════════ */}
      {showProductModal && (
        <div className="fixed inset-0 bg-yeikar-secondary/60 backdrop-blur-sm flex items-center justify-center p-4 z-50">
          <div className="bg-white rounded-3xl shadow-xl border border-yeikar-secondary-light/10 max-w-lg w-full p-6 space-y-5">
            <div>
              <h3 className="text-xl font-headline font-black text-yeikar-secondary">
                {productForm.id ? 'Editar Mueble' : 'Registrar Nuevo Mueble 🛋️'}
              </h3>
              <p className="text-xs text-yeikar-neutral/50 mt-1">
                {productForm.id ? 'Modifica los datos del producto.' : 'Define el mueble base. Luego puedes agregarle su receta de materiales.'}
              </p>
            </div>

            <form onSubmit={handleProductSubmit} className="space-y-4">
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-bold text-yeikar-neutral/55 mb-1">Código (opcional)</label>
                  <input
                    type="text"
                    placeholder="SOF-001"
                    value={productForm.codigo}
                    onChange={(e) => setProductForm({ ...productForm, codigo: e.target.value })}
                    className="w-full bg-yeikar-tertiary/30 border border-yeikar-secondary-light/10 rounded-xl p-2.5 text-sm font-mono focus:outline-none focus:border-yeikar-primary"
                  />
                </div>
                <div>
                  <label className="block text-xs font-bold text-yeikar-neutral/55 mb-1">Tipo de Producto *</label>
                  <select
                    required
                    value={productForm.tipo_producto_id}
                    onChange={(e) => setProductForm({ ...productForm, tipo_producto_id: e.target.value })}
                    className="w-full bg-yeikar-tertiary/30 border border-yeikar-secondary-light/10 rounded-xl p-2.5 text-sm focus:outline-none focus:border-yeikar-primary"
                  >
                    <option value="">Selecciona...</option>
                    {tiposProducto.map((t) => (
                      <option key={t.id} value={t.id}>{t.nombre}</option>
                    ))}
                  </select>
                </div>
              </div>

              <div>
                <label className="block text-xs font-bold text-yeikar-neutral/55 mb-1">Nombre del Mueble *</label>
                <input
                  type="text"
                  required
                  placeholder="Ej: Sofá 3 Puestos Classic, Cama Ref. Pinterest jul-2025..."
                  value={productForm.nombre}
                  onChange={(e) => setProductForm({ ...productForm, nombre: e.target.value })}
                  className="w-full bg-yeikar-tertiary/30 border border-yeikar-secondary-light/10 rounded-xl p-2.5 text-sm focus:outline-none focus:border-yeikar-primary"
                />
              </div>

              <div>
                <label className="block text-xs font-bold text-yeikar-neutral/55 mb-2">
                  Dimensiones Base (referencia para escalar la receta)
                </label>
                <div className="grid grid-cols-3 gap-3">
                  {[
                    { label: 'Ancho (m)', key: 'ancho_base', req: true },
                    { label: 'Largo (m)', key: 'largo_base', req: true },
                    { label: 'Alto (m)', key: 'alto_base', req: false },
                  ].map(({ label, key, req }) => (
                    <div key={key}>
                      <label className="block text-[10px] text-yeikar-neutral/40 mb-1">{label}{req ? ' *' : ''}</label>
                      <input
                        type="number"
                        step="0.01"
                        required={req}
                        placeholder={req ? '0.00' : 'Opc.'}
                        value={productForm[key as keyof typeof productForm] as string}
                        onChange={(e) => setProductForm({ ...productForm, [key]: e.target.value })}
                        className="w-full bg-yeikar-tertiary/30 border border-yeikar-secondary-light/10 rounded-xl p-2.5 text-sm font-mono focus:outline-none focus:border-yeikar-primary"
                      />
                    </div>
                  ))}
                </div>
              </div>

              <div>
                <label className="block text-xs font-bold text-yeikar-neutral/55 mb-1">Descripción</label>
                <textarea
                  rows={2}
                  placeholder="Detalles, referencias, notas de producción..."
                  value={productForm.descripcion}
                  onChange={(e) => setProductForm({ ...productForm, descripcion: e.target.value })}
                  className="w-full bg-yeikar-tertiary/30 border border-yeikar-secondary-light/10 rounded-xl p-2.5 text-sm focus:outline-none focus:border-yeikar-primary resize-none"
                />
              </div>

              <div className="flex justify-end gap-2 pt-2">
                <button type="button" onClick={() => setShowProductModal(false)} className="px-4 py-2 rounded-xl text-sm font-bold text-yeikar-neutral/60 hover:bg-yeikar-tertiary transition-colors">
                  Cancelar
                </button>
                <button type="submit" className="bg-yeikar-primary text-yeikar-neutral px-5 py-2 rounded-xl text-sm font-bold shadow-sm hover:shadow transition-all">
                  {productForm.id ? 'Guardar Cambios' : 'Crear Mueble 🛋️'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* ═══════════════════════════════════════════════════════════ */}
      {/* Recipe Modal */}
      {/* ═══════════════════════════════════════════════════════════ */}
      {showRecipeModal && (
        <div className="fixed inset-0 bg-yeikar-secondary/60 backdrop-blur-sm flex items-center justify-center p-4 z-50">
          <div className="bg-white rounded-3xl shadow-xl border border-yeikar-secondary-light/10 max-w-md w-full p-6 space-y-4">
            <div>
              <h3 className="text-xl font-headline font-black text-yeikar-secondary">
                {recipeForm.id ? 'Editar Material' : 'Agregar Material a Receta'}
              </h3>
              <p className="text-xs text-yeikar-neutral/50 mt-1">
                Define cuánto de este material usa el producto y cómo escala con las dimensiones.
              </p>
            </div>

            <form onSubmit={handleRecipeSubmit} className="space-y-4">
              <div>
                <label className="block text-xs font-bold text-yeikar-neutral/55 mb-1">Material del Inventario *</label>
                <select
                  required
                  value={recipeForm.material_id}
                  onChange={(e) => setRecipeForm({ ...recipeForm, material_id: e.target.value })}
                  className="w-full bg-yeikar-tertiary/30 border border-yeikar-secondary-light/10 rounded-xl p-2.5 text-sm focus:outline-none focus:border-yeikar-primary"
                >
                  <option value="">Selecciona material...</option>
                  {materiales.map((m) => (
                    <option key={m.id} value={m.id}>
                      {m.nombre} — {fmt(m.costo_base)} / {m.unidad_medida?.abreviatura || 'und'}
                    </option>
                  ))}
                </select>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-bold text-yeikar-neutral/55 mb-1">Cantidad Base *</label>
                  <input
                    type="number"
                    step="0.001"
                    required
                    placeholder="Ej: 5"
                    value={recipeForm.cantidad_base}
                    onChange={(e) => setRecipeForm({ ...recipeForm, cantidad_base: e.target.value })}
                    className="w-full bg-yeikar-tertiary/30 border border-yeikar-secondary-light/10 rounded-xl p-2.5 text-sm font-mono focus:outline-none focus:border-yeikar-primary"
                  />
                </div>

                <div>
                  <label className="block text-xs font-bold text-yeikar-neutral/55 mb-1">Tipo de Escala *</label>
                  <select
                    value={recipeForm.tipo_escala}
                    onChange={(e) => setRecipeForm({ ...recipeForm, tipo_escala: e.target.value as ProductoMaterial['tipo_escala'] })}
                    className="w-full bg-yeikar-tertiary/30 border border-yeikar-secondary-light/10 rounded-xl p-2.5 text-sm focus:outline-none focus:border-yeikar-primary"
                  >
                    <option value="FIJO">FIJO — siempre la misma cantidad</option>
                    <option value="LINEAL">LINEAL — escala con el largo</option>
                    <option value="AREA">ÁREA — escala con ancho×largo</option>
                    <option value="ESPACIADO">ESPACIADO — cada X cm</option>
                    <option value="POR_RANGO">POR RANGO — saltos discretos</option>
                    <option value="FORMULA">FÓRMULA — expresión personalizada</option>
                  </select>
                </div>
              </div>

              {/* Extra fields based on scale type */}
              {recipeForm.tipo_escala === 'ESPACIADO' && (
                <div className="grid grid-cols-2 gap-3 bg-amber-50/50 p-3 rounded-xl border border-amber-100">
                  <div>
                    <label className="block text-[10px] font-bold text-yeikar-neutral/50 mb-1">Distancia pauta (cm)</label>
                    <input type="number" step="0.1" value={recipeForm.distancia_pauta_cm} onChange={(e) => setRecipeForm({ ...recipeForm, distancia_pauta_cm: e.target.value })} className="w-full bg-white border border-amber-200 rounded-lg p-2 text-sm font-mono focus:outline-none" />
                  </div>
                  <div>
                    <label className="block text-[10px] font-bold text-yeikar-neutral/50 mb-1">Tornillos/pieza</label>
                    <input type="number" value={recipeForm.tornillos_por_pieza} onChange={(e) => setRecipeForm({ ...recipeForm, tornillos_por_pieza: e.target.value })} className="w-full bg-white border border-amber-200 rounded-lg p-2 text-sm font-mono focus:outline-none" />
                  </div>
                </div>
              )}

              {recipeForm.tipo_escala === 'FORMULA' && (
                <div className="bg-green-50/50 p-3 rounded-xl border border-green-100">
                  <label className="block text-[10px] font-bold text-yeikar-neutral/50 mb-1">Fórmula personalizada</label>
                  <input
                    type="text"
                    placeholder="Ej: nuevo_ancho * nuevo_largo * 1.2"
                    value={recipeForm.formula_personalizada}
                    onChange={(e) => setRecipeForm({ ...recipeForm, formula_personalizada: e.target.value })}
                    className="w-full bg-white border border-green-200 rounded-lg p-2 text-sm font-mono focus:outline-none"
                  />
                </div>
              )}

              <div>
                <label className="block text-xs font-bold text-yeikar-neutral/55 mb-1">Observaciones</label>
                <input
                  type="text"
                  placeholder="Notas sobre este material en la receta..."
                  value={recipeForm.observaciones}
                  onChange={(e) => setRecipeForm({ ...recipeForm, observaciones: e.target.value })}
                  className="w-full bg-yeikar-tertiary/30 border border-yeikar-secondary-light/10 rounded-xl p-2.5 text-sm focus:outline-none focus:border-yeikar-primary"
                />
              </div>

              <div className="flex justify-end gap-2 pt-2">
                <button type="button" onClick={() => setShowRecipeModal(false)} className="px-4 py-2 rounded-xl text-sm font-bold text-yeikar-neutral/60 hover:bg-yeikar-tertiary transition-colors">
                  Cancelar
                </button>
                <button type="submit" className="bg-yeikar-secondary text-white px-5 py-2 rounded-xl text-sm font-bold shadow-sm hover:shadow transition-all">
                  {recipeForm.id ? 'Guardar' : 'Agregar Material'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
