import { $, answerOption, api, el, errorToast, guardClick, markUsable, modKey, openLiveSocket, pathCode, publicBase, renderQR, setVisible, showSessionDeleted, toast, type LiveMessage } from "./common";
import type { Feedback, ParticipantBootstrap, ParticipantProfile, Query, QuizRun, Session } from "./types";

const CODE = pathCode();
let queries: Query[] = [];
let activeQuiz: QuizRun | null = null;
let pendingSelection = new Set<number>();
let lastQuestionId: number | null = null;
let me: ParticipantProfile | null = null;
let latestSessionSeq = 0;
let latestQueriesSeq = 0;
let latestQuizSeq = 0;
let profileToastTimer: ReturnType<typeof setTimeout> | null = null;
let pendingPhotoPreviewUrl: string | null = null;
let profileSubmitted = false;

let sessionEnded = false;
let feedbackEnabled = false;
async function loadSession(): Promise<void> {
  const seq = ++latestSessionSeq;
  const s = await api<Session>(`/api/sessions/${CODE}`);
  if (seq !== latestSessionSeq) return;
  applySession(s);
}

function applySession(s: Session, refreshFeedback = true): void {
  document.title = `${s.title} · Participant view — Prashna`;
  $("#title").textContent = s.title;
  $("#code").textContent = "Code " + CODE;
  $("#participant-breadcrumb-session").textContent = s.title;
  const wasEnded = sessionEnded;
  sessionEnded = s.status === "ended";
  // Vote buttons become plain counts when the session ends (UC-P-11).
  if (wasEnded !== sessionEnded) renderQueries();
  const ratingOpened = s.feedback_enabled && !feedbackEnabled;
  feedbackEnabled = s.feedback_enabled;
  setVisible($("#ask-card"), !sessionEnded);
  setVisible($("#ended-card"), sessionEnded);
  setVisible($("#feedback-card"), feedbackEnabled);
  // Saved feedback loads only when rating opens; a rename, the end of the
  // session, or a reconnect must not touch a draft (UC-P-13).
  if (ratingOpened && refreshFeedback) void loadFeedback();
  void renderQR($("#share-qr"), `${publicBase(s)}/s/${s.code}`, { cellSize: 3, margin: 2 })
    .catch(() => { /* QR is best-effort */ });
}

function applyMe(profile: ParticipantProfile): void {
  me = profile;
  $<HTMLInputElement>("#my-name").value = me.name || "";
  $<HTMLInputElement>("#my-email").value = me.email || "";
  $<HTMLInputElement>("#my-contact-number").value = me.contact_number || "";
  $<HTMLInputElement>("#my-organization").value = me.organization || "";
  $<HTMLInputElement>("#my-role").value = me.role || "";
  $<HTMLInputElement>("#my-linkedin-url").value = me.linkedin_url || "";
  renderProfilePhoto(me.photo_url);
  $<HTMLTextAreaElement>("#my-current-work").value = me.current_work || "";
  $<HTMLTextAreaElement>("#my-learning-goal").value = me.learning_goal || "";
  profileSubmitted = profileHasValues(me);
  renderProfileAction();
}

function profileHasValues(profile: ParticipantProfile): boolean {
  return Boolean(
    profile.name
    || profile.email
    || profile.contact_number
    || profile.organization
    || profile.role
    || profile.linkedin_url
    || profile.photo_url
    || profile.current_work
    || profile.learning_goal
  );
}

function renderProfileAction(): void {
  $<HTMLButtonElement>("#profile-submit").textContent = profileSubmitted
    ? "Resubmit profile"
    : "Submit profile";
  $(".profile-title-closed").textContent = profileSubmitted
    ? "Your profile"
    : "Add your profile";
  $(".profile-cta-closed").textContent = profileSubmitted
    ? "Edit details"
    : "Add details";
}

