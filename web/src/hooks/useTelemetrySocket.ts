import { useEffect } from 'react';
import { useAuthStore } from '../store/auth';
import { useTelemetryStore } from '../store/telemetry';
import type { LiveReading } from '../store/telemetry';
import type { AlarmSummary } from '../lib/apiTypes';
import { TelemetrySocket } from '../api/ws';

export function useTelemetrySocket() {
  const token = useAuthStore((s) => s.token);

  useEffect(() => {
    if (!token) return;
    const wsProto = location.origin.replace(/^http/, 'ws');
    const tel = new TelemetrySocket(`${wsProto}/ws/telemetry?channels=telemetry&token=${encodeURIComponent(token)}`);
    const alm = new TelemetrySocket(`${wsProto}/ws/alarms?token=${encodeURIComponent(token)}`);
    const offR = tel.on('reading', (m) =>
      useTelemetryStore.getState().setReading(m as LiveReading)
    );
    const offA = alm.on('alarm', (m) =>
      useTelemetryStore.getState().setAlarm(m as AlarmSummary)
    );
    tel.connect();
    alm.connect();
    return () => {
      offR();
      offA();
      tel.disconnect();
      alm.disconnect();
    };
  }, [token]);
}