import { $, api, el, errorToast, guardClick, markUsable, statusLabel, toast } from "./common";
import type {
  EditorAnswer, EditorQuestion, QuizEditor, QuizRunResults, QuizRunRow, QuizSummary,
} from "./types";

let editing: QuizEditor | null = null;
let editingId: number | null = null;
let resultsId: number | null = null;
type RunView = "flat" | "quiz" | "version" | "session";
const RUN_VIEWS: RunView[] = ["flat", "quiz", "version", "session"];
const requestedRunView = new URLSearchParams(location.search).get("runs");
let runView: RunView = RUN_VIEWS.includes(requestedRunView as RunView)
  ? requestedRunView as RunView
  : "flat";
let quizRunRows: QuizRunRow[] = [];

// ---------- list loaders ----------

async function loadQuizzes(): Promise<void> {
  const quizzes = await api<QuizSummary[]>("/api/quizzes");
  const tbody = $("#quiz-rows");
  if (!quizzes.length) {
    tbody.innerHTML = `<tr><td colspan="4" class="muted small">No quizzes yet. Add one using the title field above.</td></tr>`;
    return;
  }
  tbody.innerHTML = "";
  for (const q of quizzes) {
    const isReady = q.status === "ready";
    const tr = el("tr", { class: "rowable" + (editingId === q.id ? " selected" : "") });
    tr.appendChild(el("td", {}, q.title));
    tr.appendChild(el("td", {},
      el("span", { class: "badge " + (isReady ? "badge-ready" : "badge-draft") }, isReady ? "Ready" : "Draft")));
    tr.appendChild(el("td", { class: "num muted" }, String(q.question_count)));
    const actions = el("td", { class: "actions" });
    const toggleBtn = isReady
      ? el("button", { class: "ghost xsmall", onclick: (ev: Event) => { ev.stopPropagation(); void unpublishQuiz(q.id); } }, "Unpublish")
      : el("button", { class: "primary xsmall", onclick: (ev: Event) => { ev.stopPropagation(); void publishQuiz(q.id); } }, "Publish");
    actions.appendChild(toggleBtn);
    actions.appendChild(guardClick(
      el("button", { class: "danger ghost xsmall" }, "Delete") as HTMLButtonElement,
      (ev) => { ev.stopPropagation(); return removeQuiz(q.id); }));
    tr.appendChild(actions);
    tr.addEventListener("click", () => void openQuizDetail(q.id));
    tbody.appendChild(tr);
  }
}

async function loadQSessions(): Promise<void> {
  quizRunRows = await api<QuizRunRow[]>("/api/quiz_runs");
  renderQSessions();
}

function renderRunRow(r: QuizRunRow): HTMLTableRowElement {
  const tr = el("tr", { class: "rowable" + (resultsId === r.id ? " selected" : "") }) as HTMLTableRowElement;
  tr.appendChild(el("td", {}, r.quiz_title));
  tr.appendChild(el("td", { class: "muted small" }, "v" + r.version_no));
  tr.appendChild(el("td", {},
    el("span", { class: "muted small" }, r.session_title + " "),
    el("code", { class: "small" }, r.session_code)));
  tr.appendChild(el("td", {}, el("span", { class: "badge badge-" + r.status }, statusLabel(r.status))));
  const progress = r.status === "queued" ? "—"
    : `${Math.min(r.current_question_idx + 1, r.question_count)}/${r.question_count}`;
  tr.appendChild(el("td", { class: "num muted" }, progress));
  tr.appendChild(el("td", { class: "num muted" }, String(r.respondent_count)));
  tr.appendChild(el("td", { class: "muted small" }, new Date(r.created_at).toLocaleString()));
  tr.addEventListener("click", () => void openQSDetail(r.id));
  return tr;
}

function renderRunTable(rows: QuizRunRow[], tbody?: HTMLTableSectionElement): HTMLTableElement {
  if (tbody) {
    tbody.innerHTML = "";
    for (const row of rows) tbody.appendChild(renderRunRow(row));
    return tbody.closest("table") as HTMLTableElement;
  }
  const table = el("table", { class: "ctable" }) as HTMLTableElement;
  table.appendChild(el("thead", {}, el("tr", {},
    el("th", {}, "Quiz"),
    el("th", {}, "Ver"),
    el("th", {}, "In session"),
    el("th", {}, "Status"),
    el("th", { class: "num" }, "Progress"),
    el("th", { class: "num" }, "Resp."),
    el("th", {}, "Created"),
  )));
  const body = document.createElement("tbody");
  for (const row of rows) body.appendChild(renderRunRow(row));
  table.appendChild(body);
  return table;
}

