import { useEffect, useState } from 'react';
import { Activity, ChevronDown, Clock3, Filter, ShieldCheck, UserRound } from 'lucide-react';
import api from '../services/api';
import { Badge, Card, PageHeader, Spinner } from '../components/ui';

interface AuditEvent {
  id: number;
  actor_user_id?: number | null;
  actor_name?: string | null;
  action: string;
  entity_type: string;
  entity_id: string;
  changed_fields?: string[] | null;
  before_data?: Record<string, unknown> | null;
  after_data?: Record<string, unknown> | null;
  created_at: string;
}

const actionLabels: Record<string, string> = {
  CREATE: 'Creó',
  UPDATE: 'Editó',
  STATE_CHANGE: 'Cambió estado',
  DELETE: 'Eliminó',
  ASSIGN: 'Asignó',
  LOCATION_UPDATE: 'Reportó ubicación',
  SYSTEM_CREATE: 'Creación automática',
};

const entityLabels: Record<string, string> = {
  cliente: 'cliente',
  cotizacion: 'cotización',
  pedido: 'pedido',
  venta: 'venta',
  gasto: 'gasto',
  envio: 'envío',
  orden_produccion: 'orden de producción',
  pago: 'pago',
};

export default function Auditoria() {
  const [events, setEvents] = useState<AuditEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [action, setAction] = useState('');
  const [entityType, setEntityType] = useState('');

  useEffect(() => {
    const loadEvents = async () => {
      setLoading(true);
      try {
        const response = await api.get<AuditEvent[]>('/auditoria/', {
          params: {
            ...(action ? { action } : {}),
            ...(entityType ? { entity_type: entityType } : {}),
            limite: 200,
          },
        });
        setEvents(response.data);
      } finally {
        setLoading(false);
      }
    };
    loadEvents();
  }, [action, entityType]);

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Control y confianza"
        title="Actividad del sistema"
        subtitle="Una bitácora precisa de las decisiones y cambios que ocurren en YEIKAR."
        icon={<ShieldCheck className="h-5 w-5" />}
      />

      <div className="grid gap-4 md:grid-cols-[1fr_auto]">
        <Card className="flex items-center gap-3 bg-yeikar-secondary text-white" bodyClassName="flex items-center gap-4 p-5">
          <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-yeikar-primary text-yeikar-neutral shadow-gold"><Activity className="h-5 w-5" /></div>
          <div>
            <p className="font-headline text-sm font-bold">Trazabilidad activa</p>
            <p className="mt-1 text-xs text-white/50">Cada evento conserva actor, fecha y recurso afectado.</p>
          </div>
        </Card>
        <div className="flex flex-wrap items-center gap-2 rounded-2xl border border-yeikar-secondary-light/10 bg-white p-4 shadow-card">
          <Filter className="h-4 w-4 text-yeikar-primary-dark" />
          <label className="relative">
            <span className="sr-only">Filtrar acción</span>
            <select value={action} onChange={(event) => setAction(event.target.value)} className="input h-10 min-w-[150px] appearance-none py-2 pr-8 text-xs">
              <option value="">Todas las acciones</option>
              {Object.keys(actionLabels).map((key) => <option key={key} value={key}>{actionLabels[key]}</option>)}
            </select>
            <ChevronDown className="pointer-events-none absolute right-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-yeikar-neutral/40" />
          </label>
          <label className="relative">
            <span className="sr-only">Filtrar recurso</span>
            <select value={entityType} onChange={(event) => setEntityType(event.target.value)} className="input h-10 min-w-[150px] appearance-none py-2 pr-8 text-xs">
              <option value="">Todos los módulos</option>
              {Object.keys(entityLabels).map((key) => <option key={key} value={key}>{entityLabels[key]}</option>)}
            </select>
            <ChevronDown className="pointer-events-none absolute right-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-yeikar-neutral/40" />
          </label>
        </div>
      </div>

      <Card title="Registro reciente" subtitle={`${events.length} eventos disponibles`}>
        {loading ? <Spinner label="Cargando actividad..." /> : events.length === 0 ? (
          <div className="rounded-xl border border-dashed border-yeikar-secondary-light/20 bg-yeikar-tertiary/50 p-10 text-center text-sm text-yeikar-neutral/50">Todavía no hay actividad registrada con estos filtros.</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[760px] text-left">
              <thead><tr><th className="table-th">Actor</th><th className="table-th">Acción</th><th className="table-th">Recurso</th><th className="table-th">Cambios</th><th className="table-th">Momento</th></tr></thead>
              <tbody>
                {events.map((event) => (
                  <tr key={event.id} className="transition-colors hover:bg-yeikar-tertiary/50">
                    <td className="table-td"><div className="flex items-center gap-2.5"><span className="flex h-8 w-8 items-center justify-center rounded-lg bg-yeikar-secondary text-yeikar-primary"><UserRound className="h-3.5 w-3.5" /></span><span className="font-semibold text-yeikar-secondary">{event.actor_name || 'Sistema'}</span></div></td>
                    <td className="table-td"><Badge tone={event.action === 'DELETE' ? 'red' : event.action === 'LOCATION_UPDATE' ? 'blue' : 'gold'} dot>{actionLabels[event.action] || event.action}</Badge></td>
                    <td className="table-td"><span className="font-semibold">{entityLabels[event.entity_type] || event.entity_type}</span><span className="ml-2 font-mono text-xs text-yeikar-neutral/45">#{event.entity_id}</span></td>
                    <td className="table-td text-xs text-yeikar-neutral/55">{event.changed_fields?.length ? event.changed_fields.join(', ') : 'Registro creado'}</td>
                    <td className="table-td"><span className="flex items-center gap-1.5 whitespace-nowrap font-mono text-xs text-yeikar-neutral/55"><Clock3 className="h-3.5 w-3.5 text-yeikar-primary-dark" />{new Date(event.created_at).toLocaleString('es-CO')}</span></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}
