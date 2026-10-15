// F2: el Kanban de producción trabaja sin red (espejo local + outbox).
// Se corre contra el BUILD con service worker (vite preview en :4173).
//
//   cd frontend && npm run build:offline && npm run preview &
//   npx playwright test e2e/offline-produccion.spec.ts
import { test, expect } from '@playwright/test';

test.use({ baseURL: 'http://localhost:4173' });

const USUARIO = 'jackson';
const CONTRASENA = 'jackson2025$';
const PIN = '2468';

test('Kanban offline: ve la orden cacheada, inicia etapa sin red y sincroniza al reconectar', async ({ page, context, request }) => {
  test.setTimeout(180_000);

  // ── Datos de prueba por API (orden STOCK: no ensucia pedidos/ventas) ──
  const login = await request.post('/api/auth/login', { form: { username: USUARIO, password: CONTRASENA } });
  expect(login.ok()).toBeTruthy();
  const { access_token } = await login.json();
  const auth = { Authorization: `Bearer ${access_token}` };

  const marca = Date.now();
  const nombreProducto = `E2E Offline ${marca}`;

  const rProd = await request.post('/api/v1/producto/', {
    headers: auth,
    data: { nombre: nombreProducto, tipo_producto_id: 1, ancho_base: 1.6, largo_base: 1.9 },
  });
  expect(rProd.status()).toBe(201);
  const producto = await rProd.json();

  const rOrden = await request.post('/api/v1/produccion/orden/', {
    headers: auth,
    data: { estado: 'PENDIENTE', es_stock: true, producto_id: producto.id },
  });
  expect(rOrden.status()).toBe(201);
  const orden = await rOrden.json();

  const rEtapa = await request.post('/api/v1/produccion/etapa/', {
    headers: auth,
    data: { orden_produccion_id: orden.id, area_id: 1, empleado_responsable_id: 3, estado: 'ASIGNADA' },
  });
  expect(rEtapa.status()).toBe(201);
  const etapa = await rEtapa.json();

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

    // ── Cargar el Kanban online (llena el espejo) y abrir la estación una vez ──
    await page.goto('/produccion');
    const buscador = page.getByPlaceholder(/Buscar por cliente, producto, orden o responsable/);
    await buscador.fill(String(orden.id));
    await expect(page.getByText(nombreProducto).first()).toBeVisible({ timeout: 25_000 });
    await page.getByText(nombreProducto).first().click();
    await expect(page.getByRole('button', { name: /Iniciar trabajo/ }).first()).toBeVisible({ timeout: 20_000 });
    await page.keyboard.press('Escape');

    // ── Esperar al service worker y dejarlo controlando la página ──
    await page.waitForFunction(async () => {
      const reg = await navigator.serviceWorker.ready;
      return !!reg.active;
    }, null, { timeout: 30_000 });
    await page.reload();
    await buscador.fill(String(orden.id));
    await expect(page.getByText(nombreProducto).first()).toBeVisible({ timeout: 25_000 });
    await page.waitForFunction(() => !!navigator.serviceWorker.controller, null, { timeout: 30_000 });

    // ── Apagón: recarga sin red y entra con PIN ──
    await context.setOffline(true);
    await page.reload();
    await expect(page.getByText('Modo sin conexión')).toBeVisible({ timeout: 20_000 });
    await page.getByLabel('PIN local').fill(PIN);
    await page.getByRole('button', { name: 'Desbloquear y trabajar' }).click();
    await expect(page.getByText('Sin conexión — trabajando local')).toBeVisible({ timeout: 20_000 });

    // El tablero sale del espejo y la etapa se inicia sin red (queda en cola)
    await buscador.fill(String(orden.id));
    await expect(page.getByText(nombreProducto).first()).toBeVisible({ timeout: 25_000 });
    await page.getByText(nombreProducto).first().click();
    await page.getByRole('button', { name: /Iniciar trabajo/ }).first().click();
    await expect(page.getByText('1 por sincronizar')).toBeVisible({ timeout: 20_000 });

    // ── Vuelve la red: el outbox se empuja y la etapa queda EN_PROCESO ──
    await context.setOffline(false);
    await expect(page.getByText('Sin conexión — trabajando local')).toBeHidden({ timeout: 60_000 });
    await expect(page.getByText('1 por sincronizar')).toBeHidden({ timeout: 60_000 });

    const verEtapa = await request.get(`/api/v1/produccion/etapa/${etapa.id}`, { headers: auth });
    expect((await verEtapa.json()).estado).toBe('EN_PROCESO');
  } finally {
    await request.delete(`/api/v1/produccion/etapa/${etapa.id}`, { headers: auth });
    await request.delete(`/api/v1/produccion/orden/${orden.id}`, { headers: auth });
    await request.delete(`/api/v1/producto/${producto.id}`, { headers: auth });
  }
});
