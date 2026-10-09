# Prashna outstanding work

Last reviewed: 2026-08-17.

This is the live engineering follow-up ledger. It does not repeat proposed
features or product decisions; those remain in the
[`Deferred (decision needed)`](specs.md#deferred-decision-needed) appendix of
the behavior specification.

## Current actionable follow-ups

### Remove the legacy admin-cookie compatibility shim

`prashna/auth.py::_parse_cookie` still accepts the old signed cookie containing
only a user id and treats it as session version 1. Current cookies contain both
the user id and session version.

Remove the fallback once compatibility with installations predating the
session-version rollout is no longer required. Keep the password-change cookie
invalidation tests.

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

## Completed operational work

The Hetzner bootstrap, container-directory ownership, CI/GHCR publication,
versioned release bundle, production deploy, Cloudflare proxy preparation,
HTTP/2 enablement, and performance instrumentation are implemented. Do not
reopen them from historical plans or review reports without new evidence.
