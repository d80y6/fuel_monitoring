import type { ChangeEvent, FormEvent } from 'react';
import { useState } from 'react';
import { useMutation, useQueries, useQuery, useQueryClient } from '@tanstack/react-query';
import { useParams } from 'react-router-dom';
import { api } from '../api/client';
import type { IoTCommandType } from '../lib/apiTypes';
import { Badge } from '../components/ui/badge';
import { Field, Input, Select, Textarea } from '../components/ui/fields';
import { Skeleton } from '../components/ui/Skeleton';
import { ErrorCard } from '../components/ui/ErrorCard';

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

const NO_PAYLOAD_TYPES: IoTCommandType[] = ['reboot', 'status_probe', 'resume_reporting'];

/**
 * Validate the per-type fields against the backend contract (fmp/schemas/iot.py)
 * and build the payload object to send. Returns per-field errors so the composer
 * can render inline validation messages.
 */
function buildPayload(
  type: IoTCommandType,
  fields: Record<string, string>,
): { payload: Record<string, unknown>; errors: Record<string, string> } {
  switch (type) {
    case 'reboot':
    case 'status_probe':
    case 'resume_reporting':
      return { payload: {}, errors: {} };
    case 'pause_reporting': {
      const raw = fields.duration_s?.trim() ?? '';
      if (raw === '') return { payload: {}, errors: {} };
      const duration_s = Number(raw);
      if (!Number.isInteger(duration_s) || duration_s < 1) {
        return { payload: {}, errors: { duration_s: 'Duration must be a positive whole number of seconds' } };
      }
      return { payload: { duration_s }, errors: {} };
    }
    case 'set_interval': {
      const raw = fields.interval_s?.trim() ?? '';
      if (raw === '') return { payload: {}, errors: { interval_s: 'Interval is required' } };
      const interval_s = Number(raw);
      if (!Number.isInteger(interval_s) || interval_s < 1) {
        return { payload: {}, errors: { interval_s: 'Interval must be a positive whole number of seconds' } };
      }
      return { payload: { interval_s }, errors: {} };
    }
    case 'recalibrate': {
      const errors: Record<string, string> = {};
      const sensor = fields.sensor?.trim() ?? '';
      if (sensor === '') errors.sensor = 'Sensor is required';
      const pressureRaw = fields.reference_pressure_bar?.trim() ?? '';
      const reference_pressure_bar = Number(pressureRaw);
      if (pressureRaw === '' || !Number.isFinite(reference_pressure_bar)) {
        errors.reference_pressure_bar = 'Reference pressure must be a number';
      }
      if (Object.keys(errors).length > 0) return { payload: {}, errors };
      return { payload: { sensor, reference_pressure_bar }, errors: {} };
    }
    case 'zero_tank': {
      const errors: Record<string, string> = {};
      const tank_serial = fields.tank_serial?.trim() ?? '';
      if (tank_serial === '') errors.tank_serial = 'Tank serial is required';
      const levelRaw = fields.level_m?.trim() ?? '';
      const level_m = levelRaw === '' ? undefined : Number(levelRaw);
      if (levelRaw !== '' && !Number.isFinite(level_m)) errors.level_m = 'Level must be a number';
      if (Object.keys(errors).length > 0) return { payload: {}, errors };
      const payload: Record<string, unknown> = { tank_serial };
      if (level_m !== undefined) payload.level_m = level_m;
      return { payload, errors: {} };
    }
    case 'push_config': {
      const raw = fields.config_json?.trim() ?? '';
      if (raw === '') return { payload: {}, errors: { config_json: 'Config JSON is required' } };
      let parsed: unknown;
      try {
        parsed = JSON.parse(raw);
      } catch {
        return { payload: {}, errors: { config_json: 'Config must be valid JSON' } };
      }
      if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) {
        return { payload: {}, errors: { config_json: 'Config must be a JSON object' } };
      }
      return { payload: parsed as Record<string, unknown>, errors: {} };
    }
  }
  // Exhaustive: every command type is handled above.
  return { payload: {}, errors: {} };
}

