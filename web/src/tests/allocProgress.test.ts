import { describe, expect, it } from 'vitest';
import { progressPercent } from '../lib/allocProgress';

describe('progressPercent', () => {
  it('calculates percentage', () => {
    expect(progressPercent({ allocated_liters: 100, dispensed_liters: 40 } as any)).toBe(40);
  });
  it('caps at 100', () => {
    expect(progressPercent({ allocated_liters: 100, dispensed_liters: 150 } as any)).toBe(100);
  });
  it('returns 0 for zero allocation', () => {
    expect(progressPercent({ allocated_liters: 0, dispensed_liters: 0 } as any)).toBe(0);
  });
});
