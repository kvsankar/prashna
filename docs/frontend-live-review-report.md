# Frontend and Live-Client Review Report

Date: 2026-05-12

## Round 2 Re-Review (2026-05-12)

### Medium-High: Delegated moderators still see an owner-only Base URL control — **DONE**

**Fix:** `static/moderator.html` boot now hits `/api/admin/status` and sets an `isOwner` flag; `renderInvite()` hides the Base URL `.field` (input + Use-default button) when `isOwner` is false. QR / URL / Copy remain available to delegates.



`POST /api/sessions/{code}/participant_base_url` is now admin-cookie owner-only (`app/main.py:600`), but `static/moderator.html:41` still renders the Base URL input and "Use default" button for every moderator page. `saveModBaseUrl()` sends only the moderator headers available on that page (`static/moderator.html:143`), so a delegated moderator will receive `401`. The shared `api()` helper redirects to `/` on `401` outside the root page (`static/common.js:38`), which makes this look like a forced logout/navigation rather than a clear authorization boundary.

Recommendation: hide or disable the Base URL editor unless the page has owner/admin context, or split the moderator page into owner-only and delegate-visible controls. Add a UI test that opens `/m/{code}` with only a mod key and verifies owner-only controls are absent.

### Medium: Closed quiz runs still expose a rejected live-counts toggle — **DONE**

**Fix:** The per-run "live counts" checkbox is only rendered when `r.status !== "closed"`. UC-M-05 in `docs/specs.md` updated to document this.



The backend now allows `live_counts` only for queued and live runs and rejects closed runs (`app/main.py:1421`). The moderator UI still renders the checkbox for every run status (`static/moderator.html:326`), including closed history. Toggling it on a closed run creates a backend error path for an immutable historical record.

Recommendation: render the live-counts checkbox only for queued/live runs, or make it read-only on closed runs. Add a UI test for closed-run controls.

### Medium: Spec drift will keep producing frontend regressions — **DONE**

**Fix:** UC-M-11 in `docs/specs.md` now matches the owner-only Base URL backend and the two-tier UI. UC-A-06 already states owner-only auth. UC-M-05 notes the closed-run UI gating.



The spec now contains both owner-only and moderator-capable descriptions for participant base URL editing (`docs/specs.md:199`, `docs/specs.md:888`). Frontend work should not rely on stale UC-M-11 language until the role decision is reconciled.

Recommendation: update the spec first, then make the moderator page conditional on the resolved role model.

## Findings

### High: WebSocket reconnects do not resync missed state — **DONE**

**Fix:** `openLiveSocket` in `static/common.js` tracks an `everConnected` flag; on every reconnect after the first, it fires the existing message handler with `{type: "reconnect"}`. Each page's refresh function already responds to unknown message types by reloading, so this cascades into a full refetch. Skipped projector reconnect UI test left in place — the hard part is killing the shared uvicorn process from a Playwright test; covered indirectly by UC-D-03.



`openLiveSocket` reconnects with exponential backoff, but `onopen` only resets the retry counter (`static/common.js:65`). It does not trigger a refresh. If a client disconnects, misses the only relevant broadcast, then reconnects, it can remain stale until another state change occurs.

The projector reconnect UI test is skipped (`tests/ui/test_projector.py:158`), so this behavior is not covered.

Recommendation: let `openLiveSocket` accept an `onOpen` callback or invoke the existing message refresh on every reconnect after the first connection. Add a test with a controlled socket close/reopen.

### High: Moderator pages ignore session-state refreshes — **DONE**

**Fix:** Moderator `refresh()` now also calls `loadSession()`, so header, lifecycle controls, invite URL, and QR rerender on any broadcast (including `session_state` from a co-admin or delegate).



The moderator page passes `refresh` to `openLiveSocket` (`static/moderator.html:428`), but `refresh()` only loads queries, quiz runs, and presence (`static/moderator.html:422`). It does not reload the session itself. If another admin or delegate starts/ends the session, renames it, or changes the participant base URL, the moderator header, lifecycle controls, invite URL, and QR code stay stale.

Recommendation: include `loadSession()` in WebSocket refresh handling, or branch on message type and reload session data for `session_state`.

### Medium: Participants cannot clear a previously submitted multi-choice answer — **DONE**

**Fix:** The submit/update button is now enabled with an empty `pendingSelection` *if* the participant has already submitted (i.e. they're updating). First-time submits still require at least one selection.



For multi-choice questions, the UI can empty `pendingSelection` by toggling selected options off (`static/participant.html:205`), but the submit/update button is disabled whenever the set is empty (`static/participant.html:231`). The backend supports replacing a participant's submission with `answer_ids: []`, but the participant UI cannot send it.

Recommendation: allow an "Update answer" submission with an empty set when there was a prior submission. Add a UI test for multi-choice select, submit, clear, and update.

### Medium: Live refreshes can race and paint stale snapshots — **DEFERRED**

**Reason:** Real but low blast radius — broadcasts are throttled by user actions in this app, not by an event stream, so overlap is rare. The fix (AbortController or monotonic refresh token threaded through every reload function) is invasive and would touch every page. Will revisit if real-world ordering bugs surface. Tracking in code review notes.



WebSocket messages call async reload functions without sequencing, request cancellation, or latest-request guards (`static/common.js:67`, `static/participant.html:251`, `static/projector.html:63`, `static/moderator.html:422`). If two refreshes overlap, an older slower response can resolve last and overwrite newer UI state.

Recommendation: add a monotonically increasing refresh token or use `AbortController` so only the latest refresh can paint each surface.

### Low: Some core controls rely on placeholders or adjacent text instead of labels — **DONE**

**Fix:** Added `aria-label` attributes on moderator `#modkey-input` and `#base-url`, and participant `#my-name` and `#query-text`.



Examples include moderator key input (`static/moderator.html:29`), moderator base URL (`static/moderator.html:47`), participant name (`static/participant.html:16`), and participant query textarea (`static/participant.html:33`). These are core workflows for auth, identity, and asking questions.

Recommendation: add explicit labels or `aria-label` attributes and prefer role/label-based UI tests for these controls.

## Security Notes

No active untrusted `innerHTML` injection path was found in the reviewed role pages. Most untrusted values are rendered through text nodes. Image URLs remain a backend validation concern: admin-controlled `image_url` values are later assigned to `img.src` in quiz, participant, moderator, and projector views.

## Test Gaps

- Delegate moderator UI coverage for owner-only controls, especially Base URL editing.
- Closed quiz-run UI coverage for hidden/disabled immutable controls.
- Out-of-order refresh protection for live quiz state.
- Reconnect refresh after a missed WebSocket event remains indirectly covered only; the direct Playwright restart test is still skipped.
