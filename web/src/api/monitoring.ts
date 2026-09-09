import type { StrappingTable, TotalizerPoint } from '../lib/apiTypes';
import { request } from './http';

const API_BASE = '/api/v1';

export const monitoringApi = {
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

  async getStrapping(tankId: string): Promise<StrappingTable> {
    return request<StrappingTable>(`${API_BASE}/tanks/${tankId}/strapping`);
  },
};
