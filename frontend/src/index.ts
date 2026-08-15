import { $, api, el, errorToast, escapeHtml, guardClick, renderQR, statusLabel, toast } from "./common";
import type { AdminStatus, FeedbackSummary, SessionRow } from "./types";

let requestedSessionCode = new URLSearchParams(location.search).get("session")?.toUpperCase() ?? null;

// ----- bad code banner from /s/BOGUS redirect -----
const bad = new URLSearchParams(location.search).get("bad_code");
if (bad) {
  const msg = $("#bad-code-msg");
  msg.textContent = `Session "${bad.toUpperCase()}" does not exist. Check the code and try again.`;
  msg.style.display = "";
  history.replaceState({}, "", "/");
}
$("#join-code").addEventListener("input", () => { $("#bad-code-msg").style.display = "none"; });

// ----- GitHub OAuth error banner -----
const authErr = new URLSearchParams(location.search).get("auth_error");
if (authErr) {
  errorToast(authErr);
  history.replaceState({}, "", "/");
}

// ----- visibility helpers -----
const cards: Record<string, HTMLElement> = {
  join: $("#join-card"),
  setup: $("#setup-card"),
  login: $("#login-card"),
  sessions: $("#sessions-card"),
  library: $("#library-card"),
  sessionDetail: $("#session-detail-card"),
  confirmDelete: $("#confirm-delete-card"),
  changePw: $("#change-pw-card"),
};
function show(...names: string[]): void {
  for (const k of Object.keys(cards)) cards[k].style.display = names.includes(k) ? "" : "none";
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
  $("#admin-page-nav").style.display = s.authenticated ? "" : "none";
  if (!s.initialized) {
    setHeaderMeta(el("span", { class: "muted small" }, "Initial setup"));
    show("setup");
    return;
  }
  if (!s.authenticated) {
    setHeaderMeta(el("span", { class: "muted small" }, "Live Q&A and quizzes for training sessions."));
    $("#github-login-wrap").style.display = s.github_enabled ? "" : "none";
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
    await api("/api/admin/setup", { method: "POST", body: { username, password } });
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
      const tr = el("tr", { class: "rowable" + (currentDetail === s.code ? " selected" : "") });
      tr.addEventListener("click", () => void openSessionDetail(s));
      tr.appendChild(el("td", {}, s.title));
      tr.appendChild(el("td", {}, el("code", { class: "small" }, s.code)));
      tr.appendChild(el("td", {}, el("span", { class: "badge badge-" + s.status }, statusLabel(s.status))));
      tr.appendChild(el("td", { class: "num muted" }, String(s.query_count)));
      tr.appendChild(el("td", { class: "num muted" }, String(s.quiz_run_count)));
      tr.appendChild(el("td", { class: "muted small" }, when));

      const actions = el("td", { class: "actions" });
      actions.addEventListener("click", (e) => e.stopPropagation());
      actions.appendChild(el("a", { class: "small", href: `/m/${s.code}` }, "Moderate"));
      actions.appendChild(el("a", { class: "small", href: `/s/${s.code}` }, "Participant"));
      actions.appendChild(el("a", { class: "small", href: `/p/${s.code}`, target: "_blank" }, "Projector"));
      const delBtn = el("button", { class: "danger ghost xsmall" }, "Delete");
      delBtn.addEventListener("click", () => startDeleteFlow(s));
      actions.appendChild(delBtn);
      tr.appendChild(actions);
      tbody.appendChild(tr);
    }
    if (requestedSessionCode && currentDetail !== requestedSessionCode) {
      const requested = rows.find((row) => row.code === requestedSessionCode);
      requestedSessionCode = null;
      if (requested) {
        history.replaceState({}, "", "/");
        void openSessionDetail(requested);
      }
    }
  } catch (e) {
    tbody.innerHTML = `<tr><td colspan="7" class="error-banner">${escapeHtml((e as Error).message)}</td></tr>`;
  }
}

// ----- session detail / settings drill-down -----
let currentDetail: string | null = null;
let currentDetailData: SessionRow | null = null;

function participantUrlFor(s: SessionRow): string {
  const base = (s.participant_base_url || location.origin).replace(/\/$/, "");
  return `${base}/s/${s.code}`;
}

async function paintDetail(s: SessionRow): Promise<void> {
  currentDetailData = s;
  $("#sd-title").textContent = `Session: ${s.title}`;
  $<HTMLInputElement>("#sd-session-title").value = s.title;
  $<HTMLInputElement>("#sd-base-url").value = s.participant_base_url || "";
  $("#sd-status").textContent = statusLabel(s.status);
  $("#sd-status").className = "badge badge-" + s.status;
  renderLifecycleActions(s);
  $<HTMLAnchorElement>("#sd-open-mod").href = `/m/${s.code}`;
  const url = participantUrlFor(s);
  $("#sd-url").textContent = url;
  try { await renderQR($("#sd-qr"), url, { cellSize: 4, margin: 2 }); }
  catch { $("#sd-qr").textContent = "QR unavailable"; }
  void loadDetailFeedback(s.code);
}

