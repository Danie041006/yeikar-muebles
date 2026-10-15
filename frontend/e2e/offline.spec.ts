// Ciclo offline completo (F1). Se corre contra el BUILD con service worker
// (vite preview en :4173), no contra el dev server: el apagón real implica
// que la interfaz abra desde el caché sin red.
//
//   cd frontend && npm run build:offline && npm run preview &
//   npx playwright test e2e/offline.spec.ts
import { test, expect } from '@playwright/test';

test.use({ baseURL: 'http://localhost:4173' });

const USUARIO = 'jackson';
const CONTRASENA = 'jackson2025$';
const PIN = '2468';

test('PIN local: login → configurar PIN → apagón → bloqueo → desbloqueo → reconexión', async ({ page, context }) => {
  test.setTimeout(150_000);

  // Equipo "nuevo": sin sesión ni copia local
  await page.goto('/login');
  await page.evaluate(async () => {
    localStorage.clear();
    await new Promise<void>((resolve) => {
      const req = indexedDB.deleteDatabase('yeikar-offline');
      req.onsuccess = req.onerror = req.onblocked = () => resolve();
    });
  });

  // 1. Login online normal
  await page.goto('/login');
  await page.getByPlaceholder('Tu usuario').fill(USUARIO);
  await page.getByPlaceholder('Tu contraseña').fill(CONTRASENA);
  await page.getByRole('button', { name: /Entrar al espacio de trabajo/ }).click();
  await expect(page).toHaveURL(/\/dashboard/, { timeout: 20_000 });

  // 2. El modal ofrece configurar el PIN para apagones
  await expect(page.getByText('Configura tu PIN')).toBeVisible({ timeout: 20_000 });
  await page.getByLabel('PIN (4 a 8 dígitos)').fill(PIN);
  await page.getByLabel('Repite el PIN').fill(PIN);
  await page.getByRole('button', { name: 'Activar PIN' }).click();
  await expect(page.getByText('PIN activado')).toBeVisible({ timeout: 10_000 });

  // 3. Esperar al service worker y recargar una vez para que controle la página
  await page.waitForFunction(async () => {
    const reg = await navigator.serviceWorker.ready;
    return !!reg.active;
  }, null, { timeout: 30_000 });
  await page.reload();
  await expect(page).toHaveURL(/\/dashboard/, { timeout: 20_000 });
  await page.waitForFunction(() => !!navigator.serviceWorker.controller, null, { timeout: 30_000 });

  // 4. Apagón: se va la luz/router y se reabre la app (recarga sin red)
  await context.setOffline(true);
  await page.reload();

  await expect(page.getByText('Modo sin conexión')).toBeVisible({ timeout: 20_000 });
  await page.getByLabel('PIN local').fill(PIN);
  await page.getByRole('button', { name: 'Desbloquear y trabajar' }).click();

  // 5. Tablero operativo con el aviso de sin conexión
  await expect(page).toHaveURL(/\/dashboard/, { timeout: 20_000 });
  await expect(page.getByText('Sin conexión — trabajando local')).toBeVisible({ timeout: 20_000 });

  // 6. Vuelve la conexión: sincroniza y el aviso desaparece
  await context.setOffline(false);
  await expect(page.getByText('Sin conexión — trabajando local')).toBeHidden({ timeout: 60_000 });
});
