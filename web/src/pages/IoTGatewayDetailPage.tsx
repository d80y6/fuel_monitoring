import { FormEvent, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useParams } from 'react-router-dom';
import { api } from '../api/client';
import type { IoTCommandType } from '../lib/apiTypes';
import { Badge } from '../components/ui/badge';
import { Field, Select, Textarea } from '../components/ui/fields';

const COMMAND_TYPES: { value: IoTCommandType; label: string }[] = [
  { value: 'reboot', label: 'Reboot' },
  { value: 'status_probe', label: 'Status probe' },
  { value: 'pause_reporting', label: 'Pause reporting' },
  { value: 'resume_reporting', label: 'Resume reporting' },
  { value: 'set_interval', label: 'Set interval' },
  { value: 'recalibrate', label: 'Recalibrate' },
  { value: 'zero_tank', label: 'Zero tank' },
  { value: 'push_config', label: 'Push config' },
];

function CommandComposer({ gatewayId }: { gatewayId: string }) {
  const queryClient = useQueryClient();
  const [type, setType] = useState<IoTCommandType>('reboot');
  const [raw, setRaw] = useState('{}');
  const [error, setError] = useState<string | null>(null);

  const mut = useMutation({
    mutationFn: () => {
      let payload: Record<string, unknown>;
      try {
        payload = raw.trim() ? JSON.parse(raw) : {};
      } catch {
        throw new Error('Payload must be valid JSON');
      }
      return api.sendCommand(gatewayId, { command_type: type, payload });
    },
    onSuccess: () => {
      setRaw('{}');
      void queryClient.invalidateQueries({ queryKey: ['iot-gateway-commands', gatewayId] });
    },
    onError: (err) => setError(err instanceof Error ? err.message : 'Send failed'),
  });

  const submit = (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    mut.mutate();
  };

  return (
    <form onSubmit={submit} className="space-y-3 bg-white rounded-lg border border-slate-200 p-4">
      <h3 className="text-lg font-semibold text-slate-800">Send command</h3>
      <Field label="Command type" htmlFor="cmd-type">
        <Select id="cmd-type" value={type} onChange={(e) => setType(e.target.value as IoTCommandType)}>
          {COMMAND_TYPES.map((c) => (
            <option key={c.value} value={c.value}>{c.label}</option>
          ))}
        </Select>
      </Field>
      <Field label="Payload (JSON)" htmlFor="cmd-payload">
        <Textarea id="cmd-payload" value={raw} onChange={(e) => setRaw(e.target.value)} rows={4} spellCheck={false} placeholder={'{"interval_s": 5}'} />
      </Field>
      {error ? <p className="text-sm text-red-600">{error}</p> : null}
      <div className="flex justify-end">
        <button type="submit" disabled={mut.isPending} className="bg-brand text-white rounded px-3 py-2 text-sm font-medium disabled:opacity-50">
          Send
        </button>
      </div>
    </form>
  );
}

const STATUS_VARIANT: Record<string, 'success' | 'default' | 'warning'> = {
  acked: 'success',
  rejected: 'default',
  failed: 'default',
  sent: 'warning',
  pending: 'warning',
};

export default function IoTGatewayDetailPage() {
  const { id = '' } = useParams();
  const gateway = useQuery({ queryKey: ['iot-gateway', id], queryFn: () => api.getGateway(id) });
  const commands = useQuery({
    queryKey: ['iot-gateway-commands', id],
    queryFn: () => api.listCommands(id),
    refetchInterval: 5000,
  });

  if (gateway.isLoading) return <p className="text-sm text-slate-500">Loading…</p>;
  if (gateway.isError || !gateway.data) return <p className="text-sm text-rose-600">Failed to load gateway.</p>;
  const g = gateway.data;

  return (
    <div className="space-y-6">
      <div className="bg-white rounded-lg border border-slate-200 p-4">
        <div className="flex items-center justify-between">
          <h2 className="text-2xl font-semibold text-slate-800">{g.name}</h2>
          <Badge variant={g.connection_status === 'online' ? 'success' : 'default'}>{g.connection_status}</Badge>
        </div>
        <dl className="mt-3 grid grid-cols-2 gap-2 text-sm">
          <dt className="text-slate-500">MAC</dt><dd className="font-mono">{g.gateway_mac}</dd>
          <dt className="text-slate-500">Firmware</dt><dd>{g.firmware_version ?? '—'}</dd>
          <dt className="text-slate-500">Last seen</dt><dd>{g.last_seen ? new Date(g.last_seen).toLocaleString() : '—'}</dd>
          <dt className="text-slate-500">Linked tanks</dt><dd>{g.tank_ids.length} tank(s)</dd>
        </dl>
        {!g.is_active ? <p className="mt-3 text-sm text-amber-700">Not provisioned — link tanks via admin to enable commands.</p> : null}
      </div>

      {g.is_active ? <CommandComposer gatewayId={g.id} /> : null}

      <div className="bg-white rounded-lg border border-slate-200 p-4">
        <h3 className="text-lg font-semibold text-slate-800 mb-3">History</h3>
        {commands.isLoading ? <p className="text-sm text-slate-500">Loading…</p> : null}
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-slate-500">
            <tr>
              <th className="text-left px-4 py-2">Type</th>
              <th className="text-left px-4 py-2">Status</th>
              <th className="text-left px-4 py-2">Attempts</th>
              <th className="text-left px-4 py-2">Sent</th>
              <th className="text-left px-4 py-2">Ack</th>
            </tr>
          </thead>
          <tbody>
            {(commands.data ?? []).map((c) => (
              <tr key={c.id} className="border-t border-slate-100">
                <td className="px-4 py-2 font-medium text-slate-800">{c.command_type}</td>
                <td className="px-4 py-2">
                  <Badge variant={STATUS_VARIANT[c.status] ?? 'default'}>{c.status}</Badge>
                </td>
                <td className="px-4 py-2 text-slate-600">{c.attempts}/{c.max_attempts}</td>
                <td className="px-4 py-2 text-slate-600">{c.sent_at ? new Date(c.sent_at).toLocaleString() : '—'}</td>
                <td className="px-4 py-2 text-slate-600">
                  {c.ack_status ? `${c.ack_status}${c.ack_detail ? ` — ${c.ack_detail}` : ''}` : '—'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}