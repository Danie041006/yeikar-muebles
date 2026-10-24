import { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  AlertTriangle,
  ArrowLeft,
  ClipboardList,
  DollarSign,
  History,
  Package,
  Plus,
  Search,
  ShoppingCart,
  Users,
} from 'lucide-react';
import api from '../services/api';
import {
  inventarioService,
  type CategoriaInventario,
  type InventarioItem,
  type MovimientoResponse,
} from '../services/inventarioService';
import { productosService, type Material } from '../services/productosService';
import { cuentasService, type ResumenCuenta } from '../services/cuentasService';
import {
  Badge,
  Button,
  Card,
  EmptyState,
  Field,
  Input,
  Modal,
  MontoInput,
  PageHeader,
  SearchSelect,
  Spinner,
  StatCard,
  Textarea,
  ResponsiveDataTable,
  type DataColumn,
} from '../components/ui';
import { useToast } from '../context/ToastContext';
import { extractErrorMessage, formatCurrency } from '../utils/format';
import { hoyVE } from '../utils/fechas';

// ─── Tipos locales ────────────────────────────────────────────────────────────

interface Unidad {
  id: number;
  nombre: string;
  abreviatura: string;
}

interface CuentaOpcion {
  key: string;
  cuentaId: number;
  nombre: string;
  monedaId: number;
  codigo: string;
}

