import { $, answerOption, api, el, markUsable, openLiveSocket, pathCode, publicBase, renderQR, setVisible, showSessionDeleted } from "./common";
import type { DisplayBootstrap, Query, QuizRun } from "./types";

const CODE = pathCode();
$("#code").textContent = CODE;

let lastQrUrl: string | null = null;
let latestLoadSeq = 0;
// While a quiz run is live the projector also refetches every 5 s, so votes
// and question changes show even if live updates stop arriving (UC-D-05).
let quizIsLive = false;
let sessionDeleted = false;
setInterval(() => {
  if (quizIsLive && !sessionDeleted) void loadAll().catch(() => { /* next tick retries */ });
}, 5000);

async function loadAll(): Promise<void> {
  const seq = ++latestLoadSeq;
  const state = await api<DisplayBootstrap>(`/api/sessions/${CODE}/display-bootstrap`);
  if (seq !== latestLoadSeq) return;
  const { session: s, queries: qs, quiz_runs: runs } = state;
  document.title = `${s.title} · Projector — Prashna`;
  $("#title").textContent = s.title;
  const base = publicBase(s);
  const url = `${base}/s/${s.code}`;
  $("#origin").textContent = base.replace(/^https?:\/\//, "");
  if (url !== lastQrUrl) {
    lastQrUrl = url;
    try { await renderQR($("#join-qr"), url, { cellSize: 5, margin: 2 }); }
    catch { /* QR is best-effort */ }
  }
  renderQueries(qs);
  // Display priority: live > queued (lobby) > closed > nothing.
  const live = runs.find((r) => r.status === "live");
  const queued = runs.find((r) => r.status === "queued");
  const closed = runs.find((r) => r.status === "closed");
  quizIsLive = Boolean(live);
  if (live) renderQuiz(live);
  else if (queued) renderLobby(queued);
  else if (closed) renderQuiz(closed);
  else setVisible($("#quiz-section"), false);
}

function renderLobby(run: QuizRun): void {
  const section = $("#quiz-section");
  const body = $("#quiz-body");
  setVisible(section, true);
  body.innerHTML = "";
  body.appendChild(el("div", { class: "muted" }, "Next up:"));
  body.appendChild(el("h2", { class: "proj-lobby-title" }, run.quiz_title));
  body.appendChild(el("div", { class: "muted" }, "Scan the code to join — the quiz starts soon."));
}

function renderQueries(qs: Query[]): void {
  const root = $("#queries");
  root.innerHTML = "";
  const top = qs.filter((q) => !q.responded).sort((a, b) => b.vote_count - a.vote_count).slice(0, 8);
  if (!top.length) {
    root.appendChild(el("div", { class: "muted" }, "Waiting for questions…"));
    return;
  }
  for (const q of top) {
    root.appendChild(el("div", { class: "question" },
      el("div", { class: "vote-btn" + (q.voted ? " voted" : "") },
        el("div", { class: "count" }, String(q.vote_count)),
        el("div", { class: "label" }, "votes")),
      el("div", { class: "body" },
        el("div", { class: "text" }, q.text),
        q.author_name ? el("div", { class: "small muted" }, "— " + q.author_name) : null),
    ));
  }
}

function placeholderOptionLabel(idx: number): string {
  if (idx < 26) return `Option ${String.fromCharCode(65 + idx)}`;
  return `Option ${idx + 1}`;
}

function renderQuiz(run: QuizRun): void {
  const section = $("#quiz-section");
  const body = $("#quiz-body");
  setVisible(section, true);
  body.innerHTML = "";
  body.appendChild(el("div", { class: "muted" }, `${run.quiz_title} — question ${run.current_question_idx + 1}/${run.question_count}`));
  const q = run.current_question;
  if (!q) return;
  body.appendChild(el("h2", { class: "proj-question" }, q.text));
  if (q.image_url) body.appendChild(el("img", { class: "q-image", src: q.image_url }));
  const totals = run.results?.totals ?? {};
  const respondents = run.results?.respondents ?? 0;
  const showCounts = !!run.results;
  const showCorrect = run.reveal_current || run.status === "closed";
  const masked = run.results?.masked_counts;
  if (masked) {
    // A graded question before reveal: how the votes spread, without saying
    // which answer leads (UC-D-08). The server sends no answer for each count.
    for (const [idx, count] of masked.entries()) {
      body.appendChild(answerOption({
        text: placeholderOptionLabel(idx), imageUrl: null,
        share: respondents ? count / respondents : 0, count, correct: false,
      }));
    }
  } else {
    for (const a of q.answers) {
      body.appendChild(answerOption({
        text: a.text,
        imageUrl: a.image_url,
        share: showCounts ? (respondents ? (totals[a.id] || 0) / respondents : 0) : undefined,
        count: showCounts ? totals[a.id] || 0 : undefined,
        correct: showCorrect && Boolean(a.is_correct),
      }));
    }
  }
  if (showCounts) body.appendChild(el("div", { class: "muted" }, `${respondents} respondent(s)`));
}

// Coalesce WS-driven reloads: a live quiz emits a broadcast per participant
// answer, and the projector is in that room — debounce.
let reloadTimer: ReturnType<typeof setTimeout> | null = null;
function loadAllSoon(msg: { type: string }): void {
  if (msg.type === "session_deleted") {
    // Final (UC-X-01): stop refreshing and show the deleted state.
    sessionDeleted = true;
    if (reloadTimer) clearTimeout(reloadTimer);
    showSessionDeleted();
    return;
  }
  if (msg.type === "feedback_state" || sessionDeleted) return;
  if (reloadTimer) return;
  reloadTimer = setTimeout(() => { reloadTimer = null; void loadAll(); }, 400);
}

(async function boot() {
  await loadAll();
  markUsable("projector");
})().catch(() => { /* The role route will retain its loading state. */ });
openLiveSocket(CODE, loadAllSoon);
