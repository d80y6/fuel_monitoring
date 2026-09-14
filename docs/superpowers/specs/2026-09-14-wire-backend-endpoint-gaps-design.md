# Wire Backend Endpoint Gaps into the Frontend

Date: 2026-09-14

## Problem

A frontend/backend integration audit found five backend endpoints with no
frontend caller and one latent API-wrapper foot-gun. This spec wires all five
into the UI using existing codebase conventions.

Backend endpoints currently unreachable from the UI:

1. `POST /api/v1/auth/change-password`
2. `GET /api/v1/tanks/{id}/export` (CSV stream)
3. `POST /api/v1/dispensing/upload/{batch_id}/dispatch`
4. `PUT /api/v1/tanks/{tank_id}/strapping`
5. `GET /api/v1/analytics/consumption/{tank_id}`

Additionally, the dispatch endpoint (3) currently declares **no auth
dependency**; it will gain a `PrivilegedUser` requirement as part of this work.

## Design

All scoped changes follow existing frontend conventions: API methods live in the
existing API modules and use the `request()` helper (except the CSV export, which
creates a `getBlob()` helper since `request()` assumes JSON), UI uses the
existing `Field/Input/Select/Modal/Icon` kit, data fetching uses react-query,
and component tests use vitest in the existing style.

### 1. Password change — new Settings page

- Add `api.changePassword(current, next)` to `web/src/api/client.ts`:
  `POST /api/v1/auth/change-password` with body
  `{current_password, new_password}`; returns `{status: string}`.
- New page `web/src/pages/SettingsPage.tsx`:
  - Fields: Current password, New password, Confirm new password.
  - Client-side confirm-match validation before submit.
  - On success: success message; clear the form.
  - On failure: if the error is an `ApiError` (422 from the password-policy
    validator), show `err.detail` verbatim (already `"; "-joined` by backend).
  - Uses the existing `Field`/`Input` UI components.
- Routing (`web/src/router.tsx`): add `{ path: 'settings', element: <SettingsPage /> }`
  inside `RequireAuth` but OUTSIDE the `RequireManage` block (all authenticated
  users can change their own password).
- Sidebar (`web/src/components/layout/Sidebar.tsx`): add a new "Account" nav
  group with `{ to: '/settings', label: 'Settings', icon: 'settings' }`
  (not `manageOnly`).
- Icons (`web/src/components/ui/icons.tsx`): add a `settings` icon to
  `IconName` and `PATHS`.

### 2. Tank CSV export — TankDetail header button

- Add `getBlob(path, init)` to `web/src/api/http.ts`: sends the auth token via
  `tokenProvider()`, returns the raw `Blob` (the existing `request()` helper
  assumes JSON and cannot download a CSV stream).
- Add `api.exportTankCsv(tankId, start, end)` to `client.ts`:
  `GET /api/v1/tanks/{id}/export?start=<iso>&end=<iso>`. The caller triggers the
  browser download via object URL + temporary anchor click and revokes the URL.
- TankDetail (`web/src/pages/TankDetail.tsx`): add an "Export CSV" button in the
  telemetry card header (next to the window-pill buttons, using a new `download`
  icon) that downloads the currently selected window range (1h/6h/24h/7d),
  consistent with the visible chart. Disabled while loading.

### 3. Batch dispatch — UploadCard

- Add `api.redispatchBatch(batchId)` to `web/src/api/dispensing.ts`:
  `POST /api/v1/dispensing/upload/{batchId}/dispatch`; returns
  `{message: string, batch_id: string, status: string}`.
- `web/src/components/dispensing/UploadCard.tsx`: in `UploadSummary`, when
  `pending_dispatch.length > 0`, render a "Dispatch now" button. Clicking calls
  `redispatchBatch(outcome.result.batch_id)` and renders the returned `message`
  inline (the backend explains that plaintext codes are not persisted and a
  re-send requires re-uploading the file).
- `platform/fmp/api/v1/dispensing.py`: add `PrivilegedUser` dependency to
  `redispatch_batch_codes` (currently unauthenticated). Imported from
  `fmp.api.deps`.

