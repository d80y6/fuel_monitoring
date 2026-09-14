import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import ConsumptionCard from './ConsumptionCard';

vi.mock('echarts-for-react', () => ({ default: () => <div data-testid="mock-echarts" /> }));
vi.mock('../../hooks/useTheme', () => ({ useTheme: () => ({ resolvedScheme: 'light' }) }));
vi.mock('../../api/client', () => ({ api: { getConsumption: vi.fn() } }));

import { api } from '../../api/client';
import type { ConsumptionAnalytics } from '../../lib/apiTypes';

const analytics: ConsumptionAnalytics = {
  tank_id: 't1',
  days: 30,
  method: 'sma',
  forecast: { method: 'sma', window_days: 7, liters_per_day: 412.6 },
  series: [
    { date: '2026-08-01', liters: 400 },
    { date: '2026-08-02', liters: 425 },
  ],
};

function renderCard() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <ConsumptionCard tankId="t1" />
    </QueryClientProvider>,
  );
}

describe('ConsumptionCard', () => {
  beforeEach(() => { vi.mocked(api.getConsumption).mockReset(); });

  it('renders the forecast and chart from analytics', async () => {
    vi.mocked(api.getConsumption).mockResolvedValue(analytics as never);
    renderCard();
    expect(await screen.findByText('Consumption (last 30 days)')).toBeInTheDocument();
    expect(screen.getByText(/413 L\/day/)).toBeInTheDocument();
    expect(screen.getByTestId('mock-echarts')).toBeInTheDocument();
    expect(api.getConsumption).toHaveBeenCalledWith('t1', 30);
  });

  it('shows an empty state when there is no series', async () => {
    vi.mocked(api.getConsumption).mockResolvedValue({ ...analytics, series: [] } as never);
    renderCard();
    expect(await screen.findByText('No consumption data')).toBeInTheDocument();
    expect(screen.queryByTestId('mock-echarts')).toBeNull();
  });

  it('shows a dash forecast when liters_per_day is null', async () => {
    vi.mocked(api.getConsumption).mockResolvedValue({
      ...analytics,
      forecast: { ...analytics.forecast, liters_per_day: null },
    } as never);
    renderCard();
    expect(await screen.findByText('Consumption (last 30 days)')).toBeInTheDocument();
    expect(screen.getByText(/Forecast: —/)).toBeInTheDocument();
    expect(screen.getByTestId('mock-echarts')).toBeInTheDocument();
  });
});