# Auditoría de riesgos — Hallazgos y correcciones

**Fecha:** 2026-08-05
**Alcance:** módulos de dinero (cotización → pedido → venta → pago), producción/costeo, inventario, compras, seguridad, gastos, clientes, proveedores y concurrencia.
**Método:** suite de tests de riesgo (`backend/test/`) contra BD real (PostgreSQL), con limpieza estricta del teardown.
**Resultado:** 67/67 tests en verde (fase 1: 56; fase 2: +11), 0 residuos en BD, frontend compila.

---

## Resumen fase 1

| # | Severidad | Módulo | Bug | Fix |
|---|-----------|--------|-----|-----|
| M1 | Crítica | Dinero | Abono VES con TRM se comparaba COP contra USD → rechazo injusto o 500 | `tasa_pago = TRM / tasa_cotización` |
| M2 | Crítica | Dinero | `pago_metodo_pago_check` de BD no permitía `EFECTIVO_VES` | Constraint corregido (BD + esquema.sql + migración Alembic) |
| M3 | Alta | Dinero | Margen calculado > 999.99 reventaba `numeric(5,2)` → 500 | Clamp a 999.99 |
| M4 | Alta | Dinero | Producto inexistente daba 409 engañoso "ya convertida" | Validación previa → 400 claro |
| M5 | Alta | Dinero | Eliminar factura con pagos → 500 `NotNullViolation` | Exigir anular/eliminar pagos → 400 |
| C1 | Alta | Costeo | `tipo_escala` ignorado al escalar recetas (LINEAL 2x daba 2.0, no 4.0) | `_calcular_cantidad_material` aplica todas las escalas |
| C2 | Media | Producción | Finalizar orden sin etapas completaba igual | Rechazo si `n_etapas == 0` |
| C3 | Alta | Producción | Pedido TERMINADO con líneas sin producir (creaba envío a medias) | Requiere `todas las líneas finalizadas` |
| C4 | Alta | Producción | Finalizar pisaba el costo calculado por el supervisor | Auto-cálculo solo si no hay costo previo |
| C5 | Media | Producción | Consumo de material con etapa inexistente → 500 | Validación → 400 |
| C6 | Media | Producción | Eliminar consumo no reponía stock ni borraba el gasto | Movimiento ENTRADA inverso + borrado de Gasto |
| M1b | Media | Producción | Cancelar compra RECIBIDA no revertía stock | Movimientos SALIDA por cada ENTRADA |
| M1c | Media | Compras | Response model (`detalle` vs `detalles`) → 500 | `validation_alias="detalles"` |

---

## Resumen fase 2

| # | Severidad | Módulo | Bug | Fix |
|---|-----------|--------|-----|-----|
| F2-1 | Crítica | Dinero | Abono USD sobre cotización COP se convertía 1 USD = 1 COP (la cotización COP fija tasa 1.0) | `_derivar_tasa_pago` COP→USD no deducible → exige TRM (`tasa = TRM / tasa_venta = TRM`) |
| F2-2 | Alta | Dinero | Facturar pedido en moneda distinta a la cotización → total inflado ~4000× | Rechazo 400 (los precios están fijados en la moneda de la cotización) |
| F2-3 | Alta | Dinero | `porcentaje_ganancia` sin clamp al facturar → 500 (mismo bug que M3 pero en ventas) | Clamp a 999.99 en `crear_venta_desde_pedido` |
| F2-4 | Alta | Inventario | `registrar_movimiento` hacía `commit()` interno → compras/consumos a medias si fallaba un paso posterior | `flush()` + commit delegado al caller (router de inventario commitea) |
| F2-5 | Alta | Clientes | DELETE cliente con pedidos/ventas → 500 `IntegrityError` | 409 con mensaje claro |
| F2-6 | Alta | Proveedores | DELETE proveedor con compras → 500 `IntegrityError` | 409 con mensaje claro |
| F2-7 | Alta | Materiales | DELETE material con receta/inventario/compras → 500 `IntegrityError` | 409 con mensaje claro |
| F2-8 | Media | Gastos | `tipo_gasto_id`/`moneda_id` inexistentes → 500 `IntegrityError` | Validación de FK → 400 |
| F2-9 | Media | Gastos | PATCH con `null` en NOT NULL → TypeError/IntegrityError → 500 | 400 explícito |
| F2-10 | Media | Gastos | Gasto USD sin tasa se registraba como COP (1:1) | Tasa se resuelve por `moneda.codigo` + tasas vigentes |
| F2-11 | Media | Cotizaciones | `tasa_cambio <= 0` aceptada → total_base corrupto | `Field(gt=0)` + recálculo en `actualizar_cotizacion` |
| F2-12 | Media | Seguridad | Rotación de refresh token no atómica (race: dos refrescos válidos del mismo token) | `with_for_update()` en la revocación |
| F2-13 | Baja | Varios | Paginación sin `ORDER BY` (envíos/clientes/proveedores) → páginas repetidas | `ORDER BY id DESC` |
| F2-14 | Baja | Proveedores | `EmailStr` en salida → `ResponseValidationError` con datos legacy | `str` en `ProveedorResponse` |

