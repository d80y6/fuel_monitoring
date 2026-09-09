import type { AllocationRead, TransactionRead } from './apiTypes';

export function formatLiters(v: number | null | undefined): string {
  return v == null ? '—' : `${v.toFixed(1)} L`;
}

export function formatRemaining(v: number | null | undefined): string {
  if (v == null) return '—';
  return Math.abs(v) < 0.01 ? 'done' : `${v.toFixed(1)} L left`;
}

const STATUS_STYLES: Record<string, string> = {
  PENDING: 'bg-amber-100 text-amber-700',
  IN_PROGRESS: 'bg-blue-100 text-blue-700',
  COMPLETED: 'bg-emerald-100 text-emerald-700',
  PARTIAL: 'bg-sky-100 text-sky-700',
  OVER_DISPENSE: 'bg-orange-100 text-orange-700',
  DISCREPANCY: 'bg-rose-100 text-rose-700',
  'OVER_DISPENSE/PENDING': 'bg-orange-100 text-orange-700',
  EXPIRED: 'bg-slate-100 text-slate-500',
  VOIDED: 'bg-neutral-100 text-neutral-600',
};

export function statusColor(status: string | undefined | null): string {
  if (!status) return 'bg-slate-100 text-slate-600';
  const key = status.toUpperCase();
  return STATUS_STYLES[key] ?? 'bg-slate-100 text-slate-600';
}

export function dispensedSoFar(a: AllocationRead): number {
  return a.dispensed_liters;
}

export function deliveredLiters(t: TransactionRead): number {
  return t.actual_liters;
}
