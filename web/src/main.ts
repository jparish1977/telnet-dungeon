/**
 * Dungeon Crawler of Doom — Web Frontend
 *
 * Phase 1: Terminal-in-browser (renders ANSI over WebSocket)
 * Phase 2: Three.js 3D renderer (future)
 */

import { DungeonConnection } from "./connection";
import { TerminalRenderer } from "./terminal";

// Config
const TERMINAL_COLS = 120;
const TERMINAL_ROWS = 50;
const MAX_LOG_MESSAGES = 100;
const STATUS_POLL_MS = 1000;

// WebSocket URL: data attribute > path-based detection > same-origin root
// When served under /dungeon/ (Apache alias), connect to /dungeon/ws (proxied).
// When served standalone on port 2325, connect to root.
const container = document.getElementById("app");
const wsProto = window.location.protocol === "https:" ? "wss:" : "ws:";
const path = window.location.pathname;
const dungeonPrefix = path.startsWith("/dungeon") ? "/dungeon/ws" : "";
const WS_URL =
  container?.dataset.wsUrl || `${wsProto}//${window.location.host}${dungeonPrefix}`;

// Init
const canvas = document.getElementById("game-canvas") as HTMLCanvasElement;
const logEl = document.getElementById("log")!;
const inputEl = document.getElementById("input") as HTMLInputElement;
const statusEl = document.getElementById("conn-status")!;
const _hudEl = document.getElementById("hud")!; // reserved for HUD overlay

const terminal = new TerminalRenderer(canvas, TERMINAL_COLS, TERMINAL_ROWS);
const conn = new DungeonConnection(WS_URL);

let inputMode: "char" | "line" = "char";

// Log a message to the UI log panel
function log(text: string, cssClass?: string) {
  const p = document.createElement("p");
  if (cssClass) p.className = cssClass;
  p.textContent = text;
  logEl.appendChild(p);
  logEl.scrollTop = logEl.scrollHeight;
  // Keep last 100 messages
  while (logEl.children.length > MAX_LOG_MESSAGES) {
    logEl.removeChild(logEl.firstChild!);
  }
}

// Handle messages from the server
conn.onMessage((msg) => {
  switch (msg.type) {
    case "text":
      terminal.writeAnsi(msg.text || "");
      break;
    case "cursor":
      // Handled by terminal internally via ANSI codes in text
      break;
    case "clear_row":
      // Handled by terminal internally via ANSI codes
      break;
    case "prompt":
      inputMode = msg.mode === "line" ? "line" : "char";
      if (msg.text) {
        terminal.writeAnsi(msg.text);
      }
      inputEl.placeholder =
        msg.mode === "line" ? "Type and press Enter..." : "Press a key...";
      inputEl.focus();
      break;
    default:
      log(`[server] ${JSON.stringify(msg)}`);
  }
});

// Keyboard input with repeat suppression
let lastKeySent = 0;
const KEY_COOLDOWN = 100; // ms between repeated keys

document.addEventListener("keydown", (e) => {
  // Don't capture if typing in the input field in line mode
  if (inputMode === "line" && document.activeElement === inputEl) {
    if (e.key === "Enter") {
      conn.sendInput(inputEl.value);
      inputEl.value = "";
      inputMode = "char";
    }
    return;
  }

  // Block key repeat - only send on first press or after cooldown
  const now = Date.now();
  if (e.repeat && now - lastKeySent < KEY_COOLDOWN) {
    e.preventDefault();
    return;
  }

  // Character mode: send single keypress
  const keyMap: Record<string, string> = {
    ArrowUp: "w",
    ArrowDown: "s",
    ArrowLeft: "a",
    ArrowRight: "d",
    Enter: "\r",
  };

  const mapped = keyMap[e.key] || (e.key.length === 1 ? e.key : null);
  if (mapped) {
    e.preventDefault();
    lastKeySent = now;
    conn.sendChar(mapped);
  }
});

// Input field for line mode
inputEl.addEventListener("focus", () => {
  if (inputMode === "char") {
    inputEl.blur();
  }
});

// Connection status
setInterval((): void => {
  statusEl.textContent = conn.connected ? "Connected" : "Disconnected";
  statusEl.className = conn.connected ? "connected" : "disconnected";
}, STATUS_POLL_MS);

// Connect
log("Connecting to dungeon server...");
conn.connect();
