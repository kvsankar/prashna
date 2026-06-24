// Shared helpers
export const $ = (sel, root = document) => root.querySelector(sel);
export const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

export function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") node.className = v;
    else if (k === "html") node.innerHTML = v;
    else if (k.startsWith("on") && typeof v === "function") node.addEventListener(k.slice(2), v);
    else if (v === false || v == null) continue;
    else node.setAttribute(k, v === true ? "" : v);
  }
  for (const c of children.flat()) {
    if (c == null || c === false) continue;
    node.appendChild(c.nodeType ? c : document.createTextNode(c));
  }
  return node;
}

export function escapeHtml(s) {
  return String(s ?? "").replace(/[&<>"']/g, c => (
    { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]
  ));
}

export function pathCode() {
  return location.pathname.split("/").pop().toUpperCase();
}

export async function api(path, opts = {}) {
  const headers = { ...(opts.headers || {}) };
  if (opts.body && !(opts.body instanceof FormData)) {
    headers["Content-Type"] = "application/json";
    opts.body = JSON.stringify(opts.body);
  }
  const r = await fetch(path, { credentials: "same-origin", ...opts, headers });
  if (!r.ok) {
    let msg = r.statusText;
    try { const j = await r.json(); msg = j.detail || msg; } catch {}
    if (r.status === 401 && location.pathname !== "/") {
      location.href = "/";
    }
    throw new Error(msg);
  }
  if (r.status === 204) return null;
  const ct = r.headers.get("content-type") || "";
  return ct.includes("application/json") ? r.json() : r.text();
}

export function modKey() { return localStorage.getItem("mod_key:" + pathCode()); }
export function setModKey(k) { localStorage.setItem("mod_key:" + pathCode(), k); }

export function modHeaders() {
  const k = modKey();
  return k ? { "X-Mod-Key": k } : {};
}

export function openLiveSocket(code, onMessage) {
  const proto = location.protocol === "https:" ? "wss:" : "ws:";
  const url = `${proto}//${location.host}/ws/sessions/${code}`;
  let ws, retry = 0, alive = true;
  let everConnected = false;
  function connect() {
    ws = new WebSocket(url);
    ws.onopen = () => {
      retry = 0;
      // After a reconnect, force a refetch so the page recovers any state
      // changes that broadcasted while the socket was down. The initial
      // connect doesn't need this — the page just loaded its own data.
      if (everConnected) {
        try { onMessage({ type: "reconnect" }); } catch {}
      }
      everConnected = true;
    };
    ws.onmessage = ev => {
      try { onMessage(JSON.parse(ev.data)); } catch {}
    };
    ws.onclose = () => {
      if (!alive) return;
      retry = Math.min(retry + 1, 6);
      setTimeout(connect, 500 * 2 ** retry);
    };
    ws.onerror = () => ws.close();
  }
  connect();
  return { close() { alive = false; ws && ws.close(); } };
}

// Render a QR code into `target` (an element). Replaces its contents.
// Lazy-loads /static/vendor/qrcode.js the first time it's called.
let _qrcodePromise = null;
function _loadQR() {
  if (_qrcodePromise) return _qrcodePromise;
  _qrcodePromise = new Promise((resolve, reject) => {
    if (window.qrcode) return resolve(window.qrcode);
    const s = document.createElement("script");
    s.src = "/static/vendor/qrcode.js";
    s.onload = () => resolve(window.qrcode);
    s.onerror = () => reject(new Error("Could not load QR library"));
    document.head.appendChild(s);
  });
  return _qrcodePromise;
}

// Shared QR lightbox — click/Enter any rendered QR to blow it up fullscreen
// for easy scanning (like a picture lightbox). Created lazily, reused across
// all QRs on the page.
let _qrLightbox = null;
function _qrLightboxEl() {
  if (_qrLightbox) return _qrLightbox;
  const inner = el("div", { class: "qr-lightbox-inner" });
  const overlay = el("div", { class: "qr-lightbox", style: "display:none;" },
    inner, el("div", { class: "qr-lightbox-hint" }, "Click anywhere or press Esc to close"));
  const close = () => { overlay.style.display = "none"; inner.innerHTML = ""; };
  overlay.addEventListener("click", close);
  document.addEventListener("keydown", e => {
    if (e.key === "Escape" && overlay.style.display !== "none") close();
  });
  document.body.appendChild(overlay);
  _qrLightbox = { overlay, inner };
  return _qrLightbox;
}

function _expandQR(svg) {
  const { overlay, inner } = _qrLightboxEl();
  inner.innerHTML = "";
  const clone = svg.cloneNode(true);
  // Fill the square container; the thumbnail had height:auto.
  clone.style.cssText = "width:100%;height:100%;display:block;background:white;border-radius:8px;";
  inner.appendChild(clone);
  overlay.style.display = "";
}

export async function renderQR(target, text, { cellSize = 4, margin = 2 } = {}) {
  if (!target) return;
  const qrcode = await _loadQR();
  // Type 0 = auto-size; "M" error correction (~15%).
  const qr = qrcode(0, "M");
  qr.addData(text);
  qr.make();
  target.innerHTML = qr.createSvgTag({ cellSize, margin, scalable: true });
  // Style the embedded SVG so it adapts to the container.
  const svg = target.querySelector("svg");
  if (svg) {
    svg.style.width = "100%";
    svg.style.height = "auto";
    svg.style.display = "block";
    svg.style.background = "white";
    svg.style.borderRadius = "8px";
    // Make every QR expandable to fullscreen. Assign (not addEventListener)
    // so re-renders of the same target don't stack handlers.
    target.classList.add("qr-expandable");
    target.setAttribute("role", "button");
    target.setAttribute("tabindex", "0");
    target.setAttribute("aria-label", "Enlarge QR code for scanning");
    target.title = "Click to enlarge";
    target.onclick = () => _expandQR(svg);
    target.onkeydown = e => {
      if (e.key === "Enter" || e.key === " ") { e.preventDefault(); _expandQR(svg); }
    };
  }
}

export function toast(msg, { error = false, duration = 2800 } = {}) {
  const t = el("div", {
    class: "toast" + (error ? " toast-error" : ""),
    role: "status",
    "aria-live": error ? "assertive" : "polite",
  }, msg);
  document.body.appendChild(t);
  setTimeout(() => t.remove(), duration);
}

export function errorToast(msg) { toast(msg, { error: true, duration: 4000 }); }

// Friendly labels for lifecycle enums (Session + QuizRun). Badge CSS
// classes still use the raw status value (e.g. `badge-live`), which the
// tests assert on; only the displayed text changes.
export const STATUS_LABELS = {
  planning: "Not started",
  live: "Live",
  ended: "Ended",
  queued: "Queued",
  closed: "Closed",
};

export const statusLabel = (s) => STATUS_LABELS[s] || s;
