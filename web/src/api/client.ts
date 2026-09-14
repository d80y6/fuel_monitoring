import type {
  AlarmSummary,
  ConsumptionAnalytics,
  ListTanksResponse,
  LoginResponse,
  TankCreatePayload,
  TankRead,
  TelemetryPoint,
  UserRead,
} from '../lib/apiTypes';
import { getBlob, request, setOnUnauthorized, setTokenProvider } from './http';
import { orgApi } from './org';
import { dispensingApi } from './dispensing';
import { adminApi } from './admin';
import { monitoringApi } from './monitoring';
import { iotApi } from './iot';

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

  async refresh(refreshToken: string): Promise<LoginResponse> {
    return request<LoginResponse>(`${API_BASE}/auth/refresh`, {
      method: 'POST',
      body: JSON.stringify({ refresh_token: refreshToken }),
      skipAuthRetry: true,
    });
  },

  async logout(accessToken: string, refreshToken: string | null): Promise<void> {
    try {
      await fetch(`${API_BASE}/auth/logout`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${accessToken}`,
        },
        body: JSON.stringify({ refresh_token: refreshToken }),
      });
    } catch {
      // fire-and-forget: revocation failure is non-critical
    }
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

  async changePassword(currentPassword: string, newPassword: string): Promise<{ status: string }> {
    return request<{ status: string }>(`${API_BASE}/auth/change-password`, {
      method: 'POST',
      body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
    });
  },

  async exportTankCsv(tankId: string, start: string, end: string): Promise<Blob> {
    const params = new URLSearchParams({ start, end });
    return getBlob(`${API_BASE}/tanks/${tankId}/export?${params.toString()}`);
  },

  async getConsumption(tankId: string, days = 30, windowDays = 7): Promise<ConsumptionAnalytics> {
    const params = new URLSearchParams({ days: String(days), window_days: String(windowDays) });
    return request<ConsumptionAnalytics>(`${API_BASE}/analytics/consumption/${tankId}?${params.toString()}`);
  },

  ...orgApi,
  ...dispensingApi,
  ...adminApi,
  ...monitoringApi,
  ...iotApi,
};

export { setOnUnauthorized, setTokenProvider };
