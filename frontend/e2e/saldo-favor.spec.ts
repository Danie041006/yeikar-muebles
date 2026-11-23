import { expect, test, type Page } from '@playwright/test';

// Todo se intercepta: no se registran cobros ni créditos en una base real.
const monedas = [
  { id: 1, nombre: 'Peso colombiano', codigo: 'COP', simbolo: '$', activo: true },
  { id: 2, nombre: 'Dólar', codigo: 'USD', simbolo: 'US$', activo: true },
];
const cuentas = [
  { id: 1, nombre: 'Efectivo USD QA', codigo: 'EFECTIVO_USD', activo: true, orden: 1, moneda_id: 2, moneda_codigo: 'USD' },
];

interface Escenario {
  monedaVenta: 1 | 2;
  saldo: number;
  creditos?: Record<string, unknown>[];
}

const venta = {
  id: 4101,
  pedido_id: 8101,
  cliente_id: 701,
  moneda_id: 2,
  fecha: '2026-11-20',
  total: 7546,
  estado: 'ABONADA',
  observaciones: null,
  cliente: { id: 701, nombre: 'CESAR PATIÑO', telefono: '04221232382' },
  moneda: monedas[1],
  pedido_estado: 'ENTREGADO',
};

async function preparar(page: Page, escenario: Escenario) {
  const escrituras: { ruta: string; datos: Record<string, unknown> }[] = [];
  await page.addInitScript(() => {
    localStorage.setItem('token', 'qa-interceptada-sin-credenciales');
    localStorage.setItem('yeikar_pin_omitido_1', '1');
  });
  await page.route('**/api/**', async (ruta) => {
    const peticion = ruta.request();
    const camino = new URL(peticion.url()).pathname;
    if (peticion.method() !== 'GET') {
      escrituras.push({ ruta: camino, datos: (peticion.postDataJSON() ?? {}) as Record<string, unknown> });
      if (camino.endsWith('/pago/previsualizar')) {
        const datos = peticion.postDataJSON() as { monto: number };
        const excedente = Math.max(0, Number(datos.monto) - escenario.saldo);
        return ruta.fulfill({
          json: {
            cliente_nombre: 'CESAR PATIÑO', cuenta_nombre: 'Efectivo USD QA',
            monto: datos.monto, moneda_pago: 'USD', moneda_venta: 'USD',
            monto_aplicado: Math.min(datos.monto, escenario.saldo),
            saldo_favor: excedente, saldo_confirmado: escenario.saldo,
          },
        });
      }
      return ruta.fulfill({ status: 201, json: { id: 9001, ...(peticion.postDataJSON() as object) } });
    }
    const moneda = monedas.find((m) => m.id === escenario.monedaVenta)!;
    let respuesta: unknown = [];
    if (camino === '/api/auth/me') respuesta = {
      id: 1, nombre_usuario: 'paola_qa', nombre: 'Paola', activo: true,
      roles: [{ id: 1, nombre: 'Operativo QA' }],
      // Paola conserva Ventas y NO tiene Cuentas.
      modulos: ['dashboard', 'ventas', 'gastos', 'cotizaciones', 'pedidos'].map((modulo) => ({ modulo, gestionar: true })),
    };
    else if (camino === '/api/v1/venta/') respuesta = [{ ...venta, moneda_id: escenario.monedaVenta, moneda }];
    else if (camino === '/api/v1/venta/cuentas-por-cobrar/') respuesta = [{
      venta_id: venta.id, pedido_id: venta.pedido_id, cliente_nombre: venta.cliente.nombre,
      fecha: venta.fecha, total: escenario.saldo, total_pagado: 0, total_descontado: 0,
      saldo_pendiente: escenario.saldo, moneda_codigo: moneda.codigo,
      pedido_estado: 'ENTREGADO', recibos_count: 0,
      items: [{ descripcion: 'Comedor QA', cantidad: 1, precio: escenario.saldo }],
    }];
    else if (camino === `/api/v1/venta/${venta.id}`) respuesta = {
      ...venta, moneda_id: escenario.monedaVenta, moneda, total: escenario.saldo,
      detalles: [], pagos: [], descuentos: [],
      total_pagado: 0, total_descontado: 0, saldo_pendiente: escenario.saldo,
    };
    else if (camino === '/api/v1/catalogos/moneda/') respuesta = monedas;
    else if (camino === '/api/v1/reports/metodos-caja') respuesta = cuentas;
    else if (camino === '/api/v1/saldo-favor/') respuesta = escenario.creditos ?? [];
    return ruta.fulfill({
      json: respuesta,
      headers: { 'X-Total-Count': String(Array.isArray(respuesta) ? respuesta.length : 1) },
    });
  });
  return { escrituras };
}

