import { useState, useEffect, useCallback } from 'react';
import {
  getPreciosProduccion, crearPrecioProduccion, actualizarPrecioProduccion,
  eliminarPrecioProduccion, getAreas,
  Area, PrecioProduccion,
} from '../services/costosProduccionService';
import {
  Button, Card, Badge, Spinner, EmptyState, StatCard, PageHeader,
  Field, Input, Tabs, Modal, ConfirmDialog, SearchSelect,
  ResponsiveDataTable, type DataColumn,
} from '../components/ui';

export default function CostosProduccion() {
  const [areas, setAreas] = useState<Area[]>([]);
  const [items, setItems] = useState<PrecioProduccion[]>([]);
  const [areaActiva, setAreaActiva] = useState('');
  const [buscar, setBuscar] = useState('');
  const [loading, setLoading] = useState(false);
  const [showModal, setShowModal] = useState(false);
  const [showEditModal, setShowEditModal] = useState(false);
  const [editandoItem, setEditandoItem] = useState<PrecioProduccion | null>(null);
  const [confirmDeleteId, setConfirmDeleteId] = useState<number | null>(null);
  const [editandoId, setEditandoId] = useState<number | null>(null);
  const [montoEditando, setMontoEditando] = useState('');
  const [editandoDescId, setEditandoDescId] = useState<number | null>(null);
  const [descEditando, setDescEditando] = useState('');

  const [form, setForm] = useState({
    descripcion: '',
    precio: 0,
  });

  const cargarAreas = useCallback(async () => {
    const data = await getAreas();
    setAreas(data);
    if (data.length > 0 && !areaActiva) {
      setAreaActiva(String(data[0].id));
    }
  }, [areaActiva]);

  const cargarItems = useCallback(async () => {
    if (!areaActiva) return;
    setLoading(true);
    try {
      const data = await getPreciosProduccion({
        area_id: Number(areaActiva),
        buscar: buscar || undefined,
      });
      setItems(data);
    } finally {
      setLoading(false);
    }
  }, [areaActiva, buscar]);

  useEffect(() => {
    cargarAreas();
  }, [cargarAreas]);

  useEffect(() => {
    cargarItems();
  }, [cargarItems]);

  const areaNombre = areas.find((a) => String(a.id) === areaActiva)?.nombre || '';
  const totalArea = items.reduce((s, it) => s + Number(it.precio), 0);

  const handleCrear = async () => {
    if (!areaActiva || !form.descripcion.trim() || !form.precio || form.precio <= 0) return;
    await crearPrecioProduccion({
      area_id: Number(areaActiva),
      descripcion: form.descripcion.trim(),
      precio: form.precio,
    });
    setShowModal(false);
    setForm({ descripcion: '', precio: 0 });
    cargarItems();
  };

  const guardarMonto = async (item: PrecioProduccion, valor: string) => {
    const monto = Number(valor);
    if (isNaN(monto) || monto < 0) {
      setEditandoId(null);
      return;
    }
    await actualizarPrecioProduccion(item.id, { precio: monto });
    setEditandoId(null);
    cargarItems();
  };

  const guardarDescripcion = async (item: PrecioProduccion, valor: string) => {
    const desc = valor.trim();
    if (!desc) {
      setEditandoDescId(null);
      return;
    }
    await actualizarPrecioProduccion(item.id, { descripcion: desc });
    setEditandoDescId(null);
    cargarItems();
  };

  const abrirEdicion = (item: PrecioProduccion) => {
    setEditandoItem(item);
    setForm({ descripcion: item.descripcion, precio: Number(item.precio) });
    setShowEditModal(true);
  };

  const guardarEdicion = async () => {
    if (!editandoItem || !form.descripcion.trim() || !form.precio || form.precio <= 0) return;
    await actualizarPrecioProduccion(editandoItem.id, {
      descripcion: form.descripcion.trim(),
      precio: form.precio,
    });
    setShowEditModal(false);
    setEditandoItem(null);
    cargarItems();
  };

  const toggleActivo = async (item: PrecioProduccion) => {
    await actualizarPrecioProduccion(item.id, { activo: !item.activo });
    cargarItems();
  };

  const handleEliminar = async (id: number) => {
    await eliminarPrecioProduccion(id);
    setConfirmDeleteId(null);
    cargarItems();
  };

  const areasTabs = areas.map((a) => ({ key: String(a.id), label: a.nombre }));

  const renderActions = (it: PrecioProduccion) => (
    <div className="inline-flex items-center gap-1">
      <Button
        variant="ghost"
        size="sm"
        className="text-yeikar-secondary hover:text-yeikar-primary hover:bg-yeikar-tertiary/60"
        onClick={() => abrirEdicion(it)}
        title="Editar ítem"
      >
        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
        </svg>
        Editar
      </Button>
      <Button
        variant="ghost"
        size="sm"
        className="text-red-600 hover:text-red-700 hover:bg-red-50"
        onClick={() => setConfirmDeleteId(it.id)}
      >
        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
        </svg>
        Eliminar
      </Button>
    </div>
  );

  const columns: DataColumn<PrecioProduccion>[] = [
    {
      key: 'indice',
      header: '#',
      render: (it) => <span className="font-mono text-xs text-yeikar-neutral/40">{items.indexOf(it) + 1}</span>,
    },
    {
      key: 'descripcion',
      header: 'Descripción',
      render: (it) => (
        <>
          {editandoDescId === it.id ? (
            <Input
              type="text"
              autoFocus
              value={descEditando}
              onChange={(e) => setDescEditando(e.target.value)}
              onBlur={() => guardarDescripcion(it, descEditando)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') guardarDescripcion(it, descEditando);
                if (e.key === 'Escape') setEditandoDescId(null);
              }}
            />
          ) : (
            <button
              className="text-left hover:text-yeikar-primary hover:bg-yeikar-tertiary/60 px-2 py-1 rounded-lg transition-colors"
              onClick={() => {
                setEditandoDescId(it.id);
                setDescEditando(it.descripcion);
              }}
              title="Clic para editar descripción"
            >
              {it.descripcion}
            </button>
          )}
        </>
      ),
      mobilePrimary: true,
    },
    {
      key: 'precio',
      header: 'Precio (COP)',
      render: (it) => (
        <>
          {editandoId === it.id ? (
            <Input
              type="number"
              min="0"
              step="1000"
              autoFocus
              className="w-36 ml-auto text-right font-mono"
              value={montoEditando}
              onChange={(e) => setMontoEditando(e.target.value)}
              onBlur={() => guardarMonto(it, montoEditando)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') guardarMonto(it, montoEditando);
                if (e.key === 'Escape') setEditandoId(null);
              }}
            />
          ) : (
            <button
              className="font-mono font-bold text-yeikar-dark hover:text-yeikar-primary hover:bg-yeikar-tertiary/60 px-2 py-1 rounded-lg transition-colors"
              onClick={() => {
                setEditandoId(it.id);
                setMontoEditando(String(it.precio));
              }}
              title="Clic para editar precio"
            >
              $ {Number(it.precio).toLocaleString('es-CO')}
            </button>
          )}
        </>
      ),
      mobileLabel: 'Precio (COP)',
      align: 'right',
    },
    {
      key: 'estado',
      header: 'Estado',
      render: (it) => (
        <button onClick={() => toggleActivo(it)} title={it.activo ? 'Desactivar' : 'Activar'}>
          <Badge tone={it.activo ? 'green' : 'neutral'}>{it.activo ? 'Activo' : 'Inactivo'}</Badge>
        </button>
      ),
      align: 'center',
      mobileHidden: true,
    },
  ];

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Finanzas"
        title="Costos de Producción"
        subtitle="Listado de precios por área para la nómina (mano de obra / por producción)"
        actions={
          <Button onClick={() => setShowModal(true)}>
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M12 4v16m8-8H4" />
            </svg>
            Nuevo Ítem
          </Button>
        }
      />

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-5">
        <StatCard
          label={`Ítems de ${areaNombre}`}
          value={`${items.length}`}
          accent="from-yeikar-primary to-yeikar-primary-light"
        />
        <StatCard
          label="Total del área (COP)"
          value={`$${totalArea.toLocaleString('es-CO')}`}
          accent="from-yeikar-secondary to-yeikar-secondary-light"
        />
        <StatCard
          label="Áreas configuradas"
          value={`${areas.length}`}
          accent="from-green-600 to-green-500"
          iconBg="bg-green-50"
          iconText="text-green-700"
        />
      </div>

      <Card>
        <div className="flex flex-wrap items-center justify-between gap-3 p-4 border-b border-yeikar-secondary-light/10">
          <Tabs
            tabs={areasTabs}
            active={areaActiva}
            onChange={setAreaActiva}
            variant="pills"
          />
          <div className="w-56">
            <Input
              type="search"
              placeholder="Buscar ítem..."
              value={buscar}
              onChange={(e) => setBuscar(e.target.value)}
            />
          </div>
        </div>

        {loading ? (
          <div className="p-8">
            <Spinner size="sm" />
          </div>
        ) : (
          <ResponsiveDataTable
            columns={columns}
            rows={items}
            rowKey={(it) => it.id}
            cardBadge={(it) => (
              <button onClick={() => toggleActivo(it)} title={it.activo ? 'Desactivar' : 'Activar'}>
                <Badge tone={it.activo ? 'green' : 'neutral'}>{it.activo ? 'Activo' : 'Inactivo'}</Badge>
              </button>
            )}
            tableActions={renderActions}
            cardActions={renderActions}
            empty={
              <div className="p-8">
                <EmptyState
                  compact
                  icon={
                    <svg className="w-7 h-7" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 17V7m0 10a2 2 0 01-2 2H5a2 2 0 01-2-2V7a2 2 0 012-2h2a2 2 0 012 2m0 10a2 2 0 002 2h2a2 2 0 002-2M9 7a2 2 0 012-2h2a2 2 0 012 2m0 10V7m0 10a2 2 0 002 2h2a2 2 0 002-2V7a2 2 0 00-2-2h-2a2 2 0 00-2 2" />
                    </svg>
                  }
                  title="Sin ítems"
                  description="No hay costos con los filtros actuales en esta área."
                  action={<Button size="sm" onClick={() => setShowModal(true)}>Agregar el primero</Button>}
                />
              </div>
            }
          />
        )}
        {items.length > 0 && (
          <div className="flex items-center justify-end gap-2 px-4 py-3 border-t border-yeikar-secondary-light/10">
            <span className="text-sm text-yeikar-neutral/50">
              Total {areaNombre}: <b className="font-mono text-yeikar-secondary">$ {totalArea.toLocaleString('es-CO')}</b>
            </span>
          </div>
        )}
      </Card>

      <Modal
        open={showModal}
        onClose={() => setShowModal(false)}
        title="Nuevo precio de producción"
        subtitle={`Área: ${areaNombre}`}
        footer={
          <>
            <Button variant="outline" onClick={() => setShowModal(false)}>Cancelar</Button>
            <Button onClick={handleCrear}>Guardar Ítem</Button>
          </>
        }
      >
        <div className="space-y-4">
          <Field label="Área" required>
            <SearchSelect
              value={areaActiva}
              onChange={(v) => setAreaActiva(String(v))}
              options={areas.map((a) => ({ value: a.id, label: a.nombre }))}
              placeholder="Seleccione área..."
            />
          </Field>
          <Field label="Descripción" required>
            <Input
              type="text"
              value={form.descripcion}
              onChange={(e) => setForm({ ...form, descripcion: e.target.value })}
              placeholder="Ej: CAMA SOLA DE 1.60 Y 2X2"
            />
          </Field>
          <Field label="Precio (COP)" required>
            <Input
              type="number"
              min="0"
              step="1000"
              value={form.precio}
              onChange={(e) => setForm({ ...form, precio: Number(e.target.value) })}
            />
          </Field>
        </div>
      </Modal>

      <Modal
        open={showEditModal}
        onClose={() => { setShowEditModal(false); setEditandoItem(null); }}
        title="Editar precio de producción"
        subtitle={editandoItem ? `Área actual: ${editandoItem.area?.nombre || areaNombre}` : ''}
        footer={
          <>
            <Button variant="outline" onClick={() => { setShowEditModal(false); setEditandoItem(null); }}>Cancelar</Button>
            <Button onClick={guardarEdicion}>Guardar Cambios</Button>
          </>
        }
      >
        <div className="space-y-4">
          <Field label="Área" required>
            <SearchSelect
              value={String(editandoItem?.area_id || '')}
              onChange={(v) => {
                if (editandoItem) setEditandoItem({ ...editandoItem, area_id: Number(v) });
              }}
              options={areas.map((a) => ({ value: a.id, label: a.nombre }))}
              placeholder="Seleccione área..."
            />
          </Field>
          <Field label="Descripción" required>
            <Input
              type="text"
              value={form.descripcion}
              onChange={(e) => setForm({ ...form, descripcion: e.target.value })}
              placeholder="Ej: CAMA SOLA DE 1.60 Y 2X2"
            />
          </Field>
          <Field label="Precio (COP)" required>
            <Input
              type="number"
              min="0"
              step="1000"
              value={form.precio}
              onChange={(e) => setForm({ ...form, precio: Number(e.target.value) })}
            />
          </Field>
        </div>
      </Modal>

      <ConfirmDialog
        open={confirmDeleteId !== null}
        title="Eliminar precio"
        message="¿Eliminar este precio de producción? Esta acción no se puede deshacer."
        confirmLabel="Eliminar"
        onConfirm={() => confirmDeleteId !== null && handleEliminar(confirmDeleteId)}
        onCancel={() => setConfirmDeleteId(null)}
      />
    </div>
  );
}
