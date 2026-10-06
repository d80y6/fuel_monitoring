import type { UserRead } from './apiTypes';

/**
 * Authorization model — single source of truth on the client.
 *
 * These names MUST match the backend's `User.role` values and the guard
 * dependencies in `platform/fmp/api/deps.py`:
 *
 *   role            backend dependency       sees
 *   --------------  -----------------------  -------------------------------
 *   admin           PrivilegedUser + Admin   every tenant (platform operator)
 *   company_admin   PrivilegedUser           its own company only
 *   user            CurrentUser              its own company, read-only
 *
 * This file previously used a `manager` role and an `is_superuser` flag, neither
 * of which exists server-side: `company_admin` — the tenant administrator — was
 * locked out of every management route, and no account could ever satisfy the
 * superuser branch. `tests/roles.test.ts` now pins these values against the
 * backend source so the drift cannot come back.
 */
export const ROLES = {
  /** Platform operator: cross-tenant, may administer users and organizations. */
  PLATFORM_ADMIN: 'admin',
  /** Tenant administrator: manages assets within its own company. */
  COMPANY_ADMIN: 'company_admin',
  /** Tenant operator: read-only across its own company. */
  USER: 'user',
} as const;

export type Role = (typeof ROLES)[keyof typeof ROLES];

/** Every role the backend recognises. Keep in sync with `User.role` (schemas/user.py). */
export const ALL_ROLES: readonly string[] = Object.values(ROLES);

/** Roles allowed to mutate configuration and assets. Mirrors `require_roles("admin", "company_admin")`. */
const MANAGEMENT_ROLES: readonly string[] = [ROLES.PLATFORM_ADMIN, ROLES.COMPANY_ADMIN];

/** Roles allowed to administer users, organizations and platform-wide settings. */
const ADMINISTRATION_ROLES: readonly string[] = [ROLES.PLATFORM_ADMIN];

export function isPlatformAdmin(user: UserRead | null | undefined): boolean {
  return user?.role === ROLES.PLATFORM_ADMIN;
}

/**
 * Can this user create/edit/deactivate configuration and assets?
 * Both the platform admin and a tenant admin can.
 */
export function canManage(role?: string | null): boolean {
  return !!role && MANAGEMENT_ROLES.includes(role);
}

export function requireManage(user: UserRead | null | undefined): boolean {
  return !!user && user.is_active && canManage(user.role);
}

/** Platform-level administration only (users, organizations, cross-tenant views). */
export function canAdminister(role?: string | null): boolean {
  return !!role && ADMINISTRATION_ROLES.includes(role);
}

/**
 * True when the account is bound to a tenant.
 *
 * A platform admin has no `company_id` and sees every organization; every other
 * account is scoped to exactly one company by the server.
 */
export function isTenantBound(user: UserRead | null | undefined): boolean {
  return !!user && user.company_id !== null && user.company_id !== undefined;
}