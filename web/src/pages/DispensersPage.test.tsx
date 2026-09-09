import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, expect, it, vi, beforeEach } from 'vitest';

vi.mock('../api/client', () => ({
  api: { listDispensers: vi.fn(), createDispenser: vi.fn(), updateDispenser: vi.fn() },
}));
import { api } from '../api/client';
import DispensersPage from './DispensersPage';

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={['/dispensers/st1']}>
        <Routes>
          <Route path="/dispensers/:stationId" element={<DispensersPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('DispensersPage', () => {
  beforeEach(() => {
    vi.mocked(api.listDispensers).mockResolvedValue([
      { id: 'd1', name: 'Pump 1', station_id: 'st1', serial_number: 'DN1', modbus_address: 1, dispenser_model: 'X200', is_active: true },
    ] as never);
  });

  it('renders dispensers with active toggle', async () => {
    vi.mocked(api.updateDispenser).mockResolvedValue({
      id: 'd1', name: 'Pump 1', station_id: 'st1', serial_number: 'DN1', modbus_address: 1, dispenser_model: 'X200', is_active: false,
    } as never);
    renderPage();
    expect(await screen.findByText('Pump 1')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: /deactivate/i }));
    await waitFor(() => expect(api.updateDispenser).toHaveBeenCalledWith('d1', { is_active: false }));
  });

  it('opens create dialog and submits', async () => {
    vi.mocked(api.createDispenser).mockResolvedValue({
      id: 'd2', name: 'Pump 2', station_id: 'st1', serial_number: 'DN2', modbus_address: 2, dispenser_model: null, is_active: true,
    } as never);
    renderPage();
    await screen.findByText('Pump 1');
    await userEvent.click(screen.getByRole('button', { name: /new dispenser/i }));
    expect(screen.getByRole('dialog')).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText(/name/i), 'Pump 2');
    await userEvent.type(screen.getByLabelText(/modbus/i), '2');
    await userEvent.click(screen.getByRole('button', { name: /create/i }));
    await waitFor(() => expect(api.createDispenser).toHaveBeenCalledWith({
      station_id: 'st1', name: 'Pump 2', modbus_address: 2, dispenser_model: '',
    }));
  });
});
