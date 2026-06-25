import {
  $, api, el, errorToast, guardClick, type LiveMessage, modHeaders, modKey,
  openLiveSocket, pathCode, renderQR, setModKey, statusLabel, toast,
} from "./common";
import type { AdminStatus, FeedbackSummary, Query, QuizRun, QuizSummary, Session } from "./types";

const CODE = pathCode();

// Pick up mod_key from URL hash on first visit.
if (location.hash.includes("k=")) {
  const k = new URLSearchParams(location.hash.slice(1)).get("k");
  if (k) { setModKey(k); history.replaceState(null, "", location.pathname); }
}

let queries: Query[] = [];
let quizRuns: QuizRun[] = [];
let quizzes: QuizSummary[] = [];
let sessionState: Session | null = null;
let presenceTimer: ReturnType<typeof setInterval> | null = null;
let isOwner = false;
const pendingResponseText = new Map<number, string>();

function showWorkSurfaces(visible: boolean): void {
  for (const id of ["lifecycle-card", "setup-section", "quizzes-card", "queries-card", "feedback-card"]) {
    $("#" + id).style.display = visible ? "" : "none";
  }
}
function showKeyGate(): void {
  $("#modkey-code").textContent = CODE;
  $("#modkey-card").style.display = "";
  showWorkSurfaces(false);
  $("#modkey-input").focus();
}
async function trySubmitKey(): Promise<void> {
  const k = $<HTMLInputElement>("#modkey-input").value.trim();
  if (!k) return;
  setModKey(k);
  $("#modkey-card").style.display = "none";
  try { await boot(); } catch { showKeyGate(); errorToast("Wrong key for this session."); }
}
$("#modkey-submit").addEventListener("click", () => void trySubmitKey());
$("#modkey-input").addEventListener("keydown", (e) => { if ((e as KeyboardEvent).key === "Enter") void trySubmitKey(); });

// Close any open ⋯ run-action menu on outside-click or Esc.
document.addEventListener("click", (e) => {
  for (const d of document.querySelectorAll<HTMLDetailsElement>("details.menu[open]")) {
    if (!d.contains(e.target as Node)) d.open = false;
  }
});
document.addEventListener("keydown", (e) => {
  if (e.key !== "Escape") return;
  for (const d of document.querySelectorAll<HTMLDetailsElement>("details.menu[open]")) d.open = false;
});

async function loadSession(): Promise<void> {
  sessionState = await api<Session>(`/api/sessions/${CODE}`);
  document.title = `Mod — ${sessionState.title}`;
  $("#title").textContent = sessionState.title;
  $("#code").textContent = "Code " + CODE;
  $<HTMLAnchorElement>("#participant-link").href = `/s/${CODE}`;
  $<HTMLAnchorElement>("#projector-link").href = `/p/${CODE}`;
  renderLifecycle();
  void renderInvite();
}

function participantUrlFor(s: Session): string {
  const base = (s.participant_base_url || location.origin).replace(/\/$/, "");
  return `${base}/s/${s.code}`;
}

async function renderInvite(): Promise<void> {
  if (!sessionState) return;
  const url = participantUrlFor(sessionState);
  $<HTMLInputElement>("#base-url").value = sessionState.participant_base_url || "";
  $("#invite-url").textContent = url;
  const baseField = $("#base-url").closest(".field") as HTMLElement | null;
  if (baseField) baseField.style.display = isOwner ? "" : "none";
  try { await renderQR($("#invite-qr"), url, { cellSize: 4, margin: 2 }); }
  catch { $("#invite-qr").textContent = "QR unavailable"; }
}

