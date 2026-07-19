# Prashna Remediation Code Assessment

Supersession Note: this report is historical for formal gate purposes. On
2026-07-20, `spec.md`, `design.md`, and `plan.md` were materially revised for
Sarathi 0.3.2 terminology and checker expectations. The implemented code
remains in the same remediation boundary, but a fresh `/code-assess` is needed
after renewed plan approval if a formal assessment gate is required.

Assessment Type: Sarathi `/code-assess`

Assessed At: 2026-07-04T15:02:22Z

Work Scope: slice/change

Verdict: Pass with reservations

## Assessment Basis

This assessment covers the accepted remediation plan in `plan.md` against the
approved `spec.md`, approved `design.md`, and implementation/test changes in
the current worktree.

The assessment used two fresh-context subagent passes:

- Mechanical verifier: deterministic checkers, pre-commit, and line-width
  scan. No files were edited.
- Qualitative reviewer: adversarial review of implementation fitness,
  test oracles, traceability, logging/error handling, deployment work, and
  maintainability. No files were edited.

The main agent also spot-checked mapped tests and implementation targets for
diagnostics, reconnect recovery, mobile participant behavior, and compose
deployment smoke coverage.

## Mechanical Evidence

All requested mechanical checks passed:

- `check_spec.py`: 17/17 passed.
- `check_design.py`: 14/14 passed.
- `check_plan.py`: 17/17 passed.
- `check_code.py`: 13/13 passed.
- `uv run pre-commit run --all-files`: passed.
- Sarathi artifact line-width scan: passed for the checked command.

`check_code.py` reported:

- Test execution: passed.
- Coverage: 94.0 percent, above the 80.0 percent floor.
- PR traceability: 100.0 percent.
- ID traceability: 100.0 percent.
- Assertion traceability: 100.0 percent.
- `.sdlc/test-traceability.yaml`: 46 entries, no invalid entries, no
  unresolved tests.
- Marker approval: accepted through `APR-CODE-MARKERS-BASELINE`.

The verifier noted 30 long lines in `design.md`, all in Sarathi metadata
comments or Markdown tables. The scan command still exited zero.

## Qualitative Findings

### CA-01: Diagnostic Sanitization Is Duplicated

Severity: Low

Classification: maintainability-risk

`app/main.py` filters diagnostic fields whose names include unsafe key words
such as password, secret, token, key, or cookie. `app/db.py` and `app/ws.py`
have local diagnostic helpers that do not apply the same field-name filter.

Current call sites in `app/db.py` and `app/ws.py` appear safe, and tests assert
that relevant secrets and payload bodies are not logged. The risk is a future
maintenance footgun if a later call site passes an unsafe string field through
one of the smaller helpers.

Recommended follow-up: centralize diagnostic logging or share one sanitizer
across `app/main.py`, `app/db.py`, and `app/ws.py`.

### CA-02: Reconnect Test Hook Ships In Runtime JS

Severity: Low

Classification: test-surface-risk

`frontend/src/common.ts` exposes `window.__prashnaLiveSocketTest` when a
specific `localStorage` key is set. This gives browser tests a deterministic
way to force a socket close, and the hook is intentionally gated. The impact is
limited to a user closing their own live socket, but the hook is still test
scaffolding in the production JavaScript surface.

Recommended follow-up: consider a test build only hook or a narrower runtime
guard if the project wants to keep test scaffolding out of shipped JS.

## Test Oracle Spot Checks

The assessment inspected representative mappings from
`.sdlc/test-traceability.yaml`:

- `tests/api/test_diagnostics.py::test_auth_session_upload_and_ws_diagnostics`
  exercises setup, login, session lifecycle, upload rejection, WebSocket
  rejection, password change, logout, event names, and secret redaction.
- `tests/ui/test_projector.py::test_uc_d_05_reconnect_refetches_after_close`
  forces the live socket closed, creates a missed query, and verifies visible
  projector catch-up within the accepted timeout.
- The participant mobile flow test uses two 360 px contexts and covers
  identity, ask, vote, quiz answer, feedback, and horizontal-overflow checks.
- `tests/ops/test_compose_smoke.py` checks compose configuration, persistent
  paths, setup ownership, and a gated full compose smoke. CI enables the full
  smoke with `PRASHNA_COMPOSE_SMOKE=1`.

The sampled tests have behavioral or deployment oracles, not just ID strings.
Some documentation-contract tests remain meta-level by nature; that is
acceptable for artifact and traceability obligations.

## Residual Risks

- TDD provenance remains limited. `.sdlc/wip.md` records Red/Green evidence,
  but the current work is uncommitted on the default branch, so Sarathi cannot
  prove original Red/Green history from review-base diff evidence.
- The code checker used allowed missing git and TDD evidence for this
  default-branch brownfield adoption context.
- `app/main.py`, `tests/api/test_quizzes.py`, and
  `tests/ui/test_participant.py` remain oversized maintainability risks.
- The existing marker inventory is approved, but the marker hits still exist.

## Scores

- Upstream fitness: 4/5.
- Implementation quality: 4/5.
- Test quality: 4/5.
- Traceability: 4/5.
- Maintainability: 4/5.

## Gate

The implementation is fit to proceed to human review. The two qualitative
findings are low-severity cleanup risks, not correctness blockers.

## Follow-Up Resolution

Resolved At: 2026-07-04T15:10:52Z

Both low-severity follow-ups from this assessment have been addressed:

- `CA-01`: diagnostic logging now uses shared sanitizer logic from
  `app/diagnostics.py`; `app/db.py` and `app/ws.py` route through the same
  helper as `app/main.py`.
- `CA-02`: the reconnect test hook is now gated by Vite test mode and the
  `localStorage` test flag. A normal production `npm run build` no longer
  emits the hook name or test flag string in `frontend/dist`.

Additional regression coverage was added for unsafe diagnostic field names and
the frontend test build hook boundary.
