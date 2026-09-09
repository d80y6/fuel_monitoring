import type {
  FuelType,
  FuelTypeCreate,
  NotificationGatewayRead,
} from '../lib/apiTypes';
import { request } from './http';

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

  async listGateways(): Promise<NotificationGatewayRead[]> {
    return request<NotificationGatewayRead[]>(`${API_BASE}/notification-gateways`);
  },

  async createGateway(payload: {
    name: string;
    type: 'smpp' | 'whatsapp'
    config_json: Record<string, unknown>;
    is_active?: boolean;
    priority?: number;
  }): Promise<NotificationGatewayRead> {
    return request<NotificationGatewayRead>(`${API_BASE}/notification-gateways`, {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  },

  async updateGateway(
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

  async deleteGateway(id: string): Promise<void> {
    return request<void>(`${API_BASE}/notification-gateways/${id}`, {
      method: 'DELETE',
    });
  },
};
