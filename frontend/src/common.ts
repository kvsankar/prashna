// Shared frontend helpers (TypeScript). Imported by every page entry.
import "./app.css";

// Vendored QR library (window.qrcode), lazy-loaded from /static/vendor.
interface Qr {
  addData(data: string): void;
  make(): void;
  createSvgTag(opts: { cellSize: number; margin: number; scalable: boolean }): string;
}
type QrFactory = (typeNumber: number, errorCorrection: string) => Qr;
interface LiveSocketTestHook {
  closeActive(): void;
  activeCount(): number;
  readyState(): number;
}
declare global {
  interface Window {
    qrcode?: QrFactory;
    __prashnaLiveSocketTest?: LiveSocketTestHook;
  }
}

/** Query one element, typed. Asserts presence (callers rely on it). */
export const $ = <T extends HTMLElement = HTMLElement>(sel: string, root: ParentNode = document): T =>
  root.querySelector<T>(sel) as T;

/** Query all matching elements as an array. */
export const $$ = <T extends HTMLElement = HTMLElement>(sel: string, root: ParentNode = document): T[] =>
  Array.from(root.querySelectorAll<T>(sel));

type Child = Node | string | number | null | false | undefined;
type Attrs = Record<string, unknown>;

/** Create an element. `class`/`html` are special; `on*` attach listeners;
 *  false/null attrs are skipped; `true` becomes a bare attribute. */
export function el(tag: string, attrs: Attrs = {}, ...children: (Child | Child[])[]): HTMLElement {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") node.className = String(v);
    else if (k === "html") node.innerHTML = String(v);
    else if (k.startsWith("on") && typeof v === "function") node.addEventListener(k.slice(2), v as EventListener);
    else if (v === false || v == null) continue;
    else node.setAttribute(k, v === true ? "" : String(v));
  }
  for (const c of children.flat()) {
    if (c == null || c === false) continue;
    node.appendChild(c instanceof Node ? c : document.createTextNode(String(c)));
  }
  return node;
}

export function escapeHtml(s: unknown): string {
  const map: Record<string, string> = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" };
  return String(s ?? "").replace(/[&<>"']/g, (c) => map[c]);
}

export function pathCode(): string {
  return (location.pathname.split("/").pop() ?? "").toUpperCase();
}

export interface ApiOpts {
  method?: string;
  headers?: Record<string, string>;
  body?: unknown;
}

export async function api<T = unknown>(path: string, opts: ApiOpts = {}): Promise<T> {
  const headers: Record<string, string> = { ...(opts.headers ?? {}) };
  let body = opts.body as BodyInit | undefined;
  if (opts.body != null && !(opts.body instanceof FormData)) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(opts.body);
  }
  const r = await fetch(path, { credentials: "same-origin", ...opts, headers, body });
  if (!r.ok) {
    let msg = r.statusText;
    try { const j = await r.json(); msg = j.detail || msg; } catch { /* non-JSON error body */ }
    if (r.status === 401 && location.pathname !== "/") location.href = "/";
    throw new Error(msg);
  }
  if (r.status === 204) return null as T;
  const ct = r.headers.get("content-type") ?? "";
  return (ct.includes("application/json") ? r.json() : r.text()) as Promise<T>;
}

export function modKey(): string | null { return localStorage.getItem("mod_key:" + pathCode()); }
export function setModKey(k: string): void { localStorage.setItem("mod_key:" + pathCode(), k); }
export function modHeaders(): Record<string, string> {
  const k = modKey();
  return k ? { "X-Mod-Key": k } : {};
}

export interface LiveMessage { type: string }
export interface LiveSocket { close(): void }

export function openLiveSocket(code: string, onMessage: (msg: LiveMessage) => void): LiveSocket {
  const proto = location.protocol === "https:" ? "wss:" : "ws:";
  const url = `${proto}//${location.host}/ws/sessions/${code}`;
  let ws: WebSocket;
  let retry = 0;
  let alive = true;
  if (import.meta.env.MODE === "test") {
    let exposeTestHook = false;
    try {
      const hookFlag = localStorage.getItem("prashna:socket-close-hook");
      exposeTestHook = hookFlag === "1";
    } catch {
      exposeTestHook = false;
    }
    if (exposeTestHook) {
      window.__prashnaLiveSocketTest = {
        closeActive() { ws?.close(); },
        activeCount() {
          return ws && ws.readyState < WebSocket.CLOSING ? 1 : 0;
        },
        readyState() {
          return ws?.readyState ?? -1;
        },
      };
    }
  }
  function connect(): void {
    ws = new WebSocket(url);
    ws.onopen = () => {
      retry = 0;
      // Refetch on EVERY (re)connect, including the first, so a broadcast
      // fired between page load and socket-ready isn't missed.
      try { onMessage({ type: "reconnect" }); } catch { /* page may be tearing down */ }
    };
    ws.onmessage = (ev) => {
      try { onMessage(JSON.parse(ev.data)); } catch { /* ignore malformed frame */ }
    };
    ws.onclose = () => {
      if (!alive) return;
      retry = Math.min(retry + 1, 6);
      // Exponential backoff with ±50% jitter to avoid a synchronized
      // reconnect herd after a mass disconnect.
      const base = 500 * 2 ** retry;
      setTimeout(connect, base * (0.5 + Math.random()));
    };
    ws.onerror = () => ws.close();
  }
  connect();
  return { close() { alive = false; ws?.close(); } };
}

// --- QR rendering + shared fullscreen lightbox ---
let _qrcodePromise: Promise<QrFactory> | null = null;
function _loadQR(): Promise<QrFactory> {
  if (_qrcodePromise) return _qrcodePromise;
  _qrcodePromise = new Promise((resolve, reject) => {
    if (window.qrcode) return resolve(window.qrcode);
    const s = document.createElement("script");
    s.src = "/static/vendor/qrcode.js";
    s.onload = () => window.qrcode ? resolve(window.qrcode) : reject(new Error("QR library missing"));
    s.onerror = () => reject(new Error("Could not load QR library"));
    document.head.appendChild(s);
  });
  return _qrcodePromise;
}

let _qrLightbox: { overlay: HTMLElement; inner: HTMLElement } | null = null;
function _qrLightboxEl() {
  if (_qrLightbox) return _qrLightbox;
  const inner = el("div", { class: "qr-lightbox-inner" });
  const overlay = el("div", { class: "qr-lightbox", style: "display:none;" },
    inner, el("div", { class: "qr-lightbox-hint" }, "Click anywhere or press Esc to close"));
  const close = () => { overlay.style.display = "none"; inner.innerHTML = ""; };
  overlay.addEventListener("click", close);
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && overlay.style.display !== "none") close();
  });
  document.body.appendChild(overlay);
  _qrLightbox = { overlay, inner };
  return _qrLightbox;
}

