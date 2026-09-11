import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../api/client', () => ({
  api: { listGateways: vi.fn(), createGateway: vi.fn() },
}));
import { api } from '../api/client';
import IoTGatewaysPage from './IoTGatewaysPage';

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <Routes>
          <Route path="/" element={<IoTGatewaysPage />} />
          <Route path="/admin/iot-gateways/:id" element={<div>detail</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const gw = {
  id: 'gw1',
  gateway_mac: 'AA:BB:CC:DD:EE:01',
  name: 'East Gate',
  firmware_version: '2.1.0',
  last_seen: '2026-09-11T00:00:00Z',
  connection_status: 'online',
  is_active: true,
  tank_ids: [],
  created_at: '2026-09-11T00:00:00Z',
};

describe('IoTGatewaysPage', () => {
  beforeEach(() => {
    vi.mocked(api.listGateways).mockResolvedValue([gw] as never);
  });

  it('renders gateway rows with status pill', async () => {
    renderPage();
    expect(await screen.findByText('East Gate')).toBeInTheDocument();
    expect(screen.getByText('AA:BB:CC:DD:EE:01')).toBeInTheDocument();
    expect(screen.getByText('online')).toBeInTheDocument();
    expect(screen.getByText('2.1.0')).toBeInTheDocument();
  });

  it('shows unprovisioned badge for inactive gateway', async () => {
    vi.mocked(api.listGateways).mockResolvedValue([{ ...gw, is_active: false }] as never);
    renderPage();
    expect(await screen.findByText(/unprovisioned/i)).toBeInTheDocument();
  });

  it('navigates to detail on row click', async () => {
    renderPage();
    await userEvent.click(await screen.findByText('East Gate'));
    expect(await screen.findByText('detail')).toBeInTheDocument();
  });
});