function CommandComposer({ gatewayId }: { gatewayId: string }) {
  const queryClient = useQueryClient();
  const [type, setType] = useState<IoTCommandType>('reboot');
  const [fields, setFields] = useState<Record<string, string>>({});
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [sent, setSent] = useState<string | null>(null);

  const mut = useMutation({
    mutationFn: (payload: Record<string, unknown>) =>
      api.sendCommand(gatewayId, { command_type: type, payload }),
    onSuccess: (data) => {
      setFields({});
      setFieldErrors({});
      setSent(`Command sent — id ${data.command_id} (${data.status})`);
      void queryClient.invalidateQueries({ queryKey: ['iot-gateway-commands', gatewayId] });
    },
    onError: (err) => {
      setSent(null);
      setError(err instanceof Error ? err.message : 'Send failed');
    },
  });

  const setField = (name: string) => (e: ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) =>
    setFields((f) => ({ ...f, [name]: e.target.value }));

  const changeType = (e: ChangeEvent<HTMLSelectElement>) => {
    setType(e.target.value as IoTCommandType);
    setFields({});
    setFieldErrors({});
    setError(null);
    setSent(null);
  };

  const submit = (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setSent(null);
    setFieldErrors({});
    const { payload, errors } = buildPayload(type, fields);
    if (Object.keys(errors).length > 0) {
      setFieldErrors(errors);
      return;
    }
    mut.mutate(payload);
  };

  const fieldError = (name: string) =>
    fieldErrors[name] ? <p className="text-sm text-danger-fg">{fieldErrors[name]}</p> : null;

  return (
    <form onSubmit={submit} className="space-y-3 bg-surface rounded-lg border border-line p-4">
      <h3 className="text-lg font-semibold text-primary">Send command</h3>
      <Field label="Command type" htmlFor="cmd-type">
        <Select id="cmd-type" value={type} onChange={changeType}>
          {COMMAND_TYPES.map((c) => (
            <option key={c.value} value={c.value}>{c.label}</option>
          ))}
        </Select>
      </Field>

      {NO_PAYLOAD_TYPES.includes(type) ? (
        <p className="text-sm text-secondary">No payload required</p>
      ) : null}

      {type === 'pause_reporting' ? (
        <Field label="Duration (seconds)" htmlFor="cmd-duration-s">
          <Input id="cmd-duration-s" type="number" min={1} value={fields.duration_s ?? ''} onChange={setField('duration_s')} placeholder="seconds" />
          {fieldError('duration_s')}
        </Field>
      ) : null}

      {type === 'set_interval' ? (
        <Field label="Interval (seconds)" htmlFor="cmd-interval-s">
          <Input id="cmd-interval-s" type="number" min={1} value={fields.interval_s ?? ''} onChange={setField('interval_s')} placeholder="seconds" />
          {fieldError('interval_s')}
        </Field>
      ) : null}

      {type === 'recalibrate' ? (
        <>
          <Field label="Sensor" htmlFor="cmd-sensor">
            <Input id="cmd-sensor" value={fields.sensor ?? ''} onChange={setField('sensor')} placeholder="sensor serial" />
            {fieldError('sensor')}
          </Field>
          <Field label="Reference pressure (bar)" htmlFor="cmd-ref-pressure">
            <Input id="cmd-ref-pressure" type="number" step="any" value={fields.reference_pressure_bar ?? ''} onChange={setField('reference_pressure_bar')} placeholder="1.013" />
            {fieldError('reference_pressure_bar')}
          </Field>
        </>
      ) : null}

      {type === 'zero_tank' ? (
        <>
          <Field label="Tank serial" htmlFor="cmd-tank-serial">
            <Input id="cmd-tank-serial" value={fields.tank_serial ?? ''} onChange={setField('tank_serial')} placeholder="tank serial number" />
            {fieldError('tank_serial')}
          </Field>
          <Field label="Level (m)" htmlFor="cmd-level-m">
            <Input id="cmd-level-m" type="number" step="any" value={fields.level_m ?? ''} onChange={setField('level_m')} placeholder="optional — default 0" />
            {fieldError('level_m')}
          </Field>
        </>
      ) : null}

      {type === 'push_config' ? (
        <Field label="Config (JSON)" htmlFor="cmd-config-json">
          <Textarea id="cmd-config-json" value={fields.config_json ?? ''} onChange={setField('config_json')} rows={4} spellCheck={false} placeholder='{"poll_interval": 5}' />
          {fieldError('config_json')}
        </Field>
      ) : null}

      {error ? <p className="text-sm text-danger-fg">{error}</p> : null}
      {sent ? <p className="text-sm text-ok-fg">{sent}</p> : null}
      <div className="flex justify-end">
        <button type="submit" disabled={mut.isPending} className="bg-brand text-white rounded px-3 py-2 text-sm font-medium disabled:opacity-50">
          Send
        </button>
      </div>
    </form>
  );
}

