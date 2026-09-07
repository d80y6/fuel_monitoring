# Fuel Dynamics Engine + SCADA Frontend — Design

Date: 2026-09-07
Status: Approved
Scope: Backend tank-geometry/fuel-dynamics (models, schemas, engine, migrations, seed) AND greenfield SCADA React frontend (SVG tank canvases, GOV-vs-NSV charts, dispensing/totalizer visualizations).

## 1. Goals

1. Make the storage telemetry engine shape-aware and fuel-aware: accurate height→volume math per physical tank geometry, temperature-compensated density driven by a per-fuel model, and Gross Observed Volume (GOV) / Net Standard Volume (NSV @15°C) persisted on the measurement stream.
2. Provide the data model, migrations, seed data, and API surface that the frontend needs.
3. Build a SCADA-grade web frontend (greenfield `web/`) with geometry-aware SVG tank canvases, dual-axis GOV/NSV telemetry charts, and live dispensing + secret-totalizer drift visualizations.

## 2. Backend Data Model

### 2.1 New table `fuel_types`
| column | type | notes |
|---|---|---|
| id | uuid PK | |
| code | varchar(32) unique | e.g. `gasoline`, `diesel`, `kerosene`, `jet_fuel`, `ethanol` |
| name | varchar(64) | display name |
| base_density | float | kg/m³ at 15°C |
| thermal_expansion_coeff | float | 1/°C |
| max_vapor_pressure | float | kPa |
| viscosity_cst | float | kinematic viscosity, cSt |
| created_at / updated_at | timestamptz | TimestampMixin |

Model: `fmp/models/fuel.py`, class `FuelType`.

### 2.2 New table `strapping_tables`
| column | type | notes |
|---|---|---|
| id | uuid PK | |
| tank_id | uuid FK→tanks.id, unique | one strapping table per tank |
| calibration_data | JSONB | `[{ "height": m, "volume": L }, ...]` ascending by height, min 2 points |
| interpolation_method | varchar(20) | `linear` or `cubic_spline` |
| created_at / updated_at | timestamptz | |

Model: `fmp/models/fuel.py`, class `StrappingTable` (uses `JSONB` from postgresql dialect; store/load via `json.dumps/loads`).

### 2.3 `tanks` changes (model `fmp/models/tank.py`)
- **Add** `tank_shape varchar(20)` default `vertical_cylinder`, one of:
  `vertical_cylinder`, `horizontal_cylinder`, `rectangular`, `spherical`, `horizontal_elliptical_ends`, `custom_strapping`.
- **Add** `dish_depth float?` — dish/elliptical head depth in m (required when shape = `horizontal_elliptical_ends`).
- **Add** `tank_width float?` — interior width in m (required when shape = `rectangular`).
- **Add** `fuel_type_id uuid FK→fuel_types.id` — replacement for `fluid_density`.
- **Add** `strapping_table_id uuid FK→strapping_tables.id` nullable.
- **Drop** `fluid_density`.
- Keep `tank_orientation` (`vertical`/`horizontal`). Validation rule (model-level `@validates`/service-level check AND Pydantic schema):
  - `vertical_cylinder` → `vertical`
  - `horizontal_cylinder`, `horizontal_elliptical_ends`, `spherical` → `horizontal`
  - `rectangular` → either
  - `custom_strapping` → matches the strapping table's intended orientation (any)

Shape-specific dimension requirements:
- `vertical_cylinder`: `tank_height` + `tank_diameter`
- `horizontal_cylinder`: `tank_length` + `tank_diameter`
- `horizontal_elliptical_ends`: `tank_length` (cylindrical section only) + `tank_diameter` + `dish_depth`
- `rectangular`: `tank_height` + `tank_width` + `tank_length`
- `spherical`: `tank_diameter`
- `custom_strapping`: `strapping_table_id` set; dimensions optional

`tank_volume` remains the authoritative stated capacity (L) used by `fill_percent`.

