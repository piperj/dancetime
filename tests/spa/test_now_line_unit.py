"""
Unit tests for static/now-line.js's pure math (static/now-line.js: NowLine._test).

Deliberately does NOT use spa_server/wait_for_spa or any competition data --
loads a blank page and injects only now-line.js, then calls its exposed pure
functions directly. now-line.js's init() early-returns when #scheduleContent
is missing (as it is here), but the _test namespace's functions take
stops/t/viewportH as plain arguments with no DOM reads, so they work with no
app around them at all. See tests/spa/test_now_line.py for the integration
tier that exercises the module wired into the real running app.
"""
import pytest
from .conftest import REPO_ROOT

pytest.importorskip("playwright.sync_api", reason="playwright not installed")

NOW_LINE_JS = REPO_ROOT / "static" / "now-line.js"


@pytest.fixture
def now_line_page(browser):
    ctx = browser.new_context()
    page = ctx.new_page()
    page.set_content("<!doctype html><html><body></body></html>")
    page.add_script_tag(path=str(NOW_LINE_JS))
    yield page
    ctx.close()


def _stops(page, pairs):
    """pairs: list of (t, y) -> stops array as NowLine._test expects."""
    return page.evaluate(
        "pairs => pairs.map(([t, y]) => ({t, y}))",
        pairs,
    )


class TestSmoothstep:
    def test_endpoints(self, now_line_page):
        page = now_line_page
        assert page.evaluate("NowLine._test.smoothstep(0)") == 0
        assert page.evaluate("NowLine._test.smoothstep(1)") == 1

    def test_monotonic(self, now_line_page):
        page = now_line_page
        xs = [i / 10 for i in range(11)]
        ys = page.evaluate("xs => xs.map(x => NowLine._test.smoothstep(x))", xs)
        assert ys == sorted(ys)
        assert 0 < ys[5] < 1


class TestContentYFor:
    def test_empty_stops_is_zero(self, now_line_page):
        assert now_line_page.evaluate("NowLine._test.contentYFor([], 12345)") == 0

    def test_clamps_before_first_stop(self, now_line_page):
        page = now_line_page
        stops = _stops(page, [(1000, 100), (2000, 200)])
        y = page.evaluate("([stops]) => NowLine._test.contentYFor(stops, 0)", [stops])
        assert y == 100

    def test_clamps_after_last_stop(self, now_line_page):
        page = now_line_page
        stops = _stops(page, [(1000, 100), (2000, 200)])
        y = page.evaluate("([stops]) => NowLine._test.contentYFor(stops, 999999)", [stops])
        assert y == 200

    def test_holds_until_lead_in_window(self, now_line_page):
        """More than LEAD_MS before the next stop, the line hasn't budged yet."""
        page = now_line_page
        lead = page.evaluate("NowLine._test.LEAD_MS")
        stops = _stops(page, [(0, 100), (10 * lead, 200)])
        y = page.evaluate("([stops]) => NowLine._test.contentYFor(stops, 5 * " + str(lead) + ")", [stops])
        assert y == 100

    def test_eases_inside_lead_in_window(self, now_line_page):
        """Inside the last LEAD_MS before the next stop, the line has moved
        partway there but hasn't fully arrived."""
        page = now_line_page
        lead = page.evaluate("NowLine._test.LEAD_MS")
        stops = _stops(page, [(0, 100), (10 * lead, 200)])
        t = 10 * lead - lead // 2  # halfway through the lead-in window
        y = page.evaluate(f"([stops]) => NowLine._test.contentYFor(stops, {t})", [stops])
        assert 100 < y < 200

    def test_arrives_exactly_at_stop_time(self, now_line_page):
        page = now_line_page
        lead = page.evaluate("NowLine._test.LEAD_MS")
        stops = _stops(page, [(0, 100), (10 * lead, 200)])
        y = page.evaluate(f"([stops]) => NowLine._test.contentYFor(stops, {10 * lead})", [stops])
        assert y == 200


class TestScrollTargetFor:
    def test_offsets_by_viewport_fraction(self, now_line_page):
        page = now_line_page
        stops = _stops(page, [(0, 500)])
        fraction = page.evaluate("NowLine._test.LINE_FRACTION")
        target = page.evaluate("([stops]) => NowLine._test.scrollTargetFor(stops, 0, 1000)", [stops])
        assert target == pytest.approx(500 - 1000 * fraction)


class TestTrackedScroll:
    def test_additive(self, now_line_page):
        page = now_line_page
        assert page.evaluate("NowLine._test.trackedScroll(700, -50)") == 650
        assert page.evaluate("NowLine._test.trackedScroll(700, 0)") == 700

    def test_same_velocity_as_target(self, now_line_page):
        """The core hand-over guarantee: with a fixed offset, tracked scroll
        moves by exactly however much the target itself moved."""
        page = now_line_page
        before = page.evaluate("NowLine._test.trackedScroll(1000, 30)")
        after = page.evaluate("NowLine._test.trackedScroll(1120, 30)")
        assert after - before == 120
