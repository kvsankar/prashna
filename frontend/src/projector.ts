import { $, answerOption, api, el, markUsable, openLiveSocket, pathCode, renderQR, setVisible } from "./common";
import type { DisplayBootstrap, Query, QuizRun } from "./types";

const CODE = pathCode();
$("#code").textContent = CODE;

let lastQrUrl: string | null = null;
let latestLoadSeq = 0;

async function loadAll(): Promise<void> {
  const seq = ++latestLoadSeq;
  const state = await api<DisplayBootstrap>(`/api/sessions/${CODE}/display-bootstrap`);
  if (seq !== latestLoadSeq) return;
  const { session: s, queries: qs, quiz_runs: runs } = state;
  $("#title").textContent = s.title;
  const base = (s.participant_base_url || location.origin).replace(/\/$/, "");
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
  body.appendChild(el("div", { class: "muted" }, "Scan to join — quiz starts when the moderator clicks Start."));
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

function hashString(input: string): number {
  let hash = 2166136261;
  for (let i = 0; i < input.length; i += 1) {
    hash ^= input.charCodeAt(i);
    hash = Math.imul(hash, 16777619);
  }
  return hash >>> 0;
}

function sameAnswerOrder(a: { id: number }[], b: { id: number }[]): boolean {
  return a.length === b.length && a.every((answer, idx) => answer.id === b[idx]?.id);
}

function jumbledAnswers<T extends { id: number }>(answers: T[], seed: string): T[] {
  const ordered = [...answers].sort((a, b) => {
    const byHash = hashString(`${seed}:${a.id}`) - hashString(`${seed}:${b.id}`);
    return byHash || a.id - b.id;
  });
  if (ordered.length > 1 && sameAnswerOrder(answers, ordered)) ordered.reverse();
  return ordered;
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
  const hideAnswerDetails = showCounts && !showCorrect && run.status === "live";
  const answers = hideAnswerDetails ? jumbledAnswers(q.answers, `${run.id}:${q.id}`) : q.answers;
  for (const [idx, a] of answers.entries()) {
    body.appendChild(answerOption({
      text: hideAnswerDetails ? placeholderOptionLabel(idx) : a.text,
      imageUrl: hideAnswerDetails ? null : a.image_url,
      share: showCounts ? (respondents ? (totals[a.id] || 0) / respondents : 0) : undefined,
      count: showCounts ? totals[a.id] || 0 : undefined,
      correct: showCorrect && Boolean(a.is_correct),
    }));
  }
  if (showCounts) body.appendChild(el("div", { class: "muted" }, `${respondents} respondent(s)`));
}

// Coalesce WS-driven reloads: a live quiz emits a broadcast per participant
// answer, and the projector is in that room — debounce.
let reloadTimer: ReturnType<typeof setTimeout> | null = null;
function loadAllSoon(msg: { type: string }): void {
  if (msg.type === "feedback_state") return;
  if (reloadTimer) return;
  reloadTimer = setTimeout(() => { reloadTimer = null; void loadAll(); }, 400);
}

(async function boot() {
  await loadAll();
  markUsable("projector");
})().catch(() => { /* The role route will retain its loading state. */ });
openLiveSocket(CODE, loadAllSoon);
