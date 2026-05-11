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
  function connect() {
    ws = new WebSocket(url);
    ws.onopen = () => { retry = 0; };
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

export function toast(msg, { error = false, duration = 2800 } = {}) {
  const t = el("div", { class: "toast" + (error ? " toast-error" : "") }, msg);
  document.body.appendChild(t);
  setTimeout(() => t.remove(), duration);
}

export function errorToast(msg) { toast(msg, { error: true, duration: 4000 }); }
