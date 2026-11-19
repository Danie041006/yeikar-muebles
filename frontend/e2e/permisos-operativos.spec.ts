import { expect, test, type Page } from '@playwright/test';

test.describe.configure({ timeout: 30_000 });

// Todos los datos y las escrituras se interceptan: no se usa la cuenta de Paola
// ni se registran cobros, deudas o consumos en una base de datos real.
const moneda = { id: 1, nombre: 'Peso colombiano', codigo: 'COP', simbolo: '$', activo: true };
const cuentas = [
  { id: 1, nombre: 'Efectivo QA', codigo: 'EFECTIVO_COP', activo: true, orden: 1, moneda_id: 1, moneda_codigo: 'COP' },
  { id: 2, nombre: 'Banco QA', codigo: 'BANCO_QA', activo: true, orden: 2, moneda_id: 1, moneda_codigo: 'COP' },
];
const orden = {
  id: 101, estado: 'EN_PRODUCCION', tipo: 'PEDIDO',
  detalle_pedido: { id: 201, cantidad: 1, descripcion_especifica: 'Sofá QA', pedido: { id: 301, cliente: { nombre: 'Cliente QA' } } },
  piezas: [],
};
const etapa = {
  id: 401, orden_produccion_id: 101, area_id: 1, estado: 'EN_PROCESO', orden,
  area: { id: 1, nombre: 'Ebanistería' }, empleado_responsable: { id: 3, nombre: 'Ebanista QA' },
  consumos: [], asignados_adicionales: [],
  mano_obras: [{ id: 501, empleado_id: 3, monto: 12345, porcentaje_recargo: 0, empleado: { id: 3, nombre: 'Ebanista QA' } }],
};
const deuda = {
  id: 601, proveedor_id: 701, proveedor: { id: 701, nombre: 'Proveedor QA' },
  moneda_id: 1, moneda, monto: 8000, saldo: 8000, monto_pagado: 0, tasa_cambio: 1,
  monto_en_moneda_base: 8000, fecha: '2026-11-16', estado: 'PENDIENTE', detalles: [], pagos: [],
};
const envio = {
  id: 701, pedido_id: 801, estado: 'PREPARADO', direccion_entrega: 'Calle QA',
  guia_despacho: null, observaciones: null, empleado: null, detalles: [],
  pedido: {
    id: 801,
    cliente: { id: 1, nombre: 'Cliente Despacho QA', telefono: '555-0101', direccion: 'Calle QA' },
    detalles: [{ id: 901, cantidad: 1, tipo_item: 'FABRICADO', descripcion_especifica: 'Sofá QA' }],
  },
};

type Perfil = 'operativo' | 'costos-lectura' | 'admin';

async function preparar(page: Page, perfil: Perfil = 'operativo') {
  const consultas: string[] = [];
  const escrituras: { ruta: string; datos: Record<string, unknown> }[] = [];
  await page.addInitScript(() => {
    localStorage.setItem('token', 'qa-interceptada-sin-credenciales');
    localStorage.setItem('yeikar_pin_omitido_1', '1');
  });
  await page.route('**/api/**', async (ruta) => {
    const peticion = ruta.request();
    const camino = new URL(peticion.url()).pathname;
    consultas.push(camino);
    if (peticion.method() !== 'GET') {
      escrituras.push({ ruta: camino, datos: peticion.postDataJSON() ?? {} });
      return ruta.fulfill({ status: 201, json: { id: 801, ...peticion.postDataJSON() } });
    }
    let respuesta: unknown = [];
    if (camino === '/api/auth/me') respuesta = {
      id: 1, nombre_usuario: 'operativo_qa', nombre: 'Prueba', activo: true,
      roles: [{ id: 1, nombre: perfil === 'admin' ? 'Administrador' : 'Operativo QA' }],
      modulos: [
        ...['dashboard', 'produccion', 'gastos', 'ventas', 'cotizaciones', 'pedidos', 'inventario', 'envios'].map((modulo) => ({ modulo, gestionar: true })),
        ...(perfil === 'costos-lectura' ? [{ modulo: 'costos_produccion', gestionar: false }] : []),
      ],
    };
    else if (camino.endsWith('/produccion/orden/')) respuesta = [{ ...orden, etapas: [etapa] }];
    else if (camino.endsWith('/produccion/etapa/401/referencia-receta')) respuesta = {
      orden_id: 101, etapa_id: 401, producto_id: null, producto_nombre: 'Sofá QA',
      dimensiones: {}, materiales: [], piezas_mueble: [], cantidad: 1, area_nombre: 'Ebanistería',
    };
    else if (camino.endsWith('/produccion/etapa/401')) respuesta = etapa;
    else if (camino.endsWith('/empleado/')) respuesta = [{ id: 3, nombre: 'Ebanista QA', cargo: { id: 1, nombre: 'Ebanista' } }];
    else if (camino.endsWith('/produccion/opciones-costo-produccion')) respuesta = [{ id: 1, descripcion: 'Fabricación QA', precio: 12345 }];
    else if (camino.endsWith('/produccion/orden/101/costos-en-vivo')) respuesta = {
      orden_id: 101, estado: 'EN_PRODUCCION', secciones: [], total_produccion: 0,
      totales: { materiales: 0, mano_obra: 0, gastos: 0, excedentes: 0 },
    };
    else if (camino.endsWith('/catalogos/area/')) respuesta = [{ id: 1, nombre: 'Ebanistería' }];
    else if (camino.endsWith('/catalogos/moneda/')) respuesta = [moneda];
    else if (camino.endsWith('/cuenta/operativas') || camino.endsWith('/reports/metodos-caja')) respuesta = cuentas;
    else if (camino.endsWith('/cuenta/resumen')) respuesta = cuentas.map((cuenta) => ({
      metodo_caja: cuenta, saldo_por_moneda: [{ codigo: 'COP', simbolo: '$', monto: 987654 }],
    }));
    else if (camino.endsWith('/cuentas-por-pagar/')) respuesta = [deuda];
    else if (camino.endsWith('/cuentas-por-pagar/resumen')) respuesta = {
      total_pendiente: 8000, total_pagado: 0, total_deudas: 1,
      por_proveedor: [{ proveedor_id: 701, proveedor_nombre: 'Proveedor QA', saldo: 8000 }],
    };
    else if (camino.endsWith('/envio/')) respuesta = [envio];
    return ruta.fulfill({
      json: respuesta,
      headers: { 'X-Total-Count': String(Array.isArray(respuesta) ? respuesta.length : 1) },
    });
  });
  return { consultas, escrituras };
}

