# Diagrama Entidad-Relación (ERD)

## Modelo Visual
Para visualizar el esquema, puedes usar **dbdiagram.io** o **Draw.io** importando el siguiente código (basado en el dump).

```dbml
// Tabla Cliente
Table cliente {
  id bigint [pk]
  nombre varchar(150)
  telefono varchar(50)
  direccion text
  email varchar(120)
  ciudad varchar(100)
  estado varchar(100)
  observaciones text
  fecha_registro date
  created_at timestamp
  updated_at timestamp
}

// Tabla Producto
Table producto {
  id bigint [pk]
  nombre varchar(150)
  codigo varchar(50)
  tipo_producto_id bigint [ref: > tipo_producto.id]
  descripcion text
  activo boolean
  created_at timestamp
  updated_at timestamp
}

// Tabla Pedido
Table pedido {
  id bigint [pk]
  cotizacion_id bigint [ref: > cotizacion.id]
  cliente_id bigint [ref: > cliente.id]
  fecha date
  estado varchar(50)
  observaciones text
  fecha_entrega_estimada date
  created_at timestamp
  updated_at timestamp
}

// Tabla OrdenProduccion
Table orden_produccion {
  id bigint [pk]
  detalle_pedido_id bigint [ref: > detalle_pedido.id]
  fecha_inicio date
  fecha_fin date
  estado varchar(50)
  created_at timestamp
  updated_at timestamp
}

// ... (el resto de tablas son similares)

Relaciones Principales
Cliente → Cotizacion → Pedido → Venta (flujo comercial)

Pedido → DetallePedido → Producto (ítems del pedido)

DetallePedido → OrdenProduccion (uno a uno)

OrdenProduccion → EtapaProduccion → ConsumoMaterial / ManoObra (seguimiento)

Material → Inventario → MovimientoInventario (control de stock)

Proveedor → Compra → DetalleCompra → Material (abastecimiento)

Notas
La mayoría de las tablas tienen created_at y updated_at con triggers automáticos.

Los campos estado tienen CHECK constraints para valores permitidos.

Las claves foráneas tienen ON DELETE RESTRICT o CASCADE según corresponda.