/**
 * Espera a que todas las <img> del contenedor terminen de cargar (o fallen)
 * antes de capturar con html2canvas; si alguna tarda demasiado, sigue tras
 * el timeout para no colgar la generación del PDF.
 */
export async function esperarImagenesCargadas(
  container: HTMLElement,
  timeoutMs = 5000,
): Promise<void> {
  const pendientes = Array.from(container.querySelectorAll('img')).filter(
    (img) => !img.complete || !img.naturalWidth,
  );
  if (pendientes.length === 0) return;
  await Promise.race([
    Promise.all(
      pendientes.map(
        (img) =>
          new Promise<void>((resolve) => {
            img.addEventListener('load', () => resolve(), { once: true });
            img.addEventListener('error', () => resolve(), { once: true });
          }),
      ),
    ),
    new Promise((resolve) => setTimeout(resolve, timeoutMs)),
  ]);
}
