import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../api/client', () => ({
  api: {
    listStations: vi.fn(),
    listDispensers: vi.fn(),
    listTotalizers: vi.fn(),
    listTransactions: vi.fn(),
  },
}));
import { api } from '../api/client';

vi.mock('../components/charts/TotalizerDriftChart', () => ({
  TotalizerDriftChart: () => <div data-testid="mock-drift-chart" />,
}));

import Totalizers from './Totalizers';

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <Totalizers />
    </QueryClientProvider>,
  );
}

describe('Totalizers', () => {
  beforeEach(() => {
    vi.mocked(api.listStations).mockResolvedValue([] as never);
    vi.mocked(api.listDispensers).mockResolvedValue([] as never);
    vi.mocked(api.listTotalizers).mockResolvedValue([] as never);
    vi.mocked(api.listTransactions).mockResolvedValue([] as never);
  });

  it('renders a page header', async () => {
    renderPage();
    expect(await screen.findByRole('heading', { level: 2, name: 'Totalizers' })).toBeInTheDocument();
  });

  it('renders an empty state when there is no drift data', async () => {
    renderPage();
    expect(await screen.findByText('No totalizer drift data')).toBeInTheDocument();
  });
});