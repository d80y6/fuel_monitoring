import type { TankTransaction, AlarmSummary, Station } from './apiTypes';

export function last24hLiters(transactions: TankTransaction[]): number {
  const cutoff = Date.now() - 24 * 60 * 60 * 1000;
  return transactions
    .filter((t) => {
      const ts = new Date(t.created_at).getTime();
      return ts >= cutoff && (t.status === 'COMPLETED' || t.status === 'SETTLED');
    })
    .reduce((sum, t) => sum + (t.actual_liters || 0), 0);
}

export function onlineStations(stations: Station[]): number {
  return stations.filter((s) => s.connection_status === 'online').length;
}

export function isOpenAlarm(alarm: AlarmSummary): boolean {
  return !alarm.acknowledged;
}
