"""UI tests for /quizzes — quiz library, editor, publish, runs report.

Covers UC-A-09..22, UC-A-23, UC-A-24, UC-A-27, UC-A-28, UC-A-29.
"""
from __future__ import annotations

import re
import secrets

import pytest
from playwright.sync_api import expect

from ._helpers import (
    accept_confirm,
    admin_login_via_ui,
    api_end_session,
    api_login,
    api_make_quiz,
    api_make_session,
    api_queue_quiz_run,
    api_start_session,
    confirm_dialog,
    dismiss_confirm,
    watch_native_dialogs,
)


def _goto_quizzes(page, base_url):
    admin_login_via_ui(page, base_url)
    page.goto(base_url + "/quizzes")
    page.wait_for_selector("#quiz-rows")


def _open_row_more(row):
    """Open a quiz row's ⋯ menu (Duplicate, Delete)."""
    row.locator("details.row-more > summary").click()


def _valid_questions(*texts: str) -> list[dict]:
    return [
        {"text": t, "qtype": "single",
         "answers": [{"text": t + "-right", "is_correct": True}, {"text": t + "-wrong"}]}
        for t in texts
    ]


def _question_texts(page) -> list[str]:
    return page.locator("#editor-body .editor-q textarea").evaluate_all(
        "els => els.map(e => e.value)")


# ---------- UC-A-09 ----------


def test_uc_a_09_create_quiz_opens_editor(base_url, admin_setup, page):
    """UC-A-09: typing a title + clicking +New adds a #quiz-rows row and opens #editor-card."""
    _goto_quizzes(page, base_url)
    title = f"UI-Q09 {secrets.token_hex(3)}"
    page.fill("#new-quiz-title", title)
    page.click("#create-quiz")
    expect(page.locator("#quiz-rows tr").filter(has_text=title)).to_be_visible()
    expect(page.locator("#editor-card")).to_be_visible()
    expect(page.locator("#editor-title")).to_have_text(f"Quiz: {title}")


def test_uc_a_09_create_quiz_enter_submits(base_url, admin_setup, page):
    """UC-A-09: Enter in #new-quiz-title submits."""
    _goto_quizzes(page, base_url)
    title = f"UI-Q09e {secrets.token_hex(3)}"
    page.fill("#new-quiz-title", title)
    page.press("#new-quiz-title", "Enter")
    expect(page.locator("#quiz-rows tr").filter(has_text=title)).to_be_visible()


# ---------- UC-A-10 ----------


def test_uc_a_10_library_lists_quizzes(base_url, admin_setup, page):
    """UC-A-10: #quiz-rows contains a row per owned quiz with badge + question count."""
    c = api_login(base_url)
    q = api_make_quiz(c, f"UI-Q10 {secrets.token_hex(3)}")
    try:
        _goto_quizzes(page, base_url)
        row = page.locator("#quiz-rows tr").filter(has_text=q["title"])
        expect(row).to_be_visible()
        expect(row.locator(".badge")).to_be_visible()
    finally:
        c.close()


def test_uc_a_10_library_most_recent_at_top(base_url, admin_setup, page):
    """UC-A-10: most recently created quiz appears first."""
    c = api_login(base_url)
    api_make_quiz(c, f"UI-Q10a {secrets.token_hex(3)}")  # older quiz
    q2 = api_make_quiz(c, f"UI-Q10b {secrets.token_hex(3)}")
    try:
        _goto_quizzes(page, base_url)
        first = page.locator("#quiz-rows tr").first
        expect(first).to_contain_text(q2["title"])
    finally:
        c.close()


# ---------- UC-A-11 ----------


def test_uc_a_11_open_quiz_for_editing(base_url, admin_setup, page):
    """UC-A-11: clicking a row opens #editor-card with title and questions."""
    c = api_login(base_url)
    quiz = api_make_quiz(
        c,
        f"UI-Q11 {secrets.token_hex(3)}",
        questions=[
            {
                "text": "Sky color?",
                "qtype": "single",
                "answers": [
                    {"text": "blue", "is_correct": True},
                    {"text": "green", "is_correct": False},
                ],
            }
        ],
    )
    try:
        _goto_quizzes(page, base_url)
        row = page.locator("#quiz-rows tr").filter(has_text=quiz["title"])
        row.click()
        expect(page.locator("#editor-card")).to_be_visible()
        expect(page.locator("#editor-title")).to_have_text(f"Quiz: {quiz['title']}")
        # Question text is rendered into a textarea (text content).
        expect(page.locator("#editor-body textarea")).to_have_value("Sky color?")
        # Answer texts live in input values, not visible text.
        expect(page.locator("#editor-body input[type='text']").first).to_have_value("blue")
    finally:
        c.close()


def test_uc_a_11_editor_follows_list_and_scrolls_into_view(base_url, admin_setup, page):
    """UC-A-11: #editor-card follows the quiz list and is in view after opening, on a phone too."""
    c = api_login(base_url)
    for i in range(6):
        api_make_quiz(c, f"UI-Q11pad{i} {secrets.token_hex(3)}")
    quiz = api_make_quiz(c, f"UI-Q11view {secrets.token_hex(3)}", questions=_valid_questions("A"))
    api_make_quiz(c, f"UI-Q11top {secrets.token_hex(3)}")
    try:
        page.set_viewport_size({"width": 390, "height": 700})
        _goto_quizzes(page, base_url)
        assert page.evaluate(
            "document.querySelector('#quiz-library-card').nextElementSibling.id") == "editor-card"
        page.locator("#quiz-rows tr").filter(has_text=quiz["title"]).locator("td").first.click()
        expect(page.locator("#editor-card")).to_be_in_viewport(timeout=5000)
    finally:
        c.close()


def test_uc_a_11_editor_controls_have_accessible_names(base_url, admin_setup, page):
    """UC-A-11: editor controls are reachable by role and name; images use an Add image button."""
    c = api_login(base_url)
    quiz = api_make_quiz(c, f"UI-Q11a11y {secrets.token_hex(3)}", questions=_valid_questions("A"))
    try:
        _goto_quizzes(page, base_url)
        page.locator("#quiz-rows tr").filter(has_text=quiz["title"]).click()
        expect(page.get_by_role("textbox", name="Question 1 text")).to_have_value("A")
        expect(page.get_by_role("combobox", name="Question 1 type")).to_be_visible()
        expect(page.get_by_role("textbox", name="Answer 1 text")).to_have_value("A-right")
        expect(page.get_by_role("checkbox", name="Answer 1 is correct")).to_be_checked()
        expect(page.locator("#editor-body").get_by_role("button", name="Add image").first).to_be_visible()
        expect(page.locator("#editor-body input[type=file]").first).to_be_hidden()
    finally:
        c.close()


# ---------- UC-A-12 ----------


def test_uc_a_12_rename_quiz_updates_row(base_url, admin_setup, page):
    """UC-A-12: editing the editor title input and blurring updates the row title."""
    c = api_login(base_url)
    quiz = api_make_quiz(c, f"UI-Q12 {secrets.token_hex(3)}")
    try:
        _goto_quizzes(page, base_url)
        page.locator("#quiz-rows tr").filter(has_text=quiz["title"]).click()
        new_title = quiz["title"] + " RN"
        title_inp = page.locator("#editor-body input.inline").first
        title_inp.fill(new_title)
        title_inp.blur()
        expect(page.locator("#quiz-rows tr").filter(has_text=new_title)).to_be_visible(timeout=5000)
    finally:
        c.close()


# ---------- UC-A-13 ----------


