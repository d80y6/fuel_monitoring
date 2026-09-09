import type {
  AlarmSummary,
  ListTanksResponse,
  LoginResponse,
  TankCreatePayload,
  TankRead,
  TelemetryPoint,
  UserRead,
} from '../lib/apiTypes';
import { request, setOnUnauthorized, setTokenProvider } from './http';
import { orgApi } from './org';
import { dispensingApi } from './dispensing';
import { adminApi } from './admin';
import { monitoringApi } from './monitoring';

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
    const qs = new URLSearchParams({ limit: String(limit) });
    if (openOnly) qs.set('open_only', 'true');
    return request<AlarmSummary[]>(`${API_BASE}/tanks/${id}/alarms?${qs}`);
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

  ...orgApi,
  ...dispensingApi,
  ...adminApi,
  ...monitoringApi,
};

export { setOnUnauthorized, setTokenProvider };
