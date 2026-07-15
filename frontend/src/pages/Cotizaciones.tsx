import { useEffect, useState } from 'react';
import html2canvas from 'html2canvas';
import { jsPDF } from 'jspdf';
import { cotizacionService, Quote, QuoteCreate, Product, CalculationResult, QuoteDetail } from '../services/cotizacionService';
import { clienteService, Client } from '../services/clienteService';
import { pedidoService } from '../services/pedidoService';

interface CotizacionItemForm {
  producto_id: string;
  cantidad: number;
  ancho: string;
  largo: string;
  ganancia: string;
  observaciones: string;
  calcResult: CalculationResult | null;
  calcLoading: boolean;
}

export default function Cotizaciones() {
  const [quotes, setQuotes] = useState<Quote[]>([]);
  const [clients, setClients] = useState<Client[]>([]);
  const [products, setProducts] = useState<Product[]>([]);
  
  const [search, setSearch] = useState('');
  const [soloMesActual, setSoloMesActual] = useState(true);
  const [selectedMonth, setSelectedMonth] = useState(new Date().getMonth() + 1);
  const [selectedYear, setSelectedYear] = useState(new Date().getFullYear());
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  // Modals state
  const [isFormOpen, setIsFormOpen] = useState(false);
  const [isConvertOpen, setIsConvertOpen] = useState(false);
  const [selectedQuoteForConvert, setSelectedQuoteForConvert] = useState<Quote | null>(null);

  // States for printing
  const [isPrintModalOpen, setIsPrintModalOpen] = useState(false);
  const [selectedQuoteForPrint, setSelectedQuoteForPrint] = useState<Quote | null>(null);
  const [printClientRif, setPrintClientRif] = useState('');
  const [printExchangeRate, setPrintExchangeRate] = useState('4000');
  const [printDiscount, setPrintDiscount] = useState('0');
  const [printIva, setPrintIva] = useState('0');
  const [printCompanyRif, setPrintCompanyRif] = useState('J-50146039-3');
  const [printCompanyAddress, setPrintCompanyAddress] = useState('AV. INTERCOMUNAL CON CALLE 16 LOCAL Nro 15-205, BARRIO SIMÓN BOLÍVAR, UREÑA, TÁCHIRA');
  const [printCompanyPhone, setPrintCompanyPhone] = useState('+58 412-1234567');
  const [isGeneratingPdf, setIsGeneratingPdf] = useState(false);

  // Convert Form state
  const [deliveryDate, setDeliveryDate] = useState('');

  // Create/Edit Form state (multi-item)
  const [editingQuote, setEditingQuote] = useState<Quote | null>(null);
  const [selectedClientId, setSelectedClientId] = useState('');
  const [observaciones, setObservaciones] = useState('');
  const [items, setItems] = useState<CotizacionItemForm[]>([
    { producto_id: '', cantidad: 1, ancho: '1.0', largo: '1.0', ganancia: '40.0', observaciones: '', calcResult: null, calcLoading: false }
  ]);

  const fetchInitialData = async () => {
    try {
      const [cls, prds] = await Promise.all([
        clienteService.getAll(),
        cotizacionService.getProducts(),
      ]);
      setClients(cls);
      setProducts(prds);
    } catch (err) {
      console.error('Error fetching initial data:', err);
    }
  };

  const fetchQuotes = async (searchTerm?: string) => {
    setLoading(true);
    setError('');
    try {
      const data = await cotizacionService.getAll(
        searchTerm,
        soloMesActual,
        soloMesActual ? undefined : selectedMonth,
        soloMesActual ? undefined : selectedYear
      );
      setQuotes(data);
    } catch (err: any) {
      console.error(err);
      setError('Error al cargar cotizaciones.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchInitialData();
  }, []);

  useEffect(() => {
    const timer = setTimeout(() => {
      fetchQuotes(search);
    }, 300);
    return () => clearTimeout(timer);
  }, [search, soloMesActual, selectedMonth, selectedYear]);

  // Trigger calculation individually for each item
  const calculateItemPrice = async (index: number, pId: string, w: string, l: string, g: string) => {
    if (!pId) {
      updateItemField(index, 'calcResult', null);
      return;
    }
    setItems((prevItems) => {
      const newItems = [...prevItems];
      newItems[index] = { ...newItems[index], calcLoading: true };
      return newItems;
    });

    try {
      const res = await cotizacionService.calculatePrice(Number(pId), {
        ancho: Number(w) || 1.0,
        largo: Number(l) || 1.0,
        ganancia: Number(g) || 40.0,
      });
      setItems((prevItems) => {
        const newItems = [...prevItems];
        newItems[index] = { ...newItems[index], calcResult: res, calcLoading: false };
        return newItems;
      });
    } catch (err) {
      console.error('Error calculating price for item:', err);
      setItems((prevItems) => {
        const newItems = [...prevItems];
        newItems[index] = { ...newItems[index], calcLoading: false };
        return newItems;
      });
    }
  };

  const updateItemField = (index: number, field: keyof CotizacionItemForm, value: any) => {
    setItems((prevItems) => {
      const newItems = [...prevItems];
      newItems[index] = { ...newItems[index], [field]: value };
      
      // Auto-dimensions if product changed
      if (field === 'producto_id') {
        const selectedProd = products.find(p => p.id === Number(value));
        if (selectedProd) {
          newItems[index].ancho = selectedProd.ancho_base.toString();
          newItems[index].largo = selectedProd.largo_base.toString();
        }
      }
      
      return newItems;
    });

    // recalculate if relevant field changed
    if (['producto_id', 'ancho', 'largo', 'ganancia'].includes(field)) {
      setItems((prevItems) => {
        const current = prevItems[index];
        calculateItemPrice(index, current.producto_id, current.ancho, current.largo, current.ganancia);
        return prevItems;
      });
    }
  };

  const addItem = () => {
    setItems((prev) => [
      ...prev,
      { producto_id: '', cantidad: 1, ancho: '1.0', largo: '1.0', ganancia: '40.0', observaciones: '', calcResult: null, calcLoading: false }
    ]);
  };

  const removeItem = (index: number) => {
    if (items.length === 1) return;
    setItems((prev) => prev.filter((_, i) => i !== index));
  };

  const handleOpenCreate = () => {
    setEditingQuote(null);
    setSelectedClientId('');
    setObservaciones('');
    setItems([
      { producto_id: '', cantidad: 1, ancho: '1.0', largo: '1.0', ganancia: '40.0', observaciones: '', calcResult: null, calcLoading: false }
    ]);
    setIsFormOpen(true);
  };

  const handleSaveQuote = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedClientId) {
      setError('Por favor selecciona un cliente.');
      return;
    }

    const hasInvalidItem = items.some(item => !item.producto_id);
    if (hasInvalidItem) {
      setError('Por favor selecciona un producto para todos los renglones.');
      return;
    }

    let globalTotal = 0;
    const detalles: QuoteDetail[] = items.map((item) => {
      const itemPrice = item.calcResult ? item.calcResult.precio_venta : 0.0;
      const subtotal = itemPrice * item.cantidad;
      globalTotal += subtotal;

      return {
        producto_id: Number(item.producto_id),
        cantidad: item.cantidad,
        precio: itemPrice,
        ancho: Number(item.ancho) || 1.0,
        largo: Number(item.largo) || 1.0,
        observaciones: item.observaciones || null,
        costo_materiales: (item.calcResult?.costo_materiales || 0.0) * item.cantidad,
        costo_mano_obra: (item.calcResult?.costo_mano_obra || 0.0) * item.cantidad,
        costo_gastos: (item.calcResult?.costo_gastos_indirectos || 0.0) * item.cantidad,
        costo_total: (item.calcResult?.costo_total || 0.0) * item.cantidad,
      };
    });

    // Auto-generate preview description in observaciones field
    const itemsDescription = items.map((item) => {
      const selectedProd = products.find(p => p.id === Number(item.producto_id));
      return `${item.cantidad}x ${selectedProd?.nombre || 'Mueble'} (${item.ancho}x${item.largo}m)`;
    }).join(', ');
    
    const finalObs = observaciones 
      ? `Productos: ${itemsDescription}\nNota: ${observaciones}`
      : `Productos: ${itemsDescription}`;

    const quoteData: QuoteCreate = {
      cliente_id: Number(selectedClientId),
      fecha: new Date().toISOString().split('T')[0],
      estado: editingQuote ? editingQuote.estado : 'BORRADOR',
      total_estimado: globalTotal,
      observaciones: finalObs,
      detalles
    };

    try {
      if (editingQuote) {
        await cotizacionService.update(editingQuote.id, quoteData);
      } else {
        await cotizacionService.create(quoteData);
      }
      setIsFormOpen(false);
      fetchQuotes(search);
    } catch (err) {
      console.error(err);
      setError('Error al guardar la cotización.');
    }
  };

  const handleUpdateStatus = async (quote: Quote, newStatus: string) => {
    try {
      await cotizacionService.update(quote.id, {
        cliente_id: quote.cliente_id,
        fecha: quote.fecha,
        estado: newStatus,
        total_estimado: quote.total_estimado,
        observaciones: quote.observaciones,
      });
      fetchQuotes(search);
    } catch (err) {
      console.error(err);
      alert('Error al actualizar el estado de la cotización.');
    }
  };

  const handleDelete = async (id: number) => {
    if (window.confirm('¿Estás seguro de que deseas eliminar esta cotización?')) {
      try {
        await cotizacionService.delete(id);
        fetchQuotes(search);
      } catch (err) {
        console.error(err);
        alert('Error al eliminar.');
      }
    }
  };

  const handleOpenConvert = (quote: Quote) => {
    setSelectedQuoteForConvert(quote);
    setDeliveryDate('');
    setIsConvertOpen(true);
  };

  const handleOpenPrintPreview = (quote: Quote) => {
    setSelectedQuoteForPrint(quote);
    
    // Load Client RIF from localStorage, or default to empty
    const savedClientRif = localStorage.getItem(`rif_client_${quote.cliente_id}`) || '';
    setPrintClientRif(savedClientRif);
    
    // Load default values or saved configurations
    setPrintCompanyRif(localStorage.getItem('print_company_rif') || 'J-50146039-3');
    setPrintCompanyAddress(localStorage.getItem('print_company_address') || 'AV. INTERCOMUNAL CON CALLE 16 LOCAL Nro 15-205, BARRIO SIMÓN BOLÍVAR, UREÑA, TÁCHIRA');
    setPrintCompanyPhone(localStorage.getItem('print_company_phone') || '+58 412-1234567');
    setPrintExchangeRate(localStorage.getItem('print_exchange_rate') || '4000');
    setPrintDiscount('0');
    setPrintIva('0');
    
    setIsPrintModalOpen(true);
  };

  const handleGeneratePdf = async () => {
    if (!selectedQuoteForPrint) return;
    setIsGeneratingPdf(true);

    // Save settings in localStorage
    localStorage.setItem(`rif_client_${selectedQuoteForPrint.cliente_id}`, printClientRif);
    localStorage.setItem('print_company_rif', printCompanyRif);
    localStorage.setItem('print_company_address', printCompanyAddress);
    localStorage.setItem('print_company_phone', printCompanyPhone);
    localStorage.setItem('print_exchange_rate', printExchangeRate);

    const element = document.getElementById('pdf-preview-container');
    if (!element) { setIsGeneratingPdf(false); return; }

    try {
      const canvas = await html2canvas(element, { scale: 6, useCORS: true });
      const pdf = new jsPDF({ orientation: 'portrait', unit: 'mm', format: 'letter' });
      const pdfW = pdf.internal.pageSize.getWidth();
      const pdfH = pdf.internal.pageSize.getHeight();
      const totalH = (canvas.height * pdfW) / canvas.width;

      if (totalH <= pdfH) {
        pdf.addImage(canvas.toDataURL('image/jpeg', 0.98), 'JPEG', 0, 0, pdfW, totalH);
      } else {
        const pxPerMm = canvas.width / pdfW;
        const pageHpx = Math.floor(pdfH * pxPerMm);
        let yPx = 0; let pg = 0;
        while (yPx < canvas.height) {
          const slicePx = Math.min(pageHpx, canvas.height - yPx);
          const sc = document.createElement('canvas');
          sc.width = canvas.width; sc.height = slicePx;
          sc.getContext('2d')?.drawImage(canvas, 0, -yPx);
          if (pg > 0) pdf.addPage('letter', 'portrait');
          pdf.addImage(sc.toDataURL('image/jpeg', 0.98), 'JPEG', 0, 0, pdfW, (slicePx / canvas.width) * pdfW);
          yPx += slicePx; pg++;
        }
      }
      pdf.save(`Cotizacion_${selectedQuoteForPrint.id}.pdf`);
    } catch (err) {
      console.error('Error generating PDF:', err);
      alert('Hubo un error al generar el PDF.');
    } finally {
      setIsGeneratingPdf(false);
    }
  };

  const handleConvertQuote = async () => {
    if (!selectedQuoteForConvert) return;
    try {
      let convertDetails;
      if (selectedQuoteForConvert.detalles && selectedQuoteForConvert.detalles.length > 0) {
        convertDetails = selectedQuoteForConvert.detalles.map((det) => ({
          producto_id: det.producto_id,
          cantidad: det.cantidad,
          precio: det.precio,
          ancho: det.ancho ?? undefined,
          largo: det.largo ?? undefined,
          observaciones: det.observaciones ?? undefined,
        }));
      } else {
        const match = selectedQuoteForConvert.observaciones?.match(/Producto: (.*) \((.*)x(.*)m\)/);
        let pId = products[0]?.id || 1;
        let w = 1.0, l = 1.0;
        if (match) {
          const pName = match[1];
          w = Number(match[2]) || 1.0;
          l = Number(match[3]) || 1.0;
          const found = products.find(p => p.nombre === pName);
          if (found) pId = found.id;
        }
        convertDetails = [
          {
            producto_id: pId,
            cantidad: 1,
            precio: selectedQuoteForConvert.total_estimado,
            ancho: w,
            largo: l,
            observaciones: selectedQuoteForConvert.observaciones,
          },
        ];
      }

      await pedidoService.convertQuote(selectedQuoteForConvert.id, convertDetails, deliveryDate || undefined);
      setIsConvertOpen(false);
      alert('¡Cotización convertida a pedido con éxito!');
      fetchQuotes(search);
    } catch (err) {
      console.error(err);
      alert('Error al convertir la cotización a pedido.');
    }
  };

  // Calculations summaries
  const globalTotalCalc = items.reduce((acc, item) => {
    const price = item.calcResult ? item.calcResult.precio_venta : 0;
    return acc + (price * item.cantidad);
  }, 0);

  const globalMaterialCost = items.reduce((acc, item) => {
    const mat = item.calcResult ? item.calcResult.costo_materiales : 0;
    return acc + (mat * item.cantidad);
  }, 0);

  const globalManoObraCost = items.reduce((acc, item) => {
    const mo = item.calcResult ? item.calcResult.costo_mano_obra : 0;
    return acc + (mo * item.cantidad);
  }, 0);

  const globalGastosCost = items.reduce((acc, item) => {
    const g = item.calcResult ? item.calcResult.costo_gastos_indirectos : 0;
    return acc + (g * item.cantidad);
  }, 0);

  const globalCostoTotal = items.reduce((acc, item) => {
    const t = item.calcResult ? item.calcResult.costo_total : 0;
    return acc + (t * item.cantidad);
  }, 0);

  return (
    <div className="space-y-6">
      {/* Top Action Bar */}
      <div className="flex flex-col md:flex-row items-center justify-between gap-4 bg-white p-4 rounded-xl border border-yeikar-secondary-light/10 shadow-sm">
        <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-3 w-full md:w-auto flex-1">
          <div className="relative w-full sm:w-72">
            <input
              type="text"
              placeholder="Buscar cotizaciones..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="w-full pl-10 pr-4 py-2 border border-yeikar-secondary-light/20 rounded-lg focus:outline-none focus:ring-2 focus:ring-yeikar-primary focus:border-transparent font-body bg-yeikar-tertiary/30 text-sm"
            />
            <div className="absolute left-3.5 top-2.5 text-yeikar-neutral/40">
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
              </svg>
            </div>
          </div>
          
          <div className="flex items-center gap-2 bg-yeikar-tertiary/20 p-1.5 rounded-lg border border-yeikar-secondary/10 text-xs">
            <label className="flex items-center gap-1.5 cursor-pointer font-headline font-bold text-yeikar-secondary">
              <input
                type="checkbox"
                checked={!soloMesActual}
                onChange={(e) => setSoloMesActual(!e.target.checked)}
                className="rounded border-yeikar-secondary-light/30 text-yeikar-primary focus:ring-yeikar-primary h-4 w-4"
              />
              Historial Completo
            </label>
            
            {!soloMesActual && (
              <div className="flex items-center gap-1.5 animate-fadeIn">
                <span className="text-yeikar-neutral/40">|</span>
                <select
                  value={selectedMonth}
                  onChange={(e) => setSelectedMonth(Number(e.target.value))}
                  className="bg-white border border-yeikar-secondary-light/20 rounded px-1.5 py-0.5 focus:outline-none focus:ring-1 focus:ring-yeikar-primary text-xs font-mono"
                >
                  {Array.from({ length: 12 }, (_, i) => i + 1).map(m => (
                    <option key={m} value={m}>
                      {new Date(2020, m - 1).toLocaleString('es-ES', { month: 'long' })}
                    </option>
                  ))}
                </select>
                <select
                  value={selectedYear}
                  onChange={(e) => setSelectedYear(Number(e.target.value))}
                  className="bg-white border border-yeikar-secondary-light/20 rounded px-1.5 py-0.5 focus:outline-none focus:ring-1 focus:ring-yeikar-primary text-xs font-mono"
                >
                  {Array.from({ length: 10 }, (_, i) => new Date().getFullYear() - i).map(y => (
                    <option key={y} value={y}>{y}</option>
                  ))}
                </select>
              </div>
            )}
          </div>
        </div>
        <button
          onClick={handleOpenCreate}
          className="w-full sm:w-auto bg-yeikar-primary text-yeikar-neutral font-bold px-5 py-2 rounded-lg shadow-md hover:bg-yeikar-primary-light transition-all flex items-center justify-center gap-2 font-headline"
        >
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 4v16m8-8H4" />
          </svg>
          Nueva Cotización
        </button>
      </div>

      {error && (
        <div className="bg-red-50 text-red-700 p-4 rounded-xl border border-red-200 text-sm">
          {error}
        </div>
      )}

      {/* Main Table */}
      <div className="bg-white rounded-xl border border-yeikar-secondary-light/10 shadow-sm overflow-hidden">
        {loading ? (
          <div className="p-8 text-center text-yeikar-neutral/60 font-mono">Cargando cotizaciones...</div>
        ) : quotes.length === 0 ? (
          <div className="p-8 text-center text-yeikar-neutral/60">No hay cotizaciones registradas.</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse">
              <thead>
                <tr className="bg-yeikar-neutral text-yeikar-tertiary font-headline uppercase text-xs tracking-wider">
                  <th className="px-6 py-4 border-b border-yeikar-secondary/20">Cotización ID</th>
                  <th className="px-6 py-4 border-b border-yeikar-secondary/20">Cliente</th>
                  <th className="px-6 py-4 border-b border-yeikar-secondary/20">Fecha</th>
                  <th className="px-6 py-4 border-b border-yeikar-secondary/20">Detalles</th>
                  <th className="px-6 py-4 border-b border-yeikar-secondary/20">Total Estimado</th>
                  <th className="px-6 py-4 border-b border-yeikar-secondary/20">Estado</th>
                  <th className="px-6 py-4 border-b border-yeikar-secondary/20 text-right">Acciones</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-yeikar-secondary-light/10 text-sm font-body">
                {quotes.map((quote) => (
                  <tr key={quote.id} className="hover:bg-yeikar-tertiary/20 transition-colors">
                    <td className="px-6 py-4 font-mono font-bold text-yeikar-secondary">
                      #{quote.id}
                    </td>
                    <td className="px-6 py-4 font-bold text-yeikar-secondary font-headline">
                      {quote.cliente?.nombre || `Cliente ID: ${quote.cliente_id}`}
                    </td>
                    <td className="px-6 py-4 font-mono text-yeikar-neutral/70">
                      {quote.fecha}
                    </td>
                    <td className="px-6 py-4 text-xs whitespace-pre-line text-yeikar-neutral/80">
                      {quote.observaciones}
                    </td>
                    <td className="px-6 py-4 font-mono font-bold text-yeikar-secondary">
                      ${Number(quote.total_estimado).toLocaleString('es-CO', { minimumFractionDigits: 2 })} COP
                    </td>
                    <td className="px-6 py-4">
                      <span className={`px-2.5 py-1 rounded-full text-xs font-bold font-headline inline-block ${
                        quote.estado === 'APROBADA'
                          ? 'bg-green-100 text-green-800'
                          : quote.estado === 'ENVIADA'
                          ? 'bg-blue-100 text-blue-800'
                          : quote.estado === 'RECHAZADA'
                          ? 'bg-red-100 text-red-800'
                          : quote.estado === 'VENCIDA'
                          ? 'bg-orange-100 text-orange-800'
                          : 'bg-gray-100 text-gray-800'
                      }`}>
                        {quote.estado === 'BORRADOR' ? 'Borrador'
                          : quote.estado === 'ENVIADA' ? 'Enviada'
                          : quote.estado === 'APROBADA' ? 'Aprobada'
                          : quote.estado === 'RECHAZADA' ? 'Rechazada'
                          : quote.estado === 'VENCIDA' ? 'Vencida'
                          : quote.estado}
                      </span>
                    </td>
                    <td className="px-6 py-4 text-right">
                      <div className="flex items-center justify-end gap-2.5">
                        {quote.estado === 'BORRADOR' && (
                          <button
                            onClick={() => handleUpdateStatus(quote, 'ENVIADA')}
                            className="text-xs bg-blue-550 text-blue-600 hover:underline font-bold"
                            title="Enviar"
                          >
                            Enviar
                          </button>
                        )}
                        {quote.estado === 'ENVIADA' && (
                          <>
                            <button
                              onClick={() => handleUpdateStatus(quote, 'APROBADA')}
                              className="text-xs text-green-600 hover:underline font-bold"
                              title="Aprobar"
                            >
                              Aprobar
                            </button>
                            <button
                              onClick={() => handleUpdateStatus(quote, 'RECHAZADA')}
                              className="text-xs text-red-600 hover:underline font-bold"
                              title="Rechazar"
                            >
                              Rechazar
                            </button>
                          </>
                        )}
                        {quote.estado === 'APROBADA' && (
                          <button
                            onClick={() => handleOpenConvert(quote)}
                            className="bg-yeikar-primary hover:bg-yeikar-primary-light text-yeikar-neutral px-2.5 py-1 rounded text-xs font-bold font-headline shadow-sm"
                          >
                            Pedido
                          </button>
                        )}
                        <button
                          onClick={() => handleOpenPrintPreview(quote)}
                          className="bg-yeikar-secondary hover:bg-yeikar-secondary-light text-yeikar-primary px-2.5 py-1 rounded text-xs font-bold font-headline shadow-sm flex items-center gap-1"
                          title="Imprimir Factura Inicial"
                        >
                          <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M17 17h2a2 2 0 002-2v-4a2 2 0 00-2-2H5a2 2 0 00-2 2v4a2 2 0 002 2h2m2 4h6a2 2 0 002-2v-4a2 2 0 00-2-2H9a2 2 0 00-2 2v4a2 2 0 002 2zm8-12V5a2 2 0 00-2-2H9a2 2 0 00-2 2v4h10z" />
                          </svg>
                          Factura
                        </button>
                        <button
                          onClick={() => handleDelete(quote.id)}
                          className="p-1 text-red-600 hover:text-red-800 transition-colors"
                          title="Eliminar"
                        >
                          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                          </svg>
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Quote Form Modal */}
      {isFormOpen && (
        <div className="fixed inset-0 bg-yeikar-neutral/50 backdrop-blur-sm flex items-center justify-center p-4 z-50 overflow-y-auto">
          <div className="bg-white rounded-xl border border-yeikar-secondary-light/10 shadow-2xl w-full max-w-5xl overflow-hidden flex flex-col md:flex-row">
            {/* Form Inputs */}
            <form onSubmit={handleSaveQuote} className="p-6 space-y-4 flex-1 max-h-[85vh] overflow-y-auto">
              <div className="bg-yeikar-neutral -mx-6 -mt-6 p-4 text-yeikar-tertiary flex items-center justify-between mb-4">
                <h3 className="font-headline font-bold text-lg text-yeikar-primary">
                  {editingQuote ? 'Editar Cotización' : 'Nueva Cotización Paramétrica (Múltiples Muebles)'}
                </h3>
              </div>

              <div>
                <label className="block text-xs uppercase tracking-wider font-bold text-yeikar-neutral/60 font-headline mb-1">
                  Cliente *
                </label>
                <select
                  value={selectedClientId}
                  onChange={(e) => setSelectedClientId(e.target.value)}
                  required
                  className="w-full p-2 border border-yeikar-secondary-light/20 rounded-lg focus:ring-2 focus:ring-yeikar-primary focus:outline-none bg-yeikar-tertiary/20 text-sm"
                >
                  <option value="">Selecciona un cliente...</option>
                  {clients.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.nombre} ({c.email || c.telefono})
                    </option>
                  ))}
                </select>
              </div>

              <div className="border-t border-yeikar-secondary-light/15 my-4 pt-4">
                <div className="flex items-center justify-between mb-3">
                  <h4 className="font-headline font-black text-sm text-yeikar-secondary tracking-tight">
                    Renglones / Productos Cotizados
                  </h4>
                  <button
                    type="button"
                    onClick={addItem}
                    className="bg-yeikar-secondary text-yeikar-tertiary text-xs font-bold px-3 py-1.5 rounded-lg hover:bg-yeikar-secondary-light transition-all flex items-center gap-1"
                  >
                    <span>+ Añadir Mueble</span>
                  </button>
                </div>

                <div className="space-y-4">
                  {items.map((item, index) => (
                    <div key={index} className="bg-yeikar-tertiary/25 p-4 rounded-xl border border-yeikar-secondary-light/5 relative space-y-3">
                      {items.length > 1 && (
                        <button
                          type="button"
                          onClick={() => removeItem(index)}
                          className="absolute top-2 right-2 text-red-500 hover:text-red-700 text-xs font-bold font-headline"
                          title="Eliminar renglón"
                        >
                          Eliminar
                        </button>
                      )}

                      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                        <div className="sm:col-span-2">
                          <label className="block text-[10px] uppercase font-bold text-yeikar-neutral/50 mb-1">
                            Mueble Modelo *
                          </label>
                          <select
                            value={item.producto_id}
                            onChange={(e) => updateItemField(index, 'producto_id', e.target.value)}
                            required
                            className="w-full p-2 border border-yeikar-secondary-light/20 rounded-lg focus:ring-2 focus:ring-yeikar-primary focus:outline-none bg-white text-xs"
                          >
                            <option value="">Seleccione mueble...</option>
                            {products.map((p) => (
                              <option key={p.id} value={p.id}>
                                {p.nombre} (${Number(p.precio_base).toLocaleString()} base)
                              </option>
                            ))}
                          </select>
                        </div>
                        <div>
                          <label className="block text-[10px] uppercase font-bold text-yeikar-neutral/50 mb-1">
                            Cantidad
                          </label>
                          <input
                            type="number"
                            min="1"
                            value={item.cantidad}
                            onChange={(e) => updateItemField(index, 'cantidad', parseInt(e.target.value) || 1)}
                            required
                            className="w-full p-2 border border-yeikar-secondary-light/20 rounded-lg focus:ring-2 focus:ring-yeikar-primary focus:outline-none bg-white text-xs font-mono"
                          />
                        </div>
                      </div>

                      <div className="grid grid-cols-3 gap-2">
                        <div>
                          <label className="block text-[10px] uppercase font-bold text-yeikar-neutral/50 mb-1">
                            Ancho (m)
                          </label>
                          <input
                            type="number"
                            step="0.01"
                            value={item.ancho}
                            onChange={(e) => updateItemField(index, 'ancho', e.target.value)}
                            className="w-full p-2 border border-yeikar-secondary-light/20 rounded-lg focus:ring-2 focus:ring-yeikar-primary focus:outline-none bg-white text-xs font-mono"
                          />
                        </div>
                        <div>
                          <label className="block text-[10px] uppercase font-bold text-yeikar-neutral/50 mb-1">
                            Largo (m)
                          </label>
                          <input
                            type="number"
                            step="0.01"
                            value={item.largo}
                            onChange={(e) => updateItemField(index, 'largo', e.target.value)}
                            className="w-full p-2 border border-yeikar-secondary-light/20 rounded-lg focus:ring-2 focus:ring-yeikar-primary focus:outline-none bg-white text-xs font-mono"
                          />
                        </div>
                        <div>
                          <label className="block text-[10px] uppercase font-bold text-yeikar-neutral/50 mb-1">
                            % Ganancia
                          </label>
                          <input
                            type="number"
                            value={item.ganancia}
                            onChange={(e) => updateItemField(index, 'ganancia', e.target.value)}
                            className="w-full p-2 border border-yeikar-secondary-light/20 rounded-lg focus:ring-2 focus:ring-yeikar-primary focus:outline-none bg-white text-xs font-mono"
                          />
                        </div>
                      </div>

                      <div className="grid grid-cols-1 sm:grid-cols-4 gap-2 items-center">
                        <div className="sm:col-span-3">
                          <input
                            type="text"
                            placeholder="Observación de este mueble (ej: Tela gris, patas madera)"
                            value={item.observaciones}
                            onChange={(e) => updateItemField(index, 'observaciones', e.target.value)}
                            className="w-full p-2 border border-yeikar-secondary-light/20 rounded-lg focus:ring-2 focus:ring-yeikar-primary focus:outline-none bg-white text-xs"
                          />
                        </div>
                        <div className="text-right font-mono text-xs font-bold text-yeikar-secondary">
                          {item.calcLoading ? (
                            <span className="text-yeikar-neutral/40">Calculando...</span>
                          ) : item.calcResult ? (
                            <span>Subt: ${(item.calcResult.precio_venta * item.cantidad).toLocaleString('es-CO')}</span>
                          ) : (
                            <span>$0.00</span>
                          )}
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              <div>
                <label className="block text-xs uppercase tracking-wider font-bold text-yeikar-neutral/60 font-headline mb-1">
                  Nota global de la cotización
                </label>
                <textarea
                  value={observaciones}
                  onChange={(e) => setObservaciones(e.target.value)}
                  rows={2}
                  className="w-full p-2 border border-yeikar-secondary-light/20 rounded-lg focus:ring-2 focus:ring-yeikar-primary focus:outline-none bg-yeikar-tertiary/20 text-sm"
                  placeholder="Observaciones generales para toda la cotización/orden..."
                />
              </div>

              <div className="flex items-center justify-end gap-3 pt-4 border-t border-yeikar-secondary-light/10">
                <button
                  type="button"
                  onClick={() => setIsFormOpen(false)}
                  className="px-4 py-2 border border-yeikar-secondary-light/20 hover:bg-yeikar-tertiary/20 rounded-lg text-sm font-headline"
                >
                  Cancelar
                </button>
                <button
                  type="submit"
                  className="px-5 py-2 bg-yeikar-primary text-yeikar-neutral font-bold rounded-lg shadow-md hover:bg-yeikar-primary-light transition-all text-sm font-headline"
                >
                  {editingQuote ? 'Actualizar' : 'Guardar Cotización'}
                </button>
              </div>
            </form>

            {/* Calculations Breakdown */}
            <div className="w-full md:w-80 bg-yeikar-neutral text-yeikar-tertiary p-6 flex flex-col justify-between border-t md:border-t-0 md:border-l border-yeikar-secondary/20">
              <div>
                <h4 className="font-headline font-bold text-sm text-yeikar-primary tracking-wider uppercase mb-4">
                  Totales de Cotización
                </h4>
                <div className="space-y-4">
                  <div className="space-y-1">
                    <div className="flex justify-between text-xs text-yeikar-tertiary/60">
                      <span>Costo Materiales:</span>
                      <span className="font-mono">${Number(globalMaterialCost).toLocaleString('es-CO')}</span>
                    </div>
                    <div className="flex justify-between text-xs text-yeikar-tertiary/60">
                      <span>Costo Mano Obra:</span>
                      <span className="font-mono">${Number(globalManoObraCost).toLocaleString('es-CO')}</span>
                    </div>
                    <div className="flex justify-between text-xs text-yeikar-tertiary/60">
                      <span>Costo Indirecto:</span>
                      <span className="font-mono">${Number(globalGastosCost).toLocaleString('es-CO')}</span>
                    </div>
                    <div className="border-t border-yeikar-secondary-light/10 my-2" />
                    <div className="flex justify-between text-xs text-yeikar-primary font-bold">
                      <span>Costo Total Fábrica:</span>
                      <span className="font-mono">${Number(globalCostoTotal).toLocaleString('es-CO')}</span>
                    </div>
                  </div>
                </div>
              </div>

              <div className="border-t border-yeikar-secondary/40 pt-4 mt-6">
                <span className="text-[10px] text-yeikar-tertiary/40 uppercase tracking-widest block mb-1">
                  PRECIO TOTAL SUGERIDO:
                </span>
                <div className="text-2xl font-black text-yeikar-primary font-mono">
                  ${Number(globalTotalCalc).toLocaleString('es-CO', { maximumFractionDigits: 0 })}
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Convert Quote to Order Modal */}
      {isConvertOpen && (
        <div className="fixed inset-0 bg-yeikar-neutral/50 backdrop-blur-sm flex items-center justify-center p-4 z-50 animate-fade-in">
          <div className="bg-white rounded-xl border border-yeikar-secondary-light/10 shadow-2xl w-full max-w-md overflow-hidden">
            <div className="bg-yeikar-neutral p-4 text-yeikar-tertiary flex items-center justify-between">
              <h3 className="font-headline font-bold text-lg text-yeikar-primary">
                Convertir a Pedido de Fábrica
              </h3>
            </div>
            <div className="p-6 space-y-4">
              <p className="text-sm text-yeikar-neutral/80 font-body">
                Vas a generar un nuevo pedido para <strong>{selectedQuoteForConvert?.cliente?.nombre}</strong>.
                Por favor indica la fecha estimada de entrega.
              </p>
              <div>
                <label className="block text-xs uppercase tracking-wider font-bold text-yeikar-neutral/60 font-headline mb-1">
                  Fecha Estimada de Entrega
                </label>
                <input
                  type="date"
                  value={deliveryDate}
                  onChange={(e) => setDeliveryDate(e.target.value)}
                  className="w-full p-2 border border-yeikar-secondary-light/20 rounded-lg focus:ring-2 focus:ring-yeikar-primary focus:outline-none bg-yeikar-tertiary/20 font-mono text-sm"
                />
              </div>

              <div className="flex items-center justify-end gap-3 pt-4 border-t border-yeikar-secondary-light/10">
                <button
                  onClick={() => setIsConvertOpen(false)}
                  className="px-4 py-2 border border-yeikar-secondary-light/20 hover:bg-yeikar-tertiary/20 rounded-lg text-sm font-headline"
                >
                  Cancelar
                </button>
                <button
                  onClick={handleConvertQuote}
                  className="px-5 py-2 bg-yeikar-primary text-yeikar-neutral font-bold rounded-lg shadow-md hover:bg-yeikar-primary-light transition-all text-sm font-headline"
                >
                  Confirmar Conversión
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Print Config & Interactive Preview Modal */}
      {isPrintModalOpen && selectedQuoteForPrint && (() => {
        const subTotal    = Number(selectedQuoteForPrint.total_estimado) || 0;
        const discountVal = subTotal * (Number(printDiscount || 0) / 100);
        const netSubTotal = subTotal - discountVal;
        const ivaVal      = netSubTotal * (Number(printIva || 0) / 100);
        const grandTotal  = netSubTotal + ivaVal;
        const usdTotal    = grandTotal / (Number(printExchangeRate) || 1);

        return (
          <div className="fixed inset-0 bg-yeikar-neutral/60 backdrop-blur-sm flex items-center justify-center p-4 z-50 overflow-hidden">
            <div className="bg-white rounded-2xl border border-yeikar-secondary-light/10 shadow-2xl w-full max-w-6xl h-[92vh] flex flex-col overflow-hidden">

              {/* Modal Header */}
              <div className="bg-yeikar-neutral px-5 py-3.5 flex items-center justify-between shrink-0">
                <div>
                  <h3 className="font-headline font-bold text-base text-yeikar-primary leading-tight">
                    Cotización #{selectedQuoteForPrint.id.toString().padStart(5, '0')} — Vista Previa
                  </h3>
                  <p className="text-yeikar-tertiary/50 text-xs font-mono mt-0.5">
                    {selectedQuoteForPrint.cliente?.nombre}
                  </p>
                </div>
                <button
                  onClick={() => setIsPrintModalOpen(false)}
                  className="text-yeikar-tertiary/60 hover:text-yeikar-primary text-sm font-bold font-headline transition-colors"
                >
                  ✕ Cerrar
                </button>
              </div>

              {/* Body */}
              <div className="flex-1 flex flex-col md:flex-row overflow-hidden">

                {/* ─── Left: Config Panel ─── */}
                <div className="w-full md:w-80 shrink-0 p-5 border-b md:border-b-0 md:border-r border-stone-100 overflow-y-auto space-y-5 bg-white">

                  <section className="space-y-2">
                    <h4 className="text-[10px] uppercase tracking-widest font-bold text-stone-400">Datos del Cliente</h4>
                    <div>
                      <label className="block text-[10px] uppercase font-bold text-stone-400 mb-1">RIF / C.I.</label>
                      <input type="text" placeholder="V-12345678-9" value={printClientRif}
                        onChange={e => setPrintClientRif(e.target.value)}
                        className="w-full p-2 border border-stone-200 rounded-lg text-xs focus:ring-1 focus:ring-amber-500 outline-none" />
                    </div>
                  </section>

                  <hr className="border-stone-100" />

                  <section className="space-y-2">
                    <h4 className="text-[10px] uppercase tracking-widest font-bold text-stone-400">Tasas & Ajustes</h4>
                    <div className="grid grid-cols-3 gap-2">
                      {[
                        { label: 'Tasa COP/USD', val: printExchangeRate, set: setPrintExchangeRate },
                        { label: 'Descuento %',  val: printDiscount,     set: setPrintDiscount     },
                        { label: 'IVA %',         val: printIva,          set: setPrintIva          },
                      ].map(({ label, val, set }) => (
                        <div key={label}>
                          <label className="block text-[10px] uppercase font-bold text-stone-400 mb-1">{label}</label>
                          <input type="number" min="0" value={val} onChange={e => set(e.target.value)}
                            className="w-full p-2 border border-stone-200 rounded-lg text-xs font-mono focus:ring-1 focus:ring-amber-500 outline-none" />
                        </div>
                      ))}
                    </div>
                  </section>

                  <hr className="border-stone-100" />

                  <section className="space-y-2">
                    <h4 className="text-[10px] uppercase tracking-widest font-bold text-stone-400">Emisor (Yeikar)</h4>
                    <div>
                      <label className="block text-[10px] uppercase font-bold text-stone-400 mb-1">RIF</label>
                      <input type="text" value={printCompanyRif} onChange={e => setPrintCompanyRif(e.target.value)}
                        className="w-full p-2 border border-stone-200 rounded-lg text-xs focus:ring-1 focus:ring-amber-500 outline-none" />
                    </div>
                    <div>
                      <label className="block text-[10px] uppercase font-bold text-stone-400 mb-1">Dirección</label>
                      <textarea rows={2} value={printCompanyAddress} onChange={e => setPrintCompanyAddress(e.target.value)}
                        className="w-full p-2 border border-stone-200 rounded-lg text-xs focus:ring-1 focus:ring-amber-500 outline-none resize-none" />
                    </div>
                    <div>
                      <label className="block text-[10px] uppercase font-bold text-stone-400 mb-1">Teléfono</label>
                      <input type="text" value={printCompanyPhone} onChange={e => setPrintCompanyPhone(e.target.value)}
                        className="w-full p-2 border border-stone-200 rounded-lg text-xs focus:ring-1 focus:ring-amber-500 outline-none" />
                    </div>
                  </section>

                  <button
                    type="button"
                    onClick={handleGeneratePdf}
                    disabled={isGeneratingPdf}
                    className="w-full bg-stone-900 text-amber-400 font-bold py-3 rounded-xl shadow-md hover:bg-stone-800 transition-all flex items-center justify-center gap-2 font-headline disabled:opacity-50 text-sm border-t-2 border-amber-500"
                  >
                    {isGeneratingPdf ? (
                      <span className="animate-pulse">Generando PDF…</span>
                    ) : (
                      <>
                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                        </svg>
                        Descargar PDF
                      </>
                    )}
                  </button>
                </div>

                {/* ─── Right: Live Preview ─── */}
                <div className="flex-1 overflow-y-auto bg-stone-100 p-8">
                  {/*
                    IMPORTANT: min-h-[279.4mm] NOT h-[279.4mm]
                    The container grows with content — no stretching.
                    For PDFs larger than one page the canvas-slicing
                    function handles the split automatically.
                  */}
                  <div
                    id="pdf-preview-container"
                    className="bg-white shadow-2xl relative text-stone-800 font-sans mx-auto"
                    style={{
                      width: '215.9mm',
                      minHeight: '279.4mm',
                      padding: '14mm 15mm',
                      boxSizing: 'border-box',
                      display: 'flex',
                      flexDirection: 'column',
                      
                    }}
                  >
                    {/* Watermark */}
                    <div className="absolute inset-0 flex items-center justify-center pointer-events-none opacity-[0.035] z-0 select-none">
                      <img src="/logo-marca-de-agua.PNG" alt="" className="w-[420px] h-auto" />
                    </div>

                    {/* ── All content above watermark ── */}
                    <div className="relative z-10 flex flex-col gap-4 flex-1">
                      <div className="flex flex-col gap-4">

                      {/* ── Header ── */}
                      <div className="flex justify-between items-start pb-3 border-b border-stone-300">
                        <div className="space-y-1.5 max-w-[60%]">
                          <img src="/Logo-yeikar.png" alt="Yeikar" className="h-12 object-contain" />
                          <div className="font-serif font-bold text-stone-955 text-[11.5px] tracking-widest uppercase mt-1">
                            Comercializadora Yeikar
                          </div>
                          <div className="text-[8px] text-stone-600 font-mono font-semibold">RIF: {printCompanyRif}</div>
                          <div className="text-[8px] text-stone-650 font-medium leading-snug">DIRECCIÓN: {printCompanyAddress}</div>
                          <div className="text-[8px] text-stone-600 font-mono font-semibold">TELÉFONO: {printCompanyPhone}</div>
                        </div>

                        <div className="text-right border border-stone-300 rounded-lg p-3 bg-stone-50 min-w-[170px] shadow-sm">
                          <div className="text-[8.5px] font-bold text-stone-700 uppercase tracking-[0.15em]">Cotización / Factura Inicial</div>
                          <div className="text-sm font-bold text-amber-800 font-mono tracking-widest mt-0.5">
                            N°: 00 – {selectedQuoteForPrint.id.toString().padStart(5, '0')}
                          </div>
                          <div className="text-[8px] text-stone-600 font-mono font-bold mt-1 uppercase tracking-wider">
                            Fecha: {selectedQuoteForPrint.fecha}
                          </div>
                        </div>
                      </div>

                      {/* ── Client Info ── */}
                      <div className="grid grid-cols-4 gap-4 bg-stone-50/40 border border-stone-250 rounded-xl px-4 py-3 my-1 shadow-sm">
                        {[
                          { label: 'CLIENTE',    value: selectedQuoteForPrint.cliente?.nombre },
                          { label: 'RIF / C.I.', value: printClientRif || '—' },
                          { label: 'TELÉFONO',   value: selectedQuoteForPrint.cliente?.telefono || '—' },
                          { label: 'DIRECCIÓN',  value: selectedQuoteForPrint.cliente?.direccion || '—' },
                        ].map(({ label, value }) => (
                          <div key={label} className="min-w-0">
                            <div className="text-[7.5px] uppercase tracking-[0.14em] text-stone-550 font-bold mb-1">{label}</div>
                            <div className="text-[10px] text-stone-950 font-extrabold leading-relaxed whitespace-pre-wrap break-words" title={value}>{value}</div>
                          </div>
                        ))}
                      </div>

                      {/* ── Items Table ── */}
                      <div className="border border-stone-300 rounded-lg overflow-hidden shadow-sm">
                        <table className="w-full border-collapse text-[9.5px]">
                          <thead>
                            <tr className="bg-stone-900 text-stone-100">
                              {['Modelo', 'Cant.', 'Descripción / Medidas', 'P. Unitario', 'Total (COP)'].map((h, i) => (
                                <th key={h} className={`px-3 py-2 font-serif font-bold uppercase tracking-[0.12em] text-[8px]
                                  ${i === 0 ? 'text-left w-[20%]' : i === 1 ? 'text-center w-[8%]' : i === 2 ? 'text-left' : 'text-right w-[13%]'}`}>{h}</th>
                              ))}
                            </tr>
                          </thead>
                          <tbody className="divide-y divide-stone-200">
                            {selectedQuoteForPrint.detalles && selectedQuoteForPrint.detalles.length > 0 ? (
                              selectedQuoteForPrint.detalles.map((det, idx) => {
                                const prod       = products.find(p => p.id === det.producto_id);
                                const modelName  = prod?.nombre ?? `Prod #${det.producto_id}`;
                                const dims       = `${det.ancho ?? 1.0}×${det.largo ?? 1.0} m`;
                                const desc       = det.observaciones ? `${dims} — ${det.observaciones}` : dims;
                                const rowTotal   = Number(det.precio) * Number(det.cantidad);
                                return (
                                  <tr key={idx} className={idx % 2 === 0 ? 'bg-white' : 'bg-stone-50/60'}>
                                    <td className="px-3 py-2 font-serif font-bold text-stone-950">{modelName}</td>
                                    <td className="px-3 py-2 text-center font-mono font-extrabold text-stone-900">{Number(det.cantidad).toFixed(0)}</td>
                                    <td className="px-3 py-2 text-stone-700 italic font-medium">{desc}</td>
                                    <td className="px-3 py-2 text-right font-mono text-stone-850 font-medium">${Number(det.precio).toLocaleString('es-CO')}</td>
                                    <td className="px-3 py-2 text-right font-mono font-extrabold text-stone-950">${rowTotal.toLocaleString('es-CO')}</td>
                                  </tr>
                                );
                              })
                            ) : (
                              <tr><td colSpan={5} className="px-3 py-4 text-center text-stone-400 italic">Sin renglones.</td></tr>
                            )}
                          </tbody>
                        </table>
                      </div>

                      {/* ── Totals: Left=breakdown, Right=grand total card ── */}
                      <div className="grid grid-cols-2 gap-4 pt-1">

                        {/* Left — subtotal breakdown */}
                        <div className="space-y-1 text-[9.5px] text-stone-700 pr-2">
                          {[
                            { label: 'Sub-Total',    value: subTotal,    color: 'text-stone-900 font-bold' },
                            ...(Number(printDiscount) > 0 ? [{ label: `Descuento (${printDiscount}%)`, value: -discountVal, color: 'text-emerald-800 font-bold' }] : []),
                            { label: 'Neto Sub-Total', value: netSubTotal, color: 'text-stone-900 font-bold' },
                            ...(Number(printIva) > 0 ? [{ label: `IVA (${printIva}%)`, value: ivaVal, color: 'text-stone-900 font-bold' }] : []),
                          ].map(({ label, value, color }, i, arr) => (
                            <div key={label} className={`flex justify-between items-center ${i === arr.length - 1 ? 'border-t border-stone-300 pt-1' : ''}`}>
                              <span className="text-[7.5px] uppercase tracking-wider font-bold text-stone-500">{label}</span>
                              <span className={`font-mono font-extrabold ${color}`}>
                                {value < 0 ? '-' : ''}${Math.abs(value).toLocaleString('es-CO')} COP
                              </span>
                            </div>
                          ))}
                        </div>

                        {/* Right — grand total card */}
                        <div className="bg-stone-900 rounded-xl p-3 flex flex-col gap-1.5 shadow-md border-t-2 border-amber-600">
                          <div className="flex justify-between items-baseline">
                            <span className="text-[7.5px] tracking-[0.18em] font-bold text-stone-300 uppercase">Total a Pagar</span>
                            <span className="text-sm font-bold text-amber-400 font-mono">
                              ${Number(grandTotal).toLocaleString('es-CO')} COP
                            </span>
                          </div>
                          <div className="border-t border-stone-850 pt-1.5 space-y-0.5 text-[8.5px]">
                            <div className="flex justify-between text-stone-200 font-mono font-extrabold">
                              <span>BASE USD:</span>
                              <span className="text-amber-300">${usdTotal.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} USD</span>
                            </div>
                            <div className="flex justify-between text-stone-400 font-medium">
                              <span>TASA:</span>
                              <span className="font-mono">{Number(printExchangeRate).toLocaleString('es-CO')} COP/USD</span>
                            </div>
                          </div>
                        </div>
                      </div>

                      {/* ── Terms ── */}
                      <div className="border border-stone-300 rounded-lg px-3 py-2 bg-stone-55/40 text-[10.5px] text-stone-750 leading-relaxed font-medium">
                        <span className="font-bold text-stone-900 text-[10px] uppercase tracking-wider mr-1">Términos y Condiciones:</span>
                        Una vez aceptado el pedido y firmado este comprobante se procederá con la fabricación personalizada. Debido a que el producto entra en proceso de corte e insumos a la medida,{' '}
                        <strong className="text-stone-950 font-bold">no se aceptan cambios a último minuto</strong>.
                      </div>
                      </div>

                      {/* ── Signatures ── */}
                      <div className="grid grid-cols-2 gap-10 pt-8 mt-auto">
                        {['FIRMA DEL CLIENTE', 'FIRMA DEL EMISOR'].map(label => (
                          <div key={label} className="text-center">
                            <div className="w-36 border-t border-stone-400 mx-auto mb-1" />
                            <div className="text-[8px] font-serif font-bold uppercase tracking-wider text-stone-800">{label}</div>
                            <div className="text-[7px] text-stone-500 font-medium mt-0.5">
                              {label.includes('CLIENTE') ? 'Acepto Conforme' : 'Autorizado'}
                            </div>
                          </div>
                        ))}
                      </div>

                    </div>{/* end z-10 */}
                  </div>{/* end pdf-preview-container */}
                </div>{/* end right panel */}
              </div>{/* end body */}
            </div>
          </div>
        );
      })()}


    </div>
  );
}