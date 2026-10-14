import { $, answerOption, api, askConfirm, bindMenuDismiss, el, errorToast, exportMenu, guardClick, markUsable, modHeaders, modKey, openLiveSocket, pathCode, publicBase, renderQR, setModKey, setVisible, showSessionDeleted, statusLabel, toast, type LiveMessage } from "./common";
import type {
  FeedbackSummary,
  ModeratorBootstrap,
  ParticipantProfile,
  ParticipantProfileSummary,
  Query,
  QuizRun,
  QuizSummary,
  Session,
  SessionRow,
} from "./types";

const CODE = pathCode();
$("#session-crumb").textContent = "Session " + CODE;

// Pick up mod_key from URL hash on first visit.
if (location.hash.includes("k=")) {
  const k = new URLSearchParams(location.hash.slice(1)).get("k");
  if (k) { setModKey(k); history.replaceState(null, "", location.pathname); }
}
// A moderator link pasted into this tab changes only the part after "#",
// which doesn't reload the page; reload so the key above is read (UC-M-01).
// Section links (#quizzes-card and so on) stay ordinary jumps.
window.addEventListener("hashchange", () => {
  if (new URLSearchParams(location.hash.slice(1)).get("k")) location.reload();
});

let queries: Query[] = [];
let quizRuns: QuizRun[] = [];
let quizzes: QuizSummary[] = [];
let sessionState: Session | null = null;
let presenceTimer: ReturnType<typeof setInterval> | null = null;
let isOwner = false;
const pendingResponseText = new Map<number, string>();
let latestSessionSeq = 0;
let latestQueriesSeq = 0;
let latestQuizRunsSeq = 0;
let latestPresenceSeq = 0;
let latestFeedbackSeq = 0;
let latestProfilesSeq = 0;

// Owner-only exports (UC-A-30): they include attendees' contact details, so
// delegates never see them.
const exportBase = `/api/sessions/${CODE}/export`;
const ownerExports = [
  exportMenu("session-export", exportBase, "Export all of this session's data, including attendees' contact details",
    "Export session ▾"),
  exportMenu("qna-export", `${exportBase}?part=qna`, "Export this session's questions"),
  exportMenu("profiles-export", `${exportBase}?part=profiles`, "Export attendee profiles"),
  exportMenu("feedback-export", `${exportBase}?part=feedback`, "Export feedback"),
];
for (const menu of ownerExports) setVisible(menu, false);
// The whole-session export sits beside the lifecycle buttons, outside
// #lifecycle-actions (rebuilt on every render), so it shows in every state.
$("#lifecycle-card .card-head").appendChild(ownerExports[0]);
$("#queries-tools").appendChild(ownerExports[1]);
$("#profiles-tools").appendChild(ownerExports[2]);
$("#feedback-tools").appendChild(ownerExports[3]);

function showWorkSurfaces(visible: boolean): void {
  for (const id of ["lifecycle-card", "setup-section", "quizzes-card", "queries-card", "profiles-card", "feedback-card"]) {
    setVisible($("#" + id), visible);
  }
  // Owner-only controls (UC-A-08); delegates never see them.
  setVisible($("#settings-card"), visible && isOwner);
  for (const menu of ownerExports) setVisible(menu, visible && isOwner);
}
function showKeyGate(): void {
  $("#modkey-code").textContent = CODE;
  // Show only what a visitor without access can use (UC-M-01): the session
  // by its code, without status, online count, view links, or Sessions.
  $("#title").textContent = "Session " + CODE;
  setVisible($("header.top .meta"), false);
  setVisible($("#moderator-breadcrumbs li:first-child"), false);
  setVisible($("#modkey-card"), true);
  showWorkSurfaces(false);
  $("#modkey-input").focus();
  markUsable("moderator");
}
async function trySubmitKey(): Promise<void> {
  const k = $<HTMLInputElement>("#modkey-input").value.trim();
  if (!k) return;
  setModKey(k);
  setVisible($("#modkey-card"), false);
  try { await boot(); } catch { showKeyGate(); errorToast("Wrong key for this session."); }
}
$("#modkey-submit").addEventListener("click", () => void trySubmitKey());
$("#modkey-input").addEventListener("keydown", (e) => { if ((e as KeyboardEvent).key === "Enter") void trySubmitKey(); });

