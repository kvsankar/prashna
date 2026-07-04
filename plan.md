<!-- sarathi:artifact-format version="2" -->

# Prashna Remediation Work Plan

## Implementation Approach

This plan authorizes one reviewable remediation increment for the already
accepted Prashna brownfield baseline. The increment keeps the current product
architecture: one FastAPI app, one SQLite database, one uploads directory, one
Vite TypeScript frontend, and the existing pytest, Playwright, Docker, compose,
and GitHub Actions toolchain.

The work does not redesign Prashna. It reconciles the public-bootstrap artifact
wording, adds external Sarathi test traceability, implements privacy-safe
operator diagnostics, strengthens missing verification around reconnect,
security headers, mobile behavior, secret lifecycle, and compose deployment,
and resolves the low-severity follow-ups found during code assessment.

Success is demonstrated by behavior-focused tests, local quality gates,
Sarathi structural checks, a production bundle scan that excludes test-only
reconnect hooks, and Docker Compose smoke evidence. No live production
deployment is part of this plan.

## Overview

Work Scope: slice/change

Plan Type: Implementation

Ready To Implement: Yes

Review Level: Standard

Extra Checks: Security, Privacy and compliance, Reliability and operations,
Build and release, Documentation, UI and accessibility

Branch/CI Context: implementation branch
`codex/sarathi-brownfield-remediation` against `main`; GitHub Actions run
Python tests, frontend linting, Docker Compose smoke, and image publication
after smoke succeeds.

This implementation plan is ready because the accepted `spec.md`,
`design.md`, and `code-review.md` already identify the current intent,
architecture, risks, and remediation gaps. No child spec, child design,
Breakdown plan, new UI mock, or live deployment decision is required before
coding this increment.

## Can Implementation Start?

- Inherited Sources: `spec.md`, `design.md`, `code-review.md`,
  `.sdlc/process-decisions.yaml`, existing code, existing tests, README,
  deployment docs, and CI.
- Reviewable Increment: one cohesive branch/PR remediates the accepted
  artifact, diagnostics, test-coverage, deployment-smoke, and follow-up
  cleanup gaps.
- Unresolved Blocker: none.
- Smallest Additional Artifact: none.

Why Direct: the accepted product baseline and HLD already define the behavior,
boundaries, and verification obligations. The remediation is a compatibility
and evidence slice inside existing boundaries, not a new product capability or
architecture decision.

Acceptance & Verification: targeted Red/Green tests for changed or newly
covered behavior, existing API/UI compatibility tests, Sarathi spec/design/plan
checkers, Sarathi code checker with coverage, pre-commit, frontend linting,
production bundle scan, and Docker Compose smoke.

## Strategy

Use Red/Green/Refactor for behavior and verification changes. Reuse the
existing pytest, Playwright, pre-commit, Vite, Docker, compose, and GitHub
Actions paths instead of creating process-specific runtime machinery.

The increment is intentionally one PR because the actual branch is one cohesive
review unit and the changed areas are tightly coupled by the accepted review
gaps:

- diagnostics require code, docs, deployment log-retention notes, and tests;
- reconnect verification requires a frontend hook used only by test builds and
  browser proof;
- deployment smoke requires compose, setup, CI, docs, and ops tests together;
- traceability is external to source code and covers both existing and new
  tests.

The non-change boundary is explicit:

- no migration to a frontend framework;
- no distributed live-update layer;
- no Alembic migration framework;
- no public-bootstrap hardening beyond SRS classification;
- no hosted telemetry, dashboards, alerts, canaries, or production deployment;
- no Sarathi IDs added to production or test source for traceability.

Cleanup and simplify passes focus only on touched code, tests, docs, CI,
deployment files, and `.sdlc/` artifacts. If verification reveals a product,
architecture, security, privacy, deployment, or UI decision outside this
boundary, stop and revise the controlling artifact before expanding scope.

## Milestones

