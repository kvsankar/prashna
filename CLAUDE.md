# CLAUDE.md

Rules for coding agents working in this repository.

## Project character

Prashna is a live Q&A and quiz tool. It runs in production with real
audiences, so changes must be additive and reversible. Sweeping refactors
during an event cause problems. Keep the code clear and small. Do not add
frameworks, abstractions, or features beyond what the task needs.

## Where each topic lives

- [`README.md`](README.md): what Prashna is, install, and a quick tutorial.
- [`docs/user-guide.md`](docs/user-guide.md): the user guide, for the
  people who run sessions: roles, features, tunnels, data, backup, update,
  uninstall, password reset, and troubleshooting.
- [`docs/specs.md`](docs/specs.md): the behaviour contract. Every use case
  (`UC-A-*` admin, `UC-M-*` moderator, `UC-P-*` participant, `UC-D-*`
  projector, `UC-X-*` system) has acceptance criteria and **Tests (API)** /
  **Tests (UI)** bullets. Read its "Conventions used by the Tests blocks"
  section for the shared auth-error responses.
- [`docs/UX.md`](docs/UX.md): the frontend design system. Read it before
  touching HTML or CSS.
- [`docs/architecture.md`](docs/architecture.md): components, data model,
  entity names, design decisions, and risks.
- [`docs/development.md`](docs/development.md): setup, run commands,
  environment variables, tests, checks, project layout, releases, and the
  documentation policy.
- [`docs/todo.md`](docs/todo.md): engineering follow-ups.
- [`deploy/README.md`](deploy/README.md),
  [`distribution/README.md`](distribution/README.md),
  [`performance/README.md`](performance/README.md): operator runbooks.

Keep exactly one `CLAUDE.md`, at the repository root.

## Change workflow

`docs/specs.md` and the tests are the source of truth. To change behaviour:

1. Update `docs/specs.md` first: the use case's text and its **Tests (API)** /
   **Tests (UI)** bullets.
2. Add or update tests in `tests/api/` and `tests/ui/`. Name them after the
   use case (`test_uc_<role>_<nn>_<what>`).
3. Implement the change.
4. Run `uv run pytest` and `uv run pre-commit run --all-files`.

When a test fails, decide whether the test or the code is wrong. The spec is
the tiebreaker. If the spec and the code disagree, choose which to change
deliberately.

Items in the "Deferred (decision needed)" appendix of `docs/specs.md` need a
product decision. Do not implement them without asking.

Prefer editing existing files. Do not add a new module unless the change
clearly does not fit an existing one. Do not add an ORM migration framework,
a UI framework, or a CSS preprocessor without an explicit request.

## Conventions

- **Auth model.** The admin signs in with a username and password (bcrypt),
  which issues the signed `prashna_admin` cookie. Password sign-in is the only
  admin sign-in method. Moderator routes accept the owner's cookie **or**
  the session's `mod_key` in the `X-Mod-Key` header, through
  `require_mod_or_owner`. Admin capabilities are a superset of moderator
  capabilities; `mod_key` is the delegation mechanism. Participants are
  anonymous and identified by the `voter_token` cookie.
- **Live updates.** Every state-changing route ends with
  `broadcast_session(s, "<kind>")`. Clients refetch on the hint; never send
  model state through the socket. The kinds are listed in UC-X-01.
- **Quiz versioning.** A `QuizRun` always references a frozen `QuizVersion`.
  Editing a quiz must not change a past run. A launch captures a new version
  only when `quiz.last_edited_at` is newer than the latest version. A `ready`
  quiz stays `ready` when edited.
- **Schema changes.** `init_db()` runs `create_all`, then the additive
  migration bridge in `prashna/db.py`. When you add a column or index to an
  existing table, extend that bridge and add an old-shape SQLite regression
  test. A non-additive change needs an explicit release plan; ask first.
- **Entity names.** Do not confuse `Question` (quiz template) with `Query`
  (Q&A entry), or `QuizRun` (one playthrough) with `Session` (the gathering).
  See the data model in `docs/architecture.md`.
- **Routes file.** `prashna/main.py` holds all routes in one file. When it is
  next restructured, split it by resource (sessions, queries, quizzes, quiz
  runs, uploads, admin), not by HTTP method.
- **Error wording.** The backend's error string is authoritative; the
  frontend shows it as received.

## Frontend code

- TypeScript with `strict` on, built by Vite, with no UI framework. Do not
  introduce React, Vue, or Svelte without asking. Source is in
  `frontend/src/*.ts`; the browser loads the Vite build.
- Type DOM lookups with the generic `$<T>` helper, for example
  `$<HTMLInputElement>("#x").value`. Add API payload shapes to
  `frontend/src/types.ts`.
- Wire non-idempotent mutating buttons through `guardClick`
  ([UX.md §10](docs/UX.md#10-buttons)).
- Use stable IDs (`#new-session-title`) or documented classes
  (`.badge-live`, `.option`, `.question`) as selectors.
- Use a toast for transient errors, a banner for persistent ones, and a
  redirect when authentication expires ([UX.md §8](docs/UX.md#8-state-patterns)).
  Do not use `alert()` or `prompt()`.
- `npm run typecheck` and `npm run lint` must pass.

## Be careful with

- **The moderator URL carries a secret** in its fragment (`#k=...`). Do not
  log full URLs on the server, and do not print `mod_key` to stdout outside
  the session-creation response. The owner-only "Share moderator URL" button in
  the session page's Session settings card is the only place that exposes
  it: it copies the URL to the clipboard on demand and never renders the key
  into the DOM.
- **Uploads.** Admin quiz images and participant profile photographs are
  written to the uploads folder and served from `/uploads` with strict CSP,
  `nosniff`, and `Cross-Origin-Resource-Policy` headers (UC-X-03). The 5 MB
  cap and the extension allowlist are the only validation; keep them. SVG is
  excluded.
- **`voter_token` is not HttpOnly** on purpose, so the frontend can mark a
  participant's own entries. Do not make it HttpOnly without redesigning
  that UI.
- **`uq_session_live_run`**, a partial unique index, enforces at most one live
  `QuizRun` per `Session` in the database. The backend turns the
  `IntegrityError` into a `409`. Do not remove it; application-level checks
  alone do not survive SQLite's single-writer ordering.
- **Single process.** The WebSocket hub, the rate limiter, and the setup lock
  live in process memory. Do not add workers or replicas.
- **Production.** Do not deploy, push, or redeploy to production without an
  explicit request.
