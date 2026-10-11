import { $, api, bindMenuDismiss, el, errorToast, escapeHtml, exportMenu, guardClick, markUsable, setVisible, statusLabel, toast } from "./common";
import type { AdminStatus, SessionRow } from "./types";

// `?session=<code>` is an older link to a session; the session page is now
// `/m/<code>` (UC-A-04). `?delete=<code>` comes from the session page's
// Delete button and runs the delete flow below (UC-A-07).
const pageParams = new URLSearchParams(location.search);
const requestedSessionCode = pageParams.get("session")?.toUpperCase() ?? null;
let requestedDeleteCode = pageParams.get("delete")?.toUpperCase() ?? null;

// ----- one-time first-admin setup link (UC-A-01) -----
// The server logs /#setup=<token> on first start. Keep the token in memory
// and drop it from the address bar so it doesn't linger in history.
const setupToken = new URLSearchParams(location.hash.slice(1)).get("setup");
if (setupToken) history.replaceState(null, "", location.pathname + location.search);

// ----- bad code banner from /s/BOGUS redirect -----
const bad = new URLSearchParams(location.search).get("bad_code");
if (bad) {
  const msg = $("#bad-code-msg");
  msg.textContent = `Session "${bad.toUpperCase()}" does not exist. Check the code and try again.`;
  setVisible(msg, true);
  history.replaceState({}, "", "/");
}
$("#join-code").addEventListener("input", () => { setVisible($("#bad-code-msg"), false); });

// ----- export every owned session (UC-A-30) -----
$("#sessions-card .card-tools").appendChild(
  exportMenu("all-export", "/api/export/all", "Export all your sessions and quizzes", "Export all data ▾"));
bindMenuDismiss();

// ----- visibility helpers -----
const cards: Record<string, HTMLElement> = {
  join: $("#join-card"),
  setup: $("#setup-card"),
  setupNeeded: $("#setup-needed-card"),
  login: $("#login-card"),
  sessions: $("#sessions-card"),
  library: $("#library-card"),
  confirmDelete: $("#confirm-delete-card"),
  changePw: $("#change-pw-card"),
};
function show(...names: string[]): void {
  for (const k of Object.keys(cards)) setVisible(cards[k], names.includes(k));
}

function setHeaderMeta(node: HTMLElement): void {
  const meta = $("#header-meta");
  meta.innerHTML = "";
  meta.appendChild(node);
}

// ----- state machine -----
async function refresh(): Promise<void> {
  const s = await api<AdminStatus>("/api/admin/status");
  $<HTMLElement>("main").classList.toggle("wide", s.authenticated);
  setVisible($("#admin-page-nav"), s.authenticated);
  if (!s.initialized) {
    setHeaderMeta(el("span", { class: "muted small" }, "Initial setup"));
    // Without the link, explain where it is instead of showing a form the
    // server would refuse.
    show(setupToken ? "setup" : "setupNeeded");
    return;
  }
  if (!s.authenticated) {
    setHeaderMeta(el("span", { class: "muted small" }, "Live Q&A and quizzes for training sessions."));
    show("join", "login");
    return;
  }
  const meta = el("div", { class: "row gap" });
  meta.appendChild(el("span", { class: "small muted" }, "Signed in as "));
  meta.appendChild(el("strong", { class: "small" }, s.username ?? ""));
  const cpBtn = el("button", { class: "ghost xsmall" }, "Change password");
  cpBtn.addEventListener("click", openChangePassword);
  meta.appendChild(cpBtn);
  const logoutBtn = el("button", { class: "ghost xsmall" }, "Log out");
  logoutBtn.addEventListener("click", async () => {
    await api("/api/admin/logout", { method: "POST" });
    void refresh();
  });
  meta.appendChild(logoutBtn);
  setHeaderMeta(meta);
  if (requestedSessionCode) {
    location.replace(`/m/${encodeURIComponent(requestedSessionCode)}`);
    return;
  }
  show("sessions", "library");
  void loadSessions();
}

// ----- join -----
function submitJoin(): void {
  const code = $<HTMLInputElement>("#join-code").value.trim().toUpperCase();
  if (!code) return;
  location.href = `/s/${code}`;
}
$("#join-btn").addEventListener("click", submitJoin);
$("#join-code").addEventListener("keydown", (e) => { if ((e as KeyboardEvent).key === "Enter") submitJoin(); });

