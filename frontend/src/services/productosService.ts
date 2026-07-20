import api from './api';

export interface TipoProducto {
  id: number;
  nombre: string;
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
  tipo_producto?: TipoProducto;
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

export interface ProductoMaterial {
  id: number;
  producto_id: number;
  material_id: number;
  cantidad_base: number;
  tipo_escala: 'FIJO' | 'LINEAL' | 'AREA' | 'ESPACIADO' | 'POR_RANGO' | 'FORMULA';
  distancia_pauta_cm?: number;
  tornillos_por_pieza?: number;
  condicion_activacion?: any;
  rangos?: any;
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
};
