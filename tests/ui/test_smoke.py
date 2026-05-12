"""Smoke test that the UI scaffolding works."""
from playwright.sync_api import sync_playwright


def test_landing_renders(base_url, admin_setup):
    with sync_playwright() as p:
        b = p.chromium.launch()
        try:
            page = b.new_page()
            page.goto(base_url + "/")
            assert "Prashna" in page.title() or page.locator("h1").inner_text() == "Prashna"
        finally:
            b.close()
