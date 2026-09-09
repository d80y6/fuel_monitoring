import { render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, expect, it, vi, beforeEach } from 'vitest';

vi.mock('../../api/client', () => ({
  api: { listAllocations: vi.fn() },
}));
import { api } from '../../api/client';
import { ApiError } from '../../api/http';
import AllocationsCard from './AllocationsCard';

function renderCard() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <AllocationsCard />
    </QueryClientProvider>,
  );
}

const mockAllocation = {
  id: 'a1',
  employee_id: 'e1',
  employee_name: 'John Doe',
  invoice_number: 'INV-001',
  allocated_liters: 100,
  dispensed_liters: 50,
  remaining_liters: 50,
  status: 'IN_PROGRESS',
  created_at: '2026-01-15T10:00:00Z',
};

describe('AllocationsCard', () => {
  beforeEach(() => {
    vi.mocked(api.listAllocations).mockResolvedValue([]);
  });

  it('shows loading state', () => {
    vi.mocked(api.listAllocations).mockReturnValue(new Promise(() => {}));
    renderCard();
    expect(screen.getByText('Loading allocations…')).toBeInTheDocument();
  });

  it('shows error state', async () => {
    vi.mocked(api.listAllocations).mockRejectedValue(new ApiError(500, 'Server error'));
    renderCard();
    await waitFor(() => {
      expect(screen.getByText('Server error')).toBeInTheDocument();
    });
  });

  it('shows empty state', async () => {
    renderCard();
    await waitFor(() => {
      expect(screen.getByText('No allocations yet.')).toBeInTheDocument();
    });
  });

  it('renders allocation data', async () => {
    vi.mocked(api.listAllocations).mockResolvedValue([
      mockAllocation,
      { ...mockAllocation, id: 'a2', employee_name: 'Jane Smith', invoice_number: null },
    ]);
    renderCard();
    await waitFor(() => {
      expect(screen.getByText('John Doe')).toBeInTheDocument();
      expect(screen.getByText('INV-001')).toBeInTheDocument();
      expect(screen.getByText('Jane Smith')).toBeInTheDocument();
      expect(screen.getAllByText('—').length).toBeGreaterThan(0);
      expect(screen.getAllByText('100.0 L').length).toBe(2);
      expect(screen.getAllByText('50.0 L').length).toBe(4);
      expect(screen.getAllByText('50%').length).toBe(2);
      expect(screen.getAllByText('IN_PROGRESS').length).toBe(2);
    });
  });
});
