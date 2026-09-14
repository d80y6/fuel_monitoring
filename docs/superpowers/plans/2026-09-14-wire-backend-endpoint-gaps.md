# Plan: Wire backend endpoint gaps into the frontend

Date: 2026-09-14
Spec: `docs/superpowers/specs/2026-09-14-wire-backend-endpoint-gaps-design.md`

## Goal

Close the five frontend/backend integration gaps identified in the endpoint audit, plus the
`listTotalizers` foot-gun, per the approved design spec:

1. **Change password** — new `/settings` page (all authenticated users).
2. **Tank CSV export** — "Export CSV" button in the TankDetail header (authenticated users).
3. **Batch dispatch** — "Dispatch now" button on upload summary when codes are pending
   dispatch; add required auth to the backend endpoint (admin/company_admin).
4. **Strapping table editing** — inline manager-only editor (admin/manager).
5. **Consumption analytics** — `ConsumptionCard` chart on TankDetail.
6. **`listTotalizers` foot-gun** — make `dispenserId` required, matching the backend.

## Architecture

- All network access goes through `web/src/api/*` modules; UI reads api via TanStack Query,
  Zustand auth store, and existing component kits (`ui/fields`, `ui/PageHeader`, `ui/EmptyState`).
- Backend changes are minimal (auth dependency on the dispatch endpoint) plus one integration
  test assertion.
- All mutations invalidate their TanStack query keys so the UI refetches.
- CSRF-free; all requests carry the Bearer JWT via `http.ts` / `getBlob`.

## Tech Stack

- Frontend: React 18 + Vite, TypeScript, TanStack Query, Zustand, ECharts via `echarts-for-react`.
- Backend: FastAPI, SQLAlchemy async, Redis denylist, nameko'd `PrivilegedUser` dependency.
- Testing: vitest + Jest DOM + Testing Library (web), pytest (platform).

## Shared how-to for each task

- Frontend tests: write test first, run `npx vitest run <file>`, confirm RED, implement, run
  again, confirm GREEN, then `npx tsc --noEmit` from `web/`.
- Platform tests: `.venv/bin/pytest fmp/tests/unit -q --import-mode=importlib` from `platform/`,
  and `fmp/tests/integration/test_api_surface.py` (skips when DB/Redis unreachable).
- Commit after each task with a focused message.

---

## Task 1 — API layer: types + methods + `listTotalizers` fix

### Files
- `web/src/api/http.ts` — add `getBlob`
- `web/src/lib/apiTypes.ts` — add consumption types
- `web/src/api/client.ts` — add `changePassword`, `exportTankCsv`, `getConsumption`
- `web/src/api/dispensing.ts` — add `redispatchBatch`
- `web/src/api/monitoring.ts` — add `saveStrapping`; make `listTotalizers` require `dispenserId`
- `web/src/pages/Totalizers.tsx` — pass `dispenser!` to `listTotalizers`

### Step 1.1 — `http.ts`: add `getBlob`
```ts
export async function getBlob(path: string, init: RequestInit = {}): Promise<Blob> {
  const token = tokenProvider();
  const headers = new Headers(init.headers);
  if (token) headers.set('Authorization', `Bearer ${token}`);
  const response = await fetch(path, { ...init, headers });
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new ApiError(response.status, typeof data.detail === 'string' ? data.detail : 'Download failed');
  }
  return response.blob();
}
```
(Export it from the file; it must sit next to `tokenProvider`.)

### Step 1.2 — `apiTypes.ts`: consumption types
```ts
export interface ConsumptionPoint {
  date: string;
  liters: number;
}
export interface ConsumptionForecast {
  method: 'sma';
  window_days: number;
  liters_per_day: number;
}
export interface ConsumptionAnalytics {
  tank_id: string;
  days: number;
  method: 'sma';
  forecast: ConsumptionForecast;
  series: ConsumptionPoint[];
}
```

### Step 1.3 — `client.ts`: new methods
```ts
async changePassword(currentPassword: string, newPassword: string): Promise<{ status: string }> {
  const res = await request(`${API_BASE}/auth/change-password`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
  });
  return res.json();
},

async exportTankCsv(tankId: string, start: string, end: string): Promise<Blob> {
  const params = new URLSearchParams({ start, end });
  return getBlob(`${API_BASE}/tanks/${tankId}/export?${params.toString()}`);
},

async getConsumption(tankId: string, days = 30, windowDays = 7): Promise<ConsumptionAnalytics> {
  return this.get(`/analytics/consumption/${tankId}?days=${days}&window_days=${windowDays}`);
},
```
(Update imports: add `getBlob` from `./http`, and the new types.)

