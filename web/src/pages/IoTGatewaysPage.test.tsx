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

  it('renders the page header with New gateway action', async () => {
    renderPage();
    expect(await screen.findByRole('heading', { level: 2, name: 'IoT Gateways' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'New gateway' })).toBeInTheDocument();
  });

  it('renders a skeleton while gateways are loading', () => {
    vi.mocked(api.listGateways).mockReturnValue(new Promise(() => {}) as never);
    const { container } = renderPage();
    expect(container.querySelector('.animate-pulse')).not.toBeNull();
  });

  it('renders an error card when gateways fail to load', async () => {
    vi.mocked(api.listGateways).mockRejectedValue(new Error('boom'));
    renderPage();
    expect(await screen.findByRole('alert')).toHaveTextContent('Failed to load gateways.');
  });

  it('renders an empty state when there are no gateways', async () => {
    vi.mocked(api.listGateways).mockResolvedValue([] as never);
    renderPage();
    expect(await screen.findByText('No gateways')).toBeInTheDocument();
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
