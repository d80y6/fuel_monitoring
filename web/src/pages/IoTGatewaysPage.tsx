import { FormEvent, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { ApiError } from '../api/http';
import { api } from '../api/client';
import { Badge } from '../components/ui/badge';
import { Modal } from '../components/ui/Modal';
import { Field, Input } from '../components/ui/fields';

function GatewayDialog({ onClose }: { onClose: () => void }) {
  const queryClient = useQueryClient();
  const [form, setForm] = useState({ gateway_mac: '', name: '', firmware_version: '' });
  const [error, setError] = useState<string | null>(null);

  const mut = useMutation({
    mutationFn: () =>
      api.createGateway({
        gateway_mac: form.gateway_mac,
        name: form.name || undefined,
        firmware_version: form.firmware_version || undefined,
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['iot-gateways'] });
      onClose();
    },
    onError: (err) => setError(err instanceof ApiError ? err.detail : 'Create failed'),
  });

  const submit = (e: FormEvent) => {
    e.preventDefault();
    mut.mutate();
  };

  return (
    <Modal title="New IoT gateway" onClose={onClose}>
      <form onSubmit={submit} className="space-y-3">
        <Field label="Gateway MAC" htmlFor="gw-mac">
          <Input id="gw-mac" autoFocus value={form.gateway_mac} onChange={(e) => setForm((f) => ({ ...f, gateway_mac: e.target.value }))} required placeholder="AA:BB:CC:DD:EE:01" />
        </Field>
        <Field label="Name" htmlFor="gw-name">
          <Input id="gw-name" value={form.name} onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))} placeholder="East Gate" />
        </Field>
        <Field label="Firmware version" htmlFor="gw-fw">
          <Input id="gw-fw" value={form.firmware_version} onChange={(e) => setForm((f) => ({ ...f, firmware_version: e.target.value }))} placeholder="2.1.0" />
        </Field>
        {error ? <p className="text-sm text-red-600">{error}</p> : null}
        <div className="flex justify-end gap-2 pt-2">
          <button type="button" onClick={onClose} className="px-3 py-2 text-sm text-slate-600">Cancel</button>
          <button type="submit" disabled={mut.isPending} className="bg-brand text-white rounded px-3 py-2 text-sm font-medium disabled:opacity-50">Create</button>
        </div>
      </form>
    </Modal>
  );
}

export default function IoTGatewaysPage() {
  const gateways = useQuery({ queryKey: ['iot-gateways'], queryFn: () => api.listGateways() });
  const [creating, setCreating] = useState(false);
  const navigate = useNavigate();

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-2xl font-semibold text-slate-800">IoT Gateways</h2>
        <button onClick={() => setCreating(true)} className="bg-brand text-white rounded px-3 py-2 text-sm font-medium">
          New gateway
        </button>
      </div>
      {gateways.isLoading ? <p className="text-sm text-slate-500">Loading…</p> : null}
      {gateways.isError ? <p className="text-sm text-rose-600">Failed to load gateways.</p> : null}
      <div className="bg-white rounded-lg border border-slate-200 overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-slate-500">
            <tr>
              <th className="text-left px-4 py-2">Name</th>
              <th className="text-left px-4 py-2">MAC</th>
              <th className="text-left px-4 py-2">Status</th>
              <th className="text-left px-4 py-2">Last seen</th>
              <th className="text-left px-4 py-2">Firmware</th>
              <th className="text-left px-4 py-2">Tanks</th>
              <th className="text-left px-4 py-2">Provisioned</th>
            </tr>
          </thead>
          <tbody>
            {(gateways.data ?? []).map((g) => (
              <tr key={g.id} className="border-t border-slate-100 cursor-pointer hover:bg-slate-50" onClick={() => navigate(`/admin/iot-gateways/${g.id}`)}>
                <td className="px-4 py-2 font-medium text-slate-800">{g.name}</td>
                <td className="px-4 py-2 text-slate-600 font-mono">{g.gateway_mac}</td>
                <td className="px-4 py-2">
                  <Badge variant={g.connection_status === 'online' ? 'success' : 'default'}>{g.connection_status}</Badge>
                </td>
                <td className="px-4 py-2 text-slate-600">{g.last_seen ? new Date(g.last_seen).toLocaleString() : '—'}</td>
                <td className="px-4 py-2 text-slate-600">{g.firmware_version ?? '—'}</td>
                <td className="px-4 py-2 text-slate-600">{g.tank_ids.length}</td>
                <td className="px-4 py-2">
                  {g.is_active ? <Badge variant="success">provisioned</Badge> : <Badge variant="warning">unprovisioned</Badge>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {creating ? <GatewayDialog onClose={() => setCreating(false)} /> : null}
    </div>
  );
}