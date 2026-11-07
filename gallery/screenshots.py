"""Write the screenshots of docs/design-system.md: each group of the gallery, in light and dark mode.

Run it from gallery/ after a change to duckkit's look, and before a release: `uv run python screenshots.py`. The first
time, install the browser: `uv run playwright install chromium`. It starts the gallery on its own port, and stops it.
"""

import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

GALLERY = Path(__file__).parent
OUT = GALLERY.parent / "docs" / "design-system"
PORT = 8691  # not the gallery's own 8690, which may be open in a browser
URL = f"http://localhost:{PORT}"
WIDTH = 1200
SCALE = 2  # sharp text on a high-density screen
SETTLE = 1.5  # seconds for charts to draw and animate (theme.base_option: 400 ms) once the page is still
# Hidden in the group shots: the Ask button and Streamlit's header float over whatever is under them. The drawer has a
# shot of its own. The header's only key is its test id.
HIDE = '.st-key-ui-ask-button, [data-testid="stHeader"] { visibility: hidden; }'



def start() -> subprocess.Popen:
    server = subprocess.Popen(
        [sys.executable, "-m", "streamlit", "run", "app.py", "--server.port", str(PORT)],
        cwd=GALLERY, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        try:
            urllib.request.urlopen(f"{URL}/_stcore/health", timeout=1)
            return server
        except OSError:
            time.sleep(0.25)
    server.terminate()
    raise SystemExit(f"the gallery did not start on {URL}")


def still(page: Page) -> None:
    """Wait until Streamlit has finished its run, and the charts have drawn."""
    page.wait_for_selector('[data-testid="stApp"][data-test-script-state="notRunning"]', timeout=60_000)
    page.wait_for_load_state("networkidle")
    time.sleep(SETTLE)


def whole(page: Page) -> None:
    """Make the window as tall as the page. Streamlit scrolls its own container, not the window, so a shot of anything
    below the first screen would come out blank."""
    height = page.evaluate('document.querySelector(\'[data-testid="stMain"]\').scrollHeight')
    page.set_viewport_size({"width": WIDTH, "height": height + 100})
    time.sleep(SETTLE)  # the charts redraw at the new size


def select_row(page: Page) -> None:
    """Select a row of the gallery's table, so the shot shows a selection. The table is a canvas: the click goes to the
    row's checkbox, by position."""
    row, header, height = 5, 35, 33  # 20 Feb, the top of the chart; Streamlit's sizes for a row, in CSS pixels
    page.locator(".st-key-demo-days").click(position={"x": 18, "y": header + row * height + height // 2})
    page.wait_for_selector('[data-testid="stApp"][data-test-script-state="running"]', timeout=5_000)
    page.mouse.move(0, 0)  # off the table, which shows its toolbar while the mouse is over it
    still(page)


def shoot(page: Page, mode: str) -> list[Path]:
    page.goto(URL)
    still(page)
    whole(page)
    select_row(page)
    page.add_style_tag(content=HIDE)
    written = []
    for group in page.locator('[class*="st-key-gallery-"]:not([class*="st-key-gallery-block-"])').all():
        key = next(c for c in group.get_attribute("class").split() if c.startswith("st-key-gallery-"))
        path = OUT / f"{key.removeprefix('st-key-gallery-')}-{mode}.png"
        group.screenshot(path=path, animations="disabled")
        written.append(path)
    page.set_viewport_size({"width": WIDTH, "height": 900})
    page.goto(URL)
    still(page)
    path = OUT / f"overview-{mode}.png"  # the first screen as a viewer sees it: the sidebar and the Ask button
    page.screenshot(path=path, animations="disabled")
    written.append(path)
    page.get_by_role("button", name="Ask", exact=True).click()
    page.wait_for_selector('[role="dialog"]')
    time.sleep(SETTLE)
    path = OUT / f"ask-drawer-{mode}.png"
    page.screenshot(path=path, animations="disabled")
    written.append(path)
    return written


def main() -> None:
    OUT.mkdir(exist_ok=True)
    server = start()
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            for mode in ("light", "dark"):
                page = browser.new_page(viewport={"width": WIDTH, "height": 900}, device_scale_factor=SCALE,
                                        color_scheme=mode)
                for path in shoot(page, mode):
                    print(f"{path.relative_to(GALLERY.parent)}  {path.stat().st_size // 1024} KB")
                page.close()
            browser.close()
    finally:
        server.terminate()


if __name__ == "__main__":
    main()