def test_uc_a_13_delete_unused_quiz_removes_row(base_url, admin_setup, page):
    """UC-A-13: Delete in the row's ⋯ menu (after confirm) removes the row."""
    c = api_login(base_url)
    quiz = api_make_quiz(c, f"UI-Q13 {secrets.token_hex(3)}")
    try:
        _goto_quizzes(page, base_url)
        native = watch_native_dialogs(page)
        row = page.locator("#quiz-rows tr").filter(has_text=quiz["title"])
        _open_row_more(row)
        row.locator("button.danger").click()
        dismiss_confirm(page, "Delete this quiz?")
        page.wait_for_timeout(300)
        expect(row).to_be_visible()
        _open_row_more(row)
        row.locator("button.danger").click()
        accept_confirm(page, "Delete this quiz?", "Delete quiz")
        expect(page.locator("#quiz-rows tr").filter(has_text=quiz["title"])).to_have_count(0, timeout=5000)
        assert native == []
    finally:
        c.close()


def test_uc_a_13_delete_used_quiz_toasts_error(base_url, admin_setup, page):
    """UC-A-13: deleting a quiz that's been run shows error toast and row stays."""
    c = api_login(base_url)
    quiz = api_make_quiz(c, f"UI-Q13used {secrets.token_hex(3)}", publish=True)
    session = api_make_session(c, f"UI-Q13s {secrets.token_hex(3)}")
    api_queue_quiz_run(c, session["code"], quiz["id"])
    try:
        _goto_quizzes(page, base_url)
        row = page.locator("#quiz-rows tr").filter(has_text=quiz["title"])
        _open_row_more(row)
        row.locator("button.danger").click()
        accept_confirm(page, "Delete this quiz?", "Delete quiz")
        expect(page.locator(".toast-error")).to_be_visible()
        expect(row).to_be_visible()
    finally:
        c.close()


# ---------- UC-A-27 ----------


def test_uc_a_27_duplicate_adds_draft_row_and_opens_editor(base_url, admin_setup, page):
    """UC-A-27: Duplicate adds a '<title> (copy)' Draft row and opens the editor on the copy."""
    c = api_login(base_url)
    quiz = api_make_quiz(c, f"UI-Q27 {secrets.token_hex(3)}", publish=True)
    copy_title = quiz["title"] + " (copy)"
    try:
        _goto_quizzes(page, base_url)
        row = page.locator("#quiz-rows tr").filter(has_text=quiz["title"])
        _open_row_more(row)
        row.get_by_role("button", name="Duplicate").click()
        copy_row = page.locator("#quiz-rows tr").filter(has_text=copy_title)
        expect(copy_row).to_be_visible()
        expect(copy_row.locator(".badge-draft")).to_be_visible()
        expect(page.locator("#editor-card")).to_be_visible()
        expect(page.locator("#editor-title")).to_contain_text(copy_title)
    finally:
        c.close()


# ---------- UC-A-14 ----------


def _insert_points(page):
    return page.locator("#editor-body button.insert-point")


def _insert_labels(page) -> list[str]:
    return _insert_points(page).evaluate_all("els => els.map(e => e.getAttribute('aria-label'))")


def test_uc_a_14_insertion_points_and_labels(base_url, admin_setup, page):
    """UC-A-14: N questions show N+1 labelled insertion points and no other add button."""
    c = api_login(base_url)
    quiz = api_make_quiz(c, f"UI-Q14 {secrets.token_hex(3)}", questions=_valid_questions("A", "B", "C"))
    try:
        _open_editor(page, base_url, quiz["title"])
        expect(page.locator("#editor-body .editor-q")).to_have_count(3)
        expect(_insert_points(page)).to_have_count(4)
        assert _insert_labels(page) == [
            "Insert a question before question 1",
            "Insert a question before question 2",
            "Insert a question before question 3",
            "Add a question at the end",
        ]
        expect(page.locator("#editor-body button", has_text="Add question")).to_have_count(0)
    finally:
        c.close()


def test_uc_a_14_empty_quiz_adds_first_question(base_url, admin_setup, page):
    """UC-A-14: an empty quiz shows one insertion point; clicking it adds a focused question."""
    c = api_login(base_url)
    quiz = api_make_quiz(c, f"UI-Q14e {secrets.token_hex(3)}")
    try:
        _open_editor(page, base_url, quiz["title"])
        expect(_insert_points(page)).to_have_count(1)
        assert _insert_labels(page) == ["Add the first question"]
        page.get_by_role("button", name="Add the first question").click()
        expect(page.locator("#editor-body .editor-q")).to_have_count(1, timeout=5000)
        text = page.locator("#editor-body .editor-q textarea").first
        expect(text).to_have_value("New question")
        expect(text).to_be_focused()
        expect(_insert_points(page)).to_have_count(2)
    finally:
        c.close()


def test_uc_a_14_insert_before_question_2(base_url, admin_setup, page):
    """UC-A-14: the insertion point before question 2 inserts there, focused; the order persists."""
    c = api_login(base_url)
    quiz = api_make_quiz(c, f"UI-Q14m {secrets.token_hex(3)}", questions=_valid_questions("A", "B", "C"))
    try:
        _open_editor(page, base_url, quiz["title"])
        page.get_by_role("button", name="Insert a question before question 2").click()
        expect(page.locator("#editor-body .editor-q")).to_have_count(4, timeout=5000)
        assert _question_texts(page) == ["A", "New question", "B", "C"]
        expect(page.locator("#editor-body .editor-q textarea").nth(1)).to_be_focused()
        # Typing goes straight into the new question.
        page.keyboard.type("Inserted")
        page.locator("#editor-body .editor-q textarea").nth(1).blur()
        page.reload()
        page.locator("#quiz-rows tr").filter(has_text=quiz["title"]).click()
        expect(page.locator("#editor-body .editor-q")).to_have_count(4)
        assert _question_texts(page) == ["A", "Inserted", "B", "C"]
    finally:
        c.close()


def test_uc_a_14_insert_at_start_and_end(base_url, admin_setup, page):
    """UC-A-14: insert before question 1 goes first; the end insertion point goes last."""
    c = api_login(base_url)
    quiz = api_make_quiz(c, f"UI-Q14s {secrets.token_hex(3)}", questions=_valid_questions("A", "B"))
    try:
        _open_editor(page, base_url, quiz["title"])
        page.get_by_role("button", name="Insert a question before question 1").click()
        expect(page.locator("#editor-body .editor-q")).to_have_count(3, timeout=5000)
        assert _question_texts(page) == ["New question", "A", "B"]
        expect(page.locator("#editor-body .editor-q textarea").first).to_be_focused()
        page.get_by_role("button", name="Add a question at the end").click()
        expect(page.locator("#editor-body .editor-q")).to_have_count(4, timeout=5000)
        assert _question_texts(page) == ["New question", "A", "B", "New question"]
        expect(page.locator("#editor-body .editor-q textarea").last).to_be_focused()
    finally:
        c.close()


def test_uc_a_14_insertion_points_visible_on_touch_phone(base_url, admin_setup, browser):
    """UC-A-14: at 390 px on a touch device the insertion points show without hover, >= 32 px tall."""
    c = api_login(base_url)
    quiz = api_make_quiz(c, f"UI-Q14t {secrets.token_hex(3)}", questions=_valid_questions("A", "B"))
    ctx = browser.new_context(viewport={"width": 390, "height": 844}, has_touch=True, is_mobile=True)
    try:
        page = ctx.new_page()
        _open_editor(page, base_url, quiz["title"])
        points = _insert_points(page)
        expect(points).to_have_count(3)
        for i in range(3):
            expect(points.nth(i)).to_be_visible()
        sizes = points.evaluate_all("""els => els.map(e => ({
            h: e.getBoundingClientRect().height,
            opacity: parseFloat(getComputedStyle(e).opacity),
            plus: parseFloat(getComputedStyle(e.querySelector('.insert-plus')).opacity),
        }))""")
        assert all(x["h"] >= 32 for x in sizes), sizes
        assert all(x["opacity"] >= 0.4 and x["plus"] > 0 for x in sizes), sizes
    finally:
        ctx.close()
        c.close()