function renderProfilePhoto(url: string | null): void {
  if (pendingPhotoPreviewUrl) URL.revokeObjectURL(pendingPhotoPreviewUrl);
  pendingPhotoPreviewUrl = null;
  const preview = $<HTMLImageElement>("#my-photo-preview");
  const clear = $<HTMLButtonElement>("#my-photo-clear");
  if (url) {
    preview.src = url;
    setVisible(preview, true);
    setVisible(clear, true);
  } else {
    preview.removeAttribute("src");
    setVisible(preview, false);
    setVisible(clear, false);
  }
}

function markProfileDirty(): void {
  $("#profile-status").textContent = "Unsaved changes";
}

function previewSelectedProfilePhoto(): void {
  const input = $<HTMLInputElement>("#my-photo");
  const file = input.files?.[0];
  if (!file) return;
  if (pendingPhotoPreviewUrl) URL.revokeObjectURL(pendingPhotoPreviewUrl);
  pendingPhotoPreviewUrl = URL.createObjectURL(file);
  const preview = $<HTMLImageElement>("#my-photo-preview");
  preview.src = pendingPhotoPreviewUrl;
  setVisible(preview, true);
  setVisible($<HTMLButtonElement>("#my-photo-clear"), true);
  markProfileDirty();
}

function currentProfile(): Omit<ParticipantProfile, "id" | "photo_url"> {
  return {
    name: $<HTMLInputElement>("#my-name").value,
    email: $<HTMLInputElement>("#my-email").value,
    contact_number: $<HTMLInputElement>("#my-contact-number").value,
    organization: $<HTMLInputElement>("#my-organization").value,
    role: $<HTMLInputElement>("#my-role").value,
    linkedin_url: $<HTMLInputElement>("#my-linkedin-url").value,
    current_work: $<HTMLTextAreaElement>("#my-current-work").value,
    learning_goal: $<HTMLTextAreaElement>("#my-learning-goal").value,
  };
}

async function saveProfile(): Promise<void> {
  $("#profile-status").textContent = "Saving...";
  try {
    me = await api<ParticipantProfile>(`/api/sessions/${CODE}/me`, { method: "PATCH", body: currentProfile() });
    const photoInput = $<HTMLInputElement>("#my-photo");
    if (photoInput.files?.[0]) me = await uploadSelectedProfilePhoto();
    renderProfilePhoto(me.photo_url);
    profileSubmitted = true;
    renderProfileAction();
    $("#profile-status").textContent = "Submitted";
    if (profileToastTimer) clearTimeout(profileToastTimer);
    profileToastTimer = setTimeout(() => {
      profileToastTimer = null;
      toast(me?.name ? `Profile submitted for "${me.name}"` : "Profile submitted");
    }, 250);
  } catch (e) {
    $("#profile-status").textContent = "Save failed";
    errorToast((e as Error).message);
  }
}

async function uploadSelectedProfilePhoto(): Promise<ParticipantProfile> {
  const input = $<HTMLInputElement>("#my-photo");
  const file = input.files?.[0];
  if (!file) {
    if (!me) throw new Error("Profile has not loaded yet.");
    return me;
  }
  const form = new FormData();
  form.append("file", file);
  const saved = await api<ParticipantProfile>(
    `/api/sessions/${CODE}/me/photo`,
    {
      method: "POST",
      body: form,
    },
  );
  input.value = "";
  return saved;
}

async function clearProfilePhoto(): Promise<void> {
  const input = $<HTMLInputElement>("#my-photo");
  if (input.files?.[0]) {
    input.value = "";
    renderProfilePhoto(me?.photo_url ?? null);
    markProfileDirty();
    return;
  }
  try {
    me = await api<ParticipantProfile>(`/api/sessions/${CODE}/me`, {
      method: "PATCH",
      body: { photo_url: null },
    });
    renderProfilePhoto(null);
    $("#profile-status").textContent = "Saved";
    toast("Photograph cleared");
  } catch (e) { errorToast((e as Error).message); }
}

