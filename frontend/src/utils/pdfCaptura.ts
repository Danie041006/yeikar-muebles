/**
 * Captura un elemento del DOM y lo descarga como PDF tamaño carta.
 * Única fuente de la tubería html2canvas → jsPDF (antes estaba copiada en
 * Cotizaciones, Despachos, Facturación y Nómina).
 *
 * Si el documento marca bloques con data-pdf-item="true", los saltos de
 * página son inteligentes: nunca se corta un bloque por la mitad (patrón
 * de Nómina). Sin bloques marcados, corta a altura fija de página.
 */
export async function capturarElementoAPdf(
  element: HTMLElement,
  opciones: {
    nombreArchivo: string;
    /** Escala de html2canvas: 2 = rápido, 5-6 = máxima nitidez para fotos */
    scale?: number;
    /** Margen del PDF en mm (aplica a los 4 lados) */
    margenMm?: number;
    /** Calidad JPEG del canvas incrustado (0-1) */
    jpegCalidad?: number;
  }
): Promise<void> {
  const { nombreArchivo, scale = 2, margenMm = 10, jpegCalidad = 0.98 } = opciones;

  const { default: html2canvas } = await import('html2canvas');
  const { jsPDF } = await import('jspdf');
  const { esperarImagenesCargadas } = await import('./pdfImagenes');
  await esperarImagenesCargadas(element);

  const canvas = await html2canvas(element, { scale, useCORS: true });
  const pdf = new jsPDF({ orientation: 'portrait', unit: 'mm', format: 'letter' });
  const pdfW = pdf.internal.pageSize.getWidth();
  const pdfH = pdf.internal.pageSize.getHeight();
  const printableW = pdfW - margenMm * 2;
  const printableH = pdfH - margenMm * 2;
  const pxPerMm = canvas.width / printableW;
  const pageHpx = Math.floor(printableH * pxPerMm);

  // Posiciones relativas de los bloques marcados (para cortes inteligentes)
  const containerRect = element.getBoundingClientRect();
  const scaleDomToCanvas = canvas.height / containerRect.height;
  const itemsBounds = Array.from(element.querySelectorAll('[data-pdf-item="true"]')).map((el) => {
    const r = el.getBoundingClientRect();
    return {
      top: (r.top - containerRect.top) * scaleDomToCanvas,
      bottom: (r.bottom - containerRect.top) * scaleDomToCanvas,
      height: r.height * scaleDomToCanvas,
    };
  });

  // Cortes de página: si un bloque queda a caballo entre dos páginas y cabe
  // en una página completa, se corta justo antes de él.
  const pageBreakpoints: number[] = [0];
  let currentBreak = 0;
  while (currentBreak < canvas.height) {
    const maxCandidate = currentBreak + pageHpx;
    if (maxCandidate >= canvas.height) {
      pageBreakpoints.push(canvas.height);
      break;
    }
    let bestCut = maxCandidate;
    const overlapping = itemsBounds.find(
      (b) => b.top < maxCandidate && b.bottom > maxCandidate && b.top > currentBreak
    );
    if (overlapping && overlapping.height <= pageHpx) {
      bestCut = overlapping.top;
    }
    if (bestCut <= currentBreak) bestCut = currentBreak + pageHpx;
    pageBreakpoints.push(bestCut);
    currentBreak = bestCut;
  }

  for (let i = 0; i < pageBreakpoints.length - 1; i++) {
    const startY = pageBreakpoints[i];
    const sliceH = pageBreakpoints[i + 1] - startY;
    if (sliceH <= 0) continue;
    const sc = document.createElement('canvas');
    sc.width = canvas.width;
    sc.height = sliceH;
    const ctx = sc.getContext('2d');
    if (ctx) ctx.drawImage(canvas, 0, startY, canvas.width, sliceH, 0, 0, canvas.width, sliceH);
    if (i > 0) pdf.addPage('letter', 'portrait');
    pdf.addImage(
      sc.toDataURL('image/jpeg', jpegCalidad),
      'JPEG',
      margenMm,
      margenMm,
      printableW,
      (sliceH / canvas.width) * printableW
    );
  }

  pdf.save(nombreArchivo);
}
