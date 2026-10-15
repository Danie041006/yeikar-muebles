// F3: clientes offline (crear sin red y sincronizar al reconectar).
// Se corre contra el BUILD con service worker:
//   npm run build:offline && npm run preview &
//   npx playwright test e2e/offline-clientes.spec.ts
import { test, expect } from '@playwright/test';

test.use({ baseURL: 'http://localhost:4173' });

const USUARIO = 'jackson';
const CONTRASENA = 'jackson2025$';
const PIN = '2468';

test('Cliente creado sin red queda en cola y se sincroniza al reconectar', async ({ page, context, request }) => {
  test.setTimeout(180_000);

  const login = await request.post('/api/auth/login', { form: { username: USUARIO, password: CONTRASENA } });
  expect(login.ok()).toBeTruthy();
  const { access_token } = await login.json();
  const auth = { Authorization: `Bearer ${access_token}` };

  const marca = Date.now();
  const nombreCliente = `Cliente Offline ${marca}`;

  try {
    // ── Equipo "nuevo": login + PIN ──
    await page.goto('/login');
    await page.evaluate(async () => {
      localStorage.clear();
      await new Promise<void>((resolve) => {
        const req = indexedDB.deleteDatabase('yeikar-offline');
        req.onsuccess = req.onerror = req.onblocked = () => resolve();
      });
    });
    await page.goto('/login');
    await page.getByPlaceholder('Tu usuario').fill(USUARIO);
    await page.getByPlaceholder('Tu contraseña').fill(CONTRASENA);
    await page.getByRole('button', { name: /Entrar al espacio de trabajo/ }).click();
    await expect(page).toHaveURL(/\/dashboard/, { timeout: 20_000 });
    await expect(page.getByText('Configura tu PIN')).toBeVisible({ timeout: 20_000 });
    await page.getByLabel('PIN (4 a 8 dígitos)').fill(PIN);
    await page.getByLabel('Repite el PIN').fill(PIN);
    await page.getByRole('button', { name: 'Activar PIN' }).click();
    await expect(page.getByText('PIN activado')).toBeVisible({ timeout: 10_000 });

    // ── Visitar Clientes online (navegación SPA: llena el espejo) ──
    const cargaClientes = page.waitForResponse((r) => r.url().includes('/api/v1/cliente/') && r.status() === 200);
    await page.getByRole('link', { name: 'Clientes' }).click();
    await cargaClientes;
    await expect(page.getByRole('button', { name: /Registrar Cliente/ }).first()).toBeVisible({ timeout: 25_000 });

    // ── Esperar al service worker y dejarlo controlando (sigue en /clientes) ──
    await page.waitForFunction(async () => {
      const reg = await navigator.serviceWorker.ready;
      return !!reg.active;
    }, null, { timeout: 30_000 });
    const recargaClientes = page.waitForResponse((r) => r.url().includes('/api/v1/cliente/') && r.status() === 200);
    await page.reload();
    await recargaClientes;
    await expect(page.getByRole('button', { name: /Registrar Cliente/ }).first()).toBeVisible({ timeout: 25_000 });
    await page.waitForFunction(() => !!navigator.serviceWorker.controller, null, { timeout: 30_000 });

    // ── Apagón: recarga sin red y entra con PIN (la URL /clientes se conserva) ──
    await context.setOffline(true);
    await page.reload();
    await expect(page.getByText('Modo sin conexión')).toBeVisible({ timeout: 20_000 });
    await page.getByLabel('PIN local').fill(PIN);
    await page.getByRole('button', { name: 'Desbloquear y trabajar' }).click();
    await expect(page.getByText('Sin conexión — trabajando local')).toBeVisible({ timeout: 20_000 });

    // ── Crear cliente sin red (sin recargar: el PIN desbloquea la sesión en memoria) ──
    await page.getByRole('button', { name: /Registrar Cliente/ }).first().click();
    await page.locator('#cliente-form input[name="nombre"]').fill(nombreCliente);
    await page.locator('#cliente-form input[name="telefono"]').fill('555-7777');
    await page.getByRole('button', { name: 'Guardar' }).click();

    await expect(page.getByText('1 por sincronizar')).toBeVisible({ timeout: 20_000 });
    await expect(page.getByText(nombreCliente).first()).toBeVisible({ timeout: 20_000 });

    // ── Vuelve la red: se empuja la cola y el cliente existe en el servidor ──
    await context.setOffline(false);
    await expect(page.getByText('1 por sincronizar')).toBeHidden({ timeout: 60_000 });
    await expect(page.getByText('Sin conexión — trabajando local')).toBeHidden({ timeout: 60_000 });

    const busqueda = await request.get(`/api/v1/cliente/?search=${encodeURIComponent(nombreCliente)}`, { headers: auth });
    expect(busqueda.ok()).toBeTruthy();
    const encontrados = await busqueda.json();
    expect(encontrados.some((c: { nombre: string }) => c.nombre === nombreCliente)).toBeTruthy();
  } finally {
    const busqueda = await request.get(`/api/v1/cliente/?search=${encodeURIComponent(nombreCliente)}`, { headers: auth });
    if (busqueda.ok()) {
      for (const cliente of await busqueda.json()) {
        await request.delete(`/api/v1/cliente/${cliente.id}`, { headers: auth });
      }
    }
  }
});