for (const id of [
  "#my-name",
  "#my-email",
  "#my-contact-number",
  "#my-organization",
  "#my-role",
  "#my-linkedin-url",
  "#my-current-work",
  "#my-learning-goal",
]) {
  $(id).addEventListener("input", markProfileDirty);
}
$<HTMLInputElement>("#my-photo").addEventListener(
  "change",
  previewSelectedProfilePhoto,
);
$<HTMLButtonElement>("#my-photo-clear").addEventListener(
  "click",
  () => void clearProfilePhoto(),
);
// Guarded (UX.md §10): the photograph upload inside it is not idempotent.
guardClick($<HTMLButtonElement>("#profile-submit"), saveProfile);

async function loadQueries(): Promise<void> {
  const seq = ++latestQueriesSeq;
  const rows = await api<Query[]>(`/api/sessions/${CODE}/queries`);
  if (seq !== latestQueriesSeq) return;
  applyQueries(rows);
}

function applyQueries(rows: Query[]): void {
  queries = rows;
  renderQueries();
}

function renderQueries(): void {
  const root = $("#queries");
  root.innerHTML = "";
  if (!queries.length) {
    root.appendChild(el("div", { class: "muted small" },
      sessionEnded ? "No questions were asked." : "No questions yet. Be the first to ask."));
    return;
  }
  const sorted = [...queries].sort((a, b) => {
    if (a.responded !== b.responded) return a.responded ? 1 : -1;
    return b.vote_count - a.vote_count;
  });
  for (const q of sorted) root.appendChild(renderQuery(q));
}

function renderQuery(q: Query): HTMLElement {
  // Voting is closed once the session ends (UC-P-11): show the count as
  // text, not a button that would only answer "Session has ended".
  const voteBox = sessionEnded
    ? el("div", { class: "vote-btn" + (q.voted ? " voted" : ""), "aria-label": `${q.vote_count} votes` },
      el("div", { class: "arrow", "aria-hidden": "true" }, "▲"),
      el("div", { class: "count" }, String(q.vote_count)))
    : voteButton(q);
  // "Your question" shows only on the asker's own device (UC-P-06); the
  // question stays anonymous to everyone else.
  const meta = [
    q.author_name ? "— " + q.author_name : null,
    q.mine ? el("span", { class: "mine-marker" }, "Your question") : null,
  ].filter(Boolean) as (string | HTMLElement)[];
  const body = el("div", { class: "body" },
    el("div", { class: "text" }, q.text),
    meta.length ? el("div", { class: "small muted" }, meta.flatMap((m, i) => (i ? [" · ", m] : [m]))) : null,
    q.responded && q.response_text
      ? el("div", { class: "answer" }, el("strong", {}, "Response: "), q.response_text)
      : null,
  );
  return el("div", { class: "question" + (q.responded ? " answered" : "") }, voteBox, body);
}

function voteButton(q: Query): HTMLElement {
  // Guarded: a vote toggles, so a double tap would vote and un-vote (UC-P-05).
  return guardClick(el("button", {
    class: "vote-btn" + (q.voted ? " voted" : ""),
    "aria-pressed": String(!!q.voted),
    "aria-label": q.voted ? `Remove vote (currently ${q.vote_count})` : `Upvote (currently ${q.vote_count})`,
  },
    el("div", { class: "arrow", "aria-hidden": "true" }, "▲"),
    el("div", { class: "count" }, String(q.vote_count)),
  ) as HTMLButtonElement, () => toggleVote(q.id));
}

async function toggleVote(qid: number): Promise<void> {
  try { await api(`/api/sessions/${CODE}/queries/${qid}/vote`, { method: "POST" }); }
  catch (e) { errorToast((e as Error).message); }
  // Keep the button disabled until the list shows the new state.
  try { await loadQueries(); } catch { /* the next live update refreshes it */ }
}

// "Show my name" is a choice per question (UC-P-04): the box clears after
// each question, and the typed name is remembered on this device only. The
// profile name is never used (Anonymity).
const ASK_NAME_KEY = "prashna:ask-name";
const showNameBox = $<HTMLInputElement>("#ask-show-name");
const askName = $<HTMLInputElement>("#ask-name");
function syncAskName(): void {
  setVisible(askName, showNameBox.checked);
  if (showNameBox.checked && !askName.value) {
    try { askName.value = localStorage.getItem(ASK_NAME_KEY) ?? ""; } catch { /* storage blocked */ }
    askName.focus();
  }
}
showNameBox.addEventListener("change", syncAskName);

