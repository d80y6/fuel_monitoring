import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ApiError } from '../api/http';
import { notificationApi } from '../api/admin';
import { api } from '../api/client';
import type { NotificationRule, Site } from '../lib/apiTypes';
import { Modal } from '../components/ui/Modal';
import { ConfirmDialog } from '../components/ui/confirm';
import { ErrorCard } from '../components/ui/ErrorCard';
import { EmptyState } from '../components/ui/EmptyState';
import { Skeleton } from '../components/ui/Skeleton';
import { Badge } from '../components/ui/badge';
import { Field, Input, Select, Textarea } from '../components/ui/fields';
import { PageHeader } from '../components/ui/PageHeader';

const CHANNELS = ['sms', 'smpp', 'whatsapp', 'email', 'webhook'] as const;

type RuleForm = {
  name: string;
  min_level: 'WARNING' | 'CRITICAL';
  channel: string;
  targets: string;
  template: string;
  site_id: string;
  enabled: boolean;
};

const EMPTY: RuleForm = {
  name: '',
  min_level: 'WARNING',
  channel: 'sms',
  targets: '',
  template: '',
  site_id: '',
  enabled: true,
};

/**
 * Alarm notification rules.
 *
 * A rule matches raised alarms at or above `min_level`, optionally limited to
 * one site, and sends `targets` through `channel`. The server resolves the
 * channel to the tenant's configured gateway and records every delivery — so a
 * rule with no configured channel reports failed sends rather than pretending to
 * have notified anyone.
 */
