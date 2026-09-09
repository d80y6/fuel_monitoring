import { FormEvent, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ApiError } from '../api/http';
import { api } from '../api/client';
import type { NotificationGatewayRead } from '../lib/apiTypes';
import { Badge } from '../components/ui/badge';
import { Modal } from '../components/ui/Modal';
import { Field, Input, Select, Textarea } from '../components/ui/fields';
import { ConfirmDialog } from '../components/ui/confirm';

export default function GatewaysPage() {
  const gateways = useQuery({ queryKey: ['gateways'], queryFn: () => api.listGateways() });
  const [creating, setCreating] = useState(false);
  const [editing, setEditing] = useState<NotificationGatewayRead | null>(null);
  const [deleting, setDeleting] = useState<NotificationGatewayRead | null>(null);

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-2xl font-semibold text-slate-800">Gateways</h2>
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
              <th className="text-left px-4 py-2">Type</th>
              <th className="text-left px-4 py-2">Active</th>
              <th className="text-left px-4 py-2">Priority</th>
              <th className="text-right px-4 py-2"></th>
            </tr>
          </thead>
          <tbody>
            {(gateways.data ?? []).map((g) => (
              <tr key={g.id} className="border-t border-slate-100">
                <td className="px-4 py-2 font-medium text-slate-800">{g.name}</td>
                <td className="px-4 py-2 text-slate-600">{g.type}</td>
                <td className="px-4 py-2">
                  <Badge variant={g.is_active ? 'success' : 'default'}>{g.is_active ? 'Active' : 'Inactive'}</Badge>
                </td>
                <td className="px-4 py-2 text-slate-600">{g.priority}</td>
                <td className="px-4 py-2 text-right space-x-3">
                  <button onClick={() => setEditing(g)} className="text-sm text-slate-600 hover:text-brand-dark">
                    Edit
                  </button>
                  <button onClick={() => setDeleting(g)} className="text-sm text-rose-600">
                    Delete
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {creating ? <GatewayDialog onClose={() => setCreating(false)} /> : null}
      {editing ? <GatewayDialog initial={editing} onClose={() => setEditing(null)} /> : null}
      {deleting ? <DeleteGateway gateway={deleting} onCancel={() => setDeleting(null)} /> : null}
    </div>
  );
}

function GatewayDialog({ initial, onClose }: { initial?: NotificationGatewayRead; onClose: () => void }) {
  const queryClient = useQueryClient();
  const [form, setForm] = useState({
    name: initial?.name ?? '',
    type: initial?.type ?? 'smpp',
    is_active: initial?.is_active ?? true,
    priority: String(initial?.priority ?? 10),
    config_json: JSON.stringify(initial?.config_json ?? {}, null, 2),
  });
  const [error, setError] = useState<string | null>(null);

  const set = (k: keyof typeof form) => (e: { target: { value: string } }) =>
    setForm((f) => ({ ...f, [k]: e.target.value }));

  const mut = useMutation({
    mutationFn: () => {
      let config_json: Record<string, unknown>;
      try {
        config_json = JSON.parse(form.config_json);
      } catch {
        throw new Error('Invalid JSON');
      }
      return initial
        ? api.updateGateway(initial.id, {
            is_active: form.is_active,
            priority: Number(form.priority),
            config_json,
          })
        : api.createGateway({
            name: form.name,
            type: form.type as 'smpp' | 'whatsapp',
            config_json,
            is_active: form.is_active,
            priority: Number(form.priority),
          });
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['gateways'] });
      onClose();
    },
    onError: (err) =>
      setError(
        err instanceof ApiError ? err.detail
        : err instanceof Error && err.message === 'Invalid JSON' ? 'Config must be valid JSON'
        : 'Save failed',
      ),
  });

  const submit = (e: FormEvent) => {
    e.preventDefault();
    mut.mutate();
  };

  return (
    <Modal title={initial ? 'Edit gateway' : 'New gateway'} onClose={onClose} wide>
      <form onSubmit={submit} className="space-y-3">
        <Field label="Name" htmlFor="gateway-name">
          <Input id="gateway-name" autoFocus value={form.name} onChange={set('name')} required placeholder="SMTP relay" disabled={!!initial} />
          {initial ? <span className="text-xs text-slate-400">Not editable after creation.</span> : null}
        </Field>
        <Field label="Type" htmlFor="gateway-type">
          <Select id="gateway-type" value={form.type} onChange={set('type')} disabled={!!initial}>
            <option value="smpp">SMPP</option>
            <option value="whatsapp">WhatsApp</option>
          </Select>
          {initial ? <span className="text-xs text-slate-400">Not editable after creation.</span> : null}
        </Field>
        <Field label="Priority" htmlFor="gateway-priority">
          <Input
            id="gateway-priority"
            type="number"
            min={1}
            value={form.priority}
            onChange={set('priority')}
            required
          />
        </Field>
        <Field label="Config" htmlFor="gateway-config">
          <Textarea id="gateway-config" value={form.config_json} onChange={set('config_json')} rows={6} spellCheck={false} />
        </Field>
        <label className="flex items-center gap-2 text-sm text-slate-700">
          <input
            type="checkbox"
            checked={form.is_active}
            onChange={(e) => setForm((f) => ({ ...f, is_active: e.target.checked }))}
          />
          Active
        </label>
        {error ? <p className="text-sm text-red-600">{error}</p> : null}
        <div className="flex justify-end gap-2 pt-2">
          <button type="button" onClick={onClose} className="px-3 py-2 text-sm text-slate-600">
            Cancel
          </button>
          <button type="submit" disabled={mut.isPending} className="bg-brand text-white rounded px-3 py-2 text-sm font-medium disabled:opacity-50">
            {initial ? 'Save' : 'Create'}
          </button>
        </div>
      </form>
    </Modal>
  );
}

function DeleteGateway({ gateway, onCancel }: { gateway: NotificationGatewayRead; onCancel: () => void }) {
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);

  const del = useMutation({
    mutationFn: () => api.deleteGateway(gateway.id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['gateways'] });
      onCancel();
    },
    onError: (err) => setError(err instanceof ApiError ? err.detail : 'Delete failed'),
  });

  return (
    <ConfirmDialog
      title="Delete gateway"
      message={`Delete "${gateway.name}"?${error ? ` (${error})` : ''}`}
      confirmLabel="Delete"
      onCancel={onCancel}
      onConfirm={() => del.mutate()}
    />
  );
}