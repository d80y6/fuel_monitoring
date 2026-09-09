import type { UserRead } from './apiTypes';

export function canManage(role?: string): boolean {
  return role === 'admin' || role === 'manager';
}

export function requireManage(user: UserRead | null): boolean {
  if (!user) return false;
  return user.is_superuser || canManage(user.role);
}