### 4. Strapping editor — inline, manager-only

- Add `api.saveStrapping(tankId, payload)` to `web/src/api/monitoring.ts`:
  `PUT /api/v1/tanks/{tankId}/strapping` with body
  `{calibration_data: StrappingPoint[], interpolation_method: 'linear' | 'cubic_spline'}`.
- `web/src/components/tanks/StrappingCard.tsx`:
  - Keep the existing read-only table.
  - If `canManage(user?.role)` (imported from `lib/roles`), render an "Edit"
    button that toggles edit mode.
  - Edit mode: each row becomes editable height/volume inputs; "Add row" and
    "Remove row" buttons; "Save" (calls `saveStrapping`, invalidates the
    `['strapping', tankId]` query) and "Cancel" (drops edits).
  - Client-side validation mirrors the backend: at least 2 rows and
    ascending heights. Block save and show an inline error otherwise.
  - Render location unchanged (card only appears for `custom_strapping` tanks).

### 5. Consumption analytics — TankDetail card

- Add types to `web/src/lib/apiTypes.ts`:
  - `ConsumptionPoint { date: string; liters: number }`
  - `ConsumptionForecast { method: string; window_days: number; liters_per_day: number | null }`
  - `ConsumptionAnalytics { tank_id: string; days: number; method: string; forecast: ConsumptionForecast; series: ConsumptionPoint[] }`
- Add `api.getConsumption(tankId, days = 30, windowDays = 7)` to `client.ts`:
  `GET /api/v1/analytics/consumption/{tankId}?days=<days>&window_days=<windowDays>`.
- New `web/src/components/tanks/ConsumptionCard.tsx`:
  - react-query fetch of the consumption series.
  - Renders daily-liters as an ECharts line chart (existing
    `echarts-for-react` pattern; dates on X, liters on Y).
  - Shows the SMA forecast (`forecast.liters_per_day`) as a stat line when
    non-null.
  - Empty state when the series is empty (no readings).
- TankDetail: render `<ConsumptionCard tankId={tank.id} />` as a card below the
  existing telemetry/strapping area.

### 6. Fix the `listTotalizers` optional-param foot-gun

- `web/src/api/monitoring.ts`: make `dispenserId` a required argument
  (`dispenserId: string`) since the backend requires `dispenser_id`
  (`totalizers.py` declares it without a default).
- `web/src/pages/Totalizers.tsx`: the query is gated by
  `enabled: Boolean(dispenser)`, so inside the queryFn `dispenser` is always
  set; pass it as `dispenser!`. No behavioral change.

## Non-goals

- No new backend business logic. Strapping upsert, analytics, change-password,
  and export endpoints already work and are tested on the platform side.
- No changes to auth token flows, navigation guards beyond the `/settings`
  route, or state management stores.

## Testing

- Frontend (`web`): `npx tsc --noEmit`; `npx vitest run`.
  - New vitest component tests:
    - `SettingsPage` — renders form; confirm-match guard; mock
      `api.changePassword` success/`ApiError` paths.
    - `UploadCard` — "Dispatch now" visible when pending rows exist; click calls
      `api.redispatchBatch` and shows returned message.
    - `StrappingCard` — manager sees Edit; save calls `api.saveStrapping` and
      invalidates the query; validation blocks <2 rows / non-ascending heights;
      non-manager sees no Edit button.
    - `ConsumptionCard` — renders series + forecast; empty state.
  - Follow existing test style (mock `../api/client` via `vi.mock`).
- Platform (`platform`): `.venv/bin/pytest fmp/tests/unit -q --import-mode=importlib`
  must stay green (no unit-suite endpoint test is possible for the dispatch
  grant — `PrivilegedUser`/`CurrentUser` deps need a live DB).
  - Add an unauthenticated request assertion to
    `platform/fmp/tests/integration/test_api_surface.py`: POST
    `/api/v1/dispensing/upload/{uuid}/dispatch` with no credentials returns
    401/403. This integration test runs only when Postgres + Redis are
    reachable (skipped otherwise); the frontend suites are the primary gate.