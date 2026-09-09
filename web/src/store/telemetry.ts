import { create } from 'zustand';
import type { AlarmSummary, TelemetryPoint } from '../lib/apiTypes';

export interface LiveReading extends TelemetryPoint {
  tank_id: string;
  timestamp: string;
}

export interface TelemetryState {
  readings: Record<string, LiveReading>;
  alarms: AlarmSummary[];
  setReading: (r: LiveReading) => void;
  setAlarm: (a: AlarmSummary) => void;
}

export const useTelemetryStore = create<TelemetryState>()((set) => ({
  readings: {},
  alarms: [],
  setReading: (r) =>
    set((s) => ({ readings: { ...s.readings, [r.tank_id]: r } })),
  setAlarm: (a) => set((s) => ({ alarms: [a, ...s.alarms].slice(0, 50) })),
}));