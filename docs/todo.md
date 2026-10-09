# Prashna engineering backlog

This is the list of open engineering follow-ups. Product ideas that need a
decision are in the
[`Deferred (decision needed)`](specs.md#deferred-decision-needed) appendix of
the behaviour specification.

## Current follow-ups

### Remove the legacy admin-cookie compatibility shim

`prashna/auth.py::_parse_cookie` still accepts the old signed cookie containing
only a user id and treats it as session version 1. Current cookies contain both
the user id and session version.

Remove the fallback once compatibility with installations predating the
session-version rollout is no longer required. Keep the password-change cookie
invalidation tests.

### Split `prashna/main.py` by resource

`prashna/main.py` has about 2800 lines. Split it by resource (sessions,
queries, quizzes, quiz runs, uploads, admin) in a separate change made
outside a live event.

### Give the Hetzner data-folder variable its own name

`PRASHNA_DATA_DIR` means two things. The `prashna` command reads it as the
folder for the database and uploads. `deploy/docker-compose.yml` reads it as
the host folder mounted at `/data`. Renaming the Compose variable (for
example to `PRASHNA_DATA_HOST_DIR`, matching `PRASHNA_UPLOADS_HOST_DIR`) would
remove the clash.

### Ignore `secret-key` and `setup-token` in a source checkout

Running from a source checkout creates `secret-key` and `setup-token` in the
repository root. `.gitignore` does not list them, so they could be committed.

### Rate-limit participant photo uploads

`POST /api/sessions/{code}/me/photo` needs no admin login and has no rate
limit. Anyone with a session code can store images of up to 5 MB each.

### Close test gaps

- No tests flood the feedback and performance-beacon rate-limit buckets
  (UC-X-08).
- The tests for UC-X-10 and UC-X-11 do not follow the `test_uc_<role>_<nn>`
  naming convention.
- No automated test runs an end-to-end journey from `specs.md`.
- No load test checks the 100-person room and 1000 ms latency targets.

## Required before broader hosted operation

These do not block the current single-process, single-operator deployment:

- Add a database-enforced singleton/bootstrap invariant before introducing
  multiple workers or replicas; the current process lock is sufficient only
  for the documented single-process model.
- Introduce a general migration tool before a non-additive schema change. The
  current additive SQLite bridge remains the supported production mechanism
  for known columns and indexes.
- Replace the in-memory WebSocket hub with shared pub/sub before running more
  than one application process.
