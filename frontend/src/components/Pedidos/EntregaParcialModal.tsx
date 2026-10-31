import { useEffect, useMemo, useState } from 'react';
import { PackageCheck, Truck } from 'lucide-react';

import { useToast } from '../../context/ToastContext';
import {
  envioService,
  type PendienteEntrega,
  type PendienteEntregaItem,
} from '../../services/envioService';
import type { Order } from '../../services/pedidoService';
import { Button, EmptyState, Field, Input, Modal, Spinner } from '../ui';
import { hoyVE } from '../../utils/fechas';

interface EntregaParcialModalProps {
  open: boolean;
  pedido: Order | null;
  onClose: () => void;
  onCreated: () => void;
}

function claveItem(item: PendienteEntregaItem): string {
  return `${item.detalle_pedido_id}:${item.orden_produccion_id ?? 'sin-orden'}`;
}

export default function EntregaParcialModal({
  open,
  pedido,
  onClose,
  onCreated,
}: EntregaParcialModalProps) {
  const toast = useToast();
  const [data, setData] = useState<PendienteEntrega | null>(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [seleccion, setSeleccion] = useState<Record<string, number>>({});
  const [direccion, setDireccion] = useState('');
  const [guia, setGuia] = useState('');
  const [observaciones, setObservaciones] = useState('');
  const [fechaEntrega, setFechaEntrega] = useState('');
  const [entregarAhora, setEntregarAhora] = useState(true);

  useEffect(() => {
    if (!open || !pedido) return;
    let activo = true;
    setLoading(true);
    setError('');
    setData(null);
    setSeleccion({});
    setDireccion(pedido.cliente?.direccion || '');
    setGuia('');
    setObservaciones('');
    setFechaEntrega(hoyVE());
    setEntregarAhora(true);

    envioService.getPendientes(pedido.id)
      .then((res) => {
        if (!activo) return;
        setData(res);
        const inicial: Record<string, number> = {};
        for (const item of res.items) {
          if (item.cantidad_lista > 0) inicial[claveItem(item)] = item.cantidad_lista;
        }
        setSeleccion(inicial);
      })
      .catch((err) => {
        if (!activo) return;
        setError(err.response?.data?.detail || 'No se pudo cargar lo pendiente del pedido.');
      })
      .finally(() => {
        if (activo) setLoading(false);
      });

    return () => {
      activo = false;
    };
  }, [open, pedido]);

  const items = data?.items ?? [];
  const listos = useMemo(() => items.filter((item) => item.cantidad_lista > 0), [items]);
  const hayReservado = useMemo(
    () => items.some((item) => item.cantidad_reservada > 0),
    [items],
  );
  const totalSeleccionado = useMemo(
    () => Object.values(seleccion).reduce((total, cantidad) => total + (Number(cantidad) || 0), 0),
    [seleccion],
  );

  const alternar = (item: PendienteEntregaItem) => {
    const clave = claveItem(item);
    setSeleccion((prev) => {
      const copia = { ...prev };
      if (copia[clave] !== undefined) delete copia[clave];
      else copia[clave] = item.cantidad_lista;
      return copia;
    });
  };

  const cambiarCantidad = (item: PendienteEntregaItem, valor: string) => {
    const clave = claveItem(item);
    const cantidad = Number(valor);
    setSeleccion((prev) => ({ ...prev, [clave]: Number.isFinite(cantidad) ? cantidad : 0 }));
  };

  const guardar = async () => {
    if (!pedido || !data) return;
    const detalles = items
      .filter((item) => (seleccion[claveItem(item)] ?? 0) > 0)
      .map((item) => ({
        detalle_pedido_id: item.detalle_pedido_id,
        orden_produccion_id: item.orden_produccion_id ?? null,
        cantidad: Number(seleccion[claveItem(item)]),
      }));

    if (detalles.length === 0) {
      toast.error('Selecciona al menos un ítem listo para entregar.');
      return;
    }
    const excedido = items.find((item) => {
      const cantidad = seleccion[claveItem(item)] ?? 0;
      return cantidad > item.cantidad_lista + 0.0001;
    });
    if (excedido) {
      toast.error(`De "${excedido.descripcion}" solo hay ${excedido.cantidad_lista} disponible(s).`);
      return;
    }

    setSaving(true);
    try {
      await envioService.create({
        pedido_id: pedido.id,
        estado: entregarAhora ? 'ENTREGADO' : 'PREPARADO',
        direccion_entrega: direccion.trim() || null,
        guia_despacho: guia.trim() || null,
        observaciones: observaciones.trim() || (items.length > 1 ? 'Entrega parcial' : null),
        ...(entregarAhora && fechaEntrega
          ? { fecha_entrega: `${fechaEntrega}T12:00:00` }
          : {}),
        detalles,
      });
      toast.success(
        entregarAhora
          ? 'Entrega registrada. El pedido se cerrará cuando salga todo.'
          : 'Despacho preparado. Asígnalo en Despachos cuando salga.',
      );
      onCreated();
      onClose();
    } catch (err: any) {
      toast.error(err.response?.data?.detail || 'No se pudo registrar la entrega.');
    } finally {
      setSaving(false);
    }
  };

  const titulo = pedido ? `Entregar pedido #${pedido.id}` : 'Registrar entrega';

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={titulo}
      subtitle="Puedes llevar solo lo que ya está terminado; el resto sigue en producción."
      size="2xl"
      footer={
        <>
          <Button variant="outline" onClick={onClose} disabled={saving}>
            Cancelar
          </Button>
          <Button
            onClick={guardar}
            loading={saving}
            disabled={loading || !!error || listos.length === 0}
            icon={entregarAhora ? <PackageCheck className="h-4 w-4" /> : <Truck className="h-4 w-4" />}
          >
            {entregarAhora ? 'Registrar entrega' : 'Preparar despacho'}
          </Button>
        </>
      }
    >
      {loading ? (
        <Spinner label="Buscando lo que está listo..." />
      ) : error ? (
        <div className="rounded-xl border border-red-200 bg-red-50 p-3 text-sm text-red-700">
          {error}
        </div>
      ) : listos.length === 0 ? (
        <EmptyState
          compact
          title={hayReservado ? 'Lo pendiente ya está en un despacho' : 'Todavía no hay nada listo'}
          description={
            hayReservado
              ? 'Las piezas que faltan están reservadas en un envío PREPARADO/EN_TRANSITO. Termínalo o gestionalo desde Despachos.'
              : 'Termina al menos una orden de producción (o usa un ítem de reventa) para registrar una entrega.'
          }
        />
      ) : (
        <div className="space-y-4">
          <div className="rounded-xl border border-yeikar-primary/20 bg-yeikar-primary/5 px-3 py-2 text-xs text-yeikar-neutral/75">
            El pedido está <strong>{data?.estado}</strong>. Los ítems en producción se pueden
            seleccionar cuando su orden esté <strong>FINALIZADA</strong>.
          </div>

          <div className="space-y-2">
            {items.map((item) => {
              const clave = claveItem(item);
              const seleccionado = seleccion[clave] !== undefined;
              const listo = item.cantidad_lista > 0;
              return (
                <div
                  key={clave}
                  className={`rounded-xl border p-3 transition-colors ${
                    listo
                      ? seleccionado
                        ? 'border-yeikar-primary/40 bg-yeikar-primary/5'
                        : 'border-yeikar-secondary-light/20 bg-white'
                      : 'border-yeikar-secondary-light/10 bg-yeikar-tertiary/20 opacity-70'
                  }`}
                >
                  <div className="flex items-start gap-3">
                    <input
                      type="checkbox"
                      checked={seleccionado}
                      disabled={!listo}
                      onChange={() => alternar(item)}
                      className="mt-1 h-4 w-4 rounded border-yeikar-secondary-light/30 text-yeikar-primary focus:ring-yeikar-primary"
                      aria-label={`Entregar ${item.descripcion}`}
                    />
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <span className="font-bold text-sm text-yeikar-secondary">
                          {item.descripcion}
                        </span>
                        {listo ? (
                          <span className="rounded-full bg-green-50 px-2 py-0.5 text-[10px] font-black uppercase tracking-wide text-green-700 border border-green-200">
                            Listo: {item.cantidad_lista}
                          </span>
                        ) : (
                          <span className="rounded-full bg-amber-50 px-2 py-0.5 text-[10px] font-black uppercase tracking-wide text-amber-700 border border-amber-200">
                            {item.estado_produccion || 'En producción'}
                          </span>
                        )}
                      </div>
                      <div className="mt-1 flex flex-wrap gap-x-3 gap-y-0.5 text-[11px] font-mono text-yeikar-neutral/55">
                        <span>Total: {item.cantidad_total}</span>
                        <span>Entregado: {item.cantidad_entregada}</span>
                        {item.cantidad_reservada > 0 && (
                          <span>En otro despacho: {item.cantidad_reservada}</span>
                        )}
                        <span>Pendiente: {item.cantidad_pendiente}</span>
                      </div>
                    </div>
                    <div className="w-24 shrink-0">
                      <Input
                        type="number"
                        min={0}
                        max={item.cantidad_lista}
                        step="0.01"
                        value={seleccionado ? seleccion[clave] : ''}
                        disabled={!listo || !seleccionado}
                        onChange={(event) => cambiarCantidad(item, event.target.value)}
                        aria-label={`Cantidad a entregar de ${item.descripcion}`}
                        className="text-right font-mono"
                      />
                    </div>
                  </div>
                </div>
              );
            })}
          </div>

          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Dirección de entrega" className="sm:col-span-2">
              <Input
                value={direccion}
                onChange={(event) => setDireccion(event.target.value)}
                placeholder="Dirección a donde se lleva esta tanda"
              />
            </Field>
            {entregarAhora && (
              <Field label="Fecha de entrega">
                <Input
                  type="date"
                  value={fechaEntrega}
                  max={hoyVE()}
                  onChange={(event) => setFechaEntrega(event.target.value)}
                />
              </Field>
            )}
            <Field label="Guía de despacho (opcional)">
              <Input
                value={guia}
                onChange={(event) => setGuia(event.target.value)}
                placeholder="Nro. de guía"
              />
            </Field>
            <Field label="Novedades (opcional)" className="sm:col-span-2">
              <Input
                value={observaciones}
                onChange={(event) => setObservaciones(event.target.value)}
                placeholder="Ej.: se lleva solo la sala"
              />
            </Field>
          </div>

          <label className="flex items-start gap-3 rounded-xl border border-yeikar-secondary-light/20 bg-yeikar-tertiary/20 p-3 cursor-pointer">
            <input
              type="checkbox"
              checked={entregarAhora}
              onChange={(event) => setEntregarAhora(event.target.checked)}
              className="mt-0.5 h-4 w-4 rounded border-yeikar-secondary-light/30 text-yeikar-primary focus:ring-yeikar-primary"
            />
            <span>
              <span className="block text-sm font-bold text-yeikar-secondary">
                Ya se entregó al cliente (retiro en taller)
              </span>
              <span className="block text-xs text-yeikar-neutral/55">
                Si lo desmarcas, queda como despacho <strong>PREPARADO</strong> para asignarle
                chofer y guía en Despachos.
              </span>
            </span>
          </label>

          <p className="text-right text-xs font-mono text-yeikar-neutral/55">
            Total a entregar: <strong>{totalSeleccionado}</strong>
          </p>
        </div>
      )}
    </Modal>
  );
}
