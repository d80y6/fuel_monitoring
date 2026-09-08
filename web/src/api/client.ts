import type {
  AllocationRead,
  FuelType,
  LoginResponse,
  TankRead,
  TransactionRead,
  ListTanksResponse,
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

  async listFuelTypes(): Promise<FuelType[]> {
    return request<FuelType[]>(`${API_BASE}/fuel-types`);
  },

  async listTanks(): Promise<ListTanksResponse> {
    return request<ListTanksResponse>(`${API_BASE}/tanks`);
  },

  async tankRead(id: string): Promise<TankRead> {
    return request<TankRead>(`${API_BASE}/tanks/${id}`);
  },

  async rangeReadings(
    tankId: string,
    start: string,
    end: string,
    bucket: string = '5 minutes',
  ): Promise<{ timestamp: string; level: number; volume: number }[]> {
    const params = new URLSearchParams({ start, end, bucket });
    return request(`${API_BASE}/tanks/${tankId}/range?${params}`);
  },

  async listAllocations(maxRows: number = 100): Promise<AllocationRead[]> {
    return request<AllocationRead[]>(`${API_BASE}/dispensing/allocations?max_rows=${maxRows}`);
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