import { expect, test, type Page } from '@playwright/test';

test.describe.configure({ timeout: 30_000 });

// API interceptada: estas pruebas de interfaz no registran compras ni dinero real.
const material = { id: 101, nombre: 'MATERIAL QA', unidad_medida_id: 2, unidad_medida: { nombre: 'Unidad', abreviatura: 'Ud' }, costo_base: 1000, activo: true, departamento: 'TAPICERIA' };
const monedas = [{ id: 1, nombre: 'Pesos', codigo: 'COP', simbolo: '$', activo: true }];
const cuentas = [{ id: 1, nombre: 'Efectivo QA', moneda_id: 1, moneda_codigo: 'COP' }, { id: 2, nombre: 'Banco QA', moneda_id: 1, moneda_codigo: 'COP' }];
const captura = {
  operacion_id: 'fe162cb9-a72b-4104-a91a-90d2462be224', fecha: '2026-11-14', proveedor_nombre: 'Proveedor QA', recibido_por: 'Transportista QA', observaciones: 'Factura QA',
  lineas: [{ linea_id: '611b4afc-fcbb-4ae9-a510-d1f742d38eaa', tipo_item: 'MATERIAL', item_id: 101, material_id: 101, movimiento_id: 301, nombre: 'MATERIAL QA', unidad: 'Ud', cantidad: '10', precio_unitario: '1000', moneda_precio_id: 1, tasa_precio_a_cop: '1', descuento_porcentaje: '0', llevada_unitaria: '0', departamento: 'TAPICERIA', cliente_nombre: 'Cliente QA' }],
  pagos: [{ pago_id: '7a33c878-ee75-4424-9578-dcf832712b36', metodo_caja_id: 1, moneda_id: 1, codigo: 'COP', monto: '2000', tasa_cambio: '1', observacion: 'Material de prueba', gasto_id: 401, movimiento_caja_id: 501 }],
};
const resumen = { compra_id: 77, fecha: '2026-11-14T12:00:00', proveedor_nombre: 'Proveedor QA', articulos: 'MATERIAL QA', total_en_moneda_base: '10000', pagado_en_moneda_base: '2000', saldo_actual: '8000', version: 1, historica: false };
const detalle = { ...resumen, datos: captura, original: captura, created_at: '2026-11-14T12:00:00', abonado_posterior: '0', descontado_posterior: '0', historial: [] };

async function prepararInterfaz(page: Page) {
  const enviadas: { ruta: string; captura: Record<string, any> }[] = [];
  await page.addInitScript(() => {
    localStorage.setItem('token', 'qa-interceptada-sin-credenciales');
    localStorage.setItem('yeikar_pin_omitido_1', '1');
  });
  await page.route('**/api/**', async (ruta) => {
    const peticion = ruta.request();
    const direccion = new URL(peticion.url());
    const camino = direccion.pathname;
    if (peticion.method() === 'POST' || peticion.method() === 'PUT') {
      enviadas.push({ ruta: camino, captura: peticion.postDataJSON() });
      return ruta.fulfill({ status: 200, json: { compra_id: 77, total_en_moneda_base: 10000, pagado_en_moneda_base: 5000, saldo_en_moneda_base: 5000, lineas: [] } });
    }
    let respuesta: unknown = [];
    if (camino === '/api/auth/me') respuesta = { id: 1, nombre_usuario: 'qa', nombre: 'Prueba', roles: [{ id: 1, nombre: 'Administrador' }], modulos: [{ modulo: 'inventario', gestionar: true }] };
    else if (camino.includes('/catalogos/moneda/')) respuesta = monedas;
    else if (camino.includes('/catalogos/ubicacion/')) respuesta = [{ id: 1, nombre: 'Depósito principal', tipo: 'DEPOSITO' }];
    else if (camino.includes('/catalogos/unidad-medida/')) respuesta = [{ id: 2, nombre: 'Unidad', abreviatura: 'Ud' }];
    else if (camino.includes('/catalogos/tipo-producto/')) respuesta = [{ id: 2, nombre: 'Reventa' }];
    else if (camino.endsWith('/cuenta/operativas')) respuesta = cuentas;
    else if (camino.endsWith('/material/101')) respuesta = material;
    else if (camino.endsWith('/material/')) respuesta = [material];
    else if (camino.endsWith('/inventario/entradas/77')) respuesta = detalle;
    else if (camino.endsWith('/inventario/entradas')) respuesta = [resumen];
    else if (camino.endsWith('/inventario/')) respuesta = [{ id: 1, material_id: 101, material_nombre: 'MATERIAL QA', ubicacion_id: 1, cantidad: 20 }];
    return ruta.fulfill({ json: respuesta, headers: { 'X-Total-Count': '1' } });
  });
  await page.goto('/inventario');
  await expect(page.getByRole('button', { name: 'Entradas registradas', exact: true })).toBeVisible();
  return enviadas;
}