function _expandQR(svg: SVGElement): void {
  const { overlay, inner } = _qrLightboxEl();
  inner.innerHTML = "";
  const clone = svg.cloneNode(true) as SVGElement;
  clone.style.cssText = "width:100%;height:100%;display:block;background:white;border-radius:8px;";
  inner.appendChild(clone);
  overlay.style.display = "";
}

export async function renderQR(
  target: HTMLElement | null,
  text: string,
  { cellSize = 4, margin = 2 }: { cellSize?: number; margin?: number } = {},
): Promise<void> {
  if (!target) return;
  const qrcode = await _loadQR();
  const qr = qrcode(0, "M");
  qr.addData(text);
  qr.make();
  target.innerHTML = qr.createSvgTag({ cellSize, margin, scalable: true });
  const svg = target.querySelector("svg");
  if (svg) {
    svg.style.width = "100%";
    svg.style.height = "auto";
    svg.style.display = "block";
    svg.style.background = "white";
    svg.style.borderRadius = "8px";
    target.classList.add("qr-expandable");
    target.setAttribute("role", "button");
    target.setAttribute("tabindex", "0");
    target.setAttribute("aria-label", "Enlarge QR code for scanning");
    target.title = "Click to enlarge";
    target.onclick = () => _expandQR(svg);
    target.onkeydown = (e) => {
      if (e.key === "Enter" || e.key === " ") { e.preventDefault(); _expandQR(svg); }
    };
  }
}

export function toast(msg: string, { error = false, duration = 2800 }: { error?: boolean; duration?: number } = {}): void {
  const t = el("div", {
    class: "toast" + (error ? " toast-error" : ""),
    role: "status",
    "aria-live": error ? "assertive" : "polite",
  }, msg);
  document.body.appendChild(t);
  setTimeout(() => t.remove(), duration);
}

export function errorToast(msg: string): void { toast(msg, { error: true, duration: 4000 }); }

// Friendly labels for lifecycle enums. Badge CSS classes keep the raw status.
export const STATUS_LABELS: Record<string, string> = {
  planning: "Not started",
  live: "Live",
  ended: "Ended",
  queued: "Queued",
  closed: "Closed",
};
export const statusLabel = (s: string): string => STATUS_LABELS[s] ?? s;

/** Guard a button against double-submit: disables it while the async handler
 *  runs and ignores repeat clicks. Use for non-idempotent mutations. */
export function guardClick<B extends HTMLButtonElement>(button: B, handler: (ev: MouseEvent) => unknown): B {
  let busy = false;
  button.addEventListener("click", async (ev) => {
    if (busy) return;
    busy = true;
    button.disabled = true;
    try { await handler(ev); }
    finally { busy = false; button.disabled = false; }
  });
  return button;
}