### Step 1.4 — `dispensing.ts`: redispatchBatch
```ts
export interface DispatchStatus {
  message: string;
  batch_id: string;
  status: 'ok';
}
// in api object:
async redispatchBatch(batchId: string): Promise<DispatchStatus> {
  return this.post(`/dispensing/upload/${batchId}/dispatch`, {});
},
```

### Step 1.5 — `monitoring.ts`: saveStrapping + listTotalizers signature
```ts
async saveStrapping(
  tankId: string,
  payload: { calibration_data: StrappingPoint[]; interpolation_method: 'linear' | 'cubic_spline' },
): Promise<StrappingTable> {
  return this.put(`/tanks/${tankId}/strapping`, payload);
},

async listTotalizers(dispenserId: string, rangeStart?: string, rangeEnd?: string): Promise<TotalizerReading[]> {
  const params = new URLSearchParams({ dispenser_id: dispenserId });
  if (rangeStart) params.set('start', rangeStart);
  if (rangeEnd) params.set('end', rangeEnd);
  return this.get(`/analytics/totalizers/drift?${params.toString()}`);
},
```

### Step 1.6 — `Totalizers.tsx`: pass required id
In the query for drift totalizers, replace `api.listTotalizers(dispenser, ...)` with
`api.listTotalizers(dispenser!, ...)` (the query is gated by `enabled: Boolean(dispenser)`).

### Step 1.7 — Totalizers test update
In `web/src/pages/Totalizers.test.tsx`, the `api.listTotalizers` mock already returns `[]`;
no change needed. Run `npx vitest run Totalizers` and `npx tsc --noEmit` to confirm no
signature mismatch anywhere else.

---

## Task 2 — Settings page (change password)

### Files
- `web/src/components/ui/icons.tsx` — add `settings` icon
- `web/src/pages/SettingsPage.tsx` — new (default export)
- `web/src/pages/SettingsPage.test.tsx` — new
- `web/src/router.tsx` — add `/settings`
- `web/src/components/layout/Sidebar.tsx` — add "Account" group with Settings link

### Step 2.1 — icons.tsx
Add `'settings'` to the `IconName` union and a `settings` entry in `PATHS`
(a gear: circle + spokes — reuse the lucide `settings` 24x24 path, stroke-based renders
already match the existing icon set).

### Step 2.2 — SettingsPage.tsx
```tsx
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
```

### Step 2.3 — SettingsPage.test.tsx
```tsx
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import SettingsPage from './SettingsPage';

vi.mock('../api/client', () => ({
  api: { changePassword: vi.fn() },
}));
import { api } from '../api/client';
import { ApiError } from '../api/http';

describe('SettingsPage', () => {
  beforeEach(() => { vi.mocked(api.changePassword).mockReset(); });

  it('submits current and new password and confirms', async () => {
    vi.mocked(api.changePassword).mockResolvedValue({ status: 'ok' } as never);
    render(<SettingsPage />);
    await userEvent.type(screen.getByLabelText(/current password/i), 'Old1!aa');
    await userEvent.type(screen.getByLabelText(/new password/i), 'New2!bb');
    await userEvent.type(screen.getByLabelText(/confirm new password/i), 'New2!bb');
    await userEvent.click(screen.getByRole('button', { name: /update password/i }));
    expect(await screen.findByText('Password updated.')).toBeInTheDocument();
    expect(vi.mocked(api.changePassword)).toHaveBeenCalledWith('Old1!aa', 'New2!bb');
  });

  it('blocks submit when confirmation does not match', async () => {
    render(<SettingsPage />);
    await userEvent.type(screen.getByLabelText(/current password/i), 'Old1!aa');
    await userEvent.type(screen.getByLabelText(/new password/i), 'New2!bb');
    await userEvent.type(screen.getByLabelText(/confirm new password/i), 'Different!1');
    await userEvent.click(screen.getByRole('button', { name: /update password/i }));
    expect(await screen.findByRole('alert')).toHaveTextContent('New passwords do not match');
    expect(vi.mocked(api.changePassword)).not.toHaveBeenCalled();
  });

  it('shows backend validation errors verbatim', async () => {
    vi.mocked(api.changePassword).mockRejectedValue(
      new ApiError(422, 'must include at least 3 of: lowercase, uppercase, digit, symbol'));
    render(<SettingsPage />);
    await userEvent.type(screen.getByLabelText(/current password/i), 'Old1!aa');
    await userEvent.type(screen.getByLabelText(/new password/i), 'short');
    await userEvent.type(screen.getByLabelText(/confirm new password/i), 'short');
    await userEvent.click(screen.getByRole('button', { name: /update password/i }));
    expect(await screen.findByRole('alert')).toHaveTextContent('must include at least 3 of');
  });
});
```

