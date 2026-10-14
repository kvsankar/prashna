# Prashna UX system

A small design system to keep the app coherent as it grows. Patterns are
intentionally opinionated — pick *one* way to do each thing.

Apply by analogy: if you need a new screen, find the closest pattern
below and stay inside its rules. If no pattern fits, propose a new one
here *before* shipping a one-off.

---

## 1. Visual tokens

Every colour, tint, corner radius, font weight, shadow, type size and
control size is a CSS custom property in `frontend/src/tokens.css`.
The component styles in `frontend/src/app.css` use the tokens through
`var(...)`; they never hold the raw value.

| Group | Tokens | Use |
| --- | --- | --- |
| Surfaces | `--bg`, `--panel`, `--panel-2`, `--border` | Page, card, inset surface (rows, inputs, options), dividers |
| Text | `--text`, `--muted`, `--on-accent`, `--on-accent-muted` | Primary text, secondary text, text on an accent fill |
| Roles | `--accent`, `--accent-2`, `--good`, `--warn`, `--bad` | Primary action, links and hover, success, needs work, destructive |
| Tints | `--accent-bg`, `--good-bg`, `--warn-bg`, `--bad-bg`, `--neutral-bg`, `--hover-bg` | Badge, banner, selection and result-bar backgrounds |
| Controls | `--control-bg`, `--control-bg-hover`; `--control-h` 40, `--control-h-sm` 32, `--control-h-xs` 24; `--control-px*`; `--tap-min` 32 | Control fill, the three control heights and their side padding (§10), the touch minimum (§16a) |
| Corners | `--radius-sm` 4, `--radius-md` 6, `--radius-lg` 8, `--radius-xl` 12, `--radius-pill`, `--radius-round` | Chips and images; extra-small controls and menu items; controls, inputs and rows; cards and panels; badges; avatars |
| Weights | `--weight-medium` 500, `--weight-semibold` 600, `--weight-bold` 700 | Controls; labels and badges; titles |
| Type | `--text-xs` 11 … `--text-5xl` 48 | 11 badge, 12 table header, 13 dense body, 14 body, 16 section, 18 page, 24+ projector |
| Spacing roles | `--gap-tight` 4, `--gap-related` 8, `--gap-group` 12, `--pad-card` 16, `--gap-section` 24, `--pad-page` 24, `--pad-projector` | See "Spacing" below |
| Spacing steps | `--space-1` 4, `--space-2` 8, `--space-3` 12, `--space-4` 16, `--space-5` 24, `--space-6` 32, `--space-7` 48 | The margin utilities (`.mt-2` and so on) and the projector's larger scale |
| Other | `--shadow-menu`, `--shadow-toast`, `--nav-bg`, `--overlay-bg`, `--overlay-text`, `--backdrop`, `--star`, `--qr-bg`, `--proj-bg`, `--proj-hint` | Menus and the confirmation dialog, toasts, sticky nav, QR lightbox, the confirmation dialog's backdrop, star ratings, QR codes, projector |

Add a token rather than a one-off value.

### Spacing

Spacing says how things relate. Space inside a component is smaller than
space between related items, which is smaller than space between groups
and between sections. Pick the role, not a pixel value:

| Role | Size | Use |
| --- | --- | --- |
| `--gap-tight` | 4 px | Inside a control; a badge beside its text; a label above its field |
| `--gap-related` | 8 px | Controls in a toolbar; actions in a row; items in a list |
| `--gap-group` | 12 px | Form fields; a card's header to its content; padding inside a list item |
| `--pad-card` | 16 px | Inside a card, panel, banner or toast |
| `--gap-section` | 24 px | Between cards and sections |
| `--pad-page` | 24 px | The page gutter |

The steps (4, 8, 12, 16, 24, 32, 48 px) grow by about 1.5 times, so each
is visibly different from the next; in-between values add rules without
adding meaning. On phones (720 px and narrower) `--pad-page` and
`--gap-section` drop to 16 px, so content keeps its width.

### How the tokens are enforced

