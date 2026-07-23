"""Shared fixtures for Playwright/WebKit SPA tests."""
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

playwright_mod = pytest.importorskip("playwright.sync_api", reason="playwright not installed")

REPO_ROOT = Path(__file__).parent.parent.parent


def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="session")
def spa_server():
    """Serve the repo root over HTTP so fetch() works (file:// blocks CORS)."""
    port = _free_port()
    proc = subprocess.Popen(
        [sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1"],
        cwd=REPO_ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    # Wait until the port accepts connections
    deadline = time.time() + 5
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                break
        except OSError:
            time.sleep(0.05)
    yield f"http://127.0.0.1:{port}"
    proc.terminate()
    proc.wait()


@pytest.fixture(scope="session")
def browser():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.webkit.launch(headless=True)
        yield b
        b.close()


@pytest.fixture
def page(browser, spa_server):
    """Fresh page for each test; waits for the SPA to finish loading."""
    ctx = browser.new_context(base_url=spa_server)
    pg = ctx.new_page()
    yield pg
    ctx.close()


def wait_for_spa(page, spa_server, path=""):
    """Navigate to index.html and wait for the SPA data to load."""
    page.goto(f"{spa_server}/{path}index.html")
    # Status div gets class 'hidden' on success; text changes on error.
    # Either way, 'Loading' as the only content means we're still waiting.
    page.wait_for_function(
        """() => {
            const s = document.getElementById('status');
            return s.classList.contains('hidden') || !s.textContent.includes('Loading');
        }""",
        timeout=15_000,
    )


# Hawaii Star Ball 2024 (finished long ago, so its results never change) — the
# smallest ranking dataset that reliably has non-empty leaderboards, for tests
# that need the Ladder tab. The SPA's default competition is whichever has the
# latest start_date, which for a not-yet-started comp has zero ranking data
# and hides the Ladder tab entirely.
RANKING_FIXTURE_CYI = 1049


def ensure_ranking_tab_visible(page):
    """Switch to a competition with non-empty ranking data, if the active one has none.

    `compList`, `rankingData`, and `selectComp` are top-level bindings in
    index.html's classic (non-module) <script>, so they're reachable by name
    from page.evaluate even though they aren't attached to `window`.
    """
    has_ranking = page.evaluate(
        "() => Object.values(rankingData?.leaderboards ?? {}).some(lb => lb.couples?.length > 0)"
    )
    if has_ranking:
        return
    idx = page.evaluate(f"() => compList.findIndex(c => c.cyi === {RANKING_FIXTURE_CYI})")
    if idx == -1:
        pytest.skip(f"ranking fixture competition (cyi {RANKING_FIXTURE_CYI}) not present in data/index.json")
    page.evaluate(f"() => selectComp({idx})")
    page.wait_for_function(
        "() => Object.values(rankingData?.leaderboards ?? {}).some(lb => lb.couples?.length > 0)",
        timeout=15_000,
    )
