import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../api/client', () => ({
  api: {
    getGateway: vi.fn(),
    getTank: vi.fn(),
    sendCommand: vi.fn(),
    listCommands: vi.fn(),
    updateGateway: vi.fn(),
  },
}));
import { api } from '../api/client';
import IoTGatewayDetailPage from './IoTGatewayDetailPage';

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={['/admin/iot-gateways/gw1']}>
        <Routes>
          <Route path="/admin/iot-gateways/:id" element={<IoTGatewayDetailPage />} />
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
  tank_ids: ['t1'],
  created_at: '2026-09-11T00:00:00Z',
};

const tank = {
  id: 't1',
  name: 'Tank T1',
  site_id: 'site-01',
  connection_status: 'online',
};

const hist = [
  {
    id: 'c1', command_id: 'cmd-1', gateway_id: 'gw1', command_type: 'reboot',
    payload_json: {}, status: 'acked', attempts: 1, max_attempts: 3,
    sent_at: '2026-09-11T00:01:00Z', next_retry_at: null,
    ack_status: 'executed', ack_detail: null, ack_received_at: '2026-09-11T00:01:02Z',
    error_message: null, created_at: '2026-09-11T00:01:00Z',
  },
];

describe('IoTGatewayDetailPage', () => {
  beforeEach(() => {
    vi.mocked(api.getGateway).mockResolvedValue(gw as never);
    vi.mocked(api.getTank).mockResolvedValue(tank as never);
    vi.mocked(api.listCommands).mockResolvedValue(hist as never);
  });

  it('renders summary + history', async () => {
    renderPage();
    expect(await screen.findByText('East Gate')).toBeInTheDocument();
    expect(await screen.findByText('reboot')).toBeInTheDocument();
    expect(screen.getByText('acked')).toBeInTheDocument();
    expect(screen.getByText('1 tank(s)')).toBeInTheDocument();
  });

  it('sends a reboot command via composer', async () => {
    vi.mocked(api.sendCommand).mockResolvedValue({ command_id: 'cmd-2', status: 'pending' } as never);
    renderPage();
    await userEvent.click(await screen.findByRole('button', { name: /send/i }));
    await waitFor(() => expect(api.sendCommand).toHaveBeenCalled());
  });

  it('hides composer for inactive gateway', async () => {
    vi.mocked(api.getGateway).mockResolvedValue({ ...gw, is_active: false } as never);
    renderPage();
    expect(await screen.findByText(/not provisioned/i)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /send/i })).not.toBeInTheDocument();
  });

  it('shows a no-payload hint and sends an empty payload for no-payload types', async () => {
    vi.mocked(api.sendCommand).mockResolvedValue({ command_id: 'cmd-3', status: 'pending' } as never);
    renderPage();
    expect(await screen.findByText('No payload required')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: /send/i }));
    await waitFor(() =>
      expect(api.sendCommand).toHaveBeenCalledWith('gw1', { command_type: 'reboot', payload: {} }),
    );
  });

  it('set_interval renders an interval field and sends { interval_s }', async () => {
    vi.mocked(api.sendCommand).mockResolvedValue({ command_id: 'cmd-4', status: 'pending' } as never);
    renderPage();
    await userEvent.selectOptions(await screen.findByLabelText('Command type'), 'set_interval');
    await userEvent.type(await screen.findByLabelText('Interval (seconds)'), '30');
    await userEvent.click(screen.getByRole('button', { name: /send/i }));
    await waitFor(() =>
      expect(api.sendCommand).toHaveBeenCalledWith('gw1', { command_type: 'set_interval', payload: { interval_s: 30 } }),
    );
  });

  it('recalibrate renders sensor + reference pressure fields and sends the payload', async () => {
    vi.mocked(api.sendCommand).mockResolvedValue({ command_id: 'cmd-5', status: 'pending' } as never);
    renderPage();
    await userEvent.selectOptions(await screen.findByLabelText('Command type'), 'recalibrate');
    await userEvent.type(await screen.findByLabelText('Sensor'), 'TNK-01');
    await userEvent.type(await screen.findByLabelText('Reference pressure (bar)'), '1.013');
    await userEvent.click(screen.getByRole('button', { name: /send/i }));
    await waitFor(() =>
      expect(api.sendCommand).toHaveBeenCalledWith('gw1', {
        command_type: 'recalibrate',
        payload: { sensor: 'TNK-01', reference_pressure_bar: 1.013 },
      }),
    );
  });

  it('renders the linked tanks panel with tank details', async () => {
    vi.mocked(api.getTank).mockResolvedValue({
      ...tank,
      name: 'Underground 1',
    } as never);
    renderPage();
    expect(await screen.findByText('Underground 1')).toBeInTheDocument();
    expect(screen.getByText('Linked tanks')).toBeInTheDocument();
    expect(screen.getByText('site-01')).toBeInTheDocument();
  });

  it('active toggle deactivates the gateway and hides the composer', async () => {
    vi.mocked(api.getGateway)
      .mockResolvedValueOnce(gw as never)
      .mockResolvedValue({ ...gw, is_active: false } as never);
    vi.mocked(api.updateGateway).mockResolvedValue({ ...gw, is_active: false } as never);
    renderPage();
    await screen.findByText('East Gate');
    const toggle = await screen.findByRole('checkbox', { name: /active/i });
    expect(toggle).toBeChecked();
    await userEvent.click(toggle);
    await waitFor(() => expect(api.updateGateway).toHaveBeenCalledWith('gw1', { is_active: false }));
    await waitFor(() => expect(screen.queryByRole('button', { name: /send/i })).not.toBeInTheDocument());
  });
});