### 2.4 `measurements` changes (hypertable, model `fmp/models/tank.py`)
- **Add** `gov_volume float?` — Gross Observed Volume (L), equals existing `volume` = GOV by definition.
- **Add** `net_volume float?` — Net Standard Volume at 15°C (L).
- **Add** `density_at_temperature float?` — ρ(T) kg/m³ applied to the reading.
- Existing `volume` remains and is written identically to `gov_volume` (backward compatibility).

## 3. Measurement Engine (`fmp/ingestion/processor.py`)

All functions remain pure/dependency-free.

### 3.1 Density
Replace the density-range heuristic (`THERMAL_EXPANSION`, `_fuel_class`) with explicit coefficients:
```
def density_at_temperature(base_density: float, thermal_expansion_coeff: float, temperature_c: float | None) -> float:
    if temperature_c is None:
        return base_density
    return base_density * (1.0 - thermal_expansion_coeff * (temperature_c - 15.0))
```
Also keep `temperature_compensated_density(base_density, temperature_c)` as a thin wrapper that applies a default coefficient derived from a `FuelType` (or default gasoline coeff) — used only where a fuel object is unavailable; pipeline will call `density_at_temperature` with the tank's fuel coefficients.

### 3.2 Volume dispatch
`calculate_volume(level, *, tank_shape, orientation, tank_diameter, tank_length=None, tank_height=None, tank_width=None, dish_depth=None, strapping=None)`:
- `vertical_cylinder`: `π (d/2)² h × 1000` (existing).
- `horizontal_cylinder`: existing partial-cylinder area × length (existing).
- `horizontal_elliptical_ends`: cylinder section (existing segment math) **plus** two dished-head contributions. Heads modeled as ellipsoids of revolution (semi-axes: `tank_diameter/2`, `tank_diameter/2`, `dish_depth`); partial head volume below fill level `h` is the volume of the ellipsoid intersected by a horizontal plane at height `h`, integrated over the head length with adaptive Simpson quadrature (pure, dependency-free numeric integration, tolerance 1e-6 m³). Unit fixtures validate against closed-form reference volumes at 0/25/50/75/100% fill (tolerance 0.5%).
- `rectangular`: `width × length × level × 1000`.
- `spherical`: spherical-segment volume up to level: `V = (π h² / 3)(3r − h)` in m³, `×1000`.
- `custom_strapping`: lookup `level` against `strapping.calibration_data`; interpolate volume using the table's `interpolation_method`; clamp to table bounds.
- Clamp level to physical max in all cases; negative returns 0.

### 3.3 Strapping interpolation
New pure module `fmp/ingestion/tank_geometry.py` (keeps `processor.py` focused), exported through the processor module:
- `interpolate_strapping(points, level, method)` — `linear` via standard interpolation; `cubic_spline` via a pure-Python natural cubic spline (import-free, `solve_tridiagonal` on the second-derivative system). Clamp outside the domain (no extrapolation).

### 3.4 GOV / NSV
```
VCF = 1.0 - thermal_expansion_coeff * (temperature_c - 15.0)   # = ρ(T)/ρ(15)
NSV = GOV * VCF
gov_volume = volume  (the calibrated gross volume from §3.2)
density_at_temperature = density_at_temperature(base_density, coeff, temperature_c)
```

## 4. Pipeline (`fmp/ingestion/pipeline.py`)

- `ProcessedReading` gains `gov_volume: float`, `net_volume: float`, `density_at_temperature: float`.
- `IngestionPipeline.process` resolves density via `tank.fuel_type` (relationship). If `tank.fuel_type` is `None` (pre-migration row not yet backfilled), fall back to module constants `DEFAULT_DENSITY_KG_M3 = 750.0`, `DEFAULT_EXPANSION_COEFF = 0.00095` (gasoline) and log a warning — the migration backfills all legacy rows so this path is exceptional.
- Persist `gov_volume`, `net_volume`, `density_at_temperature` through `insert_measurements`.
- `publish_live` payload and WS messages add `gov_volume`, `net_volume`, `density_at_temperature`, `fuel_type` code.

