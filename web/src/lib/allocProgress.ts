import type { Allocation } from './apiTypes';

export function progressPercent(a: Allocation): number {
  if (!a.allocated_liters || a.allocated_liters === 0) return 0;
  return Math.min(100, Math.round((a.dispensed_liters / a.allocated_liters) * 100));
}