async function askQuery(): Promise<void> {
  const text = $<HTMLTextAreaElement>("#query-text").value.trim();
  if (!text) return;
  const name = showNameBox.checked ? askName.value.trim() : "";
  if (showNameBox.checked && !name) { toast("Type the name to show, or untick Show my name"); askName.focus(); return; }
  try {
    await api(`/api/sessions/${CODE}/queries`, {
      method: "POST",
      body: name ? { text, author_name: name } : { text },
    });
    if (name) { try { localStorage.setItem(ASK_NAME_KEY, name); } catch { /* storage blocked */ } }
    showNameBox.checked = false;
    syncAskName();
    $<HTMLTextAreaElement>("#query-text").value = "";
    loadQueries().catch(reportError);
    toast("Question submitted");
  } catch (e) { errorToast((e as Error).message); }
}
guardClick($<HTMLButtonElement>("#ask-btn"), askQuery);
// Mention the keyboard shortcut only where a keyboard is likely (UX.md §16a).
if (!matchMedia("(pointer: fine)").matches) {
  $<HTMLTextAreaElement>("#query-text").placeholder = "Type your question…";
}
$("#query-text").addEventListener("keydown", (e) => {
  const ke = e as KeyboardEvent;
  // Click, so #ask-btn's double-submit guard covers the shortcut too.
  if (ke.key === "Enter" && (ke.metaKey || ke.ctrlKey)) { ke.preventDefault(); $<HTMLButtonElement>("#ask-btn").click(); }
});

async function loadQuiz(): Promise<void> {
  const seq = ++latestQuizSeq;
  const rows = await api<QuizRun[]>(`/api/sessions/${CODE}/quiz_runs`);
  if (seq !== latestQuizSeq) return;
  applyQuizRuns(rows);
}

function applyQuizRuns(rows: QuizRun[]): void {
  activeQuiz = rows.find((r) => r.status === "live") ?? null;
  if (activeQuiz && activeQuiz.current_question && activeQuiz.current_question.id !== lastQuestionId) {
    pendingSelection = new Set(activeQuiz.my_selections ?? []);
    lastQuestionId = activeQuiz.current_question.id;
  } else if (!activeQuiz) {
    pendingSelection = new Set();
    lastQuestionId = null;
  }
  renderQuiz();
}

