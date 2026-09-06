// static/js/sse-client.js — Shared SSE connection manager
class SSEClient {
    constructor(url, options = {}) {
        this.url = url;
        this.reconnectDelay = options.reconnectDelay || 3000;
        this.onMessage = options.onMessage || (() => {});
        this.onConnect = options.onConnect || (() => {});
        this.onError = options.onError || (() => {});
        this._eventSource = null;
        this._reconnectTimer = null;
    }

    connect() {
        if (this._eventSource) this._eventSource.close();
        this._eventSource = new EventSource(this.url);

        this._eventSource.onopen = () => {
            console.log('[SSE] Connected to', this.url);
            this.onConnect();
        };

        this._eventSource.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                if (data.event === 'connected') return;
                if (data.event === 'error') {
                    console.warn('[SSE] Server error:', data.message);
                    return;
                }
                this.onMessage(data);
            } catch (e) {
                console.warn('[SSE] Parse error:', e);
            }
        };

        this._eventSource.onerror = () => {
            console.warn('[SSE] Connection lost, reconnecting in', this.reconnectDelay, 'ms');
            this._eventSource.close();
            this.onError();
            this._reconnectTimer = setTimeout(() => this.connect(), this.reconnectDelay);
        };
    }

    disconnect() {
        if (this._reconnectTimer) clearTimeout(this._reconnectTimer);
        if (this._eventSource) this._eventSource.close();
    }
}
