import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../api/client', () => ({
  api: {
    listTanks: vi.fn(),
    listFuelTypes: vi.fn(),
    listSites: vi.fn(),
  },
}));
import { api } from '../api/client';
import Tanks from './Tanks';

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <Tanks />
    </QueryClientProvider>,
  );
}

describe('Tanks', () => {
  beforeEach(() => {
    vi.mocked(api.listTanks).mockResolvedValue([] as never);
    vi.mocked(api.listFuelTypes).mockResolvedValue([] as never);
    vi.mocked(api.listSites).mockResolvedValue([] as never);
  });

  it('renders a page header with the New tank action', async () => {
    renderPage();
    expect(await screen.findByRole('heading', { level: 2, name: 'Tanks' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'New tank' })).toBeInTheDocument();
  });

  it('renders a skeleton while tanks are loading', () => {
    vi.mocked(api.listTanks).mockReturnValue(new Promise(() => {}) as never);
    const { container } = renderPage();
    expect(container.querySelector('.animate-pulse')).not.toBeNull();
  });

  it('renders an empty state when there are no tanks', async () => {
    renderPage();
    expect(await screen.findByText('No tanks')).toBeInTheDocument();
    expect(screen.getByRole('heading', { level: 2, name: 'Tanks' })).toBeInTheDocument();
  });
});