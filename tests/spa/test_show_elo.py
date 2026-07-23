"""
Suite C — locks the ?show_elo=1 gate on the Ladder and Ranking (ELO) tabs.

By default the Ladder and Ranking nav buttons must stay hidden and
unreachable, since their ELO scores can be hurtful to dance friends even
though the numbers are objective. Only ?show_elo=1 in the URL unlocks them.
"""
import pytest
from .conftest import ensure_ranking_tab_visible, wait_for_spa

pytest.importorskip("playwright.sync_api", reason="playwright not installed")


class TestShowEloGate:
    def test_ladder_and_ranking_hidden_by_default(self, page, spa_server):
        """Without ?show_elo=1, both nav buttons are hidden regardless of data."""
        wait_for_spa(page, spa_server)
        ensure_ranking_tab_visible(page)

        ranking_hidden = page.evaluate(
            "() => document.querySelector(\"nav button[data-tab='ranking']\").classList.contains('hidden')"
        )
        elo_hidden = page.evaluate(
            "() => document.querySelector(\"nav button[data-tab='elo']\").classList.contains('hidden')"
        )
        assert ranking_hidden, "Ladder nav button should be hidden without ?show_elo=1"
        assert elo_hidden, "Ranking nav button should be hidden without ?show_elo=1"

    def test_hidden_tabs_not_reachable_by_click(self, page, spa_server):
        """Nav buttons are hidden (not just visually styled) so Playwright can't click them."""
        wait_for_spa(page, spa_server)
        ensure_ranking_tab_visible(page)

        with pytest.raises(Exception):
            page.click("nav button[data-tab='ranking']", timeout=1000)

    def test_active_tab_falls_back_to_heats_if_gate_revoked_midsession(self, page, spa_server):
        """If the URL's show_elo param disappears mid-session, re-evaluating visibility
        bounces an active Ladder tab back to Heats rather than leaving it stranded open."""
        wait_for_spa(page, spa_server, query="?show_elo=1")
        ensure_ranking_tab_visible(page)
        page.click("nav button[data-tab='ranking']")
        page.wait_for_timeout(300)
        assert page.evaluate("() => activeTab") == "ranking"

        # Strip show_elo from the URL without navigating, then re-run the same
        # visibility check the app runs on every data refresh / tab click.
        page.evaluate("() => { history.replaceState(null, '', location.pathname); updateTabVisibility(); }")

        active_tab = page.evaluate("() => activeTab")
        assert active_tab == "heats", f"expected fallback to heats tab, got '{active_tab}'"
        ranking_hidden = page.evaluate(
            "() => document.querySelector(\"nav button[data-tab='ranking']\").classList.contains('hidden')"
        )
        assert ranking_hidden, "Ladder nav button should re-hide once show_elo is gone"

    def test_show_elo_param_reveals_tabs(self, page, spa_server):
        """?show_elo=1 unhides both nav buttons and they're clickable."""
        wait_for_spa(page, spa_server, query="?show_elo=1")
        ensure_ranking_tab_visible(page)

        ranking_hidden = page.evaluate(
            "() => document.querySelector(\"nav button[data-tab='ranking']\").classList.contains('hidden')"
        )
        elo_hidden = page.evaluate(
            "() => document.querySelector(\"nav button[data-tab='elo']\").classList.contains('hidden')"
        )
        assert not ranking_hidden, "Ladder nav button should be visible with ?show_elo=1"
        assert not elo_hidden, "Ranking nav button should be visible with ?show_elo=1"

        page.click("nav button[data-tab='ranking']")
        page.wait_for_timeout(300)
        active_tab = page.evaluate("() => document.querySelector('nav button.active').dataset.tab")
        assert active_tab == "ranking"

    def test_show_elo_zero_does_not_reveal_tabs(self, page, spa_server):
        """Only the exact value '1' unlocks — ?show_elo=0 (or anything else) stays hidden."""
        wait_for_spa(page, spa_server, query="?show_elo=0")
        ensure_ranking_tab_visible(page)

        ranking_hidden = page.evaluate(
            "() => document.querySelector(\"nav button[data-tab='ranking']\").classList.contains('hidden')"
        )
        assert ranking_hidden, "Ladder nav button should stay hidden for show_elo values other than '1'"
