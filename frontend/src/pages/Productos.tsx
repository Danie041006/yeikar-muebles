import React, { useEffect, useState, useCallback, useMemo } from 'react';
import { productosService, Product, ProductoMaterial, TipoProducto, SeccionProducto } from '../services/productosService';
import api from '../services/api';
import ConfirmDialog from '../components/ui/ConfirmDialog';
import { SearchSelect, Modal } from '../components/ui';
import { Hammer, Package, Sparkles, Layers, Search, Plus, RefreshCw, Copy, Pencil, Trash2, Tag, ChevronRight, LayoutGrid, X, FileSpreadsheet } from 'lucide-react';
import { useToast } from '../context/ToastContext';
import { useAuth } from '../context/AuthContext';
import EstructuraCostos from '../components/EstructuraCostos';
import { normalizarEstructuraCostos, EstructuraCostos as EstructuraCostosData } from '../utils/estructuraCostos';
import { formatCurrency } from '../utils/format';
import { subirAdjunto, eliminarAdjunto, TIPO_ADJUNTO } from '../services/adjuntosService';

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
  impuesto_porcentaje: number;
  impuestos: number;
  precio_venta: number;
  ganancia_monto: number;
  detalle: { nombre: string; cantidad: number; costo_unitario: number; subtotal: number }[];
  desglose_por_seccion: Record<string, {
    costo_insumos: number;
    costos_produccion: { nombre: string; costo_base: number; porcentaje: number; aporte: number }[];
    total_costos_produccion: number;
    subtotal: number;
    pct_gastos_seccion: number;
    gasto_seccion: number;
    pct_negocio: number;
    costo_negocio: number;
    total_seccion: number;
  }>;
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
  const toast = useToast();
  const { esAdmin } = useAuth();
  const [confirmState, setConfirmState] = useState<{ titulo: string; mensaje: string; accion: () => void } | null>(null);
  const [productos, setProductos] = useState<Product[]>([]);
  const [tiposProducto, setTiposProducto] = useState<TipoProducto[]>([]);
  const [materiales, setMateriales] = useState<Material[]>([]);
  // Material search state
  const [materialSearch, setMaterialSearch] = useState('');
  const [showMaterialDropdown, setShowMaterialDropdown] = useState(false);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');

  // Filtros de navegación por Origen y Subcategorías
  const [tipoOrigenFiltro, setTipoOrigenFiltro] = useState<'TODOS' | 'FABRICADOS' | 'REVENTA'>('TODOS');
  const [subcategoriaFiltro, setSubcategoriaFiltro] = useState<string>('TODAS');

  // Selected product, legacy recipe and structured section recipe
  const [selectedProduct, setSelectedProduct] = useState<Product | null>(null);
  const [receta, setReceta] = useState<ProductoMaterial[]>([]);
  const [secciones, setSecciones] = useState<SeccionProducto[]>([]);
  const [recetaLoading, setRecetaLoading] = useState(false);


  // Price simulator
  const [simAncho, setSimAncho] = useState('1.60');
  const [simLargo, setSimLargo] = useState('1.90');
  const [simGanancia, setSimGanancia] = useState('40');
  const [simImpuesto, setSimImpuesto] = useState('7');
  const [simManoObra, setSimManoObra] = useState('15');
  const [simGastos, setSimGastos] = useState('10');
  const [precioSimulado, setPrecioSimulado] = useState<PrecioSimulado | null>(null);
  const [estructura, setEstructura] = useState<EstructuraCostosData | null>(null);
  const [simLoading, setSimLoading] = useState(false);
  const [showRecalcular, setShowRecalcular] = useState(false);
  const [recPropuesta, setRecPropuesta] = useState<any[] | null>(null);
  const [recAplicando, setRecAplicando] = useState(false);

  // Section modal
  const [showSectionModal, setShowSectionModal] = useState(false);
  const [sectionForm, setSectionForm] = useState({
    nombre: '',
    baseTipo: 'EBANISTERÍA',
    orden: 1,
    pct_gastos_seccion: '10',
  });

  // Element (insumo) modal
  const [showElementModal, setShowElementModal] = useState(false);
  const [elementSectionId, setElementSectionId] = useState<number | null>(null);
  const [elementMaterialSearch, setElementMaterialSearch] = useState('');
  const [showElementMaterialDropdown, setShowElementMaterialDropdown] = useState(false);
  const [elementForm, setElementForm] = useState({
    nombre_insumo_original: '',
    material_id_normalizado: null as number | null,
    cantidad: '1',
    unidad_medida: '',
    observaciones: '',
    precio_unitario: null as number | null,
  });

  // Costo de producción modal
  const [showCostoProduccionModal, setShowCostoProduccionModal] = useState(false);
  const [costoProduccionSectionId, setCostoProduccionSectionId] = useState<number | null>(null);
  const [costoProduccionForm, setCostoProduccionForm] = useState({
    nombre: '',
    porcentaje: '',
    costo_base: '',
  });
  const [editingCostoProduccionId, setEditingCostoProduccionId] = useState<number | null>(null);

  // Editar política de sección modal
  const [showEditPoliticaModal, setShowEditPoliticaModal] = useState(false);
  const [editingPoliticaSeccionId, setEditingPoliticaSeccionId] = useState<number | null>(null);
  const [politicaForm, setPoliticaForm] = useState({
    pct_gastos_seccion: '',
    pct_trabajadores: '',
    costo_fabricacion: '',
  });

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
  const [fotoArchivo, setFotoArchivo] = useState<File | null>(null);
  const [fotoPreview, setFotoPreview] = useState<string | null>(null);

  // ── Importar estructura de costos pegada desde Excel ──
  const [showImportModal, setShowImportModal] = useState(false);
  const [importTexto, setImportTexto] = useState('');
  const [importNombre, setImportNombre] = useState('');
  const [importTipoId, setImportTipoId] = useState('');
  const [importNuevoTipo, setImportNuevoTipo] = useState('');
  const [importAncho, setImportAncho] = useState('1.60');
  const [importLargo, setImportLargo] = useState('1.90');
  const [importFoto, setImportFoto] = useState<File | null>(null);
  const [importPreview, setImportPreview] = useState<any>(null);
  const [importando, setImportando] = useState(false);
  const [subiendoFoto, setSubiendoFoto] = useState(false);

  const [showRecipeModal, setShowRecipeModal] = useState(false);
  const [recipeForm, setRecipeForm] = useState({
    id: null as number | null,
    material_id: '',
    cantidad_base: '',
    tipo_escala: 'FIJO' as ProductoMaterial['tipo_escala'],
    distancia_pauta_cm: '',
    tornillos_por_pieza: '',
    formula_personalizada: '',
    rangos: [] as { max: string; cantidad: string }[],
    es_fijo_override: false,
    observaciones: '',
    seccion: 'EBANISTERÍA',
  });

  const resetRecipeForm = () => setRecipeForm({
    id: null,
    material_id: '',
    cantidad_base: '',
    tipo_escala: 'FIJO',
    distancia_pauta_cm: '',
    tornillos_por_pieza: '',
    formula_personalizada: '',
    rangos: [],
    es_fijo_override: false,
    observaciones: '',
    seccion: 'EBANISTERÍA',
  });

  const handleOpenRecipeAdd = () => {
    resetRecipeForm();
    setMaterialSearch('');
    setShowRecipeModal(true);
  };

  const handleEditRecipeItem = (item: ProductoMaterial) => {
    setRecipeForm({
      id: item.id,
      material_id: String(item.material_id),
      cantidad_base: String(item.cantidad_base),
      tipo_escala: item.tipo_escala,
      distancia_pauta_cm: item.distancia_pauta_cm != null ? String(item.distancia_pauta_cm) : '',
      tornillos_por_pieza: item.tornillos_por_pieza != null ? String(item.tornillos_por_pieza) : '',
      formula_personalizada: item.formula_personalizada || '',
      rangos: (item.rangos || []).map((r) => ({ max: String(r.max), cantidad: String(r.cantidad) })),
      es_fijo_override: !!item.es_fijo_override,
      observaciones: item.observaciones || '',
      seccion: item.seccion || 'EBANISTERÍA',
    });
    setMaterialSearch(item.material?.nombre || '');
    setShowRecipeModal(true);
  };

  const fetchData = async () => {
    try {
      setLoading(true);
      const [prodData, tiposData, matData] = await Promise.all([
        productosService.getProductos(),
        api.get<TipoProducto[]>('/catalogos/tipo-producto/'),
        api.get<Material[]>('/material/?limite=1000'),
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
    setEstructura(null);
    try {
      setRecetaLoading(true);
      const [legacyData, secData] = await Promise.all([
        productosService.getReceta(product.id),
        productosService.getRecetaEstructurada(product.id)
      ]);
      setReceta(legacyData);
      setSecciones(secData);
    } catch (error) {
      console.error('Error fetching recipe:', error);
    } finally {
      setRecetaLoading(false);
    }
  }, []);


  const verRecalcular = async () => {
    setRecAplicando(true);
    try {
      const res = await api.post('/producto/recalcular-precios', { aplicar: false });
      setRecPropuesta(res.data);
      setShowRecalcular(true);
    } catch {
      toast.error('No se pudo generar la vista previa de precios.');
    } finally {
      setRecAplicando(false);
    }
  };

  const aplicarRecalcular = async () => {
    setRecAplicando(true);
    try {
      const res = await api.post('/producto/recalcular-precios', { aplicar: true });
      setRecPropuesta(res.data);
      toast.success('Precios recalculados. Revisa los que quedaron en revisión.');
      setRecAplicando(false);
    } catch {
      setRecAplicando(false);
      toast.error('No se pudieron aplicar los precios.');
    }
  };

  const handleSimularPrecio = async () => {
    if (!selectedProduct) return;
    try {
      setSimLoading(true);
      const res = await api.get(`/producto/${selectedProduct.id}/calcular-precio`, {
        params: {
          ancho: parseFloat(simAncho),
          largo: parseFloat(simLargo),
          ganancia: parseFloat(simGanancia),
          impuesto: parseFloat(simImpuesto),
          iva: 0,
        },
      });
      
      // Adaptar respuesta del backend al esquema PrecioSimulado del frontend
      const data = res.data;
      const costo_material = data.costo_materiales !== undefined ? data.costo_materiales : 0;
      const costo_mano_obra = data.costo_mano_obra !== undefined ? data.costo_mano_obra : 0;
      const costo_gastos = data.costo_gastos !== undefined ? data.costo_gastos : 0;
      const costo_total = data.costo_total !== undefined ? data.costo_total : 0;
      const impuesto_porcentaje = data.impuesto_porcentaje !== undefined ? data.impuesto_porcentaje : 7;
      const impuestos = data.impuestos !== undefined ? data.impuestos : 0;
      const precio_venta = data.precio_venta !== undefined ? data.precio_venta : 0;
      
      setPrecioSimulado({
        costo_material,
        costo_mano_obra,
        costo_gastos,
        costo_total,
        impuesto_porcentaje,
        impuestos,
        precio_venta,
        ganancia_monto: precio_venta - costo_total,
        detalle: (data.materiales || []).map((m: any) => ({
          nombre: m.nombre || m.material_nombre || "",
          cantidad: m.cantidad_calculada || 0,
          costo_unitario: m.costo_unitario || 0,
          subtotal: m.costo_subtotal || 0
        })),
        desglose_por_seccion: data.desglose_por_seccion || {},
      });
      setEstructura(normalizarEstructuraCostos(res.data));
    } catch (error) {
      console.error('Error simulating price:', error);
      toast.error('Error al calcular el precio. Verifique que el producto tenga materiales en la receta.');
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
      ancho_base: productForm.ancho_base ? parseFloat(productForm.ancho_base) : undefined,
      largo_base: productForm.largo_base ? parseFloat(productForm.largo_base) : undefined,
      alto_base: productForm.alto_base ? parseFloat(productForm.alto_base) : undefined,
    };
    try {
      let productoId: number;
      if (productForm.id) {
        await productosService.actualizarProducto(productForm.id, body);
        productoId = productForm.id;
      } else {
        const nuevoProducto = await productosService.crearProducto(body);
        productoId = nuevoProducto.id;

        // Crear secciones por defecto automáticamente
        const seccionesDefault = ['EBANISTERÍA', 'PINTURA', 'TAPICERÍA', 'TENDIDO', 'TERMINACIÓN'];
        for (let i = 0; i < seccionesDefault.length; i++) {
          await productosService.crearSeccion({
            producto_id: nuevoProducto.id,
            nombre: seccionesDefault[i],
            orden: i + 1,
          });
        }
      }
      // Foto de referencia (opcional): se sube y el servidor la optimiza
      if (fotoArchivo) {
        setSubiendoFoto(true);
        await subirAdjunto(fotoArchivo, TIPO_ADJUNTO.PRODUCTO, productoId);
      }
      setShowProductModal(false);
      setFotoArchivo(null);
      setFotoPreview(null);
      fetchData();
    } catch (error) {
      console.error('Error saving product:', error);
    } finally {
      setSubiendoFoto(false);
    }
  };

  const handleDuplicar = (p: Product) => {
    setConfirmState({
      titulo: 'Duplicar producto',
      mensaje: `¿Duplicar "${p.nombre}"? Se creará una copia con la misma receta de materiales.`,
      accion: () => ejecutarDuplicar(p),
    });
  };
  const ejecutarDuplicar = async (p: Product) => {
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
            seccion: item.seccion,
            distancia_pauta_cm: item.distancia_pauta_cm,
            tornillos_por_pieza: item.tornillos_por_pieza,
            condicion_activacion: item.condicion_activacion,
            rangos: item.rangos,
            formula_personalizada: item.formula_personalizada,
            es_fijo_override: item.es_fijo_override,
            observaciones: item.observaciones,
          })
        )
      );
      toast.success(`¡Producto duplicado con éxito! Puedes editar "${nuevo.nombre}" desde el listado.`);
      await fetchData();
      handleOpenRecipe(nuevo);
    } catch (error) {
      console.error('Error duplicating product:', error);
      toast.error('Error al duplicar el producto.');
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
      rangos: recipeForm.rangos.length > 0
        ? recipeForm.rangos
            .map((r) => ({ max: parseFloat(r.max), cantidad: parseFloat(r.cantidad) }))
            .filter((r) => !isNaN(r.max) && !isNaN(r.cantidad))
        : undefined,
      es_fijo_override: recipeForm.es_fijo_override,
      observaciones: recipeForm.observaciones || undefined,
      seccion: recipeForm.seccion,
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

  const handleDeleteProduct = (id: number) => {
    setConfirmState({
      titulo: 'Eliminar producto',
      mensaje: '¿Está seguro de eliminar este producto?',
      accion: () => ejecutarDeleteProduct(id),
    });
  };
  const ejecutarDeleteProduct = async (id: number) => {
    try {
      await productosService.eliminarProducto(id);
      if (selectedProduct?.id === id) setSelectedProduct(null);
      fetchData();
    } catch (error) {
      console.error('Error deleting product:', error);
    }
  };

  const handleDeleteRecipeItem = (recetaId: number) => {
    if (!selectedProduct) return;
    setConfirmState({
      titulo: 'Remover material',
      mensaje: '¿Remover este material de la receta?',
      accion: () => ejecutarDeleteRecipeItem(recetaId),
    });
  };
  const ejecutarDeleteRecipeItem = async (recetaId: number) => {
    try {
      await productosService.eliminarMaterialReceta(recetaId);
      if (selectedProduct) handleOpenRecipe(selectedProduct);
    } catch (error) {
      console.error('Error removing recipe item:', error);
    }
  };

  const handleCreateSection = async () => {
    if (!selectedProduct || !sectionForm.baseTipo) return;
    try {
      const seccion = await productosService.crearSeccion({
        producto_id: selectedProduct.id,
        nombre: sectionForm.baseTipo + (sectionForm.nombre ? ` (${sectionForm.nombre.trim()})` : ''),
        orden: sectionForm.orden,
        pct_gastos_seccion: sectionForm.pct_gastos_seccion ? parseFloat(sectionForm.pct_gastos_seccion) : null,
      });
      setShowSectionModal(false);
      setSectionForm({ nombre: '', baseTipo: 'EBANISTERÍA', orden: secciones.length + 1, pct_gastos_seccion: '10' });
      handleOpenRecipe(selectedProduct);
    } catch (error) {
      console.error('Error creating section:', error);
      toast.error('Error al crear la sección');
    }
  };

  const handleDeleteSection = (seccionId: number) => {
    if (!selectedProduct) return;
    setConfirmState({
      titulo: 'Eliminar sección',
      mensaje: '¿Eliminar esta sección completa? Se borrarán todos sus insumos y políticas.',
      accion: () => ejecutarDeleteSection(seccionId),
    });
  };
  const ejecutarDeleteSection = async (seccionId: number) => {
    try {
      await productosService.eliminarSeccion(seccionId);
      if (selectedProduct) handleOpenRecipe(selectedProduct);
    } catch (error) {
      console.error('Error deleting section:', error);
      toast.error('Error al eliminar la sección');
    }
  };

  const handleCreateElement = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedProduct || !elementSectionId || !elementForm.nombre_insumo_original.trim()) return;
    try {
      await productosService.crearElementoSeccion({
        seccion_id: elementSectionId,
        nombre_insumo_original: elementForm.nombre_insumo_original.trim(),
        material_id_normalizado: elementForm.material_id_normalizado,
        cantidad: parseFloat(elementForm.cantidad) || 1,
        unidad_medida: elementForm.unidad_medida || undefined,
        precio_unitario: elementForm.precio_unitario,
        observaciones: elementForm.observaciones || undefined,
      });
      setShowElementModal(false);
      setElementForm({ nombre_insumo_original: '', material_id_normalizado: null, cantidad: '1', unidad_medida: '', observaciones: '', precio_unitario: null });
      handleOpenRecipe(selectedProduct);
    } catch (error) {
      console.error('Error creating element:', error);
      toast.error('Error al crear el insumo');
    }
  };

  const handleDeleteElement = (elementoId: number) => {
    if (!selectedProduct) return;
    setConfirmState({
      titulo: 'Eliminar insumo',
      mensaje: '¿Eliminar este insumo de la sección?',
      accion: () => ejecutarDeleteElement(elementoId),
    });
  };
  const ejecutarDeleteElement = async (elementoId: number) => {
    try {
      await productosService.eliminarElementoSeccion(elementoId);
      if (selectedProduct) handleOpenRecipe(selectedProduct);
    } catch (error) {
      console.error('Error deleting element:', error);
      toast.error('Error al eliminar el insumo');
    }
  };

  const handleCreateCostoProduccion = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedProduct || !costoProduccionSectionId || !costoProduccionForm.nombre.trim()) return;
    try {
      await productosService.crearCostoProduccion({
        seccion_id: costoProduccionSectionId,
        nombre: costoProduccionForm.nombre.trim(),
        porcentaje: costoProduccionForm.porcentaje ? parseFloat(costoProduccionForm.porcentaje) : null,
        costo_base: parseFloat(costoProduccionForm.costo_base) || 0,
      });
      setShowCostoProduccionModal(false);
      setEditingCostoProduccionId(null);
      setCostoProduccionForm({ nombre: '', porcentaje: '', costo_base: '' });
      handleOpenRecipe(selectedProduct);
    } catch (error) {
      console.error('Error creating costo produccion:', error);
      toast.error('Error al crear el costo de producción');
    }
  };

  const handleEditCostoProduccion = async () => {
    if (!selectedProduct || !editingCostoProduccionId) return;
    try {
      await productosService.actualizarCostoProduccion(editingCostoProduccionId, {
        nombre: costoProduccionForm.nombre.trim() || undefined,
        porcentaje: costoProduccionForm.porcentaje ? parseFloat(costoProduccionForm.porcentaje) : null,
        costo_base: parseFloat(costoProduccionForm.costo_base) || 0,
      });
      setShowCostoProduccionModal(false);
      setEditingCostoProduccionId(null);
      setCostoProduccionForm({ nombre: '', porcentaje: '', costo_base: '' });
      handleOpenRecipe(selectedProduct);
    } catch (error) {
      console.error('Error editing costo produccion:', error);
      toast.error('Error al actualizar el costo de producción');
    }
  };

  const handleDeleteCostoProduccion = (itemId: number) => {
    if (!selectedProduct) return;
    setConfirmState({
      titulo: 'Eliminar costo de producción',
      mensaje: '¿Eliminar este costo de producción?',
      accion: () => ejecutarDeleteCostoProduccion(itemId),
    });
  };
  const ejecutarDeleteCostoProduccion = async (itemId: number) => {
    try {
      await productosService.eliminarCostoProduccion(itemId);
      if (selectedProduct) handleOpenRecipe(selectedProduct);
    } catch (error) {
      console.error('Error deleting costo produccion:', error);
      toast.error('Error al eliminar el costo de producción');
    }
  };

  const handleSavePolitica = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedProduct || !editingPoliticaSeccionId) return;
    try {
      await productosService.actualizarPoliticaSeccion(editingPoliticaSeccionId, {
        pct_gastos_seccion: politicaForm.pct_gastos_seccion ? parseFloat(politicaForm.pct_gastos_seccion) : undefined,
        pct_trabajadores: politicaForm.pct_trabajadores ? parseFloat(politicaForm.pct_trabajadores) : null,
        costo_fabricacion: politicaForm.costo_fabricacion ? parseFloat(politicaForm.costo_fabricacion) : null,
      });
      setShowEditPoliticaModal(false);
      setEditingPoliticaSeccionId(null);
      handleOpenRecipe(selectedProduct);
    } catch (error) {
      console.error('Error actualizando política:', error);
      toast.error('Error al guardar la política de la sección');
    }
  };

  // Totales principales
  const totalFabricados = useMemo(() => productos.filter((p) => !p.es_reventa).length, [productos]);
  const totalReventa = useMemo(() => productos.filter((p) => p.es_reventa).length, [productos]);

  // Lista de subcategorías disponibles según el filtro de origen
  const subcategoriasDisponibles = useMemo(() => {
    const prodsBase = productos.filter((p) => {
      if (tipoOrigenFiltro === 'FABRICADOS') return !p.es_reventa;
      if (tipoOrigenFiltro === 'REVENTA') return p.es_reventa;
      return true;
    });

    const mapa = new Map<string, number>();
    prodsBase.forEach((p) => {
      const cat = p.tipo_producto?.nombre || (p.es_reventa ? 'Reventa' : 'Sin clasificar');
      mapa.set(cat, (mapa.get(cat) || 0) + 1);
    });

    return Array.from(mapa.entries())
      .map(([nombre, count]) => ({ nombre, count }))
      .sort((a, b) => b.count - a.count);
  }, [productos, tipoOrigenFiltro]);

  // Filtrado final de productos
  const filteredProducts = useMemo(() => {
    const term = search.toLowerCase().trim();

    return productos.filter((p) => {
      // Filtro de origen (Fabricados vs Reventa)
      if (tipoOrigenFiltro === 'FABRICADOS' && p.es_reventa) return false;
      if (tipoOrigenFiltro === 'REVENTA' && !p.es_reventa) return false;

      // Filtro de subcategoría
      if (subcategoriaFiltro !== 'TODAS') {
        const cat = p.tipo_producto?.nombre || (p.es_reventa ? 'Reventa' : 'Sin clasificar');
        if (cat !== subcategoriaFiltro) return false;
      }

      // Filtro de búsqueda textual
      if (!term) return true;
      const matchName = p.nombre.toLowerCase().includes(term);
      const matchCode = p.codigo?.toLowerCase().includes(term);
      const matchDesc = p.descripcion?.toLowerCase().includes(term);
      const matchCat = (p.tipo_producto?.nombre || '').toLowerCase().includes(term);
      return matchName || matchCode || matchDesc || matchCat;
    });
  }, [productos, tipoOrigenFiltro, subcategoriaFiltro, search]);

  // Agrupación de productos por categoría para la vista estructurada
  const productosPorCategoria = useMemo(() => {
    const mapa = new Map<string, Product[]>();
    filteredProducts.forEach((p) => {
      const cat = p.tipo_producto?.nombre || (p.es_reventa ? 'Reventa Comercial' : 'Sin clasificar');
      if (!mapa.has(cat)) mapa.set(cat, []);
      mapa.get(cat)!.push(p);
    });
    return Array.from(mapa.entries()).map(([categoria, items]) => ({
      categoria,
      items,
    }));
  }, [filteredProducts]);

  // Renderizador de una tarjeta individual de producto
  const renderProductCard = (p: Product) => (
    <div
      key={p.id}
      onClick={() => handleOpenRecipe(p)}
      className={`relative bg-white border rounded-2xl p-4 cursor-pointer transition-all hover:shadow-md group flex flex-col justify-between ${
        selectedProduct?.id === p.id
          ? 'border-yeikar-primary shadow-md ring-2 ring-yeikar-primary/30 bg-amber-50/10'
          : 'border-yeikar-secondary-light/10 hover:border-yeikar-primary/40'
      }`}
    >
      <div>
        {/* Selected indicator */}
        {selectedProduct?.id === p.id && (
          <div className="absolute top-3 right-3 flex items-center gap-1 bg-yeikar-primary text-yeikar-neutral text-[10px] font-black font-headline px-2 py-0.5 rounded-full shadow">
            <span>Activo</span>
          </div>
        )}

        {/* Foto de referencia */}
        <div className="mb-3 h-32 rounded-xl overflow-hidden bg-yeikar-tertiary/30 relative">
          {p.fotos && p.fotos.length > 0 && p.fotos[0].url ? (
            <img
              src={p.fotos[0].url}
              alt={p.nombre}
              className="w-full h-full object-cover"
              loading="lazy"
            />
          ) : (
            <div className="w-full h-full flex items-center justify-center text-yeikar-neutral/25">
              <Package className="w-8 h-8" />
            </div>
          )}

          {/* Badges sobre la foto */}
          <div className="absolute bottom-2 left-2 flex items-center gap-1 flex-wrap">
            <span
              className={`text-[9px] font-black font-headline uppercase tracking-wider px-2 py-0.5 rounded-md shadow-xs ${
                p.es_reventa
                  ? 'bg-sky-600 text-white'
                  : 'bg-amber-600 text-white'
              }`}
            >
              {p.es_reventa ? 'Reventa' : 'Fabricado'}
            </span>
          </div>
        </div>

        {/* Type / Subcategory badge */}
        <div className="flex items-center justify-between gap-1 mb-1">
          <span className="text-[10px] font-black font-headline uppercase tracking-wider text-yeikar-primary-dark/80 bg-yeikar-primary/10 px-2 py-0.5 rounded">
            {p.tipo_producto?.nombre || 'General'}
          </span>
          {p.codigo && (
            <span className="text-[10px] font-mono text-yeikar-neutral/50">#{p.codigo}</span>
          )}
        </div>

        <h3 className="font-headline font-bold text-yeikar-secondary text-sm sm:text-base mt-1 leading-snug line-clamp-2">
          {p.nombre}
        </h3>

        {/* Dimensions (muebles fabricados) o badge Reventa */}
        <div className="mt-2.5 flex items-center gap-2 flex-wrap">
          {p.es_reventa ? (
            <>
              <span className="bg-sky-50 text-sky-700 border border-sky-200 px-2 py-0.5 rounded-lg text-[10px] font-black font-headline uppercase tracking-wider">
                Reventa{p.moneda && p.moneda.codigo !== 'COP' ? ` · ${p.moneda.codigo}` : ''}
              </span>
              {p.precio_venta_base != null && Number(p.precio_venta_base) > 0 && (
                <span className="text-[11px] font-mono font-bold text-yeikar-secondary">
                  {formatCurrency(Number(p.precio_venta_base), p.moneda?.codigo)}
                </span>
              )}
            </>
          ) : (
            <div className="flex items-center gap-1 bg-yeikar-tertiary/40 px-2 py-0.5 rounded-lg text-[11px] font-mono font-bold text-yeikar-secondary">
              <svg className="w-3 h-3 text-yeikar-neutral/50" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 8V4m0 0h4M4 4l5 5m11-1V4m0 0h-4m4 0l-5 5M4 16v4m0 0h4m-4 0l5-5m11 5l-5-5m5 5v-4m0 4h-4" />
              </svg>
              {p.ancho_base}m × {p.largo_base}m
              {p.alto_base ? ` × ${p.alto_base}m` : ''}
            </div>
          )}
        </div>

        {p.descripcion && (
          <p className="mt-2 text-xs text-yeikar-neutral/55 line-clamp-2 leading-relaxed">{p.descripcion}</p>
        )}
      </div>

      {/* Actions row */}
      <div
        className="mt-3 pt-2.5 border-t border-yeikar-secondary-light/10 flex gap-1.5 opacity-80 group-hover:opacity-100 transition-opacity"
        onClick={(e) => e.stopPropagation()}
      >
        <button
          onClick={() => handleDuplicar(p)}
          title="Duplicar con su receta"
          className="flex-1 flex items-center justify-center gap-1 bg-yeikar-tertiary/60 hover:bg-yeikar-tertiary text-yeikar-secondary px-2.5 py-1.5 rounded-lg text-[11px] font-bold transition-colors"
        >
          <Copy className="w-3 h-3" />
          <span>Duplicar</span>
        </button>
        <button
          onClick={() => {
            setProductForm({ id: p.id, nombre: p.nombre, codigo: p.codigo || '', tipo_producto_id: String(p.tipo_producto_id), descripcion: p.descripcion || '', ancho_base: String(p.ancho_base ?? ''), largo_base: String(p.largo_base ?? ''), alto_base: p.alto_base ? String(p.alto_base) : '' });
            setShowProductModal(true);
          }}
          className="flex-1 flex items-center justify-center gap-1 bg-yeikar-primary/10 hover:bg-yeikar-primary/20 text-yeikar-secondary px-2.5 py-1.5 rounded-lg text-[11px] font-bold transition-colors"
        >
          <Pencil className="w-3 h-3" />
          <span>Editar</span>
        </button>
        <button
          onClick={() => handleDeleteProduct(p.id)}
          className="flex items-center justify-center bg-red-50 hover:bg-red-100 text-red-500 px-2 py-1.5 rounded-lg text-[11px] font-bold transition-colors"
          title="Eliminar producto"
        >
          <Trash2 className="w-3.5 h-3.5" />
        </button>
      </div>
    </div>
  );

  // ── Importar estructura desde Excel (copy-paste) ──
  const abrirImportModal = () => {
    setImportTexto('');
    setImportNombre('');
    setImportTipoId('');
    setImportNuevoTipo('');
    setImportAncho('1.60');
    setImportLargo('1.90');
    setImportFoto(null);
    setImportPreview(null);
    setShowImportModal(true);
  };

  const analizarImport = async () => {
    if (!importTexto.trim()) {
      toast.error('Pega primero las filas del Excel.');
      return;
    }
    setImportando(true);
    setImportPreview(null);
    try {
      const resp = await api.post('/producto/importar-estructura-texto', {
        texto: importTexto,
        dry_run: true,
        tipo_producto_id: importTipoId ? Number(importTipoId) : null,
        nuevo_tipo_producto: importNuevoTipo.trim() || null,
        ancho: Number(importAncho) || 1.6,
        largo: Number(importLargo) || 1.9,
      });
      setImportPreview(resp.data);
      const sugerido: string | null = resp.data?.nombre_sugerido ?? null;
      if (sugerido && !importNombre.trim()) setImportNombre(sugerido);
    } catch (error: any) {
      toast.error(error?.response?.data?.detail || 'No se pudo analizar el texto pegado.');
    } finally {
      setImportando(false);
    }
  };

  const crearDesdeImport = async () => {
    if (!importNombre.trim()) { toast.error('Indica el nombre del producto.'); return; }
    if (!importTipoId && !importNuevoTipo.trim()) { toast.error('Selecciona o escribe el tipo de mueble.'); return; }
    if (!importPreview) { toast.error('Analiza el texto primero.'); return; }
    setImportando(true);
    try {
      const resp = await api.post('/producto/importar-estructura-texto', {
        texto: importTexto,
        dry_run: false,
        nombre: importNombre.trim(),
        tipo_producto_id: importTipoId ? Number(importTipoId) : null,
        nuevo_tipo_producto: importNuevoTipo.trim() || null,
        ancho: Number(importAncho) || 1.6,
        largo: Number(importLargo) || 1.9,
      });
      const pid = resp.data?.producto?.id;
      if (importFoto && pid) {
        await subirAdjunto(importFoto, TIPO_ADJUNTO.PRODUCTO, pid);
      }
      toast.success(`Producto "${importNombre.trim()}" creado con su estructura de costos.`);
      setShowImportModal(false);
      fetchData();
    } catch (error: any) {
      toast.error(error?.response?.data?.detail || 'No se pudo crear el producto.');
    } finally {
      setImportando(false);
    }
  };

  return (
    <div className="space-y-5">
      {/* ── Header ── */}
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
        <div>
          <h1 className="text-3xl font-black font-headline text-yeikar-secondary tracking-tight">
            Catálogo de Productos
          </h1>
          <p className="text-yeikar-neutral/60 mt-1 text-sm font-body">
            Explore y administre muebles fabricados y de reventa, configure recetas y simule costos de producción.
          </p>
        </div>

        <div className="flex items-center gap-3 flex-wrap">
          {/* Search */}
          <div className="relative w-64">
            <input
              type="text"
              placeholder="Buscar producto..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="w-full bg-white border border-yeikar-secondary-light/15 rounded-xl pl-9 pr-8 py-2.5 text-sm focus:outline-none focus:border-yeikar-primary shadow-sm font-body"
            />
            <Search className="w-4 h-4 text-yeikar-neutral/40 absolute left-3 top-3" />
            {search && (
              <button
                onClick={() => setSearch('')}
                className="absolute right-2.5 top-3 text-stone-400 hover:text-stone-600"
                title="Limpiar búsqueda"
              >
                <X className="w-4 h-4" />
              </button>
            )}
          </div>

          <button
            onClick={abrirImportModal}
            className="bg-white hover:bg-yeikar-tertiary/60 text-yeikar-secondary border border-yeikar-secondary-light/20 px-4 py-2.5 rounded-xl font-bold font-headline shadow-sm transition-all flex items-center gap-2 text-sm whitespace-nowrap"
            title="Pega las filas de una hoja de Excel con la estructura de costos"
          >
            <FileSpreadsheet className="w-4 h-4 text-yeikar-primary-dark" />
            Importar estructura
          </button>
          <button
            onClick={() => {
              setProductForm({ id: null, nombre: '', codigo: '', tipo_producto_id: '', descripcion: '', ancho_base: '1.60', largo_base: '1.90', alto_base: '' });
              setShowProductModal(true);
            }}
            className="bg-yeikar-primary hover:bg-yeikar-primary-dark text-yeikar-neutral px-5 py-2.5 rounded-xl font-bold font-headline shadow-sm hover:shadow transition-all flex items-center gap-2 text-sm whitespace-nowrap"
          >
            <Plus className="w-4 h-4" />
            Nuevo Mueble
          </button>
          {esAdmin && (
            <button
              onClick={verRecalcular}
              className="border border-yeikar-secondary-light/20 text-yeikar-secondary px-4 py-2.5 rounded-xl font-bold font-headline hover:bg-yeikar-tertiary transition-all text-sm whitespace-nowrap flex items-center gap-1.5"
              title="Recalcula los precios base de los productos con receta cuando cambian los insumos (vista previa)"
            >
              <RefreshCw className="w-3.5 h-3.5" />
              <span>Recalcular precios</span>
            </button>
          )}
        </div>
      </div>

      {/* ── Barra de Navegación por Origen y Subcategorías ── */}
      <div className="bg-white rounded-2xl border border-yeikar-secondary-light/15 p-4 shadow-xs space-y-3.5">
        {/* Nivel 1: Origen (Todos / Fabricados / Revendidos) */}
        <div className="flex items-center justify-between gap-3 flex-wrap border-b border-stone-100 pb-3">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-[11px] uppercase font-bold text-stone-400 font-headline tracking-wider mr-1 flex items-center gap-1">
              <Layers className="w-3.5 h-3.5 text-yeikar-primary" /> Origen:
            </span>

            <button
              type="button"
              onClick={() => {
                setTipoOrigenFiltro('TODOS');
                setSubcategoriaFiltro('TODAS');
              }}
              className={`px-4 py-2 rounded-xl text-xs font-black font-headline transition-all border flex items-center gap-2 ${
                tipoOrigenFiltro === 'TODOS'
                  ? 'bg-yeikar-secondary text-yeikar-tertiary border-yeikar-secondary shadow-sm'
                  : 'bg-stone-50 text-stone-600 border-stone-200 hover:bg-stone-100'
              }`}
            >
              <LayoutGrid className="w-3.5 h-3.5" />
              <span>Todos los Muebles</span>
              <span className="font-mono text-[10px] bg-white/20 px-1.5 py-0.5 rounded-full">
                {productos.length}
              </span>
            </button>

            <button
              type="button"
              onClick={() => {
                setTipoOrigenFiltro('FABRICADOS');
                setSubcategoriaFiltro('TODAS');
              }}
              className={`px-4 py-2 rounded-xl text-xs font-black font-headline transition-all border flex items-center gap-2 ${
                tipoOrigenFiltro === 'FABRICADOS'
                  ? 'bg-amber-600 text-white border-amber-600 shadow-sm'
                  : 'bg-amber-50/70 text-amber-900 border-amber-200/80 hover:bg-amber-100/60'
              }`}
            >
              <Hammer className="w-3.5 h-3.5" />
              <span>Fabricados (Taller)</span>
              <span className="font-mono text-[10px] bg-amber-950/20 px-1.5 py-0.5 rounded-full font-bold">
                {totalFabricados}
              </span>
            </button>

            <button
              type="button"
              onClick={() => {
                setTipoOrigenFiltro('REVENTA');
                setSubcategoriaFiltro('TODAS');
              }}
              className={`px-4 py-2 rounded-xl text-xs font-black font-headline transition-all border flex items-center gap-2 ${
                tipoOrigenFiltro === 'REVENTA'
                  ? 'bg-sky-700 text-white border-sky-700 shadow-sm'
                  : 'bg-sky-50/70 text-sky-900 border-sky-200/80 hover:bg-sky-100/60'
              }`}
            >
              <Package className="w-3.5 h-3.5" />
              <span>Revendidos (Comerciales)</span>
              <span className="font-mono text-[10px] bg-sky-950/20 px-1.5 py-0.5 rounded-full font-bold">
                {totalReventa}
              </span>
            </button>
          </div>

          <div className="text-xs text-stone-500 font-medium">
            Mostrando <strong className="text-yeikar-secondary">{filteredProducts.length}</strong> muebles
          </div>
        </div>

        {/* Nivel 2: Subcategorías (Camas, Sillones, Comedores, Armarios, etc.) */}
        {subcategoriasDisponibles.length > 0 && (
          <div className="flex items-center gap-2 overflow-x-auto pb-1 scrollbar-thin scrollbar-thumb-stone-200">
            <span className="text-[11px] uppercase font-bold text-stone-400 font-headline tracking-wider shrink-0 mr-1 flex items-center gap-1">
              <Tag className="w-3 h-3 text-yeikar-primary" /> Categorías:
            </span>

            <button
              type="button"
              onClick={() => setSubcategoriaFiltro('TODAS')}
              className={`px-3 py-1 rounded-lg text-xs font-bold transition-all shrink-0 border ${
                subcategoriaFiltro === 'TODAS'
                  ? 'bg-yeikar-primary text-yeikar-neutral border-yeikar-primary shadow-xs'
                  : 'bg-stone-50 text-stone-600 border-stone-200 hover:bg-stone-100'
              }`}
            >
              Todas ({subcategoriasDisponibles.reduce((acc, c) => acc + c.count, 0)})
            </button>

            {subcategoriasDisponibles.map((cat) => (
              <button
                key={cat.nombre}
                type="button"
                onClick={() => setSubcategoriaFiltro(cat.nombre)}
                className={`px-3 py-1 rounded-lg text-xs font-bold transition-all shrink-0 border flex items-center gap-1.5 ${
                  subcategoriaFiltro === cat.nombre
                    ? 'bg-yeikar-primary text-yeikar-neutral border-yeikar-primary shadow-xs'
                    : 'bg-stone-50 text-stone-700 border-stone-200 hover:border-yeikar-primary/40 hover:bg-stone-100'
                }`}
              >
                <span>{cat.nombre}</span>
                <span className="font-mono text-[10px] opacity-70">({cat.count})</span>
              </button>
            ))}
          </div>
        )}
      </div>

      {/* ── Main Layout: Grid / Categories Sections + Side Panel ── */}
      <div className="flex flex-col xl:flex-row gap-6">

        {/* ── Products Grid / Categorized Groups ── */}
        <div className="flex-1 min-w-0 space-y-6">
          {loading ? (
            <div className="flex flex-col items-center justify-center py-24 space-y-4 bg-white rounded-3xl border border-yeikar-secondary-light/10">
              <div className="w-10 h-10 border-4 border-yeikar-primary border-t-transparent rounded-full animate-spin" />
              <p className="text-sm font-mono text-yeikar-neutral/60">Cargando catálogo de productos...</p>
            </div>
          ) : filteredProducts.length === 0 ? (
            <div className="bg-white border border-dashed border-yeikar-secondary-light/15 rounded-3xl p-14 text-center text-yeikar-neutral/40">
              <Package className="w-12 h-12 mx-auto text-yeikar-neutral/20 mb-3" />
              <p className="font-semibold text-sm text-stone-700">No se encontraron productos.</p>
              <p className="text-xs text-stone-400 mt-1">
                Prueba ajustando los filtros o la búsqueda.
              </p>
              {(search || subcategoriaFiltro !== 'TODAS' || tipoOrigenFiltro !== 'TODOS') && (
                <button
                  type="button"
                  onClick={() => {
                    setSearch('');
                    setSubcategoriaFiltro('TODAS');
                    setTipoOrigenFiltro('TODOS');
                  }}
                  className="mt-4 px-4 py-1.5 bg-yeikar-secondary text-yeikar-tertiary rounded-xl text-xs font-bold hover:bg-yeikar-secondary-light transition-all shadow-xs"
                >
                  Restablecer todos los filtros
                </button>
              )}
            </div>
          ) : subcategoriaFiltro === 'TODAS' && productosPorCategoria.length > 1 ? (
            /* ── Vista Agrupada por Categorías ── */
            <div className="space-y-7">
              {productosPorCategoria.map((grupo) => (
                <div key={grupo.categoria} className="space-y-3.5">
                  {/* Encabezado de la Subcategoría */}
                  <div className="flex items-center justify-between border-b border-yeikar-secondary-light/15 pb-2.5 pt-1">
                    <div className="flex items-center gap-2">
                      <div className="w-2.5 h-2.5 rounded-full bg-yeikar-primary" />
                      <h3 className="font-headline font-black text-lg text-yeikar-secondary tracking-tight">
                        {grupo.categoria}
                      </h3>
                      <span className="text-xs font-mono font-bold bg-yeikar-secondary/10 text-yeikar-secondary px-2.5 py-0.5 rounded-full">
                        {grupo.items.length} {grupo.items.length === 1 ? 'modelo' : 'modelos'}
                      </span>
                    </div>

                    <button
                      type="button"
                      onClick={() => setSubcategoriaFiltro(grupo.categoria)}
                      className="text-xs font-bold text-yeikar-primary hover:text-yeikar-secondary transition-colors flex items-center gap-1"
                    >
                      <span>Ver solo esta categoría</span>
                      <ChevronRight className="w-3.5 h-3.5" />
                    </button>
                  </div>

                  {/* Cuadrícula de tarjetas del grupo */}
                  <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
                    {grupo.items.map(renderProductCard)}
                  </div>
                </div>
              ))}
            </div>
          ) : (
            /* ── Vista Cuadrícula para una sola Categoría / Búsqueda Filtrada ── */
            <div className="space-y-4">
              {subcategoriaFiltro !== 'TODAS' && (
                <div className="flex items-center justify-between bg-amber-50/60 border border-amber-200/60 rounded-xl p-3">
                  <div className="flex items-center gap-2">
                    <Tag className="w-4 h-4 text-yeikar-secondary" />
                    <span className="font-headline font-black text-sm text-yeikar-secondary">
                      Categoría: {subcategoriaFiltro}
                    </span>
                    <span className="text-xs font-mono font-bold bg-amber-200/60 text-amber-900 px-2 py-0.5 rounded-full">
                      {filteredProducts.length} modelos
                    </span>
                  </div>
                  <button
                    type="button"
                    onClick={() => setSubcategoriaFiltro('TODAS')}
                    className="text-xs font-bold text-stone-600 hover:text-yeikar-secondary underline"
                  >
                    Ver todas las categorías
                  </button>
                </div>
              )}

              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
                {filteredProducts.map(renderProductCard)}
              </div>
            </div>
          )}
        </div>

        {/* ── Right Panel: Recipe + Price Simulator ── */}
        {selectedProduct && !selectedProduct.es_reventa && (
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
                    {receta.length > 0 ? (
                      `${receta.length} ${receta.length === 1 ? 'material' : 'materiales'} en receta`
                    ) : secciones.length > 0 ? (
                      `${secciones.reduce((acc, s) => acc + s.elementos.length, 0)} insumos en ${secciones.length} ${secciones.length === 1 ? 'sección' : 'secciones'}`
                    ) : (
                      '0 materiales en receta'
                    )}
                  </span>
                  <div className="flex items-center gap-2">
                    <button
                      onClick={handleOpenRecipeAdd}
                      className="bg-yeikar-primary/10 hover:bg-yeikar-primary/20 text-yeikar-primary px-3 py-1.5 rounded-lg text-xs font-bold flex items-center gap-1.5 transition-colors"
                      title="Agregar material con su regla de escala (receta paramétrica)"
                    >
                      <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
                      </svg>
                      Agregar
                    </button>
                    <button
                      onClick={() => {
                        setSectionForm({ nombre: '', baseTipo: 'EBANISTERÍA', orden: 1, pct_gastos_seccion: '10' });
                        setShowSectionModal(true);
                      }}
                      className="bg-yeikar-primary/10 hover:bg-yeikar-primary/20 text-yeikar-primary px-3 py-1.5 rounded-lg text-xs font-bold flex items-center gap-1.5 transition-colors"
                      title="Crear nueva sección (ej: EBANISTERÍA - Cama, EBANISTERÍA - Nocheros)"
                    >
                      <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
                      </svg>
                      Nueva Sección
                    </button>
                  </div>
                </div>

                {recetaLoading ? (
                  <div className="flex justify-center py-8">
                    <div className="w-6 h-6 border-4 border-yeikar-primary border-t-transparent rounded-full animate-spin" />
                  </div>
                ) : secciones.length > 0 ? (
                  <div className="space-y-4 max-h-[500px] overflow-y-auto pr-1">
                    {secciones.map((sec) => (
                      <div key={sec.id} className="border border-yeikar-secondary-light/15 rounded-xl overflow-hidden bg-white shadow-sm">
                        {/* Header de la Sección */}
                        <div className="bg-yeikar-secondary/5 border-b border-yeikar-secondary-light/10 px-4 py-2.5 flex items-center justify-between">
                          <div className="flex items-center gap-2">
                            <span className="w-2 h-2 rounded-full bg-yeikar-primary"></span>
                            <span className="font-headline font-black text-xs text-yeikar-secondary uppercase tracking-wider">
                              SECCIÓN: {sec.nombre}
                            </span>
                          </div>
                          <div className="flex items-center gap-2">
                            <span className="text-[10px] font-bold font-mono bg-yeikar-secondary/10 text-yeikar-secondary px-2 py-0.5 rounded-full">
                              {sec.elementos.length} insumos
                            </span>
                            <button
                              onClick={() => handleDeleteSection(sec.id)}
                              className="p-1 hover:bg-red-50 hover:text-red-600 text-yeikar-neutral/40 rounded-lg transition-colors"
                              title={`Eliminar sección ${sec.nombre}`}
                            >
                              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                              </svg>
                            </button>
                          </div>
                        </div>

                        {/* Política de la Sección */}
                        {sec.politica && (
                          <div className="bg-amber-50/70 border-b border-amber-100 px-4 py-2">
                            <div className="flex items-center justify-between gap-2">
                              <div className="flex flex-wrap items-center gap-2">
                                {sec.politica.pct_gastos_seccion > 0 && (
                                  <span className="font-mono font-bold text-amber-800 bg-amber-100/90 px-2 py-0.5 rounded text-[10px]">
                                    +{sec.politica.pct_gastos_seccion}% Gastos
                                  </span>
                                )}
                                {sec.politica.pct_trabajadores != null && sec.politica.pct_trabajadores > 0 && (
                                  <span className="font-mono font-bold text-amber-700 bg-amber-100/70 px-2 py-0.5 rounded text-[10px]">
                                    +{sec.politica.pct_trabajadores}% Trab.
                                  </span>
                                )}
                                {sec.politica.costo_fabricacion != null && sec.politica.costo_fabricacion > 0 && (
                                  <span className="font-mono font-bold text-amber-700 bg-amber-100/70 px-2 py-0.5 rounded text-[10px]">
                                    $ Fab: {fmt(sec.politica.costo_fabricacion)}
                                  </span>
                                )}
                                {!sec.politica.pct_gastos_seccion && !sec.politica.pct_trabajadores && !sec.politica.costo_fabricacion && (
                                  <span className="text-[10px] text-amber-700/60 italic">Sin política configurada</span>
                                )}
                              </div>
                              <button
                                onClick={() => {
                                  setEditingPoliticaSeccionId(sec.id);
                                  setPoliticaForm({
                                    pct_gastos_seccion: sec.politica?.pct_gastos_seccion?.toString() ?? '',
                                    pct_trabajadores: sec.politica?.pct_trabajadores?.toString() ?? '',
                                    costo_fabricacion: sec.politica?.costo_fabricacion?.toString() ?? '',
                                  });
                                  setShowEditPoliticaModal(true);
                                }}
                                className="p-1 rounded-lg hover:bg-amber-200/60 text-amber-600 transition-colors shrink-0"
                                title="Editar política de sección"
                              >
                                <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z" />
                                </svg>
                              </button>
                            </div>
                          </div>
                        )}


                        {/* Costos de Producción de la Sección */}
                        <div className="border-b border-gray-100 px-4 py-2 space-y-1.5">
                          <div className="flex items-center justify-between">
                            <span className="text-[10px] font-bold text-yeikar-neutral/40 uppercase tracking-wider">Costos de Producción</span>
                            <button
                              onClick={() => {
                                setCostoProduccionSectionId(sec.id);
                                setEditingCostoProduccionId(null);
                                setCostoProduccionForm({ nombre: '', porcentaje: '', costo_base: '' });
                                setShowCostoProduccionModal(true);
                              }}
                              className="text-[10px] font-bold text-yeikar-primary hover:bg-yeikar-primary/10 px-2 py-1 rounded-lg transition-colors flex items-center gap-1"
                            >
                              <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
                              </svg>
                              Agregar
                            </button>
                          </div>
                          {sec.costos_produccion && sec.costos_produccion.length > 0 ? (
                            <div className="divide-y divide-amber-100">
                              {sec.costos_produccion.map((cp) => (
                                <div key={cp.id} className="flex items-center justify-between text-[11px] py-1 first:pt-0 last:pb-0 hover:bg-amber-50/50 rounded px-1 -mx-1 transition-colors group">
                                  <div className="flex-1 min-w-0 pr-2">
                                    <span className="font-semibold text-amber-900 truncate block">{cp.nombre}</span>
                                  </div>
                                  <div className="flex items-center gap-2 shrink-0">
                                    <span className="font-mono font-bold text-amber-800 bg-amber-100/70 px-1.5 py-0.5 rounded text-[10px]">
                                      {fmt(cp.costo_base)} {cp.porcentaje ? `(+${cp.porcentaje}%)` : ''}
                                    </span>
                                    <span className="font-mono text-[10px] text-emerald-700 bg-emerald-50 px-1.5 py-0.5 rounded font-bold">
                                      {fmt(cp.costo_base * (1 + (cp.porcentaje || 0) / 100))}
                                    </span>
                                    <button
                                      onClick={() => handleDeleteCostoProduccion(cp.id)}
                                      className="opacity-0 group-hover:opacity-100 p-0.5 hover:text-red-500 text-yeikar-neutral/30 transition-all"
                                      title="Eliminar costo de producción"
                                    >
                                      <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                                      </svg>
                                    </button>
                                  </div>
                                </div>
                              ))}
                            </div>
                          ) : (
                            <p className="text-[10px] text-yeikar-neutral/40 italic">Sin costos de producción registrados.</p>
                          )}
                        </div>

                         {/* Insumos Físicos de la Sección */}
                        <div className="p-3 space-y-1.5">
                          <div className="flex items-center justify-between mb-1">
                            <span className="text-[10px] font-bold text-yeikar-neutral/40 uppercase tracking-wider">Insumos</span>
                            <button
                              onClick={() => {
                                setElementSectionId(sec.id);
                                setElementMaterialSearch('');
                                setElementForm({ nombre_insumo_original: '', material_id_normalizado: null, cantidad: '1', unidad_medida: '', observaciones: '', precio_unitario: null });
                                setShowElementModal(true);
                              }}
                              className="text-[10px] font-bold text-yeikar-primary hover:bg-yeikar-primary/10 px-2 py-1 rounded-lg transition-colors flex items-center gap-1"
                            >
                              <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
                              </svg>
                              Agregar insumo
                            </button>
                          </div>
                          <div className="divide-y divide-gray-100">
                          {sec.elementos.length === 0 ? (
                            <p className="text-[11px] text-yeikar-neutral/40 italic py-1">Sin insumos registrados en esta sección.</p>
                          ) : (
                            sec.elementos.map((el) => (
                              <div key={el.id} className="flex items-center justify-between text-xs pt-1.5 first:pt-0 pb-1 px-1 hover:bg-yeikar-tertiary/20 rounded transition-colors group">
                                <div className="min-w-0 flex-1 pr-2">
                                  <span className="font-semibold text-yeikar-secondary truncate block">
                                    • {el.nombre_insumo_original}
                                  </span>
                                  {el.observaciones && (
                                    <span className="text-[10px] text-yeikar-neutral/50 block truncate">{el.observaciones}</span>
                                  )}
                                </div>
                                <div className="flex items-center gap-2 shrink-0">
                                  <span className="font-mono font-bold text-yeikar-secondary bg-gray-100 px-2 py-0.5 rounded text-[11px]">
                                    {el.cantidad} {el.unidad_medida || ''}
                                  </span>
                                  {el.precio_unitario ? (
                                    <span className="font-mono text-[10px] text-emerald-700 bg-emerald-50 px-1.5 py-0.5 rounded font-bold">
                                      {fmt(el.cantidad * el.precio_unitario)}
                                    </span>
                                  ) : null}
                                  <button
                                    onClick={() => handleDeleteElement(el.id)}
                                    className="opacity-0 group-hover:opacity-100 p-0.5 hover:text-red-500 text-yeikar-neutral/30 transition-all"
                                    title="Eliminar insumo"
                                  >
                                    <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                                    </svg>
                                  </button>
                                </div>
                              </div>
                            ))
                          )}
                          </div>
                        </div>
                        {/* Total por Sección */}
                        {sec.elementos.some(el => el.precio_unitario) && (
                          <div className="border-t border-gray-100 px-4 py-1.5 flex justify-end items-center gap-2 text-[11px]">
                            <span className="text-yeikar-neutral/50 font-bold">Total insumos:</span>
                            <span className="font-mono font-black text-yeikar-secondary bg-yeikar-secondary/5 px-2.5 py-0.5 rounded-lg">
                              {fmt(sec.elementos.reduce((sum, el) => sum + (el.cantidad * (el.precio_unitario || 0)), 0))}
                            </span>
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                ) : receta.length === 0 ? (
                  <div className="border border-dashed border-yeikar-secondary-light/15 rounded-xl p-8 text-center text-yeikar-neutral/40 text-xs italic">
                    Sin insumos ni receta — usa "Nueva Sección" para crear el área (EBANISTERÍA, PINTURA…) o "Agregar" para definir la receta paramétrica.
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
                              {item.seccion && (
                                <span className="bg-yeikar-secondary/10 text-yeikar-secondary px-1.5 py-0.5 rounded text-[9px] font-bold shrink-0">
                                  {item.seccion}
                                </span>
                              )}
                            </div>
                          </div>
                          <div className="flex items-center gap-1 shrink-0 opacity-0 group-hover:opacity-100 transition-opacity">
                            <button
                              onClick={() => handleEditRecipeItem(item)}
                              className="p-1.5 rounded-lg hover:bg-yeikar-secondary/10 text-yeikar-neutral/40 hover:text-yeikar-secondary transition-colors"
                              title="Editar material de la receta"
                            >
                              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z" />
                              </svg>
                            </button>
                            <button
                              onClick={() => handleDeleteRecipeItem(item.id)}
                              className="p-1.5 rounded-lg hover:bg-red-50 text-yeikar-neutral/40 hover:text-red-600 transition-colors"
                              title="Quitar material de la receta"
                            >
                              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
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
                  { label: '% Impuestos', value: simImpuesto, setter: setSimImpuesto },
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
                disabled={simLoading || (receta.length === 0 && secciones.every(s => s.elementos.length === 0))}
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
                  {/* ── Estructura de Costos (estilo Excel) ── */}
                  {estructura && (
                    <EstructuraCostos data={estructura} />
                  )}

                  {estructura && estructura.sin_desglose && (
                    <div className="space-y-1.5 text-xs font-mono">
                      <div className="flex justify-between">
                        <span className="text-yeikar-neutral/70">Costo Total</span>
                        <span className="font-bold text-yeikar-secondary">{fmt(precioSimulado.costo_total)}</span>
                      </div>
                      <div className="flex justify-between text-green-600 border-t border-yeikar-secondary-light/10 pt-1.5">
                        <span>Ganancia ({simGanancia}%)</span>
                        <span className="font-bold">+ {fmt(precioSimulado.ganancia_monto)}</span>
                      </div>
                    </div>
                  )}

                  {/* Price highlight */}
                  <div className="bg-gradient-to-r from-yeikar-primary to-yeikar-primary-dark rounded-xl p-4 text-center">
                    <span className="text-[10px] font-black font-mono text-yeikar-neutral/60 uppercase tracking-widest block">Precio de Venta Sugerido</span>
                    <span className="text-2xl font-black font-headline text-yeikar-secondary mt-1 block">
                      {fmt(precioSimulado.precio_venta)}
                    </span>
                    <span className="text-[11px] text-yeikar-secondary/60 font-mono">
                      Para {simAncho}m × {simLargo}m · redondeado al millar
                    </span>
                  </div>
                </div>
              )}
            </div>
          </div>
        )}

        {/* ── Right Panel: aviso para productos de REVENTA (sin receta ni dimensiones) ── */}
        {selectedProduct?.es_reventa && (
          <div className="w-full xl:w-[440px] shrink-0">
            <div className="bg-white border border-yeikar-secondary-light/10 rounded-2xl overflow-hidden shadow-sm">
              <div className="bg-gradient-to-r from-sky-600 to-sky-500 p-5">
                <span className="text-[10px] font-mono font-bold text-white/60 uppercase tracking-widest">Producto de Reventa</span>
                <h2 className="font-headline font-black text-white text-lg mt-0.5 leading-tight">
                  {selectedProduct.nombre}
                </h2>
              </div>
              <div className="p-5 space-y-3 text-sm text-yeikar-neutral/70">
                <p>
                  Este producto se compra y revende: no tiene receta de materiales,
                  secciones ni dimensiones de fabricación.
                </p>
                <p>
                  Su stock, costo de compra y precio de referencia se gestionan en{' '}
                  <strong className="text-yeikar-secondary">Inventario → Productos (Terminados / Reventa)</strong>.
                </p>
                {(selectedProduct.precio_venta_base != null || selectedProduct.precio_costo_base != null) && (
                  <div className="bg-yeikar-tertiary/30 border border-yeikar-secondary-light/10 rounded-xl p-3 space-y-1.5 font-mono text-xs">
                    {selectedProduct.precio_venta_base != null && (
                      <div className="flex justify-between">
                        <span className="text-yeikar-neutral/50">Precio de venta ref.</span>
                        <span className="font-bold text-yeikar-secondary">{formatCurrency(Number(selectedProduct.precio_venta_base), selectedProduct.moneda?.codigo)}</span>
                      </div>
                    )}
                    {selectedProduct.precio_costo_base != null && (
                      <div className="flex justify-between">
                        <span className="text-yeikar-neutral/50">Costo de compra ref.</span>
                        <span className="font-bold text-yeikar-secondary">{formatCurrency(Number(selectedProduct.precio_costo_base), selectedProduct.moneda?.codigo)}</span>
                      </div>
                    )}
                  </div>
                )}
              </div>
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
                {productForm.id ? 'Editar Mueble' : 'Registrar Nuevo Mueble '}
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
                  <SearchSelect
                    value={productForm.tipo_producto_id}
                    onChange={(v) => setProductForm({ ...productForm, tipo_producto_id: String(v) })}
                    options={tiposProducto.map((t) => ({ value: t.id, label: t.nombre }))}
                    placeholder="Selecciona..."
                  />
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

              {!(productForm.id && productos.find((p) => p.id === productForm.id)?.es_reventa) && (
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
              )}

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

              {/* Foto de referencia (opcional) */}
              <div>
                <label className="block text-xs font-bold text-yeikar-neutral/55 mb-2">
                  Foto de referencia del mueble (opcional)
                </label>
                <div className="flex items-start gap-3">
                  {/* Fotos existentes */}
                  {(productForm.id ? productos.find((p) => p.id === productForm.id)?.fotos ?? [] : []).map((f) => (
                    <div key={f.id} className="relative group">
                      <img src={f.url} alt={`Foto de referencia de ${productForm.nombre || 'la pieza'}`} className="h-16 w-16 rounded-xl object-cover border border-yeikar-secondary-light/10" />
                      <button
                        type="button"
                        title="Quitar foto"
                        onClick={async () => {
                          await eliminarAdjunto(f.id);
                          fetchData();
                        }}
                        className="absolute -top-1.5 -right-1.5 bg-red-500 text-white rounded-full w-5 h-5 flex items-center justify-center text-[10px] opacity-0 group-hover:opacity-100 transition-opacity"
                      >
                        ×
                      </button>
                    </div>
                  ))}
                  {/* Preview de la nueva foto */}
                  {fotoPreview && (
                    <img src={fotoPreview} alt="Vista previa de la nueva foto de referencia" className="h-16 w-16 rounded-xl object-cover border border-yeikar-primary/40" />
                  )}
                  {/* Selector de archivo */}
                  <label className="flex items-center justify-center gap-1.5 h-16 px-3 rounded-xl border-2 border-dashed border-yeikar-secondary-light/20 hover:border-yeikar-primary/50 cursor-pointer text-[11px] font-bold text-yeikar-neutral/50 transition-colors">
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
                    </svg>
                    {subiendoFoto ? 'Subiendo…' : 'Subir foto'}
                    <input
                      type="file"
                      accept="image/jpeg,image/png,image/webp,image/heic"
                      className="hidden"
                      onChange={(e) => {
                        const f = e.target.files?.[0];
                        if (!f) return;
                        setFotoArchivo(f);
                        if (fotoPreview) URL.revokeObjectURL(fotoPreview);
                        setFotoPreview(URL.createObjectURL(f));
                      }}
                    />
                  </label>
                </div>
                <p className="text-[10px] text-yeikar-neutral/40 mt-1.5">
                  La imagen se optimiza al subirla (máx. 15 MB; se redimensiona y comprime para no ocupar espacio).
                </p>
              </div>

              <div className="flex justify-end gap-2 pt-2">
                <button type="button" onClick={() => setShowProductModal(false)} className="px-4 py-2 rounded-xl text-sm font-bold text-yeikar-neutral/60 hover:bg-yeikar-tertiary transition-colors">
                  Cancelar
                </button>
                <button type="submit" className="bg-yeikar-primary text-yeikar-neutral px-5 py-2 rounded-xl text-sm font-bold shadow-sm hover:shadow transition-all">
                  {productForm.id ? 'Guardar Cambios' : 'Crear Mueble '}
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
              <div className="relative">
                <label className="block text-xs font-bold text-yeikar-neutral/55 mb-1">Material del Inventario *</label>
                {/* Buscador */}
                <div className="relative">
                  <span className="absolute left-3 top-1/2 -translate-y-1/2 text-yeikar-neutral/30 text-sm"></span>
                  <input
                    type="text"
                    placeholder="Buscar material..."
                    value={materialSearch}
                    autoComplete="off"
                    onFocus={() => setShowMaterialDropdown(true)}
                    onChange={(e) => {
                      setMaterialSearch(e.target.value);
                      setShowMaterialDropdown(true);
                      if (!e.target.value) setRecipeForm({ ...recipeForm, material_id: '' });
                    }}
                    className="w-full bg-yeikar-tertiary/30 border border-yeikar-secondary-light/10 rounded-xl pl-8 pr-3 py-2.5 text-sm focus:outline-none focus:border-yeikar-primary"
                  />
                  {recipeForm.material_id && (
                    <span className="absolute right-3 top-1/2 -translate-y-1/2 text-green-500 text-sm"></span>
                  )}
                </div>
                {/* Dropdown filtrado */}
                {showMaterialDropdown && (
                  <div className="absolute z-50 w-full mt-1 bg-white border border-yeikar-secondary-light/15 rounded-xl shadow-lg max-h-52 overflow-y-auto">
                    {[...materiales]
                      .sort((a, b) => a.nombre.localeCompare(b.nombre, 'es'))
                      .filter(m =>
                        m.nombre.toLowerCase().includes(materialSearch.toLowerCase())
                      )
                      .map((m) => (
                        <button
                          key={m.id}
                          type="button"
                          onClick={() => {
                            setRecipeForm({ ...recipeForm, material_id: String(m.id) });
                            setMaterialSearch(m.nombre);
                            setShowMaterialDropdown(false);
                          }}
                          className={`w-full text-left px-4 py-2.5 text-sm hover:bg-yeikar-tertiary/40 transition-colors border-b border-yeikar-secondary-light/5 last:border-0 ${
                            recipeForm.material_id === String(m.id) ? 'bg-yeikar-primary/10 font-bold' : ''
                          }`}
                        >
                          <span className="font-medium text-yeikar-secondary">{m.nombre}</span>
                          <span className="text-yeikar-neutral/40 text-xs ml-2">({m.unidad_medida?.abreviatura || 'und'})</span>
                          {m.costo_base > 0 && (
                            <span className="text-emerald-600 font-mono text-xs ml-auto float-right mt-0.5">
                              {fmt(m.costo_base)}
                            </span>
                          )}
                        </button>
                      ))
                    }
                    {materiales.filter(m => m.nombre.toLowerCase().includes(materialSearch.toLowerCase())).length === 0 && (
                      <p className="text-center text-yeikar-neutral/40 text-xs py-4">Sin resultados para "{materialSearch}"</p>
                    )}
                  </div>
                )}
                {/* Clic fuera cierra el dropdown */}
                {showMaterialDropdown && (
                  <div className="fixed inset-0 z-40" onClick={() => setShowMaterialDropdown(false)} />
                )}
                <input type="hidden" required value={recipeForm.material_id} />
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

              {recipeForm.tipo_escala === 'POR_RANGO' && (
                <div className="bg-orange-50/50 p-3 rounded-xl border border-orange-100 space-y-2">
                  <div className="flex items-center justify-between">
                    <label className="block text-[10px] font-bold text-yeikar-neutral/50">Rangos de largo (m)</label>
                    <button
                      type="button"
                      onClick={() => setRecipeForm({ ...recipeForm, rangos: [...recipeForm.rangos, { max: '', cantidad: '' }] })}
                      className="text-[10px] font-bold text-orange-600 hover:bg-orange-100 px-2 py-1 rounded-lg flex items-center gap-1 transition-colors"
                    >
                      + Agregar rango
                    </button>
                  </div>
                  <p className="text-[10px] text-orange-700/70">
                    La cantidad salta en tramos según el largo del mueble: "hasta max m → cantidad unidades".
                  </p>
                  {recipeForm.rangos.length === 0 && (
                    <p className="text-[10px] italic text-orange-700/60">Sin rangos definidos — se usará la cantidad base.</p>
                  )}
                  <div className="space-y-1.5">
                    {recipeForm.rangos.map((r, i) => (
                      <div key={i} className="flex items-center gap-2">
                        <span className="text-[10px] font-mono text-orange-600 shrink-0">hasta</span>
                        <input
                          type="number"
                          step="0.01"
                          placeholder="1.5"
                          value={r.max}
                          onChange={(e) => setRecipeForm({ ...recipeForm, rangos: recipeForm.rangos.map((x, xi) => xi === i ? { ...x, max: e.target.value } : x) })}
                          className="w-full bg-white border border-orange-200 rounded-lg p-2 text-sm font-mono focus:outline-none"
                        />
                        <span className="text-[10px] font-mono text-orange-600 shrink-0">m →</span>
                        <input
                          type="number"
                          step="0.001"
                          placeholder="6"
                          value={r.cantidad}
                          onChange={(e) => setRecipeForm({ ...recipeForm, rangos: recipeForm.rangos.map((x, xi) => xi === i ? { ...x, cantidad: e.target.value } : x) })}
                          className="w-full bg-white border border-orange-200 rounded-lg p-2 text-sm font-mono focus:outline-none"
                        />
                        <span className="text-[10px] text-orange-600 shrink-0">und</span>
                        <button
                          type="button"
                          onClick={() => setRecipeForm({ ...recipeForm, rangos: recipeForm.rangos.filter((_, xi) => xi !== i) })}
                          className="p-1 text-orange-400 hover:text-red-600 shrink-0 transition-colors"
                          title="Quitar rango"
                        >
                          ×
                        </button>
                      </div>
                    ))}
                  </div>
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

      {/* ═══════════════════════════════════════════════════════════ */}
      {/* Section Modal */}
      {/* ═══════════════════════════════════════════════════════════ */}
      {showSectionModal && (
        <div className="fixed inset-0 bg-yeikar-secondary/60 backdrop-blur-sm flex items-center justify-center p-4 z-50">
          <div className="bg-white rounded-3xl shadow-xl border border-yeikar-secondary-light/10 max-w-md w-full p-6 space-y-4">
            <div>
              <h3 className="text-xl font-headline font-black text-yeikar-secondary">
                Crear Nueva Sección / Área
              </h3>
              <p className="text-xs text-yeikar-neutral/50 mt-1">
                Selecciona el tipo base y añade un sufijo opcional (ej: "EBANISTERÍA (NOCHEROS)")
              </p>
            </div>

            <form onSubmit={handleCreateSection} className="space-y-4">
              <div>
                <label className="block text-xs font-bold text-yeikar-neutral/55 mb-1">Tipo Base *</label>
                <select
                  value={sectionForm.baseTipo}
                  onChange={(e) => setSectionForm({ ...sectionForm, baseTipo: e.target.value })}
                  className="w-full bg-yeikar-tertiary/30 border border-yeikar-secondary-light/10 rounded-xl p-2.5 text-sm focus:outline-none focus:border-yeikar-primary"
                >
                  <option value="EBANISTERÍA">EBANISTERÍA</option>
                  <option value="PINTURA">PINTURA</option>
                  <option value="TAPICERÍA">TAPICERÍA</option>
                  <option value="TENDIDO">TENDIDO</option>
                  <option value="TERMINACIÓN">TERMINACIÓN</option>
                  <option value="MANO DE OBRA">MANO DE OBRA</option>
                  <option value="OTRA">OTRA</option>
                </select>
              </div>

              <div>
                <label className="block text-xs font-bold text-yeikar-neutral/55 mb-1">Sufijo / Nombre Personalizado (opcional)</label>
                <input
                  type="text"
                  placeholder="Ej: CAMA, NOCHEROS, CABECERA..."
                  value={sectionForm.nombre}
                  onChange={(e) => setSectionForm({ ...sectionForm, nombre: e.target.value })}
                  className="w-full bg-yeikar-tertiary/30 border border-yeikar-secondary-light/10 rounded-xl p-2.5 text-sm focus:outline-none focus:border-yeikar-primary"
                />
                <p className="text-[10px] text-yeikar-neutral/40 mt-1">
                  Se creará como: <span className="font-mono text-yeikar-secondary">{sectionForm.baseTipo}{sectionForm.nombre ? ` (${sectionForm.nombre})` : ''}</span>
                </p>
              </div>

              <div>
                <label className="block text-xs font-bold text-yeikar-neutral/55 mb-1">Orden</label>
                <input
                  type="number"
                  min="1"
                  value={sectionForm.orden}
                  onChange={(e) => setSectionForm({ ...sectionForm, orden: parseInt(e.target.value) || 1 })}
                  className="w-full bg-yeikar-tertiary/30 border border-yeikar-secondary-light/10 rounded-xl p-2.5 text-sm font-mono focus:outline-none focus:border-yeikar-primary"
                />
              </div>

              <div>
                <label className="block text-xs font-bold text-yeikar-neutral/55 mb-1">% Gastos Sección (opcional)</label>
                <input
                  type="number"
                  step="0.1"
                  min="0"
                  placeholder="10"
                  value={sectionForm.pct_gastos_seccion}
                  onChange={(e) => setSectionForm({ ...sectionForm, pct_gastos_seccion: e.target.value })}
                  className="w-full bg-yeikar-tertiary/30 border border-yeikar-secondary-light/10 rounded-xl p-2.5 text-sm font-mono focus:outline-none focus:border-yeikar-primary"
                />
              </div>

              <div className="flex justify-end gap-2 pt-2">
                <button type="button" onClick={() => setShowSectionModal(false)} className="px-4 py-2 rounded-xl text-sm font-bold text-yeikar-neutral/60 hover:bg-yeikar-tertiary transition-colors">
                  Cancelar
                </button>
                <button type="submit" className="bg-yeikar-primary text-yeikar-neutral px-5 py-2 rounded-xl text-sm font-bold shadow-sm hover:shadow transition-all">
                  Crear Sección
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* ═══════════════════════════════════════════════════════════ */}
      {/* Element (Insumo) Modal */}
      {/* ═══════════════════════════════════════════════════════════ */}
      {showElementModal && (
        <div className="fixed inset-0 bg-yeikar-secondary/60 backdrop-blur-sm flex items-center justify-center p-4 z-50">
          <div className="bg-white rounded-3xl shadow-xl border border-yeikar-secondary-light/10 max-w-md w-full p-6 space-y-4">
            <div>
              <h3 className="text-xl font-headline font-black text-yeikar-secondary">
                Agregar Insumo a Sección
              </h3>
              <p className="text-xs text-yeikar-neutral/50 mt-1">
                Busca en el inventario o escribe un nombre personalizado.
              </p>
            </div>

            <form onSubmit={handleCreateElement} className="space-y-4">
              {/* Buscador de inventario */}
              <div className="relative">
                <label className="block text-xs font-bold text-yeikar-neutral/55 mb-1">
                  Buscar en Inventario <span className="font-normal text-yeikar-neutral/40">(opcional)</span>
                </label>
                <div className="relative">
                  <span className="absolute left-3 top-1/2 -translate-y-1/2 text-yeikar-neutral/30 text-sm"></span>
                  <input
                    type="text"
                    placeholder="Buscar material del inventario..."
                    value={elementMaterialSearch}
                    autoComplete="off"
                    onFocus={() => setShowElementMaterialDropdown(true)}
                    onChange={(e) => {
                      setElementMaterialSearch(e.target.value);
                      setShowElementMaterialDropdown(true);
                    }}
                    className="w-full bg-yeikar-tertiary/30 border border-yeikar-secondary-light/10 rounded-xl pl-8 pr-3 py-2.5 text-sm focus:outline-none focus:border-yeikar-primary"
                  />
                  {elementForm.material_id_normalizado && (
                    <span className="absolute right-3 top-1/2 -translate-y-1/2 text-green-500 text-sm"></span>
                  )}
                </div>
                {showElementMaterialDropdown && (
                  <div className="absolute z-50 w-full mt-1 bg-white border border-yeikar-secondary-light/15 rounded-xl shadow-lg max-h-96 overflow-y-auto">
                    {[...materiales]
                      .sort((a, b) => a.nombre.localeCompare(b.nombre, 'es'))
                      .filter(m =>
                        m.nombre.toLowerCase().includes(elementMaterialSearch.toLowerCase())
                      )
                      .map((m) => (
                        <button
                          key={m.id}
                          type="button"
                          onClick={() => {
                            setElementForm({
                              ...elementForm,
                              nombre_insumo_original: m.nombre,
                              material_id_normalizado: m.id,
                              unidad_medida: m.unidad_medida?.abreviatura || '',
                              precio_unitario: m.costo_base,
                            });
                            setElementMaterialSearch(m.nombre);
                            setShowElementMaterialDropdown(false);
                          }}
                          className={`w-full text-left px-4 py-2.5 text-sm hover:bg-yeikar-tertiary/40 transition-colors border-b border-yeikar-secondary-light/5 last:border-0 ${
                            elementForm.material_id_normalizado === m.id ? 'bg-yeikar-primary/10 font-bold' : ''
                          }`}
                        >
                          <span className="font-medium text-yeikar-secondary">{m.nombre}</span>
                          <span className="text-yeikar-neutral/40 text-xs ml-2">({m.unidad_medida?.abreviatura || 'und'})</span>
                          {m.costo_base > 0 && (
                            <span className="text-emerald-600 font-mono text-xs ml-auto float-right mt-0.5">
                              {fmt(m.costo_base)}
                            </span>
                          )}
                        </button>
                      ))
                    }
                    {materiales.filter(m => m.nombre.toLowerCase().includes(elementMaterialSearch.toLowerCase())).length === 0 && (
                      <p className="text-center text-yeikar-neutral/40 text-xs py-4">Sin resultados — escribe el nombre manualmente abajo</p>
                    )}
                  </div>
                )}
                {showElementMaterialDropdown && (
                  <div className="fixed inset-0 z-40" onClick={() => setShowElementMaterialDropdown(false)} />
                )}
              </div>

              {/* Nombre manual (si no se seleccionó del inventario) */}
              <div>
                <label className="block text-xs font-bold text-yeikar-neutral/55 mb-1">
                  {elementForm.material_id_normalizado ? 'Insumo del inventario' : 'Nombre del Insumo *'}
                </label>
                <div className="relative">
                  <input
                    type="text"
                    required
                    placeholder={elementForm.material_id_normalizado ? '' : 'Ej: Tornillo 1/2", Espuma HR35...'}
                    value={elementForm.nombre_insumo_original}
                    onChange={(e) => {
                      setElementForm({ ...elementForm, nombre_insumo_original: e.target.value });
                      if (elementForm.material_id_normalizado) {
                        setElementForm({ ...elementForm, nombre_insumo_original: e.target.value, material_id_normalizado: null, precio_unitario: null });
                        setElementMaterialSearch('');
                      }
                    }}
                    className="w-full bg-yeikar-tertiary/30 border border-yeikar-secondary-light/10 rounded-xl p-2.5 text-sm focus:outline-none focus:border-yeikar-primary"
                  />
                  {elementForm.material_id_normalizado && (
                    <span className="absolute right-3 top-1/2 -translate-y-1/2 text-[10px] font-bold text-emerald-600 bg-emerald-50 px-2 py-0.5 rounded-full">
                      Sincronizado
                    </span>
                  )}
                </div>
              </div>

              <div className="grid grid-cols-3 gap-3">
                <div>
                  <label className="block text-xs font-bold text-yeikar-neutral/55 mb-1">Cantidad</label>
                  <input
                    type="number"
                    step="0.01"
                    min="0"
                    value={elementForm.cantidad}
                    onChange={(e) => setElementForm({ ...elementForm, cantidad: e.target.value })}
                    className="w-full bg-yeikar-tertiary/30 border border-yeikar-secondary-light/10 rounded-xl p-2.5 text-sm font-mono focus:outline-none focus:border-yeikar-primary"
                  />
                </div>
                <div>
                  <label className="block text-xs font-bold text-yeikar-neutral/55 mb-1">Unidad</label>
                  <input
                    type="text"
                    placeholder="und, m, kg..."
                    value={elementForm.unidad_medida}
                    onChange={(e) => setElementForm({ ...elementForm, unidad_medida: e.target.value })}
                    className="w-full bg-yeikar-tertiary/30 border border-yeikar-secondary-light/10 rounded-xl p-2.5 text-sm focus:outline-none focus:border-yeikar-primary"
                  />
                </div>
                <div>
                  <label className="block text-xs font-bold text-yeikar-neutral/55 mb-1">Precio Unit.</label>
                  {elementForm.material_id_normalizado ? (
                    <div className="w-full bg-gray-100 border border-yeikar-secondary-light/10 rounded-xl p-2.5 text-sm font-mono text-yeikar-secondary">
                      {elementForm.precio_unitario ? fmt(elementForm.precio_unitario) : '—'}
                    </div>
                  ) : (
                    <input
                      type="number"
                      step="0.01"
                      min="0"
                      placeholder="0.00"
                      value={elementForm.precio_unitario ?? ''}
                      onChange={(e) => setElementForm({ ...elementForm, precio_unitario: e.target.value ? parseFloat(e.target.value) : null })}
                      className="w-full bg-yeikar-tertiary/30 border border-yeikar-secondary-light/10 rounded-xl p-2.5 text-sm font-mono focus:outline-none focus:border-yeikar-primary"
                    />
                  )}
                </div>
              </div>

              <div>
                <label className="block text-xs font-bold text-yeikar-neutral/55 mb-1">Observaciones</label>
                <input
                  type="text"
                  placeholder="Notas opcionales sobre este insumo..."
                  value={elementForm.observaciones}
                  onChange={(e) => setElementForm({ ...elementForm, observaciones: e.target.value })}
                  className="w-full bg-yeikar-tertiary/30 border border-yeikar-secondary-light/10 rounded-xl p-2.5 text-sm focus:outline-none focus:border-yeikar-primary"
                />
              </div>

              <div className="flex justify-end gap-2 pt-2">
                <button type="button" onClick={() => setShowElementModal(false)} className="px-4 py-2 rounded-xl text-sm font-bold text-yeikar-neutral/60 hover:bg-yeikar-tertiary transition-colors">
                  Cancelar
                </button>
                <button type="submit" className="bg-yeikar-secondary text-white px-5 py-2 rounded-xl text-sm font-bold shadow-sm hover:shadow transition-all">
                  Agregar Insumo
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* ═══════════════════════════════════════════════════════════ */}
      {/* Editar Política de Sección Modal */}
      {/* ═══════════════════════════════════════════════════════════ */}
      {showEditPoliticaModal && (
        <div className="fixed inset-0 bg-yeikar-secondary/60 backdrop-blur-sm flex items-center justify-center p-4 z-50">
          <div className="bg-white rounded-3xl shadow-xl border border-yeikar-secondary-light/10 max-w-sm w-full p-6 space-y-5">
            <div>
              <h3 className="text-xl font-headline font-black text-yeikar-secondary">Editar Política de Sección</h3>
              <p className="text-xs text-yeikar-neutral/50 mt-1">Ajusta los porcentajes que afectan el costo total.</p>
            </div>
            <form onSubmit={handleSavePolitica} className="space-y-4">
              <div>
                <label className="block text-xs font-bold text-yeikar-neutral/55 mb-1">% Gastos Sección</label>
                <div className="relative">
                  <input
                    type="number"
                    step="0.1"
                    min="0"
                    placeholder="10"
                    value={politicaForm.pct_gastos_seccion}
                    onChange={(e) => setPoliticaForm({ ...politicaForm, pct_gastos_seccion: e.target.value })}
                    className="w-full bg-yeikar-tertiary/30 border border-yeikar-secondary-light/10 rounded-xl p-2.5 pr-8 text-sm font-mono focus:outline-none focus:border-yeikar-primary"
                  />
                  <span className="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-yeikar-neutral/40 font-bold">%</span>
                </div>
                <p className="text-[10px] text-yeikar-neutral/40 mt-1">Se aplica sobre el subtotal de insumos + costos de producción.</p>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-bold text-yeikar-neutral/55 mb-1">% Trabajadores</label>
                  <div className="relative">
                    <input
                      type="number"
                      step="0.1"
                      min="0"
                      placeholder="8"
                      value={politicaForm.pct_trabajadores}
                      onChange={(e) => setPoliticaForm({ ...politicaForm, pct_trabajadores: e.target.value })}
                      className="w-full bg-yeikar-tertiary/30 border border-yeikar-secondary-light/10 rounded-xl p-2.5 pr-6 text-sm font-mono focus:outline-none focus:border-yeikar-primary"
                    />
                    <span className="absolute right-2.5 top-1/2 -translate-y-1/2 text-xs text-yeikar-neutral/40 font-bold">%</span>
                  </div>
                </div>
                <div>
                  <label className="block text-xs font-bold text-yeikar-neutral/55 mb-1">$ Costo Fabricación</label>
                  <input
                    type="number"
                    step="0.01"
                    min="0"
                    placeholder="0.00"
                    value={politicaForm.costo_fabricacion}
                    onChange={(e) => setPoliticaForm({ ...politicaForm, costo_fabricacion: e.target.value })}
                    className="w-full bg-yeikar-tertiary/30 border border-yeikar-secondary-light/10 rounded-xl p-2.5 text-sm font-mono focus:outline-none focus:border-yeikar-primary"
                  />
                </div>
              </div>
              <div className="flex justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => { setShowEditPoliticaModal(false); setEditingPoliticaSeccionId(null); }}
                  className="px-4 py-2 rounded-xl text-sm font-bold text-yeikar-neutral/60 hover:bg-yeikar-tertiary transition-colors"
                >
                  Cancelar
                </button>
                <button
                  type="submit"
                  className="bg-yeikar-secondary text-white px-5 py-2 rounded-xl text-sm font-bold shadow-sm hover:shadow transition-all"
                >
                  Guardar
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* ═══════════════════════════════════════════════════════════ */}
      {/* Costo de Producción Modal */}
      {/* ═══════════════════════════════════════════════════════════ */}
      {showCostoProduccionModal && (

        <div className="fixed inset-0 bg-yeikar-secondary/60 backdrop-blur-sm flex items-center justify-center p-4 z-50">
          <div className="bg-white rounded-3xl shadow-xl border border-yeikar-secondary-light/10 max-w-sm w-full p-6 space-y-4">
            <div>
              <h3 className="text-xl font-headline font-black text-yeikar-secondary">
                {editingCostoProduccionId ? 'Editar' : 'Agregar'} Costo de Producción
              </h3>
            </div>
            <form onSubmit={(e) => { e.preventDefault(); editingCostoProduccionId ? handleEditCostoProduccion() : handleCreateCostoProduccion(e); }} className="space-y-4">
              <div>
                <label className="block text-xs font-bold text-yeikar-neutral/55 mb-1">Nombre *</label>
                <input
                  type="text"
                  required
                  placeholder="Ej: PREPARADO CAMA, PINTURA CAMA..."
                  value={costoProduccionForm.nombre}
                  onChange={(e) => setCostoProduccionForm({ ...costoProduccionForm, nombre: e.target.value })}
                  className="w-full bg-yeikar-tertiary/30 border border-yeikar-secondary-light/10 rounded-xl p-2.5 text-sm focus:outline-none focus:border-yeikar-primary"
                />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-bold text-yeikar-neutral/55 mb-1">$ Costo Base *</label>
                  <input
                    type="number"
                    step="0.01"
                    min="0"
                    required
                    placeholder="0.00"
                    value={costoProduccionForm.costo_base}
                    onChange={(e) => setCostoProduccionForm({ ...costoProduccionForm, costo_base: e.target.value })}
                    className="w-full bg-yeikar-tertiary/30 border border-yeikar-secondary-light/10 rounded-xl p-2.5 text-sm font-mono focus:outline-none focus:border-yeikar-primary"
                  />
                </div>
                <div>
                  <label className="block text-xs font-bold text-yeikar-neutral/55 mb-1">% (opcional)</label>
                  <input
                    type="number"
                    step="0.1"
                    min="0"
                    placeholder="5"
                    value={costoProduccionForm.porcentaje}
                    onChange={(e) => setCostoProduccionForm({ ...costoProduccionForm, porcentaje: e.target.value })}
                    className="w-full bg-yeikar-tertiary/30 border border-yeikar-secondary-light/10 rounded-xl p-2.5 text-sm font-mono focus:outline-none focus:border-yeikar-primary"
                  />
                </div>
              </div>
              <div className="flex justify-end gap-2 pt-2">
                <button type="button" onClick={() => { setShowCostoProduccionModal(false); setEditingCostoProduccionId(null); setCostoProduccionForm({ nombre: '', porcentaje: '', costo_base: '' }); }} className="px-4 py-2 rounded-xl text-sm font-bold text-yeikar-neutral/60 hover:bg-yeikar-tertiary transition-colors">
                  Cancelar
                </button>
                <button type="submit" className="bg-yeikar-secondary text-white px-5 py-2 rounded-xl text-sm font-bold shadow-sm hover:shadow transition-all">
                  {editingCostoProduccionId ? 'Guardar' : 'Agregar'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
      <ConfirmDialog
        open={confirmState !== null}
        title={confirmState?.titulo ?? '¿Estás seguro?'}
        message={confirmState?.mensaje ?? ''}
        confirmLabel="Confirmar"
        danger
        onConfirm={async () => {
          const accion = confirmState?.accion;
          setConfirmState(null);
          await accion?.();
        }}
        onCancel={() => setConfirmState(null)}
      />

      {/* Modal: recálculo de precios (vista previa antes → después) */}
      <Modal
        open={showRecalcular}
        onClose={() => setShowRecalcular(false)}
        title="Recalcular precios"
        subtitle="Al subir un insumo, los productos con receta actualizan su precio base automáticamente (sin inflar). Aquí ves antes → después."
        size="4xl"
        footer={
          <div className="flex items-center gap-2">
            <button
              onClick={() => setShowRecalcular(false)}
              className="px-4 py-2 rounded-xl text-sm font-bold text-yeikar-neutral/60 hover:bg-yeikar-tertiary transition-colors"
            >
              Cerrar
            </button>
            <button
              onClick={aplicarRecalcular}
              disabled={recAplicando}
              className="bg-yeikar-primary hover:bg-yeikar-primary-dark text-yeikar-neutral px-5 py-2 rounded-xl text-sm font-bold shadow-sm transition-all"
            >
              {recAplicando ? 'Aplicando...' : 'Aplicar cambios'}
            </button>
          </div>
        }
      >
        {recPropuesta === null ? (
          <p className="text-sm text-yeikar-neutral/50">Generando vista previa...</p>
        ) : recPropuesta.length === 0 ? (
          <p className="text-sm text-yeikar-neutral/50">No hay productos con receta para recalcular.</p>
        ) : (
          <div className="overflow-x-auto max-h-96">
            <table className="w-full text-left border-collapse text-sm">
              <thead className="bg-yeikar-tertiary/30 text-yeikar-secondary text-[11px] uppercase tracking-wider">
                <tr>
                  <th className="px-3 py-2">Producto</th>
                  <th className="px-3 py-2 text-right">Costo actual</th>
                  <th className="px-3 py-2 text-right">Costo nuevo</th>
                  <th className="px-3 py-2 text-right">Precio actual</th>
                  <th className="px-3 py-2 text-right">Precio nuevo</th>
                  <th className="px-3 py-2 text-center">Estado</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-yeikar-secondary-light/10">
                {recPropuesta.map((p) => (
                  <tr key={p.producto_id} className={p.requiere_revision ? 'bg-amber-50' : ''}>
                    <td className="px-3 py-2 font-medium text-yeikar-secondary">{p.producto_nombre}</td>
                    <td className="px-3 py-2 text-right font-mono">{p.costo_anterior != null ? fmt(p.costo_anterior) : '—'}</td>
                    <td className="px-3 py-2 text-right font-mono">{fmt(p.costo_nuevo)}</td>
                    <td className="px-3 py-2 text-right font-mono">{p.precio_anterior != null ? fmt(p.precio_anterior) : '—'}</td>
                    <td className="px-3 py-2 text-right font-mono font-bold">{fmt(p.precio_nuevo)}</td>
                    <td className="px-3 py-2 text-center">
                      {p.requiere_revision ? (
                        <span className="text-[11px] font-bold text-amber-700 bg-amber-100 px-2 py-0.5 rounded-full">
                          Revisar ({Math.round(Math.abs(p.pct_cambio))}%)
                        </span>
                      ) : p.pct_cambio != null && Math.abs(p.pct_cambio) > 0.01 ? (
                        <span className={`text-[11px] font-bold px-2 py-0.5 rounded-full ${p.pct_cambio > 0 ? 'text-green-700 bg-green-100' : 'text-slate-600 bg-slate-100'}`}>
                          {p.pct_cambio > 0 ? '+' : ''}{p.pct_cambio.toFixed(1)}%
                        </span>
                      ) : (
                        <span className="text-[11px] text-yeikar-neutral/40">Sin cambio</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Modal>
      {/* ── Modal: Importar estructura de costos desde Excel (copy-paste) ── */}
      <Modal
        open={showImportModal}
        onClose={() => setShowImportModal(false)}
        title="Importar estructura de costos (Excel)"
        subtitle="Copia las filas de la hoja en Excel (Ctrl+C) y pégalas aquí. El ERP detecta secciones, insumos, mano de obra y gastos, y crea el producto con el mismo precio que tu Excel."
        size="4xl"
      >
        <div className="space-y-5">
          <div>
            <label className="block text-[10px] uppercase font-bold text-yeikar-neutral/50 mb-1">
              1 · Pega las filas del Excel (incluye las filas SECCION ...)
            </label>
            <textarea
              value={importTexto}
              onChange={(e) => setImportTexto(e.target.value)}
              rows={9}
              className="w-full bg-yeikar-tertiary/30 border border-yeikar-secondary-light/20 rounded-xl p-3 text-xs font-mono focus:outline-none focus:border-yeikar-primary"
              placeholder={'SECCION EBANISTERIA\nMADERA\t700\tAPAMATE\t\t140\t98000\nCOLBON\t1.5\tLITRO\t\t14000\t21000\nFABRICACION 300.000 *8% EDUARDO\t\t\t\t\t324000\ngastos de Ebanisteria e 10%\nTOTAL PRODUCCION\t\t\t\t\t2120330\n...'}
            />
            <button
              type="button"
              onClick={analizarImport}
              disabled={importando || !importTexto.trim()}
              className="mt-2 bg-yeikar-secondary text-yeikar-tertiary px-4 py-2 rounded-xl text-xs font-bold font-headline hover:bg-yeikar-secondary-light transition-all disabled:opacity-50"
            >
              {importando ? 'Analizando…' : 'Analizar estructura'}
            </button>
          </div>

          {importPreview && (
            <>
              {importPreview.advertencias?.length > 0 && (
                <div className="bg-amber-50 border border-amber-200 rounded-xl p-3 space-y-1">
                  {importPreview.advertencias.map((a: string, i: number) => (
                    <p key={i} className="text-xs text-amber-800">⚠ {a}</p>
                  ))}
                </div>
              )}

              <div>
                <p className="text-[10px] uppercase font-bold text-yeikar-neutral/50 mb-1">
                  2 · Revisa los totales (así se calcula el precio)
                </p>
                <div className="border border-yeikar-secondary-light/15 rounded-xl overflow-hidden">
                  <table className="w-full text-xs">
                    <thead>
                      <tr className="bg-yeikar-neutral text-yeikar-tertiary font-headline">
                        <th className="px-3 py-2 text-left">Sección</th>
                        <th className="px-2 py-2 text-right">Insumos</th>
                        <th className="px-2 py-2 text-right">Mano de obra</th>
                        <th className="px-2 py-2 text-right">Gastos</th>
                        <th className="px-3 py-2 text-right">Total</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-yeikar-secondary-light/10">
                      {(importPreview.resumen?.por_seccion ?? []).map((s: any, i: number) => (
                        <tr key={i} className={i % 2 ? 'bg-yeikar-tertiary/20' : ''}>
                          <td className="px-3 py-1.5 font-semibold text-yeikar-secondary">{s.nombre}</td>
                          <td className="px-2 py-1.5 text-right font-mono">{formatCurrency(s.insumos_total, 'COP')}</td>
                          <td className="px-2 py-1.5 text-right font-mono">{formatCurrency(s.costos_produccion_total, 'COP')}</td>
                          <td className="px-2 py-1.5 text-right font-mono text-yeikar-neutral/60">
                            {s.pct_gastos != null ? `${s.pct_gastos}% → ${formatCurrency(s.gasto, 'COP')}` : '—'}
                          </td>
                          <td className="px-3 py-1.5 text-right font-mono font-bold">{formatCurrency(s.total_seccion, 'COP')}</td>
                        </tr>
                      ))}
                      <tr className="bg-yeikar-primary/10 font-black">
                        <td className="px-3 py-2" colSpan={4}>TOTAL PRODUCCIÓN (calculado)</td>
                        <td className="px-3 py-2 text-right font-mono">{formatCurrency(importPreview.resumen?.costo_produccion, 'COP')}</td>
                      </tr>
                      {importPreview.resumen?.total_declarado_excel != null && (
                        <tr className="font-bold">
                          <td className="px-3 py-1.5" colSpan={4}>
                            TOTAL declarado en tu Excel
                            {importPreview.resumen.desviacion_porcentual != null && (
                              <span className={`ml-2 text-[10px] px-1.5 py-0.5 rounded-full ${importPreview.resumen.excede_gate_15 ? 'bg-red-100 text-red-700' : 'bg-emerald-100 text-emerald-700'}`}>
                                Δ {importPreview.resumen.desviacion_porcentual}%
                              </span>
                            )}
                          </td>
                          <td className="px-3 py-1.5 text-right font-mono">{formatCurrency(importPreview.resumen.total_declarado_excel, 'COP')}</td>
                        </tr>
                      )}
                      <tr className="bg-amber-50/80">
                        <td className="px-3 py-2" colSpan={4}>
                          Precio sugerido (+{importPreview.resumen?.impuesto_porcentaje}% impuesto, +{importPreview.resumen?.ganancia_porcentaje}% ganancia, redondeado)
                        </td>
                        <td className="px-3 py-2 text-right font-mono font-black text-yeikar-primary-dark">
                          {formatCurrency(importPreview.resumen?.precio_sin_iva, 'COP')}
                        </td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div>
                  <label className="block text-[10px] uppercase font-bold text-yeikar-neutral/50 mb-1">
                    3 · Nombre del producto *
                  </label>
                  <input
                    type="text"
                    value={importNombre}
                    onChange={(e) => setImportNombre(e.target.value)}
                    className="w-full p-2.5 border border-yeikar-secondary-light/20 rounded-xl text-sm focus:outline-none focus:border-yeikar-primary"
                    placeholder={importPreview.nombre_sugerido || 'Ej: CAMA NUBE 1.60'}
                  />
                </div>
                <div>
                  <label className="block text-[10px] uppercase font-bold text-yeikar-neutral/50 mb-1">
                    Tipo de mueble * <span className="normal-case font-normal">(para dividir el catálogo)</span>
                  </label>
                  {!importNuevoTipo && (
                    <SearchSelect
                      value={importTipoId}
                      onChange={(v) => setImportTipoId(String(v))}
                      options={tiposProducto.map((t) => ({ value: String(t.id), label: t.nombre }))}
                      placeholder="Selecciona el tipo..."
                    />
                  )}
                  <input
                    type="text"
                    value={importNuevoTipo}
                    onChange={(e) => {
                      setImportNuevoTipo(e.target.value);
                      if (e.target.value.trim()) setImportTipoId('');
                    }}
                    className={`w-full p-2.5 border border-yeikar-secondary-light/20 rounded-xl text-sm focus:outline-none focus:border-yeikar-primary ${importNuevoTipo ? '' : 'mt-1.5'}`}
                    placeholder={importNuevoTipo ? `Se creará el tipo "${importNuevoTipo}"` : '…o escribe un tipo nuevo (ej. Comedor, Silla)'}
                  />
                </div>
                <div className="grid grid-cols-2 gap-2">
                  <div>
                    <label className="block text-[10px] uppercase font-bold text-yeikar-neutral/50 mb-1">Ancho base (m)</label>
                    <input type="number" step="0.01" value={importAncho} onChange={(e) => setImportAncho(e.target.value)} className="w-full p-2.5 border border-yeikar-secondary-light/20 rounded-xl text-sm font-mono" />
                  </div>
                  <div>
                    <label className="block text-[10px] uppercase font-bold text-yeikar-neutral/50 mb-1">Largo base (m)</label>
                    <input type="number" step="0.01" value={importLargo} onChange={(e) => setImportLargo(e.target.value)} className="w-full p-2.5 border border-yeikar-secondary-light/20 rounded-xl text-sm font-mono" />
                  </div>
                </div>
                <div>
                  <label className="block text-[10px] uppercase font-bold text-yeikar-neutral/50 mb-1">Foto (opcional)</label>
                  <label className="flex items-center justify-center gap-2 w-full cursor-pointer bg-white border border-dashed border-yeikar-secondary-light/30 rounded-xl px-3 py-2.5 text-xs font-bold text-yeikar-neutral/60 hover:border-yeikar-primary transition-colors">
                    <FileSpreadsheet className="w-4 h-4 text-yeikar-primary-dark" />
                    {importFoto ? importFoto.name : 'Subir foto'}
                    <input
                      type="file"
                      accept="image/jpeg,image/png,image/webp,image/heic"
                      className="hidden"
                      onChange={(e) => setImportFoto(e.target.files?.[0] ?? null)}
                    />
                  </label>
                </div>
              </div>
            </>
          )}
        </div>
        <div className="flex justify-end gap-2 pt-4 border-t border-yeikar-secondary-light/10 mt-4">
          <button
            type="button"
            onClick={() => setShowImportModal(false)}
            className="px-4 py-2 rounded-xl text-sm font-bold text-yeikar-neutral/60 hover:bg-yeikar-tertiary transition-colors"
          >
            Cancelar
          </button>
          <button
            type="button"
            onClick={crearDesdeImport}
            disabled={importando || !importPreview}
            className="px-5 py-2 bg-yeikar-primary text-yeikar-neutral font-bold rounded-xl shadow-md hover:bg-yeikar-primary-light transition-all text-sm font-headline disabled:opacity-50"
          >
            {importando ? 'Creando…' : 'Crear producto'}
          </button>
        </div>
      </Modal>
    </div>
  );
}
