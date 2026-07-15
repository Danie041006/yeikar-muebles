# Flujo de Producción en YEIKAR

## Descripción General
YEIKAR fabrica muebles a medida (camas, mesas de noche, colchones, etc.) y también vende electrodomésticos. El flujo de producción sigue estas etapas:

1. **Cotización** → El vendedor crea una cotización para el cliente.
2. **Pedido** → El cliente aprueba y se genera un pedido.
3. **Producción** → Por cada producto del pedido, se genera una orden de producción.
4. **Etapas** → La orden pasa por etapas (ebanistería, pintura, tapicería, terminación, etc.).
5. **Consumo de Materiales** → Cada etapa registra los materiales usados (madera, MDF, espuma, etc.).
6. **Mano de Obra** → Se asignan empleados a cada etapa con su costo.
7. **Costos** → Se consolida costo de materiales + mano de obra + gastos.
8. **Venta** → Una vez producido, se registra la venta y los pagos.

## Estados de las Entidades

### Pedido
- `COTIZADO` → Inicial desde cotización
- `APROBADO` → Cliente acepta
- `PRODUCCION` → En fábrica
- `PAUSADO` → Por falta de materiales o decisión
- `TERMINADO` → Fabricación completada
- `ENTREGADO` → Entregado al cliente
- `CANCELADO`

### Orden de Producción
- `PENDIENTE` → Esperando inicio
- `EN_PRODUCCION` → En alguna etapa activa
- `PAUSADA`
- `FINALIZADA`
- `CANCELADA`

### Etapa de Producción
- `ASIGNADA` → Responsable asignado, no iniciada
- `EN_PROCESO`
- `PAUSADA`
- `COMPLETADA`

## Cálculo de Costos
- **Costo Material**: Suma de cantidades × costo unitario de materiales consumidos.
- **Costo Mano de Obra**: Suma de montos de mano_obra por etapa + porcentaje de recargo.
- **Gastos**: Asignación de gastos operativos (pueden distribuirse por horas o producto).
- **Precio de Venta Calculado**: (Costo Total) × (1 + %Ganancia/100) + Impuestos.
- **Monedas**: Soporta COP, USD, VES. Los costos se registran en la moneda de la transacción y se convierten mediante tasas de cambio históricas.

## Integración con Inventario
- Los materiales se consumen de la tabla `inventario` (cantidad actual por ubicación).
- Cada consumo genera un registro en `movimiento_inventario` con tipo `SALIDA`.
- Las compras de materiales generan `ENTRADA` en inventario.

## Reportes Clave
- Costo de producción por orden.
- Rentabilidad por producto.
- Stock actual por ubicación.
- Historial de movimientos.
- Ventas por cliente, por moneda.