export default function NotificationRulesPage() {
  const qc = useQueryClient();
  const [modal, setModal] = useState<'create' | 'edit' | null>(null);
  const [editing, setEditing] = useState<NotificationRule | null>(null);
  const [form, setForm] = useState<RuleForm>(EMPTY);
  const [error, setError] = useState<string | null>(null);
  const [deleting, setDeleting] = useState<NotificationRule | null>(null);

  const { data: rules = [], isLoading, isError, refetch } = useQuery({
    queryKey: ['notification-rules'],
    queryFn: () => notificationApi.listRules(),
  });

  const { data: sites = [] } = useQuery({
    queryKey: ['sites'],
    queryFn: () => api.listSites(),
  });

  const saveMutation = useMutation({
    mutationFn: () => {
      const payload = {
        name: form.name,
        min_level: form.min_level,
        channel: form.channel,
        targets: form.targets
          .split(/[\n,]/)
          .map((t) => t.trim())
          .filter(Boolean),
        template: form.template || null,
        site_id: form.site_id || null,
        enabled: form.enabled,
      };
      return editing
        ? notificationApi.updateRule(editing.id, payload)
        : notificationApi.createRule(payload);
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['notification-rules'] });
      setModal(null);
      setError(null);
    },
    onError: (err) => setError(err instanceof ApiError ? err.detail : 'Could not save the rule.'),
  });

  const toggleMutation = useMutation({
    mutationFn: (rule: NotificationRule) =>
      notificationApi.updateRule(rule.id, { enabled: !rule.enabled }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['notification-rules'] }),
    onError: (err) => setError(err instanceof ApiError ? err.detail : 'Could not update the rule.'),
  });

  const deleteMutation = useMutation({
    mutationFn: () => notificationApi.deleteRule(deleting!.id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['notification-rules'] });
      setDeleting(null);
    },
    onError: (err) => setError(err instanceof ApiError ? err.detail : 'Could not delete the rule.'),
  });

  const openCreate = () => {
    setEditing(null);
    setError(null);
    setForm(EMPTY);
    setModal('create');
  };

  const openEdit = (rule: NotificationRule) => {
    setEditing(rule);
    setError(null);
    setForm({
      name: rule.name,
      min_level: rule.min_level,
      channel: rule.channel,
      targets: rule.targets.join('\n'),
      template: rule.template ?? '',
      site_id: rule.site_id ?? '',
      enabled: rule.enabled,
    });
    setModal('edit');
  };

  const siteName = (id: string | null) =>
    id ? (sites.find((s) => s.id === id)?.name ?? 'Unknown site') : 'All sites';

  const canSubmit = form.name.trim() !== '' && form.targets.trim() !== '';

  return (
    <div className="space-y-4">
      <PageHeader
        title="Alarm notification rules"
        subtitle="Who is told, over which channel, when an alarm fires"
        actions={
          <button
            type="button"
            onClick={openCreate}
            className="rounded bg-brand px-4 py-2 text-sm font-medium text-white"
          >
            New Rule
          </button>
        }
      />

      {isError ? <ErrorCard message="Could not load notification rules." onRetry={() => refetch()} /> : null}

      {isLoading ? (
        <div className="space-y-2">
          <Skeleton className="h-8 w-full" />
          <Skeleton className="h-8 w-full" />
        </div>
      ) : rules.length === 0 ? (
        <EmptyState
          title="No notification rules"
          hint="Alarms are recorded and shown in the alarm center, but nobody is notified until a rule exists."
        />
      ) : (
        <table className="w-full border-collapse text-sm">
          <thead>
            <tr className="border-b border-line text-left text-secondary">
              <th scope="col" className="px-3 py-2">Rule</th>
              <th scope="col" className="px-3 py-2">Minimum level</th>
              <th scope="col" className="px-3 py-2">Channel</th>
              <th scope="col" className="px-3 py-2">Targets</th>
              <th scope="col" className="px-3 py-2">Scope</th>
              <th scope="col" className="px-3 py-2">Status</th>
              <th scope="col" className="px-3 py-2">Actions</th>
            </tr>
          </thead>
          <tbody>
            {rules.map((rule) => (
              <tr key={rule.id} className="border-b border-line/60 align-top hover:bg-inset">
                <td className="px-3 py-2 font-medium">
                  {rule.name}
                  {rule.company_id === null ? (
                    <span className="block text-xs text-muted">Platform-wide</span>
                  ) : null}
                </td>
                <td className="px-3 py-2">
                  <Badge variant={rule.min_level === 'CRITICAL' ? 'danger' : 'warning'}>
                    {rule.min_level}
                  </Badge>
                </td>
                <td className="px-3 py-2 text-secondary">{rule.channel}</td>
                <td className="px-3 py-2 text-secondary">
                  <ul className="space-y-0.5">
                    {rule.targets.map((t) => (
                      <li key={t} className="font-mono text-xs">{t}</li>
                    ))}
                  </ul>
                </td>
                <td className="px-3 py-2 text-secondary">{siteName(rule.site_id)}</td>
                <td className="px-3 py-2">
                  <Badge variant={rule.enabled ? 'success' : 'default'}>
                    {rule.enabled ? 'Enabled' : 'Disabled'}
                  </Badge>
                </td>
                <td className="space-x-3 px-3 py-2">
                  <button
                    type="button"
                    className="text-brand-dark hover:underline"
                    onClick={() => openEdit(rule)}
                  >
                    Edit
                  </button>
                  <button
                    type="button"
                    className="text-brand-dark hover:underline"
                    onClick={() => toggleMutation.mutate(rule)}
                  >
                    {rule.enabled ? 'Disable' : 'Enable'}
                  </button>
                  <button
                    type="button"
                    className="text-rose-600 hover:underline"
                    onClick={() => setDeleting(rule)}
                  >
                    Delete
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {error && !modal ? <p className="text-sm text-rose-600">{error}</p> : null}

      {modal ? (
        <Modal title={editing ? `Edit ${editing.name}` : 'New notification rule'} onClose={() => setModal(null)}>
          <div className="space-y-3">
            <Field label="Name" htmlFor="rule-name">
              <Input
                id="rule-name"
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
              />
            </Field>
            <div className="grid grid-cols-2 gap-3">
              <Field label="Minimum level" htmlFor="rule-level">
                <Select
                  id="rule-level"
                  value={form.min_level}
                  onChange={(e) => setForm({ ...form, min_level: e.target.value as RuleForm['min_level'] })}
                >
                  <option value="WARNING">WARNING and above</option>
                  <option value="CRITICAL">CRITICAL only</option>
                </Select>
              </Field>
              <Field label="Channel" htmlFor="rule-channel">
                <Select
                  id="rule-channel"
                  value={form.channel}
                  onChange={(e) => setForm({ ...form, channel: e.target.value })}
                >
                  {CHANNELS.map((c) => (
                    <option key={c} value={c}>
                      {c}
                    </option>
                  ))}
                </Select>
              </Field>
            </div>
            <Field label="Site scope" htmlFor="rule-site">
              <Select
                id="rule-site"
                value={form.site_id}
                onChange={(e) => setForm({ ...form, site_id: e.target.value })}
              >
                <option value="">All sites in this organization</option>
                {sites.map((s: Site) => (
                  <option key={s.id} value={s.id}>
                    {s.name}
                  </option>
                ))}
              </Select>
            </Field>
            <Field label="Targets (one per line)" htmlFor="rule-targets">
              <Textarea
                id="rule-targets"
                value={form.targets}
                placeholder={'+250788000000\nops@example.com'}
                onChange={(e) => setForm({ ...form, targets: e.target.value })}
              />
            </Field>
            <Field label="Message template (optional)" htmlFor="rule-template">
              <Textarea
                id="rule-template"
                value={form.template}
                placeholder="[{level}] {tank} ({site}) — {type}: {message}"
                onChange={(e) => setForm({ ...form, template: e.target.value })}
              />
            </Field>
            <label className="flex items-center gap-2 text-sm text-secondary">
              <input
                type="checkbox"
                checked={form.enabled}
                onChange={(e) => setForm({ ...form, enabled: e.target.checked })}
              />
              Enabled
            </label>
          </div>
          {error ? <p className="mt-2 text-sm text-rose-600">{error}</p> : null}
          <div className="flex justify-end gap-2 pt-4">
            <button type="button" onClick={() => setModal(null)} className="px-3 py-2 text-sm text-secondary">
              Cancel
            </button>
            <button
              type="button"
              onClick={() => saveMutation.mutate()}
              disabled={!canSubmit || saveMutation.isPending}
              className="rounded bg-brand px-3 py-2 text-sm font-medium text-white disabled:opacity-50"
            >
              {saveMutation.isPending ? 'Saving…' : editing ? 'Save' : 'Create'}
            </button>
          </div>
        </Modal>
      ) : null}

      {deleting ? (
        <ConfirmDialog
          title="Delete rule"
          message={`Stop notifying the targets in "${deleting.name}"? Alarms are still recorded.`}
          confirmLabel="Delete"
          onCancel={() => setDeleting(null)}
          onConfirm={() => deleteMutation.mutate()}
        />
      ) : null}
    </div>
  );
}