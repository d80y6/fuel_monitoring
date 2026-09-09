import { describe, expect, it } from 'vitest';
import { requireManage } from '../lib/roles';

describe('requireManage', () => {
  it('returns true for superuser', () => {
    expect(requireManage({ is_superuser: true, role: 'viewer' } as any)).toBe(true);
  });
  it('returns true for admin', () => {
    expect(requireManage({ is_superuser: false, role: 'admin' } as any)).toBe(true);
  });
  it('returns true for manager', () => {
    expect(requireManage({ is_superuser: false, role: 'manager' } as any)).toBe(true);
  });
  it('returns false for viewer', () => {
    expect(requireManage({ is_superuser: false, role: 'viewer' } as any)).toBe(false);
  });
  it('returns false for null user', () => {
    expect(requireManage(null)).toBe(false);
  });
});
