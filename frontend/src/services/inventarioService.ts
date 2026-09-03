import api from './api';

export interface InventarioItem {
  id: number;
  material_id: number;
  material_nombre: string;
  ubicacion_id: number;
  ubicacion_nombre: string;
  cantidad: number;
  // Dimensiones de lámina (cm) si el material es laminar + categoría de inventario
  material_largo_cm?: number;
  material_ancho_cm?: number;
  material_unidad?: string;
  categoria_inventario_id?: number;
  categoria_inventario_nombre?: string;
  created_at: string;
  updated_at: string;
  // additional field for table rendering (e.g. minimum stock, unit if needed, we can get from material)
  material?: {
    id: number;
    nombre: string;
    unidad_medida?: {
      abreviatura: string;
    };
    costo_base: number;
    largo_cm?: number | null;
    ancho_cm?: number | null;
  };
}

export interface SobranteLamina {
  id: number;
  material_id: number;
  material_nombre?: string;
  material_largo_cm?: number;
  material_ancho_cm?: number;
  ubicacion_id: number;
  ubicacion_nombre?: string;
  largo_cm: number;
  ancho_cm: number;
  area_cm2: number;
  estado: 'DISPONIBLE' | 'CONSUMIDO' | 'DESECHADO';
  consumo_origen_id?: number;
  consumo_origen_tipo?: string;
  observaciones?: string;
  created_at?: string;
  updated_at?: string;
}

export interface SobranteLaminaCreate {
  material_id: number;
  ubicacion_id: number;
  largo_cm: number;
  ancho_cm: number;
  observaciones?: string;
}

export interface CategoriaInventario {
  id: number;
  nombre: string;
  tipo: 'MATERIAL' | 'PRODUCTO';
  orden: number;
}

export interface AlertaStock {
  material_id: number;
  material_nombre: string;
  stock_actual: number;
  stock_minimo: number;
  ubicacion_id: number;
  ubicacion_nombre: string;
}

export interface MovimientoCreate {
  material_id: number;
  ubicacion_id: number;
  tipo: 'ENTRADA' | 'SALIDA' | 'AJUSTE' | 'DAÑO' | 'DEVOLUCION';
  cantidad: number;
  costo_unitario?: number;
  referencia_tipo?: string;
  referencia_id?: number;
  observaciones?: string;
  /** "La llevada": flete/aduana pagada además de la compra (opcional). Genera el gasto "FLETE / LLEVADA" desde la misma cuenta. */
  llevada?: number;
  /** ENTRADA pagada de contado: genera gasto "COMPRA DE INSUMOS" + salida de caja. */
  pagado_desde_metodo_caja_id?: number;
  /** Moneda en la que sale el dinero de la cuenta (default COP). */
  moneda_pago_id?: number;
  /** Tasa manual "1 [moneda_pago] = X COP". Obligatoria si moneda_pago ≠ COP. */
  tasa_pago?: number;
  /** Proveedor (dónde se compró) — opcional, solo entradas. */
  proveedor_id?: number;
  /** Cliente para el que se compró el material — opcional, solo entradas. */
  cliente_id?: number;
  /** "Fiar": ENTRADA sin pagar → se registra automáticamente la deuda (cuenta por pagar). */
  fiar?: boolean;
}

export interface MovimientoResponse {
  id: number;
  material_id: number;
  ubicacion_id: number;
  tipo: string;
  cantidad: number;
  costo_unitario?: number;
  referencia_tipo?: string;
  referencia_id?: number;
  observaciones?: string;
  llevada?: number;
  proveedor_id?: number;
  proveedor_nombre?: string;
  cliente_id?: number;
  cliente_nombre?: string;
  fecha: string;
  created_at: string;
  updated_at: string;
}

export interface ProductoInventarioItem {
  id: number;
  producto_id: number;
  producto_nombre: string;
  producto_codigo?: string;
  es_reventa?: boolean;
  ubicacion_id: number;
  ubicacion_nombre: string;
  cantidad: number;
  costo_promedio?: number;
  stock_minimo?: number;
  created_at: string;
  updated_at: string;
}

export interface AlertaStockProducto {
  producto_id: number;
  producto_nombre: string;
  stock_actual: number;
  stock_minimo: number;
  ubicacion_id: number;
  ubicacion_nombre: string;
}

export interface MovimientoProductoCreate {
  producto_id: number;
  ubicacion_id: number;
  tipo: 'ENTRADA' | 'SALIDA' | 'AJUSTE' | 'DAÑO' | 'DEVOLUCION';
  cantidad: number;
  costo_unitario?: number;
  referencia_tipo?: string;
  referencia_id?: number;
  observaciones?: string;
  /** "La llevada": flete/aduana pagada además de la compra (opcional). */
  llevada?: number;
  /** ENTRADA pagada de contado: genera egreso automático + salida de esa caja. */
  pagado_desde_metodo_caja_id?: number;
  moneda_pago_id?: number;
  tasa_pago?: number;
  /** Proveedor (dónde se compró) — opcional, solo entradas. */
  proveedor_id?: number;
  /** Cliente para el que se compró el producto — opcional, solo entradas. */
  cliente_id?: number;
}

