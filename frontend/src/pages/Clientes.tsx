import { useEffect, useState } from 'react';
import {
  Button,
  Card,
  EmptyState,
  Modal,
  PageHeader,
  SearchInput,
  Spinner,
  ConfirmDialog,
  Field,
  Input,
  Textarea,
} from '../components/ui';
import { clienteService, Client, ClientCreate } from '../services/clienteService';
import { Plus, Users, Mail, Phone, Pencil, Trash2, MapPin } from 'lucide-react';

export default function Clientes() {
  const [clients, setClients] = useState<Client[]>([]);
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  // Modal State
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [editingClient, setEditingClient] = useState<Client | null>(null);

  // Confirm Delete
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [pendingDeleteId, setPendingDeleteId] = useState<number | null>(null);

  // Form State
  const [formData, setFormData] = useState<ClientCreate>({
    nombre: '',
    telefono: '',
    email: '',
    direccion: '',
    ciudad: '',
    estado: '',
    observaciones: '',
  });

  const fetchClients = async (searchTerm?: string) => {
    setLoading(true);
    setError('');
    try {
      const data = await clienteService.getAll(searchTerm);
      setClients(data);
    } catch (err: any) {
      console.error(err);
      setError('No se pudieron cargar los clientes. Intenta de nuevo.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    const timer = setTimeout(() => {
      fetchClients(search);
    }, 300);

    return () => clearTimeout(timer);
  }, [search]);

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => {
    const { name, value } = e.target;
    setFormData((prev) => ({ ...prev, [name]: value }));
  };

  const handleOpenCreateModal = () => {
    setEditingClient(null);
    setFormData({
      nombre: '',
      telefono: '',
      email: '',
      direccion: '',
      ciudad: '',
      estado: '',
      observaciones: '',
    });
    setIsModalOpen(true);
  };

  const handleOpenEditModal = (client: Client) => {
    setEditingClient(client);
    setFormData({
      nombre: client.nombre,
      telefono: client.telefono || '',
      email: client.email || '',
      direccion: client.direccion || '',
      ciudad: client.ciudad || '',
      estado: client.estado || '',
      observaciones: client.observaciones || '',
    });
    setIsModalOpen(true);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    if (!formData.nombre.trim()) {
      setError('El nombre del cliente es obligatorio');
      return;
    }
    if (!formData.telefono.trim()) {
      setError('El número de teléfono es obligatorio');
      return;
    }

    // Limpiar campos opcionales vacíos para no enviar strings vacíos al backend
    const payload: any = {
      nombre: formData.nombre.trim(),
      telefono: formData.telefono.trim(),
      email: formData.email?.trim() || null,
      direccion: formData.direccion?.trim() || null,
      ciudad: formData.ciudad?.trim() || null,
      estado: formData.estado?.trim() || null,
      observaciones: formData.observaciones?.trim() || null,
    };

    try {
      if (editingClient) {
        await clienteService.update(editingClient.id, payload);
      } else {
        await clienteService.create(payload);
      }
      setIsModalOpen(false);
      fetchClients(search);
    } catch (err: any) {
      console.error(err);
      const detail = err?.response?.data?.detail;
      setError(typeof detail === 'string' ? detail : 'Ocurrió un error al guardar el cliente.');
    }
  };

  const handleOpenDeleteConfirm = (id: number) => {
    setPendingDeleteId(id);
    setConfirmOpen(true);
  };

  const handleDelete = async () => {
    if (pendingDeleteId === null) return;
    try {
      await clienteService.delete(pendingDeleteId);
      fetchClients(search);
    } catch (err: any) {
      console.error(err);
      alert('No se pudo eliminar el cliente.');
    }
  };

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Directorio"
        title="Clientes"
        icon={<Users className="w-5 h-5" />}
        subtitle={
          <span>
            {clients.length} cliente{clients.length !== 1 && 's'} registrado
            {clients.length !== 1 && 's'} en el sistema
          </span>
        }
        actions={
          <Button onClick={handleOpenCreateModal} icon={<Plus className="w-4 h-4" />}>
            Registrar Cliente
          </Button>
        }
      />

      <div className="flex flex-col sm:flex-row items-center justify-between gap-3">
        <SearchInput
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Buscar por nombre, email o teléfono..."
          className="w-full sm:w-96"
        />
      </div>

      {error && !isModalOpen && (
        <div className="bg-red-50 text-red-700 p-4 rounded-2xl border border-red-200 text-sm animate-fade-in">
          {error}
        </div>
      )}

      {/* Table Section */}
      <Card className="overflow-hidden" bodyClassName="p-0">
        {loading ? (
          <div className="p-10">
            <Spinner label="Cargando clientes..." />
          </div>
        ) : clients.length === 0 ? (
          <div className="p-6">
            <EmptyState
              compact
              icon={<Users className="w-6 h-6" />}
              title="No se encontraron clientes"
              description="Registra tu primer cliente para comenzar a cotizar."
              action={
                <Button size="sm" onClick={handleOpenCreateModal} icon={<Plus className="w-4 h-4" />}>
                  Registrar Cliente
                </Button>
              }
            />
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse">
              <thead>
                <tr>
                  <th className="table-th">Nombre</th>
                  <th className="table-th">Contacto</th>
                  <th className="table-th">Ubicación</th>
                  <th className="table-th">Observaciones</th>
                  <th className="table-th text-right">Acciones</th>
                </tr>
              </thead>
              <tbody>
                {clients.map((client) => (
                  <tr key={client.id} className="hover:bg-slate-50/60 transition-colors">
                    <td className="table-td font-bold text-yeikar-neutral font-headline">
                      {client.nombre}
                    </td>
                    <td className="table-td space-y-1.5">
                      {client.email && (
                        <div className="flex items-center gap-2 text-slate-600">
                          <Mail className="w-3.5 h-3.5 text-amber-800" />
                          <span className="text-xs">{client.email}</span>
                        </div>
                      )}
                      {client.telefono && (
                        <div className="flex items-center gap-2 text-slate-600">
                          <Phone className="w-3.5 h-3.5 text-amber-800" />
                          <span className="font-mono text-xs">{client.telefono}</span>
                        </div>
                      )}
                    </td>
                    <td className="table-td">
                      {client.direccion && (
                        <div className="flex items-center gap-2 text-slate-600 text-xs">
                          <MapPin className="w-3.5 h-3.5 text-slate-400 shrink-0" />
                          <span>{client.direccion}</span>
                        </div>
                      )}
                      {(client.ciudad || client.estado) && (
                        <div className="text-xs text-slate-400 font-mono ml-5.5">
                          {client.ciudad}
                          {client.ciudad && client.estado && ', '}
                          {client.estado}
                        </div>
                      )}
                    </td>
                    <td className="table-td text-slate-400 italic max-w-xs truncate text-xs">
                      {client.observaciones || '—'}
                    </td>
                    <td className="table-td text-right">
                      <div className="flex items-center justify-end gap-1">
                        <button
                          onClick={() => handleOpenEditModal(client)}
                          className="p-2 text-slate-400 hover:text-amber-800 hover:bg-amber-500/10 transition-all rounded-xl"
                          title="Editar"
                          aria-label="Editar cliente"
                        >
                          <Pencil className="w-4 h-4" />
                        </button>
                        <button
                          onClick={() => handleOpenDeleteConfirm(client.id)}
                          className="p-2 text-slate-400 hover:text-rose-700 hover:bg-rose-50 transition-all rounded-xl"
                          title="Eliminar"
                          aria-label="Eliminar cliente"
                        >
                          <Trash2 className="w-4 h-4" />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {/* Modal Form */}
      <Modal
        open={isModalOpen}
        onClose={() => setIsModalOpen(false)}
        title={editingClient ? 'Editar Cliente' : 'Registrar Nuevo Cliente'}
        subtitle={editingClient ? `Actualiza los datos de ${editingClient.nombre}` : 'Crea un nuevo cliente en el sistema'}
        size="lg"
        footer={
          <>
            <Button variant="outline" onClick={() => setIsModalOpen(false)}>
              Cancelar
            </Button>
            <Button type="submit" form="cliente-form">
              Guardar
            </Button>
          </>
        }
      >
        <form id="cliente-form" onSubmit={handleSubmit} className="space-y-4">
          {error && (
            <div className="bg-red-50 text-red-700 p-3 rounded-xl border border-red-200 text-sm animate-fade-in">
              {error}
            </div>
          )}

          <Field label="Nombre Completo / Razón Social" required>
            <Input
              type="text"
              name="nombre"
              value={formData.nombre}
              onChange={handleInputChange}
              required
            />
          </Field>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <Field label="Teléfono" required>
              <Input
                type="text"
                name="telefono"
                value={formData.telefono}
                onChange={handleInputChange}
                required
                placeholder="Ej: 300 123 4567"
                className="font-mono"
              />
            </Field>
            <Field label="Correo Electrónico">
              <Input
                type="email"
                name="email"
                value={formData.email ?? ''}
                onChange={handleInputChange}
              />
            </Field>
          </div>

          <Field label="Dirección">
            <Input
              type="text"
              name="direccion"
              value={formData.direccion ?? ''}
              onChange={handleInputChange}
            />
          </Field>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <Field label="Ciudad">
              <Input
                type="text"
                name="ciudad"
                value={formData.ciudad ?? ''}
                onChange={handleInputChange}
              />
            </Field>
            <Field label="Estado / Departamento">
              <Input
                type="text"
                name="estado"
                value={formData.estado ?? ''}
                onChange={handleInputChange}
              />
            </Field>
          </div>

          <Field label="Observaciones">
            <Textarea
              name="observaciones"
              value={formData.observaciones ?? ''}
              onChange={handleInputChange}
              rows={3}
            />
          </Field>
        </form>
      </Modal>

      {/* Confirm Delete */}
      <ConfirmDialog
        open={confirmOpen}
        title="Eliminar cliente"
        message="¿Estás seguro de que deseas eliminar este cliente?"
        confirmLabel="Eliminar"
        onCancel={() => setConfirmOpen(false)}
        onConfirm={async () => {
          await handleDelete();
          setConfirmOpen(false);
        }}
      />
    </div>
  );
}