- **Stylelint** (`.stylelintrc.json`, run by `npm run lint`, pre-commit and
  CI) rejects, in every stylesheet except `tokens.css`: hex colours,
  named colours, colour functions (`rgb()`, `rgba()`, `hsl()` and so on),
  any `font-size`, `font-weight`, `border-radius` or `box-shadow` that is
  not the matching token, and any `padding`, `margin` or `gap` that is not
  a spacing token, `0` or `auto` (controls derive their padding from
  their height). An inset accent stripe
  (`box-shadow: inset 3px 0 0 var(--accent)`) is allowed.
- **No styles outside stylesheets.** Pages have no `<style>` blocks, and
  markup and scripts never set inline styles. Use a class: a spacing
  utility (`.mt-2`, `.mb-2`, `.grow`, …) or a component class
  (`.label-col`, `.qr-box`, `.url-box`, `.card.inset`).
- Show and hide with the `hidden` attribute through `setVisible()` from
  `common.ts`; `[hidden]` overrides any display rule.
- The one allowed script write is a CSS custom property carrying data,
  e.g. a result bar's `--share`.
- `tests/api/test_frontend_contracts.py` enforces the last three rules and
  that the control sizes come from the control-height tokens.
- **Text contrast.** Text colours meet WCAG AA (4.5:1) on the surfaces
  they sit on: `--on-accent` on `--accent` (primary buttons), `--bad` on
  `--panel`, `--panel-2` and an error banner's tint, and `--muted` on
  `--panel-2`. Don't use `--accent` for text; use `--accent-2` for links
  and `--text` for a state cue such as "voting closed".
  `test_text_colours_meet_wcag_contrast` computes the ratios from
  `tokens.css`.

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
  navigation/meta (right).
- `main` is centered, max-width 900 px (`main`) or 1200 px
  (`main.wide` for dense admin views).
- Interactive role surfaces use a shared `<div class="page-nav">`
  immediately below the header. Its `nav.breadcrumbs` identifies the
  hierarchy and provides an up link; its `nav.section-links` jumps to
  the important sections of long pages. The bar is sticky on desktop
  and wraps into two rows on narrow screens.
- The session page (`/m/<code>`, shared by the admin owner and
  delegate moderators) is the most complete example: **Sessions →
  session** plus Lifecycle, Set up, Quiz, Questions, Profiles, and
  Feedback section links. A section link that targets a collapsed
  `<details>` opens it before scrolling.
- The participant surface uses the same pattern with read-appropriate
  section links. The projector remains the exception: as a public
  presentation surface it has no interactive chrome.
- Admin pages start the breadcrumb at **Sessions** (`/`). On the session
  list itself, Sessions is the only item and is the current page, not a
  link. The quiz library reads **Sessions → Quiz library**. The
  participant page starts at **Prashna**, because participants cannot
  open the session list. The breadcrumb is the way up, so the header has
  no separate home link.
- Each page has one name, used in its links, breadcrumb and tab title:
  **Sessions** (`/`), **Quiz library** (`/quizzes`), **Session page**
  (`/m/<code>`), **Participant view** (`/s/<code>`) and **Projector**
  (`/p/<code>`). Tab titles end in "— Prashna": "Sessions — Prashna",
  "Quiz library — Prashna", "<session title> — Prashna" for the session
  page, and "<session title> · Participant view — Prashna" and
  "<session title> · Projector — Prashna" for the other session views.

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

### Answer options

Answer options are one component: `answerOption()` in `common.ts`
(UC-X-14). Pass what the surface needs — `onPick` (participant only, makes
it a button), `share`/`count` (result bar and "n (p%)"), `correct`/`wrong`
(after reveal), `selected` + `chosenLabel`. Don't build `.option` markup
by hand. A correct answer always says "✓ Correct" in text, so correctness
never depends on colour alone. The same holds for the viewer's own pick
after reveal: a wrong pick shows ✗ and "Your answer · wrong", never the ✓
of a chosen answer.

### Rows wrap by default

`.row`, `.card-head`, `card-tools`, `header.top`, and `.page-nav` wrap
when their contents don't fit, so controls drop to a new line on a phone
instead of pushing the page sideways. A row that must stay on one line
(a vote button beside its question, the five rating stars, an answer
option) says so: `.row.nowrap` or `flex-wrap: nowrap` in its component
rule. Every flex container in `app.css` declares `flex-wrap` (or is a
column); `tests/api/test_frontend_contracts.py` enforces it.

