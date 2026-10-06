import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError } from '../api/http';
import UsersPage from './UsersPage';
import { useAuthStore } from '../store/auth';
import type { UserRead } from '../lib/apiTypes';

const listUsers = vi.fn();
const createUser = vi.fn();
const updateUser = vi.fn();
const setPassword = vi.fn();
const deactivate = vi.fn();
const restore = vi.fn();
const listCompanies = vi.fn();

vi.mock('../api/admin', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../api/admin')>()),
  userAdminApi: {
    list: (...args: unknown[]) => listUsers(...args),
    create: (...args: unknown[]) => createUser(...args),
    update: (...args: unknown[]) => updateUser(...args),
    setPassword: (...args: unknown[]) => setPassword(...args),
    deactivate: (...args: unknown[]) => deactivate(...args),
    restore: (...args: unknown[]) => restore(...args),
  },
}));

vi.mock('../api/client', () => ({
  api: { listCompanies: (...args: unknown[]) => listCompanies(...args) },
}));

const alphaUser: UserRead = {
  id: 'u1',
  username: 'alpha_admin',
  email: 'alpha@example.test',
  first_name: 'Ada',
  last_name: null,
  role: 'company_admin',
  company_id: 'c-alpha',
  is_active: true,
  phone: null,
  last_login: null,
  created_at: '2026-01-01T00:00:00Z',
};
const betaUser: UserRead = { ...alphaUser, id: 'u2', username: 'beta_admin', email: 'b@e.test' };
const platformRoot: UserRead = { ...alphaUser, id: 'u9', username: 'root', role: 'admin', company_id: null };
const deactivated: UserRead = { ...alphaUser, id: 'u3', username: 'gone', is_active: false };

