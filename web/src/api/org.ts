import type {
  Company,
  CompanyCreate,
  CompanyUpdate,
  Dispenser,
  DispenserCreate,
  DispenserUpdate,
  Site,
  SiteCreate,
  SiteUpdate,
  Station,
  StationCreate,
  StationUpdate,
} from '../lib/apiTypes';
import { request } from './http';

const API_BASE = '/api/v1';

export const orgApi = {
  async listCompanies(): Promise<Company[]> {
    return request<Company[]>(`${API_BASE}/companies`);
  },

  async createCompany(payload: CompanyCreate): Promise<Company> {
    return request<Company>(`${API_BASE}/companies`, {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  },

  async updateCompany(id: string, payload: CompanyUpdate): Promise<Company> {
    return request<Company>(`${API_BASE}/companies/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(payload),
    });
  },

  async deleteCompany(id: string): Promise<void> {
    return request<void>(`${API_BASE}/companies/${id}`, {
      method: 'DELETE',
    });
  },

  async listSites(companyId?: string): Promise<Site[]> {
    const url = companyId ? `${API_BASE}/companies/${companyId}/sites` : `${API_BASE}/sites`;
    return request<Site[]>(url);
  },

  async createSite(payload: SiteCreate): Promise<Site> {
    return request<Site>(`${API_BASE}/sites`, {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  },

  async updateSite(id: string, payload: SiteUpdate): Promise<Site> {
    return request<Site>(`${API_BASE}/sites/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(payload),
    });
  },

  async deleteSite(id: string): Promise<void> {
    return request<void>(`${API_BASE}/sites/${id}`, {
      method: 'DELETE',
    });
  },

  async listStations(siteId?: string): Promise<Station[]> {
    return request<Station[]>(`${API_BASE}/stations${siteId ? `?site_id=${siteId}` : ''}`);
  },

  async createStation(payload: StationCreate): Promise<Station> {
    return request<Station>(`${API_BASE}/stations`, {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  },

  async updateStation(id: string, payload: StationUpdate): Promise<Station> {
    return request<Station>(`${API_BASE}/stations/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(payload),
    });
  },

  async deleteStation(id: string): Promise<void> {
    return request<void>(`${API_BASE}/stations/${id}`, {
      method: 'DELETE',
    });
  },

  async listDispensers(stationId: string): Promise<Dispenser[]> {
    return request<Dispenser[]>(`${API_BASE}/stations/${stationId}/dispensers`);
  },

  async createDispenser(stationId: string, payload: DispenserCreate): Promise<Dispenser> {
    return request<Dispenser>(`${API_BASE}/stations/${stationId}/dispensers`, {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  },

  async updateDispenser(stationId: string, dispenserId: string, payload: DispenserUpdate): Promise<Dispenser> {
    return request<Dispenser>(`${API_BASE}/stations/${stationId}/dispensers/${dispenserId}`, {
      method: 'PATCH',
      body: JSON.stringify(payload),
    });
  },
};
