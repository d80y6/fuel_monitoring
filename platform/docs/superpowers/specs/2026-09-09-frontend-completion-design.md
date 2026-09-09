# SCADA Frontend Completion — Design Spec

Date: 2026-09-09
Status: Approved (design review of 2026-09-09)
Branch: main

## Purpose

Complete the SCADA web frontend to full coverage of the backend API surface. Today
the frontend ships monitoring only (Dashboard, Tanks, TankDetail, Dispensing
read-only, Totalizers). This spec adds the full management workflow across four
phases, implemented in one plan and shipped phase by phase:

- **Phase 0 — Organization management**: Companies → Sites → Stations → Dispensers.
- **Phase 1 — Dispensing workflow**: allocations, quota-sheet upload, code ops
  (validate/settle), richer transactions + live view.
- **Phase 2 — Monitoring polish**: dashboard KPIs + global Alarm Center.
- **Phase 3 — Admin settings**: fuel types, notification gateways, strapping read-only.

## Approach

Extend the existing stack (Vite + React + TypeScript + Tailwind + TanStack Query +
zustand + echarts). No refactor of the app shell. All backend consumption must go
through typed API client methods. Role gating and existence of the current pages are
preserved.

---

## 1. Navigation & role gating

Sidebar (grouped):

- **Overview**: Dashboard
- **Monitoring**: Tanks · Dispensing · Totalizers · Alarm Center *(new)*
- **Operations** *(admin / company_admin only)*: Companies → Sites → Stations → Dispensers (nested drill-down)
- **Admin** *(admin / company_admin only)*: Fuel Types · Notification Gateways

`canManage = user.role === 'admin' || user.role === 'company_admin'` derived from the
authenticated `UserRead` in the auth store. Non-privileged users never see the
Operations/Admin nav sections; directly visiting those routes redirects to
Dashboard.

All existing route paths remain unchanged except additions:
`/companies`, `/sites`, `/sites/:companyId` (filtered), `/stations/:siteId`,
`/dispensers/:stationId`, `/alarms`, `/admin/fuel-types`, `/admin/gateways`.
Dispensing remains `/dispensing` (gains tabs/cards, below).

## 2. Shared patterns

- **API client**: split into typed modules under `web/src/api/` —
  `org.ts`, `dispensing.ts`, `admin.ts`, `monitoring.ts` — re-exported through the
  existing `client` facade. Every backend endpoint gets a typed method; `http.ts`
  auth/error handling is unchanged.
- **Entity dialog**: generalize the existing CreateTankDialog pattern into a reusable
  modal with per-entity field schemas, client-side validation, and inline server-error
  display.
- **Mutations**: TanStack Query `useMutation` + `invalidateQueries` on affected lists.
- **Toasts**: small toast context for success/error feedback (none exists today).
- **Delete**: confirm dialog; companies/sites/stations soft-delete.
- **Badges/chips**: reuse existing connection-status chip styling for org entities.

## 3. Phase 0 — Organization pages

- **Companies** `/companies`: table (name, address, contact name/email/phone,
  created); New/Edit dialog; Delete (confirm). Row click → Sites for that company.
- **Sites** `/sites` (optional `?company=`): table (name, address, location, active);
  New/Edit dialog (company select, preselected from navigation context); Delete. Row → Stations.
- **Stations** `/stations/:siteId`: table (name, serial, RPi id, firmware,
  connection-status chip, last heartbeat); New/Edit dialog; Delete. Row → Dispensers.
- **Dispensers** `/dispensers/:stationId`: table (name, serial, modbus address, model,
  active); New dialog; **active toggle** via a new PATCH endpoint (see backend gap).
- **Integration**: Tanks page gains a site-filter dropdown (`list_tanks?site_id=`).

### Backend addition (explicit approval granted)

- **Dispenser PATCH** `PATCH /api/v1/stations/{station_id}/dispensers/{dispenser_id}`
  with `{ is_active?: bool, name?: str, model?: str }`; response `DispenserRead`.
  Adds a test in `fmp/tests/`. (No dispenser soft-delete.)

## 4. Phase 1 — Dispensing workflow

Dispensing page becomes sections/tabs; existing live view + transactions retained.

- **Allocations**: table (employee name, invoice, allocated/dispensed/remaining L,
  status badge, created, progress bar). Read-only (`GET /dispensing/allocations`).
- **Upload**: company selector + .xlsx/.csv file picker →
  `POST /dispensing/upload` → outcome summary (total/success/failed rows, per-row
  errors). "Download template" link documenting headers
  `Employee ID, Employee Name, Phone, Invoice Number, Allocated Liters`
  (backend aliases confirmed in `excel_ingestion.COLUMN_ALIASES`).
- **Code ops** (admin/company_admin only): *Validate* (code + station →
  employee name / remaining liters / reason) then *Settle* (code + station + dispenser
  + requested/actual liters + totalizer before/after) →
  status COMPLETED/PARTIAL/OVER_DISPENSE/DISCREPANCY (+ partial-code info).
  Wired to `/dispensing/validate` and `/dispensing/complete`.
- **Live view**: unchanged station selector + per-dispenser in-progress cards.
- **Transactions**: add dispenser/employee names where available + station filter.

## 5. Phase 2 — Monitoring polish

- **Dashboard KPIs** (top, above tiles): Tanks count · Open alarms (global) ·
  Stations online · Last-24h dispensed liters (terminal transactions within a day).
- **Alarm Center** `/alarms`: all open alarms across tanks (tank name, type, level,
  message, timestamp, value); one-click Ack via
  `POST /tanks/{id}/alarms/{aid}/ack`; empty state.

## 6. Phase 3 — Admin

- **Fuel Types** `/admin/fuel-types`: table (code, name, base density, thermal
  expansion, vapor pressure, viscosity) + New dialog (`POST /api/v1/fuel-types`).
  Read-only rows.
- **Notification Gateways** `/admin/gateways`: table (name, channel, enabled, config
  preview) + create/edit/delete via existing gateway CRUD. `NotificationGatewayRead`
  fields confirmed at coding time.
- **Strapping**: read-only view on TankDetail for `custom_strapping` tanks (calibration
  height→volume points + interpolation method) via `GET /strapping?tank_id=`.

## 7. Testing & verification

- **Web (Vitest + Testing Library, existing conventions)**: unit tests for new lib
  helpers (status/label maps, KPI aggregation, upload-outcome rendering, formats);
  component tests for dialogs, allocation table, upload summary, alarm-center ack,
  role-gating (admin vs `user` sidebar).
- **Backend**: test for the dispenser PATCH endpoint.
- **Gates per phase**: `npm test` + `npm run build` (web); backend pytest for the
  PATCH addition; live re-deploy of the web container + headless-chromium render
  audit on the deployed stack (zero console errors, all pages render, management
  flows exercised E2E).

## 8. Sequencing

Single implementation plan; phases built 0 → 1 → 2 → 3, verification gate after each.

## Open confirmations (resolved at coding time)

- Exact `NotificationGatewayRead` fields.
- Dispenser PATCH request/response shape (`DispenserRead` response).