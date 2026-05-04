"""
Suite A — locks current Heats and Ladder tab behaviour.

Data is discovered from window.__spa (populated by the SPA after load) and
falls back to known-good values provided by the user.
"""
import pytest
from .conftest import wait_for_spa

pytest.importorskip("playwright.sync_api", reason="playwright not installed")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _click_tab(page, tab):
    page.click(f"nav button[data-tab='{tab}']")
    page.wait_for_timeout(400)


def _type_search(page, input_id, text):
    inp = page.locator(f"#{input_id}")
    inp.fill(text)
    inp.dispatch_event("input")
    page.wait_for_timeout(500)


def _clear_search(page, input_id):
    _type_search(page, input_id, "")


def _spa_data(page):
    return page.evaluate("""() => ({
        competitors:  Array.from(window.__spa?.heatsData?.competitors  ?? []),
        studios:      Array.from(window.__spa?.heatsData?.studios      ?? []),
        bibKeys:      Object.keys(window.__spa?.bibHeats    ?? {}),
        bibToNames:   Object.keys(window.__spa?.bibToNames  ?? {}),
        allNames:     Array.from(window.__spa?.allCompetitorNames      ?? []),
        compNames:    Array.from(window.__spa?.heatsData?.competitors  ?? []),
    })""")


def _ranking_row_names(page):
    """Return text from the 'Couple' column (2nd td) of all visible ranking rows."""
    return page.evaluate("""() =>
        Array.from(document.querySelectorAll('#ranking-view .lb-table tbody tr td:nth-child(2)'))
             .map(td => td.textContent.trim())
    """)


# ---------------------------------------------------------------------------
# Heats tab
# ---------------------------------------------------------------------------

class TestHeatsTab:
    def test_competitor_search_shows_heats(self, page, spa_server):
        """Typing a known competitor name renders at least one blue session header."""
        wait_for_spa(page, spa_server)
        data = _spa_data(page)
        name = next((n for n in data["competitors"] if n), None) or "Johan Piper"

        _type_search(page, "competitorSearch", name)

        headers = page.locator("#scheduleContent .blue-box")
        assert headers.count() >= 1, f"expected session headers for '{name}'"

    def test_competitor_search_shows_heat_details(self, page, spa_server):
        """Heat cards contain heat number, time separator '·', and break markers."""
        wait_for_spa(page, spa_server)
        data = _spa_data(page)
        name = next((n for n in data["competitors"] if n), None) or "Johan Piper"

        _type_search(page, "competitorSearch", name)

        content = page.locator("#scheduleContent").inner_text()
        # Heat rows look like: "986 · 11:00 am 4 couples\n..."
        assert "·" in content, "expected heat rows with '·' time separator"
        # Break markers
        assert "break" in content.lower(), "expected break time markers in schedule"

    def test_heat_card_expandable(self, page, spa_server):
        """Clicking a heat card toggles the detail drop-down (expanded class)."""
        wait_for_spa(page, spa_server)
        data = _spa_data(page)
        name = next((n for n in data["competitors"] if n), None) or "Johan Piper"

        _type_search(page, "competitorSearch", name)

        # Heat cards are .heat-box divs; clicking toggles the adjacent .heat-details.expanded
        heat_boxes = page.locator("#scheduleContent .heat-box")
        assert heat_boxes.count() >= 1, "expected at least one .heat-box"
        heat_boxes.first.click()
        page.wait_for_timeout(300)
        details = page.locator("#scheduleContent .heat-details.expanded")
        assert details.count() >= 1, "expected at least one expanded heat-details after click"

    def test_session_header_shows_partner_names(self, page, spa_server):
        """The blue session header lists partner/member names."""
        wait_for_spa(page, spa_server)
        data = _spa_data(page)
        name = next((n for n in data["competitors"] if n), None) or "Johan Piper"

        _type_search(page, "competitorSearch", name)

        first_header = page.locator("#scheduleContent .blue-box").first
        header_text = first_header.inner_text()
        # Should show a time range or session name, and partner names below
        assert any(c.isalpha() for c in header_text), (
            f"blue-box header appears empty or garbled: '{header_text}'"
        )

    def test_studio_search_shows_session_groups(self, page, spa_server):
        """Typing a studio name renders session group(s)."""
        wait_for_spa(page, spa_server)
        data = _spa_data(page)
        studio = next((s for s in data["studios"] if s), None) or "Arete Dance Center"

        _type_search(page, "competitorSearch", studio)

        headers = page.locator("#scheduleContent .blue-box")
        assert headers.count() >= 1, f"expected session groups for studio '{studio}'"

    def test_bib_search_shows_heats(self, page, spa_server):
        """Typing a pure-digit bib renders heat cards."""
        wait_for_spa(page, spa_server)
        data = _spa_data(page)
        bib = next((b for b in data["bibKeys"] if b), None) or "657"

        _type_search(page, "competitorSearch", bib)

        headers = page.locator("#scheduleContent .blue-box")
        assert headers.count() >= 1, f"expected heats for bib '{bib}'"

    def test_empty_search_shows_all_heats(self, page, spa_server):
        """Clearing the search input shows all-heats view (not the 'select a competitor' placeholder)."""
        wait_for_spa(page, spa_server)
        _clear_search(page, "competitorSearch")
        page.wait_for_timeout(300)

        content = page.locator("#scheduleContent")
        text = content.inner_text()
        assert "select a competitor" not in text.lower(), (
            "empty state shows placeholder instead of all-heats view"
        )
        boxes = page.locator("#scheduleContent .blue-box")
        assert boxes.count() >= 1, "expected session groups in all-heats view"

    def test_not_competing_shows_message(self, page, spa_server):
        """A name not in the current comp but known to the SPA shows a not-competing message."""
        wait_for_spa(page, spa_server)
        data = _spa_data(page)
        comp_set = set(data["compNames"])
        name = next((n for n in data["allNames"] if n not in comp_set), None)
        if not name:
            pytest.skip("no cross-comp competitors available in test data")

        _type_search(page, "competitorSearch", name)
        content = page.locator("#scheduleContent").inner_text()
        assert "not competing" in content.lower(), (
            f"expected 'not competing' message for '{name}', got: {content[:200]}"
        )


