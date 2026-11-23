import { expect, test, type Locator, type Page } from '@playwright/test';
import type { PagoEntradaCreate } from '../src/services/inventarioService';

test.describe.configure({ timeout: 30_000 });
test.use({ hasTouch: true });

// Todas las llamadas están interceptadas: ninguna prueba registra dinero real.
const material = { id: 101, nombre: 'INSUMO QA PAGOS', unidad_medida_id: 2, unidad_medida: { nombre: 'Unidad', abreviatura: 'Ud' }, costo_base: 1000, activo: true };
const producto = { id: 102, nombre: 'PRODUCTO QA PAGOS', es_reventa: true, tipo_producto_id: 2, moneda_id: 1, moneda: { id: 1, codigo: 'COP' }, activo: true };
const monedas = [{ id: 1, codigo: 'COP', nombre: 'Pesos', activo: true }, { id: 2, codigo: 'USD', nombre: 'Dólares', activo: true }];
const cuentas = [
  { id: 1, nombre: 'Banco QA', moneda_id: 1, moneda_codigo: 'COP' },
  { id: 2, nombre: 'Efectivo QA', moneda_id: 1, moneda_codigo: 'COP' },
  { id: 3, nombre: 'Dólares QA', moneda_id: 2, moneda_codigo: 'USD' },
];
const movimiento = { id: 301, material_id: 101, tipo: 'ENTRADA', cantidad: 4, costo_unitario: 1000, llevada: 800, fecha: '2026-11-10T12:00:00', pagado_desde_metodo_caja_id: 1, moneda_pago_id: 1, fiar: false };
type Captura = { pagos?: PagoEntradaCreate[]; llevada?: number; costo_unitario?: number; pagos_incluyen_llevada?: boolean };

async function preparar(page: Page, detalle?: object) {
  const enviadas: { ruta: string; captura: Captura }[] = [];
  await page.addInitScript(() => {
    localStorage.setItem('token', 'qa-sin-credenciales-reales');
    localStorage.setItem('yeikar_pin_omitido_1', '1');
  });
  await page.route('**/api/**', async (ruta) => {
    const peticion = ruta.request();
    const camino = new URL(peticion.url()).pathname;
    if (peticion.method() !== 'GET') {
      if (camino.includes('/inventario/')) enviadas.push({ ruta: camino, captura: peticion.postDataJSON() });
      return ruta.fulfill({ status: 200, json: { ...movimiento, ...peticion.postDataJSON() } });
    }
    let respuesta: unknown = [];
    if (camino === '/api/auth/me') respuesta = { id: 1, nombre_usuario: 'qa', roles: [{ id: 1, nombre: 'Administrador' }], modulos: [{ modulo: 'inventario', gestionar: true }] };
    else if (camino.includes('/catalogos/moneda/')) respuesta = monedas;
    else if (camino.includes('/catalogos/ubicacion/')) respuesta = [{ id: 1, nombre: 'Depósito QA', tipo: 'DEPOSITO' }];
    else if (camino.includes('/catalogos/unidad-medida/')) respuesta = [{ id: 2, nombre: 'Unidad', abreviatura: 'Ud' }];
    else if (camino.includes('/catalogos/tipo-producto/')) respuesta = [{ id: 2, nombre: 'Reventa' }];
    else if (camino.endsWith('/cuenta/operativas')) respuesta = cuentas;
    else if (camino === '/api/v1/material/101') respuesta = material;
    else if (camino === '/api/v1/material/') respuesta = [material];
    else if (camino === '/api/v1/producto/102') respuesta = producto;
    else if (camino === '/api/v1/producto/') respuesta = [producto];
    else if (camino.endsWith('/inventario/movimiento/301')) respuesta = { ...movimiento, ...detalle };
    else if (camino.endsWith('/inventario/movimientos/material/101')) respuesta = [movimiento];
    else if (camino.endsWith('/inventario/')) respuesta = [{ id: 1, material_id: 101, ubicacion_id: 1, cantidad: 20 }];
    return ruta.fulfill({ json: respuesta, headers: { 'X-Total-Count': '1' } });
  });
  await page.goto('/inventario');
  await page.getByRole('row', { name: /INSUMO QA PAGOS/ }).click();
  await expect(page.getByRole('form', { name: 'Movimiento de insumo', exact: true })).toBeVisible();
  return enviadas;
}

async function elegirPrincipal(form: Locator, nombre: string) {
  const cuenta = cuentas.find((c) => c.nombre === nombre)!;
  await form.getByRole('combobox', { name: 'Elige la cuenta si se pagó...', exact: true })
    .selectOption(`${cuenta.id}:${cuenta.moneda_id}`);
}

