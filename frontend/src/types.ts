// Shared API payload shapes (the JSON the FastAPI backend returns).

export interface Session {
  code: string;
  title: string;
  status: string; // planning | live | ended
  participant_base_url: string | null;
  /** The running tunnel's public address (`prashna --tunnel`), else null. */
  default_base_url?: string | null;
  feedback_enabled: boolean;
  started_at?: string | null;
  ended_at?: string | null;
}

export interface Query {
  id: number;
  text: string;
  author_name: string | null;
  response_text: string | null;
  responded: boolean;
  removed: boolean;
  vote_count: number;
  voted: boolean;
  mine: boolean;
  created_at: string;
}

export interface Answer {
  id: number;
  text: string;
  is_correct: boolean | null;
  image_url: string | null;
}

export interface Question {
  id: number;
  text: string;
  qtype: string; // single | multi
  image_url: string | null;
  answers: Answer[];
}

export interface QuizResults {
  /** Counts by answer id; null for a participant before a graded question's reveal (UC-P-12). */
  totals: Record<number, number> | null;
  respondents: number;
  /** Before a graded question's reveal: the counts, largest first, with no answer attached (UC-D-08). */
  masked_counts?: number[];
}

export interface QuizRun {
  id: number;
  status: string; // queued | live | closed
  quiz_title: string;
  version_no: number;
  current_question_idx: number;
  question_count: number;
  reveal_current: boolean;
  show_live_counts: boolean;
  current_question: Question | null;
  my_selections?: number[];
  results: QuizResults | null;
}

export interface Feedback {
  rating: number;
  went_well: string | null;
  to_improve: string | null;
  updated_at: string | null;
}

export interface FeedbackSummary {
  count: number;
  average: number | null;
  distribution: Record<number, number>;
  items: Feedback[];
}

export interface ParticipantProfile {
  id: number;
  name: string | null;
  email: string | null;
  contact_number: string | null;
  organization: string | null;
  role: string | null;
  linkedin_url: string | null;
  photo_url: string | null;
  current_work: string | null;
  learning_goal: string | null;
}

export interface ParticipantProfileSummary {
  count: number;
  items: ParticipantProfile[];
}

export interface AdminStatus {
  initialized: boolean;
  authenticated: boolean;
  username: string | null;
}

/** GET/PUT /api/admin/limits (UC-A-31). */
export interface Limits {
  values: Record<string, number>;
  defaults: Record<string, number>;
}

export interface ParticipantBootstrap {
  session: Session;
  me: ParticipantProfile;
  queries: Query[];
  quiz_runs: QuizRun[];
  feedback: Feedback | null;
  viewer_is_owner: boolean;
}

export interface ModeratorBootstrap {
  session: Session;
  available_quizzes: QuizSummary[];
  is_owner: boolean;
}

export interface DisplayBootstrap {
  session: Session;
  queries: Query[];
  quiz_runs: QuizRun[];
}

// A session row from GET /api/sessions (admin list).
export interface SessionRow extends Session {
  mod_key: string;
  query_count: number;
  quiz_run_count: number;
  feedback_count: number; // participants who submitted feedback
  profile_count: number; // participants who filled in an attendee profile
  created_at: string;
}

// --- quiz authoring (/quizzes) ---
/** Where a quiz's runs are (UC-A-10); `run_status` is the most relevant
 *  state there: live over queued over closed. */
export interface QuizSessionUse {
  code: string;
  title: string;
  session_status: string;
  run_status: string;
  run_count: number;
}

export interface QuizSummary {
  id: number;
  title: string;
  status: string; // draft | ready
  question_count: number;
  sessions?: QuizSessionUse[]; // GET /api/quizzes
  in_session?: { run_status: string; run_count: number } | null; // available_quizzes
  /** Why a Ready quiz can't be added to a session (an edit broke a publish
   *  rule), or null (UC-A-10). */
  problem: string | null;
}

export interface EditorAnswer {
  id: number;
  text: string;
  is_correct: boolean;
  image_url: string | null;
}

export interface EditorQuestion {
  id: number;
  text: string;
  qtype: string;
  graded: boolean;
  order_index: number;
  image_url: string | null;
  answers: EditorAnswer[];
}

/** One failing publish rule (UC-A-21). `question_id` is null for the
 *  quiz-level rule; `answer_id` is set only when the rule is about one answer. */
export interface PublishProblem {
  question_id: number | null;
  answer_id: number | null;
  field: "questions" | "text" | "answers" | "correct" | "answer";
  message: string;
}

export interface QuizEditor {
  id: number;
  title: string;
  status: string;
  questions: EditorQuestion[];
  /** Every failing publish rule, empty when the quiz can be published. */
  problems: PublishProblem[];
}

export interface QuizRunRow {
  id: number;
  quiz_id: number;
  quiz_title: string;
  version_no: number;
  session_title: string;
  session_code: string;
  status: string;
  current_question_idx: number;
  question_count: number;
  respondent_count: number;
  created_at: string;
}

export interface ResultOption {
  text: string;
  count: number;
  is_correct: boolean;
  image_url?: string | null;
}

export interface ResultQuestion {
  text: string;
  image_url: string | null;
  respondents: number;
  answers: ResultOption[];
}

export interface QuizRunResults {
  quiz_title: string;
  version_no: number;
  session_code: string;
  session_title: string;
  status: string;
  questions: ResultQuestion[];
}
