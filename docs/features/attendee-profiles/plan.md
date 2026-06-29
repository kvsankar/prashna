# Attendee Profiles Plan

## Planned Touch Set

- `docs/features/attendee-profiles/{spec,design,plan}.md`
- `app/models.py`
- `app/db.py`
- `app/main.py`
- `frontend/participant.html`
- `frontend/moderator.html`
- `frontend/src/participant.ts`
- `frontend/src/moderator.ts`
- `frontend/src/types.ts`
- `tests/api/test_participants.py`
- `tests/ui/test_participant.py`
- `tests/ui/test_moderator.py`

## TDD Order

1. Add API tests for `GET/PATCH /me` profile fields and `GET /participants`.
2. Run the focused API tests and confirm red.
3. Add UI tests for participant profile persistence and moderator profile visibility.
4. Run the focused UI tests and confirm red.
5. Implement model columns and additive SQLite migration.
6. Implement serializers/routes.
7. Implement participant profile card.
8. Implement moderator profiles panel.
9. Run focused API/UI checks, frontend lint/build, then full test suite if focused checks pass.

## Review Gates

- Spec review: requirements are small enough for one PR and each acceptance criterion maps to a test.
- Design review: profile data stays session-scoped, optional, and non-public.
- Plan review: implementation remains inside the planned touch set.
