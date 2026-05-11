# Prashna UX system

A small design system to keep the app coherent as it grows. Patterns are
intentionally opinionated — pick *one* way to do each thing.

Apply by analogy: if you need a new screen, find the closest pattern
below and stay inside its rules. If no pattern fits, propose a new one
here *before* shipping a one-off.

---

## 1. Visual tokens

Defined as CSS variables in `static/app.css`. Don't hardcode hex outside
the token list.

| Token         | Use                                                  |
| ------------- | ---------------------------------------------------- |
| `--bg`        | Page background                                      |
| `--panel`     | Card / surface background                            |
| `--panel-2`   | Inset surface (rows, inputs, options)                |
| `--text`      | Primary text                                         |
| `--muted`     | Secondary text, labels, metadata                     |
| `--accent`    | Primary brand, default action                        |
| `--accent-2`  | Hover, links                                         |
| `--good`      | Success, "ready", "correct"                          |
| `--bad`       | Error, destructive, "wrong"                          |
| `--warn`      | "Draft", in-progress                                 |
| `--border`    | Dividers, neutral borders                            |

**Spacing scale (rough):** 4 / 6 / 8 / 12 / 16 / 20 / 28 / 40 px.
Use multiples; don't invent values.

**Radii:** 4 (chip), 6 (small control), 8 (input, button, row), 12 (card).

**Type sizes:** 11 (badge), 12 (table header), 13 (small/body-dense),
14 (body), 16 (h2/section), 18 (h1/page), 24+ (display/projector).

---

## 2. Surface taxonomy

Every screen is one of **three densities**:

| Density          | Used for                  | Typical type | Spacing |
| ---------------- | ------------------------- | ------------ | ------- |
| **Work** (dense) | Admin, moderator surfaces | 13 px        | 6–8     |
| **Read**         | Participant on phones     | 14–16 px     | 12–16   |
| **Display**      | Projector                 | 20–48 px     | 16–40   |

Use `<section class="card compact">` for work surfaces and `<section
class="card">` for read surfaces.

A page never mixes densities. If a moderator surface needs a read-style
component (e.g., a live quiz preview), embed it in its own card with
the read density.

---

## 3. Page chrome

- Every page has a top `<header class="top">` with: page title (left),
  navigation/meta (right). One line. No subnav for now.
- `main` is centered, max-width 900 px (`main`) or 1200 px
  (`main.wide` for dense admin views).
- No breadcrumbs (depth is shallow). Back-link in the header right
  (`← home`) if the page is not `/`.

---

## 4. Card pattern

A **card** is the single layout unit. Pages are sequences of cards.

```
<section class="card [compact]">
  <div class="card-head">
    <h2>Card title</h2>
    <div class="card-tools">…create/filter controls…</div>
  </div>
  <!-- content -->
</section>
```

- `card-head` houses the section title on the left and the "tools" on
  the right (create input + button, filter, sort, etc).
- One H2 per card. H3+ inside a card is rare; prefer separate cards.
- Cards stack vertically. No horizontal card grids except in galleries
  (none today).

---

## 5. Lists: tables vs cards-per-row

**Default to a compact table for work surfaces.** Use `class="ctable"`.

```
<table class="ctable">
  <thead>
    <tr><th>Name</th><th>Status</th><th class="num">Count</th><th class="actions">Actions</th></tr>
  </thead>
  <tbody>
    <tr class="rowable">
      <td>Item</td>
      <td><span class="badge badge-ready">Ready</span></td>
      <td class="num muted">5</td>
      <td class="actions">
        <button class="ghost xsmall">Edit</button>
        <button class="danger ghost xsmall">Delete</button>
      </td>
    </tr>
  </tbody>
</table>
```

**Use cards-per-row only when:**
- Items have rich, varying content (e.g., a question's text + image
  + answer + votes).
- The surface is a read-density page (participant or projector).

**Column rules:**
- Status as a badge, second column when present.
- Numeric columns get `class="num"` (right-aligned, tabular nums).
- Actions are the last column, `class="actions"`, right-aligned.
- Default sort: most recent first; surface other sorts only on demand.

**Row interaction:** the whole row is clickable to drill in (`class=
"rowable"`). Buttons inside the row use `event.stopPropagation()`. A
selected drill-in row gets `class="rowable selected"`.