# ---------- UC-A-15 ----------


def test_uc_a_15_edit_question_text_persists(base_url, admin_setup, page):
    """UC-A-15: blurring a question text input PATCHes and persists."""
    c = api_login(base_url)
    quiz = api_make_quiz(
        c,
        f"UI-Q15 {secrets.token_hex(3)}",
        questions=[
            {
                "text": "old",
                "qtype": "single",
                "answers": [
                    {"text": "a", "is_correct": True},
                    {"text": "b", "is_correct": False},
                ],
            }
        ],
    )
    try:
        _goto_quizzes(page, base_url)
        page.locator("#quiz-rows tr").filter(has_text=quiz["title"]).click()
        ta = page.locator("#editor-body textarea").first
        ta.fill("brand new text")
        ta.blur()
        # Reload editor by re-clicking row.
        page.locator("#quiz-rows tr").filter(has_text=quiz["title"]).click()
        expect(page.locator("#editor-body textarea").first).to_have_value("brand new text", timeout=5000)
    finally:
        c.close()


def test_uc_a_15_switch_qtype_persists(base_url, admin_setup, page):
    """UC-A-15: switching qtype select PATCHes."""
    c = api_login(base_url)
    quiz = api_make_quiz(
        c,
        f"UI-Q15t {secrets.token_hex(3)}",
        questions=[
            {
                "text": "q",
                "qtype": "single",
                "answers": [
                    {"text": "a", "is_correct": True},
                    {"text": "b", "is_correct": False},
                ],
            }
        ],
    )
    try:
        _goto_quizzes(page, base_url)
        page.locator("#quiz-rows tr").filter(has_text=quiz["title"]).click()
        sel = page.locator("#editor-body select").first
        sel.select_option("multi")
        # Confirm by reloading.
        page.locator("#quiz-rows tr").filter(has_text=quiz["title"]).click()
        expect(page.locator("#editor-body select").first).to_have_value("multi", timeout=5000)
    finally:
        c.close()


# ---------- UC-A-16 ----------


def test_uc_a_16_delete_question_removes_row(base_url, admin_setup, page):
    """UC-A-16: clicking Delete on a question (after confirm) removes its row."""
    c = api_login(base_url)
    quiz = api_make_quiz(
        c,
        f"UI-Q16 {secrets.token_hex(3)}",
        questions=[
            {"text": "q1", "qtype": "single", "answers": [{"text": "a"}, {"text": "b"}]},
            {"text": "q2", "qtype": "single", "answers": [{"text": "c"}, {"text": "d"}]},
        ],
    )
    try:
        _goto_quizzes(page, base_url)
        page.locator("#quiz-rows tr").filter(has_text=quiz["title"]).click()
        expect(page.locator("#editor-body .editor-q")).to_have_count(2)
        native = watch_native_dialogs(page)
        page.locator("#editor-body .editor-q").first.locator("button.danger", has_text="Delete").click()
        dialog = confirm_dialog(page, "Delete this question?")
        expect(dialog.locator(".confirm-detail")).to_have_text("Its answers are deleted too.")
        # Esc cancels and leaves the editor open (it doesn't also close the pane).
        page.keyboard.press("Escape")
        expect(dialog).to_be_hidden()
        expect(page.locator("#editor-body .editor-q")).to_have_count(2)
        page.locator("#editor-body .editor-q").first.locator("button.danger", has_text="Delete").click()
        accept_confirm(page, "Delete this question?", "Delete question")
        expect(page.locator("#editor-body .editor-q")).to_have_count(1, timeout=5000)
        assert native == []
    finally:
        c.close()


# ---------- UC-A-17 ----------


def test_uc_a_17_add_answer_appends_row(base_url, admin_setup, page):
    """UC-A-17: + Answer appends an answer row with 'New answer' text, unchecked."""
    c = api_login(base_url)
    quiz = api_make_quiz(
        c,
        f"UI-Q17 {secrets.token_hex(3)}",
        questions=[
            {"text": "q", "qtype": "single", "answers": [{"text": "a"}, {"text": "b"}]},
        ],
    )
    try:
        _goto_quizzes(page, base_url)
        page.locator("#quiz-rows tr").filter(has_text=quiz["title"]).click()
        # Wait for the editor to load the initial 2 answers from the fixture
        # before counting — otherwise the synchronous .count() races the WS fetch.
        expect(page.locator("#editor-body .editor-opt")).to_have_count(2, timeout=5000)
        page.locator("#editor-body button", has_text="+ Answer").click()
        expect(page.locator("#editor-body .editor-opt")).to_have_count(3, timeout=5000)
        last = page.locator("#editor-body .editor-opt").last
        expect(last.locator("input[type=text]")).to_have_value("New answer")
        expect(last.locator("input[type=checkbox]")).not_to_be_checked()
    finally:
        c.close()


# ---------- UC-A-18 ----------


def test_uc_a_18_edit_answer_text_and_correct(base_url, admin_setup, page):
    """UC-A-18: blurring text input PATCHes; toggling checkbox PATCHes."""
    c = api_login(base_url)
    quiz = api_make_quiz(
        c,
        f"UI-Q18 {secrets.token_hex(3)}",
        questions=[
            {"text": "q", "qtype": "single", "answers": [{"text": "alpha"}, {"text": "beta"}]},
        ],
    )
    try:
        _goto_quizzes(page, base_url)
        page.locator("#quiz-rows tr").filter(has_text=quiz["title"]).click()
        first_row = page.locator("#editor-body .editor-opt").first
        first_row.locator("input[type=text]").fill("gamma")
        first_row.locator("input[type=text]").blur()
        # Toggle correctness.
        first_row.locator("input[type=checkbox]").check()
        # Reload editor and verify.
        page.locator("#quiz-rows tr").filter(has_text=quiz["title"]).click()
        new_first = page.locator("#editor-body .editor-opt").first
        expect(new_first.locator("input[type=text]")).to_have_value("gamma", timeout=5000)
        expect(new_first.locator("input[type=checkbox]")).to_be_checked()
    finally:
        c.close()


# ---------- UC-A-19 ----------


def test_uc_a_19_delete_answer_removes_row(base_url, admin_setup, page):
    """UC-A-19: clicking ✕ on an answer removes its row."""
    c = api_login(base_url)
    quiz = api_make_quiz(
        c,
        f"UI-Q19 {secrets.token_hex(3)}",
        questions=[
            {"text": "q", "qtype": "single", "answers": [{"text": "a"}, {"text": "b"}, {"text": "c"}]},
        ],
    )
    try:
        _goto_quizzes(page, base_url)
        page.locator("#quiz-rows tr").filter(has_text=quiz["title"]).click()
        expect(page.locator("#editor-body .editor-opt")).to_have_count(3)
        page.locator("#editor-body .editor-opt").first.locator("button[aria-label='Delete answer']").click()
        expect(page.locator("#editor-body .editor-opt")).to_have_count(2, timeout=5000)
    finally:
        c.close()


# ---------- UC-A-28 ----------


def _open_editor(page, base_url, title):
    _goto_quizzes(page, base_url)
    page.locator("#quiz-rows tr").filter(has_text=title).click()
    expect(page.locator("#editor-card")).to_be_visible()


