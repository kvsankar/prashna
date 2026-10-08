// Shared API payload shapes (the JSON the FastAPI backend returns).

export interface Session {
  code: string;
  title: string;
  status: string; // planning | live | ended
  participant_base_url: string | null;
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
  qtype: string; // single | multiple
  image_url: string | null;
  answers: Answer[];
}

export interface QuizResults {
  totals: Record<number, number>;
  respondents: number;
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
  author_name?: string | null;
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
  github_enabled: boolean;
}

export interface ParticipantBootstrap {
  session: Session;
  me: ParticipantProfile;
  queries: Query[];
  quiz_runs: QuizRun[];
  feedback: Feedback | null;
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

export interface QuizEditor {
  id: number;
  title: string;
  status: string;
  questions: EditorQuestion[];
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
  session_code: string;
  session_title: string;
  status: string;
  questions: ResultQuestion[];
}