async function saveModBaseUrl(url: string): Promise<void> {
  try {
    await api(`/api/sessions/${CODE}/participant_base_url`, { method: "POST", headers: modHeaders(), body: { url } });
    await loadSession();
    toast(url ? "Base URL saved" : "Reverted to default");
  } catch (e) { errorToast((e as Error).message); }
}
$("#base-url").addEventListener("change", () => void saveModBaseUrl($<HTMLInputElement>("#base-url").value));
$("#base-url-clear").addEventListener("click", () => { $<HTMLInputElement>("#base-url").value = ""; void saveModBaseUrl(""); });
$("#invite-copy").addEventListener("click", async () => {
  const url = $("#invite-url").textContent ?? "";
  try { await navigator.clipboard.writeText(url); toast("URL copied"); }
  catch { errorToast("Couldn't copy — load over HTTPS for clipboard access."); }
});

function renderLifecycle(): void {
  if (!sessionState) return;
  const status = sessionState.status;
  $("#session-status").textContent = statusLabel(status);
  $("#session-status").className = "badge badge-" + status;
  const actions = $("#lifecycle-actions"); actions.innerHTML = "";
  const hint = $("#lifecycle-hint");
  if (status === "planning") {
    hint.textContent = "Session is in planning. Start it when the audience is ready.";
    const btn = el("button", { class: "primary small" }, "Start session");
    btn.addEventListener("click", () => void transition("start"));
    actions.appendChild(btn);
  } else if (status === "live") {
    hint.textContent = "Session is live. End it when you're done.";
    const btn = el("button", { class: "danger ghost small" }, "End session");
    btn.addEventListener("click", () => {
      if (!confirm("End the session? Participants can no longer ask questions.")) return;
      void transition("end");
    });
    actions.appendChild(btn);
  } else {
    hint.textContent = "Session has ended. Read-only from here.";
  }
}

async function transition(action: string): Promise<void> {
  try {
    await api(`/api/sessions/${CODE}/${action}`, { method: "POST", headers: modHeaders() });
    await loadSession();
    toast(`Session ${action}ed`);
  } catch (e) { errorToast((e as Error).message); }
}

async function loadPresence(): Promise<void> {
  try {
    const r = await api<{ online: number }>(`/api/sessions/${CODE}/presence`);
    $("#live-count").textContent = `${r.online} online`;
  } catch { /* presence is best-effort */ }
}

async function loadQueries(): Promise<void> {
  queries = await api<Query[]>(`/api/sessions/${CODE}/queries`, { headers: modHeaders() });
  renderQueries();
}

function renderQueries(): void {
  const root = $("#queries");
  root.innerHTML = "";
  if (!queries.length) {
    root.appendChild(el("div", { class: "muted small" }, "No questions yet. Share the participant URL to invite questions."));
    return;
  }
  const sorted = [...queries].sort((a, b) => {
    if (a.removed !== b.removed) return a.removed ? 1 : -1;
    if (a.responded !== b.responded) return a.responded ? 1 : -1;
    return b.vote_count - a.vote_count;
  });
  for (const q of sorted) root.appendChild(renderQuery(q));
}