bindMenuDismiss();

async function loadSession(): Promise<void> {
  const seq = ++latestSessionSeq;
  const loaded = await api<Session>(`/api/sessions/${CODE}`);
  if (seq !== latestSessionSeq) return;
  applySession(loaded, seq);
}

function applySession(loaded: Session, seq = latestSessionSeq): void {
  sessionState = loaded;
  document.title = `${sessionState.title} — Prashna`;
  $("#title").textContent = sessionState.title;
  $("#code").textContent = "Code " + CODE;
  $("#session-crumb").textContent = sessionState.title;
  const titleInp = $<HTMLInputElement>("#set-title");
  if (document.activeElement !== titleInp) titleInp.value = sessionState.title;
  $<HTMLAnchorElement>("#participant-link").href = `/s/${CODE}`;
  $<HTMLAnchorElement>("#projector-link").href = `/p/${CODE}`;
  renderLifecycle();
  void renderInvite(seq);
}

function participantUrlFor(s: Session): string {
  return `${publicBase(s)}/s/${s.code}`;
}

async function renderInvite(seq = latestSessionSeq): Promise<void> {
  if (seq !== latestSessionSeq) return;
  if (!sessionState) return;
  const url = participantUrlFor(sessionState);
  $<HTMLInputElement>("#base-url").value = sessionState.participant_base_url || "";
  $("#invite-url").textContent = url;
  const baseField = $("#base-url").closest(".field") as HTMLElement | null;
  if (baseField) setVisible(baseField, isOwner);
  setVisible($("#base-url-help"), isOwner);
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

// ----- owner-only Session settings (UC-A-05, UC-A-07, UC-A-08) -----
async function saveTitle(): Promise<void> {
  const input = $<HTMLInputElement>("#set-title");
  if (!sessionState || input.value === sessionState.title) return;
  try {
    await api(`/api/sessions/${CODE}`, { method: "PATCH", body: { title: input.value } });
    await loadSession();
    toast("Title saved");
  } catch (e) {
    input.value = sessionState.title;
    errorToast((e as Error).message);
  }
}
$("#set-title").addEventListener("change", () => void saveTitle());
$("#set-share-mod").addEventListener("click", async () => {
  // Fetch the key on demand so it never sits in the DOM (CLAUDE.md).
  try {
    const rows = await api<SessionRow[]>("/api/sessions");
    const row = rows.find((r) => r.code === CODE);
    if (!row) throw new Error("Session not found");
    const base = sessionState ? publicBase(sessionState) : location.origin;
    await navigator.clipboard.writeText(`${base}/m/${CODE}#k=${row.mod_key}`);
    toast("Moderator URL copied — share with delegates only.");
  } catch {
    errorToast("Couldn't copy — load over HTTPS for clipboard access.");
  }
});
// Deletion stays one flow on the session list (typed-title confirm). A live
// session can't be deleted, so say so here instead of leaving the page.
$("#set-delete").addEventListener("click", () => {
  if (sessionState?.status === "live") { errorToast("End the session before deleting it."); return; }
  location.href = `/?delete=${encodeURIComponent(CODE)}`;
});

function renderLifecycle(): void {
  if (!sessionState) return;
  const status = sessionState.status;
  // Nothing can be queued once a session has ended (UX.md §16).
  setVisible($("#quiz-composer"), status !== "ended");
  setVisible($("#quiz-hint"), status !== "ended");
  $("#session-status").textContent = statusLabel(status);
  $("#session-status").className = "badge badge-" + status;
  const actions = $("#lifecycle-actions"); actions.innerHTML = "";
  const hint = $("#lifecycle-hint");
  const feedbackBtn = el("button", { class: "ghost small" },
    sessionState.feedback_enabled ? "Close feedback" : "Open feedback");
  feedbackBtn.addEventListener("click", () => {
    void setFeedbackEnabled(!sessionState?.feedback_enabled);
  });
  if (status === "planning") {
    hint.textContent = "Not started yet. Start it when the audience is ready.";
    const btn = el("button", { class: "primary small" }, "Start session");
    btn.addEventListener("click", () => void transition("start"));
    actions.appendChild(btn);
    actions.appendChild(feedbackBtn);
  } else if (status === "live") {
    hint.textContent = "Session is live. End it when you're done.";
    const btn = el("button", { class: "danger ghost small" }, "End session");
    btn.addEventListener("click", async () => {
      const ok = await askConfirm({
        title: "End the session?",
        detail: "Participants can no longer ask questions.",
        confirmLabel: "End session",
        danger: true,
      });
      if (ok) void transition("end");
    });
    actions.appendChild(btn);
    actions.appendChild(feedbackBtn);
  } else {
    hint.textContent = "Session has ended. Results are read-only.";
    actions.appendChild(feedbackBtn);
  }
}

async function setFeedbackEnabled(enabled: boolean): Promise<void> {
  try {
    await api(`/api/sessions/${CODE}/feedback_enabled`, {
      method: "POST",
      headers: modHeaders(),
      body: { enabled },
    });
    await loadSession();
    toast(enabled ? "Feedback opened" : "Feedback closed");
  } catch (e) { errorToast((e as Error).message); }
}

async function transition(action: string): Promise<void> {
  try {
    await api(`/api/sessions/${CODE}/${action}`, { method: "POST", headers: modHeaders() });
    await loadSession();
    toast(`Session ${action}ed`);
  } catch (e) { errorToast((e as Error).message); }
}

async function loadPresence(): Promise<void> {
  const seq = ++latestPresenceSeq;
  try {
    const r = await api<{ online: number }>(`/api/sessions/${CODE}/presence`);
    if (seq !== latestPresenceSeq) return;
    $("#live-count").textContent = `${r.online} online`;
  } catch { /* presence is best-effort */ }
}

async function loadQueries(): Promise<void> {
  const seq = ++latestQueriesSeq;
  // display=true: a moderator tab is never a participant (UC-M-10).
  const rows = await api<Query[]>(`/api/sessions/${CODE}/queries?display=true`, { headers: modHeaders() });
  if (seq !== latestQueriesSeq) return;
  queries = rows;
  renderQueries();
}

function renderQueries(): void {
  const root = $("#queries");
  // A live redraw keeps the response box being typed in focused, with its
  // caret, so later keystrokes still land (UC-M-08).
  const active = document.activeElement;
  const editing = active instanceof HTMLTextAreaElement && root.contains(active)
    ? { id: active.dataset.queryId, start: active.selectionStart, end: active.selectionEnd, dir: active.selectionDirection }
    : null;
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
  const box = editing && root.querySelector<HTMLTextAreaElement>(`textarea[data-query-id="${editing.id}"]`);
  if (editing && box) {
    box.focus({ preventScroll: true });
    box.setSelectionRange(editing.start, editing.end, editing.dir);
  }
}

function renderQuery(q: Query): HTMLElement {
  const initial = pendingResponseText.has(q.id) ? pendingResponseText.get(q.id)! : (q.response_text || "");
  const respInput = el("textarea", {
    class: "response-input", rows: 1, "aria-label": "Response to this question",
    placeholder: "Type a response (optional)…", "data-query-id": q.id,
  }, initial) as HTMLTextAreaElement;
  respInput.addEventListener("input", () => pendingResponseText.set(q.id, respInput.value));
  // Secondary, not primary: there is one per row (UX.md §10).
  const respondBtn = el("button", { class: "small" }, q.responded ? "Update response" : "Mark responded");
  respondBtn.addEventListener("click", async () => {
    try {
      await api(`/api/sessions/${CODE}/queries/${q.id}/respond`, {
        method: "POST", headers: modHeaders(),
        body: { response_text: respInput.value.trim(), responded: true },
      });
      pendingResponseText.delete(q.id);
      loadQueries().catch(reportError);
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
      loadQueries().catch(reportError);
    } catch (e) { errorToast((e as Error).message); }
  });
  const removeBtn = el("button", { class: "danger ghost small" }, q.removed ? "Restore" : "Remove");
  removeBtn.addEventListener("click", async () => {
    try {
      await api(`/api/sessions/${CODE}/queries/${q.id}/remove`, {
        method: "POST", headers: modHeaders(), body: { removed: !q.removed },
      });
      loadQueries().catch(reportError);
    } catch (e) { errorToast((e as Error).message); }
  });
  const voteBox = el("div", { class: "vote-btn" + (q.voted ? " voted" : "") },
    el("div", { class: "count" }, String(q.vote_count)),
    el("div", { class: "label" }, "votes"));
  const body = el("div", { class: "body" },
    el("div", { class: "text" }, q.text),
    q.author_name ? el("div", { class: "small muted" }, "— " + q.author_name) : null,
    el("div", { class: "mt-2" }, respInput),
    // A removed question offers only Restore (UX.md §16).
    el("div", { class: "row mt-2" },
      q.removed ? null : respondBtn, q.removed ? null : reopenBtn, el("div", { class: "spacer" }), removeBtn),
  );
  return el("div", { class: "question" + (q.responded ? " answered" : "") + (q.removed ? " hidden-q" : "") }, voteBox, body);
}

function applyQuizzes(rows: QuizSummary[]): void {
  quizzes = rows;
  const sel = $<HTMLSelectElement>("#quiz-select");
  const previous = sel.value;
  sel.innerHTML = "";
  if (!quizzes.length) {
    sel.appendChild(el("option", { value: "" }, "No ready quizzes — publish one in the library"));
    return;
  }
  // A placeholder first, so a stray tap on + Add quiz can't queue the
  // wrong quiz (UC-M-03).
  sel.appendChild(el("option", { value: "" }, "Choose a quiz…"));
  for (const q of quizzes) {
    // Membership comes from the server (UC-M-03 in_session), the same
    // source as the quiz library's Add to session menu.
    const label = `${q.title} (${q.question_count} question${q.question_count === 1 ? "" : "s"})`
      + (q.status === "draft" ? " (draft)" : "")
      + (q.in_session ? ` — already added · ${statusLabel(q.in_session.run_status)}` : "")
      + (q.problem ? " — needs fixing in the quiz library" : "");
    // A Ready quiz an edit broke can't be added; show it, disabled, so a
    // delegate sees why instead of getting an error (UC-M-03).
    sel.appendChild(el("option", { value: q.id, disabled: Boolean(q.problem) }, label));
  }
  if (quizzes.some((q) => String(q.id) === previous)) sel.value = previous;
}

async function loadAvailableQuizzes(): Promise<void> {
  applyQuizzes(await api<QuizSummary[]>(`/api/sessions/${CODE}/available_quizzes`, { headers: modHeaders() }));
}

async function loadQuizRuns(): Promise<void> {
  const seq = ++latestQuizRunsSeq;
  const rows = await api<QuizRun[]>(`/api/sessions/${CODE}/quiz_runs?display=true`, { headers: modHeaders() });
  if (seq !== latestQuizRunsSeq) return;
  quizRuns = rows;
  renderQuizRuns();
}

function renderQuizRuns(): void {
  const root = $("#quiz-runs");
  root.innerHTML = "";
  if (!quizRuns.length) {
    root.appendChild(el("div", { class: "muted small" }, "No quizzes added yet — pick one above and click + Add quiz."));
    return;
  }
  // Live first (the one being driven), then queued in play order, then
  // closed newest first (UC-M-04). Run ids grow with creation time.
  const rank: Record<string, number> = { live: 0, queued: 1, closed: 2 };
  const sorted = [...quizRuns].sort((a, b) =>
    (rank[a.status] ?? 3) - (rank[b.status] ?? 3)
    || (a.status === "closed" ? b.id - a.id : a.id - b.id));
  for (const r of sorted) root.appendChild(renderQuizRun(r));
}

function renderQuizRun(r: QuizRun): HTMLElement {
  const sessionEnded = sessionState?.status === "ended";
  const tag = el("span", { class: "badge badge-" + r.status }, statusLabel(r.status));
  const progress = r.status === "queued"
    ? ` · ${r.question_count} question${r.question_count === 1 ? "" : "s"}`
    : ` · q ${r.current_question_idx + 1}/${r.question_count}`;
  const head = el("div", { class: "row run-head" },
    el("strong", {}, r.quiz_title),
    el("span", { class: "small muted" }, ` v${r.version_no}`),
    tag,
    el("span", { class: "small muted" }, progress),
    el("div", { class: "spacer" }),
  );
  if (r.status === "live" && r.reveal_current) {
    head.insertBefore(
      el("span", { class: "small" }, "voting closed"),
      head.querySelector(".spacer"));
  }
  if (r.status === "queued" && !sessionEnded) {
    head.appendChild(actBtn("primary", "Start", () => act(r.id, "start")));
  }
  if (r.status === "live" && !sessionEnded) {
    const phase = r.reveal_current ? "results" : "answering";
    const nextLabel = phase === "answering"
      ? "Reveal results →"
      : (r.current_question_idx + 1 < r.question_count ? "Next question →" : "Finish quiz →");
    head.appendChild(actBtn("primary", nextLabel, () => nextPhase(r)));
    head.appendChild(actBtn("ghost", "← Prev", () => advance(r.id, "prev")));
  }
  const menu = buildRunMenu(r);
  if (menu) head.appendChild(menu);
  // A queued run shows no answers: nothing to tally yet, and the correct
  // answer stays hidden until the run starts (UC-M-04).
  const cur = r.status === "queued" ? null : r.current_question;
  const totals = r.results?.totals ?? {};
  const respondents = r.results?.respondents ?? 0;
  const detail = el("div");
  if (cur) {
    detail.appendChild(el("div", {}, el("strong", {}, cur.text)));
    if (cur.image_url) detail.appendChild(el("img", { class: "q-image", src: cur.image_url }));
    for (const a of cur.answers) {
      // The moderator always sees which answer is correct.
      detail.appendChild(answerOption({
        text: a.text,
        imageUrl: a.image_url,
        share: respondents ? (totals[a.id] || 0) / respondents : 0,
        count: totals[a.id] || 0,
        correct: Boolean(a.is_correct),
      }));
    }
    detail.appendChild(el("div", { class: "small muted" }, `${respondents} respondent(s)`));
  }
  // Full per-question results live in the admin-only quiz library (UC-M-06).
  if (r.status === "closed" && isOwner) {
    detail.appendChild(el("a", { class: "small", href: `/quizzes?run=${r.id}` }, "View results →"));
  }
  return el("section", { class: "card inset" }, head, detail);
}

function buildRunMenu(r: QuizRun): HTMLElement | null {
  if (r.status === "closed") return null;
  const sessionEnded = sessionState?.status === "ended";
  if (sessionEnded && r.status !== "queued") return null;
  const panel = el("div", { class: "menu-panel" });
  const onFinishStep = r.status === "live" && r.reveal_current && r.current_question_idx + 1 >= r.question_count;
  if (!sessionEnded && r.status === "live" && !onFinishStep) {
    panel.appendChild(actBtn("ghost", "Finish quiz", () => act(r.id, "close")));
  }
  if (!sessionEnded && r.status === "live" && r.reveal_current) {
    panel.appendChild(actBtn("ghost", "Reopen voting", () => reveal(r.id, false)));
  }
  if (!sessionEnded) {
    const countsLabel = r.show_live_counts ? "Hide vote counts from audience" : "Show vote counts to audience";
    panel.appendChild(actBtn("ghost", countsLabel, () => toggleLiveCounts(r.id, !r.show_live_counts)));
  }
  const delLabel = r.status === "queued" ? "Remove from session" : "Delete run (discard results)";
  const del_ = actBtn("danger ghost", delLabel, () => del(r.id, r.status));
  del_.setAttribute("aria-label", r.status === "queued"
    ? "Remove this queued quiz from the session"
    : "Delete this quiz run");
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
async function del(id: number, status: string): Promise<void> {
  // A queued run has no responses and adding the quiz again undoes its
  // removal, so only deleting a live run asks first (UX.md §14).
  if (status !== "queued" && !await askConfirm({
    title: "Delete this quiz run?",
    detail: "Its responses are discarded and it leaves the session.",
    confirmLabel: "Delete run",
    danger: true,
  })) return;
  try {
    await api(`/api/sessions/${CODE}/quiz_runs/${id}`, { method: "DELETE", headers: modHeaders() });
    await loadQuizRuns();
  } catch (e) { errorToast((e as Error).message); }
}

guardClick($<HTMLButtonElement>("#add-quiz-btn"), async () => {
  const quizId = parseInt($<HTMLSelectElement>("#quiz-select").value, 10);
  if (!quizId) { errorToast("Pick a quiz first."); return; }
  // A draft is published and queued in one step (UC-M-03); the server
  // runs the publish checks and refuses delegates.
  const quiz = quizzes.find((q) => q.id === quizId);
  const isDraft = quiz?.status === "draft";
  // Repeating a quiz in a session is allowed but usually a mistake.
  if (quiz?.in_session && !await askConfirm({
    title: "Add this quiz again?",
    detail: `"${quiz.title}" is already in this session.`,
    confirmLabel: "Add again",
  })) return;
  try {
    const r = await api<QuizRun>(`/api/sessions/${CODE}/quiz_runs`, {
      method: "POST", headers: modHeaders(), body: { quiz_id: quizId, publish: isDraft },
    });
    await loadQuizRuns();
    loadAvailableQuizzes().catch(reportError);
    toast(isDraft ? `Published and queued v${r.version_no}` : `Queued v${r.version_no}`);
  } catch (e) { errorToast((e as Error).message); }
});

async function loadFeedback(): Promise<void> {
  const seq = ++latestFeedbackSeq;
  try {
    const sum = await api<FeedbackSummary>(`/api/sessions/${CODE}/feedback/summary`, { headers: modHeaders() });
    if (seq !== latestFeedbackSeq) return;
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
      el("div", {}, el("span", { class: "fb-stars-static" }, stars)),
      it.went_well ? el("div", { class: "small" }, el("strong", {}, "Went well: "), it.went_well) : null,
      it.to_improve ? el("div", { class: "small" }, el("strong", {}, "Improve: "), it.to_improve) : null,
    ));
  }
}