async function abrirCobranza(page: Page) {
  await page.goto('/ventas');
  await page.getByText('CESAR PATIÑO', { exact: true }).first().click();
  await page.getByRole('button', { name: 'Cobranza', exact: true }).click();
}

test('8.000 sobre 7.546 pide confirmación y deja 454 a favor', async ({ page }) => {
  const { escrituras } = await preparar(page, { monedaVenta: 2, saldo: 7546 });
  await abrirCobranza(page);
  await page.getByRole('button', { name: '+ Registrar cobro' }).click();
  await page.locator('input[inputmode="decimal"]').first().fill('8000');
  await page.getByRole('button', { name: 'Confirmar cobro' }).click();

  const revision = page.getByRole('dialog', { name: 'Revisar y confirmar cobro' });
  await expect(revision).toBeVisible();
  await expect(revision.getByText(/Quedarán/)).toContainText('454');
  await expect(revision.getByText(/a favor de CESAR PATIÑO/)).toBeVisible();
  await revision.getByRole('button', { name: 'Sí, registrar este cobro' }).click();

  await expect.poll(() => escrituras.filter((e) => e.ruta.endsWith('/pago/')).length).toBe(1);
  const cobro = escrituras.find((e) => e.ruta.endsWith('/pago/'))!.datos;
  expect(cobro).toMatchObject({ monto: 8000, confirmar_excedente: true, saldo_confirmado: 7546 });
  expect(String(cobro.operacion_id)).toMatch(/^[0-9a-f-]{36}$/);
  expect(escrituras.filter((e) => e.ruta.endsWith('/pago/')).length).toBe(1);
});

test('cobro sin excedente no muestra el aviso de saldo a favor', async ({ page }) => {
  const { escrituras } = await preparar(page, { monedaVenta: 2, saldo: 7546 });
  await abrirCobranza(page);
  await page.getByRole('button', { name: '+ Registrar cobro' }).click();
  await page.locator('input[inputmode="decimal"]').first().fill('7546');
  await page.getByRole('button', { name: 'Confirmar cobro' }).click();

  // Sin excedente no hay paso extra: se registra como siempre y no se pide confirmación.
  await expect.poll(() => escrituras.filter((e) => e.ruta.endsWith('/pago/')).length).toBe(1);
  await expect(page.getByRole('dialog', { name: 'Revisar y confirmar cobro' })).toHaveCount(0);
  expect(escrituras.some((e) => e.ruta.endsWith('/pago/previsualizar'))).toBe(false);
  expect(escrituras.find((e) => e.ruta.endsWith('/pago/'))!.datos).toMatchObject({ monto: 7546 });
});

test('Paola aplica un saldo a favor en otra moneda con tasa manual y sin caja', async ({ page }) => {
  const { escrituras } = await preparar(page, {
    monedaVenta: 1, saldo: 2000000,
    creditos: [{
      id: 88, cliente_id: 701, cliente_nombre: 'CESAR PATIÑO', moneda_id: 2, moneda: monedas[1],
      monto: 454, monto_usado: 0, saldo: 454, referencia: 'Cobro #90 · Venta #4101',
      created_at: '2026-11-20T12:00:00', creador_nombre: 'Paola',
    }],
  });
  page.on('dialog', (dialogo) => dialogo.accept());
  await abrirCobranza(page);

  const bloque = page.getByRole('region', { name: 'Saldo a favor del cliente' });
  await expect(bloque).toContainText('454');
  await bloque.getByLabel('Crédito que se usará').selectOption('88');
  await bloque.getByLabel(/Monto del saldo a favor/).fill('454');
  await bloque.getByLabel(/Tasa manual/).fill('3500');
  await expect(bloque).toContainText('Se aplicará');

  await bloque.getByRole('button', { name: 'Aplicar saldo a favor' }).click();
  await expect.poll(() => escrituras.filter((e) => e.ruta.endsWith('/saldo-favor/aplicar')).length).toBe(1);
  const aplicacion = escrituras.find((e) => e.ruta.endsWith('/saldo-favor/aplicar'))!.datos;
  expect(aplicacion).toMatchObject({ venta_id: 4101, saldo_favor_id: 88, monto: 454, tasa_cambio: 3500 });
  expect(escrituras.some((e) => e.ruta.endsWith('/pago/'))).toBe(false);
});

test('Paola opera cobros sin tener el módulo Cuentas', async ({ page }) => {
  await preparar(page, { monedaVenta: 2, saldo: 7546 });
  await abrirCobranza(page);
  await expect(page.getByRole('link', { name: 'Cuentas', exact: true })).toHaveCount(0);
  await expect(page.getByRole('button', { name: '+ Registrar cobro' })).toBeVisible();
});
