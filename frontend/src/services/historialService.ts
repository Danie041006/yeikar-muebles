import api from './api';
import type { AdjuntoInfo } from './adjuntosService';

export type { AdjuntoInfo };

export interface Dimensiones {
  alto?: number | null;
  ancho?: number | null;
  largo?: number | null;
}

export interface ClienteExp {
  id: number;
  nombre: string;
  cedula?: string | null;
  telefono?: string | null;
  direccion?: string | null;
  ciudad?: string | null;
  estado?: string | null;
  fecha_registro?: string | null;
}

export interface DetalleCotizacionExp {
  producto_id?: number | null;
  material_id?: number | null;
  tipo_item?: 'FABRICADO' | 'REVENTA' | 'INSUMO';
  producto_nombre?: string | null;
  cantidad: number;
  precio: number;
  dimensiones?: Dimensiones;
  costo_materiales?: number | null;
  costo_mano_obra?: number | null;
  costo_gastos?: number | null;
  costo_total?: number | null;
  observaciones?: string | null;
  receta_personalizada?: unknown;
  fotos?: AdjuntoInfo[];
}

export interface CotizacionExp {
  id: number;
  fecha: string;
  estado: string;
  total_estimado: number;
  moneda?: string | null;
  tasa_cambio?: number | null;
  total_en_moneda_base?: number | null;
  observaciones?: string | null;
  creado_por?: string | null;
  created_at?: string | null;
  detalles: DetalleCotizacionExp[];
}

export interface PedidoExp {
  id: number;
  fecha: string;
  estado: string;
  fecha_entrega_estimada?: string | null;
  observaciones?: string | null;
  creado_por?: string | null;
  cotizacion_id?: number | null;
  created_at?: string | null;
}

export interface ConsumoExp {
  id: number;
  material_id?: number | null;
  material_nombre?: string | null;
  cantidad: number;
  costo_unitario?: number | null;
  seccion?: string | null;
  fecha?: string | null;
  creado_por?: string | null;
  observaciones?: string | null;
}

export interface ManoObraExp {
  id: number;
  empleado_nombre?: string | null;
  monto: number;
  porcentaje_recargo?: number | null;
  pagado: boolean;
  observaciones?: string | null;
}

export interface EtapaExp {
  id: number;
  area_id?: number | null;
  area_nombre?: string | null;
  empleado_responsable?: string | null;
  empleados_adicionales?: string[];
  estado: string;
  fecha_inicio?: string | null;
  fecha_fin?: string | null;
  es_retrabajo: boolean;
  observaciones?: string | null;
  consumos: ConsumoExp[];
  mano_obra: ManoObraExp[];
}

export interface CostoExp {
  costo_material: number;
  costo_mano_obra: number;
  costo_gastos: number;
  precio_impuestos_base?: number | null;
  ganancia_porcentaje?: number | null;
  precio_venta_calculado: number;
  costo_total: number;
}

export interface ProduccionExp {
  orden: {
    id: number;
    estado: string;
    fecha_inicio?: string | null;
    fecha_fin?: string | null;
    creado_por?: string | null;
  };
  etapas: EtapaExp[];
  costo?: CostoExp | null;
}

export interface DetallePedidoExp {
  id: number;
  producto_id?: number | null;
  material_id?: number | null;
  tipo_item?: 'FABRICADO' | 'REVENTA' | 'INSUMO';
  producto_nombre?: string | null;
  cantidad: number;
  precio: number;
  costo_unitario?: number | null;
  porcentaje_ganancia?: number | null;
  dimensiones?: Dimensiones;
  color?: string | null;
  acabado?: string | null;
  descripcion_especifica?: string | null;
  observaciones?: string | null;
  produccion?: ProduccionExp | null;
}

export interface PagoExp {
  id: number;
  fecha: string;
  moneda?: string | null;
  monto: number;
  tasa_cambio?: number | null;
  monto_en_moneda_base: number;
  metodo_pago?: string | null;
  referencia?: string | null;
  observaciones?: string | null;
  recibos: AdjuntoInfo[];
  caja?: {
    cuenta?: string | null;
    tipo?: string | null;
    monto_en_moneda_base?: number | null;
    responsable?: string | null;
    referencia?: string | null;
  } | null;
}

