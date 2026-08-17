# SDLC Work In Progress

## Product Snapshot

Status Result: Ready

Status Summary: The documentation set has been curated into live versioned
guidance and immutable local-only records. The user approved the current system
specification and design. No documentation work remains in this increment, and
it does not alter application behavior.

Goal: Keep Prashna's current behavior, UX, deployment, distribution, and
performance operations documented without versioning one-off process history.

Working Today: The single-process application, container distribution,
Hetzner deployment, Cloudflare proxy, CI publication, and performance
instrumentation are implemented and reflected in the live docs.

Reusable Today: `docs/specs.md`, `docs/UX.md`, `spec.md`, `design.md`, and the
focused operator runbooks remain the current maintained sources.

Current Increment: Documentation lifecycle consolidation, complete and
approved. One-off reviews, assessments, completed plans, proposals, generated
reports, and dated investigations remain in the local checkout but leave Git
tracking and are covered by `.git/info/exclude`.

Remaining Shared Work: None for this documentation increment.

Target-Owned Work: The GitHub OAuth first-run affordance and legacy admin-cookie
shim cleanup remain in `docs/todo.md` as separate future changes.

Deferred: Product ideas needing decisions remain in the deferred appendix of
`docs/specs.md`; broader hosted operation still requires explicit bootstrap,
migration, and shared WebSocket designs.

Before Coding: None for the documentation increment. New behavior work needs
its own accepted scope.

Next Action: Begin the next separately scoped product or operations change;
none is required for this documentation increment.

## Process Snapshot

Last Updated: 2026-08-17T14:19:47Z
Updated By: agent
Current Stage: code-review
Current Gate: approved-for-next-stage
Project Entry Mode: brownfield_baseline
Work Scope: product/system
Ready To Implement: Yes
Delivery Assurance Profile: Standard
Approval Policy: Human checkpoints
Work Outcome: Decision/evidence
Extra Checks: Documentation, Reliability and operations, Build and release

## Current Artifacts

| Kind | Path | Status | Notes |
| --- | --- | --- | --- |
| Behavior contract | `docs/specs.md` | live | Detailed use cases and test contracts; documentation check passes. |
| UX system | `docs/UX.md` | live | Governing frontend design rules; unchanged in this increment. |
| System spec | `spec.md` | approved | Source hierarchy and current follow-up ownership clarified; structural check passes. |
| System design | `design.md` | approved | Production posture corrected; structural check passes. |
| Engineering follow-ups | `docs/todo.md` | live | Contains only current actionable and hosted-operation prerequisites. |
| Operations | `deploy/README.md`, `distribution/README.md`, `performance/README.md` | live | Focused production, portable distribution, and performance runbooks. |
| Historical records | local-only paths in `.git/info/exclude` | immutable | Preserved in the checkout, intentionally not versioned. |

## Decisions And Assumptions

- User decision: documentation consists of live maintained docs and immutable
  one-off records; one-off records are local-only through `.git/info/exclude`.
- Decision: `docs/specs.md` and `docs/UX.md` remain the detailed governing
  behavior and UX sources. `spec.md` and `design.md` remain system-level views.
- Decision: dated performance investigation is historical; current measurement
  and diagnosis guidance is consolidated into `performance/README.md`.
- Assumption: staged removal from Git plus ignored local preservation satisfies
  the requirement not to version one-off records.

## Check And Review Evidence

- 2026-08-17: dryscope scanned 30 documents and 371 sections at 0.90 and
  0.80 similarity thresholds; it found no near-duplicate section pairs.
- 2026-08-17: `check_spec.py spec.md --json` passed all structural gates.
- 2026-08-17: `check_design.py design.md --spec spec.md --json` passed all
  structural gates.
- 2026-08-17: `uv run pytest tests/api/test_docs_contracts.py -q` passed.
- 2026-08-17: staged and unstaged diff whitespace checks passed.
- 2026-08-17: the user explicitly approved the revised documentation;
  `.sdlc/approvals.yaml` records current hashes for `spec.md` and `design.md`.

## Results And Feedback

Expected Result: A fresh checkout contains only documentation that is expected
to remain current, while this checkout retains immutable one-off evidence
without Git tracking noise.

Feedback From: Explicit user documentation guidance plus repository source,
tests, deployment files, release state, and dryscope analysis.

Feedback Status: received

Feedback Evidence: User instruction in the current task, explicit approval of
the revised documentation, and the checked live documentation diff.

Current Work Group: none

Current Work: documentation-lifecycle-consolidation

Parallel Limit: 1

What Changed: One-off records were separated from the versioned live set;
status, deployment, performance, and follow-up guidance were corrected and
consolidated.

Documents To Update: None known after this increment.

Stop Conditions: Human rejection of the live/one-off classification, failed
verification, or a request to preserve a specific one-off artifact in Git.

## Open Questions And Blockers

- None for committing the documentation increment.

## Bootstrap Status

Bootstrap File: CLAUDE.md
Status: injected
Notes: The accepted documentation lifecycle and authority rules are now part of
the repository guidance.
