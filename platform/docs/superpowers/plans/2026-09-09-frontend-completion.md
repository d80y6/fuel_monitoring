# SCADA Frontend Completion — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete the SCADA web frontend to full API coverage — organization management, dispensing workflow, monitoring polish, and admin settings — across four phases shipped incrementally.

**Architecture:** Extend the existing Vite + React + TypeScript + TanStack Query frontend. Split `api/client.ts` into typed modules (org, dispensing, admin, monitoring) re-exported through the `api` facade. Add a backend dispenser PATCH endpoint. All new pages follow existing dialog + table + TanStack Query + Tailwind patterns.

**Tech Stack:** React 18, TypeScript, Tailwind CSS, TanStack Query v5, zustand, vitest + @testing-library/react, echarts, FastAPI + SQLAlchemy (backend), httpx + pytest (backend tests)

**Spec:** `platform/docs/superpowers/specs/2026-09-09-frontend-completion-design.md`

---

## File Structure

### Backend
- Modify: `platform/fmp/schemas/org.py` — add DispenserUpdate
- Modify: `platform/fmp/api/v1/stations.py` — add PATCH dispenser route
- Create: `platform/fmp/tests/integration/test_org_api.py`

### Frontend — Foundation
- Modify: `web/src/api/http.ts` — FormData guard, 204 handling
- Create: `web/src/api/http.test.ts`
- Modify: `web/src/lib/apiTypes.ts` — 15 new interfaces
- Create: `web/src/lib/roles.ts` + test
- Create: `web/src/lib/kpi.ts` + test
- Create: `web/src/lib/allocProgress.ts` + test
- Create: `web/src/api/org.ts`, `dispensing.ts`, `admin.ts`, `monitoring.ts`
- Modify: `web/src/api/client.ts` — import modules, merge
- Create: `web/src/components/ui/Modal.tsx`, `fields.tsx`, `confirm.tsx`, `badge.tsx`
- Modify: `web/src/components/layout/Sidebar.tsx` — grouped nav, role gating
- Modify: `web/src/router.tsx` — new routes, RequireManage guard

### Frontend — Pages
- Create: `web/src/pages/CompaniesPage.tsx` + test
- Create: `web/src/pages/SitesPage.tsx` + test
- Create: `web/src/pages/StationsPage.tsx` + test
- Create: `web/src/pages/DispensersPage.tsx` + test
- Modify: `web/src/pages/Tanks.tsx` — site filter
- Create: `web/src/components/dispensing/AllocationsCard.tsx` + test
- Create: `web/src/components/dispensing/UploadCard.tsx`
- Create: `web/src/components/dispensing/CodeOpsCard.tsx` + test
- Modify: `web/src/pages/Dispensing.tsx` — tabs
- Create: `web/src/components/dashboard/KpiCards.tsx` + test
- Modify: `web/src/pages/Dashboard.tsx` — KPI cards
- Replace: `web/src/pages/AlarmCenter.tsx` + test
- Replace: `web/src/pages/FuelTypesPage.tsx` + test
- Replace: `web/src/pages/GatewaysPage.tsx` + test
- Create: `web/src/components/tanks/StrappingCard.tsx` + test
- Modify: `web/src/pages/TankDetail.tsx` — StrappingCard insertion

---

## Part 0: Foundation

### Task 0.1: Backend — Dispenser PATCH endpoint

**Files:**
- Modify: `platform/fmp/schemas/org.py`
- Modify: `platform/fmp/api/v1/stations.py`
- Create: `platform/fmp/tests/integration/test_org_api.py`

- [ ] **Step 1: Add DispenserUpdate schema**

Append to `platform/fmp/schemas/org.py` after `DispenserRead`:

```python
class DispenserUpdate(BaseModel):
    name: str | None = None
    modbus_address: int | None = None
    dispenser_model: str | None = None
    is_active: bool | None = None
```

- [ ] **Step 2: Add PATCH route**

Add `DispenserUpdate` to the import in `platform/fmp/api/v1/stations.py` line 12:

```python
from fmp.schemas.org import (
    DispenserCreate,
    DispenserRead,
    DispenserUpdate,
    StationCreate,
    StationRead,
    StationUpdate,
)
```

Append route at end of file:

```python
@router.patch("/{station_id}/dispensers/{dispenser_id}", response_model=DispenserRead)
async def update_dispenser(
    station_id: uuid.UUID,
    dispenser_id: uuid.UUID,
    payload: DispenserUpdate,
    _: PrivilegedUser,
    session: SessionDep,
):
    dispenser = (
        await session.execute(
            select(Dispenser).where(
                Dispenser.id == dispenser_id,
                Dispenser.station_id == station_id,
            )
        )
    ).scalar_one_or_none()
    if dispenser is None:
        raise HTTPException(404, "dispenser not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(dispenser, field, value)
    await session.commit()
    await session.refresh(dispenser)
    return dispenser
```

- [ ] **Step 3: Write failing test**

Create `platform/fmp/tests/integration/test_org_api.py`:

```python
from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def token_override(db):
    from fmp.api.main import app
    from fmp.api.deps import get_current_user
    from fmp.core.database import async_session_factory
    from fmp.core.security import hash_password
    from fmp.models import User

    pw = hash_password("AdminPass123")
    async with async_session_factory() as session:
        user = User(
            username=f"admin_{uuid.uuid4().hex[:6]}",
            email=f"admin_{uuid.uuid4().hex[:6]}@t.io",
            password_hash=pw,
            role="admin",
            is_active=True,
        )
        session.add(user)
        await session.commit()

    async def _override():
        return user

    app.dependency_overrides[get_current_user] = _override
    yield user
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def client():
    from fmp.api.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest_asyncio.fixture
async def seed_dispenser(db):
    from fmp.core.database import async_session_factory
    from fmp.models import Company, Dispenser, Site, Station

    async with async_session_factory() as session:
        company = Company(name=f"OrgCo-{uuid.uuid4().hex[:6]}")
        session.add(company)
        await session.flush()

        site = Site(name="OrgSite", company_id=company.id)
        session.add(site)
        await session.flush()

        station = Station(
            name="OrgStation",
            site_id=site.id,
            serial_number=f"SN-{uuid.uuid4().hex[:8]}",
        )
        session.add(station)
        await session.flush()

        disp = Dispenser(
            name="P1",
            station_id=station.id,
            serial_number=f"DN-{uuid.uuid4().hex[:8]}",
        )
        session.add(disp)
        await session.commit()

        return {"dispenser_id": disp.id, "station_id": station.id}


async def test_dispenser_patch_toggles_active(
    db, token_override, client, seed_dispenser
):
    r = await client.patch(
        f"/api/v1/stations/{seed_dispenser['station_id']}"
        f"/dispensers/{seed_dispenser['dispenser_id']}",
        json={"is_active": False},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["is_active"] is False
    assert body["name"] == "P1"


async def test_dispenser_patch_preserves_unset_fields(
    db, token_override, client, seed_dispenser
):
    r = await client.patch(
        f"/api/v1/stations/{seed_dispenser['station_id']}"
        f"/dispensers/{seed_dispenser['dispenser_id']}",
        json={"dispenser_model": "ModelX"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["dispenser_model"] == "ModelX"
    assert body["is_active"] is True
    assert body["name"] == "P1"


async def test_dispenser_patch_not_found(
    db, token_override, client, seed_dispenser
):
    fake_id = uuid.uuid4()
    r = await client.patch(
        f"/api/v1/stations/{seed_dispenser['station_id']}/dispensers/{fake_id}",
        json={"is_active": False},
    )
    assert r.status_code == 404
```

- [ ] **Step 4: Run test**

```bash
cd platform && POSTGRES_PORT=5434 POSTGRES_DB=fuel_test POSTGRES_USER=fuelplatform POSTGRES_PASSWORD=fuelplatform123 REDIS_PORT=6479 python3 -m pytest fmp/tests/integration/test_org_api.py -v
```

Expected: 3 passed

- [ ] **Step 5: Run full backend test suite**

```bash
cd platform && POSTGRES_PORT=5434 POSTGRES_DB=fuel_test POSTGRES_USER=fuelplatform POSTGRES_PASSWORD=fuelplatform123 REDIS_PORT=6479 python3 -m pytest fmp/tests -q
```

- [ ] **Step 6: Commit**

```bash
rtk git add platform/fmp/schemas/org.py platform/fmp/api/v1/stations.py platform/fmp/tests/integration/test_org_api.py
rtk git commit -m "feat(api): add PATCH /stations/{id}/dispensers/{id} endpoint + test"
```

---

### Task 0.2: Frontend — Fix http.ts (FormData guard, 204 handling)

**Files:**
- Modify: `web/src/api/http.ts`
- Create: `web/src/api/http.test.ts`

- [ ] **Step 1: Write failing test**

Create `web/src/api/http.test.ts`:

```typescript
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { request, ApiError } from './http';

function jsonResponse(body: unknown, init?: ResponseInit) {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
    ...init,
  });
}

describe('request()', () => {
  beforeEach(() => {
    vi.unstubAllGlobals();
  });

  it('sets Content-Type to application/json for object bodies', async () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      jsonResponse({ ok: true }),
    );
    await request('/test', { method: 'POST', body: JSON.stringify({ a: 1 }) });
    const sentHeaders = fetchSpy.mock.calls[0][1]!.headers as Headers;
    expect(sentHeaders.get('Content-Type')).toBe('application/json');
  });

  it('does NOT set Content-Type for FormData bodies', async () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      jsonResponse({ ok: true }),
    );
    const fd = new FormData();
    fd.append('file', new Blob(), 'test.csv');
    await request('/upload', { method: 'POST', body: fd });
    const sentHeaders = fetchSpy.mock.calls[0][1]!.headers as Headers;
    expect(sentHeaders.has('Content-Type')).toBe(false);
  });

  it('returns undefined for 204 No Content', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(null, { status: 204 }),
    );
    const result = await request('/delete', { method: 'DELETE' });
    expect(result).toBeUndefined();
  });

  it('throws ApiError with detail on non-ok response', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      jsonResponse({ detail: 'not found' }, { status: 404 }),
    );
    await expect(request('/missing')).rejects.toThrow(ApiError);
    try {
      await request('/missing');
    } catch (e) {
      expect((e as ApiError).status).toBe(404);
      expect((e as ApiError).detail).toBe('not found');
    }
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd web && npx vitest run src/api/http.test.ts
```

- [ ] **Step 3: Fix http.ts**

Replace `web/src/api/http.ts` with:

```typescript
export class ApiError extends Error {
  constructor(public status: number, public detail: string) {
    super(detail);
    this.name = 'ApiError';
  }
}

let tokenProvider: () => string | null = () => null;
let onUnauthorized: () => void = () => {};

export function setTokenProvider(fn: () => string | null): void {
  tokenProvider = fn;
}

export function setOnUnauthorized(fn: () => void): void {
  onUnauthorized = fn;
}

export async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = tokenProvider();
  const headers = new Headers(init.headers);
  if (token) {
    headers.set('Authorization', `Bearer ${token}`);
  }
  if (!headers.has('Content-Type') && !(init.body instanceof FormData)) {
    headers.set('Content-Type', 'application/json');
  }

  const response = await fetch(path, { ...init, headers });

  if (response.status === 401) {
    onUnauthorized();
    throw new ApiError(response.status, 'Unauthorized');
  }

  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new ApiError(
      response.status,
      typeof data.detail === 'string' ? data.detail : 'Unknown error',
    );
  }

  if (response.status === 204) return undefined as T;
  return response.json();
}
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd web && npx vitest run src/api/http.test.ts
```

Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
rtk git add web/src/api/http.ts web/src/api/http.test.ts
rtk git commit -m "fix(api): guard Content-Type for FormData, handle 204, add tests"
```
---

### Task 0.3: Frontend — Add new apiTypes + lib helpers + tests

**Files:**
- Modify: `web/src/lib/apiTypes.ts`
- Create: `web/src/lib/roles.ts` + test
- Create: `web/src/lib/kpi.ts` + test
- Create: `web/src/lib/allocProgress.ts` + test

- [ ] **Step 1: Write failing tests for roles, kpi, allocProgress**

Create `web/src/lib/roles.test.ts`:

```typescript
import { describe, expect, it } from 'vitest';
import { canManage } from './roles';

describe('canManage', () => {
  it('returns true for admin', () => expect(canManage('admin')).toBe(true));
  it('returns true for company_admin', () => expect(canManage('company_admin')).toBe(true));
  it('returns false for viewer', () => expect(canManage('viewer')).toBe(false));
  it('returns false for null/undefined', () => {
    expect(canManage(null)).toBe(false);
    expect(canManage(undefined)).toBe(false);
  });
});
```

Create `web/src/lib/kpi.test.ts`:

```typescript
import { describe, expect, it } from 'vitest';
import { isOpenAlarm, last24hLiters, onlineStations } from './kpi';
import type { AlarmSummary, TransactionRead } from './apiTypes';

function txn(actualLiters: number, hoursAgo: number): TransactionRead {
  return {
    id: 1, station_id: 's', dispenser_id: 'd', employee_id: 'e',
    requested_liters: actualLiters, actual_liters: actualLiters,
    secret_totalizer_before: 0, secret_totalizer_after: 0,
    status: 'COMPLETED',
    created_at: new Date(Date.now() - hoursAgo * 3600_000).toISOString(),
  };
}

describe('isOpenAlarm', () => {
  it('returns true for unacknowledged', () => {
    expect(isOpenAlarm({ acknowledged: false } as AlarmSummary)).toBe(true);
  });
  it('returns false for acknowledged', () => {
    expect(isOpenAlarm({ acknowledged: true } as AlarmSummary)).toBe(false);
  });
});

describe('last24hLiters', () => {
  it('sums transactions from last 24h', () => {
    const txns = [txn(50, 1), txn(30, 25), txn(100, 0.5)];
    expect(last24hLiters(txns)).toBeCloseTo(150);
  });
  it('returns 0 for empty list', () => {
    expect(last24hLiters([])).toBe(0);
  });
});

describe('onlineStations', () => {
  it('counts online stations', () => {
    expect(onlineStations([
      { connection_status: 'online' },
      { connection_status: 'Offline' },
      { connection_status: 'online' },
    ])).toBe(2);
  });
});
```

Create `web/src/lib/allocProgress.test.ts`:

```typescript
import { describe, expect, it } from 'vitest';
import { progressPercent } from './allocProgress';