def test_uc_a_28_move_question_down_persists(base_url, admin_setup, page):
    """UC-A-28: Move question down swaps it with the next one; the order persists."""
    c = api_login(base_url)
    quiz = api_make_quiz(c, f"UI-Q28 {secrets.token_hex(3)}", questions=_valid_questions("A", "B", "C"))
    try:
        _open_editor(page, base_url, quiz["title"])
        page.locator("#editor-body .editor-q").first.get_by_role("button", name="Move question down").click()
        expect(page.locator("#editor-body .editor-q textarea").first).to_have_value("B", timeout=5000)
        assert _question_texts(page) == ["B", "A", "C"]
        page.reload()
        page.locator("#quiz-rows tr").filter(has_text=quiz["title"]).click()
        expect(page.locator("#editor-body .editor-q textarea").first).to_have_value("B")
        assert _question_texts(page) == ["B", "A", "C"]
    finally:
        c.close()


def test_uc_a_28_drag_question_persists(base_url, admin_setup, page):
    """UC-A-28: dragging a question's handle above the previous one reorders and persists."""
    c = api_login(base_url)
    quiz = api_make_quiz(c, f"UI-Q28d {secrets.token_hex(3)}", questions=_valid_questions("A", "B", "C"))
    try:
        # Mouse coordinates must be inside the viewport: make all three
        # questions visible at once.
        page.set_viewport_size({"width": 1280, "height": 1600})
        _open_editor(page, base_url, quiz["title"])
        questions = page.locator("#editor-body .editor-q")
        expect(questions).to_have_count(3)
        questions.nth(0).scroll_into_view_if_needed()
        handle = questions.nth(2).locator(".question-head .drag-handle").bounding_box()
        target = questions.nth(0).bounding_box()
        page.mouse.move(handle["x"] + handle["width"] / 2, handle["y"] + handle["height"] / 2)
        page.mouse.down()
        page.mouse.move(target["x"] + 20, target["y"] + 5, steps=12)
        page.mouse.up()
        expect(page.locator("#editor-body .editor-q textarea").first).to_have_value("C", timeout=5000)
        page.reload()
        page.locator("#quiz-rows tr").filter(has_text=quiz["title"]).click()
        expect(page.locator("#editor-body .editor-q textarea").first).to_have_value("C")
        assert _question_texts(page) == ["C", "A", "B"]
    finally:
        c.close()


def test_uc_a_28_move_buttons_disabled_at_ends(base_url, admin_setup, page):
    """UC-A-28: Move up is disabled on the first question, Move down on the last."""
    c = api_login(base_url)
    quiz = api_make_quiz(c, f"UI-Q28e {secrets.token_hex(3)}", questions=_valid_questions("A", "B"))
    try:
        _open_editor(page, base_url, quiz["title"])
        questions = page.locator("#editor-body .editor-q")
        expect(questions.first.get_by_role("button", name="Move question up")).to_be_disabled()
        expect(questions.last.get_by_role("button", name="Move question down")).to_be_disabled()
        expect(questions.first.get_by_role("button", name="Move question down")).to_be_enabled()
    finally:
        c.close()


def test_uc_a_28_move_answer_up_persists(base_url, admin_setup, page):
    """UC-A-28: Move answer up swaps it with the previous answer; the order persists."""
    c = api_login(base_url)
    quiz = api_make_quiz(c, f"UI-Q28a {secrets.token_hex(3)}", questions=_valid_questions("A"))
    try:
        _open_editor(page, base_url, quiz["title"])
        answers = page.locator("#editor-body .editor-opt")
        expect(answers.first.locator("input[type='text']")).to_have_value("A-right")
        answers.nth(1).get_by_role("button", name="Move answer up").click()
        expect(answers.first.locator("input[type='text']")).to_have_value("A-wrong", timeout=5000)
        page.reload()
        page.locator("#quiz-rows tr").filter(has_text=quiz["title"]).click()
        expect(page.locator("#editor-body .editor-opt").first.locator("input[type='text']")).to_have_value("A-wrong")
    finally:
        c.close()


# ---------- UC-A-20 (image upload) ----------


def test_uc_a_20_image_upload(base_url, admin_setup, page, tmp_path):
    """UC-A-20: picking a file via the question file input uploads + PATCHes + thumbnail renders."""
    c = api_login(base_url)
    quiz = api_make_quiz(
        c,
        f"UI-Q20 {secrets.token_hex(3)}",
        questions=[
            {"text": "q", "qtype": "single", "answers": [{"text": "a"}, {"text": "b"}]},
        ],
    )
    # 1x1 PNG (smallest valid)
    png_bytes = bytes.fromhex(
        "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
        "890000000d49444154789c63000100000005000101da4a2c1c0000000049454e"
        "44ae426082"
    )
    fp = tmp_path / "x.png"
    fp.write_bytes(png_bytes)
    try:
        _goto_quizzes(page, base_url)
        page.locator("#quiz-rows tr").filter(has_text=quiz["title"]).click()
        # The question-level file input is the first file input within the question wrap.
        file_inp = page.locator("#editor-body .editor-q input[type=file]").first
        file_inp.set_input_files(str(fp))
        # Thumbnail re-renders after the upload (editor reload).
        expect(page.locator("#editor-body .editor-q img.thumb").first).to_be_visible(timeout=5000)
    finally:
        c.close()


# ---------- UC-A-21 ----------


def test_uc_a_21_publish_valid_quiz_flips_badge(base_url, admin_setup, page):
    """UC-A-21: clicking Publish on a valid draft flips the row badge to .badge-ready."""
    c = api_login(base_url)
    quiz = api_make_quiz(
        c,
        f"UI-Q21 {secrets.token_hex(3)}",
        questions=[
            {
                "text": "q",
                "qtype": "single",
                "answers": [
                    {"text": "a", "is_correct": True},
                    {"text": "b", "is_correct": False},
                ],
            }
        ],
    )
    try:
        _goto_quizzes(page, base_url)
        row = page.locator("#quiz-rows tr").filter(has_text=quiz["title"])
        row.locator("button", has_text="Publish").click()
        expect(row.locator(".badge-ready")).to_be_visible(timeout=5000)
    finally:
        c.close()


def test_uc_a_21_publish_empty_quiz_marks_where_questions_are_added(base_url, admin_setup, page):
    """UC-A-21: publishing an empty quiz keeps it Draft and marks the place
    where questions are added."""
    c = api_login(base_url)
    quiz = api_make_quiz(c, f"UI-Q21bad {secrets.token_hex(3)}")
    try:
        _goto_quizzes(page, base_url)
        row = page.locator("#quiz-rows tr").filter(has_text=quiz["title"])
        row.locator("button", has_text="Publish").click()
        expect(page.locator("#editor-card")).to_be_visible(timeout=5000)
        add_first = page.get_by_role("button", name="Add the first question")
        expect(add_first).to_have_accessible_description("Add at least one question")
        expect(page.locator("#editor-body .problem-note")).to_have_text(["Add at least one question"])
        expect(page.locator("#editor-problem-count")).to_have_text("1 to fix")
        expect(row.locator(".badge-draft")).to_be_visible()
        expect(page.locator(".toast-error")).to_have_count(0)
    finally:
        c.close()


def _three_problem_quiz(c, title: str) -> dict:
    """A draft whose three questions each break one publish rule: Q1 has no
    text, Q2 (single choice) has no correct answer, Q3 has an empty answer."""
    return api_make_quiz(c, title, questions=[
        {"text": "", "qtype": "single",
         "answers": [{"text": "a", "is_correct": True}, {"text": "b"}]},
        {"text": "Pick one", "qtype": "single",
         "answers": [{"text": "c"}, {"text": "d"}]},
        {"text": "Third", "qtype": "single",
         "answers": [{"text": "e", "is_correct": True}, {"text": ""}]},
    ])


