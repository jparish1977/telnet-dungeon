/**
 * WebSocket connection manager for the dungeon server.
 */

export type MessageHandler = (msg: ServerMessage) => void;

export interface ServerMessage {
    type: string;
    text?: string;
    row?: number;
    col?: number;
    mode?: string;
    prefill?: string;
    [key: string]: unknown;
}

export class DungeonConnection {
    private ws: WebSocket | null = null;
    private handlers: MessageHandler[] = [];
    private reconnectTimer: number | null = null;
    public connected = false;

    constructor(private url: string) {}

    onMessage(handler: MessageHandler) {
        this.handlers.push(handler);
    }

    connect() {
        if (this.ws) {
            this.ws.close();
        }

        this.ws = new WebSocket(this.url);

        this.ws.onopen = () => {
            this.connected = true;
            console.log('[WS] Connected to dungeon server');
            // Send terminal size
            this.send({ type: 'resize', width: 120, height: 40 });
        };

        this.ws.onmessage = (event) => {
            try {
                const msg = JSON.parse(event.data) as ServerMessage;
                for (const handler of this.handlers) {
                    handler(msg);
                }
            } catch {
                console.warn('[WS] Non-JSON message:', event.data);
            }
        };

        this.ws.onclose = () => {
            this.connected = false;
            console.log('[WS] Disconnected');
            // Auto-reconnect after 3s
            this.reconnectTimer = window.setTimeout(() => this.connect(), 3000);
        };

        this.ws.onerror = (err) => {
            console.error('[WS] Error:', err);
        };
    }

    send(data: Record<string, unknown>) {
        if (this.ws?.readyState === WebSocket.OPEN) {
            this.ws.send(JSON.stringify(data));
        }
    }

    sendChar(char: string) {
        this.send({ type: 'char', char });
    }

    sendInput(text: string) {
        this.send({ type: 'input', text });
    }

    disconnect() {
        if (this.reconnectTimer) {
            clearTimeout(this.reconnectTimer);
        }
        this.ws?.close();
    }
}
