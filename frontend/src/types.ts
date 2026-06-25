// Shared API payload shapes (the JSON the FastAPI backend returns).

export interface Session {
  code: string;
  title: string;
  status: string; // planning | live | ended
  participant_base_url: string | null;
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

export interface AdminStatus {
  initialized: boolean;
  authenticated: boolean;
  username: string | null;
  github_enabled: boolean;
}

// A session row from GET /api/sessions (admin list).
export interface SessionRow extends Session {
  mod_key: string;
  query_count: number;
  quiz_run_count: number;
  created_at: string;
}
