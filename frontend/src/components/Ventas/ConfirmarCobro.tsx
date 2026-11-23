import { createPortal } from 'react-dom';
import { Button, Modal } from '../ui';
import { formatCurrency } from '../../utils/format';
import type { VistaPreviaCobro } from '../../services/ventaService';

interface Props {
  resumen: VistaPreviaCobro;
  ocupado: boolean;
  error: string;
  onConfirmar: () => void;
  onCancelar: () => void;
}

export default function ConfirmarCobro({ resumen, ocupado, error, onConfirmar, onCancelar }: Props) {
  const excedente = Number(resumen.saldo_favor);
  const excesoGrande = excedente > Number(resumen.monto) / 2;
  return createPortal(
    <Modal
      open onClose={() => { if (!ocupado) onCancelar(); }}
      title="Revisar y confirmar cobro"
      footer={<>
        <Button variant="outline" disabled={ocupado} onClick={onCancelar}>Volver a revisar</Button>
        <Button loading={ocupado} onClick={onConfirmar}>Sí, registrar este cobro</Button>
      </>}
    >
      <div className="space-y-3 text-sm text-yeikar-neutral">
        <p className="font-bold">{resumen.cliente_nombre} · {resumen.cuenta_nombre}</p>
        <dl className="space-y-2 font-mono">
          <div><dt>Dinero recibido</dt><dd className="text-xl font-black">{formatCurrency(Number(resumen.monto), resumen.moneda_pago)}</dd></div>
          <div><dt>Se aplica a esta venta</dt><dd className="font-bold">{formatCurrency(Number(resumen.monto_aplicado), resumen.moneda_venta)}</dd></div>
        </dl>
        {excedente > 0 && (
          <p className={`rounded-xl border p-3 font-bold ${excesoGrande ? 'border-red-300 bg-red-50 text-red-800' : 'border-amber-300 bg-amber-50 text-amber-900'}`}>
            Quedarán {formatCurrency(excedente, resumen.moneda_pago)} a favor de {resumen.cliente_nombre}.
            {excesoGrande && <span className="mt-2 block">El excedente supera lo aplicado. Revisa si hay un cero de más.</span>}
          </p>
        )}
        <p>Verifica el monto, la cuenta y la moneda contra el comprobante antes de confirmar.</p>
        {error && <p role="alert" className="text-red-700">{error}</p>}
      </div>
    </Modal>,
    document.body,
  );
}
