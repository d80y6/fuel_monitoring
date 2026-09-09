export type WsMessage = unknown;

type Listener = (msg: any) => void;

const READ_RECONNECT_MS = 1_000;
const RECONNECT_MAX_MS = 30_000;

export class TelemetrySocket {
  private ws: WebSocket | null = null;
  private timer: ReturnType<typeof setTimeout> | null = null;
  private retries = 0;
  private closedByUser = false;
  private listeners = new Map<string, Set<Listener>>();

  constructor(
    private url: string,
    private opts: { createSocket?: (u: string) => WebSocket } = {}
  ) {}

  connect(): void {
    this.closedByUser = false;
    this.open();
  }

  private open(): void {
    const make = this.opts.createSocket ?? ((u: string) => new WebSocket(u));
    this.ws = make(this.url);
    this.ws.onopen = () => {
      this.retries = 0;
      this.emit('status', { state: 'open' });
    };
    this.ws.onmessage = (ev: MessageEvent) => {
      let data: any = null;
      try {
        data = JSON.parse(ev.data as string);
      } catch {
        return;
      }
      if (data && typeof data.type === 'string') this.emit('alarm', data);
      else this.emit('reading', data);
    };
    this.ws.onerror = () => {};
    this.ws.onclose = () => {
      this.emit('status', { state: 'closed' });
      if (!this.closedByUser) this.scheduleReconnect();
    };
  }

  private scheduleReconnect(): void {
    const delay = Math.min(RECONNECT_MAX_MS, READ_RECONNECT_MS * 2 ** this.retries);
    this.retries += 1;
    this.timer = setTimeout(() => this.open(), delay);
  }

  disconnect(): void {
    this.closedByUser = true;
    if (this.timer) {
      clearTimeout(this.timer);
      this.timer = null;
    }
    if (this.ws) {
      this.ws.onclose = null;
      this.ws.close();
      this.ws = null;
    }
  }

  on(type: 'reading' | 'alarm' | 'status', cb: Listener): () => void {
    if (!this.listeners.has(type)) this.listeners.set(type, new Set());
    this.listeners.get(type)!.add(cb);
    return () => this.listeners.get(type)?.delete(cb);
  }

  private emit(type: string, msg: any): void {
    this.listeners.get(type)?.forEach((cb) => cb(msg));
  }
}