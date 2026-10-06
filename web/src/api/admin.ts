/**
 * Administration APIs: password changes, notification channels, user accounts
 * and the audit trail.
 *
 * Mirrors the server-side authorization model. `userAdminApi` mutates accounts
 * and requires admin or company_admin — a tenant admin may only manage its own
 * company, and the server enforces that regardless of what is sent here.
 * `notificationApi` manages channels and rules, where channel credentials are
 * write-only: the API masks them on read and preserves the stored value when a
 * client echoes the mask back.
 */
import { request } from './http';
import type {
  AuditEvent,
  FuelType,
  FuelTypeCreate,
  NotificationGateway,
  NotificationGatewayRead,
  NotificationLog,
  NotificationRule,
  NotificationRuleCreate,
  NotificationRuleUpdate,
  TestDispatchSummary,
  UserCreate,
  UserRead,
  UserUpdate,
} from '../lib/apiTypes';

const API_BASE = '/api/v1';

export const adminApi = {
  async listFuelTypes(): Promise<FuelType[]> {
    return request<FuelType[]>(`${API_BASE}/fuel-types`);
  },

  async createFuelType(payload: FuelTypeCreate): Promise<FuelType> {
    return request<FuelType>(`${API_BASE}/fuel-types`, {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  },

  async listNotificationGateways(): Promise<NotificationGatewayRead[]> {
    return request<NotificationGatewayRead[]>(`${API_BASE}/notification-gateways`);
  },

  async createNotificationGateway(payload: {
    name: string;
    type: 'smpp' | 'whatsapp' | 'sms' | 'email' | 'webhook';
    config_json: Record<string, unknown>;
    is_active?: boolean;
    priority?: number;
  }): Promise<NotificationGatewayRead> {
    return request<NotificationGatewayRead>(`${API_BASE}/notification-gateways`, {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  },

  async updateNotificationGateway(
    id: string,
    payload: Partial<{
      config_json: Record<string, unknown>;
      is_active: boolean;
      priority: number;
    }>,
  ): Promise<NotificationGatewayRead> {
    return request<NotificationGatewayRead>(`${API_BASE}/notification-gateways/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(payload),
    });
  },

  async deleteNotificationGateway(id: string): Promise<void> {
    return request<void>(`${API_BASE}/notification-gateways/${id}`, {
      method: 'DELETE',
    });
  },
};

export const userAdminApi = {
  async list(
    params: { company_id?: string; role?: string; include_inactive?: boolean } = {},
  ): Promise<UserRead[]> {
    const query = new URLSearchParams();
    if (params.company_id) query.set('company_id', params.company_id);
    if (params.role) query.set('role', params.role);
    if (params.include_inactive) query.set('include_inactive', 'true');
    const suffix = query.toString() ? `?${query}` : '';
    return request<UserRead[]>(`${API_BASE}/users${suffix}`);
  },

  async create(payload: UserCreate): Promise<UserRead> {
    return request<UserRead>(`${API_BASE}/users`, {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  },

  async get(id: string): Promise<UserRead> {
    return request<UserRead>(`${API_BASE}/users/${id}`);
  },

  async update(id: string, payload: UserUpdate): Promise<UserRead> {
    return request<UserRead>(`${API_BASE}/users/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(payload),
    });
  },

  async setPassword(id: string, newPassword: string): Promise<{ status: string }> {
    return request<{ status: string }>(`${API_BASE}/users/${id}/set-password`, {
      method: 'POST',
      body: JSON.stringify({ new_password: newPassword }),
    });
  },

  async deactivate(id: string): Promise<UserRead> {
    return request<UserRead>(`${API_BASE}/users/${id}/deactivate`, { method: 'POST' });
  },

  async restore(id: string): Promise<UserRead> {
    return request<UserRead>(`${API_BASE}/users/${id}/restore`, { method: 'POST' });
  },
};

export const notificationApi = {
  async listGateways(type?: string): Promise<NotificationGateway[]> {
    return request<NotificationGateway[]>(
      `${API_BASE}/notification-gateways${type ? `?type=${type}` : ''}`,
    );
  },

  async createGateway(payload: {
    name: string;
    type: string;
    config_json: Record<string, unknown>;
    is_active?: boolean;
    priority?: number;
  }): Promise<NotificationGateway> {
    return request<NotificationGateway>(`${API_BASE}/notification-gateways`, {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  },

  async updateGateway(
    id: string,
    payload: { is_active?: boolean; priority?: number; config_json?: Record<string, unknown> },
  ): Promise<NotificationGateway> {
    return request<NotificationGateway>(`${API_BASE}/notification-gateways/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(payload),
    });
  },

  async deleteGateway(id: string): Promise<void> {
    return request<void>(`${API_BASE}/notification-gateways/${id}`, { method: 'DELETE' });
  },

  /** Sends a real message through the channel; rejects with 502 if the provider does. */
  async testGateway(
    id: string,
    recipient: string,
    message?: string,
  ): Promise<{ status: string; provider_message_id: string; recipient: string }> {
    return request(`${API_BASE}/notification-gateways/${id}/test`, {
      method: 'POST',
      body: JSON.stringify({ recipient, message: message ?? null }),
    });
  },

  async listRules(siteId?: string): Promise<NotificationRule[]> {
    return request<NotificationRule[]>(
      `${API_BASE}/notification-rules${siteId ? `?site_id=${siteId}` : ''}`,
    );
  },

  async createRule(payload: NotificationRuleCreate): Promise<NotificationRule> {
    return request<NotificationRule>(`${API_BASE}/notification-rules`, {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  },

  async updateRule(id: string, payload: NotificationRuleUpdate): Promise<NotificationRule> {
    return request<NotificationRule>(`${API_BASE}/notification-rules/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(payload),
    });
  },

  async deleteRule(id: string): Promise<void> {
    return request<void>(`${API_BASE}/notification-rules/${id}`, { method: 'DELETE' });
  },

  async listLogs(
    params: { status?: string; channel?: string; event_type?: string; limit?: number } = {},
  ): Promise<NotificationLog[]> {
    const query = new URLSearchParams();
    if (params.status) query.set('status', params.status);
    if (params.channel) query.set('channel', params.channel);
    if (params.event_type) query.set('event_type', params.event_type);
    if (params.limit) query.set('limit', String(params.limit));
    const suffix = query.toString() ? `?${query}` : '';
    return request<NotificationLog[]>(`${API_BASE}/notifications/logs${suffix}`);
  },

  /** Platform-admin dry run of the alarm rule engine against the real gateways. */
  async testDispatch(companyId?: string, level: 'WARNING' | 'CRITICAL' = 'CRITICAL') {
    const query = new URLSearchParams({ level });
    if (companyId) query.set('company_id', companyId);
    return request<TestDispatchSummary>(`${API_BASE}/notifications/test-dispatch?${query}`, {
      method: 'POST',
    });
  },
};

export interface AuditQuery {
  company_id?: string;
  actor_id?: string;
  action?: string;
  entity_type?: string;
  entity_id?: string;
  start?: string;
  end?: string;
  limit?: number;
  offset?: number;
}

export const auditApi = {
  async list(params: AuditQuery = {}): Promise<AuditEvent[]> {
    const query = new URLSearchParams();
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== '' && value !== null) query.set(key, String(value));
    });
    const suffix = query.toString() ? `?${query}` : '';
    return request<AuditEvent[]>(`${API_BASE}/audit-events${suffix}`);
  },
};