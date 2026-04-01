/**
 * Dungeon Crawler of Doom — Web Frontend
 *
 * Phase 1: Terminal-in-browser (renders ANSI over WebSocket)
 * Phase 2: Three.js 3D renderer (future)
 */

import { DungeonConnection } from './connection';
import { TerminalRenderer } from './terminal';

// Config
const WS_PORT = 2324;
const WS_URL = `ws://${window.location.hostname || 'localhost'}:${WS_PORT}`;

// Init
const canvas = document.getElementById('game-canvas') as HTMLCanvasElement;
const logEl = document.getElementById('log')!;
const inputEl = document.getElementById('input') as HTMLInputElement;
const statusEl = document.getElementById('conn-status')!;
const hudEl = document.getElementById('hud')!;

const terminal = new TerminalRenderer(canvas, 120, 50);
const conn = new DungeonConnection(WS_URL);

let inputMode: 'char' | 'line' = 'char';

// Log a message to the UI log panel
function log(text: string, cssClass?: string) {
    const p = document.createElement('p');
    if (cssClass) p.className = cssClass;
    p.textContent = text;
    logEl.appendChild(p);
    logEl.scrollTop = logEl.scrollHeight;
    // Keep last 100 messages
    while (logEl.children.length > 100) {
        logEl.removeChild(logEl.firstChild!);
    }
}

// Handle messages from the server
conn.onMessage((msg) => {
    switch (msg.type) {
        case 'text':
            terminal.writeAnsi(msg.text || '');
            break;
        case 'cursor':
            // Handled by terminal internally via ANSI codes in text
            break;
        case 'clear_row':
            // Handled by terminal internally via ANSI codes
            break;
        case 'prompt':
            inputMode = msg.mode === 'line' ? 'line' : 'char';
            if (msg.text) {
                terminal.writeAnsi(msg.text);
            }
            inputEl.placeholder = msg.mode === 'line' ? 'Type and press Enter...' : 'Press a key...';
            inputEl.focus();
            break;
        default:
            log(`[server] ${JSON.stringify(msg)}`);
    }
});

// Keyboard input
document.addEventListener('keydown', (e) => {
    // Don't capture if typing in the input field in line mode
    if (inputMode === 'line' && document.activeElement === inputEl) {
        if (e.key === 'Enter') {
            conn.sendInput(inputEl.value);
            inputEl.value = '';
            inputMode = 'char';
        }
        return;
    }

    // Character mode: send single keypress
    const keyMap: Record<string, string> = {
        'ArrowUp': 'w', 'ArrowDown': 's', 'ArrowLeft': 'a', 'ArrowRight': 'd',
        'Enter': '\r',
    };

    const mapped = keyMap[e.key] || (e.key.length === 1 ? e.key : null);
    if (mapped) {
        e.preventDefault();
        conn.sendChar(mapped);
    }
});

// Input field for line mode
inputEl.addEventListener('focus', () => {
    if (inputMode === 'char') {
        inputEl.blur();
    }
});

// Connection status
setInterval(() => {
    statusEl.textContent = conn.connected ? 'Connected' : 'Disconnected';
    statusEl.className = conn.connected ? 'connected' : 'disconnected';
}, 1000);

// Connect
log('Connecting to dungeon server...');
conn.connect();
