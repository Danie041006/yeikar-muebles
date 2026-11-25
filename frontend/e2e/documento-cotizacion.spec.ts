import { expect, test, type Page } from '@playwright/test';

// Cotización real #17 (CESAR PATIÑO): el renglón largo del modular debe cortar
// dentro de su columna y nunca encima de P. Unitario / Total.
const modular =
  'MODULAR DE 6 PTOS. CON TELA PERSA Y LOS COJINES EN NEGRO Y MODIFICAR LOS BRASOS DEL MODULAR HACERLO TAL CUAL AL MODELO DE LA FOTO.';
const productoLargo = 'MODULAR RECLINOMATICO 5 PUESTOS GRIS PERSA CON 5 COJINES PERSA PLATA Y BASE EN MADERA';

const cliente = { id: 1, nombre: 'CESAR PATIÑO', telefono: '4222327382', direccion: 'LA INTEGRACION', cedula: '19385416' };
const moneda = { id: 2, nombre: 'Dólar', codigo: 'USD', simbolo: 'US$' };
const aMedida = (texto: string, cantidad: number, precio: number) => ({
  producto_id: null, tipo_item: 'FABRICADO', cantidad, precio, descripcion_especifica: texto,
});

const cotizacion = (detalles: unknown[]) => ({
  id: 17, cliente_id: 1, fecha: '2026-07-27', estado: 'APROBADA',
  total_estimado: 10086, moneda_id: 2, tasa_cambio: 4000, cliente, moneda, detalles,
});

const detallesReales = [
  aMedida('PUERTAS DE BAÑO EN COLOR HUMO DURATES', 1, 435),
  aMedida('PUERTA DE HABITACION EN COLOR HUMO', 2, 435),
  aMedida('CLOSET DE 2.60 DE ALTO X2,70.X 60 DE FONDO', 1, 380),
  aMedida(modular, 1, 1607),
  aMedida('CAMA DE 1.40. CON 2 MESA DE NOCHE', 1, 1500),
  aMedida('ESPEJO EN COLOR GRIS', 1, 803),
  aMedida('COLCHONES DE 2X2 PERFECT SLEEPER', 1, 803),
  aMedida('COLCHON DE 1.40 PERFECT SLEEPER', 1, 643),
  aMedida('CAMA DE 2X2 CON 2 MESAS DE NOCHE', 1, 1564),
];

async function abrirPreview(page: Page, detalles: unknown[]) {
  await page.addInitScript(() => {
    localStorage.setItem('token', 'qa-interceptada-sin-credenciales');
    localStorage.setItem('yeikar_pin_omitido_1', '1');
  });
  await page.route('**/api/**', async (ruta) => {
    const camino = new URL(ruta.request().url()).pathname;
    let respuesta: unknown = [];
    if (camino === '/api/auth/me') respuesta = {
      id: 1, nombre_usuario: 'ventas_qa', nombre: 'Ventas', activo: true,
      roles: [{ id: 1, nombre: 'Ventas QA' }],
      modulos: ['dashboard', 'cotizaciones', 'ventas', 'pedidos', 'clientes', 'productos', 'materiales', 'inventario', 'produccion']
        .map((modulo) => ({ modulo, gestionar: true })),
    };
    else if (camino === '/api/v1/cotizacion/') respuesta = [cotizacion(detalles)];
    else if (camino === '/api/v1/catalogos/moneda/') respuesta = [
      { id: 1, nombre: 'Peso colombiano', codigo: 'COP', simbolo: '$', activo: true }, moneda,
    ];
    else if (camino === '/api/v1/producto/') respuesta = [{ id: 13080, nombre: productoLargo, fotos: [] }];
    return ruta.fulfill({
      json: respuesta,
      headers: { 'X-Total-Count': String(Array.isArray(respuesta) ? respuesta.length : 1) },
    });
  });
  await page.goto('/cotizaciones');
  await page.getByRole('button', { name: /Ver Cotización/ }).first().click();
  await expect(page.getByRole('heading', { name: /Cotización #00017/ })).toBeVisible();
  return page.locator('#pdf-preview-container');
}

/** Mide el renglón que contiene `fragmento`: corte, desborde e invasión del precio. */
async function medirRenglon(documento: ReturnType<Page['locator']>, fragmento: string) {
  return documento.evaluate((nodo, texto) => {
    const fila = Array.from(nodo.querySelectorAll('tbody tr')).find((tr) => tr.textContent?.includes(texto));
    if (!fila) return null;
    const celdas = Array.from(fila.children) as HTMLElement[];
    const descripcion = celdas.find((td) => td.textContent?.includes(texto));
    const precio = celdas.find((td) => td.textContent?.trim().startsWith('US$'));
    const contenido = descripcion?.querySelector('span.min-w-0') as HTMLElement | null;
    if (!descripcion || !precio || !contenido) return null;
    const altoLinea = parseFloat(getComputedStyle(contenido).lineHeight) || 15;
    const cajaDescripcion = descripcion.getBoundingClientRect();
    const cajaPrecio = precio.getBoundingClientRect();
    const cajaTexto = contenido.getBoundingClientRect();
    return {
      renglones: Math.round(cajaTexto.height / altoLinea),
      huecoPx: Math.round((cajaPrecio.left - cajaTexto.right) * 10) / 10,
      desbordaCelda: descripcion.scrollWidth > descripcion.clientWidth + 1,
      invadePrecio: cajaTexto.right > cajaPrecio.left + 0.5,
      recortado: contenido.scrollHeight > contenido.clientHeight + 1,
      precio: precio.textContent?.trim() ?? '',
    };
  }, fragmento);
}

test('la descripción larga corta dentro de su columna, no invade el precio y sigue en una página', async ({ page }) => {
  const documento = await abrirPreview(page, detallesReales);
  const medida = await medirRenglon(documento, 'MODULAR DE 6 PTOS');
  expect(medida, 'el renglón del modular debe existir').not.toBeNull();
  expect(medida!.desbordaCelda, 'el texto no debe salirse de la celda').toBe(false);
  expect(medida!.invadePrecio, 'el texto no debe tocar la columna de precio').toBe(false);
  expect(medida!.recortado, 'el texto completo debe verse, sin recorte vertical').toBe(false);
  expect(medida!.renglones, 'el texto largo debe pasar al siguiente renglón').toBeGreaterThanOrEqual(2);
  expect(medida!.huecoPx, 'debe quedar separación con el precio').toBeGreaterThan(0);
  expect(medida!.precio).toContain('1.607');
  const alto = await documento.evaluate((nodo) => Math.round(nodo.getBoundingClientRect().height));
  expect(alto, 'la copia del cliente debe caber en una carta').toBeLessThanOrEqual(1056 + 1);
});

test('un nombre de catálogo largo también corta dentro de su columna', async ({ page }) => {
  const documento = await abrirPreview(page, [{
    producto_id: 13080, tipo_item: 'REVENTA', cantidad: 1, precio: 1999, producto_nombre: productoLargo,
  }]);
  const medida = await medirRenglon(documento, 'RECLINOMATICO');
  expect(medida, 'el renglón del producto debe existir').not.toBeNull();
  expect(medida!.desbordaCelda).toBe(false);
  expect(medida!.invadePrecio).toBe(false);
  expect(medida!.recortado).toBe(false);
  expect(medida!.renglones).toBeGreaterThanOrEqual(2);
  expect(medida!.precio).toContain('1.999');
});