### Operational vs. creational, and the collapsible "Set up" group

A work surface often mixes **creational/setup** controls (things you do
*before or between* the live action — invite people, stage a quiz) with
**operational** controls (things you do *during* it — start/reveal/close
a quiz, moderate questions). Don't interleave them. Group the creational
cards inside a collapsible `<details class="setup">` disclosure so the
operational surface stays uncluttered.

```
<details class="setup" id="setup-section">
  <summary class="setup-summary">
    <span class="setup-title">Set up</span>
    <span class="muted small">one-line hint</span>
  </summary>
  <section class="card">…creational card…</section>
  <section class="card">…creational card…</section>
</details>
```

- Each grouped block stays its own `<section class="card">` (one H2 each).
- Default open/closed by lifecycle: open while still being prepared
  (`planning`), collapsed once `live`. Set `.open` **once on load** — not
  on every refresh, or you'll fight the user's manual toggle.
- First use: the session page — Invite and, for the admin owner, Session
  settings live in "Set up"; the live Quiz + Q&A panels stay operational
  below. Adding a quiz is operational (presenters add one mid-session), so
  its **+ Add quiz** composer sits in the Quiz card header, not in Set up.

### Overflow menu (`<details class="menu">`)

When a row or card has one or two **primary** actions plus several
**rare/secondary** ones, keep the primary actions inline and move the rest
into a **⋯ overflow menu** so the row reads cleanly. Use a `<details>`
disclosure (not a custom popover) for keyboard/no-JS robustness.

```
<details class="menu">
  <summary aria-label="More actions">⋯</summary>
  <div class="menu-panel">
    <button>Secondary action</button>
    <button>Show X to audience</button>   <!-- verb toggle, not a checkbox -->
    <button class="danger ghost">Destructive action</button>
  </div>
</details>
```

- Inline = what you do most turns; menu = end/configure/delete. Keep the
  inline set to ~2–4 actions; relegate the rest (per NN/g + PatternFly).
- Menu items are **verb buttons**, including toggles — a state toggle
  reads "Show X" / "Hide X" (which flips on click) rather than a checkbox,
  which is clumsy in a menu and hides its meaning.
- **Separate the destructive action** with a `.menu-sep` divider above it,
  and color it (`danger`), so it isn't mis-clicked next to safe items.
- The `⋯` summary carries both an `aria-label` and a visible `title`
  tooltip (NN/g: don't ship a bare icon with no text cue), and stays
  visible without hover with enough contrast/hit-area.
- The panel is absolutely positioned (`right: 0`). Close it on **outside
  click and Esc** (native `<details>` only toggles on its own summary) —
  bind those handlers once at document level so they survive re-renders.
  Actions also re-render the row, which closes the menu, so confirm a
  silent toggle with a toast.
- First use: the moderator quiz-run row keeps the morphing primary +
  ← Prev inline; "Finish quiz", the Show/Hide vote-counts toggle, and
  the destructive run action live in the ⋯ menu. Queued rows say
  **Remove from session**; live rows say **Delete run (discard results)**.
  An ended session never offers Start for a legacy queued row, but keeps
  **Remove from session** available so the orphan can be cleaned up.
- The quiz library row keeps Publish/Unpublish and **Add to session**
  inline; Duplicate, Export JSON, Export Excel, and Delete live in its ⋯
  menu. **Add to session** is itself a `<details class="menu">` whose
  panel lists the open sessions as verb buttons — a menu, not a modal,
  because it is one click deep.
- **Export ▾** (UC-A-30) is a small `details.menu.export-menu` in a card's
  head or tools whose panel holds two download links, JSON and
  Excel (`exportMenu()` in `common.ts`). Downloads are links (`<a download>`),
  not buttons: they change nothing, and the admin cookie authenticates them.
  Picking one closes the menu. Show it only to the owner (§16).

---

## 5. Lists: tables vs cards-per-row

**Default to a compact table for work surfaces.** Use `class="ctable"`.

The global quiz-run report supports four explicit views: **Flat**,
**By quiz**, **By version**, and **By session**. Use a compact
`aria-pressed` button group in the card tools. Grouped views retain the
same run columns inside open `<details class="run-group">` sections so
the data remains comparable; the selection is reflected in the
`?runs=` URL parameter for bookmarking and browser history.

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
selected drill-in row gets `class="rowable selected"`. When the thing a
row names has its own page (a session and its session page), the row
navigates there instead of opening a detail card, and its title cell is
a real link so it also works from the keyboard.

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
  quizzes, one for quiz runs), use two separate detail cards —
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
  `+ Add option`, `+ Answer`. Never just "Add" without context.
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

