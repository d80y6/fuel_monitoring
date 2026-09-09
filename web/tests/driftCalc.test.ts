import { describe, expect, it } from 'vitest';
import {
  computeDriftSeries,
  driveCumulativeFromTransactions,
  toEpochMs,
} from '../src/lib/driftCalc';
import type { TransactionRead, TotalizerPoint } from '../src/lib/apiTypes';

const txs = (list: Array<{ ts: string; lit: number }>): TransactionRead[] =>
  list.map((t, i) => ({
    id: i + 1,
    station_id: 's1',
    dispenser_id: 'd1',
    employee_id: 'e1',
    requested_liters: t.lit,
    actual_liters: t.lit,
    secret_totalizer_before: 0,
    secret_totalizer_after: 0,
    status: 'COMPLETED',
    created_at: t.ts,
  }));

describe('driveCumulativeFromTransactions', () => {
  it('builds a strictly increasing cumulative requested-liters series', () => {
    const rows = txs([
      { ts: '2026-01-01T00:00:00Z', lit: 10 },
      { ts: '2026-01-01T01:00:00Z', lit: 5 },
      { ts: '2026-01-01T02:00:00Z', lit: 12 },
    ]);
    const cum = driveCumulativeFromTransactions(rows);
    expect(cum).toHaveLength(3);
    expect(cum[1].cumulativeLiters).toBeCloseTo(15, 6);
    expect(cum[2].cumulativeLiters).toBeCloseTo(27, 6);
  });
});

describe('computeDriftSeries', () => {
  it('returns [] for empty inputs', () => {
    expect(computeDriftSeries([], [])).toEqual([]);
  });

  it('subtracts authorized from totalizer cumulative at aligned timestamps', () => {
    const totalizer: TotalizerPoint[] = [
      { timestamp: '2026-01-01T00:00:00Z', station_id: 's1', dispenser_id: 'd1', totalizer_value: 1000, cumulative_liters: 1000, source: 'odometer' },
      { timestamp: '2026-01-01T01:00:00Z', station_id: 's1', dispenser_id: 'd1', totalizer_value: 1010, cumulative_liters: 1010, source: 'odometer' },
    ];
    const authorized = [
      { ts: 0, cumulativeLiters: 1005 },
      { ts: 1, cumulativeLiters: 1008 },
    ];
    const drift = computeDriftSeries(totalizer, authorized);
    expect(drift).toHaveLength(2);
    expect(drift[0].drift).toBeCloseTo(-5, 6);
    expect(drift[1].drift).toBeCloseTo(2, 6);
  });
});

describe('toEpochMs (re-exported)', () => {
  it('parses timestamps', () => {
    expect(toEpochMs('2026-01-02T03:04:05Z')).toBe(Date.parse('2026-01-02T03:04:05Z'));
  });
});