function renderQuery(q: Query): HTMLElement {
  const initial = pendingResponseText.has(q.id) ? pendingResponseText.get(q.id)! : (q.response_text || "");
  const respInput = el("textarea", { placeholder: "Type a response (optional — leave empty if you answered verbally)…" }, initial) as HTMLTextAreaElement;
  respInput.addEventListener("input", () => pendingResponseText.set(q.id, respInput.value));
  const respondBtn = el("button", { class: "primary small" }, q.responded ? "Update response" : "Mark responded");
  respondBtn.addEventListener("click", async () => {
    try {
      await api(`/api/sessions/${CODE}/queries/${q.id}/respond`, {
        method: "POST", headers: modHeaders(),
        body: { response_text: respInput.value.trim(), responded: true },
      });
      pendingResponseText.delete(q.id);
      void loadQueries();
    } catch (e) { errorToast((e as Error).message); }
  });
  const reopenBtn = q.responded ? el("button", { class: "ghost small" }, "Reopen") : null;
  reopenBtn?.addEventListener("click", async () => {
    try {
      await api(`/api/sessions/${CODE}/queries/${q.id}/respond`, {
        method: "POST", headers: modHeaders(),
        body: { response_text: respInput.value.trim(), responded: false },
      });
      pendingResponseText.delete(q.id);
      void loadQueries();
    } catch (e) { errorToast((e as Error).message); }
  });
  const removeBtn = el("button", { class: "danger ghost small" }, q.removed ? "Restore" : "Remove");
  removeBtn.addEventListener("click", async () => {
    try {
      await api(`/api/sessions/${CODE}/queries/${q.id}/remove`, {
        method: "POST", headers: modHeaders(), body: { removed: !q.removed },
      });
      void loadQueries();
    } catch (e) { errorToast((e as Error).message); }
  });
  const voteBox = el("div", { class: "vote-btn" + (q.voted ? " voted" : "") },
    el("div", { class: "count" }, String(q.vote_count)),
    el("div", { class: "label" }, "votes"));
  const body = el("div", { class: "body" },
    el("div", { class: "text" }, q.text),
    q.author_name ? el("div", { class: "small muted" }, "— " + q.author_name) : null,
    el("div", { style: "margin-top: 10px;" }, respInput),
    el("div", { class: "row", style: "margin-top: 8px; gap: 6px;" },
      respondBtn, reopenBtn, el("div", { class: "spacer" }), removeBtn),
  );
  return el("div", { class: "question" + (q.responded ? " answered" : "") + (q.removed ? " hidden-q" : "") }, voteBox, body);
}

async function loadQuizzes(): Promise<void> {
  quizzes = await api<QuizSummary[]>(`/api/sessions/${CODE}/available_quizzes`, { headers: modHeaders() });
  const sel = $<HTMLSelectElement>("#quiz-select");
  sel.innerHTML = "";
  if (!quizzes.length) {
    sel.appendChild(el("option", { value: "" }, "No ready quizzes — publish one in the library"));
  } else {
    for (const q of quizzes) sel.appendChild(el("option", { value: q.id }, `${q.title} (${q.question_count} questions)`));
  }
}

async function loadQuizRuns(): Promise<void> {
  quizRuns = await api<QuizRun[]>(`/api/sessions/${CODE}/quiz_runs`, { headers: modHeaders() });
  renderQuizRuns();
}

function renderQuizRuns(): void {
  const root = $("#quiz-runs");
  root.innerHTML = "";
  if (!quizRuns.length) {
    root.appendChild(el("div", { class: "muted small" }, "No quizzes added yet — open Set up above and Add a quiz."));
    return;
  }
  for (const r of quizRuns) root.appendChild(renderQuizRun(r));
}