NAV_IN_REACH_JS = """() => {
  const btn = document.querySelector('#editor-problem-next').getBoundingClientRect();
  const nav = document.querySelector('.page-nav');
  const navBottom = nav && getComputedStyle(nav).position === 'sticky' ? nav.getBoundingClientRect().bottom : 0;
  return { top: btn.top, bottom: btn.bottom, navBottom, vh: window.innerHeight };
}"""


@pytest.mark.parametrize("width", [1280, 390])
def test_uc_a_21_navigator_stays_in_reach_on_a_long_quiz(base_url, admin_setup, page, width):
    """UC-A-21: the editor header stays pinned, so Next problem is still on screen
    after it moves to a problem far down a long quiz."""
    c = api_login(base_url)
    ok = {"qtype": "single", "answers": [{"text": "a", "is_correct": True}, {"text": "b"}]}
    questions = [{"text": "", **ok}] + [{"text": f"Q{i}", **ok} for i in range(2, 12)] + [{"text": "", **ok}]
    quiz = api_make_quiz(c, f"UI-Q21long {secrets.token_hex(3)}", questions=questions)
    try:
        page.set_viewport_size({"width": width, "height": 700})
        _goto_quizzes(page, base_url)
        page.locator("#quiz-rows tr").filter(has_text=quiz["title"]).locator("button", has_text="Publish").click()
        expect(page.locator("#editor-problem-count")).to_have_text("2 to fix", timeout=5000)
        page.locator("#editor-problem-next").click()
        page.locator("#editor-problem-next").click()  # to the last question, far down
        expect(page.locator("#editor-problem-pos")).to_have_text("2 of 2")
        page.wait_for_timeout(600)  # let the smooth scroll settle
        box = page.evaluate(NAV_IN_REACH_JS)
        assert box["top"] >= box["navBottom"] - 1 and box["bottom"] <= box["vh"], box
    finally:
        c.close()


def test_uc_a_21_failed_publish_marks_every_problem_inline(base_url, admin_setup, page):
    """UC-A-21: a failed Publish from the library row opens the editor with
    every problem marked in place; the navigator walks them and wraps;
    fixing them clears the marks and Publish then succeeds."""
    c = api_login(base_url)
    quiz = _three_problem_quiz(c, f"UI-Q21all {secrets.token_hex(3)}")
    try:
        _goto_quizzes(page, base_url)
        expect(page.locator("#editor-card")).to_be_hidden()
        row = page.locator("#quiz-rows tr").filter(has_text=quiz["title"])
        row.locator("button", has_text="Publish").click()
        expect(page.locator("#editor-card")).to_be_visible(timeout=5000)
        expect(page.locator(".toast").last).to_have_text("Not published: fix the marked problems")
        expect(page.locator(".toast-error")).to_have_count(0)
        expect(row.locator(".badge-draft")).to_be_visible()

        cards = page.locator("#editor-body .editor-q")
        notes = page.locator("#editor-body .problem-note")
        expect(notes).to_have_text([
            "Add the question text", "Mark exactly one correct answer", "Add answer text or an image",
        ])
        for i in range(3):
            expect(cards.nth(i)).to_have_class(re.compile(r"\bhas-problem\b"))
            expect(cards.nth(i).locator(".problem-note")).to_have_count(1)
        # The answer's note sits in that answer's row.
        expect(cards.nth(2).locator(".editor-opt").nth(1).locator(".problem-note")).to_have_count(1)
        count = page.locator("#editor-problem-count")
        expect(count).to_have_text("3 to fix")
        expect(page.locator("#editor-problem-pos")).to_be_hidden()

        q1_text = page.get_by_role("textbox", name="Question 1 text")
        q2_correct = cards.nth(1).get_by_role("checkbox", name="Answer 1 is correct")
        q3_answer = cards.nth(2).get_by_role("textbox", name="Answer 2 text")
        expect(q1_text).to_have_accessible_description("Add the question text")
        expect(q3_answer).to_have_accessible_description("Add answer text or an image")

        nxt = page.get_by_role("button", name="Next problem")
        prev = page.get_by_role("button", name="Previous problem")
        nxt.click()
        expect(q1_text).to_be_focused()
        expect(page.locator("#editor-problem-pos")).to_have_text("1 of 3")
        nxt.click()
        expect(q2_correct).to_be_focused()
        nxt.click()
        expect(q3_answer).to_be_focused()
        expect(page.locator("#editor-problem-pos")).to_have_text("3 of 3")
        nxt.click()
        expect(q1_text).to_be_focused()
        prev.click()
        expect(q3_answer).to_be_focused()

        # Fixing each problem updates the marks without a Publish.
        q1_text.fill("First")
        q1_text.press("Tab")
        expect(count).to_have_text("2 to fix", timeout=5000)
        expect(cards.nth(0)).not_to_have_class(re.compile(r"\bhas-problem\b"))
        q2_correct.check()
        expect(count).to_have_text("1 to fix", timeout=5000)
        q3_answer.fill("f")
        q3_answer.press("Tab")
        expect(page.locator("#editor-problem-nav")).to_be_hidden(timeout=5000)
        expect(notes).to_have_count(0)
        expect(page.locator("#editor-body .has-problem")).to_have_count(0)

        row.locator("button", has_text="Publish").click()
        expect(row.locator(".badge-ready")).to_be_visible(timeout=5000)
    finally:
        c.close()


def test_uc_a_21_draft_shows_no_problems_before_publish(base_url, admin_setup, page):
    """UC-A-21: a draft being written shows no problem marks until a Publish
    fails, also after an edit."""
    c = api_login(base_url)
    quiz = _three_problem_quiz(c, f"UI-Q21quiet {secrets.token_hex(3)}")
    try:
        _open_editor(page, base_url, quiz["title"])
        expect(page.locator("#editor-body .editor-q")).to_have_count(3)
        text = page.get_by_role("textbox", name="Question 2 text")
        text.fill("Pick one, please")
        text.press("Tab")
        expect(page.locator("#quiz-rows tr").filter(has_text=quiz["title"])).to_be_visible()
        page.wait_for_load_state("networkidle")
        expect(page.locator("#editor-body .problem-note")).to_have_count(0)
        expect(page.locator("#editor-body .has-problem")).to_have_count(0)
        expect(page.locator("#editor-problem-nav")).to_be_hidden()
    finally:
        c.close()


# ---------- UC-A-22 ----------


def test_uc_a_22_unpublish_flips_badge_to_draft(base_url, admin_setup, page):
    """UC-A-22: Unpublish on a ready quiz flips the badge from ready to draft."""
    c = api_login(base_url)
    quiz = api_make_quiz(c, f"UI-Q22 {secrets.token_hex(3)}", publish=True)
    try:
        _goto_quizzes(page, base_url)
        row = page.locator("#quiz-rows tr").filter(has_text=quiz["title"])
        expect(row.locator(".badge-ready")).to_be_visible()
        row.locator("button", has_text="Unpublish").click()
        expect(row.locator(".badge-draft")).to_be_visible(timeout=5000)
    finally:
        c.close()


# ---------- UC-A-29 ----------


def _open_add_menu(row):
    row.locator("details.add-to-session > summary").click()


