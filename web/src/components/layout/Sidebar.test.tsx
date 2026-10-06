import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { Sidebar } from './Sidebar';
import { useAuthStore } from '../../store/auth';
import type { UserRead } from '../../lib/apiTypes';

vi.mock('../../hooks/useRealtimeAlarms', () => ({
  useRealtimeAlarms: () => [],
}));

function user(overrides: Partial<UserRead>): UserRead {
  return {
    id: 'u1',
    username: 'test',
    email: 't@t.io',
    first_name: null,
    last_name: null,
    role: 'user',
    company_id: 'c1',
    is_active: true,
    phone: null,
    last_login: null,
    created_at: '2026-01-01T00:00:00Z',
    ...overrides,
  };
}

const operator = user({});
const companyAdmin = user({ id: 'u3', username: 'ca', role: 'company_admin' });
const platformAdmin = user({ id: 'u2', username: 'root', role: 'admin', company_id: null });

describe('Sidebar', () => {
  beforeEach(() => {
    useAuthStore.setState({ user: operator, token: 'tok' });
  });

  it('gives a read-only operator only the operational pages', () => {
    render(
      <MemoryRouter>
        <Sidebar />
      </MemoryRouter>,
    );
    expect(screen.getByText('Dashboard')).toBeInTheDocument();
    expect(screen.getByText('Tanks')).toBeInTheDocument();
    expect(screen.getByText('Dispensing')).toBeInTheDocument();
    expect(screen.getByText('Alarm Center')).toBeInTheDocument();
    expect(screen.getByText('Reports')).toBeInTheDocument();
    expect(screen.getByText('Settings')).toBeInTheDocument();

    // Management and administration surfaces must be hidden.
    expect(screen.queryByText('Sites')).not.toBeInTheDocument();
    expect(screen.queryByText('Users')).not.toBeInTheDocument();
    expect(screen.queryByText('Audit Log')).not.toBeInTheDocument();
    expect(screen.queryByText('Companies')).not.toBeInTheDocument();
    expect(screen.queryByText('Fuel Types')).not.toBeInTheDocument();
  });

  it('gives a company admin management pages but not the cross-tenant Companies list', () => {
    useAuthStore.setState({ user: companyAdmin });
    render(
      <MemoryRouter>
        <Sidebar />
      </MemoryRouter>,
    );
    expect(screen.getByText('Sites')).toBeInTheDocument();
    expect(screen.getByText('Users')).toBeInTheDocument();
    expect(screen.getByText('Audit Log')).toBeInTheDocument();
    expect(screen.getByText('Fuel Types')).toBeInTheDocument();
    expect(screen.getByText('Channels')).toBeInTheDocument();
    expect(screen.getByText('IoT Gateways')).toBeInTheDocument();
    // Companies lists every tenant, so it stays platform-only.
    expect(screen.queryByText('Companies')).not.toBeInTheDocument();
  });

  it('gives a platform admin every section', () => {
    useAuthStore.setState({ user: platformAdmin });
    render(
      <MemoryRouter>
        <Sidebar />
      </MemoryRouter>,
    );
    expect(screen.getByText('Sites')).toBeInTheDocument();
    expect(screen.getByText('Companies')).toBeInTheDocument();
    expect(screen.getByText('Users')).toBeInTheDocument();
    expect(screen.getByText('Audit Log')).toBeInTheDocument();
    expect(screen.getByText('IoT Gateways')).toBeInTheDocument();
  });

  it('renders every nav item with an icon', () => {
    useAuthStore.setState({ user: platformAdmin });
    const { container } = render(
      <MemoryRouter>
        <Sidebar />
      </MemoryRouter>,
    );
    const links = container.querySelectorAll('nav a');
    expect(links.length).toBeGreaterThan(0);
    links.forEach((link) => {
      expect(link.querySelector('svg')).toBeTruthy();
      expect(link.textContent?.trim()).toBeTruthy();
    });
  });

  it('exposes an accessible navigation landmark', () => {
    const { container } = render(
      <MemoryRouter>
        <Sidebar />
      </MemoryRouter>,
    );
    expect(container.querySelector('nav[aria-label="Main"]')).toBeTruthy();
  });
});