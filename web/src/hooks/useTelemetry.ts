import { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { api } from '../api/client';
import { useTelemetryStore } from '../store/telemetry';
import type { LiveReading } from '../store/telemetry';

export function useTelemetry(tankId: string) {
  const live = useTelemetryStore((s) => s.readings[tankId]);
  const q = useQuery({
    queryKey: ['recent', tankId],
    queryFn: () => api.recentReadings(tankId, 200),
    refetchInterval: 30_000,
  });
  const recent: LiveReading[] = useMemo(
    () => (q.data ?? []).map((p) => ({ ...p, tank_id: tankId })),
    [q.data, tankId]
  );
  const latest = live ?? recent[recent.length - 1];
  return { live, recent, latest, loading: q.isLoading };
}