function renderQuiz(): void {
  const card = $("#quiz-card");
  const body = $("#quiz-body");
  // While a quiz is live it is the most urgent card, so it goes first;
  // otherwise it sits back after the rating card (UC-P-13 card order).
  if (!activeQuiz) {
    setVisible(card, false);
    if (card.previousElementSibling !== $("#feedback-card")) $("#feedback-card").after(card);
    return;
  }
  const main = card.parentElement;
  if (main && main.firstElementChild !== card) main.prepend(card);
  setVisible(card, true);
  body.innerHTML = "";
  const q = activeQuiz.current_question;
  body.appendChild(el("div", { class: "small muted" },
    `${activeQuiz.quiz_title} — question ${activeQuiz.current_question_idx + 1} of ${activeQuiz.question_count}`));
  if (!q) {
    body.appendChild(el("div", { class: "muted" }, "Waiting for moderator…"));
    return;
  }
  body.appendChild(el("h3", {}, q.text));
  if (q.image_url) body.appendChild(el("img", { class: "q-image", src: q.image_url }));
  const submitted = (activeQuiz.my_selections ?? []).length > 0;
  const totals = activeQuiz.results?.totals ?? null;
  const showCorrect = activeQuiz.reveal_current;
  const respondents = activeQuiz.results ? Math.max(activeQuiz.results.respondents, 1) : 1;
  const locked = showCorrect;
  for (const a of q.answers) {
    const selected = pendingSelection.has(a.id);
    body.appendChild(answerOption({
      text: a.text,
      imageUrl: a.image_url,
      share: totals ? (totals[a.id] || 0) / respondents : undefined,
      count: totals ? totals[a.id] || 0 : undefined,
      correct: showCorrect && a.is_correct === true,
      wrong: showCorrect && selected && a.is_correct === false,
      selected,
      // The choice is marked with a tick and words, not only a tint; after
      // reveal a wrong pick says so in words too (UC-P-08).
      chosenLabel: !locked ? "Selected" : (a.is_correct === false ? "Your answer · wrong" : "Your answer"),
      disabled: locked,
      onPick: () => {
        if (locked) return;
        if (q.qtype === "single") pendingSelection = new Set([a.id]);
        else if (pendingSelection.has(a.id)) pendingSelection.delete(a.id);
        else pendingSelection.add(a.id);
        renderQuiz();
      },
    }));
  }
  if (activeQuiz.results?.masked_counts) {
    // A graded question before reveal: how many answered, not the split (UC-P-12).
    body.appendChild(el("div", { id: "quiz-answered", class: "small muted mt-2" },
      `${activeQuiz.results.respondents} answered so far`));
  } else if (activeQuiz.results) {
    body.appendChild(el("div", { class: "small muted mt-2" },
      `${activeQuiz.results.respondents} respondent(s)`));
  }
  if (!locked) {
    const submitBtn = guardClick(
      el("button", { class: "primary" }, submitted ? "Update answer" : "Submit answer") as HTMLButtonElement,
      submitQuiz);
    const needPick = !submitted && pendingSelection.size === 0;
    const note = submitted
      ? el("span", { class: "small muted ml-3" }, "Your answer is recorded.")
      : (needPick ? el("span", { class: "small muted ml-3" }, "Pick an answer, then Submit.") : null);
    body.appendChild(el("div", { class: "mt-3" }, submitBtn, note));
  } else {
    body.appendChild(el("div", { class: "small muted mt-3" },
      "Voting closed — the answer has been revealed."));
  }
}

async function submitQuiz(): Promise<void> {
  if (!activeQuiz || !activeQuiz.current_question) return;
  const alreadySubmitted = (activeQuiz.my_selections ?? []).length > 0;
  if (!alreadySubmitted && pendingSelection.size === 0) { toast("Pick an answer first"); return; }
  try {
    await api(`/api/sessions/${CODE}/quiz_runs/${activeQuiz.id}/submit`, {
      method: "POST",
      body: { question_id: activeQuiz.current_question.id, answer_ids: [...pendingSelection] },
    });
    loadQuiz().catch(reportError);
  } catch (e) { errorToast((e as Error).message); }
}

// ---- session feedback (star rating → went-well / improve) ----
interface FeedbackDraft { rating: number; went_well: string | null; to_improve: string | null }
let myRating = 0;
let feedbackSubmitted = false;
function currentFeedback(): FeedbackDraft {
  return {
    rating: myRating,
    went_well: $<HTMLTextAreaElement>("#fb-went-well").value.trim() || null,
    to_improve: $<HTMLTextAreaElement>("#fb-to-improve").value.trim() || null,
  };
}
function renderStars(): void {
  const root = $("#fb-stars");
  root.innerHTML = "";
  const btns: HTMLElement[] = [];
  const paint = (n: number) => btns.forEach((b, idx) => b.classList.toggle("filled", idx < n));
  for (let i = 1; i <= 5; i++) {
    const b = el("button", {
      type: "button",
      class: "star",
      role: "radio",
      "aria-checked": String(i === myRating),
      "aria-label": `${i} star${i > 1 ? "s" : ""}`,
      onclick: () => {
        myRating = i;
        setVisible($("#fb-expand"), true);
        renderStars();
        markFeedbackDirty();
      },
    }, "★");
    b.addEventListener("mouseenter", () => paint(i));
    btns.push(b);
    root.appendChild(b);
  }
  root.onmouseleave = () => paint(myRating);
  paint(myRating);
  setVisible($("#fb-clear"), myRating > 0);
  setVisible($("#fb-clear-confirm"), false);
  renderFeedbackAction();
}

