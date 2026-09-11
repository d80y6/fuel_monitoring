# SUB-3 Design Spec — Frontend Visual Shell Overhaul

**Status:** Approved (brainstormed 2026-09-11)
**Roadmap:** `superpowers/plans/2026-09-11-frontend-overhaul-roadmap.md`

## 1. Context

FuelOps SCADA (`web/`) is a React 18 + Vite + TypeScript SPA using Tailwind 3.4,
ECharts (`echarts-for-react`), zustand, `@tanstack/react-query`, and react-router v6.
Current shell: light-only `slate`/`bg-white` palette, text-only sidebar nav, per-page
bare `Loading…` / `Failed to load` text, and non-theme-aware ECharts options.

SUB-3 delivers the visual shell foundation for the fleet: a semantic design-token
layer with light/dark themes (system-follow + manual override), navigational chrome
(icons, page headers, connection pill), a redesigned dashboard, reusable state
primitives, and theme-aware charts. It is the first of a three-part overhaul
(SUB-4 3D gauge, SUB-5 gateway live push) and deliberately adds **no new runtime
dependencies** beyond a small inline SVG icon set.

## 2. Goals

- Introduce a semantic token vocabulary so components stop hardcoding literal colors.
- Provide light + dark schemes with system-follow and a persisted manual override.
- Retokenize the existing UI (mechanical `slate`/`white` → token conversion).
- Upgrade the shell chrome: sidebar icons, consistent page headers, live connection pill.
- Redesign the dashboard for glanceability without new backend endpoints.
- Standardize loading/empty/error presentation across hot pages.
- Make ECharts options theme-aware and consistent (units, tooltips, legends).

## 3. Non-goals

- No route restructuring, no auth/role changes, no new pages.
- No backend changes of any kind.
- No new runtime dependencies (no icon library, no three.js in SUB-3).
- `TankCanvas` / `tankGeometry.ts` stay byte-for-byte as documented in SUB-3; the 3D
  gauge replaces them in SUB-4.
- No full 26-page state-polish sweep; primitives land on hot pages only (see §7).

## 4. Design tokens

Extend `tailwind.config.ts` with a semantic theme re-mapped per scheme. Components
consume these tokens; literal `slate-*`/`white` usages are removed by the retrofit.

Surface / canvas:

- `bg-canvas` — app background (light: `slate-100`, dark: `slate-950`)
- `bg-surface` — card background (light: `white`, dark: `slate-900`)
- `bg-surface-raised` — raised surfaces (light: `white`/ring, dark: `slate-800`)
- `bg-inset` — wells/tables (light: `slate-50`, dark: `slate-950`)

Text:

- `text-primary` (light: `slate-800`, dark: `slate-100`)
- `text-secondary` (light: `slate-600`, dark: `slate-300`)
- `text-muted` (light: `slate-400`, dark: `slate-500`)
- `text-brand` — brand accent text

Borders:

- `border-default` (light: `slate-200`, dark: `slate-800`)
- `border-strong` (light: `slate-300`, dark: `slate-700`)

Status (each maps to a `bg-*`, `text-*`, `border-*` triplet):

- `status-ok`, `status-warn`, `status-danger`, `status-info`

Fuel palette: keep the existing per-fuel colors, exposed as `fuel-{code}` tokens so
SUB-4's 3D gauge reuses them. `brand` stays as today.

Tailwind `darkMode: 'class'`.

## 5. Theme control

**Source of truth:** a zustand store `store/theme.ts` with `mode: 'light' | 'dark' | 'system'`.
A `ThemeProvider` component:

- Defaults to `'system'`.
- Resolves the effective scheme via `prefers-color-scheme` + `matchMedia`, live-updating
  on change (listener registered while in `system` mode).
- Applies/removes `dark` on `document.documentElement`.
- Persists the chosen `mode` to `localStorage['fmp-theme']`; on read failure falls back
  to `'system'` silently.
- Exposes `useTheme(): { mode, resolvedScheme, setMode }`.

**Toggle UI:** a compact segmented control (Light / System / Dark) in the header,
styled with the token classes.

**Chart theming:** `lib/chartTheme.ts` registers `light` and `dark` themes via
`echarts.registerTheme`; uses `web`-side copies of `--color-*` values kept in sync
with the token map. `TelemetryChart`/`TotalizerDriftChart` read the resolved scheme
and pass it as the ECharts `theme` prop.

## 6. Shell chrome

