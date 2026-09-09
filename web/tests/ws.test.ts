import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { TelemetrySocket } from '../src/api/ws';

class FakeWS {
  static instances: FakeWS[] = [];
  url = '';
  onopen: (() => void) | null = null;
  onmessage: ((ev: { data: string }) => void) | null = null;
  onerror: (() => void) | null = null;
  onclose: (() => void) | null = null;
  closed = false;

  constructor(url: string) {
    this.url = url;
    FakeWS.instances.push(this);
  }
  close() {
    this.closed = true;
  }
  triggerOpen() {
    this.onopen?.();
  }
  triggerMessage(data: unknown) {
    this.onmessage?.({ data: JSON.stringify(data) });
  }
  triggerClose() {
    this.onclose?.();
  }
}

const url = 'ws://x/ws/telemetry?token=tok';
const createSocket = (u: string) => new FakeWS(u) as unknown as WebSocket;

describe('TelemetrySocket', () => {
  beforeEach(() => {
    FakeWS.instances = [];
    vi.useFakeTimers();
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it('connects to the given URL and emits parsed readings', () => {
    const sock = new TelemetrySocket(url, { createSocket });
    const reading = vi.fn();
    sock.on('reading', reading);
    sock.connect();
    const ws = FakeWS.instances[0];
    expect(ws.url).toBe(url);
    ws.triggerOpen();
    ws.triggerMessage({ tank_id: 't1', level: 1.2, volume: 400, gov_volume: 401 });
    expect(reading).toHaveBeenCalledTimes(1);
    expect(reading.mock.calls[0][0].tank_id).toBe('t1');
    expect(reading.mock.calls[0][0].gov_volume).toBe(401);
    sock.disconnect();
  });

  it('treats non-JSON or alarm frames without crashing', () => {
    const sock = new TelemetrySocket(url, { createSocket });
    const alarm = vi.fn();
    sock.on('alarm', alarm);
    sock.connect();
    const ws = FakeWS.instances[0];
    ws.triggerOpen();
    ws.triggerMessage({ type: 'LEVEL', tank_id: 't1', acknowledged: false });
    expect(alarm).toHaveBeenCalledTimes(1);
    expect(sock).toBeDefined();
    sock.disconnect();
  });

  it('reconnects with exponential backoff after close, capping at 30s', () => {
    const sock = new TelemetrySocket(url, { createSocket });
    sock.connect();
    const first = FakeWS.instances[0];
    first.triggerClose();
    vi.advanceTimersByTime(999);
    expect(FakeWS.instances.length).toBe(1); // not yet
    vi.advanceTimersByTime(1);
    expect(FakeWS.instances.length).toBe(2); // reconnected after 1s
    const second = FakeWS.instances[1];
    second.triggerClose();
    vi.advanceTimersByTime(1_999);
    expect(FakeWS.instances.length).toBe(2);
    vi.advanceTimersByTime(1);
    expect(FakeWS.instances.length).toBe(3); // 2s backoff
    sock.disconnect();
  });

  it('disconnect() stops reconnects and closes the socket', () => {
    const sock = new TelemetrySocket(url, { createSocket });
    sock.connect();
    const ws = FakeWS.instances[0];
    ws.triggerClose();
    sock.disconnect();
    vi.advanceTimersByTime(5_000);
    expect(FakeWS.instances.length).toBe(1);
    expect(ws.closed).toBe(true);
  });

  it('emits status events on open and close', () => {
    const sock = new TelemetrySocket(url, { createSocket });
    const status = vi.fn();
    sock.on('status', status);
    sock.connect();
    FakeWS.instances[0].triggerOpen();
    expect(status).toHaveBeenLastCalledWith({ state: 'open' });
    FakeWS.instances[0].triggerClose();
    expect(status).toHaveBeenLastCalledWith({ state: 'closed' });
    sock.disconnect();
  });
});