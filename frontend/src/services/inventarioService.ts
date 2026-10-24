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
  /** Opcional: sin ubicación, el backend registra el movimiento en el depósito principal. */
  ubicacion_id?: number;
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
  /** Nombre libre del proveedor: si coincide con un registro se linkea; si no, queda como texto. */
  proveedor_nombre?: string;
  /** Cliente para el que se compró el material — opcional, solo entradas. */
  cliente_id?: number;
  /** Nombre libre del cliente (misma mecánica que el proveedor). */
  cliente_nombre?: string;
  /** Zona del taller a la que va la compra — opcional, solo entradas (no cambia el departamento del insumo). */
  departamento?: string;
  /** Quién trajo/entregó la compra (texto libre) — opcional, solo entradas. */
  recibido_por?: string;
  /** Quién recibió/consumió el ítem — opcional, solo salidas de oficina. */
  consumido_por?: string;
  /** "Fiar": ENTRADA sin pagar → se registra automáticamente la deuda (cuenta por pagar). */
  fiar?: boolean;
  /** % de descuento aplicado (el neto ya viaja en costo_unitario); queda en el libro. */
  descuento_porcentaje?: number;
  /** Fecha real del movimiento (YYYY-MM-DD). Sin ella: hoy. No admite futuras. */
  fecha?: string;
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
  departamento?: string | null;
  recibido_por?: string | null;
  consumido_por?: string | null;
  fecha?: string | null;
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
  /** Nombre libre del proveedor (se linkea si coincide con un registro). */
  proveedor_nombre?: string;
  /** Cliente para el que se compró el producto — opcional, solo entradas. */
  cliente_id?: number;
  /** Nombre libre del cliente (misma mecánica que el proveedor). */
  cliente_nombre?: string;
  /** "Fiar": ENTRADA sin pagar → cuenta por pagar (igual que en insumos). */
  fiar?: boolean;
  /** % de descuento aplicado (el neto ya viaja en costo_unitario); queda en el libro. */
  descuento_porcentaje?: number;
  /** Fecha real del movimiento (YYYY-MM-DD). Sin ella: hoy. No admite futuras. */
  fecha?: string;
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
  fecha?: string | null;
  created_at: string;
  updated_at: string;
}

export interface CostoUnitarioRealMaterial {
  material_id: number;
  costo_compra: number;
  pasada_unitaria: number;
  costo_real: number;
}

// ---- Libro de Entradas y Salidas (consulta por rango de fechas) ----
export interface LibroFila {
  id: number;
  item_tipo: 'MATERIAL' | 'PRODUCTO' | 'CRUDO';
  item_id: number;
  item_nombre: string;
  unidad?: string | null;
  categoria?: string | null;
  fecha: string;
  tipo: 'ENTRADA' | 'SALIDA' | 'DEVOLUCION' | 'DANO';
  cantidad: number;
  costo_unitario?: number | null;
  costo_total?: number | null;
  llevada?: number | null;
  zona: string;
  ubicacion?: string | null;
  origen: string;
  proveedor?: string | null;
  cliente?: string | null;
  recibido_por?: string | null;
  consumido_por?: string | null;
  observaciones?: string | null;
  /** Registro de la compra (solo insumos): cuenta de pago, descuento y fiar. */
  descuento?: number | null;
  pagado_desde?: string | null;
  fiado?: boolean;
  fiado_a?: string | null;
  fiado_estado?: string | null;
}

export interface LibroZona {
  zona: string;
  label: string;
  movimientos: number;
  costo: number;
  sin_costo: number;
}

export interface LibroResumen {
  lado: string;
  desde: string;
  hasta: string;
  movimientos: number;
  costo_total: number;
  movimientos_sin_costo: number;
  por_zona: LibroZona[];
}

export interface LibroEntradasSalidas {
  resumen: LibroResumen;
  filas: LibroFila[];
  truncado: boolean;
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

  // ---- Libro de Entradas y Salidas ----
  getLibro: async (params: {
    desde: string;
    hasta: string;
    lado: 'ENTRADAS' | 'SALIDAS';
    tipo_item?: 'TODOS' | 'MATERIAL' | 'PRODUCTO' | 'CRUDO';
    zona?: string;
    buscar?: string;
    categoria_id?: number;
    tipo_producto_id?: number;
  }): Promise<LibroEntradasSalidas> => {
    const response = await api.get<LibroEntradasSalidas>('/inventario/libro', { params });
    return response.data;
  },
};
