import { useQuery } from '@tanstack/react-query';
import { api } from '../api/client';
import { useTelemetryStore, type LiveReading } from '../store/telemetry';

export function useTelemetry(tankId: string) {
  const live = useTelemetryStore((s) => s.readings[tankId]);
  const q = useQuery({
    queryKey: ['recent', tankId],
    queryFn: () => api.recentReadings(tankId, 200),
    refetchInterval: 30_000,
  });
  const recent = (q.data ?? []) as LiveReading[];
  return { live, recent, loading: q.isLoading };
}