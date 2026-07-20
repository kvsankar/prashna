# SDLC Work In Progress

Last Updated: 2026-07-19T19:51:03Z
Updated By: agent
Current Stage: code-create
Current Gate: verification-passed
Project Entry Mode: brownfield_baseline
Work Scope: slice/change
Ready To Implement: Yes
Review Level: Standard
Extra Checks: Security, Privacy and compliance, Reliability and operations,
Build and release, Documentation, UI and accessibility

## Resume Summary

Small feature slice: participant profiles now support an optional photograph.
The existing participant profile form did not ask for a photo. The change adds
a participant-scoped image upload endpoint, stores the uploaded URL on the
participant record, shows the photo on participant reload, allows clearing it,
and includes it in the moderator participant-profile panel.

`spec.md` and `design.md` were updated to reflect the new optional photograph
requirement and data/interface behavior. Because those approved artifacts
changed, the approval ledger should be refreshed only after explicit human
approval.

## Current Artifacts

- Process decision: `.sdlc/process-decisions.yaml`, unchanged.
  Records brownfield entry plus Standard review level and extra checks.
- Spec: `spec.md`, revised.
  Participant identity/profile requirements now include optional photograph.
  Draft check passed 7/7.
- Design: `design.md`, revised.
  Participant data and upload-file responsibilities now include profile
  photographs. Draft check passed 13/13.
- Plan: `plan.md`, unchanged.
  This was a small approved brownfield feature slice; no separate breakdown was
  created.
- Implementation: app, frontend source, and tests revised.
  `frontend/dist/` was rebuilt locally for UI verification but remains ignored
  by Git.
- Approval ledger: `.sdlc/approvals.yaml`, stale for `spec.md` and
  `design.md` after this feature update.

## Decisions And Assumptions

- Decision: participant photos use the existing image-upload constraints:
  `.png`, `.jpg`, `.jpeg`, `.gif`, and `.webp`, with the existing 5 MB limit.
- Decision: participants cannot set arbitrary `photo_url` values through the
  profile PATCH route; photos must be uploaded through the participant photo
  endpoint and can be cleared with `photo_url: null`.
- Decision: the admin upload route now reuses the shared upload helper while
  retaining admin authentication.
- Assumption: retaining uploaded files after a participant clears or replaces a
  photo is acceptable for this small feature; no existing cleanup lifecycle was
  present.

## Check And Review Evidence

- 2026-07-19: `check_update.py` emitted no Sarathi update notice.
- 2026-07-19: `check_spec.py --spec spec.md --json` passed 7/7.
- 2026-07-19: `check_design.py --design design.md --spec spec.md --json`
  passed 13/13.
- 2026-07-19: `npm run lint` passed TypeScript, ESLint, and Stylelint.
- 2026-07-19: focused participant photo API tests passed: profile round trip,
  upload and clear, unsupported type rejection, direct URL rejection, moderator
  profile summary, and additive migration.
- 2026-07-19: affected UI tests passed: participant profile persistence with
  photo upload/clear and moderator profile photo visibility.
- 2026-07-19: `uv run pytest tests/api -q` passed the full API suite.

## Results And Feedback

Expected Result: candidates can optionally submit a photograph with their
profile, and moderators can see it with the rest of the submitted profile.
Feedback From: local implementation checks and browser/API tests.
Feedback Status: incorporated
Current Work Group: participant-profile-photo
Current Work: ready for human review and approval refresh.
Parallel Limit: 1
What Changed: optional participant photograph storage, upload API, participant
UI controls, moderator rendering, migration coverage, and related tests.
Documents To Update: `spec.md`, `design.md`, `.sdlc/wip.md`, backend,
frontend, and test files were updated.
Stop Conditions: human rejection, failed refreshed checks, new privacy
requirement, or request for uploaded-file lifecycle cleanup.

## Open Questions And Blockers

- None.

## Next Recommended Action

Human review of the feature and refreshed approval for the changed
requirements/design documents.

## Bootstrap Status

Bootstrap File: CLAUDE.md
Status: not-offered
Notes: existing repository bootstrap remains unchanged.
