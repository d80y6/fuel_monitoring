import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, expect, it, vi, beforeEach } from 'vitest';

vi.mock('../api/client', () => ({
  api: { listCompanies: vi.fn(), createCompany: vi.fn(), updateCompany: vi.fn(), deleteCompany: vi.fn() },
}));
import { api } from '../api/client';
import CompaniesPage from './CompaniesPage';

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(<QueryClientProvider client={qc}><MemoryRouter><CompaniesPage /></MemoryRouter></QueryClientProvider>);
}

const co = { id: 'c1', name: 'Acme', address: 'Kampala', contact_name: 'Ali', contact_email: 'a@x.io', contact_phone: '7001', created_at: '2026-01-01T00:00:00Z' };

describe('CompaniesPage', () => {
  beforeEach(() => { vi.mocked(api.listCompanies).mockResolvedValue([co] as never); });

  it('renders company list', async () => {
    renderPage();
    expect(await screen.findByText('Acme')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /new company/i })).toBeInTheDocument();
  });

  it('opens create dialog and submits', async () => {
    vi.mocked(api.createCompany).mockResolvedValue({ id: 'c2', name: 'NewCo', address: 'Entebbe', contact_name: 'Sam', contact_email: 's@x.io', contact_phone: '7002', created_at: '2026-01-02T00:00:00Z' } as never);
    renderPage();
    await userEvent.click(await screen.findByRole('button', { name: /new company/i }));
    await userEvent.type(screen.getByLabelText(/^name$/i), 'NewCo');
    await userEvent.type(screen.getByLabelText(/^address$/i), 'Entebbe');
    await userEvent.type(screen.getByLabelText(/^contact name$/i), 'Sam');
    await userEvent.type(screen.getByLabelText(/^contact email$/i), 's@x.io');
    await userEvent.type(screen.getByLabelText(/^contact phone$/i), '7002');
    await userEvent.click(screen.getByRole('button', { name: /^create$/i }));
    await waitFor(() => expect(api.createCompany).toHaveBeenCalledWith(expect.objectContaining({ name: 'NewCo', address: 'Entebbe', contact_name: 'Sam', contact_email: 's@x.io', contact_phone: '7002' })));
  });
});