def test_uc_a_29_add_ready_quiz_to_session(base_url, admin_setup, page):
    """UC-A-29: the menu lists open sessions (live first, no ended); clicking one queues the quiz."""
    c = api_login(base_url)
    quiz = api_make_quiz(c, f"UI-Q29 {secrets.token_hex(3)}", publish=True)
    planning = api_make_session(c, f"UI-Q29plan {secrets.token_hex(3)}")
    live = api_make_session(c, f"UI-Q29live {secrets.token_hex(3)}")
    api_start_session(c, live["code"])
    ended = api_make_session(c, f"UI-Q29end {secrets.token_hex(3)}")
    api_end_session(c, ended["code"])
    try:
        _goto_quizzes(page, base_url)
        row = page.locator("#quiz-rows tr").filter(has_text=quiz["title"])
        _open_add_menu(row)
        items = row.locator("details.add-to-session .menu-panel button")
        expect(items.filter(has_text=planning["title"])).to_be_visible()
        texts = items.all_text_contents()
        assert not any(ended["title"] in t for t in texts)
        live_pos = next(i for i, t in enumerate(texts) if live["title"] in t)
        plan_pos = next(i for i, t in enumerate(texts) if planning["title"] in t)
        assert live_pos < plan_pos
        items.filter(has_text=planning["title"]).click()
        expect(page.locator(".toast").last).to_contain_text(planning["title"])
        runs = c.get(f"/api/sessions/{planning['code']}/quiz_runs").json()
        assert [r["status"] for r in runs] == ["queued"]
    finally:
        c.close()


def test_uc_a_29_add_valid_draft_publishes(base_url, admin_setup, page):
    """UC-A-29: adding a valid draft flips its badge to Ready and queues a run."""
    c = api_login(base_url)
    quiz = api_make_quiz(c, f"UI-Q29d {secrets.token_hex(3)}", questions=_valid_questions("A"))
    s = api_make_session(c, f"UI-Q29ds {secrets.token_hex(3)}")
    try:
        _goto_quizzes(page, base_url)
        row = page.locator("#quiz-rows tr").filter(has_text=quiz["title"])
        expect(row.locator(".badge-draft")).to_be_visible()
        _open_add_menu(row)
        row.locator("details.add-to-session .menu-panel button").filter(has_text=s["title"]).click()
        expect(row.locator(".badge-ready")).to_be_visible(timeout=5000)
        assert len(c.get(f"/api/sessions/{s['code']}/quiz_runs").json()) == 1
    finally:
        c.close()


def test_uc_a_29_add_invalid_draft_toasts(base_url, admin_setup, page):
    """UC-A-29: adding an invalid draft shows an error; it stays Draft and nothing is queued."""
    c = api_login(base_url)
    quiz = api_make_quiz(c, f"UI-Q29i {secrets.token_hex(3)}")
    s = api_make_session(c, f"UI-Q29is {secrets.token_hex(3)}")
    try:
        _goto_quizzes(page, base_url)
        row = page.locator("#quiz-rows tr").filter(has_text=quiz["title"])
        _open_add_menu(row)
        row.locator("details.add-to-session .menu-panel button").filter(has_text=s["title"]).click()
        expect(page.locator(".toast-error")).to_be_visible(timeout=5000)
        expect(row.locator(".badge-draft")).to_be_visible()
        assert c.get(f"/api/sessions/{s['code']}/quiz_runs").json() == []
    finally:
        c.close()


def test_uc_a_29_menu_shows_sessions_already_holding_the_quiz(base_url, admin_setup, page):
    """UC-A-29: a session that already has this quiz says so; re-adding asks first."""
    c = api_login(base_url)
    quiz = api_make_quiz(c, f"UI-Q29dup {secrets.token_hex(3)}", publish=True)
    holding = api_make_session(c, f"UI-Q29hold {secrets.token_hex(3)}")
    other = api_make_session(c, f"UI-Q29other {secrets.token_hex(3)}")
    api_queue_quiz_run(c, holding["code"], quiz["id"])
    try:
        _goto_quizzes(page, base_url)
        row = page.locator("#quiz-rows tr").filter(has_text=quiz["title"])
        _open_add_menu(row)
        items = row.locator("details.add-to-session .menu-panel button")
        expect(items.filter(has_text=holding["title"])).to_contain_text("Already added · Queued")
        expect(items.filter(has_text=other["title"])).not_to_contain_text("Already added")

        native = watch_native_dialogs(page)
        items.filter(has_text=holding["title"]).click()
        dialog = confirm_dialog(page, "Add this quiz again?")
        expect(dialog.locator(".confirm-detail")).to_have_text(
            f'"{quiz["title"]}" is already in "{holding["title"]}".')
        dismiss_confirm(page)
        page.wait_for_timeout(500)
        assert len(c.get(f"/api/sessions/{holding['code']}/quiz_runs").json()) == 1

        _open_add_menu(row)
        row.locator("details.add-to-session .menu-panel button").filter(has_text=holding["title"]).click()
        accept_confirm(page, "Add this quiz again?", "Add again")
        expect(page.locator(".toast").last).to_contain_text(holding["title"])
        assert len(c.get(f"/api/sessions/{holding['code']}/quiz_runs").json()) == 2
        assert native == []
    finally:
        c.close()


# ---------- UC-A-23 ----------


def test_quiz_library_breadcrumbs_link_admin_and_report_sections(
    base_url, admin_setup, page
):
    """UC-A-23: the quiz library sits under Sessions in the breadcrumb, which is
    the only way up: the header has no separate home link."""
    _goto_quizzes(page, base_url)
    crumbs = page.locator(".breadcrumbs")
    expect(crumbs.locator("li")).to_have_text(["Sessions", "Quiz library"])
    expect(crumbs.locator("a", has_text="Sessions")).to_have_attribute("href", "/")
    expect(crumbs.locator('[aria-current="page"]')).to_have_text("Quiz library")
    expect(page.locator("header.top a")).to_have_count(0)
    expect(page.locator("header.top")).not_to_contain_text("home")
    expect(page).to_have_title("Quiz library — Prashna")
    expect(page.locator(".section-links a", has_text="Quiz runs")).to_have_attribute(
        "href", "#quiz-runs-card"
    )


def test_uc_a_23_qs_rows_lists_quiz_runs(base_url, admin_setup, page):
    """UC-A-23: #qs-rows shows one row per QuizRun across owned sessions."""
    c = api_login(base_url)
    quiz = api_make_quiz(c, f"UI-Q23 {secrets.token_hex(3)}", publish=True)
    s = api_make_session(c, f"UI-Q23s {secrets.token_hex(3)}")
    api_queue_quiz_run(c, s["code"], quiz["id"])
    try:
        _goto_quizzes(page, base_url)
        row = page.locator("#qs-rows tr").filter(has_text=quiz["title"]).filter(has_text=s["code"])
        expect(row).to_be_visible()
        expect(row.locator(".badge-queued")).to_be_visible()
    finally:
        c.close()


