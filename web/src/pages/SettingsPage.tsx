import { FormEvent, useState } from 'react';
import { ApiError } from '../api/http';
import { api } from '../api/client';
import { Field, Input } from '../components/ui/fields';
import { PageHeader } from '../components/ui/PageHeader';

export default function SettingsPage() {
  const [current, setCurrent] = useState('');
  const [next, setNext] = useState('');
  const [confirm, setConfirm] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setDone(false);
    if (next !== confirm) {
      setError('New passwords do not match');
      return;
    }
    setBusy(true);
    try {
      await api.changePassword(current, next);
      setDone(true);
      setCurrent('');
      setNext('');
      setConfirm('');
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'Password change failed');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div>
      <PageHeader title="Settings" subtitle="Account & security" />
      <div className="max-w-md bg-surface rounded-lg border border-line p-4">
        <h3 className="font-semibold text-primary mb-3">Change password</h3>
        <form onSubmit={submit} className="space-y-3">
          <Field label="Current password" htmlFor="cf-current">
            <Input id="cf-current" type="password" value={current} onChange={(e) => setCurrent(e.target.value)} autoComplete="current-password" required />
          </Field>
          <Field label="New password" htmlFor="cf-new">
            <Input id="cf-new" type="password" value={next} onChange={(e) => setNext(e.target.value)} autoComplete="new-password" required />
          </Field>
          <Field label="Confirm new password" htmlFor="cf-confirm">
            <Input id="cf-confirm" type="password" value={confirm} onChange={(e) => setConfirm(e.target.value)} autoComplete="new-password" required />
          </Field>
          {error ? <p role="alert" className="text-sm text-danger-fg">{error}</p> : null}
          {done ? <p className="text-sm text-ok-fg">Password updated.</p> : null}
          <div className="flex justify-end">
            <button type="submit" disabled={busy} className="bg-brand text-white rounded px-3 py-2 text-sm font-medium disabled:opacity-50">
              {busy ? 'Saving…' : 'Update password'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}