### Reorder

- Each item in an ordered list carries a **drag handle** (`⠿`,
  `.drag-handle`, `aria-label="Drag to reorder"`) plus **Move up** /
  **Move down** icon buttons (`↑` / `↓` with `aria-label`s naming the
  item, e.g. "Move question up"). Disable Move up on the first item and
  Move down on the last.
- Drag uses pointer events with `touch-action: none` on the handle, so it
  works with a mouse and on touch screens. The browser's HTML5
  drag-and-drop is not used; it doesn't fire on touch devices.
- While dragging, the item follows the pointer by moving in the DOM
  (`.dragging` style); the page auto-scrolls near the viewport edges.
- On drop, send the **whole new order** in one request (`PUT …/…_order`
  with every id) and re-render from the response — never one PATCH per
  moved item, which leaves duplicate positions when a request fails.
- First use: questions and answers in the quiz editor.

### Insertion point

Adds an item at a chosen place in an ordered list, so it doesn't have to
be added at the end and then moved.

- An **insertion point** sits before the first item, between every two
  items, and after the last; an empty list shows one. The last one is
  the list's only add control — no separate `+ Add ___` button.
- Each is a real `<button class="insert-point">`: a thin divider line
  with a small centred `+`, low-contrast at rest. It brightens on hover
  and on keyboard focus (`:focus-visible`). On touch devices (no hover)
  it stays visible at the same low contrast and is at least `--tap-min`
  tall. On desktop it is `--control-h-xs` tall, on the button scale
  (§10).
- The `aria-label` names the place: "Insert a ___ before ___ N",
  "Add a ___ at the end", or "Add the first ___" for an empty list.
- Clicking creates a blank item at that position in one request (the
  server shifts the later items in the same transaction), re-renders,
  and puts the cursor in the new item's main text field. Wire it through
  `guardClick` (§10).
- First use: questions in the quiz editor (UC-A-14). Answers are still
  added at the end with `+ Answer`.

### Delete

- A **`danger ghost xsmall`** button in the row's actions column, or in
  the row's ⋯ menu below a `.menu-sep` when the row has more actions than
  fit inline.
- Asks first with the confirmation dialog (§14) when the loss is hard to
  redo: "Delete this ___?" with a **Delete ___** action. A delete that
  is easy to redo (an answer in the quiz editor) happens at once.
- **Exception: a session that holds data.** Deleting it opens the
  typed-title card (`#confirm-delete-card`) below the session list
  instead: it lists what will be lost and enables **Delete** only when
  the session's title is typed exactly. It is deliberately slower than
  the dialog. An empty session uses the dialog.
- On success: remove the row immediately, close the detail pane if it
  was showing that entity.
- **No soft-delete or undo** until we have a real audit need. Don't
  build "undo" speculatively.

### Status transitions

Entities with lifecycle (Session, Quiz, QuizRun, Query) use **explicitly
named verb buttons**, never a status dropdown:

- `Publish` / `Unpublish` (Quiz)
- `Start` / `End` (Session); `Start` / `Reveal results` / `Next question` /
  `Finish quiz` / `Reopen voting` (QuizRun)
- `Mark responded` / `Reopen` (Query)
- `Remove` / `Restore` (Query soft-remove)

Why: each transition has different validation rules and side effects;
forcing the user to think in verbs prevents accidental jumps.

