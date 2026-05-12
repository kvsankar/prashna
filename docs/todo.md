# Prashna — Outstanding Items

Status snapshot as of 2026-05-12.

Legend: **OPEN** = needs a product/user decision · **DEFERRED** = known
gap, intentionally not addressed yet · **HOLD** = parked at user
request · **PARTIAL** = some of the recommendation landed, the rest
is deferred.

## Open — needs a product decision

### Existing DB rollout for `users.session_version` — OPEN
*Source:* critical-code-review-report Round 2 schema finding · design-review-report Round 2 schema finding.
The password-cookie invalidation fix added `users.session_version`, but
`Base.metadata.create_all()` does not add columns to existing SQLite
tables. Pick one before redeploying over an existing `prashna.db`:

- Treat this commit as a breaking local-data reset and delete/recreate
  `prashna.db`.
- Add a small startup backfill for the missing column.
- Adopt migrations now rather than waiting for SaaS data.

### Admin setup singleton invariant — OPEN
*Source:* critical-code-review-report Round 2 setup-race finding.
Same-username setup conflicts are now handled, but two concurrent setup
requests with different usernames can still race because there is no
database-level singleton. Decide whether to add a fixed bootstrap row,
transactional lock, or other invariant before any public/shared
deployment.

### Moderator Base URL role model — OPEN
*Source:* design-review-report Round 2 role-boundary finding · frontend-live-review-report Round 2 Base URL finding.
Backend is now owner-only, but UC-M-11/spec text and the moderator UI
still expose the Base URL edit flow to delegated moderators. Decide
whether Base URL editing is owner-only or mod-capable, then update the
spec and UI together.

### Closed-run live-counts control — OPEN
*Source:* frontend-live-review-report Round 2 closed-run finding.
Backend rejects `live_counts` changes on closed quiz runs, but the
moderator UI still renders the checkbox. Hide it or make it read-only
for closed history.

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
Pre-launch policy is "delete `prashna.db` on breaking changes" (per
CLAUDE.md). Adopt Alembic before real user data exists in the SaaS
instance.

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

### Frontend refresh race / stale paint — DEFERRED
*Source:* frontend-live-review-report F4.
WebSocket refresh handlers don't guard against out-of-order
responses. Real but low blast radius — broadcasts here are
user-event-driven, not a stream. Fix (AbortController or monotonic
refresh token threaded through every reload) is invasive. Revisit
if a real ordering bug surfaces.

## Operational

### Hetzner server bootstrap — HOLD
*Source:* task #14 in the in-session task list.
Docker install + nginx + TLS + container on the Hetzner VPS.
**User decision (2026-05-12):** hold. Operator runs locally and
exposes via ngrok for now; full VPS deploy is not the current
distribution path. Revisit when SaaS hosting is on the table.

### Backward-compat cookie shim — CLEANUP
*Source:* this branch.
`auth._parse_cookie` still accepts legacy uid-only cookies (no
`session_version`) so existing admin sessions survive the next deploy.
Round 2 found this only works after the database has the
`users.session_version` column. Safe to remove after the first redeploy
and schema update invalidates all existing sessions naturally — they'll
have to log in once. Drop the shim in a follow-up commit.

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
