import { useTelemetryStore } from '../store/telemetry';

export function useRealtimeAlarms() {
  return useTelemetryStore((s) => s.alarms);
}