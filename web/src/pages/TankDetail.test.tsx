import { render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../api/client', () => ({
  api: {
    getTank: vi.fn(),
    listFuelTypes: vi.fn(),
    tankAlarms: vi.fn(),
    rangeReadings: vi.fn(),
    ackAlarm: vi.fn(),
  },
}));
import { api } from '../api/client';

vi.mock('../hooks/useTelemetry', () => ({
  useTelemetry: () => ({ live: null, recent: [], latest: null, loading: false }),
}));

vi.mock('../components/charts/TelemetryChart', () => ({
  TelemetryChart: () => <div data-testid="mock-telemetry-chart" />,
}));

vi.mock('../components/tanks/TankCanvas', () => ({
  TankCanvas: () => <div data-testid="mock-tank-canvas" />,
}));

vi.mock('../components/tanks/StrappingCard', () => ({
  default: () => <div data-testid="mock-strapping-card" />,
}));

import TankDetail from './TankDetail';

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={['/tanks/t1']}>
        <Routes>
          <Route path="/tanks/:tankId" element={<TankDetail />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const tank = {
  id: 't1',
  name: 'Alpha',
  site_id: 's1',
  sensor_serial_number: 'SN1',
  device_address: 1,
  tank_orientation: 'vertical',
  tank_diameter: 3,
  tank_height: 10,
  tank_length: null,
  tank_volume: 100,
  tank_shape: 'vertical_cylinder',
  fuel_type_id: 'f1',
  dish_depth: null,
  tank_width: null,
  strapping_table_id: null,
  elevation: null,
  calibration_factor: 1,
  atmospheric_pressure: 101325,
  low_level_threshold: null,
  critical_level_threshold: null,
  high_level_threshold: null,
  low_volume_threshold: null,
  high_volume_threshold: null,
  is_active: true,
  gateway_mac: null,
  created_at: '2026-01-01T00:00:00Z',
  connection_status: 'online',
  last_connection: null,
} as never;

describe('TankDetail', () => {
  beforeEach(() => {
    vi.mocked(api.getTank).mockResolvedValue(tank);
    vi.mocked(api.listFuelTypes).mockResolvedValue([] as never);
    vi.mocked(api.tankAlarms).mockResolvedValue([] as never);
    vi.mocked(api.rangeReadings).mockResolvedValue([] as never);
  });

  it('renders the tank telemetry heading', async () => {
    renderPage();
    expect(await screen.findByRole('heading', { level: 3, name: 'Alpha' })).toBeInTheDocument();
  });

  it('renders a skeleton while the tank is loading', () => {
    vi.mocked(api.getTank).mockReturnValue(new Promise(() => {}) as never);
    const { container } = renderPage();
    expect(container.querySelector('.animate-pulse')).not.toBeNull();
  });

  it('renders an error card when the tank fails to load', async () => {
    vi.mocked(api.getTank).mockRejectedValue(new Error('boom'));
    renderPage();
    expect(await screen.findByRole('alert')).toHaveTextContent('Failed to load tank.');
  });
});