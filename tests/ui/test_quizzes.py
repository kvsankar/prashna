"""UI tests for /quizzes — quiz library, editor, publish, runs report.

Covers UC-A-09..22, UC-A-23, UC-A-24, UC-A-27.
"""
from __future__ import annotations

import secrets

from playwright.sync_api import expect

from ._helpers import (
    admin_login_via_ui,
    api_login,
    api_make_quiz,
    api_make_session,
    api_queue_quiz_run,
)


def _goto_quizzes(page, base_url):
    admin_login_via_ui(page, base_url)
    page.goto(base_url + "/quizzes")
    page.wait_for_selector("#quiz-rows")


# ---------- UC-A-09 ----------


def test_uc_a_09_create_quiz_opens_editor(base_url, admin_setup, page):
    """UC-A-09: typing a title + clicking +New adds a #quiz-rows row and opens #editor-card."""
    _goto_quizzes(page, base_url)
    title = f"UI-Q09 {secrets.token_hex(3)}"
    page.fill("#new-quiz-title", title)
    page.click("#create-quiz")
    expect(page.locator("#quiz-rows tr").filter(has_text=title)).to_be_visible()
    expect(page.locator("#editor-card")).to_be_visible()
    expect(page.locator("#editor-title")).to_contain_text(title)


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
        # Question text is rendered into a textarea (text content).
        expect(page.locator("#editor-body textarea")).to_have_value("Sky color?")
        # Answer texts live in input values, not visible text.
        expect(page.locator("#editor-body input[type='text']").first).to_have_value("blue")
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
    """UC-A-13: clicking Delete on an unused quiz (after confirm) removes the row."""
    c = api_login(base_url)
    quiz = api_make_quiz(c, f"UI-Q13 {secrets.token_hex(3)}")
    try:
        _goto_quizzes(page, base_url)
        page.on("dialog", lambda d: d.accept())
        row = page.locator("#quiz-rows tr").filter(has_text=quiz["title"])
        row.locator("button.danger").click()
        expect(page.locator("#quiz-rows tr").filter(has_text=quiz["title"])).to_have_count(0, timeout=5000)
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
        page.on("dialog", lambda d: d.accept())
        row = page.locator("#quiz-rows tr").filter(has_text=quiz["title"])
        row.locator("button.danger").click()
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
        row.get_by_role("button", name="Duplicate").click()
        copy_row = page.locator("#quiz-rows tr").filter(has_text=copy_title)
        expect(copy_row).to_be_visible()
        expect(copy_row.locator(".badge-draft")).to_be_visible()
        expect(page.locator("#editor-card")).to_be_visible()
        expect(page.locator("#editor-title")).to_contain_text(copy_title)
    finally:
        c.close()


# ---------- UC-A-14 ----------


def test_uc_a_14_add_question_appends_row(base_url, admin_setup, page):
    """UC-A-14: + Add question appends a new question row with 'New question' text."""
    c = api_login(base_url)
    quiz = api_make_quiz(c, f"UI-Q14 {secrets.token_hex(3)}")
    try:
        _goto_quizzes(page, base_url)
        page.locator("#quiz-rows tr").filter(has_text=quiz["title"]).click()
        before = page.locator("#editor-body .editor-q").count()
        page.locator("#editor-body button", has_text="+ Add question").click()
        # Wait for re-render.
        expect(page.locator("#editor-body .editor-q")).to_have_count(before + 1, timeout=5000)
        # New question textarea contains "New question".
        expect(page.locator("#editor-body textarea").last).to_have_value("New question")
    finally:
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
        page.on("dialog", lambda d: d.accept())
        page.locator("#editor-body .editor-q").first.locator("button.danger", has_text="Delete").click()
        expect(page.locator("#editor-body .editor-q")).to_have_count(1, timeout=5000)
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


def test_uc_a_21_publish_invalid_quiz_toasts_error(base_url, admin_setup, page):
    """UC-A-21: publishing an invalid (empty) quiz toasts the failing-rule and badge stays draft."""
    c = api_login(base_url)
    quiz = api_make_quiz(c, f"UI-Q21bad {secrets.token_hex(3)}")
    try:
        _goto_quizzes(page, base_url)
        row = page.locator("#quiz-rows tr").filter(has_text=quiz["title"])
        row.locator("button", has_text="Publish").click()
        expect(page.locator(".toast-error")).to_contain_text("Quiz needs at least one question")
        expect(row.locator(".badge-draft")).to_be_visible()
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


# ---------- UC-A-23 ----------


def test_quiz_library_breadcrumbs_link_admin_and_report_sections(
    base_url, admin_setup, page
):
    """Quiz authoring remains visibly nested under the admin role."""
    _goto_quizzes(page, base_url)
    crumbs = page.locator(".breadcrumbs")
    expect(crumbs).to_contain_text("Admin")
    expect(crumbs).to_contain_text("Quiz library")
    expect(crumbs.locator("a", has_text="Admin")).to_have_attribute("href", "/")
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
        page.click("#results-close")
        expect(page.locator("#results-card")).to_be_hidden()
    finally:
        c.close()