### Baseline remediation ready

<!-- sarathi:plan id="MILE-BASELINE-READY" type="milestone" refs="PR-BASELINE-REMEDIATION" -->

The accepted baseline gaps are remediated, tested, traced, and ready for human
review as one branch.

## Pull Requests / Child Work Items

### Baseline remediation increment

<!-- sarathi:plan id="PR-BASELINE-REMEDIATION" type="pr" refs="MILE-BASELINE-READY" -->

Scope: implement the accepted brownfield remediation and Sarathi process
alignment as one cohesive PR.

Planned Touch Set:

- `spec.md`
- `design.md`
- `design.html`
- `plan.md`
- `.sdlc/approvals.yaml`
- `.sdlc/process-decisions.yaml`
- `.sdlc/test-traceability.yaml`
- `.sdlc/wip.md`
- `code-review.md`
- `code-assess.md`
- `README.md`
- `app/main.py`
- `app/db.py`
- `app/ws.py`
- `app/diagnostics.py`
- `frontend/src/common.ts`
- `tests/conftest.py`
- `tests/api/test_docs_contracts.py`
- `tests/api/test_diagnostics.py`
- `tests/api/test_frontend_contracts.py`
- `tests/api/test_quiz_runs.py`
- `tests/api/test_secret_lifecycle.py`
- `tests/api/test_system.py`
- `tests/ops/test_compose_smoke.py`
- `tests/ui/conftest.py`
- `tests/ui/test_landing_anon.py`
- `tests/ui/test_live_boundaries.py`
- `tests/ui/test_moderator.py`
- `tests/ui/test_participant.py`
- `tests/ui/test_projector.py`
- `deploy/README.md`
- `deploy/docker-compose.yml`
- `deploy/setup.sh`
- `.github/workflows/docker.yml`

Build and release work:

- Add a Docker Compose smoke CI job before image publication.
- Validate compose configuration, health checks, persistent paths, setup
  ownership, image build, restart, persistence, and safe logs.
- Keep image publication disabled on pull requests and dependent on smoke
  success.

Documentation work:

- Document operator diagnostics and log-retention ownership.
- Document compose smoke execution and deployment persistent-path ownership.
- Keep public-bootstrap hardening classified as a future delta unless the user
  separately approves it as production work.

Logging and error-handling work:

- Add privacy-safe structured diagnostic events for auth, setup, password
  change, logout, session lifecycle, upload accept/reject, additive migration
  execution, WebSocket join/reject/disconnect/error/broadcast failure, Q&A
  moderation, quiz-run lifecycle, and feedback summary access.
- Centralize diagnostic sanitization so unsafe field names such as password,
  secret, token, key, and cookie are not emitted.
- Preserve existing user/API error behavior unless a test proves an accepted
  requirement was previously unverified.

UI and accessibility work:

- Add browser checks for mobile participant and projector behavior at 360 px.
- Add keyboard/accessibility assertions for mobile participant controls.
- Add a reconnect browser test using a Vite hook used only by test builds. A
  production build must not contain the reconnect test hook name or its browser
  storage flag.

Security, privacy, and operations evidence:

- Verify baseline security headers on page/static and API success/error
  samples.
- Verify secret-key restart behavior in subprocess tests.
- Verify diagnostics do not log passwords, moderator keys, uploaded bytes,
  filenames, Q&A text, or helper fields with unsafe names.
- Verify compose configuration fails actionably when the production secret is
  missing.

Test levels:

- documentation-contract;
- API contract/integration;
- subprocess contract;
- unit contract for diagnostic helper behavior;
- browser contract through Playwright;
- deployment contract and gated compose smoke;
- structural Sarathi verification.

Red evidence expected:

- docs contract fails before public-bootstrap wording is reconciled;
- traceability contract fails while accepted obligations are unclassified;
- diagnostics tests fail before structured events and redaction exist;
- reconnect contract/browser tests fail before a deterministic test hook exists;
- secret-lifecycle tests replace the legacy skipped coverage;
- compose smoke/config tests fail before persistent path, secret, health, and
  setup ownership contracts are present;
- low follow-up regression tests fail before diagnostic helper sanitization and
  the test build hook boundary are fixed.

Green evidence expected:

- targeted tests pass for every changed boundary;
- existing API/UI suites remain compatible;
- production bundle scan finds no reconnect test-hook strings;
- pre-commit, frontend linting, Sarathi code checker, and compose smoke pass or
  a remaining environment-specific failure is reported honestly.

Learning target: whether the accepted brownfield baseline can be made
reviewable and better verified without redesigning the product.

Feedback target and method: human review of PR #1 plus objective CI/local
evidence. Operator/deployment feedback is not claimed until a real deployment
or operator review occurs.

Invalidation question: if compose smoke, review, or code assessment shows the
existing single-process Docker/SQLite deployment path is not viable, revise the
design and plan before merging or deploying.

Execution dependencies: approved `spec.md` and `design.md`, current codebase,
developer-local test environment, Docker for full compose smoke, and GitHub
Actions for PR evidence.

Integration dependencies: this PR must merge as one unit because the plan,
traceability, tests, docs, diagnostics, and deployment smoke evidence describe
the same remediation boundary.

Cohesion reason: each changed file either implements an accepted review gap,
verifies it, documents it, or records Sarathi traceability/evidence for the
same branch.

## Coverage Map

The single PR inherits and covers the accepted current-baseline obligations
listed below. Detailed test to obligation mappings live in
`.sdlc/test-traceability.yaml`.

Functional requirements covered:

FR-AUTH-BOOTSTRAP, FR-AUTH-GITHUB, FR-AUTH-LOGIN, FR-AUTH-PASSWORD,
FR-DISPLAY-JOIN, FR-DISPLAY-QUIZ, FR-FEEDBACK-SUBMIT, FR-FEEDBACK-SUMMARY,
FR-LIVE-BROADCAST, FR-LIVE-RECONNECT, FR-MOD-ACCESS, FR-OPS-CONFIG,
FR-OPS-DEPLOY, FR-OPS-MIGRATE, FR-QA-ASK, FR-QA-IDENTITY, FR-QA-REMOVE,
FR-QA-RESPOND, FR-QA-SORT, FR-QA-VOTE, FR-QUIZ-PUBLISH, FR-QUIZ-TEMPLATE,
FR-QUIZ-UPLOAD, FR-QUIZ-VERSION, FR-RUN-PROGRESS, FR-RUN-QUEUE,
FR-RUN-RESULTS, FR-RUN-SUBMIT, FR-SESSION-CREATE, FR-SESSION-DELETE,
FR-SESSION-LIFECYCLE, FR-SESSION-METADATA.

Use cases covered:

UC-AUTH-BOOTSTRAP, UC-DISPLAY-PROJECTOR, UC-LIVE-SYNC, UC-MOD-RUNROOM,
UC-OPS-DEPLOY, UC-PARTICIPANT-FEEDBACK, UC-PARTICIPANT-QA,
UC-PARTICIPANT-QUIZ, UC-QUIZ-AUTHOR, UC-SESSION-ADMIN.

Non-functional requirements covered:

NFR-ACCESS, NFR-ACCESS-KEYBOARD, NFR-BOOTSTRAP-PUBLIC, NFR-BUILD-CHECKS,
NFR-CAPACITY-ROOM, NFR-DATA-PERSISTENCE, NFR-DIAG-SUPPORT, NFR-DOCS-TRACE,
NFR-ERROR-FEEDBACK, NFR-ERRORS, NFR-PERF-INTERACTION, NFR-PRIVACY-ANON,
NFR-RATE, NFR-RATE-LIMIT, NFR-RELY-HISTORY, NFR-RELY-LIVEUPDATES,
NFR-SCHEMA-MIGRATION, NFR-SEC-HEADERS, NFR-SEC-PASSWORDS, NFR-SEC-UPLOADS,
NFR-UX-RESPONSIVE.

