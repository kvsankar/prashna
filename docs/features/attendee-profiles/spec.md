# Attendee Profiles Spec

## Context

Prashna currently gives every attendee an anonymous per-session participant row and lets them optionally set a display name. Hosts can see names indirectly on questions and feedback, but there is no way to collect a lightweight attendee profile for follow-up.

## Goal

Collect optional attendee profile details from the participant page and make submitted profiles visible to the session host and delegated moderator.

## Non-Goals

- No required sign-in for attendees.
- No global attendee directory across sessions.
- No CSV export in this slice.
- No custom per-session profile fields in this slice.

## Requirements

- `AT-01`: A participant can view and update their own profile at `GET/PATCH /api/sessions/{code}/me`.
- `AT-02`: The profile fields are optional and scoped to the participant row for that session.
- `AT-03`: Supported fields are display name, email, optional contact number, organization, role/title, LinkedIn profile URL, what the attendee is working on now, and learning goal.
- `AT-04`: Blank submitted fields are stored and returned as `null`.
- `AT-05`: Fields are trimmed and length-limited: name 80, email 254, contact number 40, organization 120, role/title 120, LinkedIn URL 500, working-on-now 500, learning goal 500.
- `AT-06`: Hosts and delegated moderators can list attendee profiles for a session.
- `AT-07`: The host/moderator list returns only participants who have provided at least one profile field.
- `AT-08`: The participant page exposes the profile collection fields and saves them without blocking Q&A, quiz, or feedback workflows.
- `AT-09`: The moderator page exposes a profiles panel that shows collected profile details and updates after participant changes.
- `AT-10`: Existing SQLite deployments receive additive profile columns without deleting data.

## Privacy Notes

The profile form must stay visibly optional. Attendee profile details are host/moderator-visible session data, not public projector data.
