# Esquema de Base de Datos YEIKAR

## Descripción General
La base de datos PostgreSQL 17 está diseñada para soportar todas las operaciones del ERP: clientes, proveedores, inventario, producción, ventas, compras, monedas y control de usuarios.

## Modelo Relacional
El esquema `public` contiene 32 tablas que cubren los siguientes dominios:

### Catálogos Base
- `area`, `cargo`, `tipo_producto`, `tipo_gasto`, `unidad_medida`, `moneda`, `ubicacion`
- `rol` y `usuario_rol` para control de acceso

### Maestros de Negocio
- `cliente`, `proveedor`, `empleado`
- `producto` (catálogo de productos)
- `material` (materias primas e insumos)

### Transacciones Comerciales
- `cotizacion`, `pedido`, `venta`
- `detalle_pedido`, `detalle_venta`
- `compra`, `detalle_compra`
- `pago`

### Producción y Costos
- `orden_produccion` (por cada detalle de pedido)
- `etapa_produccion` (seguimiento por área)
- `consumo_material` (materiales usados por etapa)
- `mano_obra` (costos de personal por etapa)
- `costo_produccion` (consolidado por orden)

### Inventario
- `inventario` (existencias actuales por material/ubicación)
- `movimiento_inventario` (kardex histórico)

### Finanzas
- `gasto` (egresos operativos)
- `tasa_cambio` (histórico de conversión)

## Dump Completo de la Base de Datos

```sql
-- (Aquí pegas TODO el contenido del dump que me diste)
-- Incluye desde "SET statement_timeout = 0;" hasta el final.

Diagrama de Relaciones
Ver el diagrama generado en erd.md o usando herramientas como dbdiagram.io.

Notas sobre la Base de Datos
La base de datos ya está en producción con datos reales de YEIKAR.

El usuario yeikar tiene permisos de lectura (SELECT) sobre todas las tablas; postgres es superusuario.

Se usan triggers (trg_*_updated) para actualizar automáticamente el campo updated_at.

Las restricciones CHECK validan estados y valores negativos.

Cómo Restaurar este Dump
bash
# Crear la base de datos vacía (si no existe)
createdb -U postgres yeikar

# Restaurar el dump
psql -U postgres -d yeikar < database-schema.sql
text

**Importante:** Reemplaza el comentario `-- (Aquí pegas TODO el contenido del dump...)` con el contenido real que me pasaste. Como es muy largo, te sugiero copiarlo directamente desde el archivo que recibiste.

---