describe('progressPercent', () => {
  it('returns 0 when allocated is 0', () => {
    expect(progressPercent({ allocated_liters: 0, dispensed_liters: 10 })).toBe(0);
  });
  it('computes percentage correctly', () => {
    expect(progressPercent({ allocated_liters: 100, dispensed_liters: 37 })).toBeCloseTo(37);
  });
  it('clamps at 100', () => {
    expect(progressPercent({ allocated_liters: 50, dispensed_liters: 60 })).toBe(100);
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd web && npx vitest run src/lib/roles.test.ts src/lib/kpi.test.ts src/lib/allocProgress.test.ts
```

- [ ] **Step 3: Implement helpers + add apiTypes**

Create `web/src/lib/roles.ts`:

```typescript
export function canManage(role: string | null | undefined): boolean {
  return role === 'admin' || role === 'company_admin';
}
```

Create `web/src/lib/kpi.ts`:

```typescript
import type { AlarmSummary, TransactionRead } from './apiTypes';

export function isOpenAlarm(a: AlarmSummary): boolean {
  return !a.acknowledged;
}

export function last24hLiters(
  transactions: TransactionRead[],
  now: Date = new Date(),
): number {
  const cutoff = now.getTime() - 24 * 60 * 60 * 1000;
  return transactions.reduce((sum, t) => {
    if (!t.created_at || !Number.isFinite(t.actual_liters)) return sum;
    return new Date(t.created_at).getTime() >= cutoff ? sum + t.actual_liters : sum;
  }, 0);
}

export function onlineStations(
  stations: Array<{ connection_status: string }>,
): number {
  return stations.filter(
    (s) => s.connection_status.toLowerCase() === 'online',
  ).length;
}
```

Create `web/src/lib/allocProgress.ts`:

```typescript
export function progressPercent(a: {
  allocated_liters: number;
  dispensed_liters: number;
}): number {
  if (!a.allocated_liters) return 0;
  return Math.max(0, Math.min(100, (a.dispensed_liters / a.allocated_liters) * 100));
}
```

Append to `web/src/lib/apiTypes.ts`:

```typescript
export interface CompanyCreatePayload {
  name: string;
  address?: string | null;
  contact_name?: string | null;
  contact_email?: string | null;
  contact_phone?: string | null;
}

export interface SiteCreatePayload {
  name: string;
  company_id: string;
  address?: string | null;
  location?: string | null;
  is_active?: boolean;
}

export interface StationCreatePayload {
  name: string;
  site_id: string;
  serial_number: string;
  raspberry_pi_id?: string | null;
  firmware_version?: string | null;
}

export interface DispenserCreatePayload {
  name: string;
  serial_number: string;
  modbus_address?: number;
  dispenser_model?: string | null;
}

export interface DispenserUpdatePayload {
  is_active?: boolean;
  name?: string;
  dispenser_model?: string | null;
  modbus_address?: number;
}

export interface ExcelRowOutput {
  row: number;
  employee_id: string;
  employee_name: string;
  phone: string;
  invoice_number: string | null;
  allocated_liters: number | null;
  error: string | null;
}

export interface ExcelIngestResult {
  batch_id: string;
  total_rows: number;
  successful_rows: number;
  failed_rows: number;
  errors: ExcelRowOutput[];
}

export interface PendingDispatch {
  allocation_id: string;
  employee_id: string;
  employee_name: string;
  phone: string;
  code: string;
  liters: number;
  invoice_number: string | null;
  channel: string | null;
}

export interface ExcelIngestOutcome {
  result: ExcelIngestResult;
  pending_dispatch: PendingDispatch[];
}

export interface CodeValidateRequest {
  code: string;
  station_id: string;
  requested_liters?: number | null;
}

export interface CodeValidateResponse {
  valid: boolean;
  employee_name: string | null;
  remaining_liters: number | null;
  code_id: string | null;
  reason: string | null;
}

export interface PartialDispenseOutcome {
  partial: boolean;
  original_code_id: string;
  dispensed_liters: number;
  remaining_liters: number;
  new_code: string | null;
  new_code_id: string | null;
  new_allocation_id: string | null;
}

export interface DispenseCompleteRequest {
  code: string;
  station_id: string;
  dispenser_id: string;
  requested_liters: number;
  actual_liters: number;
  secret_totalizer_before: number;
  secret_totalizer_after: number;
}

export interface DispenseCompleteResponse {
  success: boolean;
  transaction_id: number;
  status: string;
  actual_liters: number;
  requested_liters: number;
  partial: PartialDispenseOutcome | null;
  discrepancy_flag: string | null;
}

export interface NotificationGatewayRead {
  id: string;
  name: string;
  type: string;
  config_json: Record<string, unknown>;
  is_active: boolean;
  priority: number;
  created_at: string;
}

export interface NotificationGatewayCreatePayload {
  name: string;
  type: string;
  config_json?: Record<string, unknown>;
  is_active?: boolean;
  priority?: number;
}

export interface NotificationGatewayUpdatePayload {
  is_active?: boolean;
  priority?: number;
  config_json?: Record<string, unknown>;
}

export interface FuelTypeCreatePayload {
  code: string;
  name: string;
  base_density: number;
  thermal_expansion_coeff: number;
  max_vapor_pressure: number;
  viscosity_cst: number;
}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd web && npx vitest run src/lib/roles.test.ts src/lib/kpi.test.ts src/lib/allocProgress.test.ts
```

Expected: 11 passed

- [ ] **Step 5: Commit**

```bash
rtk git add web/src/lib/
rtk git commit -m "feat(web): add apiTypes for org/dispensing/admin + lib helpers + tests"
```

---

### Task 0.4: Frontend — API module split

**Files:**
- Create: `web/src/api/org.ts`, `dispensing.ts`, `admin.ts`, `monitoring.ts`
- Modify: `web/src/api/client.ts`

- [ ] **Step 1: Create org.ts**

Create `web/src/api/org.ts`:

```typescript
import type {
  Company, CompanyCreatePayload, Dispenser, DispenserCreatePayload,
  DispenserUpdatePayload, Site, SiteCreatePayload, Station, StationCreatePayload,
} from '../lib/apiTypes';
import { request } from './http';

const API = '/api/v1';

export const orgApi = {
  async listCompanies() { return request<Company[]>(`${API}/companies`); },
  async createCompany(p: CompanyCreatePayload) { return request<Company>(`${API}/companies`, { method: 'POST', body: JSON.stringify(p) }); },
  async updateCompany(id: string, p: CompanyCreatePayload) { return request<Company>(`${API}/companies/${id}`, { method: 'PATCH', body: JSON.stringify(p) }); },
  async deleteCompany(id: string) { await request<void>(`${API}/companies/${id}`, { method: 'DELETE' }); },
  async companySites(companyId: string) { return request<Site[]>(`${API}/companies/${companyId}/sites`); },
  async listSites(companyId?: string) { return request<Site[]>(companyId ? `${API}/companies/${companyId}/sites` : `${API}/sites`); },
  async createSite(p: SiteCreatePayload) { return request<Site>(`${API}/sites`, { method: 'POST', body: JSON.stringify(p) }); },
  async updateSite(id: string, p: SiteCreatePayload) { return request<Site>(`${API}/sites/${id}`, { method: 'PATCH', body: JSON.stringify(p) }); },
  async deleteSite(id: string) { await request<void>(`${API}/sites/${id}`, { method: 'DELETE' }); },
  async listStations(siteId?: string) { return request<Station[]>(`${API}/stations${siteId ? `?site_id=${siteId}` : ''}`); },
  async createStation(p: StationCreatePayload) { return request<Station>(`${API}/stations`, { method: 'POST', body: JSON.stringify(p) }); },
  async updateStation(id: string, p: StationCreatePayload) { return request<Station>(`${API}/stations/${id}`, { method: 'PATCH', body: JSON.stringify(p) }); },
  async deleteStation(id: string) { await request<void>(`${API}/stations/${id}`, { method: 'DELETE' }); },
  async listDispensers(stationId: string) { return request<Dispenser[]>(`${API}/stations/${stationId}/dispensers`); },
  async createDispenser(stationId: string, p: DispenserCreatePayload) { return request<Dispenser>(`${API}/stations/${stationId}/dispensers`, { method: 'POST', body: JSON.stringify(p) }); },
  async updateDispenser(stationId: string, dispenserId: string, p: DispenserUpdatePayload) { return request<Dispenser>(`${API}/stations/${stationId}/dispensers/${dispenserId}`, { method: 'PATCH', body: JSON.stringify(p) }); },
};
```

- [ ] **Step 2: Create dispensing.ts**

Create `web/src/api/dispensing.ts`:

```typescript
import type {
  AllocationRead, CodeValidateRequest, CodeValidateResponse,
  DispenseCompleteRequest, DispenseCompleteResponse, ExcelIngestOutcome, TransactionRead,
} from '../lib/apiTypes';
import { request } from './http';

const API = '/api/v1';

export const dispensingApi = {
  async listAllocations(limit = 100) { return request<AllocationRead[]>(`${API}/dispensing/allocations?max_rows=${limit}`); },
  async listTransactions(limit = 200, dispenserId?: string) {
    const p = new URLSearchParams({ limit: String(limit) });
    if (dispenserId) p.set('dispenser_id', dispenserId);
    return request<TransactionRead[]>(`${API}/dispensing/transactions?${p}`);
  },
  async uploadQuotaSheet(file: File, companyId: string, uploadedById: string) {
    const body = new FormData();
    body.append('file', file);
    body.append('company_id', companyId);
    body.append('uploaded_by_id', uploadedById);
    return request<ExcelIngestOutcome>(`${API}/dispensing/upload`, { method: 'POST', body });
  },
  async validateCode(p: CodeValidateRequest) { return request<CodeValidateResponse>(`${API}/dispensing/validate`, { method: 'POST', body: JSON.stringify(p) }); },
  async completeDispense(p: DispenseCompleteRequest) { return request<DispenseCompleteResponse>(`${API}/dispensing/complete`, { method: 'POST', body: JSON.stringify(p) }); },
};
```

- [ ] **Step 3: Create admin.ts**

Create `web/src/api/admin.ts`:

```typescript
import type { FuelType, FuelTypeCreatePayload, NotificationGatewayCreatePayload, NotificationGatewayRead, NotificationGatewayUpdatePayload } from '../lib/apiTypes';
import { request } from './http';

const API = '/api/v1';

export const adminApi = {
  async listFuelTypes() { return request<FuelType[]>(`${API}/fuel-types`); },
  async createFuelType(p: FuelTypeCreatePayload) { return request<FuelType>(`${API}/fuel-types`, { method: 'POST', body: JSON.stringify(p) }); },
  async listGateways() { return request<NotificationGatewayRead[]>(`${API}/notification-gateways`); },
  async createGateway(p: NotificationGatewayCreatePayload) { return request<NotificationGatewayRead>(`${API}/notification-gateways`, { method: 'POST', body: JSON.stringify(p) }); },
  async updateGateway(id: string, p: NotificationGatewayUpdatePayload) { return request<NotificationGatewayRead>(`${API}/notification-gateways/${id}`, { method: 'PATCH', body: JSON.stringify(p) }); },
  async deleteGateway(id: string) { await request<void>(`${API}/notification-gateways/${id}`, { method: 'DELETE' }); },
};
```

- [ ] **Step 4: Create monitoring.ts**

Create `web/src/api/monitoring.ts`:

```typescript
import type { StrappingTable, TotalizerPoint } from '../lib/apiTypes';
import { request } from './http';

const API = '/api/v1';

export const monitoringApi = {
  async listTotalizers(dispenserId?: string, start?: string, end?: string, limit = 1000) {
    const p = new URLSearchParams({ limit: String(limit) });
    if (dispenserId) p.set('dispenser_id', dispenserId);
    if (start) p.set('start', start);
    if (end) p.set('end', end);
    return request<TotalizerPoint[]>(`${API}/totalizers?${p}`);
  },
  async getStrapping(tankId: string) { return request<StrappingTable>(`${API}/tanks/${tankId}/strapping`); },
};
```

- [ ] **Step 5: Rewrite client.ts to import modules**

Replace `web/src/api/client.ts`:

```typescript
import type {
  AlarmSummary, TankCreatePayload, TankRead, TelemetryPoint, UserRead,
} from '../lib/apiTypes';
import { request, setOnUnauthorized, setTokenProvider } from './http';
import { orgApi } from './org';
import { dispensingApi } from './dispensing';
import { adminApi } from './admin';
import { monitoringApi } from './monitoring';

const API = '/api/v1';

export const api = {
  async login(username: string, password: string) {
    return request<{ access_token: string; token_type: string; user: UserRead }>(
      `${API}/auth/login`, { method: 'POST', body: JSON.stringify({ username, password }) },
    );
  },
  async me() { return request<UserRead>(`${API}/auth/me`); },
  async listTanks() { return request<TankRead[]>(`${API}/tanks`); },
  async getTank(id: string) { return request<TankRead>(`${API}/tanks/${id}`); },
  async createTank(payload: TankCreatePayload) { return request<TankRead>(`${API}/tanks`, { method: 'POST', body: JSON.stringify(payload) }); },
  async recentReadings(id: string, limit = 200) { return request<TelemetryPoint[]>(`${API}/tanks/${id}/recent?limit=${limit}`); },
  async rangeReadings(id: string, start: string, end: string, bucket = '5 minutes') {
    return request<TelemetryPoint[]>(`${API}/tanks/${id}/range?${new URLSearchParams({ start, end, bucket })}`);
  },
  async tankAlarms(id: string, openOnly = false, limit = 50) {
    const qs = new URLSearchParams({ limit: String(limit) });
    if (openOnly) qs.set('open_only', 'true');
    return request<AlarmSummary[]>(`${API}/tanks/${id}/alarms?${qs}`);
  },
  async ackAlarm(tankId: string, alarmId: string) {
    return request<{ alarm_id: string; acknowledged: boolean }>(`${API}/tanks/${tankId}/alarms/${alarmId}/ack`, { method: 'POST' });
  },
  ...orgApi,
  ...dispensingApi,
  ...adminApi,
  ...monitoringApi,
};

export { setOnUnauthorized, setTokenProvider };
```

- [ ] **Step 6: Run full frontend test suite**

```bash
cd web && npm test
```

- [ ] **Step 7: Commit**

```bash
rtk git add web/src/api/
rtk git commit -m "refactor(api): split client into org/dispensing/admin/monitoring modules"
```

---

### Task 0.5: Frontend — Shared UI components

**Files:**
- Create: `web/src/components/ui/Modal.tsx`
- Create: `web/src/components/ui/fields.tsx`
- Create: `web/src/components/ui/confirm.tsx`
- Create: `web/src/components/ui/badge.tsx`

- [ ] **Step 1: Create Modal.tsx**

```typescript
import type { ReactNode } from 'react';

export function Modal({ title, children, onClose, wide }: { title: string; children: ReactNode; onClose: () => void; wide?: boolean }) {
  return (
    <div className="fixed inset-0 bg-slate-900/40 flex items-center justify-center z-50">
      <div role="dialog" aria-modal="true" aria-label={title} onKeyDown={(e) => { if (e.key === 'Escape') onClose(); }}
        className={`bg-white rounded-lg shadow-xl w-full ${wide ? 'max-w-2xl' : 'max-w-lg'} p-6 space-y-3 max-h-[90vh] overflow-auto`}>
        <h3 className="text-lg font-semibold text-slate-800">{title}</h3>
        {children}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Create fields.tsx**

```typescript
import type { InputHTMLAttributes, ReactNode, SelectHTMLAttributes, TextareaHTMLAttributes } from 'react';

export function Field({ label, htmlFor, children }: { label: string; htmlFor: string; children: ReactNode }) {
  return (
    <div>
      <label htmlFor={htmlFor} className="block text-sm font-medium text-slate-700">{label}</label>
      {children}
    </div>
  );
}

const base = 'w-full border border-slate-300 rounded px-3 py-2 text-sm';

export function Input(props: InputHTMLAttributes<HTMLInputElement>) {
  return <input {...props} className={`${base} ${props.className ?? ''}`} />;
}

export function Select(props: SelectHTMLAttributes<HTMLSelectElement>) {
  return <select {...props} className={`${base} ${props.className ?? ''}`} />;
}

export function Textarea(props: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return <textarea {...props} className={`${base} min-h-[80px] font-mono text-xs ${props.className ?? ''}`} />;
}
```

- [ ] **Step 3: Create confirm.tsx**

```typescript
import { Modal } from './Modal';

export function ConfirmDialog({ title, message, confirmLabel, onCancel, onConfirm }: {
  title: string; message: string; confirmLabel: string; onCancel: () => void; onConfirm: () => void;
}) {
  return (
    <Modal title={title} onClose={onCancel}>
      <p className="text-sm text-slate-600">{message}</p>
      <div className="flex justify-end gap-2 pt-2">
        <button type="button" onClick={onCancel} className="px-3 py-2 text-sm text-slate-600">Cancel</button>
        <button type="button" onClick={onConfirm} className="bg-rose-600 text-white rounded px-3 py-2 text-sm font-medium">{confirmLabel}</button>
      </div>
    </Modal>
  );
}
```

- [ ] **Step 4: Create badge.tsx**

```typescript
export function Badge({ children, variant = 'default' }: { children: React.ReactNode; variant?: 'default' | 'success' | 'danger' | 'warning' | 'info' }) {
  const styles: Record<string, string> = {
    default: 'bg-slate-100 text-slate-600', success: 'bg-emerald-100 text-emerald-700',
    danger: 'bg-rose-100 text-rose-700', warning: 'bg-amber-100 text-amber-700', info: 'bg-sky-100 text-sky-700',
  };
  return <span className={`inline-block text-xs px-2 py-0.5 rounded-full font-medium ${styles[variant]}`}>{children}</span>;
}
```

- [ ] **Step 5: Commit**

```bash
rtk git add web/src/components/ui/
rtk git commit -m "feat(web): add shared UI components (Modal, fields, ConfirmDialog, Badge)"
```

---

### Task 0.6: Frontend — Grouped sidebar + role gating + router

**Files:**
- Modify: `web/src/components/layout/Sidebar.tsx`
- Create: `web/src/components/layout/Sidebar.test.tsx`
- Modify: `web/src/router.tsx`
- Create: `web/src/pages/AlarmCenter.tsx`, `FuelTypesPage.tsx`, `GatewaysPage.tsx` (stubs)

- [ ] **Step 1: Write failing test**

Create `web/src/components/layout/Sidebar.test.tsx`:

```typescript
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { Sidebar } from './Sidebar';
import { useAuthStore } from '../../store/auth';

vi.mock('../../hooks/useRealtimeAlarms', () => ({
  useRealtimeAlarms: () => [],
}));

describe('Sidebar', () => {
  beforeEach(() => {
    useAuthStore.setState({
      user: { id: 'u1', username: 'test', email: 't@t.io', first_name: null, last_name: null, role: 'viewer', is_active: true, phone: null, last_login: null, created_at: '2026-01-01T00:00:00Z' },
      token: 'tok',
    });
  });

  it('hides Operations and Admin sections for viewer', () => {
    render(<MemoryRouter><Sidebar /></MemoryRouter>);
    expect(screen.queryByText('Operations')).not.toBeInTheDocument();
    expect(screen.queryByText('Admin')).not.toBeInTheDocument();
    expect(screen.getByText('Dashboard')).toBeInTheDocument();
  });

  it('shows Operations and Admin for admin role', () => {
    useAuthStore.setState({
      user: { id: 'u1', username: 'admin', email: 'a@t.io', first_name: null, last_name: null, role: 'admin', is_active: true, phone: null, last_login: null, created_at: '2026-01-01T00:00:00Z' },
    });
    render(<MemoryRouter><Sidebar /></MemoryRouter>);
    expect(screen.getByText('Operations')).toBeInTheDocument();
    expect(screen.getByText('Admin')).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd web && npx vitest run src/components/layout/Sidebar.test.tsx
```

- [ ] **Step 3: Implement Sidebar**

Replace `web/src/components/layout/Sidebar.tsx`:

```typescript
import { NavLink } from 'react-router-dom';
import { useAuthStore } from '../../store/auth';
import { useRealtimeAlarms } from '../../hooks/useRealtimeAlarms';
import { canManage } from '../../lib/roles';

interface NavItem { to: string; label: string; }
interface NavGroup { label?: string; items: NavItem[]; manageOnly?: boolean; }

const groups: NavGroup[] = [
  { items: [{ to: '/dashboard', label: 'Dashboard' }] },
  { label: 'Monitoring', items: [
    { to: '/tanks', label: 'Tanks' },
    { to: '/dispensing', label: 'Dispensing' },
    { to: '/totalizers', label: 'Totalizers' },
    { to: '/alarms', label: 'Alarm Center' },
  ]},
  { label: 'Operations', manageOnly: true, items: [{ to: '/companies', label: 'Companies' }] },
  { label: 'Admin', manageOnly: true, items: [
    { to: '/admin/fuel-types', label: 'Fuel Types' },
    { to: '/admin/gateways', label: 'Gateways' },
  ]},
];

export function Sidebar() {
  const user = useAuthStore((s) => s.user);
  const logout = useAuthStore((s) => s.logout);
  const alarms = useRealtimeAlarms();
  const openCount = alarms.filter((a) => !a.acknowledged).length;
  const manage = canManage(user?.role);

  return (
    <aside className="w-56 shrink-0 bg-slate-900 text-slate-100 flex flex-col">
      <div className="px-4 py-5 border-b border-slate-800">
        <p className="font-bold tracking-tight">FuelOps SCADA</p>
        <p className="text-xs text-slate-400">{user?.username ?? ''}</p>
      </div>
      <nav className="flex-1 px-2 py-4 space-y-4">
        {groups.filter((g) => !g.manageOnly || manage).map((g) => (
          <div key={g.label ?? '__root__'}>
            {g.label ? <p className="px-3 mb-1 text-[11px] uppercase tracking-wider text-slate-500 font-semibold">{g.label}</p> : null}
            {g.items.map((l) => (
              <NavLink key={l.to} to={l.to} className={({ isActive }) => `block rounded px-3 py-1.5 text-sm ${isActive ? 'bg-brand text-white' : 'hover:bg-slate-800'}`}>
                {l.label}
                {l.to === '/dashboard' && openCount > 0 ? <span className="ml-2 inline-block w-2 h-2 rounded-full bg-rose-400" /> : null}
              </NavLink>
            ))}
          </div>
        ))}
      </nav>
      <div className="px-4 py-4 border-t border-slate-800">
        <button onClick={logout} className="text-sm text-slate-400 hover:text-white">Sign out</button>
      </div>
    </aside>
  );
}
```

- [ ] **Step 4: Create stub pages for routes that don't exist yet**

Create `web/src/pages/AlarmCenter.tsx`:
```typescript
export default function AlarmCenter() {
  return <p className="text-slate-500">Alarm Center — coming in Phase 2.</p>;
}
```

Create `web/src/pages/FuelTypesPage.tsx`:
```typescript
export default function FuelTypesPage() {
  return <p className="text-slate-500">Fuel Types — coming in Phase 3.</p>;
}
```

Create `web/src/pages/GatewaysPage.tsx`:
```typescript
export default function GatewaysPage() {
  return <p className="text-slate-500">Gateways — coming in Phase 3.</p>;
}
```

- [ ] **Step 5: Replace router.tsx**

Replace `web/src/router.tsx`:

```typescript
import React from 'react';
import { Navigate, createBrowserRouter } from 'react-router-dom';
import { isAuthed } from './lib/authGuard';
import { canManage } from './lib/roles';
import { useAuthStore } from './store/auth';
import { AppLayout } from './components/layout/AppLayout';
import Login from './pages/Login';
import Dashboard from './pages/Dashboard';
import Tanks from './pages/Tanks';
import TankDetail from './pages/TankDetail';
import Dispensing from './pages/Dispensing';
import Totalizers from './pages/Totalizers';
import AlarmCenter from './pages/AlarmCenter';
import CompaniesPage from './pages/CompaniesPage';
import SitesPage from './pages/SitesPage';
import StationsPage from './pages/StationsPage';
import DispensersPage from './pages/DispensersPage';
import FuelTypesPage from './pages/FuelTypesPage';
import GatewaysPage from './pages/GatewaysPage';

function RequireAuth({ children }: { children: React.ReactNode }) {
  const authed = isAuthed(useAuthStore((s) => s.token));
  if (!authed) return <Navigate to="/login" replace />;
  return <>{children}</>;
}

function RequireManage({ children }: { children: React.ReactNode }) {
  const role = useAuthStore((s) => s.user?.role);
  if (!canManage(role)) return <Navigate to="/dashboard" replace />;
  return <>{children}</>;
}

export const router = createBrowserRouter([
  { path: '/login', element: <Login /> },
  {
    path: '/',
    element: (<RequireAuth><AppLayout /></RequireAuth>),
    children: [
      { index: true, element: <Navigate to="/dashboard" replace /> },
      { path: 'dashboard', element: <Dashboard /> },
      { path: 'tanks', element: <Tanks /> },
      { path: 'tanks/:tankId', element: <TankDetail /> },
      { path: 'dispensing', element: <Dispensing /> },
      { path: 'totalizers', element: <Totalizers /> },
      { path: 'alarms', element: <AlarmCenter /> },
      { path: 'companies', element: <RequireManage><CompaniesPage /></RequireManage> },
      { path: 'sites', element: <RequireManage><SitesPage /></RequireManage> },
      { path: 'stations/:siteId', element: <RequireManage><StationsPage /></RequireManage> },
      { path: 'dispensers/:stationId', element: <RequireManage><DispensersPage /></RequireManage> },
      { path: 'admin/fuel-types', element: <RequireManage><FuelTypesPage /></RequireManage> },
      { path: 'admin/gateways', element: <RequireManage><GatewaysPage /></RequireManage> },
    ],
  },
  { path: '*', element: <Navigate to="/dashboard" replace /> },
]);
```

- [ ] **Step 6: Run sidebar test + full suite**

```bash
cd web && npx vitest run src/components/layout/Sidebar.test.tsx && npm test
```

- [ ] **Step 7: Commit**

```bash
rtk git add web/src/components/layout/ web/src/router.tsx web/src/pages/AlarmCenter.tsx web/src/pages/FuelTypesPage.tsx web/src/pages/GatewaysPage.tsx
rtk git commit -m "feat(web): grouped sidebar with role gating + routed org/admin pages"
```

---

## Part 1: Organization Management

### Task 1.1: Companies page

**Files:**
- Replace: `web/src/pages/CompaniesPage.tsx`
- Create: `web/src/pages/CompaniesPage.test.tsx`

- [ ] **Step 1: Write failing test**

Create `web/src/pages/CompaniesPage.test.tsx`:

```typescript
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, expect, it, vi, beforeEach } from 'vitest';

vi.mock('../api/client', () => ({
  api: { listCompanies: vi.fn(), createCompany: vi.fn(), updateCompany: vi.fn(), deleteCompany: vi.fn() },
}));
import { api } from '../api/client';
import CompaniesPage from './CompaniesPage';

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(<QueryClientProvider client={qc}><MemoryRouter><CompaniesPage /></MemoryRouter></QueryClientProvider>);
}

const co = { id: 'c1', name: 'Acme', address: 'Kampala', contact_name: 'Ali', contact_email: 'a@x.io', contact_phone: '7001', created_at: '2026-01-01T00:00:00Z' };

describe('CompaniesPage', () => {
  beforeEach(() => { vi.mocked(api.listCompanies).mockResolvedValue([co] as never); });

  it('renders company list', async () => {
    renderPage();
    expect(await screen.findByText('Acme')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /new company/i })).toBeInTheDocument();
  });

  it('opens create dialog and submits', async () => {
    vi.mocked(api.createCompany).mockResolvedValue({ id: 'c2', name: 'NewCo', address: null, contact_name: null, contact_email: null, contact_phone: null, created_at: '2026-01-02T00:00:00Z' } as never);
    renderPage();
    await userEvent.click(await screen.findByRole('button', { name: /new company/i }));
    await userEvent.type(screen.getByLabelText(/name/i), 'NewCo');
    await userEvent.click(screen.getByRole('button', { name: /^create$/i }));
    await waitFor(() => expect(api.createCompany).toHaveBeenCalledWith(expect.objectContaining({ name: 'NewCo' })));
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd web && npx vitest run src/pages/CompaniesPage.test.tsx
```

- [ ] **Step 3: Implement CompaniesPage**

Replace `web/src/pages/CompaniesPage.tsx`:

```typescript
import { FormEvent, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { ApiError } from '../api/http';
import { api } from '../api/client';
import type { Company } from '../lib/apiTypes';
import { Modal } from '../components/ui/Modal';
import { Field, Input } from '../components/ui/fields';
import { ConfirmDialog } from '../components/ui/confirm';

export default function CompaniesPage() {
  const companies = useQuery({ queryKey: ['companies'], queryFn: () => api.listCompanies() });
  const [creating, setCreating] = useState(false);
  const [editing, setEditing] = useState<Company | null>(null);
  const [deleting, setDeleting] = useState<Company | null>(null);

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-2xl font-semibold text-slate-800">Companies</h2>
        <button onClick={() => setCreating(true)} className="bg-brand text-white rounded px-3 py-2 text-sm font-medium">New company</button>
      </div>
      <div className="bg-white rounded-lg border border-slate-200 overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-slate-500"><tr>
            <th className="text-left px-4 py-2">Name</th>
            <th className="text-left px-4 py-2">Contact</th>
            <th className="text-left px-4 py-2">Email</th>
            <th className="text-left px-4 py-2">Phone</th>
            <th className="text-right px-4 py-2"></th>
          </tr></thead>
          <tbody>
            {(companies.data ?? []).map((c) => (
              <tr key={c.id} className="border-t border-slate-100">
                <td className="px-4 py-2"><Link to={`/sites?company=${c.id}`} className="font-medium text-brand-dark hover:underline">{c.name}</Link></td>
                <td className="px-4 py-2 text-slate-600">{c.contact_name ?? '—'}</td>
                <td className="px-4 py-2 text-slate-600">{c.contact_email ?? '—'}</td>
                <td className="px-4 py-2 text-slate-600">{c.contact_phone ?? '—'}</td>
                <td className="px-4 py-2 text-right space-x-3">
                  <button onClick={() => setEditing(c)} className="text-sm text-slate-600 hover:text-brand-dark">Edit</button>
                  <button onClick={() => setDeleting(c)} className="text-sm text-rose-600">Delete</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {creating ? <CompanyDialog onClose={() => setCreating(false)} /> : null}
      {editing ? <CompanyDialog initial={editing} onClose={() => setEditing(null)} /> : null}
      {deleting ? <DeleteCompany company={deleting} onCancel={() => setDeleting(null)} /> : null}
    </div>
  );
}

function CompanyDialog({ initial, onClose }: { initial?: Company; onClose: () => void }) {
  const qc = useQueryClient();
  const [form, setForm] = useState({ name: initial?.name ?? '', address: initial?.address ?? '', contact_name: initial?.contact_name ?? '', contact_email: initial?.contact_email ?? '', contact_phone: initial?.contact_phone ?? '' });
  const [error, setError] = useState<string | null>(null);
  const set = (k: keyof typeof form) => (e: { target: { value: string } }) => setForm((f) => ({ ...f, [k]: e.target.value }));
  const mutation = useMutation({
    mutationFn: () => {
      const p = { name: form.name, address: form.address || null, contact_name: form.contact_name || null, contact_email: form.contact_email || null, contact_phone: form.contact_phone || null };
      return initial ? api.updateCompany(initial.id, p) : api.createCompany(p);
    },
    onSuccess: () => { void qc.invalidateQueries({ queryKey: ['companies'] }); onClose(); },
    onError: (err) => setError(err instanceof ApiError ? err.detail : 'Save failed'),
  });
  return (
    <Modal title={initial ? 'Edit company' : 'New company'} onClose={onClose}>
      <form onSubmit={(e: FormEvent) => { e.preventDefault(); mutation.mutate(); }} className="space-y-3">
        <Field label="Name" htmlFor="co-name"><Input id="co-name" autoFocus value={form.name} onChange={set('name')} required /></Field>
        <Field label="Address" htmlFor="co-address"><Input id="co-address" value={form.address} onChange={set('address')} /></Field>
        <Field label="Contact name" htmlFor="co-contact"><Input id="co-contact" value={form.contact_name} onChange={set('contact_name')} /></Field>
        <Field label="Email" htmlFor="co-email"><Input id="co-email" type="email" value={form.contact_email} onChange={set('contact_email')} /></Field>
        <Field label="Phone" htmlFor="co-phone"><Input id="co-phone" value={form.contact_phone} onChange={set('contact_phone')} /></Field>
        {error ? <p className="text-sm text-red-600">{error}</p> : null}
        <div className="flex justify-end gap-2 pt-2">
          <button type="button" onClick={onClose} className="px-3 py-2 text-sm text-slate-600">Cancel</button>
          <button type="submit" disabled={mutation.isPending} className="bg-brand text-white rounded px-3 py-2 text-sm font-medium disabled:opacity-50">{initial ? 'Save' : 'Create'}</button>
        </div>
      </form>
    </Modal>
  );
}

function DeleteCompany({ company, onCancel }: { company: Company; onCancel: () => void }) {
  const qc = useQueryClient();
  const mutate = useMutation({ mutationFn: () => api.deleteCompany(company.id), onSuccess: () => { void qc.invalidateQueries({ queryKey: ['companies'] }); onCancel(); } });
  return <ConfirmDialog title="Delete company" message={`Delete "${company.name}"?`} confirmLabel="Delete" onCancel={onCancel} onConfirm={() => mutate.mutate()} />;
}
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd web && npx vitest run src/pages/CompaniesPage.test.tsx
```

- [ ] **Step 5: Commit**

```bash
rtk git add web/src/pages/CompaniesPage.tsx web/src/pages/CompaniesPage.test.tsx
rtk git commit -m "feat(web): CompaniesPage with create/edit/delete dialogs"
```

---

### Task 1.2: Sites page

**Files:**
- Replace: `web/src/pages/SitesPage.tsx`
- Create: `web/src/pages/SitesPage.test.tsx`

- [ ] **Step 1: Write failing test**

Create `web/src/pages/SitesPage.test.tsx`:

```typescript
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, expect, it, vi, beforeEach } from 'vitest';

vi.mock('../api/client', () => ({
  api: { listSites: vi.fn(), listCompanies: vi.fn(), createSite: vi.fn(), updateSite: vi.fn(), deleteSite: vi.fn() },
}));
import { api } from '../api/client';
import SitesPage from './SitesPage';

function renderPage(route = '/sites') {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(<QueryClientProvider client={qc}><MemoryRouter initialEntries={[route]}><SitesPage /></MemoryRouter></QueryClientProvider>);
}

describe('SitesPage', () => {
  beforeEach(() => {
    vi.mocked(api.listCompanies).mockResolvedValue([{ id: 'c1', name: 'Acme', address: null, contact_name: null, contact_email: null, contact_phone: null, created_at: '2026-01-01T00:00:00Z' }] as never);
    vi.mocked(api.listSites).mockResolvedValue([{ id: 's1', name: 'Kampala Depot', company_id: 'c1', address: 'Kampala', location: null, is_active: true, created_at: '2026-01-01T00:00:00Z' }] as never);
  });

  it('renders site list', async () => {
    renderPage();
    expect(await screen.findByText('Kampala Depot')).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd web && npx vitest run src/pages/SitesPage.test.tsx
```

- [ ] **Step 3: Implement SitesPage**

Replace `web/src/pages/SitesPage.tsx`:

```typescript
import { FormEvent, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ApiError } from '../api/http';
import { api } from '../api/client';
import type { Company, Site } from '../lib/apiTypes';
import { Badge } from '../components/ui/badge';
import { Modal } from '../components/ui/Modal';
import { Field, Input, Select } from '../components/ui/fields';
import { ConfirmDialog } from '../components/ui/confirm';

export default function SitesPage() {
  const [params] = useSearchParams();
  const companyId = params.get('company') ?? '';
  const companies = useQuery({ queryKey: ['companies'], queryFn: () => api.listCompanies() });
  const sites = useQuery({ queryKey: ['sites', companyId], queryFn: () => api.listSites(companyId || undefined) });
  const [creating, setCreating] = useState(false);
  const [editing, setEditing] = useState<Site | null>(null);
  const [deleting, setDeleting] = useState<Site | null>(null);
  const company = companies.data?.find((c) => c.id === companyId);

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          {company ? <Link to="/companies" className="text-sm text-slate-500 hover:text-slate-700 mb-1 inline-block">← Companies</Link> : null}
          <h2 className="text-2xl font-semibold text-slate-800">{company ? `${company.name} — Sites` : 'All Sites'}</h2>
        </div>
        <button onClick={() => setCreating(true)} className="bg-brand text-white rounded px-3 py-2 text-sm font-medium">New site</button>
      </div>
      <div className="bg-white rounded-lg border border-slate-200 overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-slate-500"><tr>
            <th className="text-left px-4 py-2">Name</th><th className="text-left px-4 py-2">Address</th><th className="text-left px-4 py-2">Location</th><th className="text-left px-4 py-2">Status</th><th className="text-right px-4 py-2"></th>
          </tr></thead>
          <tbody>
            {(sites.data ?? []).map((s) => (
              <tr key={s.id} className="border-t border-slate-100">
                <td className="px-4 py-2"><Link to={`/stations/${s.id}`} className="font-medium text-brand-dark hover:underline">{s.name}</Link></td>
                <td className="px-4 py-2 text-slate-600">{s.address ?? '—'}</td>
                <td className="px-4 py-2 text-slate-600">{s.location ?? '—'}</td>
                <td className="px-4 py-2"><Badge variant={s.is_active ? 'success' : 'default'}>{s.is_active ? 'Active' : 'Inactive'}</Badge></td>
                <td className="px-4 py-2 text-right space-x-3">
                  <button onClick={() => setEditing(s)} className="text-sm text-slate-600 hover:text-brand-dark">Edit</button>
                  <button onClick={() => setDeleting(s)} className="text-sm text-rose-600">Delete</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {creating ? <SiteDialog defaultCompanyId={companyId} companies={companies.data ?? []} onClose={() => setCreating(false)} /> : null}
      {editing ? <SiteDialog initial={editing} defaultCompanyId={companyId} companies={companies.data ?? []} onClose={() => setEditing(null)} /> : null}
      {deleting ? <DeleteSite site={deleting} onCancel={() => setDeleting(null)} /> : null}
    </div>
  );
}

function SiteDialog({ initial, defaultCompanyId, companies, onClose }: { initial?: Site; defaultCompanyId: string; companies: Company[]; onClose: () => void }) {
  const qc = useQueryClient();
  const [form, setForm] = useState({ name: initial?.name ?? '', company_id: initial?.company_id ?? defaultCompanyId || companies[0]?.id ?? '', address: initial?.address ?? '', location: initial?.location ?? '' });
  const [error, setError] = useState<string | null>(null);
  const set = (k: keyof typeof form) => (e: { target: { value: string } }) => setForm((f) => ({ ...f, [k]: e.target.value }));
  const mutation = useMutation({
    mutationFn: () => { const p = { name: form.name, company_id: form.company_id, address: form.address || null, location: form.location || null, is_active: initial?.is_active ?? true }; return initial ? api.updateSite(initial.id, p) : api.createSite(p); },
    onSuccess: () => { void qc.invalidateQueries({ queryKey: ['sites'] }); onClose(); },
    onError: (err) => setError(err instanceof ApiError ? err.detail : 'Save failed'),
  });
  return (
    <Modal title={initial ? 'Edit site' : 'New site'} onClose={onClose}>
      <form onSubmit={(e: FormEvent) => { e.preventDefault(); mutation.mutate(); }} className="space-y-3">
        <Field label="Name" htmlFor="site-name"><Input id="site-name" autoFocus value={form.name} onChange={set('name')} required /></Field>
        <Field label="Company" htmlFor="site-company"><Select id="site-company" value={form.company_id} onChange={set('company_id')} required><option value="">Select…</option>{companies.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</Select></Field>
        <Field label="Address" htmlFor="site-address"><Input id="site-address" value={form.address} onChange={set('address')} /></Field>
        <Field label="Location" htmlFor="site-location"><Input id="site-location" value={form.location} onChange={set('location')} /></Field>
        {error ? <p className="text-sm text-red-600">{error}</p> : null}
        <div className="flex justify-end gap-2 pt-2">
          <button type="button" onClick={onClose} className="px-3 py-2 text-sm text-slate-600">Cancel</button>
          <button type="submit" disabled={mutation.isPending} className="bg-brand text-white rounded px-3 py-2 text-sm font-medium disabled:opacity-50">{initial ? 'Save' : 'Create'}</button>
        </div>
      </form>
    </Modal>
  );
}

function DeleteSite({ site, onCancel }: { site: Site; onCancel: () => void }) {
  const qc = useQueryClient();
  const mutate = useMutation({ mutationFn: () => api.deleteSite(site.id), onSuccess: () => { void qc.invalidateQueries({ queryKey: ['sites'] }); onCancel(); } });
  return <ConfirmDialog title="Delete site" message={`Delete "${site.name}"?`} confirmLabel="Delete" onCancel={onCancel} onConfirm={() => mutate.mutate()} />;
}
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd web && npx vitest run src/pages/SitesPage.test.tsx
```

- [ ] **Step 5: Commit**

```bash
rtk git add web/src/pages/SitesPage.tsx web/src/pages/SitesPage.test.tsx
rtk git commit -m "feat(web): SitesPage with create/edit/delete dialogs"
```

---

### Task 1.3: Stations page

**Files:**
- Create: `web/src/pages/StationsPage.tsx`
- Create: `web/src/pages/StationsPage.test.tsx`

- [ ] **Step 1: Write failing test**

Create `web/src/pages/StationsPage.test.tsx`:

```typescript
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, expect, it, vi, beforeEach } from 'vitest';

vi.mock('../api/client', () => ({
  api: { listStations: vi.fn(), createStation: vi.fn(), deleteStation: vi.fn() },
}));
import { api } from '../api/client';
import StationsPage from './StationsPage';

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(<QueryClientProvider client={qc}><MemoryRouter initialEntries={['/stations/s1']}><StationsPage /></MemoryRouter></QueryClientProvider>);
}

describe('StationsPage', () => {
  beforeEach(() => {
    vi.mocked(api.listStations).mockResolvedValue([{ id: 'st1', name: 'Station A', site_id: 's1', serial_number: 'SN1', raspberry_pi_id: 'rpi1', firmware_version: '1.0', connection_status: 'online', last_heartbeat: '2026-09-08T10:00:00Z' }] as never);
  });

  it('renders stations list', async () => {
    renderPage();
    expect(await screen.findByText('Station A')).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd web && npx vitest run src/pages/StationsPage.test.tsx
```

- [ ] **Step 3: Implement StationsPage**

Create `web/src/pages/StationsPage.tsx`:

```typescript
import { FormEvent, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ApiError } from '../api/http';
import { api } from '../api/client';
import type { Station } from '../lib/apiTypes';
import { Badge } from '../components/ui/badge';
import { Modal } from '../components/ui/Modal';
import { Field, Input } from '../components/ui/fields';
import { ConfirmDialog } from '../components/ui/confirm';

export default function StationsPage() {
  const { siteId = '' } = useParams();
  const qc = useQueryClient();
  const stations = useQuery({ queryKey: ['stations', siteId], queryFn: () => api.listStations(siteId), enabled: Boolean(siteId) });
  const [creating, setCreating] = useState(false);
  const [editing, setEditing] = useState<Station | null>(null);
  const [deleting, setDeleting] = useState<Station | null>(null);

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <Link to="/companies" className="text-sm text-slate-500 hover:text-slate-700 mb-1 inline-block">← Companies</Link>
          <h2 className="text-2xl font-semibold text-slate-800">Stations</h2>
        </div>
        <button onClick={() => setCreating(true)} className="bg-brand text-white rounded px-3 py-2 text-sm font-medium">New station</button>
      </div>
      <div className="bg-white rounded-lg border border-slate-200 overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-slate-500"><tr>
            <th className="text-left px-4 py-2">Name</th><th className="text-left px-4 py-2">Serial</th><th className="text-left px-4 py-2">RPi</th><th className="text-left px-4 py-2">Firmware</th><th className="text-left px-4 py-2">Status</th><th className="text-right px-4 py-2"></th>
          </tr></thead>
          <tbody>
            {(stations.data ?? []).map((s) => (
              <tr key={s.id} className="border-t border-slate-100">
                <td className="px-4 py-2"><Link to={`/dispensers/${s.id}`} className="font-medium text-brand-dark hover:underline">{s.name}</Link></td>
                <td className="px-4 py-2 text-slate-600">{s.serial_number}</td>
                <td className="px-4 py-2 text-slate-600">{s.raspberry_pi_id ?? '—'}</td>
                <td className="px-4 py-2 text-slate-600">{s.firmware_version ?? '—'}</td>
                <td className="px-4 py-2"><Badge variant={s.connection_status === 'online' ? 'success' : 'danger'}>{s.connection_status}</Badge></td>
                <td className="px-4 py-2 text-right space-x-3">
                  <button onClick={() => setEditing(s)} className="text-sm text-slate-600 hover:text-brand-dark">Edit</button>
                  <button onClick={() => setDeleting(s)} className="text-sm text-rose-600">Delete</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {creating ? <StationDialog siteId={siteId} onClose={() => setCreating(false)} /> : null}
      {editing ? <StationDialog initial={editing} siteId={siteId} onClose={() => setEditing(null)} /> : null}
      {deleting ? <DeleteStation station={deleting} onCancel={() => setDeleting(null)} /> : null}
    </div>
  );
}

function StationDialog({ initial, siteId, onClose }: { initial?: Station; siteId: string; onClose: () => void }) {
  const qc = useQueryClient();
  const [form, setForm] = useState({ name: initial?.name ?? '', serial_number: initial?.serial_number ?? '', raspberry_pi_id: initial?.raspberry_pi_id ?? '', firmware_version: initial?.firmware_version ?? '' });
  const [error, setError] = useState<string | null>(null);
  const set = (k: keyof typeof form) => (e: { target: { value: string } }) => setForm((f) => ({ ...f, [k]: e.target.value }));
  const mutation = useMutation({
    mutationFn: () => { const p = { name: form.name, site_id: siteId, serial_number: form.serial_number, raspberry_pi_id: form.raspberry_pi_id || null, firmware_version: form.firmware_version || null }; return initial ? api.updateStation(initial.id, p) : api.createStation(p); },
    onSuccess: () => { void qc.invalidateQueries({ queryKey: ['stations'] }); onClose(); },
    onError: (err) => setError(err instanceof ApiError ? err.detail : 'Save failed'),
  });
  return (
    <Modal title={initial ? 'Edit station' : 'New station'} onClose={onClose}>
      <form onSubmit={(e: FormEvent) => { e.preventDefault(); mutation.mutate(); }} className="space-y-3">
        <Field label="Name" htmlFor="st-name"><Input id="st-name" autoFocus value={form.name} onChange={set('name')} required /></Field>
        <Field label="Serial number" htmlFor="st-serial"><Input id="st-serial" value={form.serial_number} onChange={set('serial_number')} required /></Field>
        <Field label="Raspberry Pi ID" htmlFor="st-rpi"><Input id="st-rpi" value={form.raspberry_pi_id} onChange={set('raspberry_pi_id')} /></Field>
        <Field label="Firmware version" htmlFor="st-fw"><Input id="st-fw" value={form.firmware_version} onChange={set('firmware_version')} /></Field>
        {error ? <p className="text-sm text-red-600">{error}</p> : null}
        <div className="flex justify-end gap-2 pt-2">
          <button type="button" onClick={onClose} className="px-3 py-2 text-sm text-slate-600">Cancel</button>
          <button type="submit" disabled={mutation.isPending} className="bg-brand text-white rounded px-3 py-2 text-sm font-medium disabled:opacity-50">{initial ? 'Save' : 'Create'}</button>
        </div>
      </form>
    </Modal>
  );
}

function DeleteStation({ station, onCancel }: { station: Station; onCancel: () => void }) {
  const qc = useQueryClient();
  const mutate = useMutation({ mutationFn: () => api.deleteStation(station.id), onSuccess: () => { void qc.invalidateQueries({ queryKey: ['stations'] }); onCancel(); } });
  return <ConfirmDialog title="Delete station" message={`Delete "${station.name}"?`} confirmLabel="Delete" onCancel={onCancel} onConfirm={() => mutate.mutate()} />;
}
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd web && npx vitest run src/pages/StationsPage.test.tsx
```

- [ ] **Step 5: Commit**

```bash
rtk git add web/src/pages/StationsPage.tsx web/src/pages/StationsPage.test.tsx
rtk git commit -m "feat(web): StationsPage with create/edit/delete dialogs"
```

---

### Task 1.4: Dispensers page

**Files:**
- Create: `web/src/pages/DispensersPage.tsx`
- Create: `web/src/pages/DispensersPage.test.tsx`

- [ ] **Step 1: Write failing test**

Create `web/src/pages/DispensersPage.test.tsx`:

```typescript
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, expect, it, vi, beforeEach } from 'vitest';

vi.mock('../api/client', () => ({
  api: { listDispensers: vi.fn(), createDispenser: vi.fn(), updateDispenser: vi.fn() },
}));
import { api } from '../api/client';
import DispensersPage from './DispensersPage';

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(<QueryClientProvider client={qc}><MemoryRouter initialEntries={['/dispensers/st1']}><DispensersPage /></MemoryRouter></QueryClientProvider>);
}

describe('DispensersPage', () => {
  beforeEach(() => {
    vi.mocked(api.listDispensers).mockResolvedValue([{ id: 'd1', name: 'Pump 1', station_id: 'st1', serial_number: 'DN1', modbus_address: 1, dispenser_model: 'X200', is_active: true }] as never);
  });

  it('renders dispensers with active toggle', async () => {
    vi.mocked(api.updateDispenser).mockResolvedValue({ id: 'd1', name: 'Pump 1', station_id: 'st1', serial_number: 'DN1', modbus_address: 1, dispenser_model: 'X200', is_active: false } as never);
    renderPage();
    expect(await screen.findByText('Pump 1')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: /deactivate/i }));
    await waitFor(() => expect(api.updateDispenser).toHaveBeenCalledWith('st1', 'd1', { is_active: false }));
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd web && npx vitest run src/pages/DispensersPage.test.tsx
```

- [ ] **Step 3: Implement DispensersPage**

Create `web/src/pages/DispensersPage.tsx`:

```typescript
import { FormEvent, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ApiError } from '../api/http';
import { api } from '../api/client';
import type { Dispenser } from '../lib/apiTypes';
import { Badge } from '../components/ui/badge';
import { Modal } from '../components/ui/Modal';
import { Field, Input } from '../components/ui/fields';

export default function DispensersPage() {
  const { stationId = '' } = useParams();
  const qc = useQueryClient();
  const dispensers = useQuery({ queryKey: ['dispensers', stationId], queryFn: () => api.listDispensers(stationId), enabled: Boolean(stationId) });
  const [creating, setCreating] = useState(false);
  const toggle = useMutation({ mutationFn: (d: Dispenser) => api.updateDispenser(stationId, d.id, { is_active: !d.is_active }), onSuccess: () => void qc.invalidateQueries({ queryKey: ['dispensers', stationId] }) });

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <Link to="/companies" className="text-sm text-slate-500 hover:text-slate-700 mb-1 inline-block">← Companies</Link>
          <h2 className="text-2xl font-semibold text-slate-800">Dispensers</h2>
        </div>
        <button onClick={() => setCreating(true)} className="bg-brand text-white rounded px-3 py-2 text-sm font-medium">New dispenser</button>
      </div>
      <div className="bg-white rounded-lg border border-slate-200 overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-slate-500"><tr>
            <th className="text-left px-4 py-2">Name</th><th className="text-left px-4 py-2">Serial</th><th className="text-left px-4 py-2">Modbus</th><th className="text-left px-4 py-2">Model</th><th className="text-left px-4 py-2">Active</th><th className="text-right px-4 py-2"></th>
          </tr></thead>
          <tbody>
            {(dispensers.data ?? []).map((d) => (
              <tr key={d.id} className="border-t border-slate-100">
                <td className="px-4 py-2 font-medium text-slate-700">{d.name}</td>
                <td className="px-4 py-2 text-slate-600">{d.serial_number}</td>
                <td className="px-4 py-2 text-slate-600">{d.modbus_address}</td>
                <td className="px-4 py-2 text-slate-600">{d.dispenser_model ?? '—'}</td>
                <td className="px-4 py-2"><Badge variant={d.is_active ? 'success' : 'default'}>{d.is_active ? 'Active' : 'Inactive'}</Badge></td>
                <td className="px-4 py-2 text-right">
                  <button onClick={() => toggle.mutate(d)} className={`text-sm ${d.is_active ? 'text-amber-600' : 'text-emerald-600'}`}>{d.is_active ? 'Deactivate' : 'Activate'}</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {creating ? <DispenserDialog stationId={stationId} onClose={() => setCreating(false)} /> : null}
    </div>
  );
}

function DispenserDialog({ stationId, onClose }: { stationId: string; onClose: () => void }) {
  const qc = useQueryClient();
  const [form, setForm] = useState({ name: '', serial_number: '', modbus_address: '1', dispenser_model: '' });
  const [error, setError] = useState<string | null>(null);
  const set = (k: keyof typeof form) => (e: { target: { value: string } }) => setForm((f) => ({ ...f, [k]: e.target.value }));
  const mutation = useMutation({
    mutationFn: () => api.createDispenser(stationId, { name: form.name, serial_number: form.serial_number, modbus_address: Number(form.modbus_address) || 1, dispenser_model: form.dispenser_model || null }),
    onSuccess: () => { void qc.invalidateQueries({ queryKey: ['dispensers', stationId] }); onClose(); },
    onError: (err) => setError(err instanceof ApiError ? err.detail : 'Save failed'),
  });
  return (
    <Modal title="New dispenser" onClose={onClose}>
      <form onSubmit={(e: FormEvent) => { e.preventDefault(); mutation.mutate(); }} className="space-y-3">
        <Field label="Name" htmlFor="disp-name"><Input id="disp-name" autoFocus value={form.name} onChange={set('name')} required /></Field>
        <Field label="Serial number" htmlFor="disp-serial"><Input id="disp-serial" value={form.serial_number} onChange={set('serial_number')} required /></Field>
        <Field label="Modbus address" htmlFor="disp-modbus"><Input id="disp-modbus" type="number" min="1" max="247" value={form.modbus_address} onChange={set('modbus_address')} required /></Field>
        <Field label="Model" htmlFor="disp-model"><Input id="disp-model" value={form.dispenser_model} onChange={set('dispenser_model')} /></Field>
        {error ? <p className="text-sm text-red-600">{error}</p> : null}
        <div className="flex justify-end gap-2 pt-2">
          <button type="button" onClick={onClose} className="px-3 py-2 text-sm text-slate-600">Cancel</button>
          <button type="submit" disabled={mutation.isPending} className="bg-brand text-white rounded px-3 py-2 text-sm font-medium disabled:opacity-50">Create</button>
        </div>
      </form>
    </Modal>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd web && npx vitest run src/pages/DispensersPage.test.tsx
```

- [ ] **Step 5: Commit**

```bash
rtk git add web/src/pages/DispensersPage.tsx web/src/pages/DispensersPage.test.tsx
rtk git commit -m "feat(web): DispensersPage with create dialog + active toggle"
```

---

### Task 1.5: Tanks page — add site filter

**Files:**
- Modify: `web/src/pages/Tanks.tsx`

- [ ] **Step 1: Add site filter dropdown**

In `web/src/pages/Tanks.tsx`, add after `const [creating, setCreating] = useState(false);` (line 34):

```typescript
const [siteFilter, setSiteFilter] = useState('');
```

After the heading row (line 43), before the table div, insert:

```tsx
<div className="flex gap-4 mb-4 items-center">
  <div>
    <label htmlFor="tank-site-filter" className="block text-sm font-medium text-slate-700 mb-1">Site</label>
    <select id="tank-site-filter" className="border border-slate-300 rounded px-3 py-2 text-sm" value={siteFilter} onChange={(e) => setSiteFilter(e.target.value)}>
      <option value="">All sites</option>
      {(sites.data ?? []).map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
    </select>
  </div>
</div>
```

Update table body to filter:

```tsx
{(tanks.data ?? [])
  .filter((t) => !siteFilter || t.site_id === siteFilter)
  .map((t) => <TankRowT key={t.id} tank={t} fuels={fuels.data ?? []} />)}
```

- [ ] **Step 2: Run full test suite**

```bash
cd web && npm test
```

- [ ] **Step 3: Commit**

```bash
rtk git add web/src/pages/Tanks.tsx
rtk git commit -m "feat(web): add site filter dropdown to Tanks page"
```

---

## Part 2: Dispensing Workflow

### Task 2.1: Allocations table card

**Files:**
- Create: `web/src/components/dispensing/AllocationsCard.tsx`
- Create: `web/src/components/dispensing/AllocationsCard.test.tsx`

- [ ] **Step 1: Write failing test**

Create `web/src/components/dispensing/AllocationsCard.test.tsx`:

```typescript
import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, expect, it, vi, beforeEach } from 'vitest';

vi.mock('../../api/client', () => ({ api: { listAllocations: vi.fn() } }));
import { api } from '../../api/client';
import { AllocationsCard } from './AllocationsCard';

function renderCard() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}><AllocationsCard /></QueryClientProvider>);
}

describe('AllocationsCard', () => {
  beforeEach(() => {
    vi.mocked(api.listAllocations).mockResolvedValue([{
      id: 'a1', employee_id: 'E1', employee_name: 'Ali', invoice_number: 'INV-001',
      allocated_liters: 100, dispensed_liters: 40, remaining_liters: 60,
      status: 'IN_PROGRESS', created_at: '2026-09-08T10:00:00Z',
    }] as never);
  });

  it('renders allocation row with progress', async () => {
    renderCard();
    expect(await screen.findByText('Ali')).toBeInTheDocument();
    expect(screen.getByText('INV-001')).toBeInTheDocument();
    expect(screen.getByText('40.0 L')).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd web && npx vitest run src/components/dispensing/AllocationsCard.test.tsx
```

- [ ] **Step 3: Implement AllocationsCard**

Create `web/src/components/dispensing/AllocationsCard.tsx`:

```typescript
import { useQuery } from '@tanstack/react-query';
import { api } from '../../api/client';
import { formatLiters, formatRemaining, statusColor } from '../../lib/dispenseFormat';
import { progressPercent } from '../../lib/allocProgress';

export function AllocationsCard() {
  const allocations = useQuery({ queryKey: ['allocations'], queryFn: () => api.listAllocations(200), refetchInterval: 10_000 });
  return (
    <div className="bg-white rounded-lg border border-slate-200 p-4">
      <h3 className="font-semibold text-slate-800 mb-3">Allocations</h3>
      <table className="w-full text-sm">
        <thead><tr className="text-left text-slate-500">
          <th className="py-1 pr-2">Employee</th><th className="py-1 pr-2">Invoice</th><th className="py-1 pr-2">Dispensed</th><th className="py-1 pr-2">Remaining</th><th className="py-1 pr-2">Progress</th><th className="py-1">Status</th>
        </tr></thead>
        <tbody>
          {(allocations.data ?? []).map((a) => (
            <tr key={a.id} className="border-t border-slate-100">
              <td className="py-1 pr-2 font-medium text-slate-700">{a.employee_name || a.employee_id}</td>
              <td className="py-1 pr-2 text-slate-500">{a.invoice_number ?? '—'}</td>
              <td className="py-1 pr-2">{formatLiters(a.dispensed_liters)}</td>
              <td className="py-1 pr-2">{formatRemaining(a.remaining_liters)}</td>
              <td className="py-1 pr-2 w-24"><div className="h-2 bg-slate-100 rounded-full overflow-hidden"><div className="h-full bg-brand rounded-full" style={{ width: `${progressPercent(a)}%` }} /></div></td>
              <td className="py-1"><span className={`text-xs px-2 py-0.5 rounded-full ${statusColor(a.status)}`}>{a.status}</span></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd web && npx vitest run src/components/dispensing/AllocationsCard.test.tsx
```

- [ ] **Step 5: Commit**

```bash
rtk git add web/src/components/dispensing/AllocationsCard.tsx web/src/components/dispensing/AllocationsCard.test.tsx
rtk git commit -m "feat(web): AllocationsCard with progress bars"
```

---

### Task 2.2: Upload card

**Files:**
- Create: `web/src/components/dispensing/UploadCard.tsx`

- [ ] **Step 1: Implement UploadCard**

Create `web/src/components/dispensing/UploadCard.tsx`:

```typescript
import { FormEvent, useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { useAuthStore } from '../../store/auth';
import { ApiError } from '../../api/http';
import { api } from '../../api/client';
import type { ExcelIngestOutcome } from '../../lib/apiTypes';
import { Field, Select } from '../ui/fields';

export function UploadCard({ onUploaded }: { onUploaded?: () => void }) {
  const user = useAuthStore((s) => s.user);
  const companies = useQuery({ queryKey: ['companies'], queryFn: () => api.listCompanies() });
  const [companyId, setCompanyId] = useState('');
  const [file, setFile] = useState<File | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [outcome, setOutcome] = useState<ExcelIngestOutcome | null>(null);

  const upload = useMutation({
    mutationFn: async () => {
      if (!file || !companyId) throw new Error('Select company and file');
      return api.uploadQuotaSheet(file, companyId, user!.id);
    },
    onSuccess: (data) => { setOutcome(data); setFile(null); setError(null); onUploaded?.(); },
    onError: (err) => { setError(err instanceof ApiError ? err.detail : 'Upload failed'); setOutcome(null); },
  });

  const downloadTemplate = (e: React.MouseEvent) => {
    e.preventDefault();
    const csv = 'Employee ID,Employee Name,Phone,Invoice Number,Allocated Liters\n';
    const blob = new Blob([csv], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a'); a.href = url; a.download = 'quota_template.csv'; a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="bg-white rounded-lg border border-slate-200 p-4">
      <div className="flex items-center justify-between mb-3">
        <h3 className="font-semibold text-slate-800">Upload quota sheet</h3>
        <a href="#" onClick={downloadTemplate} className="text-xs text-brand-dark hover:underline">Download template</a>
      </div>
      <form onSubmit={(e: FormEvent) => { e.preventDefault(); upload.mutate(); }} className="space-y-3">
        <Field label="Company" htmlFor="upload-company">
          <Select id="upload-company" value={companyId} onChange={(e) => setCompanyId(e.target.value)} required>
            <option value="">Select…</option>
            {(companies.data ?? []).map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </Select>
        </Field>
        <Field label="File (.xlsx or .csv)" htmlFor="upload-file">
          <input id="upload-file" type="file" accept=".xlsx,.csv" onChange={(e) => setFile(e.target.files?.[0] ?? null)} className="block w-full text-sm text-slate-600" required />
        </Field>
        {error ? <p className="text-sm text-red-600">{error}</p> : null}
        <button type="submit" disabled={upload.isPending || !file || !companyId} className="bg-brand text-white rounded px-3 py-2 text-sm font-medium disabled:opacity-50">{upload.isPending ? 'Uploading…' : 'Upload'}</button>
      </form>
      {outcome ? (
        <div className="mt-4 p-3 bg-emerald-50 rounded text-sm">
          <p className="font-medium text-emerald-800">{outcome.result.successful_rows} succeeded, {outcome.result.failed_rows} failed ({outcome.result.total_rows} total)</p>
          {outcome.result.errors.length > 0 ? (
            <ul className="mt-2 space-y-1 text-xs text-red-700">{outcome.result.errors.map((e) => <li key={e.row}>Row {e.row}: {e.error}</li>)}</ul>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
```

- [ ] **Step 2: Run full test suite**

```bash
cd web && npm test
```

- [ ] **Step 3: Commit**

```bash
rtk git add web/src/components/dispensing/UploadCard.tsx
rtk git commit -m "feat(web): UploadCard with file picker, template download, outcome summary"
```

---

### Task 2.3: Code ops panel

**Files:**
- Create: `web/src/components/dispensing/CodeOpsCard.tsx`
- Create: `web/src/components/dispensing/CodeOpsCard.test.tsx`

- [ ] **Step 1: Write failing test**

Create `web/src/components/dispensing/CodeOpsCard.test.tsx`:

```typescript
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, expect, it, vi, beforeEach } from 'vitest';

vi.mock('../../api/client', () => ({
  api: { listStations: vi.fn(), listDispensers: vi.fn(), validateCode: vi.fn(), completeDispense: vi.fn() },
}));
import { api } from '../../api/client';
import { CodeOpsCard } from './CodeOpsCard';

function renderCard() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(<QueryClientProvider client={qc}><CodeOpsCard /></QueryClientProvider>);
}

describe('CodeOpsCard', () => {
  beforeEach(() => {
    vi.mocked(api.listStations).mockResolvedValue([{ id: 'st1', name: 'Station A', site_id: 's1', serial_number: 'SN', raspberry_pi_id: null, firmware_version: null, connection_status: 'online', last_heartbeat: null }] as never);
    vi.mocked(api.listDispensers).mockResolvedValue([{ id: 'd1', name: 'Pump 1', station_id: 'st1', serial_number: 'DN', modbus_address: 1, dispenser_model: null, is_active: true }] as never);
  });

  it('validates a code and shows employee name', async () => {
    vi.mocked(api.validateCode).mockResolvedValue({ valid: true, employee_name: 'Ali', remaining_liters: 80, code_id: 'c1', reason: null });
    renderCard();
    await userEvent.type(await screen.findByLabelText(/code/i), '123456');
    await userEvent.click(screen.getByRole('button', { name: /^validate$/i }));
    await waitFor(() => expect(screen.getByText('Ali')).toBeInTheDocument());
    expect(screen.getByText('80.0 L')).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd web && npx vitest run src/components/dispensing/CodeOpsCard.test.tsx
```

- [ ] **Step 3: Implement CodeOpsCard**

Create `web/src/components/dispensing/CodeOpsCard.tsx`:

```typescript
import { FormEvent, useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { ApiError } from '../../api/http';
import { api } from '../../api/client';
import type { CodeValidateResponse, DispenseCompleteResponse } from '../../lib/apiTypes';
import { Field, Input, Select } from '../ui/fields';
import { Badge } from '../ui/badge';

export function CodeOpsCard() {
  const stations = useQuery({ queryKey: ['stations'], queryFn: () => api.listStations() });
  const [stationId, setStationId] = useState('');
  const [code, setCode] = useState('');
  const [dispenserId, setDispenserId] = useState('');
  const [requestedLiters, setRequestedLiters] = useState('');
  const [actualLiters, setActualLiters] = useState('');
  const [totalizerBefore, setTotalizerBefore] = useState('');
  const [totalizerAfter, setTotalizerAfter] = useState('');
  const [validation, setValidation] = useState<CodeValidateResponse | null>(null);
  const [settleResult, setSettleResult] = useState<DispenseCompleteResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const effectiveStation = stationId || stations.data?.[0]?.id || '';
  const dispensers = useQuery({ queryKey: ['dispensers', effectiveStation], queryFn: () => effectiveStation ? api.listDispensers(effectiveStation) : Promise.resolve([]), enabled: Boolean(effectiveStation) });

  const validate = useMutation({
    mutationFn: () => api.validateCode({ code, station_id: effectiveStation, requested_liters: requestedLiters ? Number(requestedLiters) : null }),
    onSuccess: (data) => { setValidation(data); setError(null); setSettleResult(null); },
    onError: (err) => setError(err instanceof ApiError ? err.detail : 'Validation failed'),
  });

  const settle = useMutation({
    mutationFn: () => api.completeDispense({ code, station_id: effectiveStation, dispenser_id: dispenserId, requested_liters: Number(requestedLiters), actual_liters: Number(actualLiters), secret_totalizer_before: Number(totalizerBefore), secret_totalizer_after: Number(totalizerAfter) }),
    onSuccess: (data) => { setSettleResult(data); setError(null); },
    onError: (err) => setError(err instanceof ApiError ? err.detail : 'Settle failed'),
  });

  return (
    <div className="bg-white rounded-lg border border-slate-200 p-4 space-y-4">
      <h3 className="font-semibold text-slate-800">Code Ops</h3>
      <div className="grid grid-cols-2 gap-3">
        <Field label="Station" htmlFor="ops-station"><Select id="ops-station" value={effectiveStation} onChange={(e) => { setStationId(e.target.value); setValidation(null); setSettleResult(null); }}>{(stations.data ?? []).map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}</Select></Field>
        <Field label="Code (6-8 digits)" htmlFor="ops-code"><Input id="ops-code" inputMode="numeric" pattern="[0-9]{6,8}" value={code} onChange={(e) => setCode(e.target.value)} required /></Field>
      </div>
      <form onSubmit={(e: FormEvent) => { e.preventDefault(); validate.mutate(); }} className="flex items-end gap-2">
        <Field label="Requested liters" htmlFor="ops-requested"><Input id="ops-requested" type="number" step="any" min="0.1" value={requestedLiters} onChange={(e) => setRequestedLiters(e.target.value)} /></Field>
        <button type="submit" disabled={validate.isPending || !code || !effectiveStation} className="bg-slate-800 text-white rounded px-3 py-2 text-sm font-medium disabled:opacity-50">{validate.isPending ? '…' : 'Validate'}</button>
      </form>
      {validation ? (
        <div className="p-3 bg-slate-50 rounded text-sm space-y-1">
          {validation.valid ? (<><p className="font-medium text-slate-800">{validation.employee_name}</p><p className="text-slate-600">Remaining: <strong>{validation.remaining_liters?.toFixed(1)} L</strong></p></>) : (<p className="text-rose-600 font-medium">{validation.reason ?? 'Invalid code'}</p>)}
        </div>
      ) : null}
      {validation?.valid ? (
        <form onSubmit={(e: FormEvent) => { e.preventDefault(); settle.mutate(); }} className="grid grid-cols-2 gap-3 pt-2 border-t border-slate-100">
          <Field label="Dispenser" htmlFor="ops-dispenser"><Select id="ops-dispenser" value={dispenserId} onChange={(e) => setDispenserId(e.target.value)} required><option value="">Select…</option>{(dispensers.data ?? []).map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}</Select></Field>
          <Field label="Actual liters" htmlFor="ops-actual"><Input id="ops-actual" type="number" step="any" min="0.1" value={actualLiters} onChange={(e) => setActualLiters(e.target.value)} required /></Field>
          <Field label="Totalizer before" htmlFor="ops-tb"><Input id="ops-tb" type="number" min="0" value={totalizerBefore} onChange={(e) => setTotalizerBefore(e.target.value)} required /></Field>
          <Field label="Totalizer after" htmlFor="ops-ta"><Input id="ops-ta" type="number" min="0" value={totalizerAfter} onChange={(e) => setTotalizerAfter(e.target.value)} required /></Field>
          {error ? <p className="col-span-2 text-sm text-red-600">{error}</p> : null}
          <button type="submit" disabled={settle.isPending || !dispenserId} className="col-span-2 bg-brand text-white rounded px-3 py-2 text-sm font-medium disabled:opacity-50">{settle.isPending ? 'Settling…' : 'Settle'}</button>
        </form>
      ) : null}
      {settleResult ? (
        <div className="p-3 bg-slate-50 rounded text-sm">
          <p className="font-medium">Status: <Badge variant={settleResult.status === 'COMPLETED' ? 'success' : 'warning'}>{settleResult.status}</Badge></p>
          <p className="text-slate-600 mt-1">Delivered: {settleResult.actual_liters.toFixed(1)} L / Requested: {settleResult.requested_liters.toFixed(1)} L</p>
        </div>
      ) : null}
    </div>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd web && npx vitest run src/components/dispensing/CodeOpsCard.test.tsx
```

- [ ] **Step 5: Commit**

```bash
rtk git add web/src/components/dispensing/CodeOpsCard.tsx web/src/components/dispensing/CodeOpsCard.test.tsx
rtk git commit -m "feat(web): CodeOpsCard with validate + settle workflow"
```

---

### Task 2.4: Restructure Dispensing page with tabs

**Files:**
- Replace: `web/src/pages/Dispensing.tsx`

- [ ] **Step 1: Replace Dispensing.tsx**

Replace `web/src/pages/Dispensing.tsx`:

```typescript
import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { api } from '../api/client';
import { useLiveDispensing, isActiveAllocation } from '../hooks/useLiveDispensing';
import { DispenseLiveView } from '../components/dispensing/DispenseLiveView';
import { AllocationsCard } from '../components/dispensing/AllocationsCard';
import { UploadCard } from '../components/dispensing/UploadCard';
import { CodeOpsCard } from '../components/dispensing/CodeOpsCard';

type Tab = 'live' | 'allocations' | 'upload' | 'ops';
const TABS: { key: Tab; label: string }[] = [
  { key: 'live', label: 'Live View' },
  { key: 'allocations', label: 'Allocations' },
  { key: 'upload', label: 'Upload' },
  { key: 'ops', label: 'Code Ops' },
];

export default function Dispensing() {
  const [tab, setTab] = useState<Tab>('live');
  const [stationId, setStationId] = useState('');
  const stations = useQuery({ queryKey: ['stations'], queryFn: () => api.listStations() });
  const transactions = useQuery({ queryKey: ['transactions'], queryFn: () => api.listTransactions(200), refetchInterval: 15_000 });
  const allocations = useLiveDispensing();
  const active = (allocations.data ?? []).filter(isActiveAllocation);
  const first = stations.data?.[0];
  const effectiveStationId = stationId || first?.id || '';
  const dispensers = useQuery({ queryKey: ['dispensers', effectiveStationId], queryFn: () => effectiveStationId ? api.listDispensers(effectiveStationId) : Promise.resolve([]), enabled: Boolean(effectiveStationId) });

  const stationDispenserIds = new Set((dispensers.data ?? []).map((d) => d.id));
  const stationTransactions = stationId
    ? (transactions.data ?? []).filter((t) => stationDispenserIds.has(t.dispenser_id))
    : transactions.data ?? [];

  return (
    <div>
      <h2 className="text-2xl font-semibold text-slate-800 mb-4">Dispensing</h2>
      <div className="flex gap-4 mb-4 items-end">
        <div>
          <label htmlFor="station-select" className="block text-sm font-medium text-slate-700 mb-1">Station</label>
          <select id="station-select" className="border border-slate-300 rounded px-3 py-2 text-sm" value={stationId} onChange={(e) => setStationId(e.target.value)}>
            {(stations.data ?? []).map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
          </select>
        </div>
        <div className="flex gap-1">
          {TABS.map((t) => (
            <button key={t.key} onClick={() => setTab(t.key)} className={`px-3 py-1.5 text-sm rounded ${tab === t.key ? 'bg-brand text-white' : 'bg-slate-100 text-slate-600'}`}>{t.label}</button>
          ))}
        </div>
      </div>
      {tab === 'live' ? (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <div className="lg:col-span-2"><DispenseLiveView active={active} recent={stationTransactions} /></div>
          <div className="bg-white rounded-lg border border-slate-200 p-4">
            <h3 className="font-semibold text-slate-800 mb-3">Dispensers</h3>
            <ul className="space-y-2 text-sm">
              {(dispensers.data ?? []).map((d) => (
                <li key={d.id} className="flex items-center justify-between">
                  <span className="text-slate-700">{d.name}</span>
                  <span className={`text-xs px-2 py-0.5 rounded-full ${d.is_active ? 'bg-emerald-100 text-emerald-700' : 'bg-slate-100 text-slate-400'}`}>{d.is_active ? 'active' : 'inactive'}</span>
                </li>
              ))}
            </ul>
          </div>
        </div>
      ) : null}
      {tab === 'allocations' ? <AllocationsCard /> : null}
      {tab === 'upload' ? <UploadCard /> : null}
      {tab === 'ops' ? <CodeOpsCard /> : null}
    </div>
  );
}
```

- [ ] **Step 2: Run full test suite**

```bash
cd web && npm test
```

- [ ] **Step 3: Commit**

```bash
rtk git add web/src/pages/Dispensing.tsx
rtk git commit -m "feat(web): tabbed Dispensing page with allocations, upload, code ops"
```

---

## Part 3: Monitoring Polish

### Task 3.1: Dashboard KPI cards

**Files:**
- Create: `web/src/components/dashboard/KpiCards.tsx`
- Create: `web/src/components/dashboard/KpiCards.test.tsx`
- Modify: `web/src/pages/Dashboard.tsx`

- [ ] **Step 1: Write failing test**

Create `web/src/components/dashboard/KpiCards.test.tsx`:

```typescript
import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, expect, it, vi, beforeEach } from 'vitest';

vi.mock('../../api/client', () => ({ api: { listTanks: vi.fn(), listTransactions: vi.fn(), listStations: vi.fn() } }));
vi.mock('../../hooks/useRealtimeAlarms', () => ({ useRealtimeAlarms: () => [{ acknowledged: false, id: 'a1' }] }));

import { api } from '../../api/client';
import { KpiCards } from './KpiCards';

function renderCard() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}><KpiCards /></QueryClientProvider>);
}

describe('KpiCards', () => {
  beforeEach(() => {
    vi.mocked(api.listTanks).mockResolvedValue([{ id: 't1' }, { id: 't2' }] as never);
    vi.mocked(api.listStations).mockResolvedValue([{ connection_status: 'online' }, { connection_status: 'offline' }] as never);
    vi.mocked(api.listTransactions).mockResolvedValue([{ actual_liters: 100, created_at: new Date().toISOString(), id: 1, station_id: '', dispenser_id: '', employee_id: '', requested_liters: 100, secret_totalizer_before: 0, secret_totalizer_after: 0, status: 'COMPLETED' }] as never);
  });

  it('renders four KPI cards', async () => {
    renderCard();
    expect(await screen.findByText('2')).toBeInTheDocument();
    expect(screen.getByText('1')).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd web && npx vitest run src/components/dashboard/KpiCards.test.tsx
```

- [ ] **Step 3: Implement KpiCards**

Create `web/src/components/dashboard/KpiCards.tsx`:

```typescript
import { useQuery } from '@tanstack/react-query';
import { api } from '../../api/client';
import { useRealtimeAlarms } from '../../hooks/useRealtimeAlarms';
import { isOpenAlarm, last24hLiters, onlineStations } from '../../lib/kpi';
import { formatLiters } from '../../lib/dispenseFormat';

export function KpiCards() {
  const tanks = useQuery({ queryKey: ['tanks'], queryFn: () => api.listTanks() });
  const stations = useQuery({ queryKey: ['stations'], queryFn: () => api.listStations() });
  const transactions = useQuery({ queryKey: ['transactions'], queryFn: () => api.listTransactions(500) });
  const alarms = useRealtimeAlarms();

  const cards = [
    { label: 'Tanks', value: String((tanks.data ?? []).length), accent: 'text-slate-800' },
    { label: 'Open alarms', value: String(alarms.filter(isOpenAlarm).length), accent: 'text-rose-600' },
    { label: 'Stations online', value: String(onlineStations(stations.data ?? [])), accent: 'text-emerald-600' },
    { label: '24h dispensed', value: formatLiters(last24hLiters(transactions.data ?? [])), accent: 'text-slate-800' },
  ];

  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
      {cards.map((c) => (
        <div key={c.label} className="bg-white rounded-lg border border-slate-200 p-4">
          <p className="text-xs text-slate-500 mb-1">{c.label}</p>
          <p className={`text-2xl font-bold ${c.accent}`}>{c.value}</p>
        </div>
      ))}
    </div>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd web && npx vitest run src/components/dashboard/KpiCards.test.tsx
```

- [ ] **Step 5: Modify Dashboard.tsx**

Add to `web/src/pages/Dashboard.tsx`:

Import: `import { KpiCards } from '../components/dashboard/KpiCards';`

Insert `<KpiCards />` after the heading `</div>` (line 24, before the loading text).

- [ ] **Step 6: Run full test suite**

```bash
cd web && npm test
```

- [ ] **Step 7: Commit**

```bash
rtk git add web/src/components/dashboard/KpiCards.tsx web/src/components/dashboard/KpiCards.test.tsx web/src/pages/Dashboard.tsx
rtk git commit -m "feat(web): Dashboard KPI cards (tanks, alarms, stations online, 24h liters)"
```

---

### Task 3.2: Alarm Center page

**Files:**
- Replace: `web/src/pages/AlarmCenter.tsx`
- Create: `web/src/pages/AlarmCenter.test.tsx`

- [ ] **Step 1: Write failing test**

Create `web/src/pages/AlarmCenter.test.tsx`:

```typescript
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, expect, it, vi, beforeEach } from 'vitest';

vi.mock('../api/client', () => ({
  api: { listTanks: vi.fn(), tankAlarms: vi.fn(), ackAlarm: vi.fn() },
}));
import { api } from '../api/client';
import AlarmCenter from './AlarmCenter';

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(<QueryClientProvider client={qc}><MemoryRouter><AlarmCenter /></MemoryRouter></QueryClientProvider>);
}

describe('AlarmCenter', () => {
  beforeEach(() => {
    vi.mocked(api.listTanks).mockResolvedValue([{ id: 't1', name: 'Tank Alpha' }, { id: 't2', name: 'Tank Beta' }] as never);
    vi.mocked(api.tankAlarms).mockImplementation(async (id: string) => {
      if (id === 't1') return [{ id: 'a1', tank_id: 't1', timestamp: '2026-09-08T10:00:00Z', type: 'low_level', level: 'warning', message: 'Level low', value: 12.5, acknowledged: false, acknowledged_at: null }];
      return [];
    });
  });

  it('lists open alarms', async () => {
    renderPage();
    expect(await screen.findByText('Level low')).toBeInTheDocument();
    expect(screen.getByText('Tank Alpha')).toBeInTheDocument();
  });

  it('shows empty state when no alarms', async () => {
    vi.mocked(api.tankAlarms).mockResolvedValue([]);
    renderPage();
    await waitFor(() => expect(screen.queryByText('No open alarms.')).toBeInTheDocument());
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd web && npx vitest run src/pages/AlarmCenter.test.tsx
```

- [ ] **Step 3: Implement AlarmCenter**

Replace `web/src/pages/AlarmCenter.tsx`:

```typescript
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '../api/client';
import type { AlarmSummary, TankRead } from '../lib/apiTypes';

export default function AlarmCenter() {
  const qc = useQueryClient();
  const tanks = useQuery({ queryKey: ['tanks'], queryFn: () => api.listTanks() });
  const tankAlarmsQ = useQuery({
    queryKey: ['allOpenAlarms'],
    queryFn: async () => {
      const results = await Promise.all((tanks.data ?? []).map((t: TankRead) => api.tankAlarms(t.id, true, 100)));
      return results.flat();
    },
    enabled: Boolean(tanks.data),
    refetchInterval: 10_000,
  });

  const ack = useMutation({
    mutationFn: (a: AlarmSummary) => api.ackAlarm(a.tank_id, a.id),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ['allOpenAlarms'] }),
  });

  const tankName = (tankId: string) => tanks.data?.find((t: TankRead) => t.id === tankId)?.name ?? tankId;
  const alarms = tankAlarmsQ.data ?? [];

  return (
    <div>
      <h2 className="text-2xl font-semibold text-slate-800 mb-6">Alarm Center</h2>
      {alarms.length === 0 ? <p className="text-slate-500">No open alarms.</p> : (
        <div className="bg-white rounded-lg border border-slate-200 overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-slate-500"><tr>
              <th className="text-left px-4 py-2">Time</th><th className="text-left px-4 py-2">Tank</th><th className="text-left px-4 py-2">Type</th><th className="text-left px-4 py-2">Level</th><th className="text-left px-4 py-2">Message</th><th className="text-left px-4 py-2">Value</th><th className="text-right px-4 py-2"></th>
            </tr></thead>
            <tbody>
              {alarms.map((a: AlarmSummary) => (
                <tr key={a.id} className="border-t border-slate-100">
                  <td className="px-4 py-2 text-slate-600">{new Date(a.timestamp).toLocaleString()}</td>
                  <td className="px-4 py-2 font-medium text-slate-700">{tankName(a.tank_id)}</td>
                  <td className="px-4 py-2 text-slate-600">{a.type}</td>
                  <td className="px-4 py-2"><span className={`text-xs px-2 py-0.5 rounded-full ${a.level === 'critical' ? 'bg-rose-100 text-rose-700' : 'bg-amber-100 text-amber-700'}`}>{a.level}</span></td>
                  <td className="px-4 py-2 text-slate-600">{a.message}</td>
                  <td className="px-4 py-2 text-slate-600">{a.value != null ? Number(a.value).toFixed(2) : '—'}</td>
                  <td className="px-4 py-2 text-right"><button onClick={() => ack.mutate(a)} disabled={a.acknowledged} className="text-xs bg-slate-100 px-2 py-1 rounded disabled:opacity-40">Ack</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd web && npx vitest run src/pages/AlarmCenter.test.tsx
```

- [ ] **Step 5: Commit**

```bash
rtk git add web/src/pages/AlarmCenter.tsx web/src/pages/AlarmCenter.test.tsx
rtk git commit -m "feat(web): AlarmCenter page with global open alarms + one-click ack"
```

---

## Part 4: Admin Settings

### Task 4.1: Fuel Types page

**Files:**
- Replace: `web/src/pages/FuelTypesPage.tsx`
- Create: `web/src/pages/FuelTypesPage.test.tsx`

- [ ] **Step 1: Write failing test**

Create `web/src/pages/FuelTypesPage.test.tsx`:

```typescript
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, expect, it, vi, beforeEach } from 'vitest';

vi.mock('../api/client', () => ({
  api: { listFuelTypes: vi.fn(), createFuelType: vi.fn() },
}));
import { api } from '../api/client';
import FuelTypesPage from './FuelTypesPage';

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(<QueryClientProvider client={qc}><MemoryRouter><FuelTypesPage /></MemoryRouter></QueryClientProvider>);
}

describe('FuelTypesPage', () => {
  beforeEach(() => {
    vi.mocked(api.listFuelTypes).mockResolvedValue([{
      id: 'f1', code: 'gasoline', name: 'Gasoline', base_density: 0.75,
      thermal_expansion_coeff: 0.00095, max_vapor_pressure: 101, viscosity_cst: 0.6, created_at: '2026-01-01T00:00:00Z',
    }] as never);
  });

  it('renders fuel type list', async () => {
    renderPage();
    expect(await screen.findByText('Gasoline')).toBeInTheDocument();
    expect(screen.getByText('gasoline')).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd web && npx vitest run src/pages/FuelTypesPage.test.tsx
```

- [ ] **Step 3: Implement FuelTypesPage**

Replace `web/src/pages/FuelTypesPage.tsx`:

```typescript
import { FormEvent, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ApiError } from '../api/http';
import { api } from '../api/client';
import type { FuelType } from '../lib/apiTypes';
import { Modal } from '../components/ui/Modal';
import { Field, Input } from '../components/ui/fields';

export default function FuelTypesPage() {
  const fuelTypes = useQuery({ queryKey: ['fuel-types'], queryFn: () => api.listFuelTypes() });
  const [creating, setCreating] = useState(false);

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-2xl font-semibold text-slate-800">Fuel Types</h2>
        <button onClick={() => setCreating(true)} className="bg-brand text-white rounded px-3 py-2 text-sm font-medium">New fuel type</button>
      </div>
      <div className="bg-white rounded-lg border border-slate-200 overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-slate-500"><tr>
            <th className="text-left px-4 py-2">Code</th><th className="text-left px-4 py-2">Name</th><th className="text-right px-4 py-2">Density</th><th className="text-right px-4 py-2">Thermal Exp.</th><th className="text-right px-4 py-2">Vapor P.</th><th className="text-right px-4 py-2">Viscosity</th>
          </tr></thead>
          <tbody>
            {(fuelTypes.data ?? []).map((f) => (
              <tr key={f.id} className="border-t border-slate-100">
                <td className="px-4 py-2 font-medium text-slate-700">{f.code}</td>
                <td className="px-4 py-2 text-slate-600">{f.name}</td>
                <td className="px-4 py-2 text-right">{f.base_density}</td>
                <td className="px-4 py-2 text-right">{f.thermal_expansion_coeff}</td>
                <td className="px-4 py-2 text-right">{f.max_vapor_pressure}</td>
                <td className="px-4 py-2 text-right">{f.viscosity_cst}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {creating ? <CreateFuelTypeDialog onClose={() => setCreating(false)} /> : null}
    </div>
  );
}

function CreateFuelTypeDialog({ onClose }: { onClose: () => void }) {
  const qc = useQueryClient();
  const [form, setForm] = useState({ code: '', name: '', base_density: '', thermal_expansion_coeff: '', max_vapor_pressure: '', viscosity_cst: '' });
  const [error, setError] = useState<string | null>(null);
  const set = (k: keyof typeof form) => (e: { target: { value: string } }) => setForm((f) => ({ ...f, [k]: e.target.value }));

  const mutation = useMutation({
    mutationFn: () => api.createFuelType({
      code: form.code, name: form.name, base_density: Number(form.base_density),
      thermal_expansion_coeff: Number(form.thermal_expansion_coeff), max_vapor_pressure: Number(form.max_vapor_pressure), viscosity_cst: Number(form.viscosity_cst),
    }),
    onSuccess: () => { void qc.invalidateQueries({ queryKey: ['fuel-types'] }); onClose(); },
    onError: (err) => setError(err instanceof ApiError ? err.detail : 'Save failed'),
  });

  return (
    <Modal title="New fuel type" onClose={onClose}>
      <form onSubmit={(e: FormEvent) => { e.preventDefault(); mutation.mutate(); }} className="space-y-3">
        <Field label="Code" htmlFor="ft-code"><Input id="ft-code" autoFocus pattern="[a-z0-9_]+" value={form.code} onChange={set('code')} required /></Field>
        <Field label="Name" htmlFor="ft-name"><Input id="ft-name" value={form.name} onChange={set('name')} required /></Field>
        <Field label="Base density" htmlFor="ft-density"><Input id="ft-density" type="number" step="any" min="0.001" value={form.base_density} onChange={set('base_density')} required /></Field>
        <Field label="Thermal expansion coeff" htmlFor="ft-thermal"><Input id="ft-thermal" type="number" step="any" min="0.001" value={form.thermal_expansion_coeff} onChange={set('thermal_expansion_coeff')} required /></Field>
        <Field label="Max vapor pressure" htmlFor="ft-vapor"><Input id="ft-vapor" type="number" step="any" min="0" value={form.max_vapor_pressure} onChange={set('max_vapor_pressure')} required /></Field>
        <Field label="Viscosity (cSt)" htmlFor="ft-visc"><Input id="ft-visc" type="number" step="any" min="0" value={form.viscosity_cst} onChange={set('viscosity_cst')} required /></Field>
        {error ? <p className="text-sm text-red-600">{error}</p> : null}
        <div className="flex justify-end gap-2 pt-2">
          <button type="button" onClick={onClose} className="px-3 py-2 text-sm text-slate-600">Cancel</button>
          <button type="submit" disabled={mutation.isPending} className="bg-brand text-white rounded px-3 py-2 text-sm font-medium disabled:opacity-50">Create</button>
        </div>
      </form>
    </Modal>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd web && npx vitest run src/pages/FuelTypesPage.test.tsx
```

- [ ] **Step 5: Commit**

```bash
rtk git add web/src/pages/FuelTypesPage.tsx web/src/pages/FuelTypesPage.test.tsx
rtk git commit -m "feat(web): FuelTypesPage with list + create dialog"
```

---

### Task 4.2: Notification Gateways page

**Files:**
- Replace: `web/src/pages/GatewaysPage.tsx`
- Create: `web/src/pages/GatewaysPage.test.tsx`

- [ ] **Step 1: Write failing test**

Create `web/src/pages/GatewaysPage.test.tsx`:

```typescript
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, expect, it, vi, beforeEach } from 'vitest';

vi.mock('../api/client', () => ({
  api: { listGateways: vi.fn(), createGateway: vi.fn(), updateGateway: vi.fn(), deleteGateway: vi.fn() },
}));
import { api } from '../api/client';
import GatewaysPage from './GatewaysPage';

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(<QueryClientProvider client={qc}><MemoryRouter><GatewaysPage /></MemoryRouter></QueryClientProvider>);
}

describe('GatewaysPage', () => {
  beforeEach(() => {
    vi.mocked(api.listGateways).mockResolvedValue([{
      id: 'g1', name: 'SMS Gateway', type: 'smpp', config_json: { host: 'sms.io' }, is_active: true, priority: 10, created_at: '2026-01-01T00:00:00Z',
    }] as never);
  });

  it('renders gateway list', async () => {
    renderPage();
    expect(await screen.findByText('SMS Gateway')).toBeInTheDocument();
    expect(screen.getByText('smpp')).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd web && npx vitest run src/pages/GatewaysPage.test.tsx
```

- [ ] **Step 3: Implement GatewaysPage**

Replace `web/src/pages/GatewaysPage.tsx`:

```typescript
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
        <h2 className="text-2xl font-semibold text-slate-800">Notification Gateways</h2>
        <button onClick={() => setCreating(true)} className="bg-brand text-white rounded px-3 py-2 text-sm font-medium">New gateway</button>
      </div>
      <div className="bg-white rounded-lg border border-slate-200 overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-slate-500"><tr>
            <th className="text-left px-4 py-2">Name</th><th className="text-left px-4 py-2">Type</th><th className="text-left px-4 py-2">Active</th><th className="text-left px-4 py-2">Priority</th><th className="text-right px-4 py-2"></th>
          </tr></thead>
          <tbody>
            {(gateways.data ?? []).map((g) => (
              <tr key={g.id} className="border-t border-slate-100">
                <td className="px-4 py-2 font-medium text-slate-700">{g.name}</td>
                <td className="px-4 py-2 text-slate-600">{g.type}</td>
                <td className="px-4 py-2"><Badge variant={g.is_active ? 'success' : 'default'}>{g.is_active ? 'Active' : 'Inactive'}</Badge></td>
                <td className="px-4 py-2 text-slate-600">{g.priority}</td>
                <td className="px-4 py-2 text-right space-x-3">
                  <button onClick={() => setEditing(g)} className="text-sm text-slate-600 hover:text-brand-dark">Edit</button>
                  <button onClick={() => setDeleting(g)} className="text-sm text-rose-600">Delete</button>
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
  const qc = useQueryClient();
  const [form, setForm] = useState({
    name: initial?.name ?? '', type: initial?.type ?? 'smpp', is_active: initial?.is_active ?? true,
    priority: String(initial?.priority ?? 10), config_json: JSON.stringify(initial?.config_json ?? {}, null, 2),
  });
  const [error, setError] = useState<string | null>(null);
  const set = (k: keyof typeof form) => (e: { target: { value: string } }) => setForm((f) => ({ ...f, [k]: e.target.value }));

  const mutation = useMutation({
    mutationFn: () => {
      let config: Record<string, unknown> = {};
      try { config = JSON.parse(form.config_json); } catch { throw new Error('Invalid JSON'); }
      const p = { name: form.name, type: form.type, config_json: config, is_active: form.is_active, priority: Number(form.priority) };
      return initial ? api.updateGateway(initial.id, { is_active: form.is_active, priority: Number(form.priority), config_json: config }) : api.createGateway(p);
    },
    onSuccess: () => { void qc.invalidateQueries({ queryKey: ['gateways'] }); onClose(); },
    onError: (err) => setError(err instanceof ApiError ? err.detail : 'Save failed'),
  });

  return (
    <Modal title={initial ? 'Edit gateway' : 'New gateway'} onClose={onClose} wide>
      <form onSubmit={(e: FormEvent) => { e.preventDefault(); mutation.mutate(); }} className="space-y-3">
        <Field label="Name" htmlFor="gw-name"><Input id="gw-name" autoFocus value={form.name} onChange={set('name')} required /></Field>
        <Field label="Type" htmlFor="gw-type"><Select id="gw-type" value={form.type} onChange={set('type')}><option value="smpp">SMPP</option><option value="whatsapp">WhatsApp</option></Select></Field>
        <Field label="Priority" htmlFor="gw-priority"><Input id="gw-priority" type="number" min="1" value={form.priority} onChange={set('priority')} /></Field>
        <Field label="Config (JSON)" htmlFor="gw-config"><Textarea id="gw-config" value={form.config_json} onChange={set('config_json')} /></Field>
        {error ? <p className="text-sm text-red-600">{error}</p> : null}
        <div className="flex justify-end gap-2 pt-2">
          <button type="button" onClick={onClose} className="px-3 py-2 text-sm text-slate-600">Cancel</button>
          <button type="submit" disabled={mutation.isPending} className="bg-brand text-white rounded px-3 py-2 text-sm font-medium disabled:opacity-50">{initial ? 'Save' : 'Create'}</button>
        </div>
      </form>
    </Modal>
  );
}

function DeleteGateway({ gateway, onCancel }: { gateway: NotificationGatewayRead; onCancel: () => void }) {
  const qc = useQueryClient();
  const mutate = useMutation({ mutationFn: () => api.deleteGateway(gateway.id), onSuccess: () => { void qc.invalidateQueries({ queryKey: ['gateways'] }); onCancel(); } });
  return <ConfirmDialog title="Delete gateway" message={`Delete "${gateway.name}"?`} confirmLabel="Delete" onCancel={onCancel} onConfirm={() => mutate.mutate()} />;
}
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd web && npx vitest run src/pages/GatewaysPage.test.tsx
```

- [ ] **Step 5: Commit**

```bash
rtk git add web/src/pages/GatewaysPage.tsx web/src/pages/GatewaysPage.test.tsx
rtk git commit -m "feat(web): GatewaysPage with create/edit/delete + JSON config editor"
```

---

### Task 4.3: Strapping read-only in TankDetail

**Files:**
- Create: `web/src/components/tanks/StrappingCard.tsx`
- Create: `web/src/components/tanks/StrappingCard.test.tsx`
- Modify: `web/src/pages/TankDetail.tsx`

- [ ] **Step 1: Write failing test**

Create `web/src/components/tanks/StrappingCard.test.tsx`:

```typescript
import { render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, expect, it, vi, beforeEach } from 'vitest';

vi.mock('../../api/client', () => ({ api: { getStrapping: vi.fn() } }));
import { api } from '../../api/client';
import { StrappingCard } from './StrappingCard';

function renderCard() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}><StrappingCard tankId="t1" /></QueryClientProvider>);
}

describe('StrappingCard', () => {
  beforeEach(() => {
    vi.mocked(api.getStrapping).mockResolvedValue({
      id: 's1', tank_id: 't1', interpolation_method: 'linear',
      calibration_data: [{ height: 0, volume: 0 }, { height: 1, volume: 500 }],
      created_at: '2026-01-01T00:00:00Z',
    } as never);
  });

  it('renders strapping table', async () => {
    renderCard();
    expect(await screen.findByText('Strapping table')).toBeInTheDocument();
    expect(screen.getByText('linear')).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd web && npx vitest run src/components/tanks/StrappingCard.test.tsx
```

- [ ] **Step 3: Implement StrappingCard**

Create `web/src/components/tanks/StrappingCard.tsx`:

```typescript
import { useQuery } from '@tanstack/react-query';
import { api } from '../../api/client';

export function StrappingCard({ tankId }: { tankId: string }) {
  const strapping = useQuery({ queryKey: ['strapping', tankId], queryFn: () => api.getStrapping(tankId) });
  if (strapping.isLoading) return <p className="text-sm text-slate-500">Loading strapping table…</p>;
  const s = strapping.data;
  if (!s) return <p className="text-sm text-slate-500">No strapping table.</p>;

  return (
    <div>
      <h3 className="font-semibold text-slate-800 mb-2">Strapping table</h3>
      <p className="text-xs text-slate-500 mb-2">Interpolation: {s.interpolation_method}</p>
      <table className="w-full text-sm">
        <thead className="bg-slate-50 text-slate-500">
          <tr><th className="text-left px-3 py-1">Height (m)</th><th className="text-right px-3 py-1">Volume (L)</th></tr>
        </thead>
        <tbody>
          {s.calibration_data.map((pt) => (
            <tr key={pt.height} className="border-t border-slate-100">
              <td className="px-3 py-1">{pt.height}</td>
              <td className="px-3 py-1 text-right">{pt.volume.toLocaleString()}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd web && npx vitest run src/components/tanks/StrappingCard.test.tsx
```

- [ ] **Step 5: Modify TankDetail.tsx**

In `web/src/pages/TankDetail.tsx`:

Add import:
```typescript
import { StrappingCard } from '../components/tanks/StrappingCard';
```

After the alarm list `</div>` (line 118, before closing `</div>`), insert:

```tsx
{tank.tank_shape === 'custom_strapping' ? (
  <div className="mt-6 bg-white rounded-lg border border-slate-200 p-4">
    <StrappingCard tankId={tank.id} />
  </div>
) : null}
```

- [ ] **Step 6: Run full test suite**

```bash
cd web && npm test
```

- [ ] **Step 7: Commit**

```bash
rtk git add web/src/components/tanks/StrappingCard.tsx web/src/components/tanks/StrappingCard.test.tsx web/src/pages/TankDetail.tsx
rtk git commit -m "feat(web): StrappingCard read-only view in TankDetail for custom_strapping tanks"
```

---

## Final Verification

### Task F.1: Full test suites + build + deploy + visual audit

- [ ] **Step 1: Run backend test suite**

```bash
cd platform && POSTGRES_PORT=5434 POSTGRES_DB=fuel_test POSTGRES_USER=fuelplatform POSTGRES_PASSWORD=fuelplatform123 REDIS_PORT=6479 python3 -m pytest fmp/tests -q
```

Expected: all pass (including 3 new org_api tests)

- [ ] **Step 2: Run frontend test suite**

```bash
cd web && npm test
```

Expected: all pass (48 existing + ~18 new component/helper tests)

- [ ] **Step 3: TypeScript check + build**

```bash
cd web && npm run build
```

Expected: clean build, no errors

- [ ] **Step 4: Rebuild and redeploy web container**

```bash
cd /home/ubuntu/fuel_monitoring && docker compose up -d --build web
```

- [ ] **Step 5: Visual audit with headless chromium**

```bash
node /tmp/opencode/visual_check.js
```

Verify: no console errors, all new pages render, management flows work.

- [ ] **Step 6: Final commit** (if any fixes were needed)

```bash
rtk git add -A && rtk git commit -m "fix(web): visual audit fixes"
```

---

**Plan complete.** All tasks follow TDD: write failing test → run to verify failure → implement → run to verify pass → commit. Each task produces self-contained, independently testable changes.
