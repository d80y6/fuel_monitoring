import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, expect, it, vi, beforeEach } from 'vitest';

vi.mock('../api/client', () => ({
  api: { listTanks: vi.fn(), tankAlarms: vi.fn(), ackAlarm: vi.fn() },
}));
import { api } from '../api/client';
import AlarmCenter from './AlarmCenter';

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <AlarmCenter />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

function makeTank(overrides: Record<string, unknown> = {}) {
  return {
    id: 't1', name: 'Tank Alpha', site_id: 's1', sensor_serial_number: 'SN1',
    device_address: 1, tank_orientation: 'vertical', tank_diameter: 3, tank_height: 10,
    tank_length: null, tank_volume: 100, tank_shape: 'vertical_cylinder', fuel_type_id: 'f1',
    dish_depth: null, tank_width: null, strapping_table_id: null, elevation: null,
    calibration_factor: 1, atmospheric_pressure: 101325, low_level_threshold: null,
    critical_level_threshold: null, high_level_threshold: null, low_volume_threshold: null,
    high_volume_threshold: null, is_active: true, gateway_mac: null,
    created_at: '2026-01-01T00:00:00Z', connection_status: 'online', last_connection: null,
    ...overrides,
  } as never;
}

function makeAlarm(overrides: Record<string, unknown> = {}) {
  return {
    id: 'a1', tank_id: 't1', timestamp: '2026-09-09T10:00:00Z', type: 'low_level',
    level: 'warning', message: 'Level low', value: 1.5, acknowledged: false,
    acknowledged_at: null,
    ...overrides,
  } as never;
}

describe('AlarmCenter', () => {
  beforeEach(() => {
    vi.mocked(api.listTanks).mockResolvedValue([makeTank()] as never);
    vi.mocked(api.tankAlarms).mockResolvedValue([makeAlarm()] as never);
    vi.mocked(api.ackAlarm).mockResolvedValue({ alarm_id: 'a1', acknowledged: true } as never);
  });

  it('lists open alarms', async () => {
    renderPage();
    expect(await screen.findByText('Level low')).toBeInTheDocument();
    expect(screen.getByText('Tank Alpha')).toBeInTheDocument();
  });

  it('renders a page header', async () => {
    renderPage();
    await screen.findByText('Level low');
    expect(screen.getByRole('heading', { level: 2, name: 'Alarm Center' })).toBeInTheDocument();
  });

  it('renders a skeleton while alarms are loading', () => {
    vi.mocked(api.tankAlarms).mockReturnValue(new Promise(() => {}) as never);
    const { container } = renderPage();
    expect(container.querySelector('.animate-pulse')).not.toBeNull();
  });

  it('shows empty state when no alarms', async () => {
    vi.mocked(api.tankAlarms).mockResolvedValue([] as never);
    renderPage();
    expect(await screen.findByText('No open alarms.')).toBeInTheDocument();
  });

  it('ack button calls ackAlarm and invalidates query', async () => {
    renderPage();
    await screen.findByText('Level low');
    await userEvent.click(screen.getByRole('button', { name: /ack/i }));
    await waitFor(() => expect(api.ackAlarm).toHaveBeenCalledWith('t1', 'a1'));
  });
});
