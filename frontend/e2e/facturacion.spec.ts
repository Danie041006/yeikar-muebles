import { test, expect, type Page } from '@playwright/test';

const USUARIO = 'jackson';
const CONTRASENA = 'jackson2025$';
const CLIENTE_E2E = `E2E Facturación ${new Date().toISOString().slice(0, 10)}`;

async function login(page: Page) {
  await page.goto('/login');
  await page.getByPlaceholder('Tu usuario').fill(USUARIO);
  await page.getByPlaceholder('Tu contraseña').fill(CONTRASENA);
  await page.getByRole('button', { name: /Entrar al espacio de trabajo/ }).click();
  await expect(page).toHaveURL(/\/dashboard/, { timeout: 15_000 });
}

async function abrirFacturacion(page: Page) {
  await page.goto('/facturacion');
  await expect(page.getByRole('main').getByRole('heading', { name: 'Facturación' })).toBeVisible();
}

// Modal de detalle de factura: overlay fijo que contiene el heading "Factura Fiscal #N"
function modalFactura(page: Page) {
  return page
    .locator('div.fixed.inset-0')
    .filter({ has: page.getByRole('heading', { name: /Factura Fiscal #/ }) })
    .first();
}

// Modal de emisión: overlay fijo que contiene el heading "Emitir Factura"
function modalEmitir(page: Page) {
  return page
    .locator('div.fixed.inset-0')
    .filter({ has: page.getByRole('heading', { name: /Emitir Factura/ }) })
    .first();
}

test.describe.serial('Flujo de anulación y re-facturación (datos E2E aislados)', () => {
  test('login y abrir el detalle de la factura EMITIDA del cliente E2E', async ({ page }) => {
    await login(page);
    await abrirFacturacion(page);

    const fila = page.locator('tr', { hasText: CLIENTE_E2E });
    await expect(fila.first()).toBeVisible({ timeout: 15_000 });
    await expect(fila.first()).toContainText('EMITIDA');
    await fila.first().getByRole('button', { name: 'Ver / PDF' }).click();

    const modal = modalFactura(page);
    await expect(modal.getByText('EMITIDA', { exact: true })).toBeVisible({ timeout: 15_000 });
    await page.screenshot({ path: 'e2e/screenshots/01-factura-emitida.png', fullPage: false });
  });

  test('anular: ConfirmDialog centrado → toast de éxito → badge ANULADA', async ({ page }) => {
    await login(page);
    await abrirFacturacion(page);

    const fila = page.locator('tr', { hasText: CLIENTE_E2E }).first();
    await expect(fila).toBeVisible({ timeout: 15_000 });
    await expect(fila).toContainText('EMITIDA');
    await fila.getByRole('button', { name: 'Ver / PDF' }).click();

    const modal = modalFactura(page);
    await expect(modal.getByText('EMITIDA', { exact: true })).toBeVisible({ timeout: 15_000 });
    await modal.getByRole('button', { name: 'Anular' }).click();

    // ConfirmDialog centrado y estilizado de la app (no window.confirm)
    const confirm = page.locator('div[role="dialog"]').last();
    await expect(confirm).toBeVisible();
    await expect(confirm).toContainText('Anular factura');
    await expect(confirm).toContainText('podrá volver a facturarse');
    await page.screenshot({ path: 'e2e/screenshots/02-confirm-anular.png' });

    await confirm.getByRole('button', { name: 'Sí, anular' }).click();

    // Toast de éxito (sistema Toast de la app, no alert nativo)
    const toast = page.getByRole('status');
    await expect(toast).toContainText('anulada', { timeout: 10_000 });
    await page.screenshot({ path: 'e2e/screenshots/03-toast-anulada.png' });

    // El detalle muestra el badge ANULADA
    await expect(modal.getByText('ANULADA', { exact: true })).toBeVisible({ timeout: 10_000 });
    await expect(modal.getByRole('button', { name: 'Anular' })).toBeHidden();
    await page.screenshot({ path: 'e2e/screenshots/04-factura-anulada.png' });
  });

  test('el pedido vuelve a "Pedidos por Facturar" tras anular', async ({ page }) => {
    await login(page);
    await abrirFacturacion(page);

    await page.getByRole('button', { name: /Pedidos por Facturar/ }).click();
    await expect(page.getByText('PAGADO 100%').first()).toBeVisible({ timeout: 15_000 });
    await expect(page.getByText(CLIENTE_E2E).first()).toBeVisible();
    await page.screenshot({ path: 'e2e/screenshots/05-pedido-por-facturar.png' });
  });

  test('re-facturar: emitir la corrección y ver la nueva factura EMITIDA', async ({ page }) => {
    await login(page);
    await abrirFacturacion(page);

    await page.getByRole('button', { name: /Pedidos por Facturar/ }).click();
    await expect(page.getByText('PAGADO 100%').first()).toBeVisible({ timeout: 15_000 });
    await page.getByRole('button', { name: 'Facturar', exact: true }).first().click();

    const modal = modalEmitir(page);
    await expect(modal).toBeVisible();

    // Tasa + monto en USD de la corrección
    await modal.getByPlaceholder('Ej: 50').fill('60');
    await modal.getByPlaceholder('0.00').fill('120');
    await page.screenshot({ path: 'e2e/screenshots/06-emitir-correccion.png' });

    await modal.getByRole('button', { name: 'Emitir Factura' }).click();

    // Se abre el detalle de la nueva factura EMITIDA
    const detalle = modalFactura(page);
    await expect(detalle.getByText('EMITIDA', { exact: true })).toBeVisible({ timeout: 15_000 });
    await page.screenshot({ path: 'e2e/screenshots/07-nueva-factura-emitida.png' });
  });
});
