import { useState, useEffect, useCallback } from 'react';
import {
  getEmpleados, crearEmpleado, actualizarEmpleado, eliminarEmpleado, getCargos,
  Empleado, Cargo,
} from '../services/empleadosService';
import {
  Button, Card, Badge, Spinner, EmptyState, PageHeader,
  Field, Input, Modal, ConfirmDialog, SearchSelect,
  ResponsiveDataTable, type DataColumn,
} from '../components/ui';

const fmtCOP = (n: number) => `$ ${(Number(n) || 0).toLocaleString('es-CO')}`;

export default function Empleados() {
  const [empleados, setEmpleados] = useState<Empleado[]>([]);
  const [cargos, setCargos] = useState<Cargo[]>([]);
  const [buscar, setBuscar] = useState('');
  const [loading, setLoading] = useState(false);
  const [showModal, setShowModal] = useState(false);
  const [editando, setEditando] = useState<Empleado | null>(null);
  const [confirmDeleteId, setConfirmDeleteId] = useState<number | null>(null);

  const [form, setForm] = useState({
    nombre: '',
    cargo_id: 0,
    telefono: '',
    en_nomina: false,
    tipo_pago: 'DESTAJO',
    sueldo_semanal: '',
    porcentaje_aguinaldo: '',
  });

  const cargar = useCallback(async () => {
    setLoading(true);
    try {
      const [emps] = await Promise.all([getEmpleados({ buscar: buscar || undefined })]);
      setEmpleados(emps);
    } finally {
      setLoading(false);
    }
  }, [buscar]);

  const cargarCatalogos = useCallback(async () => {
    const cs = await getCargos();
    setCargos(cs);
  }, []);

  useEffect(() => {
    cargarCatalogos();
  }, [cargarCatalogos]);

  useEffect(() => {
    cargar();
  }, [cargar]);

  const abrirNuevo = () => {
    setEditando(null);
    setForm({
      nombre: '',
      cargo_id: cargos[0]?.id || 0,
      telefono: '',
      en_nomina: false,
      tipo_pago: 'DESTAJO',
      sueldo_semanal: '',
      porcentaje_aguinaldo: '',
    });
    setShowModal(true);
  };

  const abrirEdicion = (e: Empleado) => {
    setEditando(e);
    setForm({
      nombre: e.nombre,
      cargo_id: e.cargo_id,
      telefono: e.telefono || '',
      en_nomina: e.en_nomina,
      tipo_pago: e.tipo_pago || 'DESTAJO',
      sueldo_semanal: e.sueldo_semanal ? String(e.sueldo_semanal) : '',
      porcentaje_aguinaldo: e.porcentaje_aguinaldo ? String(e.porcentaje_aguinaldo) : '',
    });
    setShowModal(true);
  };

  const guardar = async () => {
    if (!form.nombre.trim() || !form.cargo_id) return;
    const data = {
      nombre: form.nombre.trim(),
      cargo_id: form.cargo_id,
      telefono: form.telefono || undefined,
      en_nomina: form.en_nomina,
      tipo_pago: form.en_nomina ? form.tipo_pago : undefined,
      sueldo_semanal: form.en_nomina && form.tipo_pago === 'FIJO' && form.sueldo_semanal ? Number(form.sueldo_semanal) : undefined,
      porcentaje_aguinaldo: form.porcentaje_aguinaldo ? Number(form.porcentaje_aguinaldo) : undefined,
    };
    if (editando) {
      await actualizarEmpleado(editando.id, data);
    } else {
      await crearEmpleado(data);
    }
    setShowModal(false);
    cargar();
  };

  const toggleNomina = async (e: Empleado) => {
    await actualizarEmpleado(e.id, { en_nomina: !e.en_nomina });
    cargar();
  };

  const eliminar = async (id: number) => {
    await eliminarEmpleado(id);
    setConfirmDeleteId(null);
    cargar();
  };

  const enNomina = empleados.filter((e) => e.en_nomina).length;
  const totalAguinaldo = empleados.reduce((s, e) => s + Number(e.saldo_aguinaldo || 0), 0);

  const renderAcciones = (e: Empleado) => (
    <div className="inline-flex items-center gap-1">
      <Button variant="ghost" size="sm" onClick={() => abrirEdicion(e)}>Editar</Button>
      <Button variant="ghost" size="sm" className="text-red-600 hover:text-red-700 hover:bg-red-50" onClick={() => setConfirmDeleteId(e.id)}>Eliminar</Button>
    </div>
  );

  const columns: DataColumn<Empleado>[] = [
    {
      key: 'nombre',
      header: 'Nombre',
      render: (e) => <span className="font-medium text-yeikar-secondary">{e.nombre}</span>,
      mobilePrimary: true,
    },
    {
      key: 'cargo',
      header: 'Cargo',
      render: (e) => <span className="text-yeikar-neutral/60">{e.cargo?.nombre || '-'}</span>,
      mobileSecondary: true,
    },
    {
      key: 'nomina',
      header: 'Nómina',
      render: (e) => (
        <button onClick={() => toggleNomina(e)} title="Activar/desactivar en nómina">
          <Badge tone={e.en_nomina ? 'green' : 'neutral'}>{e.en_nomina ? 'Sí' : 'No'}</Badge>
        </button>
      ),
      mobileHidden: true,
    },
    {
      key: 'tipo',
      header: 'Tipo',
      render: (e) =>
        e.en_nomina ? (
          <Badge tone={e.tipo_pago === 'FIJO' ? 'gold' : 'purple'}>{e.tipo_pago || '-'}</Badge>
        ) : (
          <span className="text-yeikar-neutral/30">—</span>
        ),
      mobileLabel: 'Tipo',
      align: 'center',
    },
    {
      key: 'sueldo',
      header: 'Sueldo semanal',
      render: (e) =>
        e.en_nomina && e.tipo_pago === 'FIJO' ? (
          <span className="font-mono">{fmtCOP(Number(e.sueldo_semanal || 0))}</span>
        ) : (
          <span className="text-yeikar-neutral/30">—</span>
        ),
      mobileLabel: 'Sueldo semanal',
      align: 'right',
    },
    {
      key: 'aguinaldo',
      header: 'Aguinaldo',
      render: (e) =>
        Number(e.saldo_aguinaldo || 0) > 0 ? (
          <span className="font-mono text-amber-700">{fmtCOP(Number(e.saldo_aguinaldo))}</span>
        ) : (
          <span className="text-yeikar-neutral/30">—</span>
        ),
      mobileLabel: 'Aguinaldo',
      align: 'right',
    },
  ];

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Administración"
        title="Empleados"
        subtitle="Registro del personal y configuración de nómina"
        actions={
          <Button onClick={abrirNuevo}>
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M12 4v16m8-8H4" />
            </svg>
            Nuevo Empleado
          </Button>
        }
      />

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-5">
        <Card className="p-4">
          <p className="text-xs font-bold uppercase tracking-wider text-yeikar-neutral/40">Empleados registrados</p>
          <p className="mt-1 font-mono text-2xl font-black text-yeikar-dark">{empleados.length}</p>
        </Card>
        <Card className="p-4">
          <p className="text-xs font-bold uppercase tracking-wider text-yeikar-neutral/40">En nómina</p>
          <p className="mt-1 font-mono text-2xl font-black text-yeikar-secondary">{enNomina}</p>
        </Card>
        <Card className="p-4">
          <p className="text-xs font-bold uppercase tracking-wider text-yeikar-neutral/40">Aguinaldo acumulado</p>
          <p className="mt-1 font-mono text-2xl font-black text-amber-700">{fmtCOP(totalAguinaldo)}</p>
        </Card>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="w-64">
          <Input
            type="search"
            placeholder="Buscar empleado..."
            value={buscar}
            onChange={(e) => setBuscar(e.target.value)}
          />
        </div>
      </div>

      <Card>
        <ResponsiveDataTable
          columns={columns}
          rows={empleados}
          rowKey={(e) => e.id}
          empty={
            loading ? (
              <div className="p-8"><Spinner size="sm" /></div>
            ) : (
              <div className="p-8">
                <EmptyState compact title="Sin empleados" description="Registra el personal del taller."
                  action={<Button size="sm" onClick={abrirNuevo}>Nuevo Empleado</Button>} />
              </div>
            )
          }
          cardBadge={(e) => (
            <button onClick={() => toggleNomina(e)} title="Activar/desactivar en nómina">
              <Badge tone={e.en_nomina ? 'green' : 'neutral'}>{e.en_nomina ? 'Sí' : 'No'}</Badge>
            </button>
          )}
          tableActions={renderAcciones}
          cardActions={renderAcciones}
        />
      </Card>

      <Modal
        open={showModal}
        onClose={() => setShowModal(false)}
        title={editando ? 'Editar empleado' : 'Nuevo empleado'}
        subtitle="Configura también su participación en la nómina"
        footer={
          <>
            <Button variant="outline" onClick={() => setShowModal(false)}>Cancelar</Button>
            <Button onClick={guardar}>{editando ? 'Guardar Cambios' : 'Guardar'}</Button>
          </>
        }
      >
        <div className="space-y-4">
          <Field label="Nombre" required>
            <Input type="text" value={form.nombre} onChange={(e) => setForm({ ...form, nombre: e.target.value })} placeholder="Ej: WILMER/EBANISTA" />
          </Field>
          <Field label="Cargo" required>
            <SearchSelect
              value={form.cargo_id}
              onChange={(v) => setForm({ ...form, cargo_id: Number(v) })}
              options={cargos.map((c) => ({ value: c.id, label: c.nombre }))}
              placeholder="Seleccione cargo..."
            />
          </Field>
          <Field label="Teléfono">
            <Input type="text" value={form.telefono} onChange={(e) => setForm({ ...form, telefono: e.target.value })} />
          </Field>
          <div className="flex items-center gap-2 pt-1">
            <input
              type="checkbox"
              id="en_nomina"
              checked={form.en_nomina}
              onChange={(e) => setForm({ ...form, en_nomina: e.target.checked })}
              className="h-4 w-4 accent-yeikar-primary"
            />
            <label htmlFor="en_nomina" className="text-sm font-medium text-yeikar-secondary">Incluido en la nómina semanal</label>
          </div>
          {form.en_nomina && (
            <>
              <Field label="Tipo de pago" required>
                <SearchSelect
                  value={form.tipo_pago}
                  onChange={(v) => setForm({ ...form, tipo_pago: String(v) })}
                  options={[
                    { value: 'DESTAJO', label: 'Destajo (cobra su producción)' },
                    { value: 'FIJO', label: 'Fijo (sueldo semanal)' },
                  ]}
                  placeholder="Seleccione tipo..."
                />
              </Field>
              {form.tipo_pago === 'FIJO' && (
                <Field label="Sueldo semanal (COP)" required>
                  <Input type="number" min="0" step="1000" value={form.sueldo_semanal} onChange={(e) => setForm({ ...form, sueldo_semanal: e.target.value })} />
                </Field>
              )}
              <Field label="% aguinaldo propio (opcional, si no usa el del área)">
                <Input type="number" min="0" max="100" step="0.5" value={form.porcentaje_aguinaldo} onChange={(e) => setForm({ ...form, porcentaje_aguinaldo: e.target.value })} placeholder="Ej: 8" />
              </Field>
            </>
          )}
        </div>
      </Modal>

      <ConfirmDialog
        open={confirmDeleteId !== null}
        title="Eliminar empleado"
        message="¿Eliminar este empleado? Esta acción no se puede deshacer."
        confirmLabel="Eliminar"
        onConfirm={() => confirmDeleteId !== null && eliminar(confirmDeleteId)}
        onCancel={() => setConfirmDeleteId(null)}
      />
    </div>
  );
}