### Sidebar (`components/layout/Sidebar.tsx`)
- Tokenized surfaces/text/borders.
- Inline SVG icon per nav item from `components/ui/icons.tsx` (~10 icons: dashboard,
  tanks, dispensing, totalizers, alarms, companies/sites/org, fuel-types, gateways,
  iot-gateways, sign-out).
- Preserve grouped nav, headings, labels, and `manageOnly` gating exactly.
- Active nav state uses `brand`; hover state tokenized.

### Page headers (`components/ui/PageHeader.tsx`)
- Consistent title + optional route-derived breadcrumb + right-side action slot.
- Applied to the hot pages (Dashboard, Tanks, TankDetail, Dispensing, AlarmCenter,
  Totalizers, IoTGateways, IoTGatewayDetail).

### Connection pill
- In the header: reflects `useTelemetrySocket` state → `connected`/`reconnecting`/
  `offline`, colored with `status-*` tokens. Small dot + label.

## 7. Dashboard redesign

Data from existing sources only (`useTelemetry`, react-query, WS store) — no backend
changes.

- KPI row: kept and retokenized; each card gets a status-tinted accent.
- **Alert summary strip:** open-alarm count + up to 3 most recent open alarms, linking
  to Alarm Center. Data source: the existing `useRealtimeAlarms()` WS-store hook the
  sidebar already uses (`alarms:live` channel) — no new endpoint.
- **Tank grid:** improved `TankTile` — status dot (`connection_status`), fill %,
  GOV, fuel-color swatch; row still navigates to `/tanks/:id`.
- **Empty state:** when no tanks exist, an `EmptyState` card with a CTA to Tanks admin.

## 8. State polish primitives

New in `components/ui/`:

- `<Skeleton />` — shimmer block for loading surfaces.
- `<EmptyState />` — `{ icon, title, hint?, action? }`.
- Standardize hot pages: replace bare `Loading…` text with `Skeleton` rows/panels and
  `Failed to load…` text with a `surface` card that has a Retry button (re-runs the
  query/mutation).

**Hot pages (primitives applied):** Dashboard, Tanks, TankDetail, Dispensing,
AlarmCenter, Totalizers, IoTGateways, IoTGatewayDetail. Other pages receive only the
mechanical token conversion.

## 9. Chart polish

`lib/chartOptions.ts` becomes theme-aware: grid/axis/legend/tooltip colors sourced from
the active scheme (via `chartTheme.ts`); axis label formatting unchanged; tooltip and
legend formatting normalized (units: GOV/NSV in L, temperature °C, density kg/m³,
fill %). Gap-fill and live-point merge behavior in `TelemetryChart` stay identical.

## 10. Error handling

- Theme persistence failure → silent fallback to `'system'`.
- WS dropped → existing reconnect logic; connection pill reflects state.
- Query/load failures → the standardized error card with Retry.
- No new error surfaces beyond the standardized states.

## 11. Testing strategy

- Every new primitive (`ThemeProvider`, `useTheme`, `chartTheme`, `Skeleton`,
  `EmptyState`, `PageHeader`, `icons`, sidebar) gets a colocated vitest test.
- Theme tests render a probe under both `light` and `dark` class states; `matchMedia`
  is mocked in the existing jsdom setup so system-follow is testable.
- `chartTheme` / `chartOptions` tested as pure functions: given `'light'` vs `'dark'`,
  return distinct expected colors and never throw.
- Dashboard / TankDetail tests updated for the new structure (existing
  `@testing-library` + react-query harness; `useTelemetrySocket` mocked as today).
- Token conversion verified by the existing UI suites staying green after retrofit
  (class-name expectations updated where necessary).

## 12. Delivery shape

SUB-3 implementation plan (~9 tasks, TDD, subagent-driven per the SUB-2 flow):

1. Tailwind token theme + `darkMode: 'class'` bootstrap.
2. `store/theme.ts` + `ThemeProvider` + `useTheme` + toggle segmented control.
3. `chartTheme.ts` + theme-aware `chartOptions.ts`.
4. `icons.tsx` + sidebar retrofit (icons + tokens).
5. `PageHeader` + connection pill + header shell.
6. State primitives (`Skeleton`, `EmptyState`, error card) + hot-page retrofit.
7. Dashboard redesign (alert strip, tank grid, empty state).
8. TankDetail / IoT pages / remaining hot-page token + state retrofits.
9. Full frontend regression (`tsc --noEmit` + full `vitest run`) + docs.

Each task: failing test → implementation → green tests → commit → spec-compliance
review → code-quality review. Full regression gate on completion.