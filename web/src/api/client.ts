import type {
  AlarmSummary,
  AllocationRead,
  Company,
  Dispenser,
  FuelType,
  ListTanksResponse,
  LoginResponse,
  Site,
  Station,
  StrappingTable,
  TankCreatePayload,
  TankRead,
  TelemetryPoint,
  TotalizerPoint,
  TransactionRead,
  UserRead,
} from '../lib/apiTypes';
import { request, setOnUnauthorized, setTokenProvider } from './http';

const API_BASE = '/api/v1';

export const api = {
  async login(username: string, password: string): Promise<LoginResponse> {
    return request<LoginResponse>(`${API_BASE}/auth/login`, {
      method: 'POST',
      body: JSON.stringify({ username, password }),
    });
  },

  async me(): Promise<UserRead> {
    return request<UserRead>(`${API_BASE}/auth/me`);
  },

  async listTanks(): Promise<ListTanksResponse> {
    return request<ListTanksResponse>(`${API_BASE}/tanks`);
  },

  async getTank(id: string): Promise<TankRead> {
    return request<TankRead>(`${API_BASE}/tanks/${id}`);
  },

  async createTank(payload: TankCreatePayload): Promise<TankRead> {
    return request<TankRead>(`${API_BASE}/tanks`, {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  },

  async recentReadings(id: string, limit: number = 200): Promise<TelemetryPoint[]> {
    return request<TelemetryPoint[]>(`${API_BASE}/tanks/${id}/recent?limit=${limit}`);
  },

  async rangeReadings(
    id: string,
    start: string,
    end: string,
    bucket: string = '5 minutes',
  ): Promise<TelemetryPoint[]> {
    const params = new URLSearchParams({ start, end, bucket });
    return request<TelemetryPoint[]>(`${API_BASE}/tanks/${id}/range?${params}`);
  },

  async tankAlarms(id: string, openOnly: boolean = false, limit: number = 50): Promise<AlarmSummary[]> {
    const open = openOnly ? '?open_only=true' : '';
    return request<AlarmSummary[]>(`${API_BASE}/tanks/${id}/alarms${open}`);
  },

  async ackAlarm(
    tankId: string,
    alarmId: string,
  ): Promise<{ alarm_id: string; acknowledged: boolean }> {
    return request<{ alarm_id: string; acknowledged: boolean }>(
      `${API_BASE}/tanks/${tankId}/alarms/${alarmId}/ack`,
      { method: 'POST' },
    );
  },

  async getStrapping(tankId: string): Promise<StrappingTable> {
    return request<StrappingTable>(`${API_BASE}/tanks/${tankId}/strapping`);
  },

  async listFuelTypes(): Promise<FuelType[]> {
    return request<FuelType[]>(`${API_BASE}/fuel-types`);
  },

  async listCompanies(): Promise<Company[]> {
    return request<Company[]>(`${API_BASE}/companies`);
  },

  async listSites(companyId?: string): Promise<Site[]> {
    return request<Site[]>(`${API_BASE}/sites${companyId ? `?company_id=${companyId}` : ''}`);
  },

  async listStations(siteId?: string): Promise<Station[]> {
    return request<Station[]>(`${API_BASE}/stations${siteId ? `?site_id=${siteId}` : ''}`);
  },

  async listDispensers(stationId: string): Promise<Dispenser[]> {
    return request<Dispenser[]>(`${API_BASE}/stations/${stationId}/dispensers`);
  },

  async listTotalizers(
    dispenserId?: string,
    start?: string,
    end?: string,
    limit: number = 1000,
  ): Promise<TotalizerPoint[]> {
    const params = new URLSearchParams();
    if (dispenserId) params.set('dispenser_id', dispenserId);
    if (start) params.set('start', start);
    if (end) params.set('end', end);
    params.set('limit', String(limit));
    return request<TotalizerPoint[]>(`${API_BASE}/totalizers?${params}`);
  },

  async listAllocations(limit: number = 100): Promise<AllocationRead[]> {
    return request<AllocationRead[]>(`${API_BASE}/dispensing/allocations?max_rows=${limit}`);
  },

  async listTransactions(
    limit: number = 200,
    dispenserId?: string,
  ): Promise<TransactionRead[]> {
    let url = `${API_BASE}/dispensing/transactions?limit=${limit}`;
    if (dispenserId) {
      url += `&dispenser_id=${dispenserId}`;
    }
    return request<TransactionRead[]>(url);
  },
};

export { setOnUnauthorized, setTokenProvider };