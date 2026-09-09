import { render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, expect, it, vi, beforeEach } from 'vitest';

vi.mock('../../api/client', () => ({
  api: { getStrapping: vi.fn() },
}));
import { api } from '../../api/client';
import { ApiError } from '../../api/http';
import StrappingCard from './StrappingCard';

function renderCard(tankId = 'tank-1') {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <StrappingCard tankId={tankId} />
    </QueryClientProvider>,
  );
}

describe('StrappingCard', () => {
  beforeEach(() => {
    vi.mocked(api.getStrapping).mockResolvedValue({
      id: 's1',
      tank_id: 'tank-1',
      interpolation_method: 'linear',
      calibration_data: [
        { height: 0, volume: 0 },
        { height: 1.5, volume: 1200 },
      ],
      created_at: '2026-01-01T00:00:00Z',
    });
  });

  it('renders loading state', () => {
    vi.mocked(api.getStrapping).mockReturnValue(new Promise(() => {}));
    renderCard();
    expect(screen.getByText('Loading strapping table…')).toBeInTheDocument();
  });

  it('renders table with interpolation and row values', async () => {
    renderCard();
    await waitFor(() => {
      expect(screen.getByText('Strapping table')).toBeInTheDocument();
      expect(screen.getByText('Interpolation: linear')).toBeInTheDocument();
      expect(screen.getByText('Height (m)')).toBeInTheDocument();
      expect(screen.getByText('Volume (L)')).toBeInTheDocument();
      expect(screen.getAllByText('0').length).toBeGreaterThanOrEqual(1);
      expect(screen.getByText('1,200')).toBeInTheDocument();
    });
  });

  it('shows empty state when no data', async () => {
    vi.mocked(api.getStrapping).mockResolvedValue({
      id: 's1',
      tank_id: 'tank-1',
      interpolation_method: 'linear',
      calibration_data: [],
      created_at: '2026-01-01T00:00:00Z',
    });
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
});