async function dividirPago(form: Locator, principal: string, moneda = 'COP') {
  await form.getByRole('button', { name: /Se pagó parte con otra cuenta/ }).click();
  await form.getByLabel(`Monto de la cuenta principal (${moneda})`, { exact: true }).fill(principal);
  await form.getByLabel('Cuenta extra 1', { exact: true }).selectOption('2:1');
  await form.getByLabel('Monto del pago extra 1 (COP)', { exact: true }).fill('800');
}

for (const caso of [
  { nombre: 'con flete', flete: '200', descuento: '', principal: '4000', total: '4.800' },
  { nombre: 'sin flete', flete: '', descuento: '', principal: '3200', total: '4.000' },
  { nombre: 'con descuento y flete', flete: '200', descuento: '10', principal: '3600', total: '4.400' },
]) {
  test(`Insumo ${caso.nombre}: aviso, cuadre y envío respetan cada cuenta`, async ({ page }) => {
    const enviadas = await preparar(page);
    const form = page.getByRole('form', { name: 'Movimiento de insumo', exact: true });
    await form.getByLabel('Cantidad', { exact: true }).fill('4');
    await form.getByLabel('Flete por unidad', { exact: true }).fill(caso.flete);
    if (caso.descuento) {
      await form.getByPlaceholder('Ej: 10', { exact: true }).fill(caso.descuento);
    }
    await elegirPrincipal(form, 'Banco QA');
    await dividirPago(form, caso.principal);
    await expect(form.getByText(/Se descontarán/)).toContainText(Number(caso.principal).toLocaleString('es-CO'));
    await expect(form.getByText(/Pagado:/)).toContainText(`Compra: ${caso.total} COP`);
    await expect(form.getByText(/Sobran|Faltan/)).toHaveCount(0);
    // Agregar una tercera cuenta no cambia ninguno de los dos montos escritos.
    await form.getByRole('button', { name: 'Agregar otro pago' }).click();
    await expect(form.getByLabel('Monto de la cuenta principal (COP)', { exact: true })).toHaveValue(caso.principal);
    await expect(form.getByLabel('Monto del pago extra 1 (COP)', { exact: true })).toHaveValue('800');
    await form.getByTitle('Quitar este pago', { exact: true }).last().click();
    await form.getByRole('button', { name: 'Registrar Movimiento', exact: true }).click();
    await expect.poll(() => enviadas.length).toBe(1);
    expect(enviadas[0].captura.pagos?.map((p) => p.monto)).toEqual([Number(caso.principal), 800]);
    expect(enviadas[0].captura.pagos_incluyen_llevada).toBe(true);
    expect(enviadas[0].captura.llevada ?? 0).toBe(caso.flete ? 800 : 0);
  });
}

test('USD principal convierte hacia COP y la tasa del pago no cambia el precio', async ({ page }) => {
  const enviadas = await preparar(page);
  const form = page.getByRole('form', { name: 'Movimiento de insumo', exact: true });
  await form.getByLabel('Cantidad', { exact: true }).fill('4');
  await form.getByTitle('Moneda en la que se digita el precio', { exact: true }).selectOption('2');
  await form.getByLabel('Precio unitario', { exact: true }).fill('0,25');
  await form.getByLabel('Tasa del precio', { exact: true }).fill('4000');
  await form.getByLabel('Flete por unidad', { exact: true }).fill('200');
  await elegirPrincipal(form, 'Dólares QA');
  await form.getByLabel('Tasa del pago principal', { exact: true }).fill('5000');
  await dividirPago(form, '0.8', 'USD');
  await expect(form.getByText(/Pagado:/)).toContainText('4.800 COP');
  await expect(form.getByText(/Sobran|Faltan/)).toHaveCount(0);
  await expect(form.getByText(/Se descontarán/)).toContainText('0,8 USD');
  await form.getByRole('button', { name: 'Registrar Movimiento', exact: true }).click();
  await expect.poll(() => enviadas.length).toBe(1);
  expect(enviadas[0].captura.costo_unitario).toBe(1000);
  expect(enviadas[0].captura.pagos?.map((p) => [p.moneda_id, p.monto, p.tasa_pago])).toEqual([
    [2, 0.8, 5000], [1, 800, undefined],
  ]);
});

test('Una fila extra incompleta no se descarta para cobrar todo de la principal', async ({ page }) => {
  const enviadas = await preparar(page);
  const form = page.getByRole('form', { name: 'Movimiento de insumo', exact: true });
  await form.getByLabel('Cantidad', { exact: true }).fill('4');
  await elegirPrincipal(form, 'Banco QA');
  await form.getByRole('button', { name: /Se pagó parte con otra cuenta/ }).click();
  await form.getByRole('button', { name: 'Registrar Movimiento', exact: true }).click();
  await expect(page.getByText('Completa los pagos extra: cuenta, monto y tasa si su moneda no es COP.')).toBeVisible();
  expect(enviadas).toHaveLength(0);
});