function renderPage() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <UsersPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('UsersPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useAuthStore.setState({ user: alphaUser, token: 'tok' });
    listUsers.mockResolvedValue([alphaUser, betaUser, deactivated]);
    listCompanies.mockResolvedValue([
      { id: 'c-alpha', name: 'Alpha Corp' },
      { id: 'c-beta', name: 'Beta Corp' },
    ]);
  });

  it('lists the accounts returned by the API', async () => {
    renderPage();
    expect(await screen.findByText('alpha_admin')).toBeInTheDocument();
    expect(screen.getByText('beta_admin')).toBeInTheDocument();
    expect(screen.getByText('gone')).toBeInTheDocument();
  });

  it('marks deactivated accounts so they are distinguishable from active ones', async () => {
    renderPage();
    expect(await screen.findByText('Deactivated')).toBeInTheDocument();
    expect(screen.getAllByText('Active').length).toBeGreaterThan(0);
  });

  it('hides the organization column from a tenant admin', async () => {
    renderPage();
    await screen.findByText('alpha_admin');
    expect(screen.queryByRole('columnheader', { name: 'Organization' })).not.toBeInTheDocument();
    expect(screen.queryByRole('combobox', { name: 'Filter by organization' })).not.toBeInTheDocument();
  });

  it('shows the organization selector to a platform admin', async () => {
    useAuthStore.setState({ user: platformRoot });
    renderPage();
    await screen.findByText('alpha_admin');
    expect(screen.getByRole('columnheader', { name: 'Organization' })).toBeInTheDocument();
    expect(screen.getByRole('combobox', { name: 'Filter by organization' })).toBeInTheDocument();
    expect((await screen.findAllByText('Alpha Corp')).length).toBeGreaterThan(0);
  });

  it('opens the create form and submits a real payload', async () => {
    createUser.mockResolvedValue(alphaUser);
    renderPage();
    await screen.findByText('alpha_admin');

    await userEvent.click(screen.getByRole('button', { name: 'New User' }));
    await userEvent.type(screen.getByLabelText('Username'), 'newoperator');
    await userEvent.type(screen.getByLabelText('Email'), 'new@example.test');
    await userEvent.type(screen.getByLabelText('Password'), 'Sup3rSecret!');
    await userEvent.click(screen.getByRole('button', { name: 'Create' }));

    await waitFor(() => expect(createUser).toHaveBeenCalledTimes(1));
    const payload = createUser.mock.calls[0][0];
    expect(payload).toMatchObject({
      username: 'newoperator',
      email: 'new@example.test',
      password: 'Sup3rSecret!',
    });
  });

  it('refuses to submit an invalid email or a too-short username', async () => {
    renderPage();
    await screen.findByText('alpha_admin');
    await userEvent.click(screen.getByRole('button', { name: 'New User' }));

    const submit = screen.getByRole('button', { name: 'Create' });
    expect(submit).toBeDisabled();

    await userEvent.type(screen.getByLabelText('Username'), 'ab');
    await userEvent.type(screen.getByLabelText('Email'), 'not-an-email');
    await userEvent.type(screen.getByLabelText('Password'), 'x');
    expect(submit).toBeDisabled();
    expect(createUser).not.toHaveBeenCalled();
  });

  it('surfaces the server error message instead of a generic failure', async () => {
    createUser.mockRejectedValue(new ApiError(409, 'username already exists'));
    renderPage();
    await screen.findByText('alpha_admin');
    await userEvent.click(screen.getByRole('button', { name: 'New User' }));
    await userEvent.type(screen.getByLabelText('Username'), 'taken');
    await userEvent.type(screen.getByLabelText('Email'), 'taken@example.test');
    await userEvent.type(screen.getByLabelText('Password'), 'Sup3rSecret!');
    await userEvent.click(screen.getByRole('button', { name: 'Create' }));

    expect(await screen.findByText('username already exists')).toBeInTheDocument();
  });

  it('sets a password through the dedicated endpoint', async () => {
    setPassword.mockResolvedValue({ status: 'ok' });
    renderPage();
    await screen.findByText('alpha_admin');

    const row = screen.getByText('alpha_admin').closest('tr')!;
    await userEvent.click(within(row).getByRole('button', { name: 'Password' }));
    await userEvent.type(screen.getByLabelText('New password'), 'An0therSecret!');
    await userEvent.click(screen.getByRole('button', { name: 'Set password' }));

    await waitFor(() => expect(setPassword).toHaveBeenCalledWith('u1', 'An0therSecret!'));
  });

  it('confirms before deactivating, then calls the endpoint', async () => {
    deactivate.mockResolvedValue(alphaUser);
    renderPage();
    await screen.findByText('alpha_admin');

    // Deactivate a different account: the signed-in user cannot deactivate itself.
    const row = screen.getByText('beta_admin').closest('tr')!;
    await userEvent.click(within(row).getByRole('button', { name: 'Deactivate' }));

    expect(await screen.findByText(/will no longer be able to sign in/)).toBeInTheDocument();
    await userEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Deactivate' }));
    await waitFor(() => expect(deactivate).toHaveBeenCalledWith('u2'));
  });

  it('disables self-deactivation so an admin cannot lock themselves out', async () => {
    renderPage();
    await screen.findByText('alpha_admin');
    const selfRow = screen.getByText('alpha_admin').closest('tr')!;
    expect(within(selfRow).getByRole('button', { name: 'Deactivate' })).toBeDisabled();
  });

  it('offers restore instead of deactivate for an inactive account', async () => {
    renderPage();
    await screen.findByText('gone');
    const row = screen.getByText('gone').closest('tr')!;
    expect(within(row).getByRole('button', { name: 'Restore' })).toBeInTheDocument();
    expect(within(row).queryByRole('button', { name: 'Deactivate' })).not.toBeInTheDocument();
  });

  it('shows an empty state rather than a blank table', async () => {
    listUsers.mockResolvedValue([]);
    renderPage();
    expect(await screen.findByText('No users')).toBeInTheDocument();
  });

  it('shows an error card with a retry affordance when loading fails', async () => {
    listUsers.mockRejectedValue(new Error('boom'));
    renderPage();
    expect(await screen.findByText('Could not load users.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Retry' })).toBeInTheDocument();
  });
});
