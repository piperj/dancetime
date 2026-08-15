"""
Heat card click behaviour (static/heat-card.js: HeatCard).

The redesigned model (all four heat-card views -- Studio, Bib, All-Heats,
individual competitor -- render identically):
  - the couples-count pill ("N couples" / "Solo on floor") is the *only*
    thing that opens the couples list
  - a Contested pill is the *only* thing that opens its judges-score panel,
    and is inert (no click) until the event has at least one posted result
  - clicking anywhere else on the card (blank space, a couples row, inside
    an open judges panel) unconditionally closes whatever's open -- it never
    opens anything
  - at most one expansion (couples list, or one specific judges panel) is
    open per card at a time

Fixture: data/heats/373.json heat 101 (session 01) genuinely has two
independently-contested events on the same physical heat (event 7:
"L-S1 Cl. Pre-Silver Merengue", event 8: "G-C Open Bronze Merengue"), both
already scored -- exactly the two-pills-in-one-card shape needed to test the
accordion behaviour, with no network mocking required since we never wait
for the live NDCA fetch to resolve.
"""
import pytest
from .conftest import wait_for_spa

pytest.importorskip("playwright.sync_api", reason="playwright not installed")

CYI = 373
HEAT_NUMBER = "101"


def _select_comp(page, cyi):
    page.evaluate(f"selectComp(compList.findIndex(c => c.cyi === {cyi}))")
    page.wait_for_function(
        """() => {
            const s = document.getElementById('status');
            return s.classList.contains('hidden') || !s.textContent.includes('Loading');
        }""",
        timeout=15_000,
    )


def _setup(page, spa_server):
    wait_for_spa(page, spa_server)
    _select_comp(page, CYI)
    page.evaluate("setHeatsSearch('')")  # empty search -> all-heats view


def _heat_box(page):
    """The .heat-box for HEAT_NUMBER -- exact match on the <strong> heat number,
    since a substring match could hit e.g. heat '1101' too."""
    return page.locator(
        f"xpath=//div[contains(@class,'heat-box')]"
        f"[.//strong[normalize-space(text())='{HEAT_NUMBER}']]"
    )


def _couples_pill(page):
    return _heat_box(page).locator("[data-role='couples-pill']")


def _open_couples(page):
    _couples_pill(page).click()


def _card_expanded(page):
    return "expanded" in (_heat_box(page).locator(".heat-details").first.get_attribute("class") or "")


def _pills(page):
    return _heat_box(page).locator("[data-role='contested-pill']")


def _panel_expanded(page, pill_index):
    # Scoped to *this* heat box -- the all-heats view has many other
    # Contested pills on the page, so a page-wide query would pick up the
    # wrong index entirely.
    panel_key = page.evaluate(
        "([box, i]) => box.querySelectorAll('[data-role=\"contested-pill\"]')[i].dataset.panelKey",
        [_heat_box(page).element_handle(), pill_index],
    )
    el = _heat_box(page).locator(f'[data-role="judges-panel"][data-panel-key="{panel_key}"]')
    return "expanded" in (el.get_attribute("class") or "")


class TestHeatCardClose:
    def test_two_contested_pills_present(self, page, spa_server):
        """Sanity check on the fixture: heat 101 has two independent Contested pills."""
        _setup(page, spa_server)
        assert _pills(page).count() == 2

    def test_couples_pill_opens_and_closes_list(self, page, spa_server):
        _setup(page, spa_server)
        assert not _card_expanded(page)

        _open_couples(page)
        assert _card_expanded(page)

        _open_couples(page)  # second click toggles closed
        assert not _card_expanded(page)

    def test_click_couples_row_closes_expanded_card(self, page, spa_server):
        """Clicking a plain competitor row inside an expanded card closes it."""
        _setup(page, spa_server)
        _open_couples(page)
        assert _card_expanded(page)

        # Plain competitor rows are the only unclassed <div>s in the expanded
        # area (everything else -- wrappers, pills, panels -- carries a class).
        row = _heat_box(page).locator(
            "xpath=.//div[contains(@class,'heat-details')]//div[not(@class)]"
        ).first
        row.click()
        assert not _card_expanded(page)

    def test_blank_card_click_never_opens_couples_list(self, page, spa_server):
        """Only the couples pill opens the list -- clicking the card's blank
        header area does nothing when nothing is open."""
        _setup(page, spa_server)
        _heat_box(page).click(position={"x": 5, "y": 5})
        assert not _card_expanded(page)

    def test_click_pill_does_not_close_card_but_opens_panel_and_closes_couples(self, page, spa_server):
        """Opening a judges panel while the couples list is open closes the
        list and opens the panel -- exactly one expansion stays active."""
        _setup(page, spa_server)
        _open_couples(page)
        assert _card_expanded(page)

        _pills(page).first.click()
        assert _panel_expanded(page, 0)
        assert not _card_expanded(page), "opening a judges panel should close the couples list"

    def test_couples_pill_closes_open_judges_panel(self, page, spa_server):
        """Opening the couples list while a judges panel is open closes the panel."""
        _setup(page, spa_server)
        _pills(page).first.click()
        assert _panel_expanded(page, 0)

        _open_couples(page)
        assert _card_expanded(page)
        assert not _panel_expanded(page, 0), "opening the couples list should close the judges panel"

    def test_second_pill_click_closes_first_opens_second(self, page, spa_server):
        """Accordion: opening one pill's panel closes any other open panel in
        the same card."""
        _setup(page, spa_server)

        _pills(page).first.click()
        assert _panel_expanded(page, 0)

        _pills(page).nth(1).click()
        assert _panel_expanded(page, 1)
        assert not _panel_expanded(page, 0), "opening the second pill should close the first"

    def test_click_inside_open_panel_closes_it(self, page, spa_server):
        """Clicking inside an open judges panel (not on a pill) closes it."""
        _setup(page, spa_server)
        _pills(page).first.click()
        assert _panel_expanded(page, 0)

        panel = _heat_box(page).locator("[data-role='judges-panel'].expanded").first
        panel.click()
        assert not _panel_expanded(page, 0)
        assert not _card_expanded(page)
