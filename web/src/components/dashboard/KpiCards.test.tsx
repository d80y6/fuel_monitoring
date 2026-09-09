import { render, screen, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, expect, it, vi, beforeEach } from 'vitest';

vi.mock('../../api/client', () => ({
  api: { listTanks: vi.fn(), listTransactions: vi.fn(), listStations: vi.fn() },
}));

vi.mock('../../hooks/useRealtimeAlarms', () => ({
  useRealtimeAlarms: () => [{ id: 'a1', acknowledged: false }],
}));

import { api } from '../../api/client';
import { KpiCards } from './KpiCards';

function renderCards() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <KpiCards />
    </QueryClientProvider>,
  );
}

function card(label: string) {
  return within(screen.getByText(label).parentElement as HTMLElement);
}

describe('KpiCards', () => {
  beforeEach(() => {
    vi.mocked(api.listTanks).mockResolvedValue([] as never);
    vi.mocked(api.listTransactions).mockResolvedValue([] as never);
    vi.mocked(api.listStations).mockResolvedValue([] as never);
  });

  it('renders tanks count, stations online, and open alarms', async () => {
    vi.mocked(api.listTanks).mockResolvedValue([
      { id: 't1' },
      { id: 't2' },
    ] as never);
    vi.mocked(api.listStations).mockResolvedValue([
      { id: 's1', connection_status: 'online' },
      { id: 's2', connection_status: 'offline' },
    ] as never);

    renderCards();

    await waitFor(() => {
      expect(card('Tanks').getByText('2')).toBeInTheDocument();
      expect(card('Stations online').getByText('1')).toBeInTheDocument();
      expect(card('Open alarms').getByText('1')).toBeInTheDocument();
    });
  });
});