## 5. API Surface

### Schemas (`fmp/schemas/`)
- `tanks.py`: `TankBase` + `tank_shape` (enum), `dish_depth`, `tank_width`, `fuel_type_id` (required), `strapping_table_id`; **remove** `fluid_density`. Add shape/orientation validator. `TelemetryPoint` + `gov_volume`, `net_volume`, `density_at_temperature`.
- New `fuel.py`: `FuelTypeCreate`, `FuelTypeRead`.
- New `strapping.py`: `StrappingTableUpsert` (`calibration_data: list[{height, volume}]`, `interpolation_method`), `StrappingTableRead`.

### Routers (`fmp/api/v1/`)
- New `fuel_types.py`: `GET /api/v1/fuel-types` (auth, any user), `POST /api/v1/fuel-types` (admin role).
- New `strapping.py`: `GET /api/v1/tanks/{tank_id}/strapping` (auth) → 404 if absent; `PUT /api/v1/tanks/{tank_id}/strapping` (privileged) upsert + wire `tank.strapping_table_id`.
- `tanks.py`: extend create/read DTOs (new fields); set `strapping_table_id` when shape is `custom_strapping`.

## 6. Migrations & Seed

- Scaffold Async Alembic under `platform/alembic/` (`alembic init -t async`; `alembic/env.py` wired to `fmp.core.database.config` URL + `Base.metadata`).
- Migration `0001`: create `fuel_types`, `strapping_tables`; add tank columns (`tank_shape`, `dish_depth`, `tank_width`, `fuel_type_id`, `strapping_table_id`), create FKs; drop `tanks.fluid_density`; add `measurements.gov_volume`, `.net_volume`, `.density_at_temperature`. `fuel_type_id` created nullable; backfill: default fuel types seeded first, legacy `fluid_density` mapped to nearest fuel type by density range (gasoline ≤780, diesel ≤860, else ethanol); column left nullable at DB level, app DTOs require it for new tanks.
- Seed script `fmp/scripts/seed_fuel_types.py` (idempotent, `INSERT ... ON CONFLICT (code) DO UPDATE`), invoked from `fmp/scripts/init_db.py` and documented in `README`.

Constants for seed:
- gasoline: base 750, coeff 0.00095, vapor 60, viscosity 0.6
- diesel: base 845, coeff 0.00080, vapor 2, viscosity 2.5
- kerosene: base 800, coeff 0.00090, vapor 1.5, viscosity 1.4
- jet_fuel: base 810, coeff 0.00085, vapor 1.2, viscosity 1.1
- ethanol: base 789, coeff 0.00110, vapor 16, viscosity 1.2

## 7. Frontend (`web/`, greenfield)

### Stack
Vite + React 18 + TypeScript + Tailwind, React Router, zustand (persisted auth + live reading store), TanStack Query (REST), Apache ECharts via `echarts-for-react`, native `WebSocket` client with reconnect/backoff.

### Structure
```
web/
  src/
    api/        http.ts (JWT axios/fetch client), ws.ts (reconnect + subscriptions)
    store/      auth.ts, telemetry.ts
    hooks/      useTelemetry, useRealtimeAlarms, useTotalizers
    components/
      tanks/    TankCanvas.tsx + shapes/ (geometry in TS)
      charts/   TelemetryChart.tsx, TotalizerDriftChart.tsx
      dispensing/DispenseLiveView.tsx
      layout/   sidebar, alarms drawer
    pages/      login, dashboard, tanks, tankDetail, dispensing, totalizers
    lib/        tankGeometry.ts (mirrors backend formulas used for SVG), chartOptions.ts
  tests/        vitest unit (geometry + chart transforms)
```

