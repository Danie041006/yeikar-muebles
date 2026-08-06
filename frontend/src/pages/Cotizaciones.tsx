import { useEffect, useState } from 'react';
import html2canvas from 'html2canvas';
import { jsPDF } from 'jspdf';
import { cotizacionService, Quote, QuoteCreate, Product, CalculationResult, QuoteDetail, Moneda } from '../services/cotizacionService';
import { clienteService, Client } from '../services/clienteService';
import { pedidoService } from '../services/pedidoService';
import { ventaService, VentaDetalle, METODOS_PAGO } from '../services/ventaService';
import { formatCurrency } from '../utils/format';

import api from '../services/api';
import { productosService } from '../services/productosService';

interface CotizacionItemForm {
  producto_id: string;
  cantidad: number;
  ancho: string;
  largo: string;
  ganancia: string;
  observaciones: string;
  calcResult: CalculationResult | null;
  calcLoading: boolean;
  receta_personalizada?: any[] | null;
}

export default function Cotizaciones() {
  const [quotes, setQuotes] = useState<Quote[]>([]);
  const [clients, setClients] = useState<Client[]>([]);
  const [products, setProducts] = useState<Product[]>([]);
  const [materiales, setMateriales] = useState<any[]>([]);
  
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
  const [printDiscount, setPrintDiscount] = useState('0');
  const [printIva, setPrintIva] = useState('0');
  const [printCompanyRif, setPrintCompanyRif] = useState('J-50146039-3');
  const [printCompanyAddress, setPrintCompanyAddress] = useState('AV. INTERCOMUNAL CON CALLE 16 LOCAL Nro 15-205, BARRIO SIMÓN BOLÍVAR, UREÑA, TÁCHIRA');
  const [printCompanyPhone, setPrintCompanyPhone] = useState('+58 412-1234567');
  const [isGeneratingPdf, setIsGeneratingPdf] = useState(false);
  const [associatedVenta, setAssociatedVenta] = useState<VentaDetalle | null>(null);

  // Convert Form state
  const [deliveryDate, setDeliveryDate] = useState('');
  const [isConverting, setIsConverting] = useState(false);
  const [convertError, setConvertError] = useState('');

  // Adelanto de la conversión (opcional)
  const [adelantoPct, setAdelantoPct] = useState('');
  const [adelantoMonedaId, setAdelantoMonedaId] = useState<number>(1);
  const [adelantoTrm, setAdelantoTrm] = useState('');
  const [adelantoMetodo, setAdelantoMetodo] = useState('');

  // Create/Edit Form state (multi-item)
  const [editingQuote, setEditingQuote] = useState<Quote | null>(null);
  const [selectedClientId, setSelectedClientId] = useState('');
  const [observaciones, setObservaciones] = useState('');
  const [items, setItems] = useState<CotizacionItemForm[]>([
    { producto_id: '', cantidad: 1, ancho: '1.0', largo: '1.0', ganancia: '40.0', observaciones: '', calcResult: null, calcLoading: false, receta_personalizada: null }
  ]);

  // Modal de personalización de receta ad-hoc por renglón
  const [showPersonalizarModal, setShowPersonalizarModal] = useState(false);
  const [personalizarIndex, setPersonalizarIndex] = useState<number | null>(null);
  const [personalizarSecciones, setPersonalizarSecciones] = useState<any[]>([]);
  const [modalPreviewCalc, setModalPreviewCalc] = useState<CalculationResult | null>(null);
  const [modalPreviewLoading, setModalPreviewLoading] = useState(false);

  // Para agregar un insumo ad-hoc en el modal
  const [addMaterialSearch, setAddMaterialSearch] = useState('');
  const [showAddMaterialDropdown, setShowAddMaterialDropdown] = useState(false);
  const [addMaterialSeccionIndex, setAddMaterialSeccionIndex] = useState<number | null>(null);

  // Para agregar un costo de producción ad-hoc
  const [showAddCostModal, setShowAddCostModal] = useState(false);
  const [addCostSeccionIndex, setAddCostSeccionIndex] = useState<number | null>(null);
  const [addCostForm, setAddCostForm] = useState({ nombre: '', porcentaje: '', costo_base: '' });

  // Rango/mueble seleccionado para ver desglose detallado de secciones en la barra lateral
  const [desgloseIndex, setDesgloseIndex] = useState<number>(0);

  // Currency state
  const [currencies, setCurrencies] = useState<Moneda[]>([]);
  const [selectedMonedaId, setSelectedMonedaId] = useState<number>(1);
  const [tasaCambio, setTasaCambio] = useState<number>(1);

  const selectedMoneda = currencies.find(c => c.id === selectedMonedaId);
  const currencyCode = selectedMoneda?.codigo || 'COP';

  // ── Derivados del modal de conversión (adelanto) ──────────────────────────
  const quoteEnConversion = selectedQuoteForConvert;
  const quoteTotal = Number(quoteEnConversion?.total_estimado) || 0;
  const quoteMoneda = currencies.find((c) => c.id === quoteEnConversion?.moneda_id);
  const monedaAdelantoSel = currencies.find((c) => c.id === adelantoMonedaId);

  // Tasa del abono ('1 {pago} = X {factura}') derivada de la TRM fijada en la cotización.
  // null = el par no se puede deducir (p.ej. VES) → se pedirá TRM manual.
  const tasaAbonoDerivada = () => {
    if (!quoteEnConversion) return 1;
    if (adelantoMonedaId === quoteEnConversion.moneda_id) return 1;
    const qt = Number(quoteEnConversion.tasa_cambio) || 0;
    if (!qt) return null;
    const qCode = quoteMoneda?.codigo;
    const pCode = monedaAdelantoSel?.codigo;
    if (qCode === 'COP' && pCode === 'USD') return qt;
    if (qCode === 'USD' && pCode === 'COP') return 1 / qt;
    return null;
  };

  const pctAbono = Number(adelantoPct) || 0;
  const abonoQuote = (quoteTotal * pctAbono) / 100;
  const tasaAbono = tasaAbonoDerivada();
  const necesitaTrmAbono = pctAbono > 0 && tasaAbono === null;
  const abonoMontoPago = pctAbono > 0 && tasaAbono ? abonoQuote / tasaAbono : 0;

  const fetchInitialData = async () => {
    try {
      const [cls, prds, mats, currs] = await Promise.all([
        clienteService.getAll(),
        cotizacionService.getProducts(),
        productosService.getMateriales(),
        cotizacionService.fetchCurrencies(),
      ]);
      setClients(cls);
      setProducts(prds);
      setMateriales(mats);
      setCurrencies(currs);
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
  const calculateItemPrice = async (index: number, pId: string, w: string, l: string, g: string, overrideReceta?: any[] | null) => {
    if (!pId) {
      updateItemField(index, 'calcResult', null);
      return;
    }
    
    const customRecipe: any[] | null = overrideReceta !== undefined ? overrideReceta : null;
    setItems((prevItems) => {
      const newItems = [...prevItems];
      newItems[index] = { ...newItems[index], calcLoading: true };
      return newItems;
    });

    try {
      let res;
      if (customRecipe && customRecipe.length > 0) {
        res = await cotizacionService.recalculateCustomRecipe(Number(g) || 40.0, customRecipe);
      } else {
        res = await cotizacionService.calculatePrice(Number(pId), {
          ancho: Number(w) || 1.0,
          largo: Number(l) || 1.0,
          ganancia: Number(g) || 40.0,
        });
      }
      
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
        newItems[index].receta_personalizada = null;
      }
      
      return newItems;
    });

    // recalculate if relevant field changed
    if (['producto_id', 'ancho', 'largo', 'ganancia'].includes(field)) {
      setItems((prevItems) => {
        const current = prevItems[index];
        calculateItemPrice(index, current.producto_id, current.ancho, current.largo, current.ganancia, current.receta_personalizada);
        return prevItems;
      });
    }
  };

  const handleOpenPersonalizarReceta = async (index: number) => {
    const item = items[index];
    if (!item.producto_id) {
      alert('Por favor selecciona un mueble primero.');
      return;
    }
    
    setPersonalizarIndex(index);
    
    if (item.receta_personalizada) {
      setPersonalizarSecciones(JSON.parse(JSON.stringify(item.receta_personalizada)));
      setModalPreviewCalc(item.calcResult || null);
      setShowPersonalizarModal(true);
    } else {
      try {
        setItems(prev => {
          const newItems = [...prev];
          newItems[index].calcLoading = true;
          return newItems;
        });
        const res = await api.get(`/producto/${item.producto_id}/receta-estructurada`);
        setPersonalizarSecciones(res.data);
        setShowPersonalizarModal(true);
      } catch (err) {
        console.error('Error al cargar la receta estructurada:', err);
        alert('Error al cargar la estructura del mueble.');
      } finally {
        setItems(prev => {
          const newItems = [...prev];
          newItems[index].calcLoading = false;
          return newItems;
        });
      }
    }
  };

  const handleUpdateSeccionPolitica = (seccionIndex: number, field: string, value: string) => {
    setPersonalizarSecciones(prev => {
      const newSecs = [...prev];
      if (!newSecs[seccionIndex].politica) {
        newSecs[seccionIndex].politica = { pct_gastos_seccion: 10, pct_trabajadores: 8, costo_fabricacion: 0 };
      }
      newSecs[seccionIndex].politica[field] = value ? parseFloat(value) : 0;
      return newSecs;
    });
  };

  const handleUpdateInsumoField = (seccionIndex: number, elementoIndex: number, field: string, value: string) => {
    setPersonalizarSecciones(prev => {
      const newSecs = [...prev];
      newSecs[seccionIndex].elementos[elementoIndex][field] = value ? parseFloat(value) : 0;
      return newSecs;
    });
  };

  const handleRemoveInsumo = (seccionIndex: number, elementoIndex: number) => {
    setPersonalizarSecciones(prev => {
      const newSecs = [...prev];
      newSecs[seccionIndex].elementos = newSecs[seccionIndex].elementos.filter((_: any, i: number) => i !== elementoIndex);
      return newSecs;
    });
  };

  const handleOpenAddMaterial = (seccionIndex: number) => {
    setAddMaterialSeccionIndex(seccionIndex);
    setAddMaterialSearch('');
    setShowAddMaterialDropdown(true);
  };

  const handleAddMaterialToSeccion = (material: any) => {
    if (addMaterialSeccionIndex === null) return;
    setPersonalizarSecciones(prev => {
      const newSecs = [...prev];
      const newEl = {
        id: Date.now(), // ID temporal
        seccion_id: newSecs[addMaterialSeccionIndex].id,
        nombre_insumo_original: material.nombre,
        material_id_normalizado: material.id,
        cantidad: 1,
        unidad_medida: material.unidad_medida?.abreviatura || 'un',
        precio_unitario: material.costo_base,
      };
      newSecs[addMaterialSeccionIndex].elementos.push(newEl);
      return newSecs;
    });
    setShowAddMaterialDropdown(false);
    setAddMaterialSeccionIndex(null);
  };

  const handleOpenAddCost = (seccionIndex: number) => {
    setAddCostSeccionIndex(seccionIndex);
    setAddCostForm({ nombre: '', porcentaje: '', costo_base: '' });
    setShowAddCostModal(true);
  };

  const handleAddCostToSeccion = (e: React.FormEvent) => {
    e.preventDefault();
    if (addCostSeccionIndex === null || !addCostForm.nombre.trim()) return;
    setPersonalizarSecciones(prev => {
      const newSecs = [...prev];
      const newCost = {
        id: Date.now(), // ID temporal
        seccion_id: newSecs[addCostSeccionIndex].id,
        nombre: addCostForm.nombre.trim(),
        porcentaje: addCostForm.porcentaje ? parseFloat(addCostForm.porcentaje) : null,
        costo_base: parseFloat(addCostForm.costo_base) || 0,
      };
      if (!newSecs[addCostSeccionIndex].costos_produccion) {
        newSecs[addCostSeccionIndex].costos_produccion = [];
      }
      newSecs[addCostSeccionIndex].costos_produccion.push(newCost);
      return newSecs;
    });
    setShowAddCostModal(false);
    setAddCostSeccionIndex(null);
  };

  const handleRemoveCost = (seccionIndex: number, costIndex: number) => {
    setPersonalizarSecciones(prev => {
      const newSecs = [...prev];
      newSecs[seccionIndex].costos_produccion = newSecs[seccionIndex].costos_produccion.filter((_: any, i: number) => i !== costIndex);
      return newSecs;
    });
  };

  // Recalcular el preview en vivo dentro del modal cuando cambia personalizarSecciones
  useEffect(() => {
    if (!showPersonalizarModal || personalizarIndex === null || !personalizarSecciones || personalizarSecciones.length === 0) {
      return;
    }
    const item = items[personalizarIndex];
    const ganancia = item ? (Number(item.ganancia) || 40.0) : 40.0;
    
    setModalPreviewLoading(true);
    const timer = setTimeout(async () => {
      try {
        const res = await cotizacionService.recalculateCustomRecipe(ganancia, personalizarSecciones);
        setModalPreviewCalc(res);
      } catch (err) {
        console.error('Error recalculando preview en modal:', err);
      } finally {
        setModalPreviewLoading(false);
      }
    }, 200);

    return () => clearTimeout(timer);
  }, [personalizarSecciones, showPersonalizarModal, personalizarIndex]);

  const handleSavePersonalizacion = () => {
    if (personalizarIndex === null) return;
    const index = personalizarIndex;
    const recetaNueva = JSON.parse(JSON.stringify(personalizarSecciones));
    const calcFinal = modalPreviewCalc;

    // Aplicar directamente al renglón la receta y el resultado ya calculado
    setItems(prev => {
      const newItems = [...prev];
      newItems[index] = {
        ...newItems[index],
        receta_personalizada: recetaNueva,
        calcResult: calcFinal || newItems[index].calcResult,
        calcLoading: false,
      };
      return newItems;
    });

    setShowPersonalizarModal(false);
    setPersonalizarIndex(null);
    setModalPreviewCalc(null);
  };

  const addItem = () => {
    setItems((prev) => [
      ...prev,
      { producto_id: '', cantidad: 1, ancho: '1.0', largo: '1.0', ganancia: '40.0', observaciones: '', calcResult: null, calcLoading: false, receta_personalizada: null }
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
    setSelectedMonedaId(1);
    setTasaCambio(1);
    setItems([
      { producto_id: '', cantidad: 1, ancho: '1.0', largo: '1.0', ganancia: '40.0', observaciones: '', calcResult: null, calcLoading: false, receta_personalizada: null }
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
        receta_personalizada: item.receta_personalizada || null,
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

    const totalEstimado = selectedMonedaId !== 1
      ? Math.round(globalTotal / tasaCambio)
      : Math.round(globalTotal);

    const quoteData: QuoteCreate = {
      cliente_id: Number(selectedClientId),
      fecha: new Date().toISOString().split('T')[0],
      estado: editingQuote ? editingQuote.estado : 'BORRADOR',
      total_estimado: totalEstimado,
      moneda_id: selectedMonedaId,
      tasa_cambio: tasaCambio,
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
    setAdelantoPct('');
    setAdelantoMonedaId(quote.moneda_id ?? 1);
    setAdelantoTrm('');
    setAdelantoMetodo('');
    setConvertError('');
    setIsConvertOpen(true);
  };

  const handleOpenPrintPreview = async (quote: Quote) => {
    setSelectedQuoteForPrint(quote);
    setAssociatedVenta(null);
    
    // Load default values or saved configurations
    setPrintCompanyRif(localStorage.getItem('print_company_rif') || 'J-50146039-3');
    setPrintCompanyAddress(localStorage.getItem('print_company_address') || 'AV. INTERCOMUNAL CON CALLE 16 LOCAL Nro 15-205, BARRIO SIMÓN BOLÍVAR, UREÑA, TÁCHIRA');
    setPrintCompanyPhone(localStorage.getItem('print_company_phone') || '+58 412-1234567');
    setPrintDiscount('0');
    setPrintIva('0');
    
    setIsPrintModalOpen(true);

    // Buscar si existe un pedido y factura/abonos asociados a esta cotización
    try {
      const ventas = await ventaService.getAll();
      const responsePedidos = await pedidoService.getAll();
      const pedidoVinculado = responsePedidos.find((p: any) => p.cotizacion_id === quote.id || p.cotizacion?.id === quote.id);
      if (pedidoVinculado) {
        const ventaVinculada = ventas.find((v: any) => v.pedido_id === pedidoVinculado.id);
        if (ventaVinculada) {
          const detalleVenta = await ventaService.getById(ventaVinculada.id);
          setAssociatedVenta(detalleVenta);
        }
      }
    } catch (err) {
      console.error('Error al cargar ventas/abonos vinculados a la cotización:', err);
    }
  };

  const handleGeneratePdf = async () => {
    if (!selectedQuoteForPrint) return;
    setIsGeneratingPdf(true);

    // Save settings in localStorage
    localStorage.setItem('print_company_rif', printCompanyRif);
    localStorage.setItem('print_company_address', printCompanyAddress);
    localStorage.setItem('print_company_phone', printCompanyPhone);

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
    if (!selectedQuoteForConvert || isConverting) return;
    setIsConverting(true);
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
        let pId: number | undefined;
        let w = 1.0, l = 1.0;
        if (match) {
          const pName = match[1];
          w = Number(match[2]) || 1.0;
          l = Number(match[3]) || 1.0;
          const found = products.find(p => p.nombre === pName);
          if (found) pId = found.id;
        }
        if (!pId) {
          alert('No se pudo identificar el producto de esta cotización. Verifique que tenga detalles o que el producto exista en el catálogo.');
          return;
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

      const metodoLabel = METODOS_PAGO.find((m) => m.value === adelantoMetodo)?.label;
      await pedidoService.convertQuote(selectedQuoteForConvert.id, {
        detalles: convertDetails,
        fecha_entrega_estimada: deliveryDate || undefined,
        adelanto: abonoMontoPago > 0 ? abonoMontoPago : undefined,
        moneda_adelanto_id: adelantoMonedaId,
        tasa_cambio_adelanto: necesitaTrmAbono ? Number(adelantoTrm) : undefined,
        metodo_pago: abonoMontoPago > 0 ? adelantoMetodo : undefined,
      });
      setIsConvertOpen(false);
      const avisoAbono =
        abonoMontoPago > 0 && monedaAdelantoSel
          ? ` Abono inicial registrado: ${formatCurrency(Math.round(abonoMontoPago), monedaAdelantoSel.codigo)}${metodoLabel ? ` · ${metodoLabel}` : ''}.`
          : '';
      alert(`¡Cotización convertida a pedido con éxito!${avisoAbono} Se creó la factura automáticamente.`);
      fetchQuotes(search);
    } catch (err) {
      console.error(err);
      setConvertError(
        (err as any)?.response?.data?.detail || 'Error al convertir la cotización a pedido.'
      );
    } finally {
      setIsConverting(false);
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
              <div className="flex items-center gap-1.5 animate-fade-in">
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
                   <th className="px-6 py-4 border-b border-yeikar-secondary/20">Registrada por</th>
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
                   <td className="px-6 py-4">
                     <div className="font-semibold text-yeikar-secondary">
                       {quote.creador_nombre || 'Registro histórico'}
                     </div>
                     <div className="mt-0.5 text-[10px] font-mono text-yeikar-neutral/45">
                       {quote.created_at ? new Date(quote.created_at).toLocaleString('es-CO') : 'Hora no disponible'}
                     </div>
                   </td>
                    <td className="px-6 py-4 text-xs whitespace-pre-line text-yeikar-neutral/80">
                      {quote.observaciones}
                    </td>
                    <td className="px-6 py-4 font-mono font-bold text-yeikar-secondary">
                      {formatCurrency(Number(quote.total_estimado), quote.moneda?.codigo)}
                      {quote.moneda && quote.moneda_id !== 1 && (
                        <span className="block text-[10px] text-yeikar-neutral/40 font-normal">
                          ≈ {formatCurrency(Number(quote.total_en_moneda_base || 0), 'COP')}
                        </span>
                      )}
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

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs uppercase tracking-wider font-bold text-yeikar-neutral/60 font-headline mb-1">
                    Moneda de Cotización *
                  </label>
                  <select
                    value={selectedMonedaId}
                    onChange={(e) => {
                      const mId = Number(e.target.value);
                      setSelectedMonedaId(mId);
                      if (mId === 1) setTasaCambio(1);
                    }}
                    className="w-full p-2 border border-yeikar-secondary-light/20 rounded-lg focus:ring-2 focus:ring-yeikar-primary focus:outline-none bg-yeikar-tertiary/20 text-sm font-bold"
                  >
                    {currencies.map((m) => (
                      <option key={m.id} value={m.id}>
                        {m.codigo} — {m.nombre} ({m.simbolo})
                      </option>
                    ))}
                  </select>
                </div>

                {selectedMonedaId !== 1 && (
                  <div>
                    <label className="block text-xs uppercase tracking-wider font-bold text-yeikar-neutral/60 font-headline mb-1">
                      Tasa de Cambio (1 {currencyCode} = X COP) *
                    </label>
                    <input
                      type="number"
                      step="0.000001"
                      min="0.000001"
                      value={tasaCambio}
                      onChange={(e) => setTasaCambio(Number(e.target.value) || 1)}
                      required
                      className="w-full p-2 border border-yeikar-secondary-light/20 rounded-lg focus:ring-2 focus:ring-yeikar-primary focus:outline-none bg-yeikar-tertiary/20 text-sm font-mono"
                    />
                    <p className="mt-1 text-[11px] text-stone-500 font-mono">
                      {formatCurrency(Math.round(globalTotalCalc / tasaCambio), currencyCode)} → {(Math.round(globalTotalCalc)).toLocaleString('es-CO')} COP
                    </p>
                  </div>
                )}
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
                            {products.map((p) => {
                              const basePrecio = Number(p.precio_venta_base ?? p.precio_costo_base ?? 0);
                              const baseMostrar = isFinite(basePrecio) && basePrecio > 0
                                ? formatCurrency(basePrecio / (selectedMonedaId === 1 ? 1 : tasaCambio), currencyCode)
                                : null;
                              return (
                                <option key={p.id} value={p.id}>
                                  {p.nombre}{baseMostrar ? ` (${baseMostrar} base)` : ''}
                                </option>
                              );
                            })}
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
                        <div className="sm:col-span-2">
                          <input
                            type="text"
                            placeholder="Observación de este mueble (ej: Tela gris, patas madera)"
                            value={item.observaciones}
                            onChange={(e) => updateItemField(index, 'observaciones', e.target.value)}
                            className="w-full p-2 border border-yeikar-secondary-light/20 rounded-lg focus:ring-2 focus:ring-yeikar-primary focus:outline-none bg-white text-xs"
                          />
                        </div>
                        <div className="sm:col-span-1 flex items-center gap-1.5 justify-start">
                          <button
                            type="button"
                            onClick={() => handleOpenPersonalizarReceta(index)}
                            className="bg-amber-100/70 hover:bg-amber-100 text-amber-900 border border-amber-200/50 px-2 py-1.5 rounded-lg text-[10px] font-bold transition-all flex items-center gap-1 leading-none"
                            title="Personalizar materiales, insumos y políticas para esta cotización"
                          >
                            <svg className="w-3.5 h-3.5 text-amber-700" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 6V4m0 2a2 2 0 100 4m0-4a2 2 0 110 4m-6 8a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4m6 6v10m6-2a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4" />
                            </svg>
                            <span>Estructura / Secciones</span>
                          </button>
                          {item.receta_personalizada && (
                            <span className="bg-emerald-100 text-emerald-800 text-[9px] font-bold px-1.5 py-0.5 rounded-full font-sans uppercase shrink-0 leading-none">
                              Personalizado
                            </span>
                          )}
                        </div>
                        <div className="text-right font-mono text-xs font-bold text-yeikar-secondary sm:col-span-1">
                          {item.calcLoading ? (
                            <span className="text-yeikar-neutral/40">Calculando...</span>
                          ) : item.calcResult ? (
                            <span>Subt: {formatCurrency(item.calcResult.precio_venta * item.cantidad / (selectedMonedaId === 1 ? 1 : tasaCambio), currencyCode)}</span>
                          ) : (
                            <span>{formatCurrency(0, currencyCode)}</span>
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
            <div className="w-full md:w-80 bg-yeikar-neutral text-yeikar-tertiary p-6 flex flex-col justify-between border-t md:border-t-0 md:border-l border-yeikar-secondary/20 overflow-y-auto max-h-[85vh]">
              <div className="space-y-6">
                <div>
                  <h4 className="font-headline font-bold text-sm text-yeikar-primary tracking-wider uppercase mb-3">
                    Totales de Cotización
                  </h4>
                  <div className="space-y-2">
                    <div className="flex justify-between text-xs text-yeikar-tertiary/60">
                      <span>Costo Total Fábrica:</span>
                      <span className="font-mono font-bold">{formatCurrency(Math.round(globalCostoTotal / (selectedMonedaId === 1 ? 1 : tasaCambio)), currencyCode)}</span>
                    </div>
                    <div className="flex justify-between text-xs text-green-500">
                      <span>Ganancia Estimada:</span>
                      <span className="font-mono font-bold">+ {formatCurrency(Math.round((globalTotalCalc - globalCostoTotal) / (selectedMonedaId === 1 ? 1 : tasaCambio)), currencyCode)}</span>
                    </div>
                  </div>
                </div>

                {/* Selector de renglón si hay múltiples */}
                {items.length > 1 && (
                  <div className="border-t border-yeikar-secondary-light/10 pt-3">
                    <label className="block text-[10px] font-bold text-yeikar-tertiary/50 uppercase mb-1">
                      Ver Desglose de:
                    </label>
                    <select
                      value={desgloseIndex}
                      onChange={(e) => setDesgloseIndex(Number(e.target.value))}
                      className="w-full p-1.5 bg-yeikar-secondary/20 border border-yeikar-secondary-light/20 rounded-lg text-xs text-yeikar-tertiary focus:outline-none"
                    >
                      {items.map((item, idx) => {
                        const prod = products.find(p => p.id === Number(item.producto_id));
                        return (
                          <option key={idx} value={idx} className="bg-yeikar-neutral text-yeikar-tertiary">
                            Renglón {idx + 1}: {prod?.nombre || 'Mueble'} ({item.ancho}x{item.largo}m)
                          </option>
                        );
                      })}
                    </select>
                  </div>
                )}

                {/* Desglose Detallado de Secciones de ese Renglón */}
                <div className="border-t border-yeikar-secondary-light/10 pt-3 space-y-3">
                  <h5 className="text-[10px] font-bold text-yeikar-primary uppercase tracking-widest">
                    Desglose de Secciones (Renglón {desgloseIndex + 1})
                  </h5>
                  {items[desgloseIndex]?.calcResult?.desglose_por_seccion ? (
                    <div className="space-y-3">
                      {Object.entries(items[desgloseIndex].calcResult.desglose_por_seccion).map(([seccionNombre, datosSec]: [string, any]) => (
                        <div key={seccionNombre} className="bg-yeikar-secondary/10 rounded-lg p-2.5 space-y-1.5 border border-yeikar-secondary-light/5">
                          <div className="flex justify-between font-bold text-[11px] text-yeikar-primary border-b border-yeikar-secondary-light/15 pb-1">
                            <span className="uppercase truncate pr-1">{seccionNombre}</span>
                            <span className="font-mono text-yeikar-primary-light">{formatCurrency(Number(datosSec.total_seccion) / (selectedMonedaId === 1 ? 1 : tasaCambio), currencyCode)}</span>
                          </div>
                          <div className="space-y-0.5 text-[10px] text-yeikar-tertiary/75 font-mono">
                            {datosSec.costo_insumos > 0 && (
                              <div className="flex justify-between">
                                <span>Insumos</span>
                                <span>{formatCurrency(Number(datosSec.costo_insumos) / (selectedMonedaId === 1 ? 1 : tasaCambio), currencyCode)}</span>
                              </div>
                            )}
                            {datosSec.total_costos_produccion > 0 && (
                              <div className="flex justify-between text-amber-500 font-medium">
                                <span>C. Producción</span>
                                <span>+{formatCurrency(Number(datosSec.total_costos_produccion) / (selectedMonedaId === 1 ? 1 : tasaCambio), currencyCode)}</span>
                              </div>
                            )}
                            {datosSec.gasto_seccion > 0 && (
                              <div className="flex justify-between">
                                <span>Gastos ({datosSec.pct_gastos_seccion}%)</span>
                                <span>+{formatCurrency(Number(datosSec.gasto_seccion) / (selectedMonedaId === 1 ? 1 : tasaCambio), currencyCode)}</span>
                              </div>
                            )}
                          </div>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <p className="text-[10px] text-yeikar-tertiary/40 italic">
                      Selecciona un mueble válido para ver su desglose.
                    </p>
                  )}
                </div>
              </div>

              <div className="border-t border-yeikar-secondary/40 pt-4 mt-6">
                <span className="text-[10px] text-yeikar-tertiary/40 uppercase tracking-widest block mb-1">
                  PRECIO TOTAL SUGERIDO:
                </span>
                <div className="text-2xl font-black text-yeikar-primary font-mono">
                  {formatCurrency(Math.round(globalTotalCalc / (selectedMonedaId === 1 ? 1 : tasaCambio)), currencyCode)}
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Convert Quote to Order Modal */}
      {isConvertOpen && (
        <div className="fixed inset-0 bg-yeikar-neutral/50 backdrop-blur-sm flex items-center justify-center p-4 z-50 animate-fade-in">
          <div className="bg-white rounded-xl border border-yeikar-secondary-light/10 shadow-2xl w-full max-w-lg overflow-hidden">
            <div className="bg-yeikar-neutral p-4 text-yeikar-tertiary flex items-center justify-between">
              <h3 className="font-headline font-bold text-lg text-yeikar-primary">
                Convertir a Pedido de Fábrica
              </h3>
            </div>
            <div className="p-6 space-y-4">
              <p className="text-sm text-yeikar-neutral/80 font-body">
                Vas a generar un nuevo pedido para <strong>{selectedQuoteForConvert?.cliente?.nombre}</strong>.
                La factura se creará automáticamente en la moneda de la cotización.
              </p>

              {/* Info de la cotización (bloqueada) */}
              <div className="bg-yeikar-tertiary/30 border border-yeikar-secondary-light/10 rounded-lg p-3 text-xs text-yeikar-neutral/80 space-y-0.5">
                <div className="flex justify-between">
                  <span className="font-bold text-yeikar-neutral/50">Cotización</span>
                  <span className="font-mono">{quoteMoneda?.nombre} ({quoteMoneda?.codigo} {quoteMoneda?.simbolo})</span>
                </div>
                <div className="flex justify-between">
                  <span className="font-bold text-yeikar-neutral/50">Total</span>
                  <span className="font-mono font-bold text-yeikar-secondary">
                    {formatCurrency(Math.round(quoteTotal), quoteMoneda?.codigo ?? 'COP')}
                  </span>
                </div>
                {Number(selectedQuoteForConvert?.tasa_cambio) && quoteMoneda?.codigo !== 'COP' && (
                  <div className="flex justify-between">
                    <span className="font-bold text-yeikar-neutral/50">Tasa fijada al cotizar</span>
                    <span className="font-mono">
                      1 {quoteMoneda?.codigo} = {formatCurrency(Number(selectedQuoteForConvert?.tasa_cambio), 'COP')}
                    </span>
                  </div>
                )}
              </div>

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

              {/* Abono inicial (opcional) */}
              <div className="border-t border-yeikar-secondary-light/10 pt-4">
                <div className="flex items-center justify-between mb-1">
                  <label className="block text-xs uppercase tracking-wider font-bold text-yeikar-neutral/60 font-headline">
                    Abono inicial <span className="normal-case font-normal text-yeikar-neutral/40">(opcional)</span>
                  </label>
                  <span className="text-xs font-mono font-bold text-yeikar-primary">
                    {pctAbono > 0 ? `= ${formatCurrency(Math.round(abonoQuote), quoteMoneda?.codigo ?? 'COP')}` : 'Sin abono'}
                  </span>
                </div>

                <div className="flex flex-wrap gap-2">
                  <div className="relative flex-1 min-w-32">
                    <input
                      type="number"
                      min="0"
                      max="100"
                      placeholder="0"
                      value={adelantoPct}
                      onChange={(e) => setAdelantoPct(e.target.value)}
                      className="w-full p-2 pr-8 border border-yeikar-secondary-light/20 rounded-lg focus:ring-2 focus:ring-yeikar-primary focus:outline-none bg-yeikar-tertiary/20 font-mono text-sm"
                    />
                    <span className="absolute right-3 top-1/2 -translate-y-1/2 text-sm text-yeikar-neutral/40 font-bold">%</span>
                  </div>
                  <select
                    value={adelantoMonedaId}
                    onChange={(e) => setAdelantoMonedaId(Number(e.target.value))}
                    className="flex-1 min-w-32 p-2 border border-yeikar-secondary-light/20 rounded-lg focus:ring-2 focus:ring-yeikar-primary focus:outline-none bg-yeikar-tertiary/20 font-mono text-sm"
                  >
                    {currencies.map((m) => (
                      <option key={m.id} value={m.id}>
                        {m.nombre} ({m.codigo} {m.simbolo})
                      </option>
                    ))}
                  </select>
                  <select
                    value={adelantoMetodo}
                    onChange={(e) => {
                      const valor = e.target.value;
                      setAdelantoMetodo(valor);
                      const meta = METODOS_PAGO.find((m) => m.value === valor);
                      if (meta) {
                        const mon = currencies.find((c) => c.codigo === meta.moneda);
                        if (mon) setAdelantoMonedaId(mon.id);
                      }
                    }}
                    className="flex-1 min-w-32 p-2 border border-yeikar-secondary-light/20 rounded-lg focus:ring-2 focus:ring-yeikar-primary focus:outline-none bg-yeikar-tertiary/20 font-mono text-sm"
                  >
                    <option value="">Método de pago</option>
                    {METODOS_PAGO.map((m) => (
                      <option key={m.value} value={m.value}>
                        {m.label}
                      </option>
                    ))}
                  </select>
                </div>

                {pctAbono > 0 && tasaAbono && adelantoMonedaId !== quoteEnConversion?.moneda_id && (
                  <p className="text-xs text-yeikar-neutral/60 mt-2 font-mono">
                    ≈ {formatCurrency(Math.round(abonoMontoPago), monedaAdelantoSel?.codigo ?? '')}
                    {' '}· convertido con la tasa de la cotización
                  </p>
                )}

                {necesitaTrmAbono && (
                  <div className="mt-2">
                    <label className="block text-xs uppercase tracking-wider font-bold text-yeikar-neutral/60 font-headline mb-1">
                      TRM: 1 {monedaAdelantoSel?.codigo ?? '?'} = X {quoteMoneda?.codigo ?? '?'}
                    </label>
                    <input
                      type="number"
                      min="0"
                      step="0.0001"
                      value={adelantoTrm}
                      onChange={(e) => setAdelantoTrm(e.target.value)}
                      placeholder="Ej: 38,50"
                      className="w-full p-2 border border-yeikar-secondary-light/20 rounded-lg focus:ring-2 focus:ring-yeikar-primary focus:outline-none bg-yeikar-tertiary/20 font-mono text-sm"
                    />
                  </div>
                )}
              </div>

              {convertError && (
                <p className="text-xs text-red-600 bg-red-50 border border-red-200 rounded-lg px-3 py-2">
                  {convertError}
                </p>
              )}

              {/* Resumen antes de confirmar */}
              <div className="bg-yeikar-tertiary/30 border border-yeikar-secondary-light/10 rounded-lg px-3 py-2 text-xs font-mono text-yeikar-secondary">
                {pctAbono > 0
                  ? `Abono inicial: ${pctAbono}% = ${formatCurrency(Math.round(abonoMontoPago), monedaAdelantoSel?.codigo ?? quoteMoneda?.codigo ?? '')}${adelantoMonedaId !== quoteEnConversion?.moneda_id && tasaAbono ? ` (≈ ${formatCurrency(Math.round(abonoQuote), quoteMoneda?.codigo ?? '')})` : ''}${adelantoMetodo ? ` · ${METODOS_PAGO.find((m) => m.value === adelantoMetodo)?.label}` : ''} — se registra como primer pago.`
                  : 'Sin abono inicial — la factura quedará PENDIENTE.'}
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
                  disabled={isConverting}
                  className="px-5 py-2 bg-yeikar-primary text-yeikar-neutral font-bold rounded-lg shadow-md hover:bg-yeikar-primary-light disabled:opacity-50 disabled:cursor-not-allowed transition-all text-sm font-headline"
                >
                  {isConverting ? 'Convirtiendo...' : 'Confirmar Conversión'}
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
                    <h4 className="text-[10px] uppercase tracking-widest font-bold text-stone-400">Tasas & Ajustes</h4>
                    <div className="grid grid-cols-2 gap-2">
                      {[
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
                      <div className="grid grid-cols-3 gap-4 bg-stone-50/40 border border-stone-250 rounded-xl px-4 py-3 my-1 shadow-sm">
                        {[
                          { label: 'CLIENTE',    value: selectedQuoteForPrint.cliente?.nombre },
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
                              {['Modelo', 'Cant.', 'Descripción / Medidas', 'P. Unitario', `Total (${selectedQuoteForPrint.moneda?.codigo || 'COP'})`].map((h, i) => (
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
                                    <td className="px-3 py-2 text-right font-mono text-stone-850 font-medium">{formatCurrency(Number(det.precio), selectedQuoteForPrint.moneda?.codigo || 'COP')}</td>
                                    <td className="px-3 py-2 text-right font-mono font-extrabold text-stone-950">{formatCurrency(rowTotal, selectedQuoteForPrint.moneda?.codigo || 'COP')}</td>
                                  </tr>
                                );
                              })
                            ) : (
                              <tr><td colSpan={5} className="px-3 py-4 text-center text-stone-400 italic">Sin renglones.</td></tr>
                            )}
                          </tbody>
                        </table>
                      </div>

                      {/* ── Dynamic Payments History (Seguimiento de Abonos) ── */}
                      {associatedVenta && associatedVenta.pagos && associatedVenta.pagos.length > 0 && (
                        <div className="my-1">
                          <div className="text-[8.5px] font-serif font-bold uppercase tracking-wider text-stone-800 mb-1 flex items-center justify-between">
                            <span>Historial de Abonos / Pagos Realizados</span>
                            <span className="font-mono text-stone-600 font-normal">({associatedVenta.pagos.length} registros)</span>
                          </div>
                          <div className="border border-stone-300 rounded-lg overflow-hidden shadow-sm">
                            <table className="w-full border-collapse text-[8.5px]">
                              <thead>
                                <tr className="bg-stone-100 text-stone-800 font-bold uppercase text-[7.5px] tracking-wider border-b border-stone-300">
                                  <th className="px-2 py-1 text-left">Fecha</th>
                                  <th className="px-2 py-1 text-left">Método</th>
                                  <th className="px-2 py-1 text-left">Ref.</th>
                                  <th className="px-2 py-1 text-right">Monto Recibido</th>
                                  <th className="px-2 py-1 text-right">Equivalente en COP</th>
                                </tr>
                              </thead>
                              <tbody className="divide-y divide-stone-200 font-mono">
                                {associatedVenta.pagos.map((p, idx) => {
                                  const metodoLabel = METODOS_PAGO.find((m) => m.value === p.metodo_pago)?.label ?? p.metodo_pago;
                                  return (
                                    <tr key={p.id || idx} className={idx % 2 === 0 ? 'bg-white' : 'bg-stone-50/50'}>
                                      <td className="px-2 py-1 text-stone-700">{new Date(p.fecha).toLocaleDateString('es-ES')}</td>
                                      <td className="px-2 py-1 font-bold text-stone-900">{metodoLabel}</td>
                                      <td className="px-2 py-1 text-stone-600">{p.referencia || '—'}</td>
                                      <td className="px-2 py-1 text-right font-bold text-stone-800">
                                        {p.moneda?.simbolo ?? ''}{Number(p.monto).toLocaleString('es-ES')}
                                      </td>
                                      <td className="px-2 py-1 text-right font-bold text-emerald-800">
                                        {formatCurrency(Number(p.monto_en_moneda_base || p.monto), 'COP')}
                                        {p.tasa_cambio && p.tasa_cambio !== 1 && (
                                          <span className="block text-[7px] text-stone-500 font-normal">Tasa: {p.tasa_cambio}</span>
                                        )}
                                      </td>
                                    </tr>
                                  );
                                })}
                              </tbody>
                            </table>
                          </div>
                        </div>
                      )}

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
                                {value < 0 ? '-' : ''}{formatCurrency(Math.abs(value), selectedQuoteForPrint.moneda?.codigo || 'COP')}
                              </span>
                            </div>
                          ))}
                        </div>

                        {/* Right — grand total card */}
                        <div className="bg-amber-50/60 rounded-xl p-3 flex flex-col gap-1.5 border border-amber-300/80 shadow-sm">
                          <div className="flex justify-between items-baseline">
                            <span className="text-[8px] tracking-[0.15em] font-bold text-stone-700 uppercase">Total Cotización</span>
                            <span className="text-base font-black text-amber-900 font-mono">
                              {formatCurrency(grandTotal, selectedQuoteForPrint.moneda?.codigo || 'COP')}
                            </span>
                          </div>

                          {selectedQuoteForPrint.tasa_cambio && selectedQuoteForPrint.moneda_id !== 1 && (
                            <div className="flex justify-between items-baseline text-[8.5px] text-stone-600 font-mono font-medium border-t border-amber-200/60 pt-1">
                              <span>EQUIVALENTE EN COP:</span>
                              <span>{formatCurrency(grandTotal * Number(selectedQuoteForPrint.tasa_cambio), 'COP')}</span>
                            </div>
                          )}

                          {associatedVenta && Number(associatedVenta.total_pagado) > 0 && (
                            <div className="flex justify-between items-baseline text-[8.5px] text-emerald-800 font-mono font-extrabold border-t border-amber-200/60 pt-1">
                              <span>TOTAL ABONADO:</span>
                              <span>-{formatCurrency(Number(associatedVenta.total_pagado), 'COP')}</span>
                            </div>
                          )}

                          <div className="border-t border-amber-200/80 pt-1.5 space-y-0.5 text-[8.5px]">
                            {associatedVenta && (
                              <div className="flex justify-between text-amber-900 font-mono font-black text-[9.5px]">
                                <span>SALDO PENDIENTE:</span>
                                <span>{formatCurrency(Number(associatedVenta.saldo_pendiente), 'COP')}</span>
                              </div>
                            )}
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

      {/* ═══════════════════════════════════════════════════════════ */}
      {/* Modal de Personalización de Receta Ad-Hoc */}
      {/* ═══════════════════════════════════════════════════════════ */}
      {showPersonalizarModal && personalizarIndex !== null && (
        <div className="fixed inset-0 bg-yeikar-neutral/60 backdrop-blur-sm flex items-center justify-center p-4 z-50 overflow-y-auto">
          <div className="bg-white rounded-2xl shadow-2xl border border-yeikar-secondary-light/10 max-w-4xl w-full h-[90vh] flex flex-col overflow-hidden animate-fade-in">
            {/* Header del Modal */}
            <div className="bg-yeikar-neutral p-4 text-yeikar-tertiary flex flex-col md:flex-row md:items-center justify-between shrink-0 gap-3 border-b border-yeikar-secondary/20">
              <div>
                <h3 className="font-headline font-bold text-base text-yeikar-primary flex items-center gap-2">
                  <span>Personalizar Estructura y Secciones del Mueble</span>
                  {modalPreviewLoading && (
                    <span className="text-[10px] text-amber-400 font-mono animate-pulse">
                      (Calculando nuevo precio...)
                    </span>
                  )}
                </h3>
                <p className="text-xs text-yeikar-tertiary/50">
                  Esta configuración se aplicará únicamente a este renglón de la cotización actual.
                </p>
              </div>

              {/* Banner de Precio en Tiempo Real */}
              <div className="flex items-center gap-4 bg-yeikar-secondary/40 px-3.5 py-1.5 rounded-xl border border-yeikar-secondary-light/15 shrink-0">
                <div className="text-right">
                  <span className="text-[9px] uppercase tracking-wider text-yeikar-tertiary/60 font-bold block">
                    Costo Fábrica
                  </span>
                  <span className="font-mono text-xs font-bold text-yeikar-tertiary">
                    ${modalPreviewCalc ? Number(modalPreviewCalc.costo_total).toLocaleString('es-CO', { maximumFractionDigits: 0 }) : '...'}
                  </span>
                </div>
                <div className="h-6 w-px bg-yeikar-secondary-light/20" />
                <div className="text-right">
                  <span className="text-[9px] uppercase tracking-wider text-amber-400 font-bold block">
                    Nuevo Precio Sugerido
                  </span>
                  <span className="font-mono text-base font-black text-yeikar-primary">
                    ${modalPreviewCalc ? Number(modalPreviewCalc.precio_venta).toLocaleString('es-CO', { maximumFractionDigits: 0 }) : '...'}
                  </span>
                </div>
              </div>

              <button
                onClick={() => { setShowPersonalizarModal(false); setPersonalizarIndex(null); setModalPreviewCalc(null); }}
                className="text-yeikar-tertiary/60 hover:text-yeikar-primary text-sm font-bold font-headline self-start md:self-auto"
              >
                ✕ Cerrar
              </button>
            </div>

            {/* Cuerpo del Modal */}
            <div className="flex-1 overflow-y-auto p-6 space-y-6">
              {personalizarSecciones && personalizarSecciones.length > 0 ? (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                  {personalizarSecciones.map((sec, secIdx) => {
                    const secInfo = modalPreviewCalc?.desglose_por_seccion?.[sec.nombre];
                    return (
                      <div key={sec.id || secIdx} className="border border-yeikar-secondary-light/10 rounded-xl overflow-hidden bg-white shadow-sm flex flex-col">
                        {/* Cabecera Sección */}
                        <div className="bg-yeikar-secondary/5 border-b border-yeikar-secondary-light/10 px-4 py-2.5 flex items-center justify-between">
                          <span className="font-headline font-black text-xs text-yeikar-secondary uppercase tracking-wider">
                            Sección: {sec.nombre}
                          </span>
                          <div className="flex items-center gap-2">
                            {secInfo && (
                              <span className="text-[10px] font-bold font-mono bg-green-50 text-green-700 border border-green-200/80 px-2 py-0.5 rounded-full">
                                Subtotal: ${Number(secInfo.total_seccion).toLocaleString('es-CO', { maximumFractionDigits: 0 })}
                              </span>
                            )}
                            <span className="text-[10px] font-bold font-mono bg-yeikar-secondary/10 text-yeikar-secondary px-2 py-0.5 rounded-full">
                              {sec.elementos?.length || 0} insumos
                            </span>
                          </div>
                        </div>

                        {/* Política de la Sección */}
                        <div className="bg-amber-50/50 border-b border-amber-100/50 px-4 py-3 space-y-2">
                          <div className="flex items-center justify-between">
                            <span className="text-[10px] font-bold text-amber-800 uppercase tracking-wider">Política de Sección</span>
                          </div>
                          <div className="grid grid-cols-2 gap-3">
                            <div>
                              <label className="block text-[9px] font-bold text-yeikar-neutral/50 mb-1">% GASTOS SECCIÓN</label>
                              <input
                                type="number"
                                step="0.1"
                                min="0"
                                value={sec.politica?.pct_gastos_seccion ?? 10}
                                onChange={(e) => handleUpdateSeccionPolitica(secIdx, 'pct_gastos_seccion', e.target.value)}
                                className="w-full p-1.5 border border-amber-250 bg-white rounded-lg text-xs font-mono"
                              />
                            </div>
                            <div>
                              <label className="block text-[9px] font-bold text-yeikar-neutral/50 mb-1">% TRABAJADORES</label>
                              <input
                                type="number"
                                step="0.1"
                                min="0"
                                value={sec.politica?.pct_trabajadores ?? 8}
                                onChange={(e) => handleUpdateSeccionPolitica(secIdx, 'pct_trabajadores', e.target.value)}
                                className="w-full p-1.5 border border-amber-250 bg-white rounded-lg text-xs font-mono"
                              />
                            </div>
                          </div>
                        </div>

                        {/* Costos de Producción Avanzados (Pintura, etc.) */}
                        <div className="border-b border-stone-100 px-4 py-3 space-y-2">
                          <div className="flex items-center justify-between">
                            <span className="text-[10px] font-bold text-yeikar-neutral/40 uppercase tracking-wider">Costos de Producción</span>
                            <button
                              type="button"
                              onClick={() => handleOpenAddCost(secIdx)}
                              className="text-[10px] font-bold text-yeikar-primary hover:underline flex items-center gap-1"
                            >
                              + Agregar Costo
                            </button>
                          </div>

                          {sec.costos_produccion && sec.costos_produccion.length > 0 ? (
                            <div className="divide-y divide-amber-100">
                              {sec.costos_produccion.map((cp: any, cpIdx: number) => (
                                <div key={cp.id || cpIdx} className="flex items-center justify-between text-[11px] py-1.5 hover:bg-amber-50/30 px-1 -mx-1 rounded">
                                  <span className="font-semibold text-amber-900">{cp.nombre}</span>
                                  <div className="flex items-center gap-2">
                                    <span className="font-mono text-amber-800 bg-amber-100/60 px-1.5 py-0.5 rounded text-[10px]">
                                      ${Number(cp.costo_base).toLocaleString()} {cp.porcentaje ? `(+${cp.porcentaje}%)` : ''}
                                    </span>
                                    <button
                                      type="button"
                                      onClick={() => handleRemoveCost(secIdx, cpIdx)}
                                      className="text-red-500 hover:text-red-700"
                                    >
                                      ✕
                                    </button>
                                  </div>
                                </div>
                              ))}
                            </div>
                          ) : (
                            <p className="text-[10px] text-yeikar-neutral/40 italic">Sin costos de producción.</p>
                          )}
                        </div>

                        {/* Insumos */}
                        <div className="p-4 flex-1 space-y-3">
                          <div className="flex items-center justify-between">
                            <span className="text-[10px] font-bold text-yeikar-neutral/40 uppercase tracking-wider">Insumos Físicos</span>
                            <button
                              type="button"
                              onClick={() => handleOpenAddMaterial(secIdx)}
                              className="text-[10px] font-bold text-yeikar-primary hover:underline"
                            >
                              + Agregar Insumo
                            </button>
                          </div>

                          {sec.elementos && sec.elementos.length > 0 ? (
                            <div className="space-y-2.5 max-h-[220px] overflow-y-auto pr-1">
                              {sec.elementos.map((el: any, elIdx: number) => (
                                <div key={el.id || elIdx} className="bg-stone-50 p-2.5 rounded-lg border border-stone-100 relative space-y-1">
                                  <button
                                    type="button"
                                    onClick={() => handleRemoveInsumo(secIdx, elIdx)}
                                    className="absolute top-1 right-2 text-stone-400 hover:text-red-650 text-xs"
                                    title="Quitar"
                                  >
                                    ✕
                                  </button>
                                  <div className="font-bold text-xs text-yeikar-secondary truncate pr-4">
                                    {el.nombre_insumo_original}
                                  </div>
                                  <div className="grid grid-cols-2 gap-2 pt-1">
                                    <div>
                                      <label className="block text-[8px] font-semibold text-stone-400 mb-0.5">CANTIDAD ({el.unidad_medida})</label>
                                      <input
                                        type="number"
                                        step="0.001"
                                        min="0"
                                        value={el.cantidad}
                                        onChange={(e) => handleUpdateInsumoField(secIdx, elIdx, 'cantidad', e.target.value)}
                                        className="w-full p-1 border border-stone-200 bg-white rounded text-xs font-mono"
                                      />
                                    </div>
                                    <div>
                                      <label className="block text-[8px] font-semibold text-stone-400 mb-0.5">PRECIO UNITARIO ($)</label>
                                      <input
                                        type="number"
                                        min="0"
                                        value={el.precio_unitario ?? 0}
                                        onChange={(e) => handleUpdateInsumoField(secIdx, elIdx, 'precio_unitario', e.target.value)}
                                        className="w-full p-1 border border-stone-200 bg-white rounded text-xs font-mono"
                                      />
                                    </div>
                                  </div>
                                </div>
                              ))}
                            </div>
                          ) : (
                            <p className="text-[10px] text-yeikar-neutral/40 italic">No hay insumos agregados.</p>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>
              ) : (
                <div className="flex flex-col items-center justify-center py-12 text-yeikar-neutral/45">
                  <svg className="w-12 h-12 mb-3 animate-spin text-yeikar-primary" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M4 12a8 8 0 018-8v8H4z" />
                  </svg>
                  <span>Cargando receta estructurada...</span>
                </div>
              )}
            </div>

            {/* Footer del Modal */}
            <div className="bg-yeikar-neutral/5 p-4 border-t border-yeikar-secondary-light/10 flex items-center justify-between shrink-0">
              <div className="text-xs">
                {modalPreviewCalc ? (
                  <div className="flex items-center gap-2">
                    <span className="text-yeikar-secondary font-headline font-bold">
                      Precio Nuevo Sugerido:
                    </span>
                    <span className="text-yeikar-primary text-base font-black font-mono">
                      ${Number(modalPreviewCalc.precio_venta).toLocaleString('es-CO', { maximumFractionDigits: 0 })}
                    </span>
                  </div>
                ) : (
                  <span className="text-yeikar-tertiary/50 italic text-[11px]">Calculando precio en tiempo real...</span>
                )}
              </div>
              <div className="flex items-center gap-3">
                <button
                  type="button"
                  onClick={() => { setShowPersonalizarModal(false); setPersonalizarIndex(null); setModalPreviewCalc(null); }}
                  className="px-4 py-2 border border-yeikar-secondary-light/15 hover:bg-stone-50 rounded-xl text-xs font-bold font-headline"
                >
                  Cancelar
                </button>
                <button
                  type="button"
                  onClick={handleSavePersonalizacion}
                  disabled={modalPreviewLoading}
                  className="px-5 py-2 bg-yeikar-primary text-yeikar-neutral font-bold rounded-xl shadow-md hover:bg-yeikar-primary-light transition-all text-xs font-headline flex items-center gap-2 disabled:opacity-50"
                >
                  <span>Guardar Personalización</span>
                  {modalPreviewCalc && (
                    <span className="bg-yeikar-neutral/20 text-yeikar-neutral font-mono text-[10px] px-1.5 py-0.5 rounded">
                      ${Number(modalPreviewCalc.precio_venta).toLocaleString('es-CO', { maximumFractionDigits: 0 })}
                    </span>
                  )}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ═══════════════════════════════════════════════════════════ */}
      {/* Modal / Buscador para Agregar Insumo */}
      {/* ═══════════════════════════════════════════════════════════ */}
      {showAddMaterialDropdown && addMaterialSeccionIndex !== null && (
        <div className="fixed inset-0 bg-yeikar-secondary/60 backdrop-blur-sm flex items-center justify-center p-4 z-[60]">
          <div className="bg-white rounded-2xl shadow-2xl border border-stone-150 max-w-md w-full p-6 space-y-4">
            <div className="flex items-center justify-between">
              <h4 className="font-headline font-bold text-sm text-yeikar-secondary">Buscar Material en Inventario</h4>
              <button
                type="button"
                onClick={() => { setShowAddMaterialDropdown(false); setAddMaterialSeccionIndex(null); }}
                className="text-stone-400 hover:text-stone-600 font-bold"
              >
                ✕
              </button>
            </div>
            <input
              type="text"
              placeholder="Buscar madera, tela, tornillos..."
              value={addMaterialSearch}
              onChange={(e) => setAddMaterialSearch(e.target.value)}
              className="w-full p-2 border border-stone-250 rounded-lg focus:ring-2 focus:ring-yeikar-primary text-xs"
              autoFocus
            />
            <div className="max-h-[220px] overflow-y-auto divide-y divide-stone-100 pr-1 text-xs">
              {materiales
                .filter(m => m.nombre.toLowerCase().includes(addMaterialSearch.toLowerCase()))
                .slice(0, 15)
                .map((m) => (
                  <button
                    key={m.id}
                    type="button"
                    onClick={() => handleAddMaterialToSeccion(m)}
                    className="w-full text-left p-2.5 hover:bg-yeikar-tertiary/20 rounded transition-colors flex justify-between items-center"
                  >
                    <span className="font-semibold text-stone-900">{m.nombre}</span>
                    <span className="font-mono text-stone-500 bg-stone-100 px-2 py-0.5 rounded text-[10px]">
                      ${Number(m.costo_base).toLocaleString()}
                    </span>
                  </button>
                ))}
            </div>
          </div>
        </div>
      )}

      {/* ═══════════════════════════════════════════════════════════ */}
      {/* Modal Agregar Costo de Producción */}
      {/* ═══════════════════════════════════════════════════════════ */}
      {showAddCostModal && addCostSeccionIndex !== null && (
        <div className="fixed inset-0 bg-yeikar-secondary/60 backdrop-blur-sm flex items-center justify-center p-4 z-[60]">
          <div className="bg-white rounded-2xl shadow-2xl border border-stone-150 max-w-sm w-full p-6 space-y-4">
            <div>
              <h4 className="font-headline font-bold text-sm text-yeikar-secondary">Agregar Costo de Producción</h4>
            </div>
            <form onSubmit={handleAddCostToSeccion} className="space-y-3 text-xs">
              <div>
                <label className="block font-bold text-stone-500 mb-1">Nombre del Costo *</label>
                <input
                  type="text"
                  required
                  placeholder="Ej: PREPARADO, PINTURA"
                  value={addCostForm.nombre}
                  onChange={(e) => setAddCostForm({ ...addCostForm, nombre: e.target.value })}
                  className="w-full p-2 border border-stone-250 rounded-lg text-xs"
                />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block font-bold text-stone-500 mb-1">Costo Base ($) *</label>
                  <input
                    type="number"
                    min="0"
                    required
                    placeholder="0.00"
                    value={addCostForm.costo_base}
                    onChange={(e) => setAddCostForm({ ...addCostForm, costo_base: e.target.value })}
                    className="w-full p-2 border border-stone-250 rounded-lg text-xs font-mono"
                  />
                </div>
                <div>
                  <label className="block font-bold text-stone-500 mb-1">% Incremental (Opcional)</label>
                  <input
                    type="number"
                    min="0"
                    placeholder="5"
                    value={addCostForm.porcentaje}
                    onChange={(e) => setAddCostForm({ ...addCostForm, porcentaje: e.target.value })}
                    className="w-full p-2 border border-stone-250 rounded-lg text-xs font-mono"
                  />
                </div>
              </div>
              <div className="flex justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => { setShowAddCostModal(false); setAddCostSeccionIndex(null); }}
                  className="px-4 py-2 hover:bg-stone-50 rounded-lg"
                >
                  Cancelar
                </button>
                <button
                  type="submit"
                  className="px-4 py-2 bg-yeikar-primary text-yeikar-neutral font-bold rounded-lg"
                >
                  Agregar Costo
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

    </div>
  );
}