interface FilaOficina extends Material {
  stock: number;
  valor: number;
  categoriaNombre: string | null;
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

const norm = (s: string) =>
  s.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toUpperCase();

function parsePagoKey(key: string): { cuentaId: number | null; monedaId: number | null } {
  const [cuentaId, monedaId] = (key || '').split(':');
  return {
    cuentaId: cuentaId ? Number(cuentaId) : null,
    monedaId: monedaId ? Number(monedaId) : null,
  };
}

const inputCls =
  'w-full bg-yeikar-tertiary/20 border border-yeikar-secondary-light/10 rounded-xl p-2.5 text-sm text-yeikar-neutral focus:outline-none focus:border-yeikar-primary font-mono';

// ─── Página ───────────────────────────────────────────────────────────────────

export default function InventarioOficina() {
  const toast = useToast();
  const navigate = useNavigate();

  const [loading, setLoading] = useState(true);
  const [materiales, setMateriales] = useState<Material[]>([]);
  const [inventario, setInventario] = useState<InventarioItem[]>([]);
  const [categorias, setCategorias] = useState<CategoriaInventario[]>([]);
  const [unidades, setUnidades] = useState<Unidad[]>([]);
  const [cuentas, setCuentas] = useState<CuentaOpcion[]>([]);
  const [search, setSearch] = useState('');

  // Modales
  const [articuloEditando, setArticuloEditando] = useState<Material | null>(null);
  const [showArticulo, setShowArticulo] = useState(false);
  const [articuloForm, setArticuloForm] = useState({
    nombre: '',
    unidad_medida_id: '',
    costo_base: '',
    stock_minimo: '3',
  });

  const [entradaMaterial, setEntradaMaterial] = useState<Material | null>(null);
  const [entradaForm, setEntradaForm] = useState({
    cantidad: '',
    costo_unitario: '',
    fecha: hoyVE(),
    proveedor_nombre: '',
    pago_key: '',
    tasa_pago: '',
    fiar: false,
    observaciones: '',
  });

  const [consumoMaterial, setConsumoMaterial] = useState<FilaOficina | null>(null);
  const [consumoForm, setConsumoForm] = useState({
    cantidad: '',
    consumido_por: '',
    fecha: hoyVE(),
    observaciones: '',
  });

  const [historialMaterial, setHistorialMaterial] = useState<Material | null>(null);
  const [historial, setHistorial] = useState<MovimientoResponse[]>([]);
  const [loadingHistorial, setLoadingHistorial] = useState(false);

  const [showConteo, setShowConteo] = useState(false);
  const [conteo, setConteo] = useState<Record<number, string>>({});
  const [guardando, setGuardando] = useState(false);

  // ── Carga ──────────────────────────────────────────────────────────────────
  const cargar = useCallback(async () => {
    setLoading(true);
    try {
      const [mats, inv, cats, unis, resumen] = await Promise.all([
        productosService.getMateriales(undefined, 1000),
        inventarioService.getInventario(),
        inventarioService.getCategorias('MATERIAL').catch(() => []),
        api.get<Unidad[]>('/catalogos/unidad-medida/').then((r) => r.data).catch(() => []),
        cuentasService.getResumen().catch(() => []),
      ]);
      setMateriales(mats);
      setInventario(inv);
      setCategorias(cats);
      setUnidades(unis);
      setCuentas(
        resumen.map((r: ResumenCuenta) => {
          const propia =
            r.saldo_por_moneda.find((l) => l.moneda_id === r.metodo_caja.moneda_id) ??
            r.saldo_por_moneda[0];
          return {
            key: `${r.metodo_caja.id}:${propia?.moneda_id ?? r.metodo_caja.moneda_id ?? 1}`,
            cuentaId: r.metodo_caja.id,
            nombre: r.metodo_caja.nombre,
            monedaId: propia?.moneda_id ?? r.metodo_caja.moneda_id ?? 1,
            codigo: propia?.codigo ?? r.metodo_caja.moneda_codigo ?? 'COP',
          };
        }),
      );
    } catch (error) {
      toast.error(extractErrorMessage(error, 'No se pudo cargar el inventario de oficina.'));
    } finally {
      setLoading(false);
    }
  }, [toast]);

  useEffect(() => {
    void cargar();
  }, [cargar]);

  // ── Datos derivados ────────────────────────────────────────────────────────
  const categoriaOficina = useMemo(
    () => categorias.find((c) => norm(c.nombre).includes('OFICINA')) ?? null,
    [categorias],
  );

  const stockPorMaterial = useMemo(() => {
    const map: Record<number, number> = {};
    for (const item of inventario) {
      map[item.material_id] = (map[item.material_id] ?? 0) + Number(item.cantidad || 0);
    }
    return map;
  }, [inventario]);

  const filas = useMemo<FilaOficina[]>(() => {
    return materiales
      .filter(
        (m) =>
          m.departamento === 'OFICINA' ||
          (categoriaOficina != null && m.categoria_inventario_id === categoriaOficina.id),
      )
      .map((m) => {
        const stock = stockPorMaterial[m.id] ?? 0;
        return {
          ...m,
          stock,
          valor: stock * Number(m.costo_base || 0),
          categoriaNombre:
            categorias.find((c) => c.id === m.categoria_inventario_id)?.nombre ?? null,
        };
      })
      .sort((a, b) => a.nombre.localeCompare(b.nombre));
  }, [materiales, categoriaOficina, categorias, stockPorMaterial]);

  const filtradas = useMemo(() => {
    const q = norm(search.trim());
    if (!q) return filas;
    return filas.filter(
      (f) =>
        norm(f.nombre).includes(q) ||
        (f.categoriaNombre && norm(f.categoriaNombre).includes(q)),
    );
  }, [filas, search]);

  const stockBajo = filas.filter((f) => f.stock <= Number(f.stock_minimo ?? 0)).length;
  const valorTotal = filas.reduce((acc, f) => acc + f.valor, 0);

  // ── Acciones ───────────────────────────────────────────────────────────────
  const abrirNuevo = () => {
    setArticuloEditando(null);
    setArticuloForm({
      nombre: '',
      unidad_medida_id: '',
      costo_base: '',
      stock_minimo: '3',
    });
    setShowArticulo(true);
  };

  const abrirEditar = (m: Material) => {
    setArticuloEditando(m);
    setArticuloForm({
      nombre: m.nombre,
      unidad_medida_id: String(m.unidad_medida_id),
      costo_base: m.costo_base != null ? String(m.costo_base) : '',
      stock_minimo: m.stock_minimo != null ? String(m.stock_minimo) : '3',
    });
    setShowArticulo(true);
  };

  const guardarArticulo = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!articuloForm.nombre.trim()) {
      toast.error('Escribe el nombre del artículo.');
      return;
    }
    if (!articuloForm.unidad_medida_id) {
      toast.error('Selecciona la unidad de medida.');
      return;
    }
    setGuardando(true);
    try {
      const payload = {
        nombre: articuloForm.nombre.trim().toUpperCase(),
        unidad_medida_id: Number(articuloForm.unidad_medida_id),
        costo_base: parseFloat(articuloForm.costo_base || '0') || 0,
        stock_minimo: parseFloat(articuloForm.stock_minimo || '0') || 0,
        categoria_inventario_id: categoriaOficina?.id ?? null,
        departamento: 'OFICINA',
      };
      let creado: Material;
      if (articuloEditando) {
        creado = await productosService.actualizarMaterial(articuloEditando.id, payload);
        toast.success('Artículo actualizado.');
      } else {
        creado = await productosService.crearMaterial(payload);
        toast.success('Artículo creado. Registra la entrada de la compra.');
      }
      setShowArticulo(false);
      await cargar();
      if (!articuloEditando) {
        abrirEntrada(creado);
      }
    } catch (error) {
      toast.error(extractErrorMessage(error, 'No se pudo guardar el artículo.'));
    } finally {
      setGuardando(false);
    }
  };

  const abrirEntrada = (m: Material) => {
    setEntradaMaterial(m);
    setEntradaForm({
      cantidad: '',
      costo_unitario: m.costo_base != null ? String(m.costo_base) : '',
      fecha: hoyVE(),
      proveedor_nombre: '',
      pago_key: '',
      tasa_pago: '',
      fiar: false,
      observaciones: '',
    });
  };

  const guardarEntrada = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!entradaMaterial) return;
    const cantidad = parseFloat(entradaForm.cantidad || '0');
    if (!(cantidad > 0)) {
      toast.error('La cantidad debe ser mayor que cero.');
      return;
    }
    const pago = parsePagoKey(entradaForm.pago_key);
    const tasa = parseFloat(entradaForm.tasa_pago || '0');
    if (pago.cuentaId && pago.monedaId !== 1 && !(tasa > 0)) {
      toast.error('Indica la tasa de cambio de la cuenta de pago a COP.');
      return;
    }
    if (!pago.cuentaId && entradaForm.fiar) {
      if (!entradaForm.proveedor_nombre.trim()) {
        toast.error('Para fiar indica el proveedor.');
        return;
      }
      if (!(parseFloat(entradaForm.costo_unitario || '0') > 0)) {
        toast.error('Para fiar indica el costo unitario.');
        return;
      }
    }
    setGuardando(true);
    try {
      await inventarioService.crearMovimiento({
        material_id: entradaMaterial.id,
        tipo: 'ENTRADA',
        cantidad,
        costo_unitario: parseFloat(entradaForm.costo_unitario || '0') || undefined,
        fecha: entradaForm.fecha || hoyVE(),
        proveedor_nombre: entradaForm.proveedor_nombre.trim() || undefined,
        pagado_desde_metodo_caja_id: pago.cuentaId || undefined,
        moneda_pago_id: pago.cuentaId ? pago.monedaId ?? undefined : undefined,
        tasa_pago: pago.cuentaId && pago.monedaId !== 1 ? tasa : undefined,
        fiar: !pago.cuentaId && entradaForm.fiar ? true : undefined,
        departamento: 'OFICINA',
        referencia_tipo: 'ENTRADA_OFICINA',
        observaciones: entradaForm.observaciones.trim() || undefined,
      });
      toast.success('Entrada registrada en el inventario de oficina.');
      setEntradaMaterial(null);
      await cargar();
    } catch (error) {
      toast.error(extractErrorMessage(error, 'No se pudo registrar la entrada.'));
    } finally {
      setGuardando(false);
    }
  };

  const abrirConsumo = (f: FilaOficina) => {
    setConsumoMaterial(f);
    setConsumoForm({
      cantidad: '',
      consumido_por: '',
      fecha: hoyVE(),
      observaciones: '',
    });
  };

  const guardarConsumo = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!consumoMaterial) return;
    const cantidad = parseFloat(consumoForm.cantidad || '0');
    if (!(cantidad > 0)) {
      toast.error('La cantidad debe ser mayor que cero.');
      return;
    }
    if (cantidad > consumoMaterial.stock) {
      toast.error(
        `Solo hay ${consumoMaterial.stock.toLocaleString('es-CO')} ${consumoMaterial.unidad_medida?.abreviatura || ''} disponibles.`,
      );
      return;
    }
    if (!consumoForm.consumido_por.trim()) {
      toast.error('Indica quién recibe o consume el artículo.');
      return;
    }
    setGuardando(true);
    try {
      await inventarioService.crearMovimiento({
        material_id: consumoMaterial.id,
        tipo: 'SALIDA',
        cantidad,
        fecha: consumoForm.fecha || hoyVE(),
        consumido_por: consumoForm.consumido_por.trim(),
        departamento: 'OFICINA',
        referencia_tipo: 'CONSUMO_OFICINA',
        observaciones: consumoForm.observaciones.trim() || 'Consumo de oficina',
      });
      toast.success('Consumo registrado. El stock quedó actualizado.');
      setConsumoMaterial(null);
      await cargar();
    } catch (error) {
      toast.error(extractErrorMessage(error, 'No se pudo registrar el consumo.'));
    } finally {
      setGuardando(false);
    }
  };

  const abrirHistorial = async (m: Material) => {
    setHistorialMaterial(m);
    setHistorial([]);
    setLoadingHistorial(true);
    try {
      const data = await inventarioService.getKardex(m.id);
      setHistorial(data);
    } catch (error) {
      toast.error(extractErrorMessage(error, 'No se pudo cargar el historial.'));
    } finally {
      setLoadingHistorial(false);
    }
  };

  const abrirConteo = () => {
    const inicial: Record<number, string> = {};
    for (const f of filas) inicial[f.id] = String(f.stock);
    setConteo(inicial);
    setShowConteo(true);
  };

  const guardarConteo = async () => {
    const cambios = filas
      .map((f) => ({
        fila: f,
        contado:
          conteo[f.id] === '' || conteo[f.id] == null ? f.stock : Number(conteo[f.id]),
      }))
      .filter((x) => Number.isFinite(x.contado) && x.contado !== x.fila.stock);

    if (cambios.length === 0) {
      toast.info('No hay diferencias: el stock coincide con el conteo.');
      return;
    }

    const negativos = cambios.filter((c) => c.contado < 0);
    if (negativos.length > 0) {
      toast.error('El stock contado no puede ser negativo.');
      return;
    }

    setGuardando(true);
    try {
      for (const { fila, contado } of cambios) {
        await inventarioService.crearMovimiento({
          material_id: fila.id,
          tipo: 'AJUSTE',
          cantidad: contado,
          fecha: hoyVE(),
          departamento: 'OFICINA',
          referencia_tipo: 'CONTEO_OFICINA',
          observaciones: `Conteo físico de oficina (stock anterior: ${fila.stock.toLocaleString('es-CO')})`,
        });
      }
      toast.success(
        `Conteo guardado: ${cambios.length} artículo(s) ajustado(s).`,
      );
      setShowConteo(false);
      await cargar();
    } catch (error) {
      toast.error(extractErrorMessage(error, 'No se pudo guardar el conteo.'));
    } finally {
      setGuardando(false);
    }
  };

  // ── Tabla ──────────────────────────────────────────────────────────────────
  const columns: DataColumn<FilaOficina>[] = [
    {
      key: 'nombre',
      header: 'Artículo',
      mobilePrimary: true,
      render: (f) => (
        <div className="min-w-0">
          <span className="block truncate font-semibold text-yeikar-secondary">{f.nombre}</span>
          <span className="block text-[10px] text-yeikar-neutral/45">
            {[f.categoriaNombre, f.unidad_medida?.nombre].filter(Boolean).join(' · ') || 'Oficina'}
          </span>
        </div>
      ),
    },
    {
      key: 'stock',
      header: 'Stock',
      align: 'right',
      mobileLabel: 'Stock',
      render: (f) => {
        const bajo = f.stock <= Number(f.stock_minimo ?? 0);
        return (
          <span
            className={`font-mono text-sm font-black ${bajo ? 'text-red-600' : 'text-yeikar-secondary'}`}
          >
            {f.stock.toLocaleString('es-CO', { maximumFractionDigits: 2 })}
            <span className="ml-1 text-[10px] font-normal text-yeikar-neutral/40">
              {f.unidad_medida?.abreviatura || ''}
            </span>
          </span>
        );
      },
    },
    {
      key: 'minimo',
      header: 'Mínimo',
      align: 'right',
      mobileLabel: 'Mínimo',
      render: (f) => (
        <span className="font-mono text-xs text-yeikar-neutral/60">
          {Number(f.stock_minimo ?? 0).toLocaleString('es-CO')}
        </span>
      ),
    },
    {
      key: 'costo',
      header: 'Costo unit.',
      align: 'right',
      mobileLabel: 'Costo',
      render: (f) => (
        <span className="font-mono text-xs text-yeikar-neutral/70">
          {formatCurrency(Number(f.costo_base || 0), 'COP')}
        </span>
      ),
    },
    {
      key: 'valor',
      header: 'Valor',
      align: 'right',
      mobileLabel: 'Valor',
      render: (f) => (
        <span className="font-mono text-xs font-bold text-yeikar-secondary">
          {formatCurrency(f.valor, 'COP')}
        </span>
      ),
    },
  ];

  const accionesFila = (f: FilaOficina) => (
    <div
      className="flex flex-wrap items-center justify-end gap-1.5"
      onClick={(e) => e.stopPropagation()}
    >
      <Button size="sm" variant="outline" onClick={() => abrirEntrada(f)}>
        Entrada
      </Button>
      <Button size="sm" onClick={() => abrirConsumo(f)} disabled={f.stock <= 0}>
        Consumir
      </Button>
      <Button size="sm" variant="ghost" onClick={() => void abrirHistorial(f)}>
        Historial
      </Button>
    </div>
  );

  // ── Render ─────────────────────────────────────────────────────────────────
  return (
    <div className="space-y-7">
      <PageHeader
        eyebrow="Almacén"
        title="Inventario de Oficina"
        subtitle="Papelería, cafetería y aseo de oficina. Entra por compra y sale por consumo o conteo físico."
        icon={<ClipboardList className="w-7 h-7" />}
        actions={
          <>
            <Button variant="ghost" onClick={() => navigate('/inventario')} icon={<ArrowLeft className="w-4 h-4" />}>
              Inventario general
            </Button>
            <Button variant="outline" onClick={abrirConteo} icon={<ClipboardList className="w-4 h-4" />}>
              Conteo físico
            </Button>
            <Button onClick={abrirNuevo} icon={<Plus className="w-4 h-4" />}>
              Nuevo artículo
            </Button>
          </>
        }
      />

      {/* KPIs */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <StatCard
          label="Artículos de oficina"
          value={filas.length.toLocaleString('es-CO')}
          icon={<Package className="w-5 h-5" />}
          accent="from-yeikar-primary to-amber-300"
        />
        <StatCard
          label="Stock bajo"
          value={stockBajo.toLocaleString('es-CO')}
          icon={<AlertTriangle className="w-5 h-5" />}
          accent="from-red-500 to-rose-300"
          hint={stockBajo > 0 ? 'Revisa los artículos marcados en rojo.' : 'Todo por encima del mínimo.'}
        />
        <StatCard
          label="Valor del inventario"
          value={formatCurrency(valorTotal, 'COP')}
          icon={<DollarSign className="w-5 h-5" />}
          accent="from-emerald-500 to-emerald-300"
        />
      </div>

      {/* Tabla */}
      <Card className="overflow-hidden">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 p-5 border-b border-yeikar-secondary-light/10">
          <div>
            <h2 className="font-headline font-black text-yeikar-secondary">Existencias</h2>
            <p className="text-xs text-yeikar-neutral/50 mt-0.5">
              La salida rápida registra quién recibió el artículo. Para diferencias de inventario usa
              “Conteo físico”.
            </p>
          </div>
          <div className="relative w-full sm:w-72">
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Buscar artículo..."
              className="w-full bg-yeikar-tertiary/30 border border-yeikar-secondary-light/10 rounded-xl pl-9 pr-3 py-2 text-sm focus:outline-none focus:border-yeikar-primary"
            />
            <Search className="absolute left-3 top-2.5 w-4 h-4 text-yeikar-neutral/40" />
          </div>
        </div>

        {loading ? (
          <div className="flex flex-col items-center justify-center py-20 gap-3">
            <Spinner />
            <p className="text-xs font-mono text-yeikar-neutral/50">Cargando inventario de oficina...</p>
          </div>
        ) : (
          <ResponsiveDataTable
            columns={columns}
            rows={filtradas}
            rowKey={(f) => f.id}
            tableActions={accionesFila}
            cardActions={accionesFila}
            onRowClick={(f) => void abrirHistorial(f)}
            cardBadge={(f) => (
              <Badge tone={f.stock <= Number(f.stock_minimo ?? 0) ? 'red' : 'green'}>
                {f.stock.toLocaleString('es-CO', { maximumFractionDigits: 2 })}{' '}
                {f.unidad_medida?.abreviatura || ''}
              </Badge>
            )}
            empty={
              <EmptyState
                title={search ? `Sin resultados para “${search}”` : 'Aún no hay artículos de oficina'}
                description={
                  search
                    ? 'Prueba con otro nombre o limpia la búsqueda.'
                    : 'Crea hojas, lapiceros, café, vasos, aseo... y registra su primera compra.'
                }
                action={
                  !search ? (
                    <Button onClick={abrirNuevo} icon={<Plus className="w-4 h-4" />}>
                      Crear primer artículo
                    </Button>
                  ) : undefined
                }
              />
            }
          />
        )}
      </Card>

      <p className="text-[11px] text-yeikar-neutral/40 flex items-center gap-1.5">
        <Users className="w-3.5 h-3.5" />
        Sugerencia: usa “Consumir” cada vez que alguien saque algo y “Conteo físico” una vez al mes
        para cuadrar diferencias sin registrar cada salida.
      </p>

      {/* ─── Modal artículo (crear / editar) ───────────────────────────────── */}
      <Modal
        open={showArticulo}
        onClose={() => setShowArticulo(false)}
        title={articuloEditando ? 'Editar artículo de oficina' : 'Nuevo artículo de oficina'}
        subtitle="Se guarda como material del departamento OFICINA."
        footer={
          <>
            <Button variant="outline" onClick={() => setShowArticulo(false)}>
              Cancelar
            </Button>
            <Button form="form-articulo-oficina" type="submit" loading={guardando}>
              {articuloEditando ? 'Guardar cambios' : 'Crear y registrar entrada'}
            </Button>
          </>
        }
      >
        <form id="form-articulo-oficina" onSubmit={guardarArticulo} className="space-y-4">
          <Field label="Nombre del artículo" required>
            <Input
              autoFocus
              value={articuloForm.nombre}
              onChange={(e) => setArticuloForm((p) => ({ ...p, nombre: e.target.value }))}
              placeholder="Ej. RESMA PAPEL CARTA, LAPICERO NEGRO..."
            />
          </Field>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Unidad de medida" required>
              <SearchSelect
                value={articuloForm.unidad_medida_id}
                onChange={(v) => setArticuloForm((p) => ({ ...p, unidad_medida_id: String(v) }))}
                options={unidades.map((u) => ({
                  value: u.id,
                  label: `${u.nombre} (${u.abreviatura})`,
                }))}
                placeholder="Selecciona..."
              />
            </Field>
            <Field label="Stock mínimo" hint="Para la alerta de reposición.">
              <Input
                type="number"
                min="0"
                step="0.5"
                value={articuloForm.stock_minimo}
                onChange={(e) => setArticuloForm((p) => ({ ...p, stock_minimo: e.target.value }))}
              />
            </Field>
          </div>
          <Field label="Costo unitario de referencia (COP)">
            <MontoInput
              min="0"
              value={articuloForm.costo_base}
              onChange={(v) => setArticuloForm((p) => ({ ...p, costo_base: v }))}
              placeholder="0"
            />
          </Field>
          <p className="text-[11px] text-yeikar-neutral/50 bg-yeikar-tertiary/30 border border-yeikar-secondary-light/10 rounded-xl px-3 py-2">
            Al crearlo se abrirá el formulario de entrada para que registres la compra real (fecha,
            proveedor y cuenta de pago).
          </p>
        </form>
      </Modal>

      {/* ─── Modal entrada ────────────────────────────────────────────────── */}
      <Modal
        open={entradaMaterial != null}
        onClose={() => setEntradaMaterial(null)}
        title="Entrada de oficina"
        subtitle={entradaMaterial ? entradaMaterial.nombre : undefined}
        footer={
          <>
            <Button variant="outline" onClick={() => setEntradaMaterial(null)}>
              Cancelar
            </Button>
            <Button form="form-entrada-oficina" type="submit" loading={guardando} icon={<ShoppingCart className="w-4 h-4" />}>
              Registrar entrada
            </Button>
          </>
        }
      >
        <form id="form-entrada-oficina" onSubmit={guardarEntrada} className="space-y-4">
          <div className="grid grid-cols-2 gap-3">
            <Field label="Cantidad" required>
              <Input
                autoFocus
                type="number"
                min="0.01"
                step="any"
                value={entradaForm.cantidad}
                onChange={(e) => setEntradaForm((p) => ({ ...p, cantidad: e.target.value }))}
                placeholder="0"
              />
            </Field>
            <Field label="Costo unitario (COP)">
              <MontoInput
                min="0"
                value={entradaForm.costo_unitario}
                onChange={(v) => setEntradaForm((p) => ({ ...p, costo_unitario: v }))}
                placeholder="0"
              />
            </Field>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Fecha">
              <Input
                type="date"
                max={hoyVE()}
                value={entradaForm.fecha}
                onChange={(e) => setEntradaForm((p) => ({ ...p, fecha: e.target.value }))}
              />
            </Field>
            <Field label="Proveedor" hint="Dónde se compró (opcional).">
              <Input
                value={entradaForm.proveedor_nombre}
                onChange={(e) =>
                  setEntradaForm((p) => ({ ...p, proveedor_nombre: e.target.value }))
                }
                placeholder="Ej. Papelería Central"
              />
            </Field>
          </div>
          <Field
            label="¿De qué cuenta salió el dinero?"
            hint="Opcional. Si la eliges se registra el gasto y la salida de caja."
          >
            <SearchSelect
              value={entradaForm.pago_key}
              onChange={(v) => setEntradaForm((p) => ({ ...p, pago_key: String(v), fiar: String(v) ? false : p.fiar }))}
              options={[
                { value: '', label: 'Sin cuenta (solo inventario)' },
                ...cuentas.map((c) => ({
                  value: c.key,
                  label: `${c.nombre} · ${c.codigo}`,
                })),
              ]}
              placeholder="Sin cuenta..."
            />
          </Field>
          {!parsePagoKey(entradaForm.pago_key).cuentaId && (
            <label className="flex items-start gap-2.5 rounded-xl border border-yeikar-secondary-light/10 bg-yeikar-tertiary/20 px-3 py-2.5 cursor-pointer">
              <input
                type="checkbox"
                checked={entradaForm.fiar}
                onChange={(e) => setEntradaForm((p) => ({ ...p, fiar: e.target.checked }))}
                className="mt-0.5 accent-yeikar-primary"
              />
              <span className="text-xs text-yeikar-neutral/70">
                Quedó fiado al proveedor
                <span className="block text-[11px] text-yeikar-neutral/45">
                  Crea una cuenta por pagar con el proveedor (no descuenta caja).
                </span>
              </span>
            </label>
          )}
          {parsePagoKey(entradaForm.pago_key).cuentaId &&
            parsePagoKey(entradaForm.pago_key).monedaId !== 1 && (
              <Field label="Tasa de cambio a COP" required>
                <Input
                  type="number"
                  min="0"
                  step="any"
                  value={entradaForm.tasa_pago}
                  onChange={(e) => setEntradaForm((p) => ({ ...p, tasa_pago: e.target.value }))}
                  placeholder="1 [moneda cuenta] = ? COP"
                />
              </Field>
            )}
          <Field label="Observaciones">
            <Textarea
              rows={2}
              value={entradaForm.observaciones}
              onChange={(e) =>
                setEntradaForm((p) => ({ ...p, observaciones: e.target.value }))
              }
              placeholder="Factura, remisión, detalle..."
            />
          </Field>
          {parseFloat(entradaForm.cantidad || '0') > 0 &&
            parseFloat(entradaForm.costo_unitario || '0') > 0 && (
              <p className="text-xs font-mono text-yeikar-secondary bg-yeikar-tertiary/30 border border-yeikar-secondary-light/10 rounded-xl px-3 py-2">
                Total: {formatCurrency(
                  (parseFloat(entradaForm.cantidad) || 0) *
                    (parseFloat(entradaForm.costo_unitario) || 0),
                  'COP',
                )}
              </p>
            )}
        </form>
      </Modal>

      {/* ─── Modal consumo ────────────────────────────────────────────────── */}
      <Modal
        open={consumoMaterial != null}
        onClose={() => setConsumoMaterial(null)}
        title="Registrar consumo"
        subtitle={
          consumoMaterial
            ? `${consumoMaterial.nombre} · disponible: ${consumoMaterial.stock.toLocaleString('es-CO', { maximumFractionDigits: 2 })} ${consumoMaterial.unidad_medida?.abreviatura || ''}`
            : undefined
        }
        footer={
          <>
            <Button variant="outline" onClick={() => setConsumoMaterial(null)}>
              Cancelar
            </Button>
            <Button form="form-consumo-oficina" type="submit" loading={guardando}>
              Descontar del inventario
            </Button>
          </>
        }
      >
        <form id="form-consumo-oficina" onSubmit={guardarConsumo} className="space-y-4">
          <div className="grid grid-cols-2 gap-3">
            <Field label="Cantidad" required>
              <Input
                autoFocus
                type="number"
                min="0.01"
                step="any"
                value={consumoForm.cantidad}
                onChange={(e) => setConsumoForm((p) => ({ ...p, cantidad: e.target.value }))}
                placeholder="0"
              />
            </Field>
            <Field label="Fecha">
              <Input
                type="date"
                max={hoyVE()}
                value={consumoForm.fecha}
                onChange={(e) => setConsumoForm((p) => ({ ...p, fecha: e.target.value }))}
              />
            </Field>
          </div>
          <Field label="¿Quién lo recibe o consume?" required>
            <Input
              value={consumoForm.consumido_por}
              onChange={(e) => setConsumoForm((p) => ({ ...p, consumido_por: e.target.value }))}
              placeholder="Ej. Recepción, María, Contabilidad..."
            />
          </Field>
          <Field label="Observaciones">
            <Textarea
              rows={2}
              value={consumoForm.observaciones}
              onChange={(e) =>
                setConsumoForm((p) => ({ ...p, observaciones: e.target.value }))
              }
              placeholder="Para qué se usó..."
            />
          </Field>
        </form>
      </Modal>

      {/* ─── Modal historial ──────────────────────────────────────────────── */}
      <Modal
        open={historialMaterial != null}
        onClose={() => setHistorialMaterial(null)}
        title="Historial del artículo"
        subtitle={historialMaterial?.nombre}
        size="xl"
        footer={
          <>
            <Button variant="outline" onClick={() => setHistorialMaterial(null)}>
              Cerrar
            </Button>
            {historialMaterial && (
              <Button
                onClick={() => {
                  const m = historialMaterial;
                  setHistorialMaterial(null);
                  abrirEditar(m);
                }}
              >
                Editar artículo
              </Button>
            )}
          </>
        }
      >
        {loadingHistorial ? (
          <div className="flex items-center justify-center py-10">
            <Spinner />
          </div>
        ) : historial.length === 0 ? (
          <p className="text-sm text-yeikar-neutral/50 italic py-6 text-center">
            Sin movimientos todavía.
          </p>
        ) : (
          <div className="space-y-2 max-h-[55vh] overflow-y-auto pr-1">
            {historial.map((m) => {
              const entrada = m.tipo === 'ENTRADA' || m.tipo === 'DEVOLUCION';
              return (
                <div
                  key={m.id}
                  className="border border-yeikar-secondary-light/10 rounded-xl p-3 space-y-1"
                >
                  <div className="flex items-center justify-between gap-2">
                    <Badge tone={entrada ? 'green' : m.tipo === 'AJUSTE' ? 'neutral' : 'red'}>
                      {m.tipo}
                    </Badge>
                    <span className="font-mono text-[10px] text-yeikar-neutral/40">
                      {m.fecha ? new Date(m.fecha).toLocaleString('es-CO') : '—'}
                    </span>
                  </div>
                  <div className="flex items-center justify-between text-sm">
                    <span className="text-yeikar-neutral/60">
                      {entrada ? '+' : m.tipo === 'AJUSTE' ? '=' : '−'}
                      {Number(m.cantidad).toLocaleString('es-CO', { maximumFractionDigits: 2 })}
                    </span>
                    {m.costo_unitario != null && (
                      <span className="font-mono text-xs text-yeikar-neutral/50">
                        {formatCurrency(Number(m.costo_unitario), 'COP')} c/u
                      </span>
                    )}
                  </div>
                  {(m.consumido_por || m.recibido_por || m.proveedor_nombre || m.cliente_nombre) && (
                    <p className="text-[11px] text-yeikar-neutral/55">
                      {m.consumido_por && (
                        <>
                          Consumió: <b className="text-yeikar-secondary">{m.consumido_por}</b>
                        </>
                      )}
                      {m.recibido_por && (
                        <>
                          {m.consumido_por ? ' · ' : ''}
                          Recibió: <b className="text-yeikar-secondary">{m.recibido_por}</b>
                        </>
                      )}
                      {m.proveedor_nombre && (
                        <>
                          {(m.consumido_por || m.recibido_por) ? ' · ' : ''}
                          Proveedor: <b className="text-yeikar-secondary">{m.proveedor_nombre}</b>
                        </>
                      )}
                      {m.cliente_nombre && (
                        <>
                          {(m.consumido_por || m.recibido_por || m.proveedor_nombre) ? ' · ' : ''}
                          Cliente: <b className="text-yeikar-secondary">{m.cliente_nombre}</b>
                        </>
                      )}
                    </p>
                  )}
                  {m.observaciones && (
                    <p className="text-[11px] text-yeikar-neutral/45 italic">{m.observaciones}</p>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </Modal>

      {/* ─── Modal conteo físico ──────────────────────────────────────────── */}
      <Modal
        open={showConteo}
        onClose={() => setShowConteo(false)}
        title="Conteo físico de oficina"
        subtitle="Escribe lo que realmente hay. Solo se ajustan los artículos con diferencias."
        size="2xl"
        footer={
          <>
            <Button variant="outline" onClick={() => setShowConteo(false)}>
              Cancelar
            </Button>
            <Button onClick={() => void guardarConteo()} loading={guardando} icon={<History className="w-4 h-4" />}>
              Guardar conteo
            </Button>
          </>
        }
      >
        <div className="space-y-2 max-h-[60vh] overflow-y-auto pr-1">
          <div className="grid grid-cols-[1fr_100px_100px] gap-2 text-[10px] font-mono font-bold uppercase tracking-wider text-yeikar-neutral/45 px-1">
            <span>Artículo</span>
            <span className="text-right">Stock sistema</span>
            <span className="text-right">Contado</span>
          </div>
          {filas.map((f) => {
            const contado = conteo[f.id];
            const diff =
              contado === '' || contado == null ? 0 : Number(contado) - f.stock;            return (
              <div
                key={f.id}
                className="grid grid-cols-[1fr_100px_100px] gap-2 items-center border border-yeikar-secondary-light/10 rounded-xl px-3 py-2"
              >
                <div className="min-w-0">
                  <p className="truncate text-sm font-semibold text-yeikar-secondary">{f.nombre}</p>
                  {diff !== 0 && Number.isFinite(diff) && (
                    <p className={`text-[10px] font-mono ${diff < 0 ? 'text-red-600' : 'text-emerald-700'}`}>
                      diferencia {diff > 0 ? '+' : ''}
                      {diff.toLocaleString('es-CO', { maximumFractionDigits: 2 })}
                    </p>
                  )}
                </div>
                <span className="text-right font-mono text-xs text-yeikar-neutral/60">
                  {f.stock.toLocaleString('es-CO', { maximumFractionDigits: 2 })}
                </span>
                <Input
                  type="number"
                  min="0"
                  step="any"
                  value={contado ?? ''}
                  onChange={(e) => setConteo((p) => ({ ...p, [f.id]: e.target.value }))}
                  className="text-right font-mono"
                />
              </div>
            );
          })}
          {filas.length === 0 && (
            <p className="text-sm text-yeikar-neutral/50 italic text-center py-6">
              No hay artículos de oficina para contar.
            </p>
          )}
        </div>
      </Modal>
    </div>
  );
}
