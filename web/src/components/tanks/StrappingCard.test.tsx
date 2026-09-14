import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { beforeEach, describe, expect, it, vi } from 'vitest';

let role: string | null = 'admin';
vi.mock('../../store/auth', () => ({
  useAuthStore: (sel: (s: { user: { role: string } | null }) => unknown) =>
    sel({ user: role ? { role } : null }),
}));
vi.mock('../../api/client', () => ({
  api: { getStrapping: vi.fn(), saveStrapping: vi.fn() },
}));

import { api } from '../../api/client';
import { ApiError } from '../../api/http';
import StrappingCard from './StrappingCard';
import type { StrappingTable } from '../../lib/apiTypes';

const table: StrappingTable = {
  id: 'st1',
  tank_id: 't1',
  interpolation_method: 'linear',
  created_at: '2026-01-01T00:00:00Z',
  calibration_data: [
    { height: 0, volume: 0 },
    { height: 1, volume: 1000 },
    { height: 2, volume: 2200 },
  ],
};

function renderCard() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <StrappingCard tankId="t1" />
    </QueryClientProvider>,
  );
}

describe('StrappingCard', () => {
  beforeEach(() => {
    role = 'admin';
    vi.mocked(api.getStrapping).mockReset();
    vi.mocked(api.saveStrapping).mockReset();
    vi.mocked(api.getStrapping).mockResolvedValue(table as never);
    vi.mocked(api.saveStrapping).mockResolvedValue(table as never);
  });

  it('renders loading state', () => {
    vi.mocked(api.getStrapping).mockReturnValue(new Promise(() => {}));
    renderCard();
    expect(screen.getByText('Loading strapping table…')).toBeInTheDocument();
  });

  it('renders the strapping table read-only', async () => {
    renderCard();
    expect(await screen.findByText('Strapping table')).toBeInTheDocument();
    expect(screen.getByText('Interpolation: linear')).toBeInTheDocument();
    expect(screen.getByText('Height (m)')).toBeInTheDocument();
    expect(screen.getByText('Volume (L)')).toBeInTheDocument();
    expect(screen.getAllByText('0').length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText('1,000')).toBeInTheDocument();
    expect(screen.getByText('2,200')).toBeInTheDocument();
  });

  it('shows empty state when no data', async () => {
    vi.mocked(api.getStrapping).mockResolvedValue({
      id: 'st1',
      tank_id: 't1',
      interpolation_method: 'linear',
      calibration_data: [],
      created_at: '2026-01-01T00:00:00Z',
    } as never);
    renderCard();
    await waitFor(() => {
      expect(screen.getByText('No strapping table.')).toBeInTheDocument();
    });
  });

  it('shows error detail for ApiError', async () => {
    vi.mocked(api.getStrapping).mockRejectedValue(new ApiError(404, 'Not found'));
    renderCard();
    await waitFor(() => {
      expect(screen.getByText('Not found')).toBeInTheDocument();
    });
  });

  it('shows generic error for non-ApiError', async () => {
    vi.mocked(api.getStrapping).mockRejectedValue(new Error('network'));
    renderCard();
    await waitFor(() => {
      expect(screen.getByText('Failed to load strapping table')).toBeInTheDocument();
    });
  });

  it('shows Edit for managers only', async () => {
    renderCard();
    expect(await screen.findByRole('button', { name: /^edit$/i })).toBeInTheDocument();
  });

  it('hides Edit for non-managers', async () => {
    role = 'user';
    renderCard();
    await screen.findByText('Interpolation: linear');
    expect(screen.queryByRole('button', { name: /^edit$/i })).toBeNull();
  });

  it('saves edited rows and interpolation method', async () => {
    renderCard();
    await screen.findByRole('button', { name: /^edit$/i });
    await userEvent.click(screen.getByRole('button', { name: /^edit$/i }));
    await userEvent.selectOptions(screen.getByLabelText(/interpolation/i), 'cubic_spline');
    await userEvent.click(screen.getByRole('button', { name: /^save$/i }));
    await waitFor(() => expect(api.saveStrapping).toHaveBeenCalledTimes(1));
    const [tankId, payload] = vi.mocked(api.saveStrapping).mock.calls[0];
    expect(tankId).toBe('t1');
    expect(payload.interpolation_method).toBe('cubic_spline');
    expect(payload.calibration_data).toHaveLength(3);
  });

  it('blocks save with fewer than two rows', async () => {
    renderCard();
    await screen.findByRole('button', { name: /^edit$/i });
    await userEvent.click(screen.getByRole('button', { name: /^edit$/i }));
    const removes = screen.getAllByRole('button', { name: /remove row \d+/i });
    await userEvent.click(removes[0]);
    await userEvent.click(removes[0]);
    await userEvent.click(screen.getByRole('button', { name: /^save$/i }));
    expect(await screen.findByRole('alert')).toHaveTextContent('at least 2 points');
    expect(api.saveStrapping).not.toHaveBeenCalled();
  });

  it('blocks save when heights are not ascending', async () => {
    renderCard();
    await screen.findByRole('button', { name: /^edit$/i });
    await userEvent.click(screen.getByRole('button', { name: /^edit$/i }));
    const heights = screen.getAllByLabelText(/^height \d+$/i);
    await userEvent.clear(heights[2]);
    await userEvent.type(heights[2], '1');
    await userEvent.click(screen.getByRole('button', { name: /^save$/i }));
    expect(await screen.findByRole('alert')).toHaveTextContent('strictly ascending');
    expect(api.saveStrapping).not.toHaveBeenCalled();
  });
});