function renderFeedbackAction(): void {
  const button = $<HTMLButtonElement>("#fb-submit");
  button.textContent = feedbackSubmitted ? "Resubmit feedback" : "Submit feedback";
  $("#fb-submit-hint").textContent = myRating
    ? "Your rating and comments are submitted together."
    : "Choose a rating to submit feedback.";
}

// True while the stars or comments hold changes not yet submitted; saved
// feedback never overwrites them (UC-P-13).
let feedbackDraftDirty = false;
function markFeedbackDirty(): void {
  feedbackDraftDirty = true;
  $("#fb-status").textContent = feedbackSubmitted ? "Unsaved changes" : "Ready to submit";
}

async function saveFeedback(): Promise<void> {
  if (!feedbackEnabled) return;
  if (!myRating) {
    toast("Choose a rating first");
    return;
  }
  const cur = currentFeedback();
  const wasResubmission = feedbackSubmitted;
  try {
    await api(`/api/sessions/${CODE}/feedback`, { method: "POST", body: cur });
    feedbackSubmitted = true;
    feedbackDraftDirty = false;
    $("#fb-status").textContent = "Submitted ✓";
    renderFeedbackAction();
    renderFeedbackSummary();
    // A finished task folds away to one line; tapping it reopens (UC-P-13).
    $<HTMLDetailsElement>("#feedback-card").open = false;
    toast(wasResubmission ? "Feedback resubmitted" : "Thanks for your feedback");
  } catch (e) {
    $("#fb-status").textContent = "Submit failed";
    errorToast((e as Error).message);
  }
}
async function clearFeedback(): Promise<void> {
  if (!feedbackEnabled) return;
  if (feedbackSubmitted) {
    try { await api(`/api/sessions/${CODE}/feedback`, { method: "DELETE" }); }
    catch (e) { errorToast((e as Error).message); return; }
  }
  myRating = 0;
  feedbackSubmitted = false;
  feedbackDraftDirty = false;
  $<HTMLTextAreaElement>("#fb-went-well").value = "";
  $<HTMLTextAreaElement>("#fb-to-improve").value = "";
  setVisible($("#fb-expand"), false);
  $("#fb-status").textContent = "";
  renderStars();
  renderFeedbackSummary();
  toast("Feedback cleared");
}
$("#fb-clear").addEventListener("click", () => {
  setVisible($("#fb-clear"), false);
  setVisible($("#fb-clear-confirm"), true);
});
$("#fb-clear-no").addEventListener("click", () => {
  setVisible($("#fb-clear-confirm"), false);
  setVisible($("#fb-clear"), true);
});
$("#fb-clear-yes").addEventListener("click", () => {
  setVisible($("#fb-clear-confirm"), false);
  void clearFeedback();
});
async function loadFeedback(): Promise<void> {
  try {
    const f = await api<Feedback | null>(`/api/sessions/${CODE}/feedback/mine`);
    applyFeedback(f);
  } catch { /* no feedback yet */ }
}

/** One-line header summary of the saved rating, shown once submitted. */
function renderFeedbackSummary(): void {
  const summary = $("#fb-summary");
  summary.textContent = `Rated ${"★".repeat(myRating)}${"☆".repeat(5 - myRating)}`;
  setVisible(summary, feedbackSubmitted && myRating > 0);
}

