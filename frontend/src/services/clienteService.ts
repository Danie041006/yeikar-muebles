import api from './api';
import {
  actualizarOperacionLocal,
  borrarCache,
  cancelarOperacionLocal,
  conCache,
  esIdLocal,
  mutarOEncolar,
  parchearCache,
} from '../offline/cache';

export interface Client {
  id: number;
  nombre: string;
  telefono: string;
  direccion?: string;
  ciudad?: string;
  estado?: string;
  cedula?: string;
  observaciones?: string;
  fecha_registro?: string;
  created_at?: string;
  updated_at?: string;
}

export interface ClientCreate {
  nombre: string;
  telefono: string;
  direccion?: string | null;
  ciudad?: string | null;
  estado?: string | null;
  cedula?: string | null;
  observaciones?: string | null;
}

async function parchearListas(cambios: Record<string, unknown> | null, id: number): Promise<void> {
  await parchearCache('clientes:', (lista) => {
    if (!Array.isArray(lista)) return undefined;
    return cambios === null
      ? lista.filter((c: any) => c.id !== id)
      : lista.map((c: any) => (c.id === id ? { ...c, ...cambios } : c));
  });
}

export const clienteService = {
  getAll: async (search?: string): Promise<Client[]> => {
    return conCache(`clientes:${search ?? ''}`, async () => {
      const response = await api.get<Client[]>('/cliente/', {
        params: search ? { search } : {},
      });
      return response.data;
    });
  },

  getById: async (id: number): Promise<Client> => {
    return conCache(`cliente:${id}`, async () => {
      const response = await api.get<Client>(`/cliente/${id}`);
      return response.data;
    });
  },

  create: async (client: ClientCreate): Promise<Client> => {
    return mutarOEncolar<Client>('cliente.crear', { ...client }, {
      enLinea: async () => {
        const response = await api.post<Client>('/cliente/', client);
        return response.data;
      },
      fabricarLocal: (idLocal) => ({ id: idLocal, ...client }) as Client,
      optimista: async (idLocal) => {
        await parchearCache('clientes:', (lista) =>
          Array.isArray(lista) ? [{ id: idLocal, ...client }, ...lista] : undefined,
        );
      },
    });
  },

  update: async (id: number, client: Partial<ClientCreate>): Promise<Client> => {
    if (esIdLocal(id)) {
      await actualizarOperacionLocal('cliente.crear', id, { ...client });
      const actual = await clienteService.getById(id).catch(() => null);
      await parchearListas({ ...client }, id);
      await parchearCache('cliente:', (c) => (c?.id === id ? { ...c, ...client } : undefined));
      return { ...(actual ?? {}), id, ...client } as Client;
    }
    return mutarOEncolar<Client>('cliente.actualizar', { cliente_id: id, ...client }, {
      enLinea: async () => {
        const response = await api.put<Client>(`/cliente/${id}`, client);
        return response.data;
      },
      optimista: async () => {
        await parchearListas(client as Record<string, unknown>, id);
        await parchearCache('cliente:', (c) => (c?.id === id ? { ...c, ...client } : undefined));
      },
    });
  },

  delete: async (id: number): Promise<void> => {
    if (esIdLocal(id)) {
      await cancelarOperacionLocal('cliente.crear', id);
      await parchearListas(null, id);
      await borrarCache(`cliente:${id}`);
      return;
    }
    await mutarOEncolar<void>('cliente.eliminar', { cliente_id: id }, {
      enLinea: async () => {
        await api.delete(`/cliente/${id}`);
      },
      optimista: async () => {
        await parchearListas(null, id);
        await borrarCache(`cliente:${id}`);
      },
    });
  },
};