### Step 2.4 — router.tsx
Add under the `RequireAuth` tree (outside `RequireManage`):
```tsx
<Route path="/settings" element={<SettingsPage />} />
```
with `import SettingsPage from './pages/SettingsPage';` (lazy import if router uses lazy).

### Step 2.5 — Sidebar.tsx
Add an "Account" group (labels use the same dictionary style as existing groups):
```tsx
{ navGroups.map(...) } // existing groups
```
render a new account group after the existing ones:
```tsx
<div>
  <div className="px-3 text-xs text-secondary">Account</div>
  <NavItem to="/settings" icon="settings" label={t('settings')} />
</div>
```
Add the `'settings'` translation key to the label dictionary (same shape as existing entries).

Run `npx vitest run SettingsPage`, `npx tsc --noEmit`, then the full `npx vitest run`.
Commit as `feat(web): settings page for changing password`.

---

## Task 3 — TankDetail CSV export

### Files
- `web/src/components/ui/icons.tsx` — add `download` icon
- `web/src/pages/TankDetail.tsx` — export button + handler
- `web/src/pages/TankDetail.test.tsx` — add export test, mock `URL.createObjectURL`

### Step 3.1 — icons.tsx
Add `'download'` to `IconName` and `PATHS` (lucide `download` path).

### Step 3.2 — TankDetail.tsx
Add state + handler beside the existing window batch state:
```tsx
const [exporting, setExporting] = useState(false);
const [exportError, setExportError] = useState<string | null>(null);

const handleExport = async () => {
  const hours = WINDOWS[window];
  const end = new Date();
  const start = new Date(end.getTime() - hours * 60 * 60 * 1000);
  setExporting(true);
  setExportError(null);
  try {
    const blob = await api.exportTankCsv(tank.id, start.toISOString(), end.toISOString());
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `tank-${tank.id}-${start.toISOString().slice(0, 10)}-to-${end.toISOString().slice(0, 10)}.csv`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  } catch {
    setExportError('Export failed');
  } finally {
    setExporting(false);
  }
};
```
In the telemetry card header row, next to the window pills:
```tsx
<button type="button" onClick={handleExport} disabled={exporting}
        className="flex items-center gap-1.5 text-xs bg-inset px-2 py-1 rounded">
  <Icon name="download" className="w-3.5 h-3.5" />
  {exporting ? 'Exporting…' : 'Export CSV'}
</button>
{exportError ? <p className="text-xs text-danger-fg">{exportError}</p> : null}
```
(Match the row layout and `Icon` usage already present in that header.)

### Step 3.3 — TankDetail.test.tsx
- Add `exportTankCsv: vi.fn()` to the `../api/client` mock.
- Import `userEvent`.
- New test:
```tsx
it('exports the current window as CSV', async () => {
  const create = vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:url');
  const revoke = vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => {});
  const click = vi.fn();
  HTMLAnchorElement.prototype.click = click;
  vi.mocked(api.exportTankCsv).mockResolvedValue(new Blob([]) as never);
  renderPage();
  await screen.findByRole('heading', { level: 3, name: /Alpha · Telemetry/ });
  await userEvent.click(screen.getByRole('button', { name: /export csv/i }));
  expect(vi.mocked(api.exportTankCsv)).toHaveBeenCalledTimes(1);
  const [id, start, end] = vi.mocked(api.exportTankCsv).mock.calls[0];
  expect(id).toBe('t1');
  expect(new Date(start).getTime()).toBeLessThanOrEqual(new Date(end).getTime());
  expect(start).toMatch(/T.*Z$/);
  expect(click).toHaveBeenCalled();
  create.mockRestore();
  revoke.mockRestore();
  (HTMLAnchorElement.prototype.click as unknown) = undefined;
});
```
Run `npx vitest run TankDetail`, `npx tsc --noEmit`.
Commit as `feat(web): export tank telemetry range as CSV`.