let feedbackLoaded = false;
function applyFeedback(f: Feedback | null): void {
  if (feedbackDraftDirty) return;
  if (f) {
      myRating = f.rating;
      $<HTMLTextAreaElement>("#fb-went-well").value = f.went_well || "";
      $<HTMLTextAreaElement>("#fb-to-improve").value = f.to_improve || "";
      setVisible($("#fb-expand"), true);
      feedbackSubmitted = true;
      $("#fb-status").textContent = "Submitted ✓";
  } else {
      myRating = 0;
      feedbackSubmitted = false;
      $<HTMLTextAreaElement>("#fb-went-well").value = "";
      $<HTMLTextAreaElement>("#fb-to-improve").value = "";
      setVisible($("#fb-expand"), false);
      $("#fb-status").textContent = "";
  }
  renderStars();
  renderFeedbackSummary();
  // Start collapsed when the participant already rated; later refreshes
  // leave the card as the participant left it.
  if (!feedbackLoaded) {
    feedbackLoaded = true;
    if (f) $<HTMLDetailsElement>("#feedback-card").open = false;
  }
}
$("#fb-went-well").addEventListener("input", markFeedbackDirty);
$("#fb-to-improve").addEventListener("input", markFeedbackDirty);
guardClick($<HTMLButtonElement>("#fb-submit"), saveFeedback);

// A refetch a live update triggers is never silent when it fails (UX.md §8).
function reportError(error: unknown): void { errorToast((error as Error).message); }

function refreshAll(): void {
  loadSession().catch(reportError);
  loadQueries().catch(reportError);
  loadQuiz().catch(reportError);
}

let quizCountTimer: ReturnType<typeof setTimeout> | null = null;
function scheduleQuizRefresh(): void {
  if (quizCountTimer) return;
  quizCountTimer = setTimeout(() => { quizCountTimer = null; loadQuiz().catch(reportError); }, 1000);
}

/** Links to the session's other views, for its owner or a delegate moderator
 * (who holds the session's moderator key); participants see none. */
function renderViewLinks(isOwner: boolean): void {
  const links: [string, string][] = [];
  if (isOwner) links.push(["Sessions", "/"]);
  if (isOwner || modKey()) links.push(["Session page", `/m/${CODE}`], ["Projector", `/p/${CODE}`]);
  const box = $("#view-links");
  box.replaceChildren(...links.flatMap(([label, href]) => [" · ", el("a", { href }, label)]));
  setVisible(box, links.length > 0);
}

// Refetch only what each event affects; ignore peers' quiz_submission unless
// live counts are shown (else every submit → every client refetches: O(N^2)).
function onLive(msg: LiveMessage): void {
  switch (msg.type) {
    case "query_new": case "query_vote": case "query_responded":
    case "query_removed": case "query_deleted":
      loadQueries().catch(reportError); break;
    case "quiz_run_new": case "quiz_run_update": case "quiz_run_deleted":
      loadQuiz().catch(reportError); break;
    case "session_state":
      loadSession().catch(reportError); loadQuiz().catch(reportError); break;
    case "feedback_state":
      loadSession().catch(reportError); break;
    case "quiz_submission":
      if (activeQuiz && activeQuiz.results) scheduleQuizRefresh(); break;
    case "feedback": case "participant":
      break;
    case "session_deleted":
      if (quizCountTimer) clearTimeout(quizCountTimer);
      showSessionDeleted();
      break;
    default:
      refreshAll(); break;
  }
}

(async function boot() {
  // Connect before rendering interactive state so a session transition cannot
  // land between the initial fetch and socket readiness.
  openLiveSocket(CODE, onLive);
  // A live update can refetch a part while this request is in flight; the
  // bootstrap is then older, so it skips that part (UC-X-11).
  const sessionSeq = ++latestSessionSeq;
  const queriesSeq = ++latestQueriesSeq;
  const quizSeq = ++latestQuizSeq;
  const state = await api<ParticipantBootstrap>(`/api/sessions/${CODE}/participant-bootstrap`);
  if (sessionSeq === latestSessionSeq) applySession(state.session, false);
  applyMe(state.me);
  if (queriesSeq === latestQueriesSeq) applyQueries(state.queries);
  if (quizSeq === latestQuizSeq) applyQuizRuns(state.quiz_runs);
  applyFeedback(state.feedback);
  renderViewLinks(state.viewer_is_owner);
  markUsable("participant");
})().catch((error: unknown) => errorToast((error as Error).message));