export interface VentaExp {
  id: number;
  fecha: string;
  estado: string;
  moneda?: string | null;
  total: number;
  tasa_cambio?: number | null;
  total_en_moneda_base?: number | null;
  creado_por?: string | null;
  observaciones?: string | null;
  total_pagado: number;
  saldo_pendiente: number;
  detalles: {
    producto_id?: number | null;
    material_id?: number | null;
    tipo_item?: 'FABRICADO' | 'REVENTA' | 'INSUMO';
    producto_nombre?: string | null;
    cantidad: number;
    precio: number;
    costo_unitario?: number | null;
    utilidad?: number | null;
    descuento?: number | null;
  }[];
  pagos: PagoExp[];
}

export interface GastoExp {
  id: number;
  fecha: string;
  descripcion?: string | null;
  monto: number;
  moneda?: string | null;
  monto_en_moneda_base?: number | null;
  area?: string | null;
  creado_por?: string | null;
  observaciones?: string | null;
}

export interface FacturaExp {
  id: number;
  fecha_emision: string;
  estado: string;
  total_usd: number;
  tasa_usd_ves?: number | null;
  base_imponible_bs?: number | null;
  iva_bs?: number | null;
  igtf_bs?: number | null;
  total_bs: number;
  creado_por?: string | null;
  observaciones?: string | null;
  detalles?: {
    producto_id?: number | null;
    material_id?: number | null;
    tipo_item?: 'FABRICADO' | 'REVENTA' | 'INSUMO';
    producto_nombre?: string | null;
    descripcion?: string | null;
    cantidad: number;
    precio_usd: number;
    subtotal_usd: number;
    subtotal_bs: number;
  }[];
}

export interface EnvioExp {
  id: number;
  estado: string;
  guia_despacho?: string | null;
  chofer?: string | null;
  asignado_por?: string | null;
  creado_por?: string | null;
  fecha_salida?: string | null;
  fecha_entrega?: string | null;
  direccion_entrega?: string | null;
  observaciones?: string | null;
  asignaciones?: {
    empleado?: string | null;
    asignado_en?: string | null;
    desasignado_en?: string | null;
  }[];
  ubicaciones?: {
    latitud: number;
    longitud: number;
    capturada_en?: string | null;
    reportado_por?: string | null;
  }[];
}

export interface AuditoriaExp {
  fecha: string;
  accion: string;
  entidad: string;
  entidad_id: string;
  actor?: string | null;
  cambios?: Record<string, unknown> | null;
}

export interface Expediente {
  cliente?: ClienteExp | null;
  cotizacion?: CotizacionExp | null;
  pedido?: PedidoExp | null;
  detalles_pedido: DetallePedidoExp[];
  venta?: VentaExp | null;
  gastos: GastoExp[];
  facturas: FacturaExp[];
  envio?: EnvioExp | null;
  auditoria: AuditoriaExp[];
  factura_entrada?: { id: number; fecha_emision: string; estado: string; total_usd: number; total_bs: number; creado_por?: string | null };
  envio_entrada?: { id: number; estado: string; guia_despacho?: string | null; fecha_salida?: string | null; fecha_entrega?: string | null };
}

export interface ClienteResumen {
  cliente: ClienteExp;
  resumen: {
    cotizaciones: { id: number; fecha: string; estado: string; total_estimado: number; moneda?: string | null }[];
    pedidos: { id: number; fecha: string; estado: string; cotizacion_id: number }[];
    ventas: { id: number; fecha: string; estado: string; moneda?: string | null; total: number; total_pagado: number }[];
    facturas: { id: number; fecha_emision: string; estado: string; total_bs: number }[];
    envios: { id: number; estado: string; guia_despacho?: string | null; fecha_salida?: string | null }[];
  };
}

export const historialService = {
  fichaCotizacion: (id: number): Promise<Expediente> => api.get(`/historial/cotizacion/${id}`).then((r) => r.data),
  fichaPedido: (id: number): Promise<Expediente> => api.get(`/historial/pedido/${id}`).then((r) => r.data),
  fichaFactura: (id: number): Promise<Expediente> => api.get(`/historial/factura/${id}`).then((r) => r.data),
  fichaEnvio: (id: number): Promise<Expediente> => api.get(`/historial/envio/${id}`).then((r) => r.data),
  fichaCliente: (id: number): Promise<ClienteResumen> => api.get(`/historial/cliente/${id}`).then((r) => r.data),
};