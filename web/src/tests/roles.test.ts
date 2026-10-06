import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';
import { ALL_ROLES, ROLES, canAdminister, canManage, requireManage } from '../lib/roles';
import type { UserRead } from '../lib/apiTypes';

function user(overrides: Partial<UserRead> = {}): UserRead {
  return {
    id: 'u1',
    username: 'test',
    email: 't@t.io',
    first_name: null,
    last_name: null,
    role: ROLES.USER,
    company_id: 'c1',
    is_active: true,
    phone: null,
    last_login: null,
    created_at: '2026-01-01T00:00:00Z',
    ...overrides,
  };
}

describe('role contract', () => {
  it('exposes exactly the roles the backend recognises', () => {
    expect([...ALL_ROLES].sort()).toEqual(['admin', 'company_admin', 'user']);
  });

  it('locks a company_admin into management and out of platform administration', () => {
    // The regression this file exists for: company_admin used to be rejected.
    expect(canManage(ROLES.COMPANY_ADMIN)).toBe(true);
    expect(requireManage(user({ role: ROLES.COMPANY_ADMIN }))).toBe(true);
    expect(canAdminister(ROLES.COMPANY_ADMIN)).toBe(false);
  });

  it('grants a platform admin both management and administration', () => {
    expect(canManage(ROLES.PLATFORM_ADMIN)).toBe(true);
    expect(canAdminister(ROLES.PLATFORM_ADMIN)).toBe(true);
  });

  it('denies a plain operator', () => {
    expect(canManage(ROLES.USER)).toBe(false);
    expect(requireManage(user())).toBe(false);
    expect(canAdminister(ROLES.USER)).toBe(false);
  });

  it('denies unknown and missing roles rather than defaulting to allow', () => {
    expect(canManage(undefined)).toBe(false);
    expect(canManage(null)).toBe(false);
    expect(canManage('manager')).toBe(false);
    expect(canManage('superuser')).toBe(false);
    expect(canManage('')).toBe(false);
  });

  it('denies a deactivated account even with a management role', () => {
    expect(requireManage(user({ role: ROLES.COMPANY_ADMIN, is_active: false }))).toBe(false);
  });

  it('rejects a null user', () => {
    expect(requireManage(null)).toBe(false);
    expect(requireManage(undefined)).toBe(false);
  });

  it('pins the role names to the backend source of truth', () => {
    // Reads the real backend files so the client cannot drift from the server.
    const backend = readFileSync(resolve(__dirname, '../../../platform/fmp/api/deps.py'), 'utf8');

    // The management guard must accept admin + company_admin, in that order.
    expect(backend).toContain('require_roles("admin", "company_admin")');

    const tenancy = readFileSync(resolve(__dirname, '../../../platform/fmp/core/tenancy.py'), 'utf8');
    // A platform operator is role 'admin' with no company.
    expect(tenancy).toContain('self.role == "admin" and self.company_id is None');

    const schemas = readFileSync(resolve(__dirname, '../../../platform/fmp/schemas/user.py'), 'utf8');
    expect(schemas).toContain('company_id: uuid.UUID | None = None');
  });
});