def test_uc_a_23_switches_flat_quiz_version_and_session_views(
    base_url, admin_setup, page
):
    """The global report can regroup the same runs without another API shape."""
    c = api_login(base_url)
    quiz = api_make_quiz(c, f"UI-Q23groups {secrets.token_hex(3)}", publish=True)
    first = api_make_session(c, f"UI-Q23-first {secrets.token_hex(3)}")
    second = api_make_session(c, f"UI-Q23-second {secrets.token_hex(3)}")
    api_queue_quiz_run(c, first["code"], quiz["id"])
    question_id = c.get(
        f"/api/quizzes/{quiz['id']}?include_correct=true"
    ).json()["questions"][0]["id"]
    c.patch(
        f"/api/quiz_questions/{question_id}",
        json={"text": "Updated question for version two?"},
    ).raise_for_status()
    api_queue_quiz_run(c, second["code"], quiz["id"])
    try:
        _goto_quizzes(page, base_url)

        page.locator("[data-run-view='quiz']").click()
        expect(page.locator("[data-run-view='quiz']")).to_have_attribute(
            "aria-pressed", "true"
        )
        quiz_group = page.locator("#qs-groups .run-group").filter(
            has_text=quiz["title"]
        )
        expect(quiz_group).to_have_count(1)
        expect(quiz_group).to_contain_text(first["code"])
        expect(quiz_group).to_contain_text(second["code"])

        page.locator("[data-run-view='version']").click()
        version_groups = page.locator("#qs-groups .run-group").filter(
            has_text=quiz["title"]
        )
        expect(version_groups).to_have_count(2)
        version_titles = " ".join(version_groups.locator("summary").all_text_contents())
        assert "v1" in version_titles and "v2" in version_titles
        assert "runs=version" in page.url
        page.reload()
        expect(page.locator("[data-run-view='version']")).to_have_attribute(
            "aria-pressed", "true"
        )
        expect(page.locator("#qs-groups .run-group").filter(
            has_text=quiz["title"]
        )).to_have_count(2)

        page.locator("[data-run-view='session']").click()
        expect(page.locator("#qs-groups .run-group").filter(
            has_text=first["code"]
        )).to_have_count(1)
        expect(page.locator("#qs-groups .run-group").filter(
            has_text=second["code"]
        )).to_have_count(1)

        page.locator("[data-run-view='flat']").click()
        expect(page.locator("#qs-flat")).to_be_visible()
        expect(page.locator("#qs-rows tr").filter(
            has_text=quiz["title"]
        )).to_have_count(2)
    finally:
        c.close()


# ---------- UC-A-24 ----------


def test_uc_a_24_results_card_scrolls_into_view(base_url, admin_setup, page):
    """UC-A-24: #results-card is in the viewport after opening a run."""
    c = api_login(base_url)
    quiz = api_make_quiz(c, f"UI-Q24view {secrets.token_hex(3)}", publish=True)
    s = api_make_session(c, f"UI-Q24views {secrets.token_hex(3)}")
    api_queue_quiz_run(c, s["code"], quiz["id"])
    try:
        page.set_viewport_size({"width": 390, "height": 700})
        _goto_quizzes(page, base_url)
        page.locator("#qs-rows tr").filter(has_text=quiz["title"]).first.click()
        expect(page.locator("#results-card")).to_be_in_viewport(timeout=5000)
    finally:
        c.close()



def test_uc_a_24_results_card_opens_and_closes(base_url, admin_setup, page):
    """UC-A-24: clicking a #qs-rows row opens #results-card with per-question counts;
    #results-close closes it.
    """
    c = api_login(base_url)
    quiz = api_make_quiz(c, f"UI-Q24 {secrets.token_hex(3)}", publish=True)
    s = api_make_session(c, f"UI-Q24s {secrets.token_hex(3)}")
    api_queue_quiz_run(c, s["code"], quiz["id"])
    try:
        _goto_quizzes(page, base_url)
        row = page.locator("#qs-rows tr").filter(has_text=quiz["title"]).filter(has_text=s["code"])
        row.click()
        expect(page.locator("#results-card")).to_be_visible()
        expect(page.locator("#results-body")).to_contain_text("2+2?")
        link = page.locator("#results-body a", has_text="Open session page →")
        expect(link).to_have_attribute("href", f"/m/{s['code']}")
        expect(link).to_have_attribute("target", "_blank")
        page.click("#results-close")
        expect(page.locator("#results-card")).to_be_hidden()
    finally:
        c.close()


def test_uc_a_09_double_enter_creates_one_quiz(base_url, admin_setup, page):
    """UC-A-09: two quick Enter presses in #new-quiz-title create one quiz."""
    c = api_login(base_url)
    title = f"UI-Q09dd {secrets.token_hex(3)}"
    try:
        _goto_quizzes(page, base_url)
        page.fill("#new-quiz-title", title)
        page.evaluate("""() => {
          const field = document.querySelector("#new-quiz-title");
          for (let i = 0; i < 2; i++) {
            field.dispatchEvent(new KeyboardEvent("keydown",
              { key: "Enter", bubbles: true, cancelable: true }));
          }
        }""")
        expect(page.locator("#quiz-rows tr").filter(has_text=title)).to_have_count(1, timeout=5000)
        page.wait_for_timeout(500)
        quizzes = [q for q in c.get("/api/quizzes").json() if q["title"] == title]
        assert len(quizzes) == 1, quizzes
    finally:
        c.close()


def _broken_ready_quiz(c, title: str) -> dict:
    """A Ready quiz whose only question was then deleted: still Ready, but it
    fails the publish checks (UC-A-10 `problem`)."""
    quiz = api_make_quiz(c, title, publish=True)
    question = c.get(f"/api/quizzes/{quiz['id']}").json()["questions"][0]["id"]
    c.delete(f"/api/quiz_questions/{question}").raise_for_status()
    return quiz


def test_uc_a_10_needs_fixing_badge(base_url, admin_setup, page):
    """UC-A-10: a Ready quiz with a problem shows Ready and Needs fixing; a
    valid Ready quiz doesn't show Needs fixing."""
    c = api_login(base_url)
    broken = _broken_ready_quiz(c, f"UI-A10broken {secrets.token_hex(3)}")
    fine = api_make_quiz(c, f"UI-A10fine {secrets.token_hex(3)}", publish=True)
    try:
        _goto_quizzes(page, base_url)
        row = page.locator("#quiz-rows tr").filter(has_text=broken["title"])
        expect(row.locator(".badge-ready")).to_be_visible()
        expect(row.locator(".badge-needs-fixing")).to_have_text("Needs fixing")
        fine_row = page.locator("#quiz-rows tr").filter(has_text=fine["title"])
        expect(fine_row.locator(".badge-ready")).to_be_visible()
        expect(fine_row.locator(".badge-needs-fixing")).to_have_count(0)
    finally:
        c.close()


def test_uc_a_29_needs_fixing_quiz_cannot_be_added(base_url, admin_setup, page):
    """UC-A-29: the Add to session menu of a quiz that needs fixing explains
    why and lists no sessions."""
    c = api_login(base_url)
    broken = _broken_ready_quiz(c, f"UI-A29broken {secrets.token_hex(3)}")
    s = api_make_session(c, f"UI-A29bs {secrets.token_hex(3)}")
    try:
        _goto_quizzes(page, base_url)
        row = page.locator("#quiz-rows tr").filter(has_text=broken["title"])
        _open_add_menu(row)
        panel = row.locator("details.add-to-session .menu-panel")
        expect(panel).to_contain_text("Can't be added to a session yet: Quiz needs at least one question")
        expect(panel.locator("button")).to_have_count(0)
        assert c.get(f"/api/sessions/{s['code']}/quiz_runs").json() == []
    finally:
        c.close()


# ---------- review batch 5: editor and report wording ----------