async function abrirEtapa(page: Page) {
  await page.goto('/produccion');
  await page.getByRole('heading', { name: 'Sofá QA', exact: true }).click();
  const modal = page.getByRole('dialog', { name: 'Etapa 401 de Sofá QA' });
  await expect(modal.getByRole('button', { name: 'La etapa', exact: true })).toBeVisible();
  return modal;
}

test('Operativo conserva Kanban, Mano de obra y Hoja; no ve Costos ni el desglose', async ({ page }) => {
  const { consultas } = await preparar(page);
  const modal = await abrirEtapa(page);
  await expect(modal.getByRole('button', { name: 'Costos', exact: true })).toHaveCount(0);
  await expect(modal.getByRole('button', { name: /Mano de obra/ })).toBeVisible();
  await expect(modal.getByText('Total etapa', { exact: true })).toHaveCount(0);
  await expect(modal.getByRole('button', { name: 'Completar etapa', exact: true }).first()).toBeVisible();
  await modal.getByRole('button', { name: 'Materiales', exact: true }).click();
  await expect(modal.getByRole('heading', { name: 'Materiales — pedir y registrar' })).toBeVisible();
  await modal.getByRole('button', { name: 'La etapa', exact: true }).click();
  await modal.getByRole('button', { name: 'Hoja de Trabajo', exact: true }).click();
  await expect(page.getByText('Hoja de Trabajo — Ebanistería', { exact: true })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Materiales e Insumos — Ebanistería' })).toBeVisible();
  expect(consultas.filter((ruta) => ruta.endsWith('/costos-en-vivo'))).toEqual([]);
  expect(consultas.some((ruta) => ruta.endsWith('/opciones-costo-produccion'))).toBe(true);
  await expect(page.getByRole('link', { name: 'Cuentas', exact: true })).toHaveCount(0);
  await expect(page.getByRole('link', { name: 'Ventas y cobros', exact: true })).toBeVisible();
});

test('Producción gestión registra mano de obra y crea tarifa sin ver Costos', async ({ page }) => {
  const { consultas, escrituras } = await preparar(page);
  const modal = await abrirEtapa(page);
  await modal.getByRole('button', { name: /Mano de obra/ }).click();
  await expect(modal.getByRole('heading', { name: 'Mano de obra — quién y cuánto' })).toBeVisible();
  await expect(modal.getByRole('button', { name: 'Costos', exact: true })).toHaveCount(0);
  await modal.getByRole('button', { name: 'Empleado…' }).click();
  await modal.getByRole('option', { name: 'Ebanista QA', exact: true }).click();
  await modal.getByRole('button', { name: /Sin tarifa/ }).click();
  await modal.getByRole('option', { name: /Fabricación QA/ }).click();
  await modal.getByPlaceholder('$', { exact: true }).fill('2500');
  await modal.getByRole('button', { name: '+ Agregar mano de obra a la etapa' }).click();
  await expect.poll(() => escrituras.some((e) => e.ruta.endsWith('/produccion/mano-obra/'))).toBe(true);
  const mano = escrituras.find((e) => e.ruta.endsWith('/produccion/mano-obra/'))!.datos;
  expect(mano).toMatchObject({ empleado_id: 3, monto: 2500 });

  await modal.getByRole('button', { name: '+ Nuevo costo de producción' }).click();
  await modal.getByPlaceholder('Tipo de costo (ej. HECHURA EXTRA)').fill('Tarifa QA');
  await modal.getByPlaceholder('Precio ($)').fill('3000');
  await modal.getByRole('button', { name: 'Crear', exact: true }).click();
  await expect.poll(() =>
    escrituras.some((e) => e.ruta.endsWith('/produccion/opciones-costo-produccion')),
  ).toBe(true);
  expect(consultas.filter((ruta) => ruta.endsWith('/costos-en-vivo'))).toEqual([]);
});

for (const perfil of ['costos-lectura', 'admin'] as const) {
  test(`${perfil}: conserva Costos y Mano de obra`, async ({ page }) => {
    const { consultas } = await preparar(page, perfil);
    const modal = await abrirEtapa(page);
    await expect(modal.getByRole('button', { name: /Mano de obra/ })).toBeVisible();
    await modal.getByRole('button', { name: 'Costos', exact: true }).click();
    await expect(modal.getByRole('heading', { name: 'Estructura de costos de la orden' })).toBeVisible();
    await expect.poll(() => consultas.some((ruta) => ruta.endsWith('/costos-en-vivo'))).toBe(true);
    await expect.poll(() => consultas.some((ruta) => ruta.endsWith('/opciones-costo-produccion'))).toBe(true);
  });
}

test('Gastos permite elegir cuenta y pagar deuda sin consultar ni mostrar saldos de cuentas', async ({ page }) => {
  const { consultas, escrituras } = await preparar(page);
  await page.goto('/gastos');
  await page.getByRole('button', { name: 'Nuevo Gasto', exact: true }).click();
  const gasto = page.getByRole('dialog', { name: 'Nuevo Gasto / Egreso' });
  await gasto.getByRole('button', { name: 'Efectivo QA · COP', exact: true }).click();
  await expect(gasto.getByRole('option', { name: 'Banco QA · COP', exact: true })).toBeVisible();
  await expect(gasto.getByRole('listbox')).not.toContainText(/saldo/i);
  await gasto.getByRole('option', { name: 'Banco QA · COP', exact: true }).click();
  await gasto.getByRole('button', { name: 'Cancelar', exact: true }).click();
  await page.getByRole('button', { name: /Por Pagar/ }).click();
  await page.getByRole('button', { name: 'Abonar', exact: true }).click();
  const abono = page.getByRole('dialog', { name: 'Abonar a Proveedor QA' });
  await abono.getByRole('button', { name: 'Efectivo QA · COP', exact: true }).click();
  await expect(abono.getByRole('listbox')).not.toContainText(/saldo/i);
  await abono.getByRole('option', { name: 'Banco QA · COP', exact: true }).click();
  await abono.getByLabel('¿Cuánto abonas?').fill('3000');
  await abono.getByRole('button', { name: 'Abonar', exact: true }).click();
  await expect(abono).toBeHidden();
  const enviada = escrituras.find((solicitud) => solicitud.ruta.endsWith('/601/abonos'));
  expect(enviada?.datos).toMatchObject({ metodo_caja_id: 2, monto: 3000 });
  expect(consultas).toContain('/api/v1/cuenta/operativas');
  expect(consultas).not.toContain('/api/v1/cuenta/resumen');
});

test('Admin conserva los saldos del selector de Gastos', async ({ page }) => {
  const { consultas } = await preparar(page, 'admin');
  await page.goto('/gastos');
  await page.getByRole('button', { name: 'Nuevo Gasto', exact: true }).click();
  const modal = page.getByRole('dialog', { name: 'Nuevo Gasto / Egreso' });
  await expect(modal.getByRole('button', { name: /Efectivo QA · COP \(saldo/ })).toBeVisible();
  expect(consultas).toContain('/api/v1/cuenta/resumen');
});

test('Paola entra a Despachos y ve los pedidos listos para despachar', async ({ page }) => {
  const { consultas } = await preparar(page);
  await page.goto('/envios');
  await expect(page).not.toHaveURL(/\/mis-despachos/);
  await expect(page.getByRole('heading', { name: 'Envíos y Despachos', exact: true })).toBeVisible();
  await expect(page.getByText('Cliente Despacho QA', { exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Asignar y Enviar', exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: '+ Registrar entrega', exact: true })).toBeVisible();
  await expect(page.getByRole('link', { name: 'Despachos', exact: true })).toBeVisible();
  expect(consultas).toContain('/api/v1/envio/');
  await page.goto('/mis-despachos');
  await expect(page).toHaveURL(/\/envios$/);
});

test('La URL directa de Cuentas también queda fuera del rol operativo', async ({ page }) => {
  const { consultas } = await preparar(page);
  await page.goto('/cuentas');
  await expect(page).toHaveURL(/\/dashboard$/);
  expect(consultas.filter((ruta) => ruta.startsWith('/api/v1/cuenta/'))).toEqual([]);
});
