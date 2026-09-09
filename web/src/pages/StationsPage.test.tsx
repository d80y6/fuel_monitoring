import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, expect, it, vi, beforeEach } from 'vitest';

vi.mock('../api/client', () => ({
  api: { listStations: vi.fn(), createStation: vi.fn(), deleteStation: vi.fn(), updateStation: vi.fn() },
}));
import { api } from '../api/client';
import StationsPage from './StationsPage';

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={['/stations/s1']}>
        <Routes><Route path="stations/:siteId" element={<StationsPage />} /></Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const station = { id: 'st1', name: 'Station A', site_id: 's1', serial_number: 'SN1', raspberry_pi_id: 'rpi1', firmware_version: '1.0', connection_status: 'online', last_heartbeat: '2026-09-08T10:00:00Z' };

describe('StationsPage', () => {
  beforeEach(() => { vi.mocked(api.listStations).mockResolvedValue([station] as never); });

  it('renders stations list', async () => {
    renderPage();
    expect(await screen.findByText('Station A')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /new station/i })).toBeInTheDocument();
  });

  it('opens create dialog and submits', async () => {
    vi.mocked(api.createStation).mockResolvedValue({ id: 'st2', name: 'Station B', site_id: 's1', serial_number: 'SN2', raspberry_pi_id: null, firmware_version: null, connection_status: 'offline', last_heartbeat: null } as never);
    renderPage();
    await userEvent.click(await screen.findByRole('button', { name: /new station/i }));
    await userEvent.type(screen.getByLabelText(/name/i), 'Station B');
    await userEvent.type(screen.getByLabelText(/serial number/i), 'SN2');
    await userEvent.click(screen.getByRole('button', { name: /^create$/i }));
    await waitFor(() => expect(api.createStation).toHaveBeenCalledWith(expect.objectContaining({ name: 'Station B', serial_number: 'SN2' })));
  });
});
