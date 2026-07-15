import { useEffect, useState } from 'react';
import { authApi } from '../services/api';

interface Role {
  id: number;
  nombre: string;
  descripcion?: string;
}

interface User {
  id: number;
  nombre_usuario: string;
  email: string | null;
  activo: boolean;
  ultimo_acceso: string | null;
  created_at: string;
  roles: Role[];
}

export default function Usuarios() {
  const [users, setUsers] = useState<User[]>([]);
  const [roles, setRoles] = useState<Role[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  // Create User modal and form state
  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [newUsername, setNewUsername] = useState('');
  const [newEmail, setNewEmail] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [createLoading, setCreateLoading] = useState(false);

  // Fetch initial data
  const fetchData = async () => {
    setLoading(true);
    setError('');
    try {
      const [usersRes, rolesRes] = await Promise.all([
        authApi.get<User[]>('/users'),
        authApi.get<Role[]>('/roles'),
      ]);
      setUsers(usersRes.data);
      setRoles(rolesRes.data);
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

  const handleCreateUser = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setSuccess('');
    setCreateLoading(true);
    try {
      const response = await authApi.post<User>('/users', {
        nombre_usuario: newUsername,
        email: newEmail || null,
        password: newPassword,
      });
      setUsers([...users, response.data]);
      setSuccess(`Usuario "${newUsername}" creado con éxito.`);
      setIsCreateOpen(false);
      setNewUsername('');
      setNewEmail('');
      setNewPassword('');
    } catch (err: any) {
      console.error(err);
      setError(err.response?.data?.detail || 'Error al crear el nuevo usuario.');
    } finally {
      setCreateLoading(false);
    }
  };

  const handleDeleteUser = async (user: User) => {
    if (!window.confirm(`¿Estás seguro de que deseas eliminar permanentemente al usuario "${user.nombre_usuario}"?`)) {
      return;
    }
    setError('');
    setSuccess('');
    try {
      await authApi.delete(`/users/${user.id}`);
      setUsers(users.filter(u => u.id !== user.id));
      setSuccess(`Usuario "${user.nombre_usuario}" eliminado correctamente.`);
    } catch (err: any) {
      console.error(err);
      setError(err.response?.data?.detail || 'Error al eliminar el usuario.');
    }
  };

  return (
    <div className="space-y-6">
      {/* Top Header & Actions */}
      <div className="flex flex-col sm:flex-row items-center justify-between gap-4 bg-white p-6 rounded-2xl border border-yeikar-secondary-light/10 shadow-sm">
        <div>
          <h1 className="text-2xl font-black font-headline text-yeikar-neutral tracking-tight">
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
        <div className="bg-red-50 text-red-700 p-4 rounded-xl border border-red-200 text-sm animate-fadeIn flex items-center gap-3">
          <svg className="w-5 h-5 text-red-600 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          <span>{error}</span>
        </div>
      )}

      {success && (
        <div className="bg-green-50 text-green-700 p-4 rounded-xl border border-green-200 text-sm animate-fadeIn flex items-center gap-3">
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
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse">
              <thead>
                <tr className="bg-yeikar-tertiary/20 text-yeikar-secondary font-headline font-bold text-xs uppercase tracking-wider border-b border-yeikar-secondary-light/10">
                  <th className="p-4">Usuario</th>
                  <th className="p-4">Email</th>
                  <th className="p-4">Creado el</th>
                  <th className="p-4">Último Acceso</th>
                  <th className="p-4">Estado</th>
                  <th className="p-4">Roles de Acceso</th>
                  <th className="p-4 text-center">Acciones</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-yeikar-secondary-light/5 text-sm">
                {users.length === 0 ? (
                  <tr>
                    <td colSpan={7} className="p-8 text-center text-yeikar-neutral/40 italic">
                      No hay usuarios registrados.
                    </td>
                  </tr>
                ) : (
                  users.map((u) => (
                    <tr key={u.id} className="hover:bg-yeikar-tertiary/10 transition-colors">
                      {/* Username */}
                      <td className="p-4">
                        <div className="flex items-center gap-3">
                          <div className="w-9 h-9 rounded-lg bg-yeikar-secondary/10 flex items-center justify-center font-bold text-yeikar-secondary border border-yeikar-secondary/10 font-headline text-sm">
                            {u.nombre_usuario.substring(0, 2).toUpperCase()}
                          </div>
                          <span className="font-bold text-yeikar-secondary font-headline">{u.nombre_usuario}</span>
                        </div>
                      </td>

                      {/* Email */}
                      <td className="p-4 text-yeikar-neutral/70 font-mono text-xs">
                        {u.email || <span className="text-yeikar-neutral/30 italic">Sin correo</span>}
                      </td>

                      {/* Created date */}
                      <td className="p-4 text-yeikar-neutral/50 font-mono text-xs">
                        {new Date(u.created_at).toLocaleDateString('es-ES')}
                      </td>

                      {/* Last access */}
                      <td className="p-4 text-yeikar-neutral/50 font-mono text-xs">
                        {u.ultimo_acceso ? (
                          new Date(u.ultimo_acceso).toLocaleDateString('es-ES', {
                            day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit'
                          })
                        ) : (
                          <span className="text-yeikar-neutral/30 italic">Nunca</span>
                        )}
                      </td>

                      {/* Active switch */}
                      <td className="p-4">
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
                      </td>

                      {/* Role pills checkbox-like toggle */}
                      <td className="p-4">
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
                      </td>

                      {/* Actions */}
                      <td className="p-4 text-center">
                        <button
                          onClick={() => handleDeleteUser(u)}
                          className="text-red-500 hover:text-red-700 p-1.5 hover:bg-red-50 rounded-lg transition-colors"
                          title="Eliminar usuario"
                        >
                          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                          </svg>
                        </button>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Modal - Create User */}
      {isCreateOpen && (
        <div className="fixed inset-0 bg-yeikar-neutral/60 backdrop-blur-sm z-50 flex items-center justify-center p-4 animate-fadeIn">
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
    </div>
  );
}
