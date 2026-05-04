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