interface RunGroup {
  key: string;
  title: string;
  rows: QuizRunRow[];
}

function groupedRuns(view: Exclude<RunView, "flat">): RunGroup[] {
  const groups = new Map<string, RunGroup>();
  for (const row of quizRunRows) {
    let key: string;
    let title: string;
    if (view === "quiz") {
      key = String(row.quiz_id);
      title = row.quiz_title;
    } else if (view === "version") {
      key = `${row.quiz_id}:${row.version_no}`;
      title = `${row.quiz_title} · v${row.version_no}`;
    } else {
      key = row.session_code;
      title = `${row.session_title} · ${row.session_code}`;
    }
    const existing = groups.get(key);
    if (existing) existing.rows.push(row);
    else groups.set(key, { key, title, rows: [row] });
  }
  return [...groups.values()];
}

function renderQSessions(): void {
  const tbody = $("#qs-rows");
  const flat = $("#qs-flat");
  const grouped = $("#qs-groups");
  const summaries: Record<RunView, string> = {
    flat: "Each row is one playthrough of a quiz inside a session.",
    quiz: "Runs are grouped by reusable quiz, across versions and sessions.",
    version: "Runs are grouped by the immutable quiz version used for each playthrough.",
    session: "Runs are grouped by the session in which they were played.",
  };
  $("#qs-view-summary").textContent = summaries[runView];
  for (const button of document.querySelectorAll<HTMLButtonElement>("[data-run-view]")) {
    button.setAttribute("aria-pressed", String(button.dataset.runView === runView));
  }

  if (!quizRunRows.length) {
    flat.style.display = "";
    grouped.style.display = "none";
    tbody.innerHTML = `<tr><td colspan="7" class="muted small">No quiz runs yet. Open a session as moderator and click <strong>Add to session</strong> to queue one.</td></tr>`;
    return;
  }

  if (runView === "flat") {
    flat.style.display = "";
    grouped.style.display = "none";
    renderRunTable(quizRunRows, tbody as HTMLTableSectionElement);
    return;
  }

  flat.style.display = "none";
  grouped.style.display = "";
  grouped.innerHTML = "";
  for (const group of groupedRuns(runView)) {
    const details = el("details", { class: "run-group", open: true, "data-group-key": group.key }) as HTMLDetailsElement;
    details.appendChild(el("summary", {},
      el("span", { class: "run-group-title" }, group.title),
      el("span", { class: "run-group-meta" }, `${group.rows.length} run${group.rows.length === 1 ? "" : "s"}`),
    ));
    details.appendChild(el("div", { class: "table-scroll" }, renderRunTable(group.rows)));
    grouped.appendChild(details);
  }
}

function setRunView(view: RunView): void {
  runView = view;
  const url = new URL(location.href);
  if (view === "flat") url.searchParams.delete("runs");
  else url.searchParams.set("runs", view);
  history.replaceState({}, "", url);
  renderQSessions();
}

for (const button of document.querySelectorAll<HTMLButtonElement>("[data-run-view]")) {
  button.addEventListener("click", () => setRunView(button.dataset.runView as RunView));
}

// ---------- detail panes ----------

function showEditor(title: string): void {
  $("#editor-title").textContent = title;
  $("#editor-card").style.display = "";
  void loadQuizzes();
}
function closeEditor(): void {
  editingId = null;
  editing = null;
  $("#editor-card").style.display = "none";
  void loadQuizzes();
}
function showResults(title: string): void {
  $("#results-title").textContent = title;
  $("#results-card").style.display = "";
  void loadQSessions();
}
function closeResults(): void {
  resultsId = null;
  $("#results-card").style.display = "none";
  void loadQSessions();
}
$("#editor-close").addEventListener("click", closeEditor);
$("#results-close").addEventListener("click", closeResults);

// ---------- quiz CRUD ----------