test('Entrada individual: dos montos explícitos, sin asignar el total a la primera cuenta', async ({ page }) => {
  const enviadas = await prepararInterfaz(page);
  await page.getByText('MATERIAL QA', { exact: true }).first().click();
  await page.getByLabel('Cantidad recibida del material').fill('10');
  await page.getByPlaceholder('Ej. Distribuidora Maderas C.A.').fill('Proveedor QA');
  await page.getByRole('button', { name: 'Agregar pago', exact: true }).click();
  await page.getByLabel('Cuenta / medio 1').selectOption('1:1');
  await page.getByLabel('Monto que salió (COP)', { exact: true }).fill('2000');
  await page.getByRole('button', { name: 'Agregar pago', exact: true }).click();
  await page.getByLabel('Cuenta / medio 2').selectOption('2:1');
  await page.getByLabel('Monto que salió (COP)', { exact: true }).nth(1).fill('3000');
  await expect(page.getByLabel('Monto que salió (COP)', { exact: true }).first()).toHaveValue('2000');
  await expect(page.getByRole('region', { name: 'Pagos de la entrada' })).toContainText('COP 5.000,00');
  await page.getByRole('button', { name: 'Registrar Movimiento', exact: true }).click();
  await expect.poll(() => enviadas.filter((solicitud) => solicitud.ruta.endsWith('/compra-multiple')).length).toBe(1);
  const enviada = enviadas.find((solicitud) => solicitud.ruta.endsWith('/compra-multiple'))!.captura;
  expect(enviada.pagos.map((pago: { monto: number }) => pago.monto)).toEqual([2000, 3000]);
  expect(enviada.lineas).toHaveLength(1);
});

test('Corrección precarga artículos y pagos, y exige revisión antes de enviar', async ({ page }) => {
  const enviadas = await prepararInterfaz(page);
  await page.getByRole('button', { name: 'Entradas registradas', exact: true }).click();
  await page.getByRole('button', { name: 'Corregir entrada', exact: true }).click();
  const modal = page.getByRole('dialog', { name: 'Corregir entrada de inventario' });
  await expect(modal.getByLabel('Proveedor', { exact: true })).toHaveValue('Proveedor QA');
  // Escape cierra el diálogo sin enviar nada (accesibilidad de teclado).
  await page.keyboard.press('Escape');
  await expect(modal).toBeHidden();
  await page.getByRole('button', { name: 'Entradas registradas', exact: true }).click();
  await page.getByRole('button', { name: 'Corregir entrada', exact: true }).click();
  await expect(modal.getByLabel('Cliente / destino (opcional)')).toHaveValue('Cliente QA');
  await expect(modal.getByLabel('Monto que salió (COP)', { exact: true })).toHaveValue('2000');
  await expect(modal.getByLabel('Concepto u observación del pago 1')).toHaveValue('Material de prueba');
  await modal.getByLabel('Monto que salió (COP)', { exact: true }).fill('3000');
  await modal.getByLabel('Motivo de la corrección *').fill('Corregí el monto digitado');
  await modal.getByRole('button', { name: 'Revisar corrección', exact: true }).click();
  await expect(modal.getByText('Revisa antes de confirmar', { exact: true })).toBeVisible();
  expect(enviadas.filter((solicitud) => solicitud.ruta.endsWith('/entradas/77'))).toHaveLength(0);
  await modal.getByRole('button', { name: 'Confirmar corrección', exact: true }).click();
  await expect.poll(() => enviadas.filter((solicitud) => solicitud.ruta.endsWith('/entradas/77')).length).toBe(1);
  const solicitud = enviadas.find((enviada) => enviada.ruta.endsWith('/entradas/77'))!.captura;
  expect(solicitud.entrada.pagos[0].monto).toBe(3000);
  expect(solicitud.entrada.lineas[0].linea_id).toBe(captura.lineas[0].linea_id);
  expect(solicitud.version).toBe(1);
});