test('Corregir entrada antigua suma su flete a lo realmente cobrado, sin otro cargo', async ({ page }) => {
  const enviadas = await preparar(page, {
    pagos_incluyen_llevada: false,
    pagos: [
      { metodo_caja_id: 1, moneda_id: 1, monto: '3200', monto_en_moneda_base: '3200' },
      { metodo_caja_id: 2, moneda_id: 1, monto: '800', monto_en_moneda_base: '800' },
    ],
    pago_llevada: { metodo_caja_id: 1, moneda_id: 1, monto: '800', monto_en_moneda_base: '800' },
  });
  await page.getByRole('button', { name: 'Historial', exact: true }).click();
  await page.getByRole('button', { name: 'Editar', exact: true }).click();
  const form = page.getByRole('form', { name: 'Corregir entrada de insumo', exact: true });
  await expect(form.getByLabel('Monto de la cuenta principal (COP)', { exact: true })).toHaveValue('4000');
  await expect(form.getByText(/Pagado:/)).toContainText('Compra: 4.800 COP');
  await form.getByRole('button', { name: 'Guardar corrección', exact: true }).click();
  await expect.poll(() => enviadas.length).toBe(1);
  expect(enviadas[0].captura.pagos?.map((p) => p.monto)).toEqual([4000, 800]);
  expect(enviadas[0].captura.pagos_incluyen_llevada).toBe(true);
});

test('Corrección con principal USD conserva el importe incluso con redondeo', async ({ page }) => {
  const enviadas = await preparar(page, {
    pagos_incluyen_llevada: true, moneda_pago_id: 2, tasa_pago: 4000, costo_unitario: 1001,
    pagos: [
      { metodo_caja_id: 3, moneda_id: 2, monto: '1', tasa_pago: '4000', monto_en_moneda_base: '4000' },
      { metodo_caja_id: 2, moneda_id: 1, monto: '800', monto_en_moneda_base: '800' },
    ],
  });
  await page.getByRole('button', { name: 'Historial', exact: true }).click();
  await page.getByRole('button', { name: 'Editar', exact: true }).click();
  const form = page.getByRole('form', { name: 'Corregir entrada de insumo', exact: true });
  await expect(form.getByLabel('Monto de la cuenta principal (USD)', { exact: true })).toHaveValue('1');
  await expect(form.getByText(/Pagado:/)).toContainText('4.800 COP');
  await expect(form.getByText(/Pagado:/)).toContainText('Compra: 4.804 COP');
  await expect(form.getByText(/Diferencia admitida por redondeo/)).toContainText('4 COP');
  await expect(form.getByText(/Sobran|Faltan/)).toHaveCount(0);
  await form.getByRole('button', { name: 'Guardar corrección', exact: true }).click();
  await expect.poll(() => enviadas.length).toBe(1);
  expect(enviadas[0].captura.pagos?.map((p) => [p.monto, p.tasa_pago])).toEqual([[1, 4000], [800, undefined]]);
});

test('Reventa incluye el flete en el cuadre sin asignar el total al primer método', async ({ page }) => {
  const enviadas = await preparar(page);
  await page.getByRole('button', { name: 'Cerrar', exact: true }).click();
  await page.getByRole('button', { name: 'Productos de Reventa', exact: true }).click();
  await page.getByRole('row', { name: /PRODUCTO QA PAGOS/ }).click();
  const form = page.getByRole('form', { name: 'Movimiento de producto', exact: true });
  await form.getByRole('combobox', { name: 'Seleccione...', exact: true }).selectOption('1');
  await form.getByLabel('Cantidad', { exact: true }).fill('4');
  await form.getByLabel('Precio unitario', { exact: true }).fill('1000');
  await form.getByLabel('Flete total', { exact: true }).fill('800');
  await elegirPrincipal(form, 'Banco QA');
  await dividirPago(form, '4000');
  await expect(form.getByText(/Se descontarán/)).toContainText('4.000 COP');
  await expect(form.getByText(/Pagado:/)).toContainText('Compra: 4.800 COP');
  await form.getByRole('button', { name: 'Registrar Movimiento', exact: true }).click();
  await expect.poll(() => enviadas.length).toBe(1);
  expect(enviadas[0].ruta).toBe('/api/v1/inventario/producto/movimiento');
  expect(enviadas[0].captura.pagos?.map((p) => p.monto)).toEqual([4000, 800]);
  expect(enviadas[0].captura.pagos_incluyen_llevada).toBe(true);
});