---

## Task 4 — UploadCard batch dispatch

### Files
- `web/src/components/dispensing/UploadCard.tsx` — dispatch mutation + button
- `web/src/components/dispensing/UploadCard.test.tsx` — dispatch test

### Step 4.1 — UploadCard.tsx
Import `useMutation` + `ApiError`; in `UploadCard`:
```tsx
const [dispatchMsg, setDispatchMsg] = useState<string | null>(null);
const dispatchMutation = useMutation({
  mutationFn: (batchId: string) => api.redispatchBatch(batchId),
  onSuccess: (d) => setDispatchMsg(d.message),
  onError: (err) => setDispatchMsg(err instanceof ApiError ? err.detail : 'Dispatch failed'),
});
```
Pass to the summary: `outcome`, `onDispatch={(batchId) => { setDispatchMsg(null); dispatchMutation.mutate(batchId); }}`,
`dispatching={dispatchMutation.isPending}`, `dispatchMsg={dispatchMsg}`.

Extend `UploadSummary` props and card body when `pending_dispatch.length > 0`:
```tsx
{pending_dispatch?.length ? (
  <div className="space-y-1">
    <p className="text-xs text-secondary">
      {pending_dispatch.length} {pending_dispatch.length === 1 ? 'code' : 'codes'} pending dispatch.
    </p>
    <button type="button" onClick={() => onDispatch(outcome.result.batch_id)} disabled={dispatching}
            className="text-xs bg-inset px-2 py-1 rounded">
      {dispatching ? 'Dispatching…' : 'Dispatch now'}
    </button>
    {dispatchMsg ? <p className="text-xs text-primary">{dispatchMsg}</p> : null}
  </div>
) : null}
```
(`type="button"` is required — the summary lives inside the upload form.)