async function loadProfiles(): Promise<void> {
  const seq = ++latestProfilesSeq;
  try {
    const sum = await api<ParticipantProfileSummary>(`/api/sessions/${CODE}/participants`, { headers: modHeaders() });
    if (seq !== latestProfilesSeq) return;
    renderProfiles(sum);
  } catch { /* non-fatal */ }
}

function profileLine(label: string, value: string | null): HTMLElement | null {
  if (!value) return null;
  return el("div", { class: "small" }, el("strong", {}, label + ": "), value);
}

function renderProfile(item: ParticipantProfile): HTMLElement {
  const name = item.name || "Anonymous attendee";
  // A link only for web addresses; any other value is shown as text (UC-M-13).
  const linkedinIsWeb = /^https?:\/\//i.test(item.linkedin_url || "");
  const linkedin = item.linkedin_url
    ? el("div", { class: "small" }, el("strong", {}, "LinkedIn: "), linkedinIsWeb
      ? el("a", { href: item.linkedin_url, target: "_blank", rel: "noopener noreferrer" }, item.linkedin_url)
      : item.linkedin_url)
    : null;
  const photo = item.photo_url
    ? el("img", {
      class: "profile-photo-preview",
      src: item.photo_url,
      alt: name,
    })
    : null;
  return el("div", { class: "fb-item" },
    el("div", { class: "profile-photo-row" }, photo, el("strong", {}, name)),
    profileLine("Email", item.email),
    profileLine("Contact", item.contact_number),
    profileLine("Organization", item.organization),
    profileLine("Role", item.role),
    linkedin,
    profileLine("Working on", item.current_work),
    profileLine("Goal", item.learning_goal),
  );
}

