import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { Sidebar } from './Sidebar';
import { useAuthStore } from '../../store/auth';

vi.mock('../../hooks/useRealtimeAlarms', () => ({
  useRealtimeAlarms: () => [],
}));

const viewer = { id: 'u1', username: 'test', email: 't@t.io', first_name: null, last_name: null, role: 'viewer', is_superuser: false, is_active: true, phone: null, last_login: null, created_at: '2026-01-01T00:00:00Z' };
const admin = { id: 'u2', username: 'admin', email: 'a@t.io', first_name: null, last_name: null, role: 'admin', is_superuser: false, is_active: true, phone: null, last_login: null, created_at: '2026-01-01T00:00:00Z' };

describe('Sidebar', () => {
  beforeEach(() => {
    useAuthStore.setState({ user: viewer, token: 'tok' });
  });

  it('hides Operations and Admin sections for viewer', () => {
    render(<MemoryRouter><Sidebar /></MemoryRouter>);
    expect(screen.queryByText('Operations')).not.toBeInTheDocument();
    expect(screen.queryByText('Admin')).not.toBeInTheDocument();
    expect(screen.getByText('Dashboard')).toBeInTheDocument();
    expect(screen.getByText('Tanks')).toBeInTheDocument();
  });

  it('shows Operations and Admin for admin role', () => {
    useAuthStore.setState({ user: admin });
    render(<MemoryRouter><Sidebar /></MemoryRouter>);
    expect(screen.getByText('Operations')).toBeInTheDocument();
    expect(screen.getByText('Admin')).toBeInTheDocument();
    expect(screen.getByText('Companies')).toBeInTheDocument();
    expect(screen.getByText('Gateways')).toBeInTheDocument();
  });
});