### Step 4.2 — UploadCard.test.tsx
- Add `redispatchBatch: vi.fn()` to the `../api/client` mock.
- New test:
```tsx
it('dispatches pending codes and shows the returned message', async () => {
  vi.mocked(api.uploadQuotaSheet).mockResolvedValue(outcome as never);
  vi.mocked(api.redispatchBatch).mockResolvedValue({
    message: 'Codes not persisted by design; re-upload to re-send.',
    batch_id: 'b1',
    status: 'ok',
  } as never);
  renderCard();
  await screen.findByText('Acme');
  await userEvent.selectOptions(screen.getByLabelText(/company/i), 'c1');
  await userEvent.upload(screen.getByLabelText(/file/i), new File(['x'], 'sheet.xlsx'));
  await userEvent.click(screen.getByRole('button', { name: /^upload$/i }));
  await screen.findByText('2 codes pending dispatch.');
  await userEvent.click(screen.getByRole('button', { name: /dispatch now/i }));
  await screen.findByText('Codes not persisted by design; re-upload to re-send.');
  expect(vi.mocked(api.redispatchBatch)).toHaveBeenCalledWith('b1');
});
```
(Adjust the pending-code count to the fixture's `outcome.result.pending_dispatch.length`.)
Run `npx vitest run UploadCard`, `npx tsc --noEmit`.
Commit as `feat(web): dispatch pending upload codes from the upload card`.

---

## Task 5 — Backend: require auth on the dispatch endpoint + integration test

### Files
- `platform/fmp/api/v1/dispensing.py` — add `PrivilegedUser` dependency
- `platform/fmp/tests/integration/test_api_surface.py` — unauth dispatch assertion

### Step 5.1 — dispensing.py
```python
from fmp.api.deps import CurrentUser, PrivilegedUser, SessionDep
```
and change the handler signature:
```python
@router.post("/upload/{batch_id}/dispatch")
async def redispatch_batch_codes(
    batch_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _user: PrivilegedUser = None,
) -> dict:
```

### Step 5.2 — test_api_surface.py
Add next to the existing unauth checks:
```python
# dispatch requires an authenticated admin/company_admin
r = await client.post(f"/api/v1/dispensing/upload/{uuid.uuid4()}/dispatch")
assert r.status_code in (401, 403)
```

### Step 5.3 — verify
`.venv/bin/pytest fmp/tests/unit -q --import-mode=importlib` (expect the same 147 passed / 4 pre-existing DB errors),
then `.venv/bin/pytest fmp/tests/integration/test_api_surface.py -q --import-mode=importlib`
(skips when DB/Redis unreachable; when reachable, the new assertion must pass).
Commit as `fix(api): require admin access to redispatch batch codes`.

---

## Task 6 — StrappingCard inline editor (manager-only)

### Files
- `web/src/components/tanks/StrappingCard.tsx` — edit mode
- `web/src/components/tanks/StrappingCard.test.tsx` — new editor tests

### Step 6.1 — Component
```tsx
import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ApiError } from '../../api/http';
import { api } from '../../api/client';
import { useAuthStore } from '../../store/auth';
import { canManage } from '../../lib/roles';
import type { StrappingPoint } from '../../lib/apiTypes';

interface StrappingDraft {
  height: number;
  volume: number;
}

export default function StrappingCard({ tankId }: { tankId: string }) {
  const user = useAuthStore((s) => s.user);
  const qc = useQueryClient();
  const [editing, setEditing] = useState(false);
  const [rows, setRows] = useState<StrappingDraft[]>([]);
  const [method, setMethod] = useState<'linear' | 'cubic_spline'>('linear');
  const [error, setError] = useState<string | null>(null);

  const strapping = useQuery({
    queryKey: ['strapping', tankId],
    queryFn: () => api.getStrapping(tankId),
  });

  const save = useMutation({
    mutationFn: (payload: { calibration_data: StrappingDraft[]; interpolation_method: 'linear' | 'cubic_spline' }) =>
      api.saveStrapping(tankId, payload),
    onSuccess: () => {
      setEditing(false);
      qc.invalidateQueries({ queryKey: ['strapping', tankId] });
    },
    onError: (err) => setError(err instanceof ApiError ? err.detail : 'Save failed'),
  });

  const startEdit = () => {
    setRows((strapping.data?.calibration_data ?? []).map((p) => ({ height: p.height, volume: p.volume })));
    setMethod(strapping.data?.interpolation_method ?? 'linear');
    setError(null);
    setEditing(true);
  };

  const setRow = (i: number, field: keyof StrappingDraft, value: string) => {
    setRows((prev) => prev.map((r, idx) => (idx === i ? { ...r, [field]: Number(value) } : r)));
  };
  const addRow = () => setRows((prev) => [...prev, { height: 0, volume: 0 }]);
  const removeRow = (i: number) => setRows((prev) => prev.filter((_, idx) => idx !== i));

  const submit = () => {
    setError(null);
    if (rows.length < 2) { setError('Strapping table requires at least 2 points.'); return; }
    for (let i = 1; i < rows.length; i++) {
      if (rows[i - 1].height >= rows[i].height) { setError('Heights must be strictly ascending.'); return; }
    }
    save.mutate({ calibration_data: rows, interpolation_method: method });
  };

  if (strapping.isLoading) {
    return <p className="text-sm text-secondary">Loading strapping table…</p>;
  }

  const s = strapping.data;
  const canEdit = canManage(user?.role);

  return (
    <div>
      <div className="flex items-center justify-between mb-2">
        <h3 className="font-semibold text-primary">Strapping table</h3>
        {canEdit && !editing ? (
          <button type="button" onClick={startEdit} className="text-xs bg-inset px-2 py-1 rounded">Edit</button>
        ) : null}
      </div>

      {editing ? (
        <div className="space-y-2">
          <div className="flex items-center gap-2">
            <label htmlFor="strap-method" className="text-xs text-secondary">Interpolation</label>
            <select id="strap-method" value={method} onChange={(e) => setMethod(e.target.value as 'linear' | 'cubic_spline')}
                    className="border border-line-strong rounded px-2 py-1 text-sm">
              <option value="linear">linear</option>
              <option value="cubic_spline">cubic_spline</option>
            </select>
          </div>
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs text-secondary">
                <th className="py-1">Height (m)</th>
                <th className="py-1">Volume (L)</th>
                <th className="py-1" aria-hidden="true"></th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row, i) => (
                <tr key={i}>
                  <td className="pr-2">
                    <input aria-label={`height ${i}`} type="number" step="any"
                           value={row.height} onChange={(e) => setRow(i, 'height', e.target.value)}
                           className="w-full border border-line-strong rounded px-2 py-1" />
                  </td>
                  <td className="pr-2">
                    <input aria-label={`volume ${i}`} type="number" step="any"
                           value={row.volume} onChange={(e) => setRow(i, 'volume', e.target.value)}
                           className="w-full border border-line-strong rounded px-2 py-1" />
                  </td>
                  <td>
                    <button type="button" aria-label={`remove row ${i}`} onClick={() => removeRow(i)}
                            className="text-xs text-danger-fg">Remove</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="flex items-center gap-2">
            <button type="button" onClick={addRow} className="text-xs bg-inset px-2 py-1 rounded">Add row</button>
            <button type="button" onClick={submit} disabled={save.isPending}
                    className="text-xs bg-brand text-white px-2 py-1 rounded disabled:opacity-50">Save</button>
            <button type="button" onClick={() => setEditing(false)} className="text-xs bg-inset px-2 py-1 rounded">Cancel</button>
          </div>
          {error ? <p role="alert" className="text-sm text-danger-fg">{error}</p> : null}
          {save.isError ? <p role="alert" className="text-sm text-danger-fg">Save failed</p> : null}
        </div>
      ) : s ? (
        <>
          <p className="text-xs text-secondary mb-2">Interpolation: {s.interpolation_method}</p>
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs text-secondary">
                <th className="py-1">Height (m)</th>
                <th className="py-1">Volume (L)</th>
              </tr>
            </thead>
            <tbody>
              {s.calibration_data.map((pt) => (
                <tr key={pt.height}>
                  <td className="py-1">{pt.height}</td>
                  <td className="py-1">{pt.volume.toLocaleString('en-US')}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      ) : (
        <p className="text-sm text-secondary">No strapping table for this tank.</p>
      )}
    </div>
  );
}
```
(`strapping.error` invalidates data; the "No strapping table" read-out is derived from the Query
result like before — keep the previous error path. Managers can enter edit mode from an empty
state to create the first table, which the PUT upsert accepts.)

### Step 6.2 — StrappingCard.test.tsx
```tsx
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { beforeEach, describe, expect, it, vi } from 'vitest';

let role: string | null = 'admin';
vi.mock('../../store/auth', () => ({
  useAuthStore: (sel: (s: { user: { role: string } | null }) => unknown) =>
    sel({ user: role ? { role } : null }),
}));
vi.mock('../../api/client', () => ({
  api: { getStrapping: vi.fn(), saveStrapping: vi.fn() },
}));

import { api } from '../../api/client';
import StrappingCard from './StrappingCard';
import type { StrappingTable } from '../../lib/apiTypes';

const table: StrappingTable = {
  id: 'st1',
  tank_id: 't1',
  interpolation_method: 'linear',
  created_at: '2026-01-01T00:00:00Z',
  calibration_data: [
    { height: 0, volume: 0 },
    { height: 1, volume: 1000 },
    { height: 2, volume: 2200 },
  ],
};

function renderCard() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <StrappingCard tankId="t1" />
    </QueryClientProvider>,
  );
}

describe('StrappingCard', () => {
  beforeEach(() => {
    role = 'admin';
    vi.mocked(api.getStrapping).mockReset();
    vi.mocked(api.saveStrapping).mockReset();
    vi.mocked(api.getStrapping).mockResolvedValue(table as never);
    vi.mocked(api.saveStrapping).mockResolvedValue(table as never);
  });

  it('renders the strapping table read-only', async () => {
    renderCard();
    expect(await screen.findByText('Interpolation: linear')).toBeInTheDocument();
    expect(screen.getByText('2,200')).toBeInTheDocument();
  });

  it('shows Edit for managers only', async () => {
    renderCard();
    expect(await screen.findByRole('button', { name: /^edit$/i })).toBeInTheDocument();
  });

  it('hides Edit for non-managers', async () => {
    role = 'user';
    renderCard();
    await screen.findByText('Interpolation: linear');
    expect(screen.queryByRole('button', { name: /^edit$/i })).toBeNull();
  });

  it('saves edited rows and interpolation method', async () => {
    renderCard();
    await screen.findByRole('button', { name: /^edit$/i });
    await userEvent.click(screen.getByRole('button', { name: /^edit$/i }));
    await userEvent.selectOptions(screen.getByLabelText(/interpolation/i), 'cubic_spline');
    await userEvent.click(screen.getByRole('button', { name: /^save$/i }));
    await waitFor(() => expect(api.saveStrapping).toHaveBeenCalledTimes(1));
    const [tankId, payload] = vi.mocked(api.saveStrapping).mock.calls[0];
    expect(tankId).toBe('t1');
    expect(payload.interpolation_method).toBe('cubic_spline');
    expect(payload.calibration_data).toHaveLength(3);
  });

  it('blocks save with fewer than two rows', async () => {
    renderCard();
    await screen.findByRole('button', { name: /^edit$/i });
    await userEvent.click(screen.getByRole('button', { name: /^edit$/i }));
    const removes = screen.getAllByRole('button', { name: /remove row \d+/i });
    await userEvent.click(removes[0]);
    await userEvent.click(removes[0]);
    await userEvent.click(screen.getByRole('button', { name: /^save$/i }));
    expect(await screen.findByRole('alert')).toHaveTextContent('at least 2 points');
    expect(api.saveStrapping).not.toHaveBeenCalled();
  });

  it('blocks save when heights are not ascending', async () => {
    renderCard();
    await screen.findByRole('button', { name: /^edit$/i });
    await userEvent.click(screen.getByRole('button', { name: /^edit$/i }));
    const heights = screen.getAllByLabelText(/^height \d+$/i);
    await userEvent.clear(heights[2]);
    await userEvent.type(heights[2], '1');
    await userEvent.click(screen.getByRole('button', { name: /^save$/i }));
    expect(await screen.findByRole('alert')).toHaveTextContent('strictly ascending');
    expect(api.saveStrapping).not.toHaveBeenCalled();
  });
});
```
Run `npx vitest run StrappingCard`, `npx tsc --noEmit`.
Commit as `feat(web): inline strapping table editor for managers`.

---

## Task 7 — ConsumptionCard on TankDetail

### Files
- `web/src/components/tanks/ConsumptionCard.tsx` — new
- `web/src/components/tanks/ConsumptionCard.test.tsx` — new
- `web/src/pages/TankDetail.tsx` — render card
- `web/src/pages/TankDetail.test.tsx` — mock the new card, add presence test

### Step 7.1 — ConsumptionCard.tsx
```tsx
import { useQuery } from '@tanstack/react-query';
import ReactECharts from 'echarts-for-react';
import { api } from '../../api/client';
import { EmptyState } from '../ui/EmptyState';
import { chartColors } from '../../lib/chartColors';
import { chartThemeName } from '../../lib/chartTheme';
import { useTheme } from '../../hooks/useTheme';

interface ConsumptionCardProps {
  tankId: string;
  days?: number;
}

export default function ConsumptionCard({ tankId, days = 30 }: ConsumptionCardProps) {
  const { resolvedScheme } = useTheme();
  const c = chartColors[resolvedScheme];
  const q = useQuery({
    queryKey: ['consumption', tankId, days],
    queryFn: () => api.getConsumption(tankId, days),
  });

  if (q.isLoading) return <p className="text-sm text-secondary">Loading consumption…</p>;
  if (q.isError) return <p className="text-sm text-danger-fg">Failed to load consumption analytics.</p>;

  const data = q.data;
  if (!data || data.series.length === 0) {
    return (
      <EmptyState
        title="No consumption data"
        hint="Daily consumption will appear once the tank has readings."
      />
    );
  }

  const option = {
    tooltip: {
      trigger: 'axis' as const,
      backgroundColor: c.tooltipBg,
      borderColor: c.tooltipBorder,
      textStyle: { color: c.text },
    },
    grid: { left: 64, right: 24, top: 32, bottom: 40 },
    xAxis: {
      type: 'category' as const,
      data: data.series.map((p) => p.date),
      axisLine: { lineStyle: { color: c.axisLine } },
      axisLabel: { color: c.muted },
    },
    yAxis: {
      type: 'value' as const,
      name: 'Liters/day',
      axisLabel: { color: c.muted },
      splitLine: { lineStyle: { color: c.splitLine } },
    },
    series: [
      {
        name: 'Consumption',
        type: 'line' as const,
        smooth: true,
        data: data.series.map((p) => p.liters),
        lineStyle: { color: c.legend },
        itemStyle: { color: c.legend },
      },
    ],
  };

  return (
    <div>
      <h3 className="font-semibold text-primary mb-2">Consumption (last {data.days} days)</h3>
      <p className="text-xs text-secondary mb-2">
        Forecast: {Math.round(data.forecast.liters_per_day).toLocaleString('en-US')} L/day
      </p>
      <ReactECharts
        option={option}
        theme={chartThemeName(resolvedScheme)}
        notMerge
        style={{ height: 260, width: '100%' }}
      />
    </div>
  );
}
```

### Step 7.2 — ConsumptionCard.test.tsx
```tsx
import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import ConsumptionCard from './ConsumptionCard';

vi.mock('echarts-for-react', () => ({ default: () => <div data-testid="mock-echarts" /> }));
vi.mock('../../hooks/useTheme', () => ({ useTheme: () => ({ resolvedScheme: 'light' }) }));
vi.mock('../../api/client', () => ({ api: { getConsumption: vi.fn() } }));

import { api } from '../../api/client';
import type { ConsumptionAnalytics } from '../../lib/apiTypes';

const analytics: ConsumptionAnalytics = {
  tank_id: 't1',
  days: 30,
  method: 'sma',
  forecast: { method: 'sma', window_days: 7, liters_per_day: 412.6 },
  series: [
    { date: '2026-08-01', liters: 400 },
    { date: '2026-08-02', liters: 425 },
  ],
};

function renderCard() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <ConsumptionCard tankId="t1" />
    </QueryClientProvider>,
  );
}

describe('ConsumptionCard', () => {
  beforeEach(() => { vi.mocked(api.getConsumption).mockReset(); });

  it('renders the forecast and chart from analytics', async () => {
    vi.mocked(api.getConsumption).mockResolvedValue(analytics as never);
    renderCard();
    expect(await screen.findByText('Consumption (last 30 days)')).toBeInTheDocument();
    expect(screen.getByText(/413 L\/day/)).toBeInTheDocument();
    expect(screen.getByTestId('mock-echarts')).toBeInTheDocument();
    expect(api.getConsumption).toHaveBeenCalledWith('t1', 30);
  });

  it('shows an empty state when there is no series', async () => {
    vi.mocked(api.getConsumption).mockResolvedValue({ ...analytics, series: [] } as never);
    renderCard();
    expect(await screen.findByText('No consumption data')).toBeInTheDocument();
    expect(screen.queryByTestId('mock-echarts')).toBeNull();
  });
});
```

### Step 7.3 — TankDetail integration
- Render `<ConsumptionCard tankId={tank.id} />` in the body after the telemetry/strapping block.
- In `TankDetail.test.tsx` add a mock for the card:
```tsx
vi.mock('../components/tanks/ConsumptionCard', () => ({
  default: () => <div data-testid="mock-consumption-card" />,
}));
```
and a test asserting it renders; the earlier `renderPage` tests must stay green.

Run `npx vitest run TankDetail ConsumptionCard`, `npx tsc --noEmit`.
Commit as `feat(web): consumption analytics chart on tank detail`.

---

## Final verification

From `/home/ubuntu/fuel_monitoring/web`:
- `npx tsc --noEmit` (exit 0)
- `npx vitest run` (all green; expect 45 files + the new SettingsPage/StrappingCard/ConsumptionCard suites, ~190+ tests)

From `/home/ubuntu/fuel_monitoring/platform`:
- `.venv/bin/pytest fmp/tests/unit -q --import-mode=importlib`
  (expect 147 passed, 4 pre-existing errors in `test_celery_loop_safety.py` due to no DB on :5432)
- `.venv/bin/pytest fmp/tests/integration/test_api_surface.py -q --import-mode=importlib`
  (passes when DB/Redis reachable; skips otherwise)

## Open questions / callouts

- The dispatch endpoint is a by-design placeholder: plaintext codes are not persisted, so
  "re-dispatch" simply returns an explanatory message; real re-send requires a fresh upload.
- Backend `PrivilegedUser` = `admin`/`company_admin`; the frontend editor gate uses
  `canManage` = `admin`/`manager`. The UI will show the strapping editor to `manager` users;
  if this mismatch matters, adjust the gate later.
- No visual companion requested (declined); this plan ships the five integrations only.