Además: `pytest test/` ahora ignora `test_integracion_api.py` (script standalone con `sys.exit`) en `pytest.ini`.

---

## Dinero — flujo cotización → pedido → venta → pago

Archivos: `backend/app/modules/orders/service.py`, `orders/router.py`, `sales/service.py`, `sales/router.py`, `sales/schemas.py`.

### M1 — Abono VES con TRM (crítico)

**Síntoma:** adelanto de 1000 VES a TRM 10 (1 VES = 10 COP) sobre una factura en USD (tasa 3900) lanzaba *"el pago excede el saldo"* (o 500). El error real era una comparación de magnitudes en monedas distintas.

**Causa raíz:** la TRM indicada por el usuario es *COP por unidad de la moneda del pago* (p. ej. 1 VES = 10 COP), pero `crear_pago` trataba `tasa_cambio` como *"1 VES = X USD"* y convertía 1000 VES × 10 = 10000 USD contra un saldo de ~500 USD.

**Fix:** nueva función `_derivar_tasa_pago(db, moneda_venta, moneda_pago, tasa_cotizacion)` en `orders/service.py`:
- Misma moneda → `tasa = 1.0` (derivada).
- COP↔USD → se deriva de la TRM congelada en la cotización (`tasa` o `1/tasa`).
- Par no deducible (p. ej. VES) → requiere TRM del abono y se normaliza: `tasa_pago = TRM_abono / tasa_cotizacion` = 10/3900 ≈ 0.002564 → **1000 VES = 2.56 USD**, el comportamiento esperado por el negocio.
- Validaciones previas: `tasa_cambio <= 0` y ausencia de método de pago → 400, **antes** de tocar cualquier registro (nada de pedidos/facturas a medias).

### M2 — `EFECTIVO_VES` prohibido en BD (crítico)

**Síntoma:** todo pago en VES fallaba con `CheckViolation` → mapeado a 409 "ya convertida" (falso positivo).

**Causa raíz:** el CHECK `pago_metodo_pago_check` de la BD permitía `EFECTIVO_COP`, `EFECTIVO_USD`, `BANCOLOMBIA`, `BANCARIBE`, `ZELLE`, pero **no** `EFECTIVO_VES`, mientras que la validación de la app sí lo aceptaba.

**Fix en 3 capas:**
1. BD viva: `ALTER TABLE pago DROP CONSTRAINT pago_metodo_pago_check` + re-ADD incluyendo `EFECTIVO_VES`.
2. `backend/esquema.sql` (línea ~969) actualizado.
3. Nueva migración Alembic `backend/alembic/versions/c3f4a5b6c7d8_efectivo_ves_metodo_pago_check.py` (aplicada; DB en head).

### M3 — Overflow de margen (alto)

**Síntoma:** convertir una cotización sin `porcentaje_ganancia` con costo 1000 y precio 100000 → margen 9900% → `numeric(5,2)` overflow → `DataError` → 500.

**Fix:** `orders/service.py`:
```python
margen = ((float(precio) - float(costo)) / float(costo)) * 100
detalle_dict["porcentaje_ganancia"] = min(999.99, round(margen, 2))
```

### M4 — Producto inexistente → 409 engañoso (alto)

**Síntoma:** producto inexistente en el detalle → `IntegrityError` de FK que el router mapeaba a *"La cotización ya fue convertida a pedido"*.

**Fix:** `convertir_cotizacion_a_pedido` valida la existencia de cada `producto_id` (consulta `Producto.id`) antes de insertar el `DetallePedido` → **400** con mensaje explícito. El 409 queda solo para la idempotencia real de la conversión duplicada.

### M5 — Eliminar factura con pagos → 500 (alto)

**Síntoma:** `DELETE /venta/{id}` con pagos registrados → `NotNullViolation` (SQLAlchemy intentaba `venta_id = NULL` en pagos cuya columna es NOT NULL).

**Fix:** `eliminar_venta` en `sales/service.py` consulta `db_venta.pagos` y lanza `ValueError` → **400** en el router con el mensaje de anular primero los pagos.

### Otros arreglos en el flujo
- Conversión ahora crea la factura automática en la moneda de la cotización (`crear_venta_desde_pedido` con `commit=False` y `permitir_estado_cotizado=True`), registrando el adelanto como primer pago de forma atómica con la conversión.
- Serialización con `SELECT ... FOR UPDATE` para evitar dobles conversiones concurrentes (antes un race → 500).

---

## Producción y costeo

Archivos: `backend/app/modules/productos/cost_service.py`, `production/service.py`, `production/router.py`, `purchases/service.py`, `purchases/schemas.py`.

### C1 — Escalado muerto por `tipo_escala` (alto)