function LinkedTanksPanel({ tankIds }: { tankIds: string[] }) {
  const tanks = useQueries({
    queries: tankIds.map((id) => ({
      queryKey: ['tank', id],
      queryFn: () => api.getTank(id),
      retry: false,
    })),
  });

  return (
    <div className="bg-surface rounded-lg border border-line p-4">
      <h3 className="text-lg font-semibold text-primary mb-3">Linked tanks</h3>
      {tankIds.length === 0 ? (
        <p className="text-sm text-secondary">No tanks linked. Link tanks via admin (PATCH tank_ids) to enable commands.</p>
      ) : (
        <ul className="divide-y divide-line">
          {tanks.map((q, i) => {
            const tankId = tankIds[i];
            const tank = q.data;
            return (
              <li key={tankId} className="py-2 flex items-center justify-between gap-2">
                <div className="min-w-0">
                  <p className="font-medium text-primary">{tank?.name ?? tankId}</p>
                  {tank ? <p className="text-xs text-muted font-mono truncate">{tank.site_id}</p> : null}
                </div>
                <Badge variant={tank?.connection_status === 'online' ? 'success' : 'default'}>
                  {q.isLoading ? 'loading…' : (tank?.connection_status ?? 'unknown')}
                </Badge>
              </li>
            );
          })}
        </ul>
      )}
    </div>
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
  const queryClient = useQueryClient();
  const gateway = useQuery({ queryKey: ['iot-gateway', id], queryFn: () => api.getGateway(id) });
  const commands = useQuery({
    queryKey: ['iot-gateway-commands', id],
    queryFn: () => api.listCommands(id),
    refetchInterval: 5000,
  });

  const toggleActive = useMutation({
    mutationFn: () => api.updateGateway(id, { is_active: !(gateway.data?.is_active ?? false) }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['iot-gateway', id] });
    },
  });

  if (gateway.isLoading) return <Skeleton className="h-72 w-full" />;
  if (gateway.isError || !gateway.data) return <ErrorCard message="Failed to load gateway." />;
  const g = gateway.data;

  return (
    <div className="space-y-6">
      <div className="bg-surface rounded-lg border border-line p-4">
        <div className="flex items-center justify-between">
          <h2 className="text-2xl font-semibold text-primary">{g.name}</h2>
          <div className="flex items-center gap-3">
            <Badge variant={g.connection_status === 'online' ? 'success' : 'default'}>{g.connection_status}</Badge>
            <label className="flex items-center gap-2 text-sm text-secondary">
              <input
                type="checkbox"
                checked={g.is_active}
                onChange={() => toggleActive.mutate()}
                disabled={toggleActive.isPending}
              />
              Active
            </label>
          </div>
        </div>
        <dl className="mt-3 grid grid-cols-2 gap-2 text-sm">
          <dt className="text-secondary">MAC</dt><dd className="font-mono">{g.gateway_mac}</dd>
          <dt className="text-secondary">Firmware</dt><dd>{g.firmware_version ?? '—'}</dd>
          <dt className="text-secondary">Last seen</dt><dd>{g.last_seen ? new Date(g.last_seen).toLocaleString() : '—'}</dd>
          <dt className="text-secondary">Tanks</dt><dd>{g.tank_ids.length} tank(s)</dd>
        </dl>
        {!g.is_active ? <p className="mt-3 text-sm text-warn-fg">Not provisioned — link tanks via admin to enable commands.</p> : null}
      </div>

      <LinkedTanksPanel tankIds={g.tank_ids} />

      {g.is_active ? <CommandComposer gatewayId={g.id} /> : null}

      <div className="bg-surface rounded-lg border border-line p-4">
        <h3 className="text-lg font-semibold text-primary mb-3">History</h3>
        {commands.isLoading ? <p className="text-sm text-secondary">Loading…</p> : null}
        <table className="w-full text-sm">
          <thead className="bg-inset text-secondary">
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
              <tr key={c.id} className="border-t border-line">
                <td className="px-4 py-2 font-medium text-primary">{c.command_type}</td>
                <td className="px-4 py-2">
                  <Badge variant={STATUS_VARIANT[c.status] ?? 'default'}>{c.status}</Badge>
                </td>
                <td className="px-4 py-2 text-secondary">{c.attempts}/{c.max_attempts}</td>
                <td className="px-4 py-2 text-secondary">{c.sent_at ? new Date(c.sent_at).toLocaleString() : '—'}</td>
                <td className="px-4 py-2 text-secondary">
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