function renderQuizRun(r: QuizRun): HTMLElement {
  const tag = el("span", { class: "badge badge-" + r.status }, statusLabel(r.status));
  const head = el("div", { class: "row", style: "margin-bottom: 8px; gap: 6px;" },
    el("strong", {}, r.quiz_title),
    el("span", { class: "small muted" }, ` v${r.version_no}`),
    tag,
    el("span", { class: "small muted" }, ` · q ${r.current_question_idx + 1}/${r.question_count}`),
    el("div", { class: "spacer" }),
  );
  if (r.status === "live" && r.reveal_current) {
    head.insertBefore(
      el("span", { class: "small", style: "color: var(--accent);" }, "voting closed"),
      head.querySelector(".spacer"));
  }
  if (r.status === "queued") {
    head.appendChild(actBtn("primary", "Start", () => act(r.id, "start")));
  }
  if (r.status === "live") {
    const phase = r.reveal_current ? "results" : "answering";
    const nextLabel = phase === "answering"
      ? "Reveal results →"
      : (r.current_question_idx + 1 < r.question_count ? "Next question →" : "Finish quiz →");
    head.appendChild(actBtn("primary", nextLabel, () => nextPhase(r)));
    head.appendChild(actBtn("ghost", "← Prev", () => advance(r.id, "prev")));
  }
  const menu = buildRunMenu(r);
  if (menu) head.appendChild(menu);
  const cur = r.current_question;
  const totals = r.results?.totals ?? {};
  const respondents = r.results?.respondents ?? 0;
  const detail = el("div");
  if (cur) {
    detail.appendChild(el("div", {}, el("strong", {}, cur.text)));
    if (cur.image_url) detail.appendChild(el("img", { class: "q-image", src: cur.image_url }));
    for (const a of cur.answers) {
      const pct = respondents ? Math.round((totals[a.id] || 0) / respondents * 100) : 0;
      const aDiv = el("div", { class: "option disabled" + (a.is_correct ? " correct" : "") });
      const bar = el("div", { class: "bar" });
      bar.style.transform = `scaleX(${respondents ? (totals[a.id] || 0) / respondents : 0})`;
      aDiv.appendChild(bar);
      if (a.image_url) aDiv.appendChild(el("img", { class: "opt-img", src: a.image_url }));
      aDiv.appendChild(el("div", { class: "opt-text" }, a.text + (a.is_correct ? "  ✓" : "")));
      aDiv.appendChild(el("div", { class: "opt-pct" }, `${totals[a.id] || 0} (${pct}%)`));
      detail.appendChild(aDiv);
    }
    detail.appendChild(el("div", { class: "small muted" }, `${respondents} respondent(s)`));
  }
  return el("section", { class: "card", style: "background: var(--panel-2);" }, head, detail);
}

function buildRunMenu(r: QuizRun): HTMLElement | null {
  if (r.status === "closed") return null;
  const panel = el("div", { class: "menu-panel" });
  const onFinishStep = r.status === "live" && r.reveal_current && r.current_question_idx + 1 >= r.question_count;
  if (r.status === "live" && !onFinishStep) {
    panel.appendChild(actBtn("ghost", "Finish quiz", () => act(r.id, "close")));
  }
  if (r.status === "live" && r.reveal_current) {
    panel.appendChild(actBtn("ghost", "Reopen voting", () => reveal(r.id, false)));
  }
  const countsLabel = r.show_live_counts ? "Hide vote counts from audience" : "Show vote counts to audience";
  panel.appendChild(actBtn("ghost", countsLabel, () => toggleLiveCounts(r.id, !r.show_live_counts)));
  const delLabel = r.status === "live" ? "Delete run (discard results)" : "Delete run";
  const del_ = actBtn("danger ghost", delLabel, () => del(r.id));
  del_.setAttribute("aria-label", "Delete this quiz run");
  panel.appendChild(el("div", { class: "menu-sep" }));
  panel.appendChild(del_);
  return el("details", { class: "menu" },
    el("summary", { "aria-label": "More actions", title: "Run actions" }, "⋯"),
    panel);
}

function actBtn(cls: string, label: string, handler: () => unknown): HTMLButtonElement {
  return guardClick(el("button", { class: cls + " small" }, label) as HTMLButtonElement, handler);
}

async function act(id: number, verb: string): Promise<void> {
  try {
    await api(`/api/sessions/${CODE}/quiz_runs/${id}/${verb}`, { method: "POST", headers: modHeaders() });
    await loadQuizRuns();
    await loadSession();
  } catch (e) { errorToast((e as Error).message); }
}
async function advance(id: number, direction: string): Promise<void> {
  try {
    await api(`/api/sessions/${CODE}/quiz_runs/${id}/advance`, { method: "POST", headers: modHeaders(), body: { direction } });
    await loadQuizRuns();
  } catch (e) { errorToast((e as Error).message); }
}
async function reveal(id: number, val: boolean): Promise<void> {
  try {
    await api(`/api/sessions/${CODE}/quiz_runs/${id}/reveal`, { method: "POST", headers: modHeaders(), body: { reveal: val } });
    await loadQuizRuns();
  } catch (e) { errorToast((e as Error).message); }
}
async function nextPhase(r: QuizRun): Promise<void> {
  if (!r.reveal_current) return reveal(r.id, true);
  if (r.current_question_idx + 1 < r.question_count) return advance(r.id, "next");
  return act(r.id, "close");
}
async function toggleLiveCounts(id: number, show: boolean): Promise<void> {
  try {
    await api(`/api/sessions/${CODE}/quiz_runs/${id}/live_counts`, { method: "POST", headers: modHeaders(), body: { show } });
    await loadQuizRuns();
    toast(show ? "Vote counts shown to audience" : "Vote counts hidden");
  } catch (e) { errorToast((e as Error).message); }
}
async function del(id: number): Promise<void> {
  if (!confirm("Delete this quiz run? Its responses are discarded and it leaves the session.")) return;
  try {
    await api(`/api/sessions/${CODE}/quiz_runs/${id}`, { method: "DELETE", headers: modHeaders() });
    await loadQuizRuns();
  } catch (e) { errorToast((e as Error).message); }
}

