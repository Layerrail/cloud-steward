import os
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / "artifacts"
IMAGES = ROOT / "docs" / "images"
EDGE = Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe")
URL = os.getenv("CLOUD_STEWARD_DEMO_URL", "https://cloud-steward.onrender.com")
NAME = os.getenv("CLOUD_STEWARD_DEMO_NAME", "demo")
GOAL = os.getenv("CLOUD_STEWARD_DEMO_GOAL")
CONTEXT_QUERY = os.getenv("CLOUD_STEWARD_DEMO_CONTEXT_QUERY")


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
        page.route("https://fonts.googleapis.com/**", lambda route: route.abort())
        page.route("https://fonts.gstatic.com/**", lambda route: route.abort())
        page.goto(URL, wait_until="domcontentloaded", timeout=120_000)
        page.locator("#integrations .integration").first.wait_for(timeout=30_000)
        page.screenshot(path=IMAGES / f"cloud-steward-{NAME}-hero.png", full_page=False)
        print("Captured integration status", flush=True)
        page.wait_for_timeout(5_000)

        if GOAL:
            page.locator("#goal").fill(GOAL)
        else:
            page.locator("[data-demo]").click()
        if CONTEXT_QUERY:
            page.locator("#context-query").fill(CONTEXT_QUERY)
        page.locator("#composer").evaluate(
            "element => element.scrollIntoView({block: 'start'})"
        )
        page.wait_for_timeout(5_000)

        page.locator("#plan-form").evaluate("form => form.requestSubmit()")
        print("Submitted governed plan request", flush=True)
        page.locator("#result-section").wait_for(state="visible", timeout=300_000)
        print("Received governed plan", flush=True)
        page.locator("#result-section").scroll_into_view_if_needed()
        page.wait_for_timeout(6_000)
        page.screenshot(path=IMAGES / f"cloud-steward-{NAME}-plan.png", full_page=False)

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
        context.close()
        print("Finalized browser recording", flush=True)
        video.save_as(ARTIFACTS / f"cloud-steward-{NAME}-silent.webm")
        print("Saved browser recording", flush=True)
        browser.close()


if __name__ == "__main__":
    record()
