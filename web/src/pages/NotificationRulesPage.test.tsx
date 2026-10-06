import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import NotificationRulesPage from './NotificationRulesPage';
import { ApiError } from '../api/http';
import { useAuthStore } from '../store/auth';
import type { NotificationRule, UserRead } from '../lib/apiTypes';

const listRules = vi.fn();
const createRule = vi.fn();
const updateRule = vi.fn();
const deleteRule = vi.fn();
const listSites = vi.fn();

vi.mock('../api/admin', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../api/admin')>()),
  notificationApi: {
    listRules: (...args: unknown[]) => listRules(...args),
    createRule: (...args: unknown[]) => createRule(...args),
    updateRule: (...args: unknown[]) => updateRule(...args),
    deleteRule: (...args: unknown[]) => deleteRule(...args),
  },
}));

vi.mock('../api/client', () => ({
  api: { listSites: (...args: unknown[]) => listSites(...args) },
}));

const operator: UserRead = {
  id: 'u1',
  username: 'ca',
  email: 'ca@example.test',
  first_name: null,
  last_name: null,
  role: 'company_admin',
  company_id: 'c1',
  is_active: true,
  phone: null,
  last_login: null,
  created_at: '2026-01-01T00:00:00Z',
};

const RULE: NotificationRule = {
  id: 'r1',
  company_id: 'c1',
  name: 'Critical alarms to ops',
  event_type: 'alarm',
  min_level: 'CRITICAL',
  site_id: null,
  channel: 'sms',
  targets: ['+250788000000'],
  template: null,
  enabled: true,
  created_at: '2026-01-01T00:00:00Z',
};
const DISABLED: NotificationRule = { ...RULE, id: 'r2', name: 'Webhook mirror', channel: 'webhook', enabled: false, targets: ['https://ops.example/hook'] };

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <NotificationRulesPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('NotificationRulesPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useAuthStore.setState({ user: operator, token: 'tok' });
    listRules.mockResolvedValue([RULE, DISABLED]);
    listSites.mockResolvedValue([{ id: 's1', name: 'Main Depot' }]);
  });

  it('lists rules with their level, channel and targets', async () => {
    renderPage();
    expect(await screen.findByText('Critical alarms to ops')).toBeInTheDocument();
    expect(screen.getByText('+250788000000')).toBeInTheDocument();
    expect(screen.getAllByText('All sites').length).toBeGreaterThan(0);
    expect(screen.getByText('Enabled')).toBeInTheDocument();
    expect(screen.getByText('Disabled')).toBeInTheDocument();
  });

  it('states plainly that no rule means no notifications', async () => {
    listRules.mockResolvedValue([]);
    renderPage();
    expect(await screen.findByText('No notification rules')).toBeInTheDocument();
    expect(screen.getByText(/nobody is notified until a rule exists/i)).toBeInTheDocument();
  });

  it('splits multiple targets onto their own lines', async () => {
    listRules.mockResolvedValue([{ ...RULE, targets: ['+250788000000', 'ops@example.com'] }]);
    renderPage();
    expect(await screen.findByText('+250788000000')).toBeInTheDocument();
    expect(screen.getByText('ops@example.com')).toBeInTheDocument();
  });

  it('creates a rule with parsed targets', async () => {
    createRule.mockResolvedValue(RULE);
    renderPage();
    await screen.findByText('Critical alarms to ops');

    await userEvent.click(screen.getByRole('button', { name: 'New Rule' }));
    await userEvent.type(screen.getByLabelText('Name'), 'Critical to ops');
    await userEvent.selectOptions(screen.getByLabelText('Minimum level'), 'CRITICAL');
    await userEvent.selectOptions(screen.getByLabelText('Channel'), 'sms');
    await userEvent.type(screen.getByLabelText('Targets (one per line)'), '+250788000000\nops@example.com');
    await userEvent.click(screen.getByRole('button', { name: 'Create' }));

    await waitFor(() => expect(createRule).toHaveBeenCalledTimes(1));
    expect(createRule.mock.calls[0][0]).toMatchObject({
      name: 'Critical to ops',
      min_level: 'CRITICAL',
      channel: 'sms',
      targets: ['+250788000000', 'ops@example.com'],
    });
  });

  it('will not create a rule without a name or targets', async () => {
    renderPage();
    await screen.findByText('Critical alarms to ops');
    await userEvent.click(screen.getByRole('button', { name: 'New Rule' }));

    expect(screen.getByRole('button', { name: 'Create' })).toBeDisabled();
    await userEvent.type(screen.getByLabelText('Name'), 'x');
    expect(screen.getByRole('button', { name: 'Create' })).toBeDisabled();
    expect(createRule).not.toHaveBeenCalled();
  });

  it('surfaces the server error verbatim', async () => {
    createRule.mockRejectedValue(new ApiError(422, 'at least one channel must be active'));
    renderPage();
    await screen.findByText('Critical alarms to ops');
    await userEvent.click(screen.getByRole('button', { name: 'New Rule' }));
    await userEvent.type(screen.getByLabelText('Name'), 'Rule');
    await userEvent.type(screen.getByLabelText('Targets (one per line)'), '+250788000000');
    await userEvent.click(screen.getByRole('button', { name: 'Create' }));

    expect(await screen.findByText('at least one channel must be active')).toBeInTheDocument();
  });

  it('toggles a rule through the update endpoint', async () => {
    updateRule.mockResolvedValue({ ...RULE, enabled: false });
    renderPage();
    await screen.findByText('Critical alarms to ops');
    const row = screen.getByText('Critical alarms to ops').closest('tr')!;
    await userEvent.click(within(row).getByRole('button', { name: 'Disable' }));

    await waitFor(() => expect(updateRule).toHaveBeenCalledWith('r1', { enabled: false }));
  });

  it('confirms deletion and calls the endpoint', async () => {
    deleteRule.mockResolvedValue(undefined);
    renderPage();
    await screen.findByText('Critical alarms to ops');
    const row = screen.getByText('Critical alarms to ops').closest('tr')!;
    await userEvent.click(within(row).getByRole('button', { name: 'Delete' }));

    expect(await screen.findByText(/Alarms are still recorded/)).toBeInTheDocument();
    await userEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Delete' }));
    await waitFor(() => expect(deleteRule).toHaveBeenCalledWith('r1'));
  });

  it('offers an error card with retry on load failure', async () => {
    listRules.mockRejectedValue(new Error('down'));
    renderPage();
    expect(await screen.findByText('Could not load notification rules.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Retry' })).toBeInTheDocument();
  });
});