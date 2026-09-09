import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, expect, it, vi, beforeEach } from 'vitest';

vi.mock('../api/client', () => ({
  api: { listSites: vi.fn(), listCompanies: vi.fn(), createSite: vi.fn(), updateSite: vi.fn(), deleteSite: vi.fn() },
}));
import { api } from '../api/client';
import SitesPage from './SitesPage';

function renderPage(route = '/sites') {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(<QueryClientProvider client={qc}><MemoryRouter initialEntries={[route]}><SitesPage /></MemoryRouter></QueryClientProvider>);
}

describe('SitesPage', () => {
  beforeEach(() => {
    vi.mocked(api.listCompanies).mockResolvedValue([{ id: 'c1', name: 'Acme', address: null, contact_name: null, contact_email: null, contact_phone: null, created_at: '2026-01-01T00:00:00Z' }] as never);
    vi.mocked(api.listSites).mockResolvedValue([{ id: 's1', name: 'Kampala Depot', company_id: 'c1', address: 'Kampala', location: null, is_active: true, created_at: '2026-01-01T00:00:00Z' }] as never);
  });

  it('renders site list', async () => {
    renderPage();
    expect(await screen.findByText('Kampala Depot')).toBeInTheDocument();
  });
});
