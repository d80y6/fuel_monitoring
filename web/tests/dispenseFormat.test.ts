import { describe, expect, it } from 'vitest';
import {
  formatLiters,
  formatRemaining,
  statusColor,
} from '../src/lib/dispenseFormat';

describe('formatLiters', () => {
  it('renders liters with one decimal', () => {
    expect(formatLiters(12.5)).toBe('12.5 L');
    expect(formatLiters(0)).toBe('0.0 L');
    expect(formatLiters(null)).toBe('—');
  });
});

describe('formatRemaining', () => {
  it('renders remaining liters with sign, or a completed marker at ~0', () => {
    expect(formatRemaining(50)).toBe('50.0 L left');
    expect(formatRemaining(0.0001)).toBe('done');
    expect(formatRemaining(-0.0001)).toBe('done');
  });
});

describe('statusColor', () => {
  it('maps backend UPPERCASE statuses to tailwind classes, defaulting to slate', () => {
    expect(statusColor('PENDING')).toBe('bg-amber-100 text-amber-700');
    expect(statusColor('IN_PROGRESS')).toBe('bg-blue-100 text-blue-700');
    expect(statusColor('COMPLETED')).toBe('bg-emerald-100 text-emerald-700');
    expect(statusColor('PARTIAL')).toBe('bg-sky-100 text-sky-700');
    expect(statusColor('OVER_DISPENSE')).toBe('bg-orange-100 text-orange-700');
    expect(statusColor('DISCREPANCY')).toBe('bg-rose-100 text-rose-700');
    expect(statusColor('EXPIRED')).toBe('bg-slate-100 text-slate-500');
    expect(statusColor('unknown_thing')).toBe('bg-slate-100 text-slate-600');
  });

  it('is case-insensitive', () => {
    expect(statusColor('completed')).toBe('bg-emerald-100 text-emerald-700');
  });
});