// ----- setup -----
async function submitSetup(): Promise<void> {
  const username = $<HTMLInputElement>("#su-user").value.trim();
  const password = $<HTMLInputElement>("#su-pass").value;
  const confirmPw = $<HTMLInputElement>("#su-pass2").value;
  if (password !== confirmPw) { errorToast("Passwords don't match"); return; }
  try {
    await api("/api/admin/setup", { method: "POST", body: { username, password, setup_token: setupToken } });
    void refresh();
  } catch (e) { errorToast((e as Error).message); }
}
guardClick($<HTMLButtonElement>("#su-btn"), submitSetup);
$("#su-pass2").addEventListener("keydown", (e) => { if ((e as KeyboardEvent).key === "Enter") void submitSetup(); });

// ----- login -----
async function submitLogin(): Promise<void> {
  const username = $<HTMLInputElement>("#li-user").value.trim();
  const password = $<HTMLInputElement>("#li-pass").value;
  try {
    await api("/api/admin/login", { method: "POST", body: { username, password } });
    void refresh();
  } catch (e) { errorToast((e as Error).message); }
}
$("#li-btn").addEventListener("click", () => void submitLogin());
$("#li-pass").addEventListener("keydown", (e) => { if ((e as KeyboardEvent).key === "Enter") void submitLogin(); });

// ----- sessions: create -----
async function createSession(): Promise<void> {
  const titleInp = $<HTMLInputElement>("#new-session-title");
  const title = titleInp.value.trim();
  if (!title) { errorToast("Session title is required"); titleInp.focus(); return; }
  try {
    const s = await api<SessionRow>("/api/sessions", { method: "POST", body: { title } });
    titleInp.value = "";
    toast(`Created "${s.title}" — code ${s.code}`);
    void loadSessions();
  } catch (e) { errorToast((e as Error).message); }
}
guardClick($<HTMLButtonElement>("#new-session-btn"), createSession);
$("#new-session-title").addEventListener("keydown", (e) => { if ((e as KeyboardEvent).key === "Enter") void createSession(); });

// ----- sessions: list -----
async function loadSessions(): Promise<void> {
  const tbody = $("#session-rows");
  try {
    const rows = await api<SessionRow[]>("/api/sessions");
    if (!rows.length) {
      tbody.innerHTML = `<tr><td colspan="7" class="muted small">No sessions yet. Add one using the title field above.</td></tr>`;
      return;
    }
    tbody.innerHTML = "";
    for (const s of rows) {
      const when = new Date(s.created_at).toLocaleString();
      // A session has its own page, so the row navigates there (UX.md §5).
      const sessionUrl = `/m/${s.code}`;
      const tr = el("tr", { class: "rowable" });
      tr.addEventListener("click", () => { location.href = sessionUrl; });
      tr.appendChild(el("td", {}, el("a", { href: sessionUrl }, s.title)));
      tr.appendChild(el("td", {}, el("code", { class: "small" }, s.code)));
      tr.appendChild(el("td", {}, el("span", { class: "badge badge-" + s.status }, statusLabel(s.status))));
      tr.appendChild(el("td", { class: "num muted" }, String(s.query_count)));
      tr.appendChild(el("td", { class: "num muted" }, String(s.quiz_run_count)));
      tr.appendChild(el("td", { class: "muted small" }, when));

      const actions = el("td", { class: "actions" });
      actions.addEventListener("click", (e) => e.stopPropagation());
      actions.appendChild(el("a", { class: "btn ghost xsmall", href: `/m/${s.code}` }, "Moderate"));
      actions.appendChild(el("a", { class: "btn ghost xsmall", href: `/s/${s.code}` }, "Participant"));
      actions.appendChild(el("a", { class: "btn ghost xsmall", href: `/p/${s.code}`, target: "_blank" }, "Projector"));
      if (s.status === "planning") {
        const startBtn = el("button", { class: "ghost xsmall" }, "Start") as HTMLButtonElement;
        guardClick(startBtn, async () => {
          try {
            await api(`/api/sessions/${s.code}/start`, { method: "POST" });
            await loadSessions();
          } catch (e) { errorToast((e as Error).message); }
        });
        actions.appendChild(startBtn);
      }
      const delBtn = el("button", { class: "danger ghost xsmall" }, "Delete");
      delBtn.addEventListener("click", () => startDeleteFlow(s));
      actions.appendChild(delBtn);
      tr.appendChild(actions);
      tbody.appendChild(tr);
    }
    if (requestedDeleteCode) {
      const requested = rows.find((row) => row.code === requestedDeleteCode);
      requestedDeleteCode = null;
      history.replaceState({}, "", "/");
      if (requested) startDeleteFlow(requested);
    }
  } catch (e) {
    tbody.innerHTML = `<tr><td colspan="7" class="error-banner">${escapeHtml((e as Error).message)}</td></tr>`;
  }
}

