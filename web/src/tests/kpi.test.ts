import { describe, expect, it, vi, afterEach } from 'vitest';
import { last24hLiters, onlineStations, isOpenAlarm } from '../lib/kpi';

describe('last24hLiters', () => {
  afterEach(() => vi.restoreAllMocks());
  it('sums completed transactions in last 24h', () => {
    vi.spyOn(Date, 'now').mockReturnValue(new Date('2026-09-09T12:00:00Z').getTime());
    const txns = [
      { actual_liters: 100, created_at: '2026-09-09T11:00:00Z', status: 'COMPLETED' },
      { actual_liters: 50, created_at: '2026-09-08T11:00:00Z', status: 'COMPLETED' }, // >24h ago
      { actual_liters: 30, created_at: '2026-09-09T10:00:00Z', status: 'SETTLED' },
    ] as any[];
    expect(last24hLiters(txns)).toBe(130);
  });
});

describe('onlineStations', () => {
  it('counts online stations', () => {
    expect(onlineStations([
      { connection_status: 'online' },
      { connection_status: 'offline' },
      { connection_status: 'online' },
    ] as any[])).toBe(2);
  });
});

describe('isOpenAlarm', () => {
  it('returns true for unacknowledged alarms', () => {
    expect(isOpenAlarm({ acknowledged: false } as any)).toBe(true);
  });
  it('returns false for acknowledged alarms', () => {
    expect(isOpenAlarm({ acknowledged: true } as any)).toBe(false);
  });
});
