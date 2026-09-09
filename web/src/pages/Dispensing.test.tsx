import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, expect, it, vi, beforeEach } from 'vitest';

vi.mock('../api/client', () => ({
  api: {
    listStations: vi.fn(),
    listTransactions: vi.fn(),
    listDispensers: vi.fn(),
    listAllocations: vi.fn(),
  },
}));
import { api } from '../api/client';

vi.mock('../store/auth', () => ({
  useAuthStore: vi.fn(),
}));
import { useAuthStore } from '../store/auth';

vi.mock('../components/dispensing/AllocationsCard', () => ({
  default: () => <div data-testid="card-Allocations" />,
}));

vi.mock('../components/dispensing/CodeOpsCard', () => ({
  CodeOpsCard: () => <div data-testid="card-CodeOps" />,
}));

vi.mock('../components/dispensing/UploadCard', () => ({
  default: () => <div data-testid="card-Upload" />,
}));

vi.mock('../hooks/useLiveDispensing', () => ({
  useLiveDispensing: () => ({ data: [] }),
  isActiveAllocation: () => false,
}));

vi.mock('../components/dispensing/DispenseLiveView', () => ({
  DispenseLiveView: () => <div data-testid="card-DispenseLive" />,
}));

import Dispensing from './Dispensing';

function renderPage(userOverride: { role: string } = { role: 'manager' }) {
  vi.mocked(useAuthStore).mockImplementation((selector: any) => {
    const state = { user: { role: userOverride.role, is_superuser: false, username: 'test' } };
    return typeof selector === 'function' ? selector(state) : state;
  });

  vi.mocked(api.listStations).mockResolvedValue([
    { id: 's1', name: 'Station A', site_id: 'c1', serial_number: 'SN-001', raspberry_pi_id: null, firmware_version: null, connection_status: 'online', last_heartbeat: null },
  ] as never);
  vi.mocked(api.listTransactions).mockResolvedValue([]);
  vi.mocked(api.listDispensers).mockResolvedValue([]);
  vi.mocked(api.listAllocations).mockResolvedValue([]);

  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <Dispensing />
    </QueryClientProvider>,
  );
}

describe('Dispensing page tabs', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders with Overview tab active by default', async () => {
    renderPage();
    expect(await screen.findByText('Station A')).toBeInTheDocument();
    expect(screen.getByTestId('card-DispenseLive')).toBeInTheDocument();
    expect(screen.getByText('Dispensers')).toBeInTheDocument();
    expect(screen.queryByTestId('card-Allocations')).not.toBeInTheDocument();
  });

  it('clicking Allocations shows the allocations card', async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByText('Station A');
    await user.click(screen.getByText('Allocations'));
    expect(screen.getByTestId('card-Allocations')).toBeInTheDocument();
  });

  it('clicking Operations shows the ops card', async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByText('Station A');
    await user.click(screen.getByRole('button', { name: /operations/i }));
    expect(screen.getByTestId('card-CodeOps')).toBeInTheDocument();
  });

  it('manager user can see and click Upload tab', async () => {
    const user = userEvent.setup();
    renderPage({ role: 'manager' });
    await screen.findByText('Station A');
    await user.click(screen.getByText('Upload'));
    expect(screen.getByTestId('card-Upload')).toBeInTheDocument();
  });

  it('non-manager user cannot see Upload tab', async () => {
    renderPage({ role: 'user' });
    await screen.findByText('Station A');
    expect(screen.queryByText('Upload')).not.toBeInTheDocument();
    expect(screen.queryByTestId('card-Upload')).not.toBeInTheDocument();
  });
});
