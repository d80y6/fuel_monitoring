import { describe, expect, it } from 'vitest';
import { useSocketStatusStore } from './socket';

describe('useSocketStatusStore', () => {
  it('starts with both channels closed', () => {
    expect(useSocketStatusStore.getState().telemetry).toBe('closed');
    expect(useSocketStatusStore.getState().alarms).toBe('closed');
  });
  it('records channel state changes', () => {
    useSocketStatusStore.getState().setSocketState('telemetry', 'open');
    useSocketStatusStore.getState().setSocketState('alarms', 'open');
    expect(useSocketStatusStore.getState().telemetry).toBe('open');
    expect(useSocketStatusStore.getState().alarms).toBe('open');
  });
});