guardClick($<HTMLButtonElement>("#add-quiz-btn"), async () => {
  const quizId = parseInt($<HTMLSelectElement>("#quiz-select").value, 10);
  if (!quizId) { errorToast("Pick a quiz first."); return; }
  try {
    const r = await api<QuizRun>(`/api/sessions/${CODE}/quiz_runs`, {
      method: "POST", headers: modHeaders(), body: { quiz_id: quizId },
    });
    await loadQuizRuns();
    toast(`Queued v${r.version_no}`);
  } catch (e) { errorToast((e as Error).message); }
});

async function loadFeedback(): Promise<void> {
  try {
    const sum = await api<FeedbackSummary>(`/api/sessions/${CODE}/feedback/summary`, { headers: modHeaders() });
    renderFeedback(sum);
  } catch { /* non-fatal */ }
}
function renderFeedback(sum: FeedbackSummary): void {
  const head = $("#feedback-summary"); head.innerHTML = "";
  const root = $("#feedback-list"); root.innerHTML = "";
  if (!sum || !sum.count) {
    root.appendChild(el("div", { class: "muted small" }, "No feedback yet."));
    return;
  }
  head.appendChild(el("span", { class: "fb-avg" }, `★ ${sum.average}`));
  head.appendChild(el("span", { class: "small muted" }, ` · ${sum.count} response(s)`));
  for (const it of sum.items) {
    const stars = "★".repeat(it.rating) + "☆".repeat(5 - it.rating);
    root.appendChild(el("div", { class: "fb-item" },
      el("div", {},
        el("span", { class: "fb-stars-static" }, stars),
        it.author_name ? el("span", { class: "small muted" }, "  — " + it.author_name) : null),
      it.went_well ? el("div", { class: "small" }, el("strong", {}, "Went well: "), it.went_well) : null,
      it.to_improve ? el("div", { class: "small" }, el("strong", {}, "Improve: "), it.to_improve) : null,
    ));
  }
}

function refresh(): void { void loadSession(); void loadQueries(); void loadQuizRuns(); void loadPresence(); void loadFeedback(); }
let refreshTimer: ReturnType<typeof setTimeout> | null = null;
function refreshSoon(_msg: LiveMessage): void {
  if (refreshTimer) return;
  refreshTimer = setTimeout(() => { refreshTimer = null; refresh(); }, 400);
}

async function boot(): Promise<void> {
  try {
    const st = await api<AdminStatus>("/api/admin/status");
    isOwner = !!(st && st.authenticated);
  } catch { isOwner = false; }
  await loadSession();
  $<HTMLDetailsElement>("#setup-section").open = sessionState?.status === "planning";
  await loadQuizzes();
  refresh();
  openLiveSocket(CODE, refreshSoon);
  if (presenceTimer) clearInterval(presenceTimer);
  presenceTimer = setInterval(() => void loadPresence(), 15000);
  showWorkSurfaces(true);
}

boot().catch(() => {
  showKeyGate();
  if (modKey()) errorToast("Couldn't load session — re-enter the moderator key.");
});