function renderProfiles(sum: ParticipantProfileSummary): void {
  const head = $("#profiles-summary"); head.innerHTML = "";
  const root = $("#profiles-list"); root.innerHTML = "";
  if (!sum || !sum.count) {
    root.appendChild(el("div", { class: "muted small" }, "No attendee profiles yet."));
    return;
  }
  head.appendChild(el("span", { class: "small muted" }, `${sum.count} profile${sum.count === 1 ? "" : "s"}`));
  for (const item of sum.items) root.appendChild(renderProfile(item));
}

// A refetch a live update triggers is never silent when it fails (UX.md §8).
function reportError(error: unknown): void { errorToast((error as Error).message); }

function refreshAll(): void {
  loadSession().catch(reportError);
  loadQueries().catch(reportError);
  loadQuizRuns().catch(reportError);
  void loadPresence();
  void loadProfiles();
  void loadFeedback();
}
let refreshTimer: ReturnType<typeof setTimeout> | null = null;
const pendingLiveTypes = new Set<string>();
function refreshSoon(msg: LiveMessage): void {
  if (msg.type === "session_deleted") {
    // Final (UC-X-01): stop every refresh and show the deleted state.
    if (refreshTimer) clearTimeout(refreshTimer);
    if (presenceTimer) clearInterval(presenceTimer);
    refreshTimer = presenceTimer = null;
    showSessionDeleted();
    return;
  }
  pendingLiveTypes.add(msg.type);
  if (refreshTimer) return;
  refreshTimer = setTimeout(() => {
    refreshTimer = null;
    const types = new Set(pendingLiveTypes);
    pendingLiveTypes.clear();
    if (types.has("reconnect")) { refreshAll(); return; }
    const knownTypes = new Set([
      "session_state", "feedback_state", "query_new", "query_vote",
      "query_responded", "query_removed", "query_deleted", "quiz_run_new",
      "quiz_run_update", "quiz_run_deleted", "quiz_submission", "feedback",
      "participant",
    ]);
    if ([...types].some((type) => !knownTypes.has(type))) { refreshAll(); return; }
    if (["session_state", "feedback_state"].some((type) => types.has(type))) loadSession().catch(reportError);
    if (["query_new", "query_vote", "query_responded", "query_removed", "query_deleted"].some((type) => types.has(type))) loadQueries().catch(reportError);
    if (["quiz_run_new", "quiz_run_update", "quiz_run_deleted", "quiz_submission"].some((type) => types.has(type))) loadQuizRuns().catch(reportError);
    // The picker's "already added" labels follow runs being added, started,
    // closed, or removed.
    if (["quiz_run_new", "quiz_run_update", "quiz_run_deleted"].some((type) => types.has(type))) loadAvailableQuizzes().catch(reportError);
    if (["feedback", "feedback_state"].some((type) => types.has(type))) void loadFeedback();
    if (types.has("participant")) { void loadPresence(); void loadProfiles(); }
  }, 400);
}

async function boot(): Promise<void> {
  const state = await api<ModeratorBootstrap>(`/api/sessions/${CODE}/moderator-bootstrap`, { headers: modHeaders() });
  isOwner = state.is_owner;
  // The Sessions list is the admin's page; a delegate cannot use it.
  setVisible($("#moderator-breadcrumbs li:first-child"), isOwner);
  setVisible($("header.top .meta"), true);
  applySession(state.session);
  applyQuizzes(state.available_quizzes);
  $<HTMLDetailsElement>("#setup-section").open = sessionState?.status === "planning";
  showWorkSurfaces(true);
  markUsable("moderator");
  loadQueries().catch(reportError);
  loadQuizRuns().catch(reportError);
  void loadPresence();
  // Profiles and feedback are below the operational controls. Load them in
  // parallel without delaying the usable moderator surface.
  void loadProfiles();
  void loadFeedback();
  openLiveSocket(CODE, refreshSoon);
  if (presenceTimer) clearInterval(presenceTimer);
  presenceTimer = setInterval(() => void loadPresence(), 15000);
}

boot().catch(() => {
  showKeyGate();
  if (modKey()) errorToast("Couldn't load session — re-enter the moderator key.");
});
