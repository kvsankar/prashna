# Prashna Brownfield Baseline Code Review

Review Type: Brownfield Baseline Conformance Audit

Reviewed At: 2026-07-03T18:00:15Z

Work Scope: product/system

Implementation Readiness: Decomposable

## Review Basis

This review judges existing code and tests against reconstructed accepted
intent in `spec.md` and `design.md`. It does not claim conformance to a
pre-approved implementation plan. The process decision permits planless
baseline review only for retrospective baseline review.

The review is non-independent. Subagent tools exist in this host, but current
delegation policy requires explicit user permission before spawning subagents.

## Verification Evidence Considered

- `check_spec.py spec.md --require-approvals --json`: passed 17/17.
- `check_design.py design.md --spec spec.md --require-approvals --json`:
  passed 14/14.
- `sha256sum spec.md design.md`: hashes match `.sdlc/approvals.yaml`.
- `UV_CACHE_DIR=/tmp/uv-cache uv run ruff check .`: passed.
- `npm run lint`: TypeScript, ESLint, and Stylelint passed.
- `UV_CACHE_DIR=/tmp/uv-cache uv run pre-commit run --all-files`: passed.
- `timeout 210 env UV_CACHE_DIR=/tmp/uv-cache uv run pytest --tb=short`:
  416 passed, 5 skipped, 1758 warnings, completed in 157.22 s.
- Focused auth/system/rate-limit API slice:
  56 passed, 2 skipped, completed in 14.98 s.
- Focused landing UI smoke:
  9 passed, 1 skipped, completed in 5.78 s.

Coverage percentage was not collected in this pass. This was a qualitative
review, not a full `/code-assess`.

## Code Gaps Against SRS

### CG-01: Operator Diagnostics Are Not Implemented To The Accepted NFR

Classification: `fix-code`

Severity: High

Evidence:

- `spec.md:640` requires incident-useful auth, lifecycle, upload, and
  live-update diagnostics retained for at least 7 days.
- `design.md:642` records operator diagnostics as a known observability risk.
- `app/main.py:95` through `app/main.py:104` only logs the missing-secret
  startup warning.
- Route paths for moderator Q&A and quiz-run lifecycle changes, such as
  `app/main.py:1215` through `app/main.py:1248` and `app/main.py:1707`
  through `app/main.py:1855`, mutate incident-relevant state without
  application-level diagnostic logging.
- `deploy/docker-compose.yml:4` through `deploy/docker-compose.yml:22` define
  the service and health check but no log-retention policy.

Impact:

The product can pass functional tests while still failing the accepted
diagnostics requirement. Operators would have weak evidence for auth, setup,
OAuth, upload, migration, and live-update incidents.

Concrete fix:

Add safe structured logs for admin auth/setup/OAuth, session lifecycle, upload
rejections, migration startup, WebSocket join/broadcast failures, and quiz/Q&A
moderator mutations. Add deployment log retention or document the host-level
retention mechanism, then add log-review or incident-drill tests/checks.

### CG-02: Public Bootstrap Requirement Contradicts The Accepted Non-Goal

Classification: `revise-artifact`

Severity: Medium

Evidence:

- `spec.md:90` says public-first bootstrap is not current baseline scope.
- `spec.md:653` says public deployments expose first-admin setup to zero users
  outside the intended operator path.
- `spec.md:1009` keeps bootstrap hardening as an open question.
- `app/main.py:664` through `app/main.py:681` implements public first-run
  setup while the database has no admin.

Impact:

This should not automatically become redesign or implementation work during
adoption. The SRS currently mixes an accepted private-operator baseline with a
public-deployment hardening requirement.

Concrete fix:

Revise the SRS to choose one current-baseline statement. Either keep public
bootstrap hardening as a non-goal/open future delta, or promote it to an
explicit `fix-code` remediation requirement.

## Test Gaps Against SRS And Design

### TG-01: Accepted `AT` / `JT` / `TEST` Obligations Lack Traceability

Classification: `add-or-strengthen-tests`

Severity: High

Evidence:

- `.sdlc/test-traceability.yaml` does not exist.
- Existing tests still cite the legacy `UC-*` taxonomy, for example
  `tests/api/test_admin_auth.py:1`.
- `design.md:562` through `design.md:570` makes docs/behavior contract checks
  part of `TEST-DOCS-CONTRACT`, but current doc contract tests only sample
  selected legacy docs in `tests/api/test_docs_contracts.py:13` through
  `tests/api/test_docs_contracts.py:35`.

Impact:

The suite is large and healthy, but there is no machine-reviewable map from
accepted Sarathi `AT-*`, `JT-*`, and design `TEST-*` obligations to executable
tests. Reviewers must infer coverage manually.

Concrete fix:

Add `.sdlc/test-traceability.yaml` mapping each accepted `AT`, `JT`, and
`TEST` obligation to existing tests or to planned remediation tests. Do not
rename tests merely to carry IDs unless the repo explicitly adopts that style.

### TG-02: Reconnect Recovery Is Only Indirectly Tested

Classification: `add-or-strengthen-tests`

Severity: High

Evidence:

- `spec.md:779` requires role pages to refetch within 5 s after socket
  reconnect.
- `design.md:517` through `design.md:525` requires WebSocket integration and
  browser recovery checks.
- `frontend/src/common.ts:88` through `frontend/src/common.ts:117` implements
  reconnect and refetch behavior.
- `tests/ui/test_projector.py:197` through `tests/ui/test_projector.py:203`
  explicitly skips the reconnect browser test.

Impact:

The implementation may be correct, but the accepted `AT-LIVE-RECONNECT` and
`TEST-LIVE-REFRESH` obligations are not directly verified.