async function createQuiz(): Promise<void> {
  const titleInp = $<HTMLInputElement>("#new-quiz-title");
  const title = titleInp.value.trim();
  if (!title) return;
  try {
    const q = await api<QuizSummary>("/api/quizzes", { method: "POST", body: { title } });
    titleInp.value = "";
    await loadQuizzes();
    void openQuizDetail(q.id);
  } catch (e) { errorToast((e as Error).message); }
}
guardClick($<HTMLButtonElement>("#create-quiz"), createQuiz);
$("#new-quiz-title").addEventListener("keydown", (e) => { if ((e as KeyboardEvent).key === "Enter") void createQuiz(); });

async function removeQuiz(id: number): Promise<void> {
  if (!confirm("Delete this quiz template?")) return;
  try {
    await api(`/api/quizzes/${id}`, { method: "DELETE" });
    if (editingId === id) closeEditor();
    void loadQuizzes();
    toast("Quiz deleted");
  } catch (e) { errorToast((e as Error).message); }
}

async function publishQuiz(id: number): Promise<void> {
  try {
    await api(`/api/quizzes/${id}/publish`, { method: "POST" });
    void loadQuizzes();
    toast("Quiz published");
    if (editingId === id) void openQuizDetail(id);
  } catch (e) { errorToast("Can't publish: " + (e as Error).message); }
}

async function unpublishQuiz(id: number): Promise<void> {
  try {
    await api(`/api/quizzes/${id}/unpublish`, { method: "POST" });
    void loadQuizzes();
    if (editingId === id) void openQuizDetail(id);
  } catch (e) { errorToast((e as Error).message); }
}

// ---------- quiz editor ----------

async function openQuizDetail(id: number): Promise<void> {
  try {
    editing = await api<QuizEditor>(`/api/quizzes/${id}?include_correct=true`);
    editingId = id;
    showEditor(`Editing quiz: ${editing.title}`);
    renderEditor();
  } catch (e) { errorToast((e as Error).message); }
}

function renderEditor(): void {
  const quiz = editing;
  if (!quiz) return;
  const body = $("#editor-body");
  body.innerHTML = "";
  const isReady = quiz.status === "ready";
  body.appendChild(el("div", { class: "row gap" },
    el("span", { class: "badge " + (isReady ? "badge-ready" : "badge-draft") }, isReady ? "Ready" : "Draft")));

  body.appendChild(el("div", { class: "small muted", style: "margin-bottom: 8px;" },
    "Edits are versioned at next Launch — they don't affect past runs."));

  const titleInp = el("input", { value: quiz.title, class: "inline" }) as HTMLInputElement;
  titleInp.addEventListener("change", async () => {
    const r = await api<{ status?: string }>(`/api/quizzes/${quiz.id}`, { method: "PATCH", body: { title: titleInp.value } });
    quiz.title = titleInp.value;
    if (r && r.status) quiz.status = r.status;
    void loadQuizzes();
    renderEditor();
    $("#editor-title").textContent = `Editing quiz: ${quiz.title}`;
  });
  body.appendChild(el("div", { class: "row gap field-row" },
    el("label", { class: "small muted" }, "Title"), titleInp));

  for (const it of quiz.questions) body.appendChild(renderQuestion(it));

  body.appendChild(el("div", { class: "row gap", style: "margin-top: 10px;" },
    guardClick(el("button", { class: "primary small" }, "+ Add question") as HTMLButtonElement, addQuestion)));
}