A failed transition (e.g., publish-but-incomplete) never uses an
`alert()`. When the failure is about specific items, mark them in place
(see **Inline problems** below); otherwise show the server's message in
an error toast.

### Inline problems

Shows every reason an entity can't move to its next state at the item it
is about, so the author fixes them all in one pass. First use: the publish
rules in the quiz editor (UC-A-21), shown after a failed Publish and for a
Ready quiz that an edit broke (UC-A-10).

- The detail pane opens on the entity if it was closed. A short plain
  toast says what happened ("Not published: fix the marked problems");
  the marks carry the detail.
- Each item with a problem (`.has-problem`) gets a thin inset stripe in
  `--warn` (`box-shadow: inset 3px 0 0 var(--warn)`), the same shape as
  the feedback card's accent stripe. No border, tint or icon.
- Each problem has a one-line `.problem-note`: small text in `--warn`,
  directly under the field it is about, worded as an instruction ("Add
  the question text", "Mark exactly one correct answer"). The note is
  the field's accessible description (`aria-describedby`).
- A navigator in the detail card's header (`.problem-nav`) reads "N to
  fix", with **↑** / **↓** `.ghost.small` buttons labelled "Previous
  problem" / "Next problem". Each press scrolls the next problem to the
  centre of the screen (smoothly, unless the person prefers reduced
  motion), focuses its field, wraps at the ends and shows the position
  ("2 of 3"). The count is a polite live region.
- Once shown, the marks update after every edit and go away as each
  problem is fixed; the navigator goes with the last one. Don't show
  them before the author asks for the transition: a draft being written
  is not an error.
- No modal and no error block listing the problems.

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
- Render a useful static shell before boot requests complete. Public join and
  login controls must not be hidden behind an authentication-status round trip;
  role pages may use their existing inline loading primers until their single
  bootstrap response paints the operational surface.

### Empty

Always a *primer*, not a blank: muted small text + a pointer to the
create affordance.

> "No sessions yet. Create one above to share a code with your
> audience."

### Error

| Kind                 | Surface                                                      |
| -------------------- | ------------------------------------------------------------ |
| Transient action     | Toast (bottom right), 2.8 s; an error toast stays 4 s        |
| Form / sticky error  | `.error-banner` *inside* the affected card, until dismissed  |
| Item-specific rules  | Inline problem notes and the navigator (§7 Inline problems)  |
| Blocking failure     | Banner on the page; no modal                                 |
| Session deleted      | `#session-deleted` banner replaces the page's content (`showSessionDeleted()`, UC-X-01) |
| Auth expired         | Redirect to `/` (handled in `api()`)                         |

Never use `alert()`, `confirm()` or `prompt()`; a question before an
action uses the confirmation dialog (§14).

### Info / lifecycle hint

`.info-banner` inside the detail pane, for a sticky, non-error note about
the entity's state as a whole. Its text uses `--text`, so it stays
readable on the tint. Problems with specific items use **Inline
problems** (§7) instead.

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

**Views are links, actions are buttons.** A control that only opens
another page or view (Participant, Projector, "Open quiz library →") is a
plain link, styled like every other link. A control that changes
something (Start, Delete, + New session, Export) is a button. Never style
a link as a button or use a button only to navigate.

| Class           | Use                                                       |
| --------------- | --------------------------------------------------------- |
| `.primary`      | The single most important action on the surface; indigo fill |
| (default)       | Secondary actions; `--control-bg` fill with a border, lighter on hover |
| `.ghost`        | Tertiary actions; outline only, no fill                   |
| `.danger`       | Destructive; red text on the variant's fill (add `.ghost` for an outline only), red outline on hover |
| `.small`        | Inside dense tables / `card-tools`                        |
| `.xsmall`       | Row actions inside `.ctable`                              |

**Size scale (UC-X-13).** Three sizes, no others:

| Size      | Text  | Height | Use                                              |
| --------- | ----- | ------ | ------------------------------------------------ |
| default   | 14 px | 40 px  | A card's own actions (Submit, Ask, Join, Log in) |
| `.small`  | 13 px | 32 px  | Card tools, menus, the header, editor rows, buttons inside a card's content |
| `.xsmall` | 11 px | 24 px  | Row actions in `.ctable` tables only             |

- Buttons and menu triggers (`details.menu > summary`: Export ▾, Add to
  session ▾, ⋯) share one recipe in `frontend/src/app.css`. A size sets the height,
  side padding, font size and corners; a variant sets the colours. Menu
  triggers take the `.small` size, or `.xsmall` inside `.ctable` rows, so
  they match the buttons beside them. Inline fields (`input.inline`,
  `select.inline`) take the `.small` height; full-width fields take the
  default height.
- Controls in one row share one height: buttons beside an inline field are
  `.small`. The heights sit on the 8 px grid, and the smallest meets
  WCAG 2.2's 24 × 24 px minimum target.
- All of a card's own actions share one size; never mix default and
  `.small` for the same kind of action on a page.
- A custom call-to-action that isn't a `<button>` (e.g. the profile
  summary's "Add details") copies the default size and weight.
- On touch devices every size grows to at least 32 px tall (§16a).

- Verb-first labels: "Publish", "Delete", "Open session page →".
- One primary button per card. Two primaries on one surface is a smell.
- Cancel / dismiss is a `.ghost`, never colored.
- **Mutating buttons are guarded against double-submit.** Any button whose
  handler performs a *non-idempotent* server mutation (create / append /
  delete / advance) must be wired through `guardClick(button, handler)`
  from `common.ts` — it disables the button while the async handler runs
  and ignores repeat clicks, so a slow request can't be fired twice
  (duplicate rows, double-advance, etc.). Idempotent actions (login,
  lifecycle start/end, set-value, copy, navigation) don't need
  it. A toggle the server flips (the participant vote) is not idempotent:
  a double tap would undo it, so it is guarded. Don't hand-roll per-button
  `disabled` flags — reuse `guardClick`.

---

## 11. Badges & status

Use `.badge` for any lifecycle state: an uppercase pill with a tint and
no border, so it never looks like a button. Per-state classes follow the
pattern `badge-<state-slug>`, and the colour says what the state means:

- Green, running or usable: `badge-live`, `badge-ready`.
- Indigo, waiting to run: `badge-queued`.
- Orange, needs work: `badge-draft`, and `badge-needs-fixing` beside a
  Ready badge when an edit broke a publish rule. Keep orange for states
  that need attention.
- Neutral: `badge-planning` (not started, bright text); `badge-ended`,
  `badge-closed` (finished, muted text). A state without its own class
  is neutral.

Badges are read-only. Don't make them clickable. If you need to *change*
state, use a verb button (§7 Status transitions).

---

## 12. Keyboard

- **Enter** submits the obvious form on any single-field composer
  (`+ New`, login, join code).
- **Cmd/Ctrl+Enter** submits multiline composers (textarea: ask a
  question).
- A shortcut submits by calling the form button's `click()`, never the
  handler directly, so the button's `guardClick` guard also stops a
  double press.
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

Reserved for the rare case where work must block. The only modal is the
**confirmation dialog**. Never use a modal for create or edit (§7).

### Confirmation dialog

One in-page dialog asks before an action, in Prashna's own style. It
replaces the browser's `confirm()` pop-up, which Prashna never uses
(`test_frontend_uses_no_native_dialogs`).

**Confirm only when the loss is hard to redo.**

- Confirm: end the session; delete a quiz run; delete a quiz question
  or a quiz; delete an empty session; clear your feedback.
- Don't confirm: delete an answer in the quiz editor (add it again);
  remove a queued quiz from a session (add it again); remove a Q&A
  question (**Restore** brings it back); any toggle.
- A **heads-up** before an action that is allowed but usually a mistake
  (adding a quiz to a session that already has it) uses the same dialog
  with a plain action, not a red one.

**Anatomy.** `askConfirm({ title, detail, confirmLabel, danger })` in
`common.ts` opens one `<dialog class="confirm-dialog">`, created on
first use and reused. It resolves `true` for the action, `false`
otherwise.

- A card like `section.card` (`--panel`, border, `--radius-xl`,
  `--pad-card`, `--shadow-menu`), centred on the dimmed page
  (`--backdrop`, 50% black). It is at most 420 px wide and keeps the
  page gutter on phones.
- The heading (`.confirm-title`) is a short question: "End the
  session?", "Delete this question?".
- An optional one-line detail (`.confirm-detail`) says what happens:
  "Participants can no longer ask questions."
- Two default-size buttons at the bottom right: **Cancel** (`.ghost`) on
  the left, the action on the right. The action is named with a verb and
  its object ("End session", "Delete question", "Add again"), never "OK"
  or "Yes". It is `.danger` for a loss and `.primary` for a heads-up.

**Behaviour.**

- The dialog opens with `showModal()`, so the page behind it can't be
  used and Tab stays inside it.
- **Cancel**, **Esc** and a click on the backdrop all cancel. Esc stops
  at the dialog; it doesn't also close a menu or a detail pane.
- Focus starts on **Cancel** for a loss, so a stray Enter is safe, and on
  the action for a heads-up.
- When the dialog closes, focus returns to the control that opened it.
- The handler awaits the answer: `if (!await askConfirm({...})) return;`.

---

## 15. Lifecycle visibility (cross-cutting)

Every entity with state must show that state in three places:
1. **Its row** in the parent list (badge column).
2. **Its detail header** in the drill-down.
3. **Anywhere it's referenced** (e.g., the session page's quiz picker
   says "Q1 (5 questions) (draft)" for a draft; delegates see only
   `ready` quizzes, applying §16).

