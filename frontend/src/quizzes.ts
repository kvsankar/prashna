import { $, api, bindMenuDismiss, el, errorToast, guardClick, markUsable, statusLabel, toast } from "./common";
import type {
  EditorAnswer, EditorQuestion, QuizEditor, QuizRun, QuizRunResults, QuizRunRow, QuizSummary, SessionRow,
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
      ? el("button", { class: "ghost xsmall", onclick: () => void unpublishQuiz(q.id) }, "Unpublish")
      : el("button", { class: "primary xsmall", onclick: () => void publishQuiz(q.id) }, "Publish");
    actions.appendChild(toggleBtn);
    actions.appendChild(addToSessionMenu(q));
    actions.appendChild(rowMoreMenu(q));
    tr.appendChild(actions);
    // Clicks on the row's controls (buttons, menus) don't open the editor.
    // Not stopPropagation: the document-level menu dismiss must still see them.
    tr.addEventListener("click", (ev) => {
      if ((ev.target as Element).closest("button, a, details")) return;
      void openQuizDetail(q.id);
    });
    tbody.appendChild(tr);
  }
}

function rowMoreMenu(q: QuizSummary): HTMLElement {
  const panel = el("div", { class: "menu-panel" },
    guardClick(
      el("button", { class: "ghost small", title: "Make an editable copy of this quiz" }, "Duplicate") as HTMLButtonElement,
      () => duplicateQuiz(q.id)),
    el("div", { class: "menu-sep" }),
    guardClick(
      el("button", { class: "danger ghost small" }, "Delete") as HTMLButtonElement,
      () => removeQuiz(q.id)),
  );
  return el("details", { class: "menu row-more" },
    el("summary", { "aria-label": "More actions", title: "More actions" }, "⋯"),
    panel);
}

// Sessions that can still take a quiz: live first, then not started; the
// API already orders newest first within each group (UC-A-29).
async function openSessions(): Promise<SessionRow[]> {
  const rows = await api<SessionRow[]>("/api/sessions");
  return [
    ...rows.filter((r) => r.status === "live"),
    ...rows.filter((r) => r.status === "planning"),
  ];
}

function addToSessionMenu(q: QuizSummary): HTMLElement {
  const panel = el("div", { class: "menu-panel session-picker" });
  const details = el("details", { class: "menu add-to-session" },
    el("summary", { title: "Queue this quiz in a session" }, "Add to session ▾"),
    panel) as HTMLDetailsElement;
  // Load on open so the list is current without a request per row.
  details.addEventListener("toggle", async () => {
    if (!details.open) return;
    panel.replaceChildren(el("div", { class: "muted small" }, "Loading…"));
    try {
      const sessions = await openSessions();
      panel.replaceChildren();
      if (!sessions.length) {
        panel.appendChild(el("div", { class: "muted small" },
          "No open sessions. ", el("a", { href: "/" }, "Create one →")));
        return;
      }
      for (const s of sessions) {
        panel.appendChild(guardClick(
          el("button", { class: "ghost small" },
            el("span", { class: "badge badge-" + s.status }, statusLabel(s.status)),
            " " + s.title + " ",
            el("code", { class: "small" }, s.code)) as HTMLButtonElement,
          () => addQuizToSession(q, s, details)));
      }
    } catch (e) {
      details.open = false;
      errorToast((e as Error).message);
    }
  });
  return details;
}

