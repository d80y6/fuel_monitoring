import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, expect, it, vi, beforeEach } from 'vitest';

vi.mock('../api/client', () => ({
  api: { listGateways: vi.fn(), createGateway: vi.fn(), updateGateway: vi.fn(), deleteGateway: vi.fn() },
}));
import { api } from '../api/client';
import GatewaysPage from './GatewaysPage';

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(<QueryClientProvider client={qc}><MemoryRouter><GatewaysPage /></MemoryRouter></QueryClientProvider>);
}

const gw = {
  id: 'g1',
  name: 'SMTP relay',
  type: 'smpp',
  config_json: {},
  is_active: true,
  priority: 10,
  created_at: '2026-01-01T00:00:00Z',
};

describe('GatewaysPage', () => {
  beforeEach(() => {
    vi.mocked(api.listGateways).mockResolvedValue([gw] as never);
  });

  it('renders gateway list', async () => {
    renderPage();
    expect(await screen.findByText('SMTP relay')).toBeInTheDocument();
    expect(screen.getByText('smpp')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /new gateway/i })).toBeInTheDocument();
  });

  it('opens create dialog and submits', async () => {
    vi.mocked(api.createGateway).mockResolvedValue({
      id: 'g2', name: 'New gateway', type: 'smpp', config_json: {}, is_active: true, priority: 10, created_at: '2026-01-02T00:00:00Z',
    } as never);
    renderPage();
    await userEvent.click(await screen.findByRole('button', { name: /new gateway/i }));
    await userEvent.type(screen.getByLabelText(/^name$/i), 'New gateway');
    await userEvent.click(screen.getByRole('button', { name: /^create$/i }));
    await waitFor(() =>
      expect(api.createGateway).toHaveBeenCalledWith(
        expect.objectContaining({ name: 'New gateway', type: 'smpp', config_json: {}, is_active: true, priority: 10 }),
      ),
    );
  });

  it('opens edit dialog, updates config, and submits', async () => {
    vi.mocked(api.updateGateway).mockResolvedValue(gw as never);
    renderPage();
    await userEvent.click(await screen.findByRole('button', { name: /^edit$/i }));
    await userEvent.clear(screen.getByLabelText(/^config$/i));
    fireEvent.change(screen.getByLabelText(/^config$/i), { target: { value: '{"host":"x"}' } });
    await userEvent.click(screen.getByRole('checkbox', { name: /active/i }));
    await userEvent.click(screen.getByRole('button', { name: /^save$/i }));
    await waitFor(() =>
      expect(api.updateGateway).toHaveBeenCalledWith(
        'g1',
        expect.objectContaining({ is_active: false, priority: 10, config_json: { host: 'x' } }),
      ),
    );
    expect(api.updateGateway).not.toHaveBeenCalledWith('g1', expect.objectContaining({ name: 'SMTP relay' }));
  });

  it('disables name and type when editing', async () => {
    renderPage();
    await userEvent.click(await screen.findByRole('button', { name: /^edit$/i }));
    expect(screen.getByLabelText(/^name$/i)).toBeDisabled();
    expect(screen.getByLabelText(/^type$/i)).toBeDisabled();
    expect(screen.getAllByText('Not editable after creation.')).toHaveLength(2);
  });

  it('deletes a gateway after confirmation', async () => {
    vi.mocked(api.deleteGateway).mockResolvedValue(undefined as never);
    renderPage();
    await userEvent.click(await screen.findByRole('button', { name: /^delete$/i }));
    expect(await screen.findByText('Delete "SMTP relay"?')).toBeInTheDocument();
    await userEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: /^delete$/i }));
    await waitFor(() => expect(api.deleteGateway).toHaveBeenCalledWith('g1'));
  });
});