**Empty state:** a `<tr><td colspan>` with muted small text *plus* a
hint about how to create (e.g., "No quizzes yet. Add one using the
title field above."). Never an empty `<tbody>`.

---

## 6. Detail pattern (drill-down)

When a row is clicked, expand a **detail card below** the list. Only
one detail card is open at a time per page.

```
<section class="card compact" id="detail-card">
  <div class="card-head">
    <h2 id="detail-title">Detail: …</h2>
    <button class="ghost small" id="detail-close">Close</button>
  </div>
  <div id="detail-body">…</div>
</section>
```

- The detail card's `h2` names the *thing* ("Quiz: Intro to Python"),
  not the operation ("Edit").
- A close button is the only way out; clicking another row swaps
  contents in place.
- Detail content uses the same density as the parent list.
- If a single page needs two distinct drill-downs (e.g., one for
  quizzes, one for quiz sessions), use two separate detail cards —
  don't time-share one slot.

**Alternative when content is small:** inline expansion of the row
itself with `tr.expanded > td.detail-cell` content. Reserved for
< 5 lines of detail.

---

## 7. CRUD patterns

### Create

- **Inline composer** in the parent card's `card-head` `.card-tools`:

  ```
  <input class="inline" placeholder="New quiz title">
  <button class="primary small">+ New</button>
  ```

- The button text always starts with **`+`** and a noun: `+ New`,
  `+ Add option`, `+ Add question`. Never just "Add" without context.
- A successful create scrolls/opens the new item in the detail pane.
- **Use a modal only** when creation requires fields that can't fit in
  a single inline input (rare). Modals are last resort.
- **Never a separate "New ___" page.** Don't navigate away.

### Read

- See **§5 Lists** and **§6 Detail**.
- The detail view always shows the entity's lifecycle (badges, parent
  context). It's a *passport*, not a form.

### Update

- **Inline edit in the detail pane.** Each field is a live input.
- **Persist on `blur` / `change`.** No Save button.
- After save: refresh the parent list (so the row reflects the new
  state), keep the detail pane open.
- **Optimistic updates** for cheap mutations (toggles, votes). Roll
  back visually on error.
- **Pessimistic refresh** for structural changes (adding a question,
  reordering) — re-fetch and re-render the detail.

### Delete

- A **`danger ghost xsmall`** button in the row's actions column.
- Confirms with native `confirm("Delete this ___?")` for now. Replace
  with a modal once we have a modal pattern.
- On success: remove the row immediately, close the detail pane if it
  was showing that entity.
- **No soft-delete or undo** until we have a real audit need. Don't
  build "undo" speculatively.

### Status transitions

Entities with lifecycle (Quiz, QuizSession, Question) use **explicitly
named verb buttons**, never a status dropdown:

- `Publish` / `Unpublish` (not "set status to ready")
- `Start` / `Close` / `Reveal` (not "advance state machine")
- `Hide` / `Unhide`
- `Mark answered` / `Unmark`

Why: each transition has different validation rules and side effects;
forcing the user to think in verbs prevents accidental jumps.

A failed transition (e.g., publish-but-incomplete) shows the validation
message in a banner attached to the detail pane, not an `alert()`.

### Bulk actions

Deferred until any list exceeds ~50 rows. When we add them:
- Checkbox in column 1, "Select all" in header.
- Bulk action bar appears as a sticky strip when ≥ 1 row selected.

---

## 8. State patterns

### Loading

- For full-card loads: a single muted `<tr><td colspan>Loading…</td>`
  in the table body. No spinner.
- For inline actions: button shows its label unchanged but is disabled
  until the request returns. No spinners on buttons.
- **Never block the whole page** with a loader.

### Empty

Always a *primer*, not a blank: muted small text + a pointer to the
create affordance.

> "No sessions yet. Create one above to share a code with your
> audience."

### Error

| Kind                 | Surface                                                      |
| -------------------- | ------------------------------------------------------------ |
| Transient action     | Toast (bottom right), 2.5s                                   |
| Form / sticky error  | `.error-banner` *inside* the affected card, until dismissed  |
| Blocking failure     | Banner on the page; no modal                                 |
| Auth expired         | Redirect to `/` (handled in `api()`)                         |

**Never** raw `alert()` for new code. (Legacy uses it; migrate as
touched.)

### Info / lifecycle hint

`.info-banner` inside the detail pane, e.g., "This quiz is Ready —
editing will revert it to Draft."

---

