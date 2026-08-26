import api from './api';
import type { AdjuntoInfo } from './adjuntosService';

export interface TipoProducto {
  id: number;
  nombre: string;
}

export interface MonedaInfo {
  id: number;
  codigo: string; // COP, USD, VES, EUR
  nombre: string;
  simbolo: string;
  activo?: boolean;
}

export interface Product {
  id: number;
  nombre: string;
  codigo?: string;
  tipo_producto_id: number;
  descripcion?: string;
  activo?: boolean;
  ancho_base?: number;
  largo_base?: number;
  alto_base?: number;
  stock_minimo?: number;
  es_reventa?: boolean;
  /** Moneda de los precios de referencia (COP=1). Los reventa suelen ser USD. */
  moneda_id?: number | null;
  moneda?: MonedaInfo | null;
  /** Precio de referencia en la moneda declarada (moneda_id), NO en COP. */
  precio_costo_base?: number | null;
  precio_venta_base?: number | null;
  tipo_producto?: TipoProducto;
  /** Fotos de referencia del mueble. */
  fotos?: AdjuntoInfo[];
}

export interface Material {
  id: number;
  nombre: string;
  unidad_medida_id: number;
  costo_base: number;
  activo?: boolean;
  unidad_medida?: {
    id: number;
    nombre: string;
    abreviatura: string;
  };
}

export interface RangoEscala {
  max: number;
  cantidad: number;
}

export interface ProductoMaterial {
  id: number;
  producto_id: number;
  material_id: number;
  cantidad_base: number;
  tipo_escala: 'FIJO' | 'LINEAL' | 'AREA' | 'ESPACIADO' | 'POR_RANGO' | 'FORMULA';
  seccion?: string;
  distancia_pauta_cm?: number;
  tornillos_por_pieza?: number;
  condicion_activacion?: any;
  rangos?: RangoEscala[];
  formula_personalizada?: string;
  es_fijo_override?: boolean;
  observaciones?: string;
  material?: {
    id: number;
    nombre: string;
    costo_base: number;
    unidad_medida?: {
      nombre: string;
      abreviatura: string;
    };
  };
}

export interface PoliticaSeccion {
  id: number;
  seccion_id: number;
  mano_obra_base: number;
  pct_liquidacion_mo: number;
  pct_gastos_seccion: number;
  costo_fabricacion?: number | null;
  pct_trabajadores?: number | null;
  pct_negocio?: number | null;
}

export interface ElementoSeccion {
  id: number;
  seccion_id: number;
  nombre_insumo_original: string;
  material_id_normalizado?: number;
  estado_resolucion: string;
  cantidad: number;
  unidad_medida?: string;
  observaciones?: string;
  precio_unitario?: number;
  costo_subtotal?: number;
}

export interface SeccionProducto {
  id: number;
  producto_id: number;
  nombre: string;
  orden: number;
  elementos: ElementoSeccion[];
  politica?: PoliticaSeccion;
  costos_produccion: CostoProduccionSeccion[];
}

export interface CostoProduccionSeccion {
  id: number;
  seccion_id: number;
  nombre: string;
  porcentaje?: number | null;
  costo_base: number;
}

export const productosService = {
  getProductos: async (search?: string): Promise<Product[]> => {
    const response = await api.get<Product[]>('/producto/', {
      params: search ? { buscar: search } : {},
    });
    return response.data;
  },

  getById: async (id: number): Promise<Product> => {
    const response = await api.get<Product>(`/producto/${id}`);
    return response.data;
  },

  crearProducto: async (product: Omit<Product, 'id'>): Promise<Product> => {
    const response = await api.post<Product>('/producto/', product);
    return response.data;
  },

  actualizarProducto: async (id: number, product: Partial<Product>): Promise<Product> => {
    const response = await api.put<Product>(`/producto/${id}`, product);
    return response.data;
  },

  eliminarProducto: async (id: number): Promise<void> => {
    await api.delete(`/producto/${id}`);
  },

  getReceta: async (productoId: number): Promise<ProductoMaterial[]> => {
    const response = await api.get<ProductoMaterial[]>(`/producto/${productoId}/receta`);
    return response.data;
  },

  getRecetaEstructurada: async (productoId: number): Promise<SeccionProducto[]> => {
    const response = await api.get<SeccionProducto[]>(`/producto/${productoId}/receta-estructurada`);
    return response.data;
  },

  actualizarPoliticaSeccion: async (seccionId: number, data: Partial<PoliticaSeccion>): Promise<PoliticaSeccion> => {
    const response = await api.put<PoliticaSeccion>(`/seccion/${seccionId}/politica`, data);
    return response.data;
  },

  agregarMaterialReceta: async (productoId: number, item: Omit<ProductoMaterial, 'id' | 'producto_id'>): Promise<ProductoMaterial> => {
    const response = await api.post<ProductoMaterial>(`/producto/${productoId}/receta`, item);
    return response.data;
  },

  actualizarMaterialReceta: async (recetaId: number, item: Partial<ProductoMaterial>): Promise<ProductoMaterial> => {
    const response = await api.put<ProductoMaterial>(`/receta/${recetaId}`, item);
    return response.data;
  },

  eliminarMaterialReceta: async (recetaId: number): Promise<void> => {
    await api.delete(`/receta/${recetaId}`);
  },

  getMateriales: async (search?: string): Promise<Material[]> => {
    const response = await api.get<Material[]>('/material/', {
      params: search ? { buscar: search } : {},
    });
    return response.data;
  },

  crearMaterial: async (material: Omit<Material, 'id' | 'unidad_medida'>): Promise<Material> => {
    const response = await api.post<Material>('/material/', material);
    return response.data;
  },

  crearSeccion: async (seccion: { producto_id: number; nombre: string; orden?: number; pct_gastos_seccion?: number | null }): Promise<SeccionProducto> => {
    const response = await api.post<SeccionProducto>('/seccion/', seccion);
    return response.data;
  },

  eliminarSeccion: async (seccionId: number): Promise<void> => {
    await api.delete(`/seccion/${seccionId}`);
  },

  crearElementoSeccion: async (elemento: {
    seccion_id: number;
    nombre_insumo_original: string;
    material_id_normalizado?: number | null;
    cantidad?: number;
    unidad_medida?: string;
    precio_unitario?: number | null;
    observaciones?: string;
  }): Promise<ElementoSeccion> => {
    const response = await api.post<ElementoSeccion>(`/seccion/${elemento.seccion_id}/elemento`, elemento);
    return response.data;
  },

  eliminarElementoSeccion: async (elementoId: number): Promise<void> => {
    await api.delete(`/elemento/${elementoId}`);
  },

  // Costos de producción por sección
  crearCostoProduccion: async (data: { seccion_id: number; nombre: string; porcentaje?: number | null; costo_base: number }): Promise<CostoProduccionSeccion> => {
    const response = await api.post<CostoProduccionSeccion>(`/seccion/${data.seccion_id}/costo-produccion`, data);
    return response.data;
  },

  actualizarCostoProduccion: async (itemId: number, data: Partial<CostoProduccionSeccion>): Promise<CostoProduccionSeccion> => {
    const response = await api.put<CostoProduccionSeccion>(`/seccion-costo-produccion/${itemId}`, data);
    return response.data;
  },

  eliminarCostoProduccion: async (itemId: number): Promise<void> => {
    await api.delete(`/seccion-costo-produccion/${itemId}`);
  },
};

