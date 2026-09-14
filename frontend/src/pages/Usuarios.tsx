import { useEffect, useState } from 'react';
import { authApi } from '../services/api';
import api from '../services/api';
import ConfirmDialog from '../components/ui/ConfirmDialog';
import { useToast } from '../context/ToastContext';
import { ResponsiveDataTable, type DataColumn } from '../components/ui';

interface Role {
  id: number;
  nombre: string;
  descripcion?: string;
}

interface User {
  id: number;
  nombre_usuario: string;
  nombre?: string | null;
  email: string | null;
  activo: boolean;
  ultimo_acceso: string | null;
  created_at: string;
  totp_habilitado?: boolean;
  roles: Role[];
}

interface ModuloCatalogo {
  clave: string;
  nombre: string;
  descripcion?: string;
}

interface ModuloAcceso {
  modulo: string;
  gestionar: boolean;
}

const ROLES_SUPER = ['Dueño', 'Administrador'];

const NIVELES = [
  { valor: null as boolean | null, label: 'No', titulo: 'Sin acceso' },
  { valor: false as boolean | null, label: 'Ver', titulo: 'Solo lectura' },
  { valor: true as boolean | null, label: 'Gestionar', titulo: 'Leer y operar' },
];

function ModuloSelectorModulos({
  modulos,
  draft,
  setDraft,
}: {
  modulos: ModuloCatalogo[];
  draft: ModuloAcceso[];
  setDraft: (next: ModuloAcceso[]) => void;
}) {
  const nivelDe = (modulo: string) => draft.find((d) => d.modulo === modulo)?.gestionar ?? null;
  const setNivel = (modulo: string, nivel: boolean | null) => {
    const next = draft.filter((d) => d.modulo !== modulo);
    if (nivel !== null) next.push({ modulo, gestionar: nivel });
    setDraft(next);
  };

  return (
    <div className="divide-y divide-yeikar-secondary-light/5">
      {modulos.map((m) => {
        const activo = nivelDe(m.clave);
        return (
          <div key={m.clave} className="py-2.5 flex items-center justify-between gap-3">
            <div>
              <p className="text-sm font-bold text-yeikar-secondary font-headline">{m.nombre}</p>
              {m.descripcion && <p className="text-xs text-yeikar-neutral/45">{m.descripcion}</p>}
            </div>
            <div className="flex gap-1 shrink-0">
              {NIVELES.map((op) => {
                const selected = activo === op.valor;
                return (
                  <button
                    key={String(op.valor)}
                    onClick={() => setNivel(m.clave, op.valor)}
                    title={op.titulo}
                    className={`px-2.5 py-1 rounded-lg text-xs font-bold border transition-all ${
                      selected
                        ? 'bg-yeikar-primary text-yeikar-neutral border-yeikar-primary'
                        : 'bg-white border-yeikar-secondary-light/10 text-yeikar-neutral/40 hover:bg-yeikar-tertiary'
                    }`}
                  >
                    {op.label}
                  </button>
                );
              })}
            </div>
          </div>
        );
      })}
    </div>
  );
}

const minOptions = [
  { key: 'no', valor: null as boolean | null, label: 'No' },
  { key: 'ver', valor: false as boolean | null, label: 'Ver' },
  { key: 'gestionar', valor: true as boolean | null, label: 'Gestionar' },
];

function onChangeNivel(
  m: ModuloCatalogo,
  valor: boolean | null,
  draft: ModuloAcceso[],
  onChange: (next: ModuloAcceso[]) => void,
) {
  const next = draft.filter((d) => d.modulo !== m.clave);
  if (valor !== null) next.push({ modulo: m.clave, gestionar: valor });
  onChange(next);
}

