import { expect, test, type Page } from '@playwright/test';

test.describe.configure({ timeout: 30_000 });
test.use({ hasTouch: true });

// API interceptada: no crea empleados ni cargos reales.
const cargos = [
  { id: 1, nombre: 'Operario' },
  { id: 2, nombre: 'ASESORA' },
  { id: 3, nombre: 'EXHIBIDORA DE VENTAS' },
  { id: 4, nombre: 'Chofer' },
];
const empleado = {
  id: 7, nombre: 'Stefanny', cargo_id: 1, telefono: null, activo: true,
  en_nomina: true, tipo_pago: 'DESTAJO', cargo: cargos[0],
  cargos: [cargos[0], cargos[1], cargos[2]],
};

type Enviado = { ruta: string; metodo: string; cuerpo: Record<string, any> };

async function preparar(page: Page, listado = [empleado]) {
  const enviados: Enviado[] = [];
  await page.addInitScript(() => {
    localStorage.setItem('token', 'qa-sin-credenciales-reales');
    localStorage.setItem('yeikar_pin_omitido_1', '1');
  });
  await page.route('**/api/**', async (ruta) => {
    const peticion = ruta.request();
    const camino = new URL(peticion.url()).pathname;
    const cuerpo = peticion.method() === 'GET' ? {} : (peticion.postDataJSON() ?? {});
    if (peticion.method() !== 'GET') {
      enviados.push({ ruta: camino, metodo: peticion.method(), cuerpo });
      if (camino.endsWith('/empleado/cargo/')) {
        const nuevo = { id: 5, nombre: String(cuerpo.nombre || '').trim() };
        cargos.push(nuevo);
        return ruta.fulfill({ status: 201, json: nuevo });
      }
      const ids: number[] = Array.isArray(cuerpo.cargo_ids) ? cuerpo.cargo_ids : [];
      const asignados = ids
        .map((id) => cargos.find((c) => c.id === id))
        .filter((c): c is { id: number; nombre: string } => Boolean(c));
      return ruta.fulfill({
        status: peticion.method() === 'POST' ? 201 : 200,
        json: {
          ...empleado, ...cuerpo, id: empleado.id,
          cargo_id: ids[0] ?? cuerpo.cargo_id,
          cargos: asignados.length ? asignados : [cargos.find((c) => c.id === cuerpo.cargo_id)],
        },
      });
    }
    let respuesta: unknown = [];
    if (camino === '/api/auth/me') respuesta = {
      id: 1, nombre_usuario: 'qa', nombre: 'Prueba',
      roles: [{ id: 1, nombre: 'Administrador' }],
      modulos: [{ modulo: 'empleados', gestionar: true }],
    };
    else if (camino === '/api/v1/catalogos/cargo/') respuesta = cargos;
    else if (camino === '/api/v1/empleado/') respuesta = listado;
    return ruta.fulfill({ json: respuesta, headers: { 'X-Total-Count': String(listado.length) } });
  });
  await page.goto('/empleados');
  await expect(page.getByRole('button', { name: 'Nuevo Empleado', exact: true }).first()).toBeVisible();
  return enviados;
}

test('Stefanny: cargo principal + asesora + exhibidora, y crear cargo sin salir', async ({ page }) => {
  const enviados = await preparar(page, []);
  await page.getByRole('button', { name: 'Nuevo Empleado', exact: true }).first().click();
  const modal = page.getByRole('dialog');
  await modal.getByPlaceholder('Ej: WILMER/EBANISTA').fill('Stefanny');
  await modal.getByRole('combobox', { name: 'Seleccione cargo...', exact: true }).selectOption('1');

  await modal.getByRole('button', { name: /ASESORA/ }).click();
  await modal.getByRole('button', { name: /EXHIBIDORA DE VENTAS/ }).click();
  await expect(modal.getByRole('button', { name: /ASESORA/ })).toHaveAttribute('aria-pressed', 'true');
  await expect(modal.getByRole('button', { name: /EXHIBIDORA DE VENTAS/ })).toHaveAttribute('aria-pressed', 'true');

  await modal.getByPlaceholder(/Crear cargo nuevo/).fill('Gerente de ventas');
  await modal.getByRole('button', { name: 'Crear cargo', exact: true }).click();
  await expect(modal.getByRole('button', { name: /Gerente de ventas/ })).toHaveAttribute('aria-pressed', 'true');

  await modal.getByRole('button', { name: 'Guardar', exact: true }).click();
  await expect.poll(() => enviados.filter((e) => e.metodo === 'POST').length).toBe(2);
  const alta = enviados.find((e) => e.ruta.endsWith('/empleado/'))!;
  expect(alta.cuerpo.nombre).toBe('Stefanny');
  expect(alta.cuerpo.cargo_id).toBe(1);
  expect(alta.cuerpo.cargo_ids).toEqual([1, 2, 3, 5]);
});

test('Editar precarga todos los cargos y guarda solo los seleccionados', async ({ page }) => {
  const enviados = await preparar(page);
  await page.getByRole('button', { name: 'Editar', exact: true }).click();
  const modal = page.getByRole('dialog');
  await expect(modal.getByRole('combobox', { name: 'Seleccione cargo...', exact: true })).toHaveValue('1');
  await expect(modal.getByRole('button', { name: /ASESORA/ })).toHaveAttribute('aria-pressed', 'true');
  await expect(modal.getByRole('button', { name: /EXHIBIDORA DE VENTAS/ })).toHaveAttribute('aria-pressed', 'true');

  await modal.getByRole('button', { name: /ASESORA/ }).click();
  await modal.getByRole('button', { name: 'Guardar Cambios', exact: true }).click();
  await expect.poll(() => enviados.length).toBe(1);
  expect(enviados[0].cuerpo.cargo_ids).toEqual([1, 3]);
});
