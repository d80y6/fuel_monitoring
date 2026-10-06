import { render, screen, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import AuditPage from './AuditPage';
import { useAuthStore } from '../store/auth';
import type { UserRead } from '../lib/apiTypes';

const listAudit = vi.fn();

vi.mock('../api/admin', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../api/admin')>()),
  auditApi: { list: (...args: unknown[]) => listAudit(...args) },
}));

const platformAdmin: UserRead = {
  id: 'u1',
  username: 'root',
  email: 'root@example.test',
  first_name: null,
  last_name: null,
  role: 'admin',
  company_id: null,
  is_active: true,
  phone: null,
  last_login: null,
  created_at: '2026-01-01T00:00:00Z',
};
const tenantAdmin: UserRead = {
  ...platformAdmin,
  id: 'u2',
  username: 'ca',
  role: 'company_admin',
  company_id: 'c1',
};

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <AuditPage />
    </QueryClientProvider>,
  );
}

/** The event name appears both in the table and in the action filter, so scope to the table. */
async function tableRows(): Promise<HTMLElement> {
  return screen.findByRole('table', { name: /audit events/i });
}

const EVENTS = [
  {
    id: 'e1',
    at: '2026-02-01T10:00:00Z',
    actor_id: 'u2',
    actor_username: 'ca',
    company_id: 'c1',
    action: 'tank.update',
    entity_type: 'tank',
    entity_id: 'tank-123',
    detail: { changed: ['low_level_threshold'] },
  },
  {
    id: 'e2',
    at: '2026-02-01T11:00:00Z',
    actor_id: 'u1',
    actor_username: 'root',
    company_id: null,
    action: 'user.create',
    entity_type: 'user',
    entity_id: 'u5',
    detail: null,
  },
];

describe('AuditPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useAuthStore.setState({ user: platformAdmin, token: 'tok' });
    listAudit.mockResolvedValue(EVENTS);
  });

  it('renders each event with actor, action and entity', async () => {
    renderPage();
    const table = await tableRows();
    expect(within(table).getByText('tank.update')).toBeInTheDocument();
    expect(within(table).getByText('user.create')).toBeInTheDocument();
    expect(within(table).getByText('ca')).toBeInTheDocument();
    expect(within(table).getByText('tank-123')).toBeInTheDocument();
  });

  it('renders the detail payload so a reviewer can see what changed', async () => {
    renderPage();
    expect(await screen.findByText(/low_level_threshold/)).toBeInTheDocument();
  });

  it('shows an empty state instead of an empty table', async () => {
    listAudit.mockResolvedValue([]);
    renderPage();
    expect(await screen.findByText('No audit events')).toBeInTheDocument();
    expect(screen.queryByRole('table')).not.toBeInTheDocument();
  });

  it('offers a retry when loading fails', async () => {
    listAudit.mockRejectedValue(new Error('down'));
    renderPage();
    expect(await screen.findByText('Could not load the audit log.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Retry' })).toBeInTheDocument();
  });

  it('requests the default page size with no filters', async () => {
    renderPage();
    await tableRows();
    const calls = listAudit.mock.calls;
    expect(calls[calls.length - 1][0]).toMatchObject({
      action: undefined,
      entity_type: undefined,
      limit: 100,
    });
  });

  it('passes the action filter through to the API', async () => {
    const { default: userEvent } = await import('@testing-library/user-event');
    renderPage();
    await tableRows();

    await userEvent.selectOptions(screen.getByLabelText('Filter by action'), 'tank.update');
    await waitFor(() =>
      expect(listAudit).toHaveBeenLastCalledWith(expect.objectContaining({ action: 'tank.update' })),
    );
  });

  it('renders for a tenant admin', async () => {
    useAuthStore.setState({ user: tenantAdmin });
    renderPage();
    const table = await tableRows();
    expect(within(table).getByText('tank.update')).toBeInTheDocument();
  });
});