export default function Usuarios() {
  const toast = useToast();
  const [confirmUser, setConfirmUser] = useState<User | null>(null);
  const [confirmRol, setConfirmRol] = useState<Role | null>(null);
  const [users, setUsers] = useState<User[]>([]);
  const [roles, setRoles] = useState<Role[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  // Create User modal and form state
  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [newUsername, setNewUsername] = useState('');
  const [newNombre, setNewNombre] = useState('');
  const [newEmail, setNewEmail] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [createLoading, setCreateLoading] = useState(false);

  // Roles y módulos section
  const [modulosCatalogo, setModulosCatalogo] = useState<ModuloCatalogo[]>([]);
  const [permisosRoles, setPermisosRoles] = useState<Record<number, ModuloAcceso[]>>({});
  const [rolEditor, setRolEditor] = useState<Role | null>(null);
  const [rolDraft, setRolDraft] = useState<ModuloAcceso[]>([]);
  const [rolSaving, setRolSaving] = useState(false);

  // Create role modal
  const [isRolCreateOpen, setIsRolCreateOpen] = useState(false);
  const [newRolNombre, setNewRolNombre] = useState('');
  const [newRolDescripcion, setNewRolDescripcion] = useState('');
  const [rolCreateLoading, setRolCreateLoading] = useState(false);

  // Edit role modal
  const [isRolEditOpen, setIsRolEditOpen] = useState(false);
  const [editRolId, setEditRolId] = useState<number | null>(null);
  const [editRolNombre, setEditRolNombre] = useState('');
  const [editRolDescripcion, setEditRolDescripcion] = useState('');
  const [rolEditLoading, setRolEditLoading] = useState(false);

  // Fetch initial data
  const fetchData = async () => {
    setLoading(true);
    setError('');
    try {
      const [usersRes, rolesRes, modulosRes] = await Promise.all([
        authApi.get<User[]>('/users'),
        authApi.get<Role[]>('/roles'),
        authApi.get<ModuloCatalogo[]>('/modulos'),
      ]);
      setUsers(usersRes.data);
      setRoles(rolesRes.data);
      setModulosCatalogo(modulosRes.data);
    } catch (err: any) {
      console.error(err);
      setError('Error al cargar la información de usuarios y roles.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, []);

  const handleToggleStatus = async (user: User) => {
    setError('');
    setSuccess('');
    try {
      const newStatus = !user.activo;
      await authApi.put(`/users/${user.id}/status`, null, {
        params: { activo: newStatus },
      });
      setUsers(users.map(u => u.id === user.id ? { ...u, activo: newStatus } : u));
      setSuccess(`Estado del usuario "${user.nombre_usuario}" actualizado correctamente.`);
    } catch (err: any) {
      console.error(err);
      setError(err.response?.data?.detail || 'Error al cambiar el estado del usuario.');
    }
  };

  const handleToggleRole = async (user: User, role: Role) => {
    setError('');
    setSuccess('');
    const hasRole = user.roles.some(r => r.id === role.id);
    try {
      if (hasRole) {
        // Remove role
        await authApi.delete(`/usuario/${user.id}/roles/${role.id}`);
        setUsers(users.map(u => {
          if (u.id === user.id) {
            return { ...u, roles: u.roles.filter(r => r.id !== role.id) };
          }
          return u;
        }));
        setSuccess(`Rol "${role.nombre}" revocado del usuario "${user.nombre_usuario}".`);
      } else {
        // Assign role
        await authApi.post(`/usuario/${user.id}/roles/${role.id}`);
        setUsers(users.map(u => {
          if (u.id === user.id) {
            return { ...u, roles: [...u.roles, role] };
          }
          return u;
        }));
        setSuccess(`Rol "${role.nombre}" asignado al usuario "${user.nombre_usuario}".`);
      }
    } catch (err: any) {
      console.error(err);
      setError(err.response?.data?.detail || 'Error al modificar los roles del usuario.');
    }
  };

  // Rescate: el usuario perdió la app 2FA. Apaga su segundo factor y cierra
  // sus sesiones; entra de nuevo solo con contraseña.
  const handleReset2FA = async (user: User) => {
    if (!window.confirm(`¿Resetear el 2FA de "${user.nombre_usuario}"? Sus sesiones se cerrarán.`)) return;
    setError('');
    setSuccess('');
    try {
      await authApi.post(`/users/${user.id}/reset-2fa`);
      setUsers(users.map(u => u.id === user.id ? { ...u, totp_habilitado: false } : u));
      setSuccess(`2FA de "${user.nombre_usuario}" reseteado. Sus sesiones fueron cerradas.`);
    } catch (err: any) {
      console.error(err);
      setError(err.response?.data?.detail || 'Error al resetear el 2FA.');
    }
  };

  const handleCreateUser = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setSuccess('');
    setCreateLoading(true);
    try {
      const response = await authApi.post<User>('/users', {
        nombre_usuario: newUsername,
        nombre: newNombre || null,
        email: newEmail || null,
        password: newPassword,
      });
      setUsers([...users, response.data]);
      setSuccess(`Usuario "${newUsername}" creado con éxito.`);
      setIsCreateOpen(false);
      setNewUsername('');
      setNewNombre('');
      setNewEmail('');
      setNewPassword('');
    } catch (err: any) {
      console.error(err);
      setError(err.response?.data?.detail || 'Error al crear el nuevo usuario.');
    } finally {
      setCreateLoading(false);
    }
  };

  const handleDeleteUser = (user: User) => {
    setConfirmUser(user);
  };
  const ejecutarDeleteUser = async () => {
    if (!confirmUser) return;
    const user = confirmUser;
    setConfirmUser(null);
    setError('');
    setSuccess('');
    try {
      await authApi.delete(`/users/${user.id}`);
      setUsers(users.filter(u => u.id !== user.id));
      toast.success(`Usuario "${user.nombre_usuario}" eliminado correctamente.`);
    } catch (err: any) {
      console.error(err);
      toast.error(err.response?.data?.detail || 'Error al eliminar el usuario.');
    }
  };

  // --- Roles y módulos ---
  const abrirEditorRol = async (rol: Role) => {
    setError('');
    try {
      let permisos = permisosRoles[rol.id];
      if (!permisos) {
        const res = await authApi.get<ModuloAcceso[]>(`/roles/${rol.id}/permisos`);
        permisos = res.data;
        setPermisosRoles((prev) => ({ ...prev, [rol.id]: res.data }));
      }
      setRolDraft(permisos.map((p) => ({ ...p })));
      setRolEditor(rol);
    } catch (err: any) {
      console.error(err);
      setError(err.response?.data?.detail || 'Error al cargar los permisos del rol.');
    }
  };

  const guardarPermisosRol = async () => {
    if (!rolEditor) return;
    setRolSaving(true);
    setError('');
    setSuccess('');
    try {
      await authApi.put(`/roles/${rolEditor.id}/permisos`, { permisos: rolDraft });
      setPermisosRoles((prev) => ({ ...prev, [rolEditor.id]: rolDraft.map((p) => ({ ...p })) }));
      setSuccess(`Privilegios del rol "${rolEditor.nombre}" guardados correctamente.`);
      setRolEditor(null);
    } catch (err: any) {
      console.error(err);
      setError(err.response?.data?.detail || 'Error al guardar los privilegios del rol.');
    } finally {
      setRolSaving(false);
    }
  };

  const handleCreateRol = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setSuccess('');
    setRolCreateLoading(true);
    try {
      const res = await api.post<Role>('/catalogos/rol/', {
        nombre: newRolNombre,
        descripcion: newRolDescripcion || null,
      });
      setRoles((prev) => [...prev, res.data]);
      setSuccess(`Rol "${newRolNombre}" creado. Ahora puedes configurar sus módulos.`);
      setIsRolCreateOpen(false);
      setNewRolNombre('');
      setNewRolDescripcion('');
    } catch (err: any) {
      console.error(err);
      setError(err.response?.data?.detail || 'Error al crear el rol.');
    } finally {
      setRolCreateLoading(false);
    }
  };

  const openEditRol = (rol: Role) => {
    setEditRolId(rol.id);
    setEditRolNombre(rol.nombre);
    setEditRolDescripcion(rol.descripcion || '');
    setIsRolEditOpen(true);
  };

  const handleEditRol = async (e: React.FormEvent) => {
    e.preventDefault();
    if (editRolId === null) return;
    setError('');
    setSuccess('');
    setRolEditLoading(true);
    try {
      const res = await api.put<Role>(`/catalogos/rol/${editRolId}`, {
        nombre: editRolNombre,
        descripcion: editRolDescripcion || null,
      });
      setRoles((prev) => prev.map((r) => (r.id === editRolId ? res.data : r)));
      setSuccess(`Rol "${editRolNombre}" actualizado.`);
      setIsRolEditOpen(false);
    } catch (err: any) {
      console.error(err);
      setError(err.response?.data?.detail || 'Error al actualizar el rol.');
    } finally {
      setRolEditLoading(false);
    }
  };

  const handleDeleteRol = async (rol: Role) => {
    if (ROLES_SUPER.includes(rol.nombre)) {
      setError(`El rol "${rol.nombre}" es un rol de acceso total y no se puede eliminar.`);
      return;
    }
    setConfirmRol(rol);
  };
  const ejecutarDeleteRol = async () => {
    if (!confirmRol) return;
    const rol = confirmRol;
    setConfirmRol(null);
    setError('');
    setSuccess('');
    try {
      await api.delete(`/catalogos/rol/${rol.id}`);
      setRoles((prev) => prev.filter((r) => r.id !== rol.id));
      toast.success(`Rol "${rol.nombre}" eliminado.`);
    } catch (err: any) {
      console.error(err);
      toast.error(err.response?.data?.detail || 'Error al eliminar el rol.');
    }
  };

  const resumenModulos = (rol: Role) => {
    const permisos = permisosRoles[rol.id];
    if (!permisos) return null;
    const gestiona = permisos.filter((p) => p.gestionar).length;
    const soloVer = permisos.filter((p) => !p.gestionar).length;
    return { gestiona, soloVer };
  };

  const renderActions = (u: User) => (
    <button
      onClick={() => handleDeleteUser(u)}
      className="text-red-500 hover:text-red-700 p-1.5 hover:bg-red-50 rounded-lg transition-colors"
      title="Eliminar usuario"
    >
      <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
      </svg>
    </button>
  );

  const columns: DataColumn<User>[] = [
    {
      key: 'usuario',
      header: 'Usuario',
      render: (u) => (
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-lg bg-yeikar-secondary/10 flex items-center justify-center font-bold text-yeikar-secondary border border-yeikar-secondary/10 font-headline text-sm">
            {(u.nombre || u.nombre_usuario).substring(0, 2).toUpperCase()}
          </div>
          <div className="min-w-0">
            <div className="font-bold text-yeikar-secondary font-headline truncate">
              {u.nombre_usuario}
            </div>
            {u.nombre && (
              <div className="text-[10px] text-yeikar-neutral/50 font-mono truncate">
                {u.nombre}
              </div>
            )}
          </div>
        </div>
      ),
      mobilePrimary: true,
    },
    {
      key: 'email',
      header: 'Email',
      render: (u) => (
        <span className="text-yeikar-neutral/70 font-mono text-xs">
          {u.email || <span className="text-yeikar-neutral/30 italic">Sin correo</span>}
        </span>
      ),
      mobileLabel: 'Email',
      mobileSecondary: true,
    },
    {
      key: 'creado',
      header: 'Creado el',
      render: (u) => (
        <span className="text-yeikar-neutral/50 font-mono text-xs">
          {new Date(u.created_at).toLocaleDateString('es-ES')}
        </span>
      ),
      mobileLabel: 'Creado',
    },
    {
      key: 'ultimo_acceso',
      header: 'Último Acceso',
      render: (u) => (
        <span className="text-yeikar-neutral/50 font-mono text-xs">
          {u.ultimo_acceso ? (
            new Date(u.ultimo_acceso).toLocaleDateString('es-ES', {
              day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit'
            })
          ) : (
            <span className="text-yeikar-neutral/30 italic">Nunca</span>
          )}
        </span>
      ),
      mobileLabel: 'Último Acceso',
    },
    {
      key: 'estado',
      header: 'Estado',
      render: (u) => (
        <button
          onClick={() => handleToggleStatus(u)}
          className={`px-3 py-1 rounded-full text-xs font-bold transition-all ${
            u.activo
              ? 'bg-green-50 text-green-700 hover:bg-green-100 border border-green-200'
              : 'bg-red-50 text-red-700 hover:bg-red-100 border border-red-200'
          }`}
        >
          {u.activo ? 'Activo' : 'Inactivo'}
        </button>
      ),
      mobileHidden: true,
    },
    {
      key: 'roles',
      header: 'Roles de Acceso',
      render: (u) => (
        <div className="flex flex-wrap gap-1.5 max-w-xs">
          {roles.map((role) => {
            const isAssigned = u.roles.some((r) => r.id === role.id);
            return (
              <button
                key={role.id}
                onClick={() => handleToggleRole(u, role)}
                className={`px-2 py-1 rounded text-xs font-headline font-bold transition-all border ${
                  isAssigned
                    ? 'bg-yeikar-primary/10 border-yeikar-primary text-yeikar-primary-dark shadow-sm'
                    : 'bg-white border-yeikar-secondary-light/10 text-yeikar-neutral/40 hover:bg-yeikar-tertiary'
                }`}
              >
                {role.nombre}
              </button>
            );
          })}
        </div>
      ),
      mobileLabel: 'Roles de Acceso',
    },
    {
      key: 'dosfa',
      header: '2FA',
      render: (u) => (
        <div className="flex items-center gap-2">
          <span
            className={`px-2 py-1 rounded text-[10px] font-bold uppercase border ${
              u.totp_habilitado
                ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
                : 'bg-yeikar-tertiary/20 text-yeikar-neutral/45 border-yeikar-secondary-light/15'
            }`}
          >
            {u.totp_habilitado ? 'Activo' : 'Off'}
          </span>
          {u.totp_habilitado && (
            <button
              onClick={() => handleReset2FA(u)}
              title="Resetear 2FA (para quien perdió su app)"
              className="px-1.5 py-1 rounded text-[10px] font-bold text-rose-500 hover:bg-rose-50 border border-transparent hover:border-rose-200 transition-all"
            >
              Reiniciar
            </button>
          )}
        </div>
      ),
      mobileLabel: '2FA',
    },
  ];

  return (
    <div className="space-y-6">
      {/* Top Header & Actions */}
      <div className="flex flex-col sm:flex-row items-center justify-between gap-4 bg-white p-6 rounded-2xl border border-yeikar-secondary-light/10 shadow-sm">
        <div>
          <h1 className="text-3xl font-black font-headline text-yeikar-neutral tracking-tight">
            Gestión de Usuarios y Roles
          </h1>
          <p className="text-sm text-yeikar-neutral/50">
            Administra los accesos del personal, monitorea logins y asigna permisos específicos por rol.
          </p>
        </div>
        <button
          onClick={() => setIsCreateOpen(true)}
          className="w-full sm:w-auto bg-yeikar-primary text-yeikar-neutral font-bold px-5 py-2.5 rounded-lg shadow-md hover:bg-yeikar-primary-light transition-all flex items-center justify-center gap-2 font-headline"
        >
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M18 9v3m0 0v3m0-3h3m-3 0h-3m-2-5a4 4 0 11-8 0 4 4 0 018 0zM3 20a6 6 0 0112 0v1H3v-1z" />
          </svg>
          Nuevo Usuario
        </button>
      </div>

      {/* Notifications */}
      {error && (
        <div className="bg-red-50 text-red-700 p-4 rounded-xl border border-red-200 text-sm animate-fade-in flex items-center gap-3">
          <svg className="w-5 h-5 text-red-600 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          <span>{error}</span>
        </div>
      )}

      {success && (
        <div className="bg-green-50 text-green-700 p-4 rounded-xl border border-green-200 text-sm animate-fade-in flex items-center gap-3">
          <svg className="w-5 h-5 text-green-600 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          <span>{success}</span>
        </div>
      )}

      {/* Main Table View */}
      <div className="bg-white border border-yeikar-secondary-light/10 rounded-2xl overflow-hidden shadow-sm">
        {loading ? (
          <div className="p-12 text-center text-yeikar-neutral/40 flex flex-col items-center justify-center gap-3">
            <div className="w-8 h-8 border-4 border-yeikar-primary border-t-transparent rounded-full animate-spin"></div>
            <span className="text-sm font-mono">Cargando usuarios...</span>
          </div>
        ) : (
          <ResponsiveDataTable
            columns={columns}
            rows={users}
            rowKey={(u) => u.id}
            cardBadge={(u) => (
              <button
                onClick={() => handleToggleStatus(u)}
                className={`px-3 py-1 rounded-full text-xs font-bold transition-all ${
                  u.activo
                    ? 'bg-green-50 text-green-700 hover:bg-green-100 border border-green-200'
                    : 'bg-red-50 text-red-700 hover:bg-red-100 border border-red-200'
                }`}
              >
                {u.activo ? 'Activo' : 'Inactivo'}
              </button>
            )}
            tableActions={renderActions}
            cardActions={renderActions}
            empty={<div className="p-8 text-center text-yeikar-neutral/40 italic">No hay usuarios registrados.</div>}
          />
        )}
      </div>

      {/* Roles y módulos */}
      <div className="bg-white border border-yeikar-secondary-light/10 rounded-2xl overflow-hidden shadow-sm">
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 p-6 border-b border-yeikar-secondary-light/10">
          <div>
            <h2 className="text-lg font-black font-headline text-yeikar-secondary tracking-tight">
              Roles y módulos
            </h2>
            <p className="text-sm text-yeikar-neutral/50">
              Define qué módulos del ERP abre cada rol y si solo lo ve o también lo gestiona.
            </p>
          </div>
          <button
            onClick={() => setIsRolCreateOpen(true)}
            className="w-full sm:w-auto bg-yeikar-secondary text-yeikar-primary font-bold px-4 py-2 rounded-lg hover:bg-yeikar-secondary-light transition-all flex items-center justify-center gap-2 font-headline text-sm"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 4v16m8-8H4" />
            </svg>
            Nuevo Rol
          </button>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4 p-6">
          {roles.map((rol) => {
            const resumen = resumenModulos(rol);
            const esSuper = ROLES_SUPER.includes(rol.nombre);
            return (
              <div key={rol.id} className="border border-yeikar-secondary-light/15 rounded-2xl p-4 flex flex-col gap-3 hover:shadow-md transition-shadow">
                <div className="flex items-start justify-between">
                  <div>
                    <p className="font-headline font-black text-yeikar-neutral">{rol.nombre}</p>
                    <p className="text-xs text-yeikar-neutral/50 mt-0.5">{rol.descripcion || 'Sin descripción'}</p>
                  </div>
                  {esSuper && (
                    <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-yeikar-primary/10 text-yeikar-primary-dark border border-yeikar-primary/20 uppercase tracking-wide shrink-0">
                      Total
                    </span>
                  )}
                </div>

                <p className="text-xs font-mono text-yeikar-neutral/60">
                  {esSuper
                    ? 'Acceso total a todos los módulos'
                    : resumen
                    ? `${resumen.gestiona} gestionan · ${resumen.soloVer} solo ver`
                    : 'Sin permisos configurados (ve solo su panel)'}
                </p>

                <div className="flex gap-2 mt-auto pt-1">
                  <button
                    onClick={() => abrirEditorRol(rol)}
                    className="flex-1 bg-yeikar-secondary/10 text-yeikar-secondary text-xs font-bold px-3 py-2 rounded-lg hover:bg-yeikar-secondary/20 transition-all font-headline"
                  >
                    Configurar módulos
                  </button>
                  <button
                    onClick={() => openEditRol(rol)}
                    className="bg-yeikar-tertiary text-yeikar-neutral/60 text-xs font-bold px-3 py-2 rounded-lg hover:bg-yeikar-secondary-light/30 transition-colors"
                    title="Editar rol"
                  >
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
                    </svg>
                  </button>
                  <button
                    onClick={() => handleDeleteRol(rol)}
                    className="px-3 py-2 text-red-500 hover:bg-red-50 rounded-lg transition-colors"
                    title="Eliminar rol"
                  >
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                    </svg>
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Modal - Create User */}
      {isCreateOpen && (
        <div className="fixed inset-0 bg-yeikar-neutral/60 backdrop-blur-sm z-50 flex items-center justify-center p-4 animate-fade-in">
          <div className="bg-white rounded-3xl border border-yeikar-secondary/15 max-w-md w-full shadow-2xl p-6 relative animate-scaleIn">
            <h3 className="text-lg font-black font-headline text-yeikar-secondary mb-1">
              Crear Nuevo Usuario
            </h3>
            <p className="text-xs text-yeikar-neutral/50 mb-4">
              Registra credenciales para un nuevo miembro del equipo.
            </p>

            <form onSubmit={handleCreateUser} className="space-y-4 font-headline">
              {/* Username */}
              <div className="space-y-1">
                <label className="text-xs font-bold text-yeikar-secondary uppercase tracking-wider block">
                  Nombre de Usuario *
                </label>
                <input
                  type="text"
                  required
                  value={newUsername}
                  onChange={(e) => setNewUsername(e.target.value.toLowerCase().replace(/\s+/g, ''))}
                  placeholder="ej. pedro.gonzalez"
                  className="w-full px-3 py-2 border border-yeikar-secondary-light/20 rounded-lg focus:outline-none focus:ring-2 focus:ring-yeikar-primary bg-yeikar-tertiary/20 text-sm font-mono"
                />
              </div>

              {/* Nombre visible */}
              <div className="space-y-1">
                <label className="text-xs font-bold text-yeikar-secondary uppercase tracking-wider block">
                  Nombre visible
                </label>
                <input
                  type="text"
                  value={newNombre}
                  onChange={(e) => setNewNombre(e.target.value)}
                  placeholder="ej. Carolina (se muestra en los saludos)"
                  className="w-full px-3 py-2 border border-yeikar-secondary-light/20 rounded-lg focus:outline-none focus:ring-2 focus:ring-yeikar-primary bg-yeikar-tertiary/20 text-sm"
                />
              </div>

              {/* Email */}
              <div className="space-y-1">
                <label className="text-xs font-bold text-yeikar-secondary uppercase tracking-wider block">
                  Correo Electrónico
                </label>
                <input
                  type="email"
                  value={newEmail}
                  onChange={(e) => setNewEmail(e.target.value)}
                  placeholder="ej. pedro@yeikar.com"
                  className="w-full px-3 py-2 border border-yeikar-secondary-light/20 rounded-lg focus:outline-none focus:ring-2 focus:ring-yeikar-primary bg-yeikar-tertiary/20 text-sm font-mono"
                />
              </div>

              {/* Password */}
              <div className="space-y-1">
                <label className="text-xs font-bold text-yeikar-secondary uppercase tracking-wider block">
                  Contraseña Temporal *
                </label>
                <input
                  type="password"
                  required
                  value={newPassword}
                  onChange={(e) => setNewPassword(e.target.value)}
                  placeholder="Mínimo 6 caracteres"
                  className="w-full px-3 py-2 border border-yeikar-secondary-light/20 rounded-lg focus:outline-none focus:ring-2 focus:ring-yeikar-primary bg-yeikar-tertiary/20 text-sm"
                />
              </div>

              {/* Form Actions */}
              <div className="flex gap-3 pt-2">
                <button
                  type="button"
                  onClick={() => setIsCreateOpen(false)}
                  className="flex-1 py-2.5 border border-yeikar-secondary-light/20 rounded-lg text-yeikar-secondary hover:bg-yeikar-tertiary font-bold text-sm transition-all"
                >
                  Cancelar
                </button>
                <button
                  type="submit"
                  disabled={createLoading}
                  className="flex-1 py-2.5 bg-yeikar-primary text-yeikar-neutral rounded-lg hover:bg-yeikar-primary-light font-bold text-sm transition-all flex items-center justify-center gap-2"
                >
                  {createLoading ? (
                    <div className="w-5 h-5 border-2 border-yeikar-neutral border-t-transparent rounded-full animate-spin"></div>
                  ) : (
                    'Crear Usuario'
                  )}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Modal - Create Rol */}
      {isRolCreateOpen && (
        <div className="fixed inset-0 bg-yeikar-neutral/60 backdrop-blur-sm z-50 flex items-center justify-center p-4 animate-fade-in">
          <div className="bg-white rounded-3xl border border-yeikar-secondary/15 max-w-md w-full shadow-2xl p-6 relative animate-scaleIn">
            <h3 className="text-lg font-black font-headline text-yeikar-secondary mb-1">Nuevo Rol</h3>
            <p className="text-xs text-yeikar-neutral/50 mb-4">
              Crea un rol y luego configúrala qué módulos verá/gestionará.
            </p>
            <form onSubmit={handleCreateRol} className="space-y-4 font-headline">
              <div className="space-y-1">
                <label className="text-xs font-bold text-yeikar-secondary uppercase tracking-wider block">
                  Nombre del Rol *
                </label>
                <input
                  type="text"
                  required
                  value={newRolNombre}
                  onChange={(e) => setNewRolNombre(e.target.value)}
                  placeholder="ej. Despachador"
                  className="w-full px-3 py-2 border border-yeikar-secondary-light/20 rounded-lg focus:outline-none focus:ring-2 focus:ring-yeikar-primary bg-yeikar-tertiary/20 text-sm"
                />
              </div>
              <div className="space-y-1">
                <label className="text-xs font-bold text-yeikar-secondary uppercase tracking-wider block">
                  Descripción
                </label>
                <textarea
                  value={newRolDescripcion}
                  onChange={(e) => setNewRolDescripcion(e.target.value)}
                  rows={2}
                  placeholder="¿Qué funciones cumple este rol?"
                  className="w-full px-3 py-2 border border-yeikar-secondary-light/20 rounded-lg focus:outline-none focus:ring-2 focus:ring-yeikar-primary bg-yeikar-tertiary/20 text-sm resize-none"
                />
              </div>
              <div className="flex gap-3 pt-2">
                <button
                  type="button"
                  onClick={() => setIsRolCreateOpen(false)}
                  className="flex-1 py-2.5 border border-yeikar-secondary-light/20 rounded-lg text-yeikar-secondary hover:bg-yeikar-tertiary font-bold text-sm transition-all"
                >
                  Cancelar
                </button>
                <button
                  type="submit"
                  disabled={rolCreateLoading}
                  className="flex-1 py-2.5 bg-yeikar-primary text-yeikar-neutral rounded-lg hover:bg-yeikar-primary-light font-bold text-sm transition-all flex items-center justify-center gap-2"
                >
                  {rolCreateLoading ? (
                    <div className="w-5 h-5 border-2 border-yeikar-neutral border-t-transparent rounded-full animate-spin"></div>
                  ) : (
                    'Crear Rol'
                  )}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Modal - Edit Rol */}
      {isRolEditOpen && (
        <div className="fixed inset-0 bg-yeikar-neutral/60 backdrop-blur-sm z-50 flex items-center justify-center p-4 animate-fade-in">
          <div className="bg-white rounded-3xl border border-yeikar-secondary/15 max-w-md w-full shadow-2xl p-6 relative animate-scaleIn">
            <h3 className="text-lg font-black font-headline text-yeikar-secondary mb-4">Editar Rol</h3>
            <form onSubmit={handleEditRol} className="space-y-4 font-headline">
              <div className="space-y-1">
                <label className="text-xs font-bold text-yeikar-secondary uppercase tracking-wider block">
                  Nombre del Rol *
                </label>
                <input
                  type="text"
                  required
                  value={editRolNombre}
                  onChange={(e) => setEditRolNombre(e.target.value)}
                  className="w-full px-3 py-2 border border-yeikar-secondary-light/20 rounded-lg focus:outline-none focus:ring-2 focus:ring-yeikar-primary bg-yeikar-tertiary/20 text-sm"
                />
              </div>
              <div className="space-y-1">
                <label className="text-xs font-bold text-yeikar-secondary uppercase tracking-wider block">
                  Descripción
                </label>
                <textarea
                  value={editRolDescripcion}
                  onChange={(e) => setEditRolDescripcion(e.target.value)}
                  rows={2}
                  className="w-full px-3 py-2 border border-yeikar-secondary-light/20 rounded-lg focus:outline-none focus:ring-2 focus:ring-yeikar-primary bg-yeikar-tertiary/20 text-sm resize-none"
                />
              </div>
              <div className="flex gap-3 pt-2">
                <button
                  type="button"
                  onClick={() => setIsRolEditOpen(false)}
                  className="flex-1 py-2.5 border border-yeikar-secondary-light/20 rounded-lg text-yeikar-secondary hover:bg-yeikar-tertiary font-bold text-sm transition-all"
                >
                  Cancelar
                </button>
                <button
                  type="submit"
                  disabled={rolEditLoading}
                  className="flex-1 py-2.5 bg-yeikar-primary text-yeikar-neutral rounded-lg hover:bg-yeikar-primary-light font-bold text-sm transition-all"
                >
                  {rolEditLoading ? 'Guardando...' : 'Guardar'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Modal - Configurar módulos del rol */}
      {rolEditor && (
        <div className="fixed inset-0 bg-yeikar-neutral/60 backdrop-blur-sm z-50 flex items-center justify-center p-4 animate-fade-in">
          <div className="bg-white rounded-3xl border border-yeikar-secondary/15 max-w-2xl w-full shadow-2xl p-6 relative animate-scaleIn max-h-[85vh] flex flex-col">
            <div className="flex items-start justify-between mb-1">
              <div>
                <h3 className="text-lg font-black font-headline text-yeikar-secondary">
                  Privilegios del rol "{rolEditor.nombre}"
                </h3>
                <p className="text-xs text-yeikar-neutral/50">
                  'No' = sin acceso · 'Ver' = solo lectura · 'Gestionar' = leer y operar
                </p>
              </div>
              <button
                onClick={() => setRolEditor(null)}
                className="text-yeikar-neutral/40 hover:text-yeikar-neutral p-1 rounded-lg hover:bg-yeikar-tertiary"
              >
                <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>

            <div className="overflow-y-auto flex-1 pr-1 mt-2">
              <ModuloSelectorModulos modulos={modulosCatalogo} draft={rolDraft} setDraft={setRolDraft} />
            </div>

            <div className="flex gap-3 pt-4 border-t border-yeikar-secondary-light/10 mt-4">
              <button
                onClick={() => setRolEditor(null)}
                className="flex-1 py-2.5 border border-yeikar-secondary-light/20 rounded-lg text-yeikar-secondary hover:bg-yeikar-tertiary font-bold text-sm transition-all"
              >
                Cancelar
              </button>
              <button
                onClick={guardarPermisosRol}
                disabled={rolSaving}
                className="flex-1 py-2.5 bg-yeikar-primary text-yeikar-neutral rounded-lg hover:bg-yeikar-primary-light font-bold text-sm transition-all disabled:opacity-50 flex items-center justify-center gap-2"
              >
                {rolSaving ? (
                  <div className="w-5 h-5 border-2 border-yeikar-neutral border-t-transparent rounded-full animate-spin"></div>
                ) : (
                  'Guardar Privilegios'
                )}
              </button>
            </div>
          </div>
        </div>
      )}
      <ConfirmDialog
        open={confirmUser !== null}
        title="Eliminar usuario"
        message={confirmUser ? `¿Estás seguro de que deseas eliminar permanentemente al usuario "${confirmUser.nombre_usuario}"?` : ''}
        confirmLabel="Sí, eliminar"
        danger
        onConfirm={ejecutarDeleteUser}
        onCancel={() => setConfirmUser(null)}
      />
      <ConfirmDialog
        open={confirmRol !== null}
        title="Eliminar rol"
        message={confirmRol ? `¿Eliminar el rol "${confirmRol.nombre}"? Los usuarios que lo tengan perderán esos privilegios.` : ''}
        confirmLabel="Sí, eliminar"
        danger
        onConfirm={ejecutarDeleteRol}
        onCancel={() => setConfirmRol(null)}
      />
    </div>
  );
}