function renderQuestion(qq: EditorQuestion): HTMLElement {
  const quizId = editing!.id;
  const wrap = el("div", { class: "editor-q compact" });

  const textInp = el("textarea", { rows: 2 }, qq.text) as HTMLTextAreaElement;
  textInp.addEventListener("change", () => void patchQuestion(qq.id, { text: textInp.value }));

  const typeSel = el("select", { class: "inline narrow" }) as HTMLSelectElement;
  for (const t of ["single", "multi"]) {
    const o = el("option", { value: t }, t === "single" ? "Single" : "Multiple");
    if (qq.qtype === t) o.setAttribute("selected", "");
    typeSel.appendChild(o);
  }
  typeSel.addEventListener("change", () => void patchQuestion(qq.id, { qtype: typeSel.value }));

  const pollBox = el("input", { type: "checkbox" }) as HTMLInputElement;
  if (!qq.graded) pollBox.setAttribute("checked", "");
  pollBox.addEventListener("change", async () => {
    await patchQuestion(qq.id, { graded: !pollBox.checked });
    void openQuizDetail(quizId);
  });
  const pollLabel = el("label", {
    class: "poll-toggle small muted",
    title: "Poll — collect responses with no correct answer",
  }, pollBox, "Poll");

  const head = el("div", { class: "row gap question-head" },
    el("strong", {}, `Q${qq.order_index + 1}`), typeSel, pollLabel, el("div", { class: "spacer" }),
    guardClick(el("button", { class: "danger ghost xsmall" }, "Delete") as HTMLButtonElement, async () => {
      if (!confirm("Delete this question?")) return;
      await api(`/api/quiz_questions/${qq.id}`, { method: "DELETE" });
      void openQuizDetail(quizId);
    }));
  wrap.appendChild(head);
  wrap.appendChild(textInp);

  const imgRow = el("div", { class: "row gap small muted", style: "margin-top: 6px;" });
  if (qq.image_url) imgRow.appendChild(el("img", { src: qq.image_url, class: "thumb" }));
  const imgInp = el("input", { type: "file", accept: "image/*", class: "inline" }) as HTMLInputElement;
  imgInp.addEventListener("change", async () => {
    const file = imgInp.files?.[0];
    if (!file) return;
    const url = await uploadImage(file);
    if (url) { await patchQuestion(qq.id, { image_url: url }); void openQuizDetail(quizId); }
  });
  imgRow.appendChild(imgInp);
  if (qq.image_url) {
    imgRow.appendChild(el("button", { class: "ghost xsmall", onclick: async () => {
      await patchQuestion(qq.id, { image_url: null }); void openQuizDetail(quizId);
    } }, "Clear"));
  }
  wrap.appendChild(imgRow);

  const opts = el("div", { class: "options" });
  for (const op of qq.answers) opts.appendChild(renderAnswer(qq, op));
  wrap.appendChild(opts);
  wrap.appendChild(guardClick(
    el("button", { class: "ghost xsmall", style: "margin-top: 4px;" }, "+ Answer") as HTMLButtonElement,
    async () => {
      await api(`/api/quiz_questions/${qq.id}/answers`, { method: "POST", body: { text: "New answer" } });
      void openQuizDetail(quizId);
    }));
  return wrap;
}

function renderAnswer(qq: EditorQuestion, op: EditorAnswer): HTMLElement {
  const quizId = editing!.id;
  const row = el("div", { class: "editor-opt" });
  const txt = el("input", { type: "text", value: op.text, class: "inline" }) as HTMLInputElement;
  txt.addEventListener("change", () => void patchAnswer(op.id, { text: txt.value }));
  if (qq.graded) {
    const correctBox = el("input", { type: "checkbox" }) as HTMLInputElement;
    if (op.is_correct) correctBox.setAttribute("checked", "");
    correctBox.addEventListener("change", () => void patchAnswer(op.id, { is_correct: correctBox.checked }));
    row.appendChild(el("label", { class: "small", title: "Correct" }, correctBox));
  }
  row.appendChild(txt);
  if (op.image_url) row.appendChild(el("img", { src: op.image_url, class: "thumb-sm", alt: "" }));
  const imgInp = el("input", {
    type: "file", accept: "image/*", class: "inline",
    "aria-label": "Set answer image", style: "width: auto; max-width: 140px;",
  }) as HTMLInputElement;
  imgInp.addEventListener("change", async () => {
    const file = imgInp.files?.[0];
    if (!file) return;
    const url = await uploadImage(file);
    if (url) { await patchAnswer(op.id, { image_url: url }); void openQuizDetail(quizId); }
  });
  row.appendChild(imgInp);
  if (op.image_url) {
    row.appendChild(el("button", {
      class: "ghost xsmall", "aria-label": "Clear answer image",
      onclick: async () => { await patchAnswer(op.id, { image_url: null }); void openQuizDetail(quizId); },
    }, "Clear"));
  }
  row.appendChild(guardClick(
    el("button", { class: "danger ghost xsmall", "aria-label": "Delete answer" }, "✕") as HTMLButtonElement,
    async () => {
      await api(`/api/quiz_answers/${op.id}`, { method: "DELETE" });
      void openQuizDetail(quizId);
    }));
  return row;
}

