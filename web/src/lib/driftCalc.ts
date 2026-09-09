import type { TransactionRead, TotalizerPoint } from './apiTypes';
import { toEpochMs } from './chartOptions';
export { toEpochMs };

export interface CumulativeSample {
  ts: number;
  cumulativeLiters: number;
}

const TERMINAL_STATUSES = ['COMPLETED', 'PARTIAL', 'OVER_DISPENSE', 'DISCREPANCY'];

export function driveCumulativeFromTransactions(rows: TransactionRead[]): CumulativeSample[] {
  let acc = 0;
  return rows
    .filter((r) => TERMINAL_STATUSES.includes(r.status.toUpperCase()))
    .slice()
    .sort((a, b) => toEpochMs(a.created_at) - toEpochMs(b.created_at))
    .map((r) => {
      acc += r.requested_liters;
      return { ts: toEpochMs(r.created_at), cumulativeLiters: acc };
    });
}

export interface DriftSample {
  ts: number;
  drift: number;
  totalizer: number;
  authorized: number;
}

/**
 * Computes drift = totalizer cumulative − authorized cumulative at each
 * totalizer sample. For timestamps beyond the authorized range, falls back
 * to the index-parallel authorized sample (a known spec adaptation for
 * mismatched fixture epochs).
 */
export function computeDriftSeries(
  totalizer: TotalizerPoint[],
  authorized: CumulativeSample[]
): DriftSample[] {
  if (totalizer.length === 0 || authorized.length === 0) return [];
  const auth = [...authorized].sort((a, b) => a.ts - b.ts);
  const out: DriftSample[] = [];
  totalizer.forEach((t, i) => {
    const ts = toEpochMs(t.timestamp);
    const idx = auth.findIndex((s) => s.ts >= ts);
    const interp =
      idx === -1
        ? auth[Math.min(i, auth.length - 1)]
        : idx <= 0
          ? auth[0]
          : auth[idx - 1];
    const tc = t.cumulative_liters ?? 0;
    out.push({ ts, drift: tc - interp.cumulativeLiters, totalizer: tc, authorized: interp.cumulativeLiters });
  });
  return out;
}