async function loadDetailFeedback(code: string): Promise<void> {
  const root = $("#sd-feedback");
  root.innerHTML = "";
  let sum: FeedbackSummary;
  try { sum = await api<FeedbackSummary>(`/api/sessions/${code}/feedback/summary`); }
  catch { return; }
  root.appendChild(el("div", { class: "card-head" }, el("h2", {}, "Feedback")));
  if (!sum.count) {
    root.appendChild(el("div", { class: "muted small" }, "No feedback yet."));
    return;
  }
  root.appendChild(el("div", {},
    el("span", { class: "fb-avg" }, `★ ${sum.average}`),
    el("span", { class: "small muted" }, ` · ${sum.count} response(s)`),
  ));
  for (const it of sum.items) {
    const stars = "★".repeat(it.rating) + "☆".repeat(5 - it.rating);
    root.appendChild(el("div", { class: "fb-item" },
      el("div", {},
        el("span", { class: "fb-stars-static" }, stars),
        it.author_name ? el("span", { class: "small muted" }, "  — " + it.author_name) : null,
      ),
      it.went_well ? el("div", { class: "small" }, el("strong", {}, "Went well: "), it.went_well) : null,
      it.to_improve ? el("div", { class: "small" }, el("strong", {}, "Improve: "), it.to_improve) : null,
    ));
  }
}

function renderLifecycleActions(s: SessionRow): void {
  const hint = $("#sd-lifecycle-hint");
  const actions = $("#sd-lifecycle-actions");
  actions.innerHTML = "";
  if (s.status === "planning") {
    hint.textContent = "Not yet started.";
    const btn = el("button", { class: "primary xsmall" }, "Start session");
    btn.addEventListener("click", () => void transitionSession("start"));
    actions.appendChild(btn);
  } else if (s.status === "live") {
    hint.textContent = "Live now.";
    const btn = el("button", { class: "danger ghost xsmall" }, "End session");
    btn.addEventListener("click", () => {
      if (!confirm("End the session? Participants can no longer ask or vote.")) return;
      void transitionSession("end");
    });
    actions.appendChild(btn);
  } else {
    hint.textContent = "Ended — read-only.";
  }
}

async function transitionSession(action: string): Promise<void> {
  if (!currentDetailData) return;
  try {
    await api(`/api/sessions/${currentDetailData.code}/${action}`, { method: "POST" });
    toast(`Session ${action === "start" ? "started" : "ended"}`);
    await refreshDetail();
  } catch (e) { errorToast((e as Error).message); }
}

$("#sd-share-mod").addEventListener("click", async () => {
  if (!currentDetailData) return;
  const url = `${location.origin}/m/${currentDetailData.code}#k=${currentDetailData.mod_key}`;
  try {
    await navigator.clipboard.writeText(url);
    toast("Moderator URL copied — share with delegates only.");
  } catch {
    errorToast("Couldn't copy — load over HTTPS for clipboard access.");
  }
});

async function openSessionDetail(s: SessionRow): Promise<void> {
  currentDetail = s.code;
  $("#session-detail-card").style.display = "";
  await paintDetail(s);
  void loadSessions();
  $("#session-detail-card").scrollIntoView({ behavior: "smooth", block: "nearest" });
}

function closeSessionDetail(): void {
  currentDetail = null;
  currentDetailData = null;
  $("#session-detail-card").style.display = "none";
  void loadSessions();
}
$("#sd-close").addEventListener("click", closeSessionDetail);

async function refreshDetail(): Promise<void> {
  const fresh = await api<SessionRow[]>("/api/sessions");
  const found = fresh.find((x) => x.code === currentDetailData?.code);
  if (found) await paintDetail(found);
  void loadSessions();
}

async function saveBaseUrl(): Promise<void> {
  if (!currentDetailData) return;
  try {
    await api(`/api/sessions/${currentDetailData.code}/participant_base_url`, {
      method: "POST", body: { url: $<HTMLInputElement>("#sd-base-url").value },
    });
    toast("Base URL saved");
    await refreshDetail();
  } catch (e) { errorToast((e as Error).message); }
}
$("#sd-base-url").addEventListener("change", () => void saveBaseUrl());
$("#sd-clear").addEventListener("click", async () => {
  $<HTMLInputElement>("#sd-base-url").value = "";
  await saveBaseUrl();
});

async function saveTitle(): Promise<void> {
  if (!currentDetailData) return;
  const newTitle = $<HTMLInputElement>("#sd-session-title").value.trim();
  if (!newTitle || newTitle === currentDetailData.title) return;
  try {
    await api(`/api/sessions/${currentDetailData.code}`, { method: "PATCH", body: { title: newTitle } });
    toast("Title saved");
    await refreshDetail();
  } catch (e) {
    $<HTMLInputElement>("#sd-session-title").value = currentDetailData.title;
    errorToast((e as Error).message);
  }
}
$("#sd-session-title").addEventListener("change", () => void saveTitle());

$("#sd-copy").addEventListener("click", async () => {
  const url = $("#sd-url").textContent ?? "";
  try { await navigator.clipboard.writeText(url); toast("URL copied"); }
  catch { errorToast("Couldn't copy — select the URL above to copy manually."); }
});

// ----- session delete flow -----
function hideConfirmCard(): void {
  $("#confirm-delete-card").style.display = "none";
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
  $("#confirm-delete-card").style.display = "";
  confInp.focus();
  $("#confirm-delete-card").scrollIntoView({ behavior: "smooth", block: "nearest" });
}

// ----- change password -----
function openChangePassword(): void {
  $<HTMLInputElement>("#cp-current").value = "";
  $<HTMLInputElement>("#cp-new").value = "";
  $<HTMLInputElement>("#cp-new2").value = "";
  $("#change-pw-card").style.display = "";
  $("#cp-current").focus();
  $("#change-pw-card").scrollIntoView({ behavior: "smooth", block: "nearest" });
}
function closeChangePassword(): void {
  $("#change-pw-card").style.display = "none";
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
  if (e.key !== "Escape") return;
  if ($("#change-pw-card").style.display !== "none") { closeChangePassword(); return; }
  if ($("#confirm-delete-card").style.display !== "none") { hideConfirmCard(); return; }
  if ($("#session-detail-card").style.display !== "none") closeSessionDetail();
});

void refresh();