async function patchQuestion(id: number, body: Record<string, unknown>): Promise<void> {
  try {
    await api(`/api/quiz_questions/${id}`, { method: "PATCH", body });
    void loadQuizzes();
  } catch (e) { errorToast((e as Error).message); }
}
async function patchAnswer(id: number, body: Record<string, unknown>): Promise<void> {
  try {
    await api(`/api/quiz_answers/${id}`, { method: "PATCH", body });
    void loadQuizzes();
  } catch (e) { errorToast((e as Error).message); }
}
async function addQuestion(): Promise<void> {
  if (!editing) return;
  try {
    await api(`/api/quizzes/${editing.id}/questions`, {
      method: "POST", body: { text: "New question", qtype: "single" },
    });
    void openQuizDetail(editing.id);
  } catch (e) { errorToast((e as Error).message); }
}
async function uploadImage(file: File): Promise<string | null> {
  const fd = new FormData();
  fd.append("file", file);
  const r = await fetch("/api/uploads", { method: "POST", body: fd, credentials: "same-origin" });
  if (!r.ok) { errorToast("Upload failed"); return null; }
  return (await r.json() as { url: string }).url;
}

// ---------- quiz run results ----------

async function openQSDetail(id: number): Promise<void> {
  try {
    const r = await api<QuizRunResults>(`/api/quiz_runs/${id}/results`);
    resultsId = id;
    showResults(`Quiz session: ${r.quiz_title} in ${r.session_code}`);
    renderResults(r);
  } catch (e) { errorToast((e as Error).message); }
}

function renderResults(r: QuizRunResults): void {
  const body = $("#results-body");
  body.innerHTML = "";
  body.appendChild(el("div", { class: "row gap" },
    el("span", { class: "badge badge-" + r.status }, statusLabel(r.status)),
    el("span", { class: "muted small" }, `${r.session_title} · `, el("code", { class: "small" }, r.session_code)),
    el("div", { class: "spacer" }),
    el("a", { href: `/m/${r.session_code}`, target: "_blank", class: "small" }, "Open moderator →")));

  if (!r.questions.length) {
    body.appendChild(el("div", { class: "muted small", style: "margin-top: 12px;" }, "Quiz has no questions."));
    return;
  }
  for (let i = 0; i < r.questions.length; i++) {
    const q = r.questions[i];
    const max = Math.max(1, q.respondents);
    const card = el("div", { class: "result-q" });
    card.appendChild(el("div", { class: "row gap" },
      el("strong", {}, `Q${i + 1}.`),
      el("span", {}, q.text),
      el("div", { class: "spacer" }),
      el("span", { class: "small muted" }, `${q.respondents} respondent${q.respondents === 1 ? "" : "s"}`)));
    if (q.image_url) card.appendChild(el("img", { src: q.image_url, class: "thumb", style: "margin-top: 6px;" }));
    for (const op of q.answers) {
      const pct = Math.round((op.count / max) * 100);
      const optRow = el("div", { class: "result-opt" + (op.is_correct ? " correct" : "") });
      const bar = el("div", { class: "result-bar" });
      bar.style.width = pct + "%";
      optRow.appendChild(bar);
      optRow.appendChild(el("span", { class: "result-mark" }, op.is_correct ? "✓" : ""));
      optRow.appendChild(el("span", { class: "result-text" }, op.text));
      optRow.appendChild(el("span", { class: "result-num" }, `${op.count} · ${pct}%`));
      card.appendChild(optRow);
    }
    body.appendChild(card);
  }
}

// Escape closes whichever drill-down is open (results first, then editor).
document.addEventListener("keydown", (e) => {
  if (e.key !== "Escape") return;
  if ($("#results-card").style.display !== "none") { closeResults(); return; }
  if ($("#editor-card").style.display !== "none") closeEditor();
});

Promise.all([loadQuizzes(), loadQSessions()])
  .then(() => markUsable("quizzes"))
  .catch((error: unknown) => errorToast((error as Error).message));
