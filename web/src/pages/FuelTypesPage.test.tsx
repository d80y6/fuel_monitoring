import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, expect, it, vi, beforeEach } from 'vitest';

vi.mock('../api/client', () => ({
  api: { listFuelTypes: vi.fn(), createFuelType: vi.fn() },
}));
import { api } from '../api/client';
import FuelTypesPage from './FuelTypesPage';

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(<QueryClientProvider client={qc}><MemoryRouter><FuelTypesPage /></MemoryRouter></QueryClientProvider>);
}

const fuelType = {
  id: 'ft1',
  code: 'diesel',
  name: 'Diesel',
  base_density: 0.85,
  thermal_expansion_coeff: 0.0007,
  max_vapor_pressure: 0.6,
  viscosity_cst: 3.0,
  created_at: '2026-01-01T00:00:00Z',
};

describe('FuelTypesPage', () => {
  beforeEach(() => { vi.mocked(api.listFuelTypes).mockResolvedValue([fuelType] as never); });

  it('renders fuel type list', async () => {
    renderPage();
    expect(await screen.findByText('Diesel')).toBeInTheDocument();
    expect(screen.getByText('diesel')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /new fuel type/i })).toBeInTheDocument();
  });

  it('opens create dialog and submits', async () => {
    vi.mocked(api.createFuelType).mockResolvedValue({ ...fuelType, id: 'ft2', code: 'gasoline', name: 'Gasoline' } as never);
    renderPage();
    await userEvent.click(await screen.findByRole('button', { name: /new fuel type/i }));
    fireEvent.change(screen.getByLabelText(/^code$/i), { target: { value: 'gasoline' } });
    fireEvent.change(screen.getByLabelText(/^name$/i), { target: { value: 'Gasoline' } });
    fireEvent.change(screen.getByLabelText(/^density$/i), { target: { value: '0.75' } });
    fireEvent.change(screen.getByLabelText(/thermal exp/i), { target: { value: '0.0008' } });
    fireEvent.change(screen.getByLabelText(/vapor p/i), { target: { value: '0.5' } });
    fireEvent.change(screen.getByLabelText(/viscosity/i), { target: { value: '2.5' } });
    const form = screen.getByRole('button', { name: /^create$/i }).closest('form');
    fireEvent.submit(form!);
    await waitFor(() => {
      expect(api.createFuelType).toHaveBeenCalledWith({
        code: 'gasoline',
        name: 'Gasoline',
        base_density: 0.75,
        thermal_expansion_coeff: 0.0008,
        max_vapor_pressure: 0.5,
        viscosity_cst: 2.5,
      });
    });
  });
});