export interface MovimientoProductoResponse {
  id: number;
  producto_id: number;
  ubicacion_id: number;
  tipo: string;
  cantidad: number;
  costo_unitario?: number;
  referencia_tipo?: string;
  referencia_id?: number;
  observaciones?: string;
  llevada?: number;
  proveedor_id?: number;
  proveedor_nombre?: string;
  cliente_id?: number;
  cliente_nombre?: string;
  fecha: string;
  created_at: string;
  updated_at: string;
}

export interface CostoUnitarioRealMaterial {
  material_id: number;
  costo_compra: number;
  pasada_unitaria: number;
  costo_real: number;
}

export const inventarioService = {
  getInventario: async (params?: { material_id?: number; ubicacion_id?: number }): Promise<InventarioItem[]> => {
    const response = await api.get<InventarioItem[]>('/inventario/', { params });
    return response.data;
  },

  /** Costo real por unidad = compra + "la pasada" (llevada prorrateada de la última entrada). */
  getCostoUnitarioRealMaterial: async (materialId: number): Promise<CostoUnitarioRealMaterial> => {
    const response = await api.get<CostoUnitarioRealMaterial>(`/inventario/material/${materialId}/costo-unitario-real`);
    return response.data;
  },

  getAlertas: async (umbral: number = 8.0): Promise<AlertaStock[]> => {
    const response = await api.get<AlertaStock[]>('/inventario/alertas', {
      params: { umbral },
    });
    return response.data;
  },

  crearMovimiento: async (movimiento: MovimientoCreate): Promise<MovimientoResponse> => {
    const response = await api.post<MovimientoResponse>('/inventario/movimiento', movimiento);
    return response.data;
  },

  getKardex: async (materialId: number, limit: number = 100): Promise<MovimientoResponse[]> => {
    const response = await api.get<MovimientoResponse[]>(`/inventario/movimientos/material/${materialId}`, {
      params: { limit },
    });
    return response.data;
  },

  // ---- Inventario de PRODUCTOS (terminados / de reventa) ----
  getInventarioProductos: async (params?: { producto_id?: number; ubicacion_id?: number; solo_reventa?: boolean }): Promise<ProductoInventarioItem[]> => {
    const response = await api.get<ProductoInventarioItem[]>('/inventario/productos', { params });
    return response.data;
  },

  getAlertasProductos: async (umbral: number = 8.0): Promise<AlertaStockProducto[]> => {
    const response = await api.get<AlertaStockProducto[]>('/inventario/productos/alertas', {
      params: { umbral },
    });
    return response.data;
  },

  crearMovimientoProducto: async (movimiento: MovimientoProductoCreate): Promise<MovimientoProductoResponse> => {
    const response = await api.post<MovimientoProductoResponse>('/inventario/producto/movimiento', movimiento);
    return response.data;
  },

  getKardexProducto: async (productoId: number, limit: number = 100): Promise<MovimientoProductoResponse[]> => {
    const response = await api.get<MovimientoProductoResponse[]>(`/inventario/movimientos/producto/${productoId}`, {
      params: { limit },
    });
    return response.data;
  },

  // ---- Sobrantes de láminas (retazos de materiales laminares) ----
  getSobrantes: async (params?: { material_id?: number; estado?: string; ubicacion_id?: number }): Promise<SobranteLamina[]> => {
    const response = await api.get<SobranteLamina[]>('/inventario/sobrantes', { params });
    return response.data;
  },

  crearSobrante: async (datos: SobranteLaminaCreate): Promise<SobranteLamina> => {
    const response = await api.post<SobranteLamina>('/inventario/sobrantes', datos);
    return response.data;
  },

  actualizarSobrante: async (id: number, datos: Partial<SobranteLaminaCreate> & { estado?: string }): Promise<SobranteLamina> => {
    const response = await api.put<SobranteLamina>(`/inventario/sobrantes/${id}`, datos);
    return response.data;
  },

  eliminarSobrante: async (id: number): Promise<void> => {
    await api.delete(`/inventario/sobrantes/${id}`);
  },

  // ---- Categorías de inventario (desglose en la UI) ----
  getCategorias: async (tipo?: 'MATERIAL' | 'PRODUCTO'): Promise<CategoriaInventario[]> => {
    const response = await api.get<CategoriaInventario[]>('/inventario/categorias', {
      params: tipo ? { tipo } : undefined,
    });
    return response.data;
  },

  crearCategoria: async (nombre: string, tipo: 'MATERIAL' | 'PRODUCTO', orden = 0): Promise<CategoriaInventario> => {
    const response = await api.post<CategoriaInventario>('/inventario/categorias', { nombre, tipo, orden });
    return response.data;
  },
};
