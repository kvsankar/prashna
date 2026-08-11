# Attendee Profiles Design

## Data Model

Extend `Participant` with nullable columns:

- `email VARCHAR(254)`
- `contact_number VARCHAR(40)`
- `organization VARCHAR(120)`
- `role VARCHAR(120)`
- `linkedin_url VARCHAR(500)`
- `current_work TEXT`
- `learning_goal TEXT`

The existing `name` column remains the display name. These fields are session-scoped because `Participant` is already scoped by `(session_id, voter_token)`.

## Migration

Prashna does not use Alembic. Add these columns to `app/db.py:_apply_additive_migrations()` so existing SQLite files are backfilled on startup.

## API

Extend existing participant self routes:

- `GET /api/sessions/{code}/me`
- `PATCH /api/sessions/{code}/me`

Add host/moderator list route:

- `GET /api/sessions/{code}/participants`

The list route uses the existing `require_mod_or_owner` authorization model, sorts by most recently seen first, and includes only rows with at least one profile field.

## Frontend

Participant page:

- Replace the single inline name input with a compact `Your profile` card.
- Submit profile fields together through the existing `/me` endpoint. After a
  submitted profile is loaded, prefill its values and label the action
  `Resubmit profile`.
- Keep the existing `#my-name` selector for current UI tests.

Moderator page:

- Add an `Attendee profiles` panel alongside questions/feedback.
- Render name/email/contact number/organization/role/LinkedIn/current work/goal when present.
- Refresh this panel on normal moderator refresh and participant websocket updates.

Admin session detail can remain unchanged in this slice; host visibility is covered by the moderator surface, which owners can also access without a mod-key.

## Test Architecture

- API tests in `tests/api/test_participants.py` cover self-profile persistence, trimming/nulling, moderator list authorization, and list filtering.
- UI tests in `tests/ui/test_participant.py` cover filling the profile form and persistence after reload.
- UI tests in `tests/ui/test_moderator.py` cover the moderator profiles panel rendering submitted details.
