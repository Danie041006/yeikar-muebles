import api from './api';

export interface Client {
  id: number;
  nombre: string;
  telefono?: string;
  direccion?: string;
  email?: string;
  ciudad?: string;
  estado?: string;
  observaciones?: string;
  fecha_registro?: string;
  created_at?: string;
  updated_at?: string;
}

export interface ClientCreate {
  nombre: string;
  telefono?: string;
  direccion?: string;
  email?: string;
  ciudad?: string;
  estado?: string;
  observaciones?: string;
}

export const clienteService = {
  getAll: async (search?: string): Promise<Client[]> => {
    const response = await api.get<Client[]>('/cliente/', {
      params: search ? { search } : {},
    });
    return response.data;
  },

  getById: async (id: number): Promise<Client> => {
    const response = await api.get<Client>(`/cliente/${id}`);
    return response.data;
  },

  create: async (client: ClientCreate): Promise<Client> => {
    const response = await api.post<Client>('/cliente/', client);
    return response.data;
  },

  update: async (id: number, client: Partial<ClientCreate>): Promise<Client> => {
    const response = await api.put<Client>(`/cliente/${id}`, client);
    return response.data;
  },

  delete: async (id: number): Promise<void> => {
    await api.delete(`/cliente/${id}`);
  },
};