Acceptance and journey tests covered:

AT-AUTH-BOOTSTRAP, AT-AUTH-GITHUB, AT-AUTH-LOGIN, AT-AUTH-PASSWORD,
AT-BUILD-CHECKS, AT-DISPLAY-JOIN, AT-DISPLAY-QUIZ, AT-DOCS-TRACE,
AT-FEEDBACK-SUBMIT, AT-FEEDBACK-SUMMARY, AT-LIVE-BROADCAST,
AT-LIVE-RECONNECT, AT-MOD-ACCESS, AT-NFR-ACCESS, AT-NFR-ERRORS,
AT-NFR-RATE, AT-OPS-CONFIG, AT-OPS-DEPLOY, AT-OPS-MIGRATE, AT-QA-ASK,
AT-QA-IDENTITY, AT-QA-REMOVE, AT-QA-RESPOND, AT-QA-SORT, AT-QA-VOTE,
AT-QUIZ-PUBLISH, AT-QUIZ-TEMPLATE, AT-QUIZ-UPLOAD, AT-QUIZ-VERSION,
AT-RUN-PROGRESS, AT-RUN-QUEUE, AT-RUN-RESULTS, AT-RUN-SUBMIT,
AT-SESSION-CREATE, AT-SESSION-DELETE, AT-SESSION-LIFECYCLE,
AT-SESSION-METADATA, JT-OPS-RELEASE, JT-QUIZ-HISTORY, JT-ROOM-LIVE.

Components and executable test obligations covered:

COMP-ADMIN, COMP-API, COMP-AUTH, COMP-DATA, COMP-LIVE, COMP-MODERATOR,
COMP-OPS, COMP-PARTICIPANT, COMP-PROJECTOR, COMP-QUIZLIB, COMP-UPLOADS,
TEST-AUTH-BOUNDARY, TEST-DEPLOY-SMOKE, TEST-DOCS-CONTRACT,
TEST-LIVE-REFRESH, TEST-PROJECTOR-STATE, TEST-QA-FLOW, TEST-QUIZ-HISTORY,
TEST-SESSION-LIFECYCLE, TEST-SQLITE-MIGRATION, TEST-UPLOAD-SECURITY.

## Sequencing & Risks

Implementation order inside the PR:

1. Reconcile public-bootstrap artifact wording and seed traceability.
2. Expand `.sdlc/test-traceability.yaml` and docs contracts.
3. Add diagnostics and redaction tests, then implementation and docs.
4. Add reconnect test hook and browser recovery tests.
5. Strengthen security-header and mobile UI coverage.
6. Add secret-lifecycle and compose smoke evidence.
7. Resolve code-assessment low follow-ups.
8. Run cleanup, simplify, and assessment checks.

Key risks:

- Docker may be unavailable or behave differently in CI/local environments.
  Report unavailable smoke evidence instead of treating it as passing.
- Added diagnostics must remain useful but secret-safe.
- Test hooks must not ship in normal production bundles.
- Approval records become stale when this plan or design is revised for the
  new Sarathi contract; human review must refresh them before treating the
  gate as approved.

Rollback strategy: revert this branch/PR as one unit. The runtime behavior
changes are additive diagnostics, tests, docs, CI/deploy validation, and
deployment configuration; no destructive data migration or production
deployment is included.

## Traceability

| Human item | Machine ID | Verification |
| --- | --- | --- |
| Baseline remediation ready | MILE-BASELINE-READY | Sarathi checks and PR review |
| Baseline remediation increment | PR-BASELINE-REMEDIATION | Tests, CI, code assessment |
| External test map | `.sdlc/test-traceability.yaml` | Docs contract and code checker |