// ----- session delete flow -----
function hideConfirmCard(): void {
  setVisible($("#confirm-delete-card"), false);
  $<HTMLInputElement>("#cd-confirm").value = "";
  const go = $<HTMLButtonElement>("#cd-go");
  go.disabled = true;
  go.onclick = null;
}
$("#cd-cancel").addEventListener("click", hideConfirmCard);

async function deleteNoData(s: SessionRow): Promise<void> {
  try {
    await api(`/api/sessions/${s.code}`, { method: "DELETE", body: {} });
    toast(`Deleted "${s.title}"`);
    void loadSessions();
  } catch (e) { errorToast((e as Error).message); }
}

function startDeleteFlow(s: SessionRow): void {
  if (s.status === "live") {
    errorToast("End the session before deleting it.");
    return;
  }
  const hasData = s.query_count > 0 || s.quiz_run_count > 0;
  if (!hasData) {
    if (confirm(`Delete empty session "${s.title}"?`)) void deleteNoData(s);
    return;
  }
  const warn = $("#cd-warn");
  warn.textContent =
    `This permanently deletes "${s.title}" and everything in it: ` +
    `${s.query_count} question(s), ${s.quiz_run_count} quiz run(s), ` +
    `and all participant responses. Cannot be undone.`;
  const confInp = $<HTMLInputElement>("#cd-confirm");
  const goBtn = $<HTMLButtonElement>("#cd-go");
  confInp.value = "";
  goBtn.disabled = true;
  confInp.oninput = () => { goBtn.disabled = confInp.value !== s.title; };
  goBtn.onclick = async () => {
    try {
      await api(`/api/sessions/${s.code}`, { method: "DELETE", body: { confirm_title: confInp.value } });
      hideConfirmCard();
      toast(`Deleted "${s.title}"`);
      void loadSessions();
    } catch (e) { errorToast((e as Error).message); }
  };
  setVisible($("#confirm-delete-card"), true);
  confInp.focus();
  $("#confirm-delete-card").scrollIntoView({ behavior: "smooth", block: "nearest" });
}

// ----- change password -----
function openChangePassword(): void {
  $<HTMLInputElement>("#cp-current").value = "";
  $<HTMLInputElement>("#cp-new").value = "";
  $<HTMLInputElement>("#cp-new2").value = "";
  setVisible($("#change-pw-card"), true);
  $("#cp-current").focus();
  $("#change-pw-card").scrollIntoView({ behavior: "smooth", block: "nearest" });
}
function closeChangePassword(): void {
  setVisible($("#change-pw-card"), false);
}
$("#cp-close").addEventListener("click", closeChangePassword);
async function submitChangePassword(): Promise<void> {
  const current = $<HTMLInputElement>("#cp-current").value;
  const next = $<HTMLInputElement>("#cp-new").value;
  const confirm2 = $<HTMLInputElement>("#cp-new2").value;
  if (next !== confirm2) { errorToast("New passwords don't match"); return; }
  if (next.length < 8) { errorToast("Password must be at least 8 characters"); return; }
  try {
    await api("/api/admin/change_password", {
      method: "POST",
      body: { current_password: current, new_password: next },
    });
    toast("Password updated");
    closeChangePassword();
  } catch (e) { errorToast((e as Error).message); }
}
guardClick($<HTMLButtonElement>("#cp-submit"), submitChangePassword);
$("#cp-new2").addEventListener("keydown", (e) => { if ((e as KeyboardEvent).key === "Enter") void submitChangePassword(); });

// Escape closes whichever drill-down is open.
document.addEventListener("keydown", (e) => {
  if (e.key !== "Escape" || e.defaultPrevented) return;
  if (!$("#change-pw-card").hidden) { closeChangePassword(); return; }
  if (!$("#confirm-delete-card").hidden) hideConfirmCard();
});

markUsable("landing");
void refresh();