def test_uc_a_10_editor_warns_when_an_edit_breaks_a_publish_rule(base_url, admin_setup, page):
    """UC-A-10: the open editor shows Needs fixing, the inline notes and the
    navigator after an edit breaks a publish rule, and hides them once the
    cause is gone."""
    c = api_login(base_url)
    quiz = api_make_quiz(c, f"UI-A10ed {secrets.token_hex(3)}", publish=True)
    try:
        _open_editor(page, base_url, quiz["title"])
        nav = page.locator("#editor-problem-nav")
        notes = page.locator("#editor-body .problem-note")
        badge = page.locator("#editor-body .badge-needs-fixing")
        expect(page.locator("#editor-body .badge-ready")).to_be_visible()
        expect(nav).to_be_hidden()
        expect(notes).to_have_count(0)
        # Clearing the text (a field edit, no re-render) breaks a rule.
        text = page.get_by_role("textbox", name="Question 1 text")
        text.fill("")
        text.press("Tab")
        expect(notes).to_have_text(["Add the question text"], timeout=5000)
        expect(page.locator("#editor-problem-count")).to_have_text("1 to fix")
        expect(badge).to_have_text("Needs fixing")
        text.fill("2+2?")
        text.press("Tab")
        expect(nav).to_be_hidden(timeout=5000)
        expect(notes).to_have_count(0)
        expect(badge).to_be_hidden()
        # A blank question at the end has no answers: the quiz stays Ready
        # but can't be added to a session.
        page.get_by_role("button", name="Add a question at the end").click()
        expect(page.locator("#editor-body .editor-q")).to_have_count(2)
        q2 = page.locator("#editor-body .editor-q").nth(1)
        expect(q2.locator(".problem-note")).to_have_text(
            ["Add at least 2 answers", "Mark exactly one correct answer"], timeout=5000)
        expect(q2).to_have_class(re.compile(r"\bhas-problem\b"))
        expect(page.locator("#editor-problem-count")).to_have_text("2 to fix")
        expect(badge).to_have_text("Needs fixing")
        q2.get_by_role("button", name="Delete", exact=True).click()
        accept_confirm(page, "Delete this question?", "Delete question")
        expect(page.locator("#editor-body .editor-q")).to_have_count(1, timeout=5000)
        expect(nav).to_be_hidden(timeout=5000)
        expect(notes).to_have_count(0)
        expect(badge).to_be_hidden()
    finally:
        c.close()


def test_uc_a_11_editor_controls_have_visible_words(base_url, admin_setup, page):
    """UC-A-11: the correct checkbox, the Poll toggle and the type select say
    what they mean in visible words; the hint names no Launch control."""
    c = api_login(base_url)
    quiz = api_make_quiz(c, f"UI-A11w {secrets.token_hex(3)}", questions=_valid_questions("q"))
    try:
        _open_editor(page, base_url, quiz["title"])
        first_answer = page.locator("#editor-body .editor-opt").first
        expect(first_answer.locator("label")).to_have_text("Correct")
        expect(page.get_by_role("checkbox", name="Answer 1 is correct")).to_be_visible()
        expect(page.locator("#editor-body .question-head .poll-toggle")).to_have_text("Poll (no correct answer)")
        options = page.get_by_label("Question 1 type").locator("option")
        expect(options).to_have_text(["Single choice", "Multiple choice"])
        body = page.locator("#editor-body")
        expect(body).not_to_contain_text("Launch")
        expect(body).to_contain_text(
            "Changes reach quizzes already added to a session when they start; past results stay as they were.")
    finally:
        c.close()


def test_uc_a_09_empty_title_says_title_is_required(base_url, admin_setup, page):
    """UC-A-09: + New with an empty title says so and creates nothing."""
    c = api_login(base_url)
    try:
        _goto_quizzes(page, base_url)
        before = len(c.get("/api/quizzes").json())
        page.fill("#new-quiz-title", "   ")
        page.click("#create-quiz")
        expect(page.locator(".toast-error")).to_contain_text("Quiz title is required")
        assert len(c.get("/api/quizzes").json()) == before
    finally:
        c.close()


def test_uc_a_12_empty_title_is_refused_and_restored(base_url, admin_setup, page):
    """UC-A-12: clearing the title shows the server's message and puts the
    saved title back."""
    c = api_login(base_url)
    quiz = api_make_quiz(c, f"UI-A12e {secrets.token_hex(3)}")
    try:
        _open_editor(page, base_url, quiz["title"])
        title = page.get_by_label("Quiz title", exact=True)
        title.fill("")
        title.blur()
        expect(page.locator(".toast-error")).to_contain_text("Quiz title is required")
        expect(page.get_by_label("Quiz title", exact=True)).to_have_value(quiz["title"])
        expect(page.locator("#editor-title")).to_contain_text(quiz["title"])
        assert c.get(f"/api/quizzes/{quiz['id']}").json()["title"] == quiz["title"]
    finally:
        c.close()


def test_uc_a_19_failed_answer_delete_shows_the_error(base_url, admin_setup, page):
    """UC-A-19: a failed delete shows the server's message, keeps the row, and
    raises no unhandled error."""
    c = api_login(base_url)
    quiz = api_make_quiz(
        c, f"UI-A19f {secrets.token_hex(3)}",
        questions=[{"text": "q", "answers": [{"text": "a"}, {"text": "b"}, {"text": "c"}]}],
    )
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.route("**/api/quiz_answers/*", lambda route: route.fulfill(
        status=500, content_type="application/json", body='{"detail": "Server is busy"}')
        if route.request.method == "DELETE" else route.continue_())
    try:
        _open_editor(page, base_url, quiz["title"])
        expect(page.locator("#editor-body .editor-opt")).to_have_count(3)
        page.locator("#editor-body .editor-opt").first.locator("button[aria-label='Delete answer']").click()
        expect(page.locator(".toast-error")).to_contain_text("Server is busy")
        expect(page.locator("#editor-body .editor-opt")).to_have_count(3)
        page.wait_for_timeout(200)
        assert errors == []
    finally:
        c.close()


def test_uc_a_20_refused_upload_shows_the_reason(base_url, admin_setup, page, tmp_path):
    """UC-A-20: a refused upload shows the server's reason, not "Upload failed"."""
    c = api_login(base_url)
    quiz = api_make_quiz(c, f"UI-A20r {secrets.token_hex(3)}", questions=_valid_questions("q"))
    notes = tmp_path / "notes.txt"
    notes.write_text("not an image")
    try:
        _open_editor(page, base_url, quiz["title"])
        page.locator("#editor-body .editor-q input[type=file]").first.set_input_files(str(notes))
        expect(page.locator(".toast-error")).to_have_text("Images must be PNG, JPEG, GIF or WebP")
    finally:
        c.close()


def test_uc_a_23_run_report_uses_plain_words(base_url, admin_setup, page):
    """UC-A-23: the report's headers are spelled out and its summary has no
    internal terms."""
    _goto_quizzes(page, base_url)
    headers = page.locator("#qs-table thead th")
    expect(headers).to_have_text(["Quiz", "Version", "In session", "Status", "Progress", "Responses", "Created"])
    for view in ("flat", "quiz", "version", "session"):
        page.click(f"[data-run-view={view}]")
        summary = page.locator("#qs-view-summary").inner_text()
        assert "playthrough" not in summary and "immutable" not in summary, summary


def test_uc_a_24_results_use_the_shared_answer_rows(base_url, admin_setup, page):
    """UC-A-24: the run report names the run, shows its version, and draws
    answers with the shared component ("✓ Correct", "n (p%)")."""
    c = api_login(base_url)
    quiz = api_make_quiz(c, f"UI-A24s {secrets.token_hex(3)}", publish=True)
    s = api_make_session(c, f"UI-A24ss {secrets.token_hex(3)}")
    run = api_queue_quiz_run(c, s["code"], quiz["id"])
    c.post(f"/api/sessions/{s['code']}/quiz_runs/{run['id']}/start").raise_for_status()
    c.post(f"/api/sessions/{s['code']}/quiz_runs/{run['id']}/close").raise_for_status()
    try:
        _goto_quizzes(page, base_url)
        page.goto(f"{base_url}/quizzes?run={run['id']}")
        expect(page.locator("#results-title")).to_have_text(f"Quiz run: {quiz['title']} · {s['title']}")
        body = page.locator("#results-body")
        expect(body).to_contain_text("Version 1")
        expect(body.locator(".option.correct .opt-correct")).to_have_text("✓ Correct")
        pcts = body.locator(".opt-pct").all_inner_texts()
        assert pcts and all(re.fullmatch(r"\d+ \(\d+%\)", p) for p in pcts), pcts
    finally:
        c.close()