## 9. Form / field patterns

- One field per row in vertical forms (`.field > label + input`).
- Use **inline fields** (`<input class="inline">`) for single-field
  composers in `card-tools` or detail rows.
- Labels above inputs, not floating. Placeholder is a hint, not a
  label.
- Required-field markers and inline validation: deferred until we have
  a form that actually fails on submit-time.
- **Always autocomplete-correct**: `autocomplete="username"`,
  `"current-password"`, `"new-password"`, etc.
- `autocapitalize="characters"` on code inputs.

---

## 10. Buttons

| Class           | Use                                                       |
| --------------- | --------------------------------------------------------- |
| `.primary`      | The single most important action on the surface           |
| (default)       | Secondary actions                                         |
| `.ghost`        | Tertiary / link-like; no background                       |
| `.danger`       | Destructive; pair with `.ghost` for low-visual-weight     |
| `.small`        | Inside dense tables / `card-tools`                        |
| `.xsmall`       | Row actions inside `.ctable`                              |

- Verb-first labels: "Publish", "Delete", "Open moderator →".
- One primary button per card. Two primaries on one surface is a smell.
- Cancel / dismiss is a `.ghost`, never colored.

---

## 11. Badges & status

Use `.badge` for any lifecycle state. Per-state classes follow the
pattern `badge-<state-slug>`:

- `badge-draft` (warn yellow)
- `badge-ready` (good green)
- `badge-live` (good green)
- `badge-closed` (muted grey)
- `badge-answered`, `badge-hidden`, etc. — add as needed.

Badges are read-only. Don't make them clickable. If you need to *change*
state, use a verb button (§7 Status transitions).

---

## 12. Keyboard

- **Enter** submits the obvious form on any single-field composer
  (`+ New`, login, join code).
- **Cmd/Ctrl+Enter** submits multiline composers (textarea: ask a
  question).
- **Escape** closes the detail pane.
- Tab order matches reading order; trust the natural DOM order, don't
  override `tabindex` unless you have to.
- Every interactive element is reachable by keyboard. No
  `<div onclick>` for primary actions — use `<button>`.

---

## 13. Links vs buttons

- **`<a>`** = "navigate somewhere" (`/m/CODE`, `/quizzes`).
- **`<button>`** = "do something here" (publish, delete, start).
- A "thing that opens in a new tab" is an `<a target="_blank">`, not a
  styled button.

---

## 14. Modals

Reserved for the rare case where work must block. Today we have *none*.
When we add one:

- Centered overlay on `rgba(0,0,0,0.5)`.
- `Esc` and click-outside both dismiss.
- Primary action on the right, ghost cancel on the left.
- Never use a modal for create — see §7 Create. Never use a modal for
  delete confirmation once we have a confirm-modal helper — until then,
  `confirm()` is acceptable.

---

## 15. Lifecycle visibility (cross-cutting)

Every entity with state must show that state in three places:
1. **Its row** in the parent list (badge column).
2. **Its detail header** in the drill-down.
3. **Anywhere it's referenced** (e.g., the moderator's quiz dropdown
   says "Q1 (5 q)" — but won't list drafts at all, applying §17).

---

## 16. Don't show what the user can't act on

- Hide controls the current role can't use, don't disable them.
- Filter lists by what the current viewer can act on:
  - Moderator's quiz dropdown → only `ready` quizzes.
  - Participant's question list → only `not hidden` questions.
  - Admin's session list → all sessions.
- Disabled state is reserved for transient blocks ("submit while
  loading"), not for permission.

---

## 17. Anti-patterns

- ❌ A modal for editing or creating.
- ❌ A "Save" button next to a text field that already persists on
  blur.
- ❌ Status as an editable dropdown.
- ❌ Native `alert()` for non-blocking errors.
- ❌ Stretching one detail pane to host two unrelated entities.
- ❌ Mixing densities in one page.
- ❌ Empty states that just say "Nothing here."
- ❌ `<div onclick>` for primary actions.
- ❌ Pre-baking secret-containing URLs into the DOM.

---

## 18. Adding a new pattern

If you need a screen this doc doesn't answer:

1. Pick the closest pattern above and try to bend the new screen to it
   for 10 minutes.
2. If it genuinely doesn't fit, add a section here *before* coding,
   with: name, when to use, structure, example, anti-patterns.
3. Link to it from any feature PR that uses it.

Coherence > novelty.
