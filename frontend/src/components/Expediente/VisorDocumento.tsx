import { useState, type ReactNode } from 'react';
import { Eye, Download } from 'lucide-react';
import Modal from '../ui/Modal';

interface VisorDocumentoProps {
  titulo: string;
  documentoId: string;
  children: ReactNode;
  onDescargar?: () => void;
}

async function descargarPdf(element: HTMLElement, nombreArchivo: string) {
  const { default: html2canvas } = await import('html2canvas');
  const { jsPDF } = await import('jspdf');
  const { esperarImagenesCargadas } = await import('../../utils/pdfImagenes');
  await esperarImagenesCargadas(element);
  const canvas = await html2canvas(element, { scale: 2, useCORS: true });
  const pdf = new jsPDF({ orientation: 'portrait', unit: 'mm', format: 'letter' });
  const pdfW = pdf.internal.pageSize.getWidth();
  const pdfH = pdf.internal.pageSize.getHeight();
  const totalH = (canvas.height * pdfW) / canvas.width;
  if (totalH <= pdfH) {
    pdf.addImage(canvas.toDataURL('image/jpeg', 0.98), 'JPEG', 0, 0, pdfW, totalH);
  } else {
    const pxPerMm = canvas.width / pdfW;
    const pageHpx = Math.floor(pdfH * pxPerMm);
    const totalPages = Math.ceil(canvas.height / pageHpx);
    for (let pg = 0; pg < totalPages; pg++) {
      const sliceY = pg * pageHpx;
      const slicePx = Math.min(pageHpx, canvas.height - sliceY);
      const sc = document.createElement('canvas');
      sc.width = canvas.width;
      sc.height = slicePx;
      const ctx = sc.getContext('2d');
      if (ctx) ctx.drawImage(canvas, 0, sliceY, canvas.width, slicePx, 0, 0, canvas.width, slicePx);
      if (pg > 0) pdf.addPage('letter', 'portrait');
      pdf.addImage(sc.toDataURL('image/jpeg', 0.98), 'JPEG', 0, 0, pdfW, (slicePx / canvas.width) * pdfW);
    }
  }
  pdf.save(nombreArchivo);
}

export default function VisorDocumento({
  titulo,
  documentoId,
  children,
  onDescargar,
}: VisorDocumentoProps) {
  const [modalAbierto, setModalAbierto] = useState(false);
  const elId = `visor-doc-${documentoId}`;

  const handleDescargar = async (source?: 'desktop' | 'mobile') => {
    if (onDescargar) {
      onDescargar();
      return;
    }
    const suffix = source === 'mobile' ? '-mobile' : '';
    const element = document.getElementById(`${elId}${suffix}`);
    if (!element) return;
    await descargarPdf(element, `${titulo.replace(/\s+/g, '_')}_${documentoId}.pdf`);
  };

  return (
    <>
      {/* Desktop: documento inline */}
      <div className="hidden md:block bg-stone-100 border border-yeikar-secondary-light/10 rounded-2xl p-4 overflow-x-auto">
        <div className="flex items-center justify-between mb-3">
          <p className="font-mono text-[10px] font-bold uppercase tracking-widest text-yeikar-neutral/45 flex items-center gap-2">
            <Eye className="w-4 h-4" />
            {titulo}
            <span className="text-yeikar-neutral/35 font-normal">· solo lectura</span>
          </p>
          <button
            onClick={() => handleDescargar('desktop')}
            className="flex items-center gap-1.5 text-[11px] font-bold text-yeikar-primary hover:text-yeikar-primary-dark transition-colors"
          >
            <Download className="w-3.5 h-3.5" />
            Descargar PDF
          </button>
        </div>
        <div id={elId} className="min-w-[816px]">
          {children}
        </div>
      </div>

      {/* Móvil: botón ojito + modal */}
      <div className="md:hidden">
        <button
          onClick={() => setModalAbierto(true)}
          className="flex items-center gap-2 w-full rounded-xl border border-yeikar-secondary-light/15 bg-white p-3 text-left hover:bg-yeikar-tertiary/30 transition-colors"
        >
          <span className="flex items-center justify-center h-9 w-9 rounded-lg bg-yeikar-primary/10 text-yeikar-primary">
            <Eye className="w-5 h-5" />
          </span>
          <div className="flex-1 min-w-0">
            <p className="font-headline font-bold text-sm text-yeikar-secondary truncate">{titulo}</p>
            <p className="text-[11px] text-yeikar-neutral/50">Toca para ver el documento completo</p>
          </div>
          <Download className="w-4 h-4 text-yeikar-neutral/40" />
        </button>

        <Modal
          open={modalAbierto}
          onClose={() => setModalAbierto(false)}
          title={titulo}
          size="5xl"
          footer={
            <button
              onClick={() => handleDescargar('mobile')}
              className="flex items-center gap-1.5 px-4 py-2 rounded-xl bg-yeikar-primary text-white text-sm font-bold hover:bg-yeikar-primary-dark transition-colors"
            >
              <Download className="w-4 h-4" />
              Descargar PDF
            </button>
          }
        >
          <div className="-mx-6 -my-5 overflow-x-auto">
            <div id={`${elId}-mobile`} className="min-w-[816px] px-6 py-5">
              {children}
            </div>
          </div>
        </Modal>
      </div>
    </>
  );
}