Concrete fix:

Add a deterministic test for `openLiveSocket` reconnect behavior, or add a
browser/integration test that forces a socket close and verifies visible state
refetch within 5 s.

### TG-03: Security Header Tests Do Not Sample API Payloads

Classification: `add-or-strengthen-tests`

Severity: Medium

Evidence:

- `spec.md:615` requires non-upload pages and API payloads to include the four
  baseline security headers across at least four samples per class.
- `app/main.py:111` through `app/main.py:133` applies the baseline headers to
  non-upload responses, including API responses.
- `tests/api/test_system.py:210` through `tests/api/test_system.py:217` only
  samples `/` and `/static/app.css` for baseline headers.

Impact:

The implementation appears stronger than the tests, but the accepted
`NFR-SEC-HEADERS` verification method is under-specified by current tests.

Concrete fix:

Extend the header test to sample at least four page/static responses and four
API JSON/error responses.

### TG-04: Mobile Participant Viewport Obligation Is Not Tested

Classification: `add-or-strengthen-tests`

Severity: Medium

Evidence:

- `spec.md:630` through `spec.md:635` requires keyboard checks and participant
  usability at a 360 px viewport for at least two users.
- `design.md:526` through `design.md:534` includes mobile viewport behavior in
  `TEST-PROJECTOR-STATE`.
- `tests/ui/conftest.py:113` through `tests/ui/conftest.py:122` creates a
  default browser context without a mobile viewport.
- Search found no UI tests setting a 360 px viewport.

Impact:

Existing UI tests cover several keyboard paths, but the accepted mobile-width
participant requirement is not directly verified.

Concrete fix:

Add a participant-focused Playwright test at 360 px width, with two participant
contexts, covering join, profile, ask/vote, live quiz, feedback, and no
overlap/clipping in the primary participant flows.

### TG-05: Deployment Smoke Obligation Is Not Executed

Classification: `add-or-strengthen-tests`

Severity: Medium

Evidence:

- `design.md:552` through `design.md:561` requires build, package,
  deployment, health-check, persistent-path, and startup-diagnostic evidence.
- `.github/workflows/docker.yml:49` through `.github/workflows/docker.yml:88`
  builds and publishes an image, but does not run `docker compose up` or hit
  the health endpoint.
- `deploy/docker-compose.yml:17` through `deploy/docker-compose.yml:22`
  defines a health check that current CI does not exercise.

Impact:

The image can build while the documented compose path, health check, and
persistent volume configuration remain untested.

Concrete fix:

Add a CI or local smoke that builds the image, starts the compose service with
temporary data/uploads volumes, waits for `/api/admin/status`, restarts the
container, and verifies persistence paths.

### TG-06: Secret-Key Lifecycle Is Skipped Instead Of Verified

Classification: `add-or-strengthen-tests`

Severity: Medium

Evidence:

- `spec.md:782` through `spec.md:785` includes secret-key behavior in
  `AT-OPS-CONFIG`.
- `tests/api/test_system.py:443` through `tests/api/test_system.py:445` skips
  the restart-based secret-key lifecycle test.
- `tests/api/test_system.py:448` through `tests/api/test_system.py:456` covers
  only the pure helper behavior.

Impact:

The accepted deployment configuration behavior is not verified across process
restart, which is the important operator scenario.

Concrete fix:

Add a subprocess or integration test that starts the app with a fixed secret,
verifies old cookies survive restart, then verifies unset or changed secrets
invalidate old cookies.

## Qualitative Scorecard

- Upstream code-readiness: 3/5.
  - Fix: resolve the public-bootstrap contradiction in `spec.md`.
- Brownfield baseline conformance: 3/5.
  - Fix: address CG-01 and classify CG-02 before remediation planning.
- Test implementation quality and level completeness: 3/5.
  - Fix: add traceability plus the missing reconnect, API-header, mobile,
    deploy-smoke, and restart-lifecycle checks.
- Verification-oracle rigor: 4/5.
  - Fix: strengthen the indirect reconnect and deployment oracles.
- Logging and telemetry fitness: 2/5.
  - Fix: implement retained, safe operational diagnostics.
- Error-handling fitness: 4/5.
  - Fix: expand `AT-NFR-ERRORS` mapping in traceability.
- Correctness: 4/5.
  - Fix: no broad behavior failure found; diagnostics remain the main
    implementation gap.
- Design fidelity: 4/5.
  - Fix: keep redesign candidates as risks until user-approved deltas.
- Build/deployment completeness: 3/5.
  - Fix: add compose/health/persistence smoke evidence.
- Quality-gate fitness: 4/5.
  - Fix: consider a coverage threshold once UI coverage capture is settled.
- Maintainability: 4/5.
  - Fix: address the repeated `datetime.utcnow()` deprecation warnings in a
    future low-risk cleanup.

## Top Fixes

1. Revise `spec.md` to settle the public-bootstrap contradiction.
2. Add `.sdlc/test-traceability.yaml` mapping `AT`, `JT`, and `TEST`
   obligations to current and missing tests.
3. Plan a brownfield remediation delta for operational diagnostics.
4. Plan test remediation for reconnect recovery, API security headers, mobile
   participant viewport, deploy smoke, and secret-key lifecycle.

## Review Verdict

Verdict: Pass-with-fixes.

The existing implementation is broadly consistent with the reconstructed
product behavior and the full local test suite passes within the accepted
180 s window. It is not ready to treat the accepted SRS/design as fully
covered: the audit found one material implementation gap, one upstream artifact
contradiction, and several requirements-derived test gaps. New remediation work
should go through a focused `/plan-create` after the user accepts or revises the
gap classifications.
