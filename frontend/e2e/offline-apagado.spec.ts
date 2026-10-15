// Guardián de producción: con el modo offline APAGADO (build normal, el que
// usa Vercel) no debe aparecer el PIN, ni el indicador, ni llamadas a /sync.
//
//   cd frontend && npm run build && npm run preview &
//   npx playwright test e2e/offline-apagado.spec.ts
import { test, expect } from '@playwright/test';

test.use({ baseURL: 'http://localhost:4173' });

const USUARIO = 'jackson';
const CONTRASENA = 'jackson2025$';

test('Build de producción: el modo offline queda inactivo (sin PIN, sin /sync)', async ({ page }) => {
  test.setTimeout(90_000);

  const llamadasSync: string[] = [];
  page.on('request', (peticion) => {
    if (peticion.url().includes('/api/v1/sync/')) llamadasSync.push(peticion.url());
  });

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

  // Ni modal de PIN ni indicador offline, aunque pasen segundos
  await page.waitForTimeout(4000);
  await expect(page.getByText('Configura tu PIN')).toBeHidden();
  await expect(page.getByText('Sin conexión — trabajando local')).toBeHidden();

  // El motor de sync no debe llamar al backend
  expect(llamadasSync).toHaveLength(0);
});