---

## 16. Don't show what the user can't act on

- Hide controls the current role can't use, don't disable them.
- Hide controls the current *state* makes useless: the session page hides
  **+ Add quiz** once a session has ended.
- Section links (§3) list only sections that are currently visible.
- Filter lists by what the current viewer can act on:
  - Moderator's quiz picker → `ready` quizzes for delegates; `ready` and
    `draft` (publish on add) for the admin owner.
  - Participant's question list → only `not hidden` questions.
  - Admin's session list → all sessions.
- Disabled state is reserved for transient blocks ("submit while
  loading"), not for permission.

---

## 16a. Phones and touch

Participants are almost always on phones; admins and moderators sometimes
are. Check every change at 390 px wide (UC-X-12).

- **No sideways page scroll.** Wide tables go in `.table-scroll`; row
  headers that hold controls use `flex-wrap: wrap`.
- **Wide lists stack on phones.** A table too wide for 390 px gets the
  `stack` class (`table.ctable.stack`): at 720 px and narrower each row
  becomes a block — the first cell (`.stack-line`) on its own line, then
  the status, code, counts and date wrapping on the next, then the
  actions (`.actions`) on their own line. Counts carry their unit through
  `data-label` ("2 questions"), because the column headers are hidden.
  The session list and the quiz runs list use it. Don't wrap a table in
  `.table-scroll` if its rows hold `details.menu` dropdowns — the scroll
  box clips them; let the actions cell wrap instead.
- **16 px inputs on narrow screens.** iOS Safari zooms the page when a
  focused field's font is under 16 px.
- **Tap targets ≥ 32 px tall on touch** (`@media (pointer: coarse)`),
  including `.xsmall` buttons, menu toggles, section links, breadcrumb
  and header links, and the links in a table's actions column. A link
  inside a sentence is exempt, as in WCAG 2.2.
- **Bring opened detail cards into view** (`scrollIntoView`), and place
  a detail card right after the list it belongs to.
- **Most urgent content first.** Keep collapsed or below the fold what
  isn't needed in the moment (e.g. a queued quiz run shows its title and
  Start, not its answers).
- **Mention keyboard shortcuts only where a keyboard is likely**
  (`matchMedia("(pointer: fine)")`).

---

## 17. Anti-patterns

- ❌ A modal for editing or creating.
- ❌ A "Save" button next to a text field that already persists on
  blur.
- ❌ Status as an editable dropdown.
- ❌ Native `alert()` for non-blocking errors, or native `confirm()` before an action.
- ❌ Stretching one detail pane to host two unrelated entities.
- ❌ Interleaving setup/creational controls with live/operational ones on
  a work surface (group setup behind a `<details class="setup">`, see §4).
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
