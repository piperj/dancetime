"""
Integration tests for the "Now" line (static/now-line.js) wired into the
real running app -- see tests/spa/test_now_line_unit.py for the isolated
pure-math tier.

CYI 373 is a finished competition, so Date.now() during a test run is well
outside any heat's real time range -- the line clamps to the first or last
stop deterministically. Assertions here are structural/behavioral, not
exact live positioning (see CLAUDE.md's own note on this under Known
Corpus/Debug Scripts -- these tests inherit the same constraint as the
"live" NDCA test).
"""
import pytest
from .conftest import wait_for_spa

pytest.importorskip("playwright.sync_api", reason="playwright not installed")

CYI = 373


def _select_comp(page, cyi):
    page.evaluate(f"selectComp(compList.findIndex(c => c.cyi === {cyi}))")
    page.wait_for_function(
        """() => {
            const s = document.getElementById('status');
            return s.classList.contains('hidden') || !s.textContent.includes('Loading');
        }""",
        timeout=15_000,
    )


def _setup_all_heats(page, spa_server, query=""):
    wait_for_spa(page, spa_server, query=query)
    _select_comp(page, CYI)
    page.evaluate("setHeatsSearch('')")  # empty search -> all-heats view
    page.wait_for_selector("#now-fab")
    page.wait_for_timeout(100)  # let the rAF loop run a couple of frames


class TestTabVisibility:
    """Uses the Elo tab, not Ladder/Ranking, to switch away from Heats --
    per CLAUDE.md's documented `?show_elo=1` gate, the Ladder tab also needs
    non-empty ranking data to be visible/clickable, while the Elo tab only
    needs the gate itself, so it's the simpler tab to switch to here."""

    def test_root_hidden_on_elo_tab(self, page, spa_server):
        _setup_all_heats(page, spa_server, query="?show_elo=1")
        assert "hidden" not in (page.locator("#now-line-root").get_attribute("class") or "")

        page.locator('nav button[data-tab="elo"]').click()
        page.wait_for_timeout(50)
        assert "hidden" in (page.locator("#now-line-root").get_attribute("class") or "")

    def test_no_scroll_writes_while_on_another_tab(self, page, spa_server):
        _setup_all_heats(page, spa_server, query="?show_elo=1")
        page.locator('nav button[data-tab="elo"]').click()
        page.wait_for_timeout(50)

        # #scheduleContent is hidden on the Elo tab, so the page has little
        # to no scrollable height left -- an injected scrollTo() would just
        # get silently re-clamped by the browser itself, which isn't what
        # this is testing. Assert stability instead: whatever scrollY
        # settles to, it shouldn't keep changing on its own.
        first = page.evaluate("window.scrollY")
        page.wait_for_timeout(300)  # several rAF frames' worth
        second = page.evaluate("window.scrollY")
        assert first == second, \
            "NowLine kept writing scrollY while the Heats tab wasn't active"


class TestLinePosition:
    def test_line_within_stop_bounds(self, page, spa_server):
        _setup_all_heats(page, spa_server)
        stops = page.evaluate("NowLine._test.debugStops()")
        assert len(stops) > 0
        ys = [s["y"] for s in stops]
        line_top = page.evaluate("parseFloat(document.getElementById('now-line').style.top)")
        assert min(ys) - 1 <= line_top <= max(ys) + 1


class TestFab:
    def test_fab_exists_and_toggles(self, page, spa_server):
        _setup_all_heats(page, spa_server)
        fab = page.locator("#now-fab")
        assert fab.count() == 1
        ring = page.locator("#now-fab .now-fab-ring")
        before = ring.get_attribute("stroke")
        fab.click()
        page.wait_for_timeout(400)  # past the single/double-tap commit delay
        after = ring.get_attribute("stroke")
        assert after != before


class TestUserScrollTakesPrecedence:
    def test_wheel_scroll_is_not_fought(self, page, spa_server):
        _setup_all_heats(page, spa_server)
        page.mouse.move(200, 300)
        page.mouse.wheel(0, 400)
        page.wait_for_timeout(500)  # comfortably past the release debounce
        after_settle = page.evaluate("window.scrollY")

        page.wait_for_timeout(300)
        still = page.evaluate("window.scrollY")
        assert still == after_settle, "scroll position drifted/jittered after settling"

    def test_double_tap_fab_moves_toward_target(self, page, spa_server):
        _setup_all_heats(page, spa_server)
        page.mouse.move(200, 300)
        # CYI 373 is finished, so "now" clamps to the last stop -- the line
        # tracks all the way to the bottom of a long list. Scrolling further
        # down would be a no-op (already maxed out), leaving nothing for
        # double-tap to correct, so scroll up instead to create a real gap.
        page.mouse.wheel(0, -600)
        page.wait_for_timeout(400)
        before = page.evaluate("window.scrollY")

        page.locator("#now-fab").dblclick()
        page.wait_for_timeout(200)
        after = page.evaluate("window.scrollY")
        assert after != before, "double-tap on the FAB should recenter the screen"


class TestCardExpandRebuildsStops:
    def test_expanding_a_card_updates_stops(self, page, spa_server):
        _setup_all_heats(page, spa_server)
        before = page.evaluate("NowLine._test.debugStops()")

        page.locator("[data-role='couples-pill']").first.click()
        page.wait_for_timeout(150)  # MutationObserver callback + next rAF frame

        after = page.evaluate("NowLine._test.debugStops()")
        assert len(after) == len(before)
        assert any(a["y"] != b["y"] for a, b in zip(after, before)), \
            "expanding a card's couples list should shift stop positions below it"


class TestBackgroundingGuard:
    def test_mid_gesture_hide_clears_frozen_state(self, page, spa_server):
        _setup_all_heats(page, spa_server)

        # Start a gesture with no matching pointerup -- the OS can swallow it
        # on a real screen lock / app switch.
        page.locator("#scheduleContent").dispatch_event("pointerdown")
        page.wait_for_timeout(20)
        assert page.evaluate("NowLine.isInteracting()") is True

        # Simulate the page being hidden -- document.hidden is normally a
        # read-only getter, so it's stubbed for this test.
        page.evaluate("""() => {
            Object.defineProperty(document, 'hidden', { value: true, configurable: true });
            document.dispatchEvent(new Event('visibilitychange'));
        }""")
        page.wait_for_timeout(20)
        assert page.evaluate("NowLine.isInteracting()") is False, \
            "a mid-gesture backgrounding should force-clear the frozen state, not leave it stuck"


class TestRegressionOldNextHeatMarkerRemoved:
    def test_hamburger_has_no_current_heat_entry(self, page, spa_server):
        _setup_all_heats(page, spa_server)
        page.locator('button[aria-label="Navigate"]').click()
        items = page.locator("#navigator-items div").all_text_contents()
        assert not any("Current heat" in t for t in items)

    def test_no_next_heat_marker_in_dom(self, page, spa_server):
        _setup_all_heats(page, spa_server)
        assert page.locator("#nextHeatMarker").count() == 0
        assert page.locator(".next-marker").count() == 0

    def test_all_done_marker_still_present_for_finished_competitor(self, page, spa_server):
        """A finished competition's individual-competitor view should still
        show the unrelated '✅ All done!' marker -- only the next-heat scroll
        marker was replaced, not this one."""
        wait_for_spa(page, spa_server)
        _select_comp(page, CYI)
        name = page.evaluate("heatsData.competitors[0]")
        page.evaluate(f"setHeatsSearch({name!r})")
        page.wait_for_timeout(100)
        assert page.locator("#allDoneMarker").count() == 1
