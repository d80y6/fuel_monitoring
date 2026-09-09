import type { UserRead } from './apiTypes';

export function requireManage(user: UserRead | null): boolean {
  if (!user) return false;
  return user.is_superuser || user.role === 'admin' || user.role === 'manager';
}
