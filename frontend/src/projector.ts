import { $, api, el, openLiveSocket, pathCode, renderQR } from "./common";
import type { Query, QuizRun, Session } from "./types";

const CODE = pathCode();
$("#code").textContent = CODE;

let lastQrUrl: string | null = null;
let latestLoadSeq = 0;

async function loadAll(): Promise<void> {
  const seq = ++latestLoadSeq;
  const [s, qs, runs] = await Promise.all([
    api<Session>(`/api/sessions/${CODE}`),
    api<Query[]>(`/api/sessions/${CODE}/queries`),
    api<QuizRun[]>(`/api/sessions/${CODE}/quiz_runs`),
  ]);
  if (seq !== latestLoadSeq) return;
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
  else $("#quiz-section").style.display = "none";
}

function renderLobby(run: QuizRun): void {
  const section = $("#quiz-section");
  const body = $("#quiz-body");
  section.style.display = "";
  body.innerHTML = "";
  body.appendChild(el("div", { class: "muted" }, "Next up:"));
  body.appendChild(el("h2", { style: "font-size: 40px; margin: 8px 0 24px;" }, run.quiz_title));
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

function renderQuiz(run: QuizRun): void {
  const section = $("#quiz-section");
  const body = $("#quiz-body");
  section.style.display = "";
  body.innerHTML = "";
  body.appendChild(el("div", { class: "muted" }, `${run.quiz_title} — question ${run.current_question_idx + 1}/${run.question_count}`));
  const q = run.current_question;
  if (!q) return;
  body.appendChild(el("h2", { style: "font-size: 32px; margin: 12px 0;" }, q.text));
  if (q.image_url) body.appendChild(el("img", { class: "q-image", src: q.image_url }));
  const totals = run.results?.totals ?? {};
  const respondents = run.results?.respondents ?? 0;
  const showCounts = !!run.results;
  const showCorrect = run.reveal_current || run.status === "closed";
  for (const a of q.answers) {
    const aDiv = el("div", { class: "option disabled" + (showCorrect && a.is_correct ? " correct" : "") });
    if (showCounts) {
      const bar = el("div", { class: "bar" });
      bar.style.transform = `scaleX(${respondents ? (totals[a.id] || 0) / respondents : 0})`;
      aDiv.appendChild(bar);
    }
    if (a.image_url) aDiv.appendChild(el("img", { class: "opt-img", src: a.image_url }));
    aDiv.appendChild(el("div", { class: "opt-text" }, a.text));
    if (showCounts) {
      const pct = respondents ? Math.round((totals[a.id] || 0) / respondents * 100) : 0;
      aDiv.appendChild(el("div", { class: "opt-pct" }, `${totals[a.id] || 0} (${pct}%)`));
    }
    body.appendChild(aDiv);
  }
  if (showCounts) body.appendChild(el("div", { class: "muted" }, `${respondents} respondent(s)`));
}

// Coalesce WS-driven reloads: a live quiz emits a broadcast per participant
// answer, and the projector is in that room — debounce.
let reloadTimer: ReturnType<typeof setTimeout> | null = null;
function loadAllSoon(): void {
  if (reloadTimer) return;
  reloadTimer = setTimeout(() => { reloadTimer = null; void loadAll(); }, 400);
}

void loadAll();
openLiveSocket(CODE, loadAllSoon);
