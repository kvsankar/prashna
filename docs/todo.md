# Prashna — Outstanding Items

Status snapshot as of 2026-05-12.

Legend: **OPEN** = needs a product/user decision · **DEFERRED** = known
gap, intentionally not addressed yet · **HOLD** = parked at user
request · **PARTIAL** = some of the recommendation landed, the rest
is deferred.

## Open — needs a product decision

### Admin setup singleton invariant — OPEN
*Source:* critical-code-review-report Round 2 setup-race finding.
Same-username setup conflicts are now handled, but two concurrent setup
requests with different usernames can still race because there is no
database-level singleton. Decide whether to add a fixed bootstrap row,
transactional lock, or other invariant before any public/shared
deployment.

## Workflow / deferred decisions

### First-run admin setup is publicly claimable — DEFERRED (workflow workaround)
*Source:* design-review-report D5.
**User decision (2026-05-12):** no code change for now. Operator runs
the app on localhost, completes setup, then exposes via ngrok — so
`POST /api/admin/setup` is never reachable publicly before being
claimed. Revisit when the deploy story shifts away from
operator-on-localhost (e.g. a true public SaaS instance).

If/when revisited, the three candidate flows are:

- (a) One-time setup token printed at container startup; required by
  `POST /api/admin/setup`.
- (b) Out-of-band CLI bootstrap (`docker run … prashna setup …`).
- (c) Private bootstrap mode (bind localhost / firewall-gated) until
  setup completes.

### Image upload content sniffing — OPEN
*Source:* critical-code-review-report C8 · also in specs.md "Deferred"
appendix.
`POST /api/uploads` trusts the file extension. Decoding bytes with
Pillow would catch mismatches but adds a hard runtime dep. Current
mitigations (auth-only, 5 MB cap, extension allowlist excluding SVG,
strict `nosniff`/`CSP`/`CORP` on `/uploads`) are adequate for the
authed-admin path. Revisit when the SaaS instance accepts uploads
from less-trusted operators.

## Deferred — intentional, revisit before scale or launch

### Alembic migrations — DEFERRED
*Source:* design-review-report D3.
The app now has a lightweight additive SQLite migration bridge for known
post-deploy columns and indexes, but not a general migration system.
Adopt Alembic before real user data exists in the SaaS instance or
before non-additive schema changes ship.

### Multi-worker WebSocket hub — DEFERRED
*Source:* design-review-report D4 (second half).
`app/ws.py` is in-memory and assumes one process. Needed: Redis or
Postgres pub-sub before running multiple workers or replicas. Not
needed for the current single-container deploy.

### Central lifecycle state-machine service — DEFERRED (PARTIAL)
*Source:* design-review-report D1.
Per-route source-state guards landed (advance/reveal/close require
`live`; end-session blocks while a quiz is live). Extracting a
shared state-machine service for `Session` and `QuizRun` is
deferred — single-file `app/main.py` is a project value; split when
the file forces it.

## Operational

### Hetzner server bootstrap — PLANNED
*Source:* task #14 in the in-session task list.
Docker install + nginx + TLS + container on the Hetzner VPS.
**User decision (2026-06-23):** back on — user plans a single-operator
Hetzner deploy (behind the bundled nginx) for their own use, not
multi-tenant SaaS. (Reverses the 2026-05-12 hold.) Deploy artifacts
now set `PRASHNA_TRUSTED_PROXY_HOPS=1` for the nginx hop; rate limiting
is in-app (UC-X-08). Still a private single-admin instance, so the
first-visitor-claims-admin window stays workflow-mitigated.

### Backward-compat cookie shim — CLEANUP
*Source:* this branch.
`auth._parse_cookie` still accepts legacy uid-only cookies (no
`session_version`) so existing admin sessions survive the next deploy.
The additive SQLite migration bridge now backfills `users.session_version`.
Safe to remove after the first redeploy and schema update invalidates all
existing sessions naturally — they'll have to log in once. Drop the shim
in a follow-up commit.

### Push & redeploy — GATED ON USER
*Source:* feedback_no_auto_docker memory.
Commit `6c8fd5b` is local-only. `git push origin main` triggers the
ghcr.io image build via CI; not pushed without explicit ask.

## Closed (for context)

Most of the originally actioned review findings (C1–C7, C9, D2, F1,
F2, F3, F5) are committed in `6c8fd5b`, but Round 2 reopened the
admin-setup race as partial and found new schema/UI/spec follow-ups. See
`docs/critical-code-review-report.md`,
`docs/design-review-report.md`, and
`docs/frontend-live-review-report.md` for per-finding Done/Deferred
annotations with rationale.

Additional items closed by the 2026-06-25 TDD pass:

- Existing SQLite rollout for `users.session_version` and other known
  additive schema changes: `app/db.py` now backfills supported columns and
  indexes, with an old-shape DB regression test.
- Moderator Base URL role model: backend, spec, and moderator UI now treat
  Base URL editing as owner-only while delegates see read-only invite
  controls.
- Closed-run live-counts control: closed runs no longer render the live
  counts menu item.
- Frontend refresh race / stale paint: live clients now use monotonic
  refresh sequence guards.