# ---------------------------------------------------------------------------
# Ladder tab
# ---------------------------------------------------------------------------

class TestLadderTab:
    def test_competitor_search_filters_rows(self, page, spa_server):
        """Typing a known ranking competitor in Ladder filters leaderboard rows."""
        wait_for_spa(page, spa_server)
        _click_tab(page, "ranking")
        page.wait_for_timeout(400)

        # Pick a name directly from a visible row — guaranteed to be in ranking data.
        row_names = _ranking_row_names(page)
        name = None
        if row_names:
            # Couple cell shows "Alexander Novikov & Laura Sirott" — grab just the first name
            name = row_names[0].split(" & ")[0].strip()
        if not name:
            name = "Alexander Novikov"

        _type_search(page, "search-ranking", name)
        filtered = _ranking_row_names(page)
        assert len(filtered) >= 1, f"expected at least one row for '{name}'"
        assert any(name.split()[0].lower() in r.lower() for r in filtered), (
            f"name '{name}' not in any filtered row: {filtered[:3]}"
        )

    def test_bib_search_filters_rows(self, page, spa_server):
        """Typing a bib in Ladder filters to that competitor via bibToNames."""
        wait_for_spa(page, spa_server)
        data = _spa_data(page)
        if not data["bibToNames"]:
            pytest.skip("bibToNames not available (pre-2e3cb26 SPA)")

        # Get all names visible in the unfiltered ladder.
        _click_tab(page, "ranking")
        page.wait_for_timeout(400)
        row_names = _ranking_row_names(page)
        all_row_names = {r.split(" & ")[0].strip() for r in row_names}
        all_row_names |= {r.split(" & ")[1].strip() for r in row_names if " & " in r}

        bib = next(
            (b for b in data["bibToNames"]
             if any(n in all_row_names for n in
                    page.evaluate(f"() => Array.from(window.__spa?.bibToNames?.['{b}'] ?? [])"))),
            None,
        )
        if not bib:
            pytest.skip("no bib found whose names appear in ranking leaderboards")

        _type_search(page, "search-ranking", bib)
        filtered = _ranking_row_names(page)
        assert len(filtered) >= 1, f"expected leaderboard rows for bib '{bib}'"

    def test_not_competing_shows_message(self, page, spa_server):
        """A name not in the current comp shows a not-competing message in Ladder."""
        wait_for_spa(page, spa_server)
        data = _spa_data(page)
        comp_set = set(data["compNames"])
        name = next((n for n in data["allNames"] if n not in comp_set), None)
        if not name:
            pytest.skip("no cross-comp competitors available")

        _click_tab(page, "ranking")
        _type_search(page, "search-ranking", name)
        content = page.locator("#ranking-view").inner_text()
        assert "not competing" in content.lower(), (
            f"expected 'not competing' in Ladder for '{name}', got: {content[:200]}"
        )

    def test_url_competitor_param_persists_across_tabs(self, page, spa_server):
        """?competitor=Name populates both Heats and Ladder search inputs."""
        wait_for_spa(page, spa_server)
        data = _spa_data(page)
        name = next((n for n in data["competitors"] if n), None) or "Johan Piper"

        page.goto(f"{spa_server}/index.html?competitor={name.replace(' ', '%20')}")
        page.wait_for_function(
            """() => {
                const s = document.getElementById('status');
                return s.classList.contains('hidden') || !s.textContent.includes('Loading');
            }""",
            timeout=15_000,
        )
        page.wait_for_timeout(500)

        heats_val = page.locator("#competitorSearch").input_value()
        assert name in heats_val, f"Heats input expected '{name}', got '{heats_val}'"

        _click_tab(page, "ranking")
        ladder_val = page.locator("#search-ranking").input_value()
        assert name in ladder_val, f"Ladder input expected '{name}', got '{ladder_val}'"