### Components
- **TankCanvas** (`components/tanks/`): SVG per `tank_shape`, fill polygon computed from latest level via TS mirror of the backend geometry (`lib/tankGeometry.ts`, tested against backend fixture vectors), liquid color keyed by `fuel_type`, threshold overlay lines (low/critical/high), inflow/outflow animated arrows on sign of `flow_rate`. Clients:
  - list/dashboard tile (mini)
  - `/tanks/:id` detailed canvas + readouts (GOV/NSV, level, temperature, density, fill%).
- **TelemetryChart**: dual Y-axis — left: GOV line + NSV line; right: temperature + pressure. ECharts `dataZoom`, tooltip linkage, threshold band (`markArea`) from low/critical/high thresholds. Data: TanStack Query on `/api/v1/tanks/{id}/range` merged with live WS points.
- **DispenseLiveView**: quota progress (dispensed vs allocated liters per employee), OTP code lifecycle stages (issued → validated → completed/expired).
- **TotalizerDriftChart**: cumulative authorized liters (from dispensing transactions) overlaid on hardware secret-totalizer series (`/api/v1/totalizers?dispenser_id=`); third line = drift (totalizer − authorized cumulative).

### Auth/authn
Login → `POST /api/v1/auth/login` → JWT in zustand (localStorage); refresh via `/api/v1/auth/me` on boot; 401 → redirect `/login`. WS connections use `?token=` query (`get_current_user_from_query`).

### E2E wiring
Docker compose: add `web` build (Node 20 multi-stage → build to `dist`, nginx-static or serve via existing nginx), health + routing to `/api` and `/ws` through the existing `nginx` config (SSE/WS upgrade headers).

## 8. Testing Strategy

### Unit (TDD, all new behavior has failing tests first)
- `test_tank_geometry.py`: vertical, horizontal, dished-heads, rectangular, spherical, custom strapping (linear + cubic spline, scheme boundary, clamp).
- `test_fuel_dynamics.py`: density@T (incl. T<15, T=None), VCF, NSV = GOV×VCF.
- `test_strapping_spline.py`: natural spline interior accuracy + monotonic clamp.
- Frontend Vitest: `tankGeometry.ts` against backend fixture vectors; chart data-transform helpers (rounding, gap fill, axis bounds).

### Integration (live DB, httpx ASGI)
- tank CRUD with fuel_type + every shape; shape/orientation validator 422s.
- strapping upsert + `GET`, `custom_strapping` tank integrity.
- telemetry writes NSV/density; `range`/`recent` return new fields; WS live payload includes GOV/NSV.
- fuel-types list (auth) + create (admin only → 403 for user role).

### Legacy test updates
Existing `test_processor.py` cases encoding the density-range heuristic are intentionally updated (removed) — new fuel-driven tests supersede them. `test_pipeline_events.py`/`test_telemetry_pipeline.py` updated for the new `ProcessedReading`/measurement fields.

## 9. Rollout Order (implementation plan phases)

1. Models (`FuelType`, `StrappingTable`, Tank/Measurement column changes) + migration `0001` + seed script.
2. Engine: `tank_geometry.py` (spline + shapes) + `processor.py` density/VCF/NSV + GOV/NSV — TDD unit tests.
3. Pipeline + schemas + routers (fuel-types, strapping, tanks DTO) — TDD integration tests.
4. Frontend scaffold + auth + WS client + tank list/detail + TankCanvas + charts + dispensing/totalizers views — vitest.
5. Compose `web` service + nginx wiring, full E2E smoke, docs update.

## 10. Explicit Decisions (approved)
- `fuel_type_id` replaces `fluid_density` (FK single source of truth).
- Strapping data stored as JSONB array; spline in pure Python.
- GOV/NSV/density persisted on `measurements`.
- `tank_width` added (rectangular shape); `dish_depth` for dished ends.
- `tank_orientation` kept and validated against `tank_shape`.
- `fuel_type_id` nullable at DB level (legacy rows), required by `TankCreate` DTO.
- Frontend: React+Vite+TS+Tailwind SPA; ECharts; greenfield build including web.