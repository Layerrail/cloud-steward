from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / "artifacts"
IMAGES = ROOT / "docs" / "images"
EDGE = Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe")
URL = "https://cloud-steward.onrender.com"


def record() -> None:
    ARTIFACTS.mkdir(exist_ok=True)
    IMAGES.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path=EDGE, headless=True)
        context = browser.new_context(
            viewport={"width": 1280, "height": 720},
            record_video_dir=ARTIFACTS,
            record_video_size={"width": 1280, "height": 720},
            color_scheme="light",
        )
        page = context.new_page()
        page.goto(URL, wait_until="networkidle", timeout=120_000)
        page.screenshot(path=IMAGES / "cloud-steward-hero.png", full_page=False)
        page.wait_for_timeout(5_000)

        page.locator("[data-demo]").click()
        page.locator("#composer").scroll_into_view_if_needed()
        page.wait_for_timeout(5_000)

        page.locator("#plan-form").evaluate("form => form.requestSubmit()")
        page.locator("#result-section").wait_for(state="visible", timeout=30_000)
        page.locator("#result-section").scroll_into_view_if_needed()
        page.wait_for_timeout(6_000)
        page.screenshot(path=IMAGES / "cloud-steward-plan.png", full_page=False)

        for action in page.locator(".action-item").all():
            action.scroll_into_view_if_needed()
            page.wait_for_timeout(2_000)

        page.locator("#approve-button").scroll_into_view_if_needed()
        page.wait_for_timeout(3_000)
        page.locator("#approve-button").click()
        page.locator("#approval-status").filter(has_text="Recorded").wait_for(timeout=20_000)
        page.wait_for_timeout(5_000)

        page.locator(".history-section").scroll_into_view_if_needed()
        page.wait_for_timeout(5_000)
        video = page.video
        if video is None:
            raise RuntimeError("Playwright did not create a video")
        page.close()
        video.save_as(ARTIFACTS / "cloud-steward-demo-silent.webm")
        context.close()
        browser.close()


if __name__ == "__main__":
    record()
