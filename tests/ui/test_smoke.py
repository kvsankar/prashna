"""Smoke test that the UI scaffolding works."""


def test_landing_renders(base_url, admin_setup, page):
    page.goto(base_url + "/")
    # Landing page shows the title in the header.
    assert page.locator("h1").first.inner_text() == "Prashna"
