import type {
  IoTCommand,
  IoTCommandCreate,
  IoTGateway,
  IoTGatewayCreate,
  IoTGatewayUpdate,
} from '../lib/apiTypes';
import { request } from './http';

const API_BASE = '/api/v1/iot-gateways';

export const iotApi = {
  async listGateways(active?: boolean): Promise<IoTGateway[]> {
    const qs = active === undefined ? '' : `?active=${active}`;
    return request<IoTGateway[]>(`${API_BASE}${qs}`);
  },

  async createGateway(payload: IoTGatewayCreate): Promise<IoTGateway> {
    return request<IoTGateway>(API_BASE, {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  },

  async getGateway(id: string): Promise<IoTGateway> {
    return request<IoTGateway>(`${API_BASE}/${id}`);
  },

  async updateGateway(id: string, payload: IoTGatewayUpdate): Promise<IoTGateway> {
    return request<IoTGateway>(`${API_BASE}/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(payload),
    });
  },

  async sendCommand(id: string, payload: IoTCommandCreate): Promise<{ command_id: string; status: string }> {
    return request<{ command_id: string; status: string }>(`${API_BASE}/${id}/commands`, {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  },

  async listCommands(id: string, status?: string, limit = 50): Promise<IoTCommand[]> {
    const params = new URLSearchParams({ limit: String(limit) });
    if (status) params.set('status', status);
    return request<IoTCommand[]>(`${API_BASE}/${id}/commands?${params}`);
  },
};