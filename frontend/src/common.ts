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

/** Show or hide an element with the `hidden` attribute. app.css makes
 *  `[hidden]` win over any display rule. Use this instead of setting
 *  `style.display` (UX.md §1, enforced by test_frontend_contracts). */
export function setVisible(node: HTMLElement, visible: boolean): void {
  node.hidden = !visible;
}

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

// Section links list only sections that are currently shown (UX.md §16):
// hide a link whenever its target card is hidden (display: none), and show
// it again when the card appears. Debounced to one pass per frame.
let sectionSyncQueued = false;
function syncSectionLinks(): void {
  sectionSyncQueued = false;
  for (const link of document.querySelectorAll<HTMLAnchorElement>(".section-links a[href^='#']")) {
    const target = document.querySelector<HTMLElement>(link.hash);
    const visible = !target || target.getClientRects().length > 0;
    if (link.hidden === visible) setVisible(link, visible);
  }
}
function queueSectionSync(): void {
  if (sectionSyncQueued) return;
  sectionSyncQueued = true;
  requestAnimationFrame(syncSectionLinks);
}
if (document.querySelector(".section-links")) {
  new MutationObserver((records) => {
    if (records.some((r) => !(r.target as Element).closest?.(".section-links"))) queueSectionSync();
  }).observe(document.body, { subtree: true, attributes: true, attributeFilter: ["style", "hidden"] });
  queueSectionSync();
}

// Section navigation is shared by the long role-based pages. If a jump target
// is a collapsed disclosure (for example moderator Set up), open it before the
// browser scrolls to the anchor.
document.addEventListener("click", (event) => {
  const link = (event.target as Element | null)?.closest<HTMLAnchorElement>(".section-links a[href^='#']");
  if (!link) return;
  const target = document.querySelector<HTMLElement>(link.hash);
  if (target instanceof HTMLDetailsElement) target.open = true;
});

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

type UsableRole = "landing" | "participant" | "moderator" | "projector" | "quizzes";
let usableMarked = false;

/** Mark and asynchronously report when this page becomes useful to a person.
 * The payload is deliberately identifier-free: no URL, code, cookie, or IP. */
export function markUsable(role: UsableRole): void {
  if (usableMarked) return;
  usableMarked = true;
  performance.mark("prashna-usable");
  const usableMs = performance.now();
  const send = () => {
    try {
      const nav = performance.getEntriesByType("navigation")[0] as PerformanceNavigationTiming | undefined;
      const resources = performance.getEntriesByType("resource") as PerformanceResourceTiming[];
      const paints = Object.fromEntries(
        performance.getEntriesByType("paint").map((entry) => [entry.name, entry.startTime]),
      );
      const all = nav ? [nav, ...resources] : resources;
      const appTimes = all.flatMap((entry) =>
        entry.serverTiming.filter((timing) => timing.name === "app").map((timing) => timing.duration),
      );
      const payload = {
        role,
        usable_ms: usableMs,
        dcl_ms: nav?.domContentLoadedEventEnd || null,
        fcp_ms: paints["first-contentful-paint"] ?? null,
        app_server_ms: appTimes.length ? Math.max(...appTimes) : null,
        protocol: nav?.nextHopProtocol || resources.find((entry) => entry.nextHopProtocol)?.nextHopProtocol || "unknown",
        navigation_type: nav?.type ?? "navigate",
      };
      navigator.sendBeacon("/api/diagnostics/performance",
        new Blob([JSON.stringify(payload)], { type: "application/json" }),
      );
    } catch { /* Performance reporting must never affect the page. */ }
  };
  if ("requestIdleCallback" in window) window.requestIdleCallback(send, { timeout: 2000 });
  else setTimeout(send, 0);
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
  let connectedOnce = false;
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
      // The page performs its own initial load. Refetch only after a real
      // reconnect so opening the socket does not duplicate every first-load
      // API request.
      if (connectedOnce) {
        try { onMessage({ type: "reconnect" }); } catch { /* page may be tearing down */ }
      }
      connectedOnce = true;
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
  const overlay = el("div", { class: "qr-lightbox", hidden: true },
    inner, el("div", { class: "qr-lightbox-hint" }, "Click anywhere or press Esc to close"));
  const close = () => { setVisible(overlay, false); inner.innerHTML = ""; };
  overlay.addEventListener("click", close);
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && !overlay.hidden) close();
  });
  document.body.appendChild(overlay);
  _qrLightbox = { overlay, inner };
  return _qrLightbox;
}

function _expandQR(svg: SVGElement): void {
  const { overlay, inner } = _qrLightboxEl();
  inner.innerHTML = "";
  const clone = svg.cloneNode(true) as SVGElement;
  clone.classList.add("qr-svg", "qr-svg-full");
  inner.appendChild(clone);
  setVisible(overlay, true);
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
    svg.classList.add("qr-svg");
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

/** Close open `details.menu` disclosures on outside click and Esc (UX.md
 *  §4). Native `<details>` only toggles on its own summary. Bind once per
 *  page; an Esc that closed a menu is marked `defaultPrevented` so page-level
 *  Esc handlers can leave their drill-downs open. */
export function bindMenuDismiss(): void {
  document.addEventListener("click", (e) => {
    for (const d of document.querySelectorAll<HTMLDetailsElement>("details.menu[open]")) {
      if (!d.contains(e.target as Node)) d.open = false;
    }
  });
  document.addEventListener("keydown", (e) => {
    if (e.key !== "Escape") return;
    for (const d of document.querySelectorAll<HTMLDetailsElement>("details.menu[open]")) {
      d.open = false;
      e.preventDefault();
    }
  });
}
