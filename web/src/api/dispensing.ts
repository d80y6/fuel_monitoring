import type {
  AllocationRead,
  CodeValidateRequest,
  CodeValidateResponse,
  DispenseCompleteResponse,
  DispenseRequest,
  ExcelIngestOutcome,
  TransactionRead,
} from '../lib/apiTypes';
import { request } from './http';

const API_BASE = '/api/v1';

export const dispensingApi = {
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

  async uploadQuotaSheet(formData: FormData): Promise<ExcelIngestOutcome> {
    return request<ExcelIngestOutcome>(`${API_BASE}/dispensing/upload`, {
      method: 'POST',
      body: formData,
    });
  },

  async validateCode(payload: CodeValidateRequest): Promise<CodeValidateResponse> {
    return request<CodeValidateResponse>(`${API_BASE}/dispensing/validate`, {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  },

  async completeDispense(payload: DispenseRequest): Promise<DispenseCompleteResponse> {
    return request<DispenseCompleteResponse>(`${API_BASE}/dispensing/complete`, {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  },
};
