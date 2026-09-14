import type { StrappingPoint, StrappingTable, TotalizerPoint } from '../lib/apiTypes';
import { request } from './http';

const API_BASE = '/api/v1';

export const monitoringApi = {
  async listTotalizers(
    dispenserId: string,
    rangeStart?: string,
    rangeEnd?: string,
  ): Promise<TotalizerPoint[]> {
    const params = new URLSearchParams({ dispenser_id: dispenserId });
    if (rangeStart) params.set('start', rangeStart);
    if (rangeEnd) params.set('end', rangeEnd);
    return request<TotalizerPoint[]>(`${API_BASE}/totalizers?${params.toString()}`);
  },

  async getStrapping(tankId: string): Promise<StrappingTable> {
    return request<StrappingTable>(`${API_BASE}/tanks/${tankId}/strapping`);
  },

  async saveStrapping(
    tankId: string,
    payload: { calibration_data: StrappingPoint[]; interpolation_method: 'linear' | 'cubic_spline' },
  ): Promise<StrappingTable> {
    return request<StrappingTable>(`${API_BASE}/tanks/${tankId}/strapping`, {
      method: 'PUT',
      body: JSON.stringify(payload),
    });
  },
};