async function addQuizToSession(q: QuizSummary, s: SessionRow, menu: HTMLDetailsElement): Promise<void> {
  const isDraft = q.status !== "ready";
  try {
    // A draft is published and queued in one step; the server runs the
    // publish checks and nothing changes if they fail (UC-M-03).
    await api<QuizRun>(`/api/sessions/${s.code}/quiz_runs`, {
      method: "POST", body: { quiz_id: q.id, publish: isDraft },
    });
    menu.open = false;
    toast(isDraft ? `Published and added to "${s.title}"` : `Added to "${s.title}"`);
    void loadQuizzes();
    void loadQSessions();
  } catch (e) {
    menu.open = false;
    errorToast((e as Error).message);
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
    tbody.innerHTML = `<tr><td colspan="7" class="muted small">No quiz runs yet. Use <strong>Add to session</strong> on a quiz above, or <strong>+ Add quiz</strong> on a session page.</td></tr>`;
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

// Bring a newly opened detail card into view; on a phone it is otherwise
// off-screen below the list (UX.md §16a).
function revealCard(card: HTMLElement): void {
  card.scrollIntoView({ behavior: "smooth", block: "start" });
}

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

async function duplicateQuiz(id: number): Promise<void> {
  try {
    const q = await api<QuizSummary>(`/api/quizzes/${id}/duplicate`, { method: "POST" });
    await loadQuizzes();
    void openQuizDetail(q.id);
    toast("Quiz duplicated");
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
    const opening = editingId !== id;
    editing = await api<QuizEditor>(`/api/quizzes/${id}?include_correct=true`);
    editingId = id;
    showEditor(`Editing quiz: ${editing.title}`);
    renderEditor();
    // Re-renders after each edit keep the scroll position.
    if (opening) revealCard($("#editor-card"));
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

  const titleInp = el("input", { value: quiz.title, class: "inline", "aria-label": "Quiz title" }) as HTMLInputElement;
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

  const list = el("div", { id: "editor-questions" });
  quiz.questions.forEach((qq, idx) => list.appendChild(renderQuestion(qq, idx)));
  body.appendChild(list);

  body.appendChild(el("div", { class: "row gap", style: "margin-top: 10px;" },
    guardClick(el("button", { class: "primary small" }, "+ Add question") as HTMLButtonElement, addQuestion)));
}

function renderQuestion(qq: EditorQuestion, idx: number): HTMLElement {
  const quizId = editing!.id;
  const ids = editing!.questions.map((q) => q.id);
  const wrap = el("div", { class: "editor-q compact", "data-id": qq.id });
  const saveOrder = (order: number[]) => saveQuestionOrder(quizId, order);

  const textInp = el("textarea", { rows: 2, "aria-label": `Question ${idx + 1} text` }, qq.text) as HTMLTextAreaElement;
  textInp.addEventListener("change", () => void patchQuestion(qq.id, { text: textInp.value }));

  const typeSel = el("select", { class: "inline narrow", "aria-label": `Question ${idx + 1} type` }) as HTMLSelectElement;
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

  // Number by position so deletes leave no gaps (UC-A-28).
  const head = el("div", { class: "row gap question-head" },
    dragHandle(wrap, "question", saveOrder),
    el("strong", {}, `Q${idx + 1}`), typeSel, pollLabel, el("div", { class: "spacer" }),
    ...moveButtons(ids, idx, "question", saveOrder),
    guardClick(el("button", { class: "danger ghost xsmall" }, "Delete") as HTMLButtonElement, async () => {
      if (!confirm("Delete this question?")) return;
      await api(`/api/quiz_questions/${qq.id}`, { method: "DELETE" });
      void openQuizDetail(quizId);
    }));
  wrap.appendChild(head);
  wrap.appendChild(textInp);

  const imgRow = el("div", { class: "row gap small muted", style: "margin-top: 6px;" });
  if (qq.image_url) imgRow.appendChild(el("img", { src: qq.image_url, class: "thumb" }));
  imgRow.append(...imagePicker(Boolean(qq.image_url), `Question ${idx + 1} image`, async (file) => {
    const url = await uploadImage(file);
    if (url) { await patchQuestion(qq.id, { image_url: url }); void openQuizDetail(quizId); }
  }));
  if (qq.image_url) {
    imgRow.appendChild(el("button", { class: "ghost xsmall", onclick: async () => {
      await patchQuestion(qq.id, { image_url: null }); void openQuizDetail(quizId);
    } }, "Clear"));
  }
  wrap.appendChild(imgRow);

  const opts = el("div", { class: "options" });
  qq.answers.forEach((op, aIdx) => opts.appendChild(renderAnswer(qq, op, aIdx)));
  wrap.appendChild(opts);
  wrap.appendChild(guardClick(
    el("button", { class: "ghost xsmall", style: "margin-top: 4px;" }, "+ Answer") as HTMLButtonElement,
    async () => {
      await api(`/api/quiz_questions/${qq.id}/answers`, { method: "POST", body: { text: "New answer" } });
      void openQuizDetail(quizId);
    }));
  return wrap;
}

function renderAnswer(qq: EditorQuestion, op: EditorAnswer, idx: number): HTMLElement {
  const quizId = editing!.id;
  const ids = qq.answers.map((a) => a.id);
  const saveOrder = (order: number[]) => saveAnswerOrder(quizId, qq.id, order);
  const row = el("div", { class: "editor-opt", "data-id": op.id });
  row.appendChild(dragHandle(row, "answer", saveOrder));
  const txt = el("input", { type: "text", value: op.text, class: "inline", "aria-label": `Answer ${idx + 1} text` }) as HTMLInputElement;
  txt.addEventListener("change", () => void patchAnswer(op.id, { text: txt.value }));
  if (qq.graded) {
    const correctBox = el("input", { type: "checkbox", "aria-label": `Answer ${idx + 1} is correct` }) as HTMLInputElement;
    if (op.is_correct) correctBox.setAttribute("checked", "");
    correctBox.addEventListener("change", () => void patchAnswer(op.id, { is_correct: correctBox.checked }));
    row.appendChild(el("label", { class: "small", title: "Correct" }, correctBox));
  }
  row.appendChild(txt);
  if (op.image_url) row.appendChild(el("img", { src: op.image_url, class: "thumb-sm", alt: "" }));
  row.append(...imagePicker(Boolean(op.image_url), `Answer ${idx + 1} image`, async (file) => {
    const url = await uploadImage(file);
    if (url) { await patchAnswer(op.id, { image_url: url }); void openQuizDetail(quizId); }
  }));
  if (op.image_url) {
    row.appendChild(el("button", {
      class: "ghost xsmall", "aria-label": "Clear answer image",
      onclick: async () => { await patchAnswer(op.id, { image_url: null }); void openQuizDetail(quizId); },
    }, "Clear"));
  }
  for (const btn of moveButtons(ids, idx, "answer", saveOrder)) row.appendChild(btn);
  row.appendChild(guardClick(
    el("button", { class: "danger ghost xsmall", "aria-label": "Delete answer" }, "✕") as HTMLButtonElement,
    async () => {
      await api(`/api/quiz_answers/${op.id}`, { method: "DELETE" });
      void openQuizDetail(quizId);
    }));
  return row;
}

// ---------- reorder (UC-A-28, UX.md §7 Reorder) ----------

type SaveOrder = (ids: number[]) => Promise<void>;

async function saveQuestionOrder(quizId: number, ids: number[]): Promise<void> {
  try {
    await api(`/api/quizzes/${quizId}/question_order`, { method: "PUT", body: { question_ids: ids } });
  } catch (e) { errorToast((e as Error).message); }
  void openQuizDetail(quizId);
}

async function saveAnswerOrder(quizId: number, questionId: number, ids: number[]): Promise<void> {
  try {
    await api(`/api/quiz_questions/${questionId}/answer_order`, { method: "PUT", body: { answer_ids: ids } });
  } catch (e) { errorToast((e as Error).message); }
  void openQuizDetail(quizId);
}

function moveButtons(ids: number[], idx: number, noun: string, save: SaveOrder): HTMLButtonElement[] {
  const swapped = (from: number, to: number): number[] => {
    const next = [...ids];
    [next[from], next[to]] = [next[to], next[from]];
    return next;
  };
  const make = (label: string, glyph: string, target: number): HTMLButtonElement => {
    const btn = el("button", {
      class: "ghost xsmall move-btn", "aria-label": `Move ${noun} ${label}`, title: `Move ${noun} ${label}`,
    }, glyph) as HTMLButtonElement;
    if (target < 0 || target >= ids.length) {
      btn.disabled = true;
      return btn;
    }
    return guardClick(btn, () => save(swapped(idx, target)));
  };
  return [make("up", "↑", idx - 1), make("down", "↓", idx + 1)];
}

/** A handle that drags `item` among its siblings with pointer events (works
 *  with mouse and touch), then saves the new order of the siblings' ids. */
function dragHandle(item: HTMLElement, noun: string, save: SaveOrder): HTMLElement {
  const handle = el("button", {
    class: "ghost xsmall drag-handle", type: "button",
    "aria-label": `Drag to reorder ${noun}`, title: "Drag to reorder",
  }, "⠿");
  handle.addEventListener("pointerdown", (down: PointerEvent) => {
    const list = item.parentElement;
    if (down.button !== 0 || !list) return;
    down.preventDefault();
    // Listen on the document, not with pointer capture on the handle:
    // moving `item` in the DOM detaches the handle and drops capture.
    const order = () => [...list.children].map((c) => Number((c as HTMLElement).dataset.id));
    const before = order().join();
    item.classList.add("dragging");
    const move = (ev: PointerEvent): void => {
      if (ev.pointerId !== down.pointerId) return;
      const edge = 60;
      if (ev.clientY < edge) window.scrollBy(0, -16);
      else if (ev.clientY > window.innerHeight - edge) window.scrollBy(0, 16);
      const next = [...list.children].find((c) => {
        if (c === item) return false;
        const r = c.getBoundingClientRect();
        return ev.clientY < r.top + r.height / 2;
      });
      if (next) { if (next !== item.nextElementSibling) list.insertBefore(item, next); }
      else if (list.lastElementChild !== item) list.appendChild(item);
    };
    const end = (ev: PointerEvent): void => {
      if (ev.pointerId !== down.pointerId) return;
      document.removeEventListener("pointermove", move);
      document.removeEventListener("pointerup", end);
      document.removeEventListener("pointercancel", end);
      item.classList.remove("dragging");
      if (order().join() !== before) void save(order());
    };
    document.addEventListener("pointermove", move);
    document.addEventListener("pointerup", end);
    document.addEventListener("pointercancel", end);
  });
  return handle;
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
/** "Add image" / "Change image" button driving a hidden file input; the
 *  native file control's "No file chosen" text is noise in a dense editor. */
function imagePicker(hasImage: boolean, inputLabel: string, onFile: (file: File) => Promise<void>): HTMLElement[] {
  const input = el("input", { type: "file", accept: "image/*", hidden: true, "aria-label": inputLabel }) as HTMLInputElement;
  input.addEventListener("change", () => {
    const file = input.files?.[0];
    if (file) void onFile(file);
  });
  const button = el("button", { class: "ghost xsmall", type: "button", title: inputLabel },
    hasImage ? "Change image" : "Add image");
  button.addEventListener("click", () => input.click());
  return [button, input];
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
    const opening = resultsId !== id;
    const r = await api<QuizRunResults>(`/api/quiz_runs/${id}/results`);
    resultsId = id;
    showResults(`Quiz session: ${r.quiz_title} in ${r.session_code}`);
    renderResults(r);
    if (opening) revealCard($("#results-card"));
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

bindMenuDismiss();

// Escape closes whichever drill-down is open (results first, then editor),
// unless it just closed an open menu.
document.addEventListener("keydown", (e) => {
  if (e.key !== "Escape" || e.defaultPrevented) return;
  if ($("#results-card").style.display !== "none") { closeResults(); return; }
  if ($("#editor-card").style.display !== "none") closeEditor();
});

Promise.all([loadQuizzes(), loadQSessions()])
  .then(() => markUsable("quizzes"))
  .catch((error: unknown) => errorToast((error as Error).message));