**Síntoma:** productos con receta tomaban un branch temprano que ignoraba `tipo_escala`; un largo 2x en modo LINEAL daba 2.0 en vez de 4.0 → costos por debajo de lo real.

**Fix:** nuevo helper `_calcular_cantidad_material` en `cost_service.py` que aplica `tipo_escala` (`FIJO`, `LINEAL`, `AREA`, `ESPACIADO`, `POR_RANGO`, `FORMULA`) sobre `cantidad_calculada` y `costo_linea`.

### C2 — Finalizar orden sin etapas (media)

**Síntoma:** una `OrdenProduccion` sin etapas se podía marcar FINALIZADA.

**Fix:** rechazo con 400/422 si `n_etapas == 0` al finalizar.

### C3 — Pedido TERMINADO con líneas sin producir (alto)

**Síntoma:** bastaba finalizar **una** orden para marcar todo el pedido TERMINADO y crear el envío, aunque quedaran otras líneas sin producción.

**Fix:** el pedido pasa a TERMINADO solo si `n_detalles > 0 and n_ordenes_finalizadas == n_detalles`.

### C4 — Costo pisado (alto)

**Síntoma:** finalizar re-calculaba el costo con ganancia 0% sobreescribiendo el costo ya calculado por el supervisor (y descuadrando márgenes de pedidos previos).

**Fix:** auto-cálculo de costo solo si aún no hay costo registrado (`if not obtener_costo_por_orden`).

### C5 — Consumo con etapa inexistente → 500 (media)

**Fix:** `crear_consumo_material` valida la existencia de la `etapa_produccion_id` → 400.

### C6 — Eliminar consumo no reponía stock (media)

**Síntoma:** al borrar un consumo de material, el stock quedaba descontado para siempre y el Gasto automático quedaba huérfano.

**Fix:** `eliminar_consumo_material` crea un movimiento ENTRADA inverso por el mismo material y borra el Gasto asociado.

### M1b — Cancelar compra RECIBIDA no revertía stock (media)

**Síntoma:** pasar una compra de RECIBIDA a CANCELADA/BORRADOR/EMITIDA dejaba el stock incrementado sin revertir.

**Fix:** `actualizar_compra` en `purchases/service.py` detecta la salida del estado RECIBIDA y crea movimientos SALIDA por cada ENTRADA registrada.

### M1c — Response model de compras → 500 (media)

**Síntoma:** `detalle` (singular) en el schema vs `detalles` (plural) en el modelo → `ResponseValidationError`.

**Fix:** `Field(validation_alias="detalles")` en `purchases/schemas.py`.

---

## Infraestructura de tests

Archivo: `backend/test/conftest.py`.

- **`Cleaner`**: borra en orden inverso de FK en teardown, permitiendo que la suite completa deje **0 filas de prueba** en la BD.
- **`registrar_venta_de_pedido(client, cleaner, pedido_id)`**: registra la factura auto-generada por la conversión (+ `detalle_venta` + pagos). Sin esto, borrar el pedido fallaba por FK `venta_pedido_id_fkey`.
- **`registrar_inventario_de_material(db, cleaner, material_id)`**: registra todos los `movimiento_inventario` e `inventario` de un material, incluyendo los creados internamente por consumos, reversas y compras RECIBIDA.
- **`ORDEN_LIMPIEZA`**: corregido — `inventario` y `movimiento_inventario` se limpian **antes** que `material` (fallaba FK `inventario_material_id_fkey`).

---

## Cobertura de la suite

| Archivo | Tests | Cubre |
|---|---|---|
| `test_money_flow.py` | 15 | flujo completo, saldos, multi-moneda, idempotencia, eliminación, CxC |
| `test_money_core.py` | 8 | unitarios: `_derivar_tasa_pago`, `_calcular_por_rango`, evaluador de condiciones |
| `test_production_risks.py` | 8 | C1–C6 + M1 (producción/compra) |
| `test_concurrency.py` | 4 | pagos/conversiones/consumos/salidas simultáneos |
| `test_security.py` | 14 | JWT, refresh rotation, permisos por módulo |
| `test_auditoria2.py` | 11 | regresiones fase 2: TRM COP→USD, DELETE con FK 409, gastos, cotización, moneda de venta |
| `test_iqe.py` + `test_permisos.py` | 7 | legacy (verificación de no-regresión) |

**Comando de verificación:**
```sh
cd backend && source venv/bin/activate
python -m pytest test/ -s   # verificar sin advertencias CLEANUP
```

---

## Notas de reproducibilidad

- La BD vive en head de Alembic (`c3f4a5b6c7d8`). Deploy fresco: `alembic upgrade head` deja el constraint correcto.
- Los datos reales (clientes, productos, materiales, compras, órdenes) no fueron tocados; solo se eliminaron filas de prueba `test_%`.
- Frontend: `npm run build` verificado (TypeScript strict).
