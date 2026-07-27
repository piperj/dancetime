"""
Suite A — locks current Heats and Ladder tab behaviour.

Data is discovered from window.__spa (populated by the SPA after load) and
falls back to known-good values provided by the user.
"""
import pytest
from .conftest import ensure_ranking_tab_visible, wait_for_spa

pytest.importorskip("playwright.sync_api", reason="playwright not installed")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _click_tab(page, tab):
    page.click(f"nav button[data-tab='{tab}']")
    page.wait_for_function(
        "(tab) => document.querySelector(`nav button[data-tab='${tab}']`).classList.contains('active')",
        arg=tab,
    )


def _type_search(page, input_id, text):
    """Fill the search box and fire its 'input' handler.

    No trailing sleep needed: both #competitorSearch and #search-ranking
    handlers (selectHeatsCompetitor/renderRanking) run synchronously and
    dispatch_event() doesn't return until they've finished, so the DOM is
    already updated by the time this call returns.
    """
    inp = page.locator(f"#{input_id}")
    inp.fill(text)
    inp.dispatch_event("input")
    # Both inputs are native <input list=datalist>; WebKit can leave the
    # autocomplete popup open over the content below and silently swallow
    # the next click there (see test_judges_scores.py's _search_competitor
    # for the confirmed repro). Blur before any click below the search box.
    inp.press("Escape")


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


def _ranking_rows(page, *, wins=False):
    """Return the 'Couple' column (2nd td) of all visible ranking rows.

    With wins=True, return {couple, wins} dicts instead (6th td is Wins%).
    """
    if wins:
        return page.evaluate("""() =>
            Array.from(document.querySelectorAll('#ranking-view .lb-table tbody tr')).map(tr => {
                const tds = tr.querySelectorAll('td');
                return { couple: tds[1].textContent.trim(), wins: tds[5].textContent.trim() };
            })
        """)
    return page.evaluate("""() =>
        Array.from(document.querySelectorAll('#ranking-view .lb-table tbody tr td:nth-child(2)'))
             .map(td => td.textContent.trim())
    """)


def _ranking_row_names(page):
    return _ranking_rows(page)


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
        # Pick the competitor with the most heats: a break marker only appears when
        # floor heats are skipped between two of their heats, so a competitor with
        # one heat per session (or heats on different days) legitimately has none.
        name = page.evaluate("""() => {
            const ch = window.__spa?.heatsData?.competitor_heats ?? {};
            let best = null, n = -1;
            for (const [k, v] of Object.entries(ch)) if (v.length > n) { n = v.length; best = k; }
            return best;
        }""") or "Johan Piper"

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
# Heat-round grouping (solo numbering collisions)
# ---------------------------------------------------------------------------

class TestSplitHeatRounds:
    """splitHeatRounds() must not merge a solo that reuses a regular heat number.

    Solos are numbered independently, so (heat_number, session) can collide with
    an unrelated heat later in the day. Real rounds of one physical heat carry
    distinct round names, so a repeated round name marks a separate heat.
    Regression for Manhattan Dance (cyi 904) heat 23: an 8-couple 8:29am final
    was rendered as "Solo on floor" because a 3:48pm solo shared its number.
    """

    def _split(self, page, sorted_heats, anchor_key):
        return page.evaluate(
            "([s, k]) => window.__spa.splitHeatRounds(s, k)",
            [sorted_heats, anchor_key],
        )

    def test_solo_collision_is_excluded(self, page, spa_server):
        wait_for_spa(page, spa_server)
        real = {"key": "01_23_am", "heat_number": "23", "session": "01",
                "round": "Final", "time": "2026-07-01T08:29:42"}
        solo = {"key": "01_23_pm", "heat_number": "23", "session": "01",
                "round": "Final", "time": "2026-07-01T15:48:00"}
        rounds = self._split(page, [real, solo], real["key"])
        keys = [h["key"] for h in rounds]
        assert keys == ["01_23_am"], f"solo should be excluded, got {keys}"

    def test_genuine_rounds_are_kept_together(self, page, spa_server):
        wait_for_spa(page, spa_server)
        semi = {"key": "09_1297_semi", "heat_number": "1297", "session": "09",
                "round": "Semi-Final", "time": "2026-07-03T11:25:00"}
        final = {"key": "09_1297_final", "heat_number": "1297", "session": "09",
                 "round": "Final", "time": "2026-07-03T11:31:00"}
        rounds = self._split(page, [semi, final], semi["key"])
        keys = [h["key"] for h in rounds]
        assert keys == ["09_1297_semi", "09_1297_final"], (
            f"distinct-named rounds must stay grouped, got {keys}"
        )


# ---------------------------------------------------------------------------
# Physical-heat partitioning (one card per real heat)
# ---------------------------------------------------------------------------

class TestPartitionRounds:
    """partitionRounds() splits a (heat_number, session) bucket into physical
    heats on a repeated round name."""

    def _partition(self, page, rounds):
        return page.evaluate(
            "(r) => window.__spa.partitionRounds(r).map(p => p.map(h => h.key))", rounds
        )

    def test_repeated_round_name_splits(self, page, spa_server):
        wait_for_spa(page, spa_server)
        a = {"key": "a", "round": "Final", "time": "2026-07-01T08:00:00"}
        b = {"key": "b", "round": "Final", "time": "2026-07-01T14:00:00"}
        assert self._partition(page, [a, b]) == [["a"], ["b"]]

    def test_distinct_rounds_stay_one_heat(self, page, spa_server):
        wait_for_spa(page, spa_server)
        q = {"key": "q", "round": "Quarter-Final", "time": "2026-07-01T08:00:00"}
        s = {"key": "s", "round": "Semi-Final", "time": "2026-07-01T08:20:00"}
        f = {"key": "f", "round": "Final", "time": "2026-07-01T08:40:00"}
        assert self._partition(page, [q, s, f]) == [["q", "s", "f"]]


class TestDedupePhysicalHeats:
    """dedupePhysicalHeats() yields one anchor per physical heat, so a solo that
    reuses a regular heat number is not deduped away."""

    def _dedupe(self, page, heats):
        return page.evaluate(
            "(h) => window.__spa.dedupePhysicalHeats(h).map(x => x.key)", heats
        )

    def test_solo_collision_yields_two_cards(self, page, spa_server):
        wait_for_spa(page, spa_server)
        regular = {"key": "reg", "heat_number": "1", "session": "01",
                   "round": "Final", "time": "2026-07-01T08:00:00"}
        solo = {"key": "solo", "heat_number": "1", "session": "01",
                "round": "Final", "time": "2026-07-01T14:01:00"}
        keys = self._dedupe(page, [solo, regular])
        assert keys == ["reg", "solo"], f"both physical heats expected, got {keys}"

    def test_multiround_heat_yields_one_card(self, page, spa_server):
        wait_for_spa(page, spa_server)
        q = {"key": "q", "heat_number": "1", "session": "04",
             "round": "Quarter-Final", "time": "2026-07-02T20:30:00"}
        s = {"key": "s", "heat_number": "1", "session": "04",
             "round": "Semi-Final", "time": "2026-07-02T21:12:00"}
        f = {"key": "f", "heat_number": "1", "session": "04",
             "round": "Final", "time": "2026-07-02T21:46:00"}
        keys = self._dedupe(page, [q, s, f])
        assert keys == ["q"], f"multi-round heat should collapse to one anchor, got {keys}"

    def test_formation_collision_yields_two_cards(self, page, spa_server):
        """A formation reusing a regular heat number is its own card.

        cyi 1030 heat 9 / session 03: 'Solo Rumba Formation' shares (9, 03) with
        a 'Pro Cabaret-Theater Arts' final. Both are Finals, so the repeated round
        name splits them — no dependence on the event name.
        """
        wait_for_spa(page, spa_server)
        cabaret = {"key": "cab", "heat_number": "9", "session": "03",
                   "round": "Final", "time": "2025-11-28T20:10:00"}
        formation = {"key": "form", "heat_number": "9", "session": "03",
                     "round": "Final", "time": "2025-11-28T22:40:00"}
        keys = self._dedupe(page, [cabaret, formation])
        assert keys == ["cab", "form"], f"formation must not be deduped away, got {keys}"

    def test_keywordless_collision_yields_two_cards(self, page, spa_server):
        """Two ordinary heats reusing a number split with no keyword to classify on.

        cyi 1030 heats 2 & 3 / session 01: a social 'Pre Silver' final and a
        'Professional Rising Star' final share the number hours apart. This is why
        grouping keys on round-partition, not event-name classification.
        """
        wait_for_spa(page, spa_server)
        social = {"key": "soc", "heat_number": "2", "session": "01",
                  "round": "Final", "time": "2025-11-28T18:01:15"}
        pro = {"key": "pro", "heat_number": "2", "session": "01",
               "round": "Final", "time": "2025-11-28T21:38:03"}
        keys = self._dedupe(page, [social, pro])
        assert keys == ["soc", "pro"], f"keyword-less collision must split, got {keys}"


class TestCollectUniqueHeats:
    """collectUniqueHeats() must collapse a key that appears more than once.

    Regression: the studio view flatMaps every member's heat keys, so two
    studio-mates in the same heat feed the identical key twice. Without a
    key-level dedup, partitionRounds splits the repeated round name into two
    partitions and the heat renders (and is counted) twice.
    """

    def test_duplicate_key_yields_one_heat(self, page, spa_server):
        wait_for_spa(page, spa_server)
        key = page.evaluate("() => window.__spa.heatsData?.heats?.[0]?.key ?? null")
        assert key, "no heats loaded to exercise collectUniqueHeats"
        n = page.evaluate("(k) => window.__spa.collectUniqueHeats([k, k, k]).length", key)
        assert n == 1, f"a repeated key must collapse to one heat, got {n}"


class TestRestMinutes:
    """restMinutes() = clock gap minus the assumed heat length (90s)."""

    def _rest(self, page, a, b):
        return page.evaluate("([a, b]) => window.__spa.restMinutes(a, b)", [a, b])

    def test_subtracts_heat_length(self, page, spa_server):
        wait_for_spa(page, spa_server)
        rest = self._rest(page, "2026-07-01T14:00:00", "2026-07-01T14:10:00")
        assert rest == pytest.approx(8.5), f"expected 8.5 min, got {rest}"

    def test_back_to_back_is_near_zero(self, page, spa_server):
        wait_for_spa(page, spa_server)
        rest = self._rest(page, "2026-07-01T14:00:00", "2026-07-01T14:01:30")
        assert rest == pytest.approx(0.0), f"expected 0 min, got {rest}"


class TestHeatsSkipped:
    """heatsSkipped() reports a break when floor heats ran between two heats,
    using the global floor-position index built from the loaded competition."""

    def _positions(self, page):
        return page.evaluate("() => ({...window.__spa.floorPositionByKey})")

    def test_positions_built(self, page, spa_server):
        wait_for_spa(page, spa_server)
        assert len(self._positions(page)) > 0, "floor positions not built on load"

    def test_adjacent_no_skip_gap_skips(self, page, spa_server):
        wait_for_spa(page, spa_server)
        pos = self._positions(page)
        # key at each floor index, so we can pick adjacent vs gapped pairs.
        by_index = {}
        for k, i in pos.items():
            by_index.setdefault(i, k)
        indices = sorted(by_index)
        # Find an adjacent pair (i, i+1) and a gapped pair (i, i+2).
        adj = next(((by_index[i], by_index[i + 1]) for i in indices if i + 1 in by_index), None)
        gap = next(((by_index[i], by_index[i + 2]) for i in indices if i + 2 in by_index), None)
        assert adj and gap, "need both an adjacent and a gapped pair in test data"

        def skipped(a, b):
            return page.evaluate("([a, b]) => window.__spa.heatsSkipped(a, b)", [a, b])

        assert skipped(*adj) is False, "adjacent floor heats must not be a break"
        assert skipped(*gap) is True, "a skipped floor heat must register as a break"

    def test_same_heat_is_not_a_skip(self, page, spa_server):
        wait_for_spa(page, spa_server)
        pos = self._positions(page)
        # Two round keys of the same physical heat share a floor index.
        from collections import Counter
        counts = Counter(pos.values())
        shared_index = next((i for i, c in counts.items() if c >= 2), None)
        if shared_index is None:
            pytest.skip("no multi-round heat in loaded data")
        keys = [k for k, i in pos.items() if i == shared_index][:2]
        skipped = page.evaluate("([a, b]) => window.__spa.heatsSkipped(a, b)", keys)
        assert skipped is False, "rounds of one heat must not register as a break"



# ---------------------------------------------------------------------------
# Ladder tab
# ---------------------------------------------------------------------------

class TestLadderTab:
    def test_competitor_search_filters_rows(self, page, spa_server):
        """Typing a known ranking competitor in Ladder filters leaderboard rows."""
        wait_for_spa(page, spa_server, query="?show_elo=1")
        ensure_ranking_tab_visible(page)
        _click_tab(page, "ranking")

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
        wait_for_spa(page, spa_server, query="?show_elo=1")
        ensure_ranking_tab_visible(page)
        data = _spa_data(page)
        if not data["bibToNames"]:
            pytest.skip("bibToNames not available (pre-2e3cb26 SPA)")

        # Get all names visible in the unfiltered ladder.
        _click_tab(page, "ranking")
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
        wait_for_spa(page, spa_server, query="?show_elo=1")
        ensure_ranking_tab_visible(page)
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

    def test_wins_percent_is_scoped_to_the_couple_not_the_person(self, page, spa_server):
        """A competitor with multiple partners in the same comp must show a
        distinct, partner-specific Wins% per couple row — not one partner's
        blended-across-all-their-partners average reused for every row they
        appear in (regression: Ladder rows were keyed by avgScores[c.competitor],
        which is a per-person average, not per-couple)."""
        wait_for_spa(page, spa_server, query="?show_elo=1")
        ensure_ranking_tab_visible(page)

        # Find a real competitor who danced with 2+ distinct partners in the
        # loaded competition, straight from heatsData — no synthetic fixture needed.
        # Compute each candidate's per-partner win rates in the same pass so this
        # needs exactly one browser round trip regardless of how many candidates
        # there are (rather than one evaluate() per candidate afterwards).
        candidates = page.evaluate("""() => {
            const heatsData = window.__spa.heatsData;
            const byKey = {};
            (heatsData.heats || []).forEach(h => byKey[h.key] = h);
            const results = [];
            for (const [name, keys] of Object.entries(heatsData.competitor_heats || {})) {
                const partners = new Set();
                for (const k of keys) {
                    const heat = byKey[k];
                    if (!heat) continue;
                    const e = heat.entries.find(e => e.competitor1 === name || e.competitor2 === name);
                    if (!e) continue;
                    const partner = e.competitor1 === name ? e.competitor2 : e.competitor1;
                    if (partner) partners.add(partner);
                }
                if (partners.size < 2) continue;
                const pairs = [...partners].map(p => {
                    const v = window.__spa.avgScoresByCouple[window.__spa.coupleKey(name, p)];
                    return [p, v == null ? null : Math.round(v * 100)];
                }).filter(([, v]) => v !== null);
                results.push({ name, pairs });
            }
            return results;
        }""")
        if not candidates:
            pytest.skip("no competitor with multiple partners in this competition's data")

        # Pick the first candidate with two partnerships whose win rates actually differ.
        name, partners, expected = None, None, None
        for cand in candidates:
            pairs = cand["pairs"]
            first = pairs[0] if pairs else None
            second = next((pv for pv in pairs if first and pv[1] != first[1]), None)
            if first and second:
                name = cand["name"]
                partners = [first[0], second[0]]
                expected = [first[1], second[1]]
                break
        if name is None:
            pytest.skip("no competitor found with 2+ partnerships that have distinct computable win rates")

        _click_tab(page, "ranking")
        _type_search(page, "search-ranking", name)

        rows = _ranking_rows(page, wins=True)

        for partner, want_pct in zip(partners, expected):
            row = next((r for r in rows if partner in r["couple"] and name in r["couple"]), None)
            assert row is not None, f"no rendered row found for {name} & {partner}: {rows}"
            assert row["wins"] == f"{want_pct}%", (
                f"{name} & {partner}: rendered Wins {row['wins']!r}, expected {want_pct}%"
            )

    def test_url_competitor_param_persists_across_tabs(self, page, spa_server):
        """?competitor=Name populates both Heats and Ladder search inputs."""
        wait_for_spa(page, spa_server, query="?show_elo=1")
        data = _spa_data(page)
        name = next((n for n in data["competitors"] if n), None) or "Johan Piper"

        page.goto(f"{spa_server}/index.html?competitor={name.replace(' ', '%20')}&show_elo=1")
        page.wait_for_function(
            """() => {
                const s = document.getElementById('status');
                return s.classList.contains('hidden') || !s.textContent.includes('Loading');
            }""",
            timeout=15_000,
        )

        heats_val = page.locator("#competitorSearch").input_value()
        assert name in heats_val, f"Heats input expected '{name}', got '{heats_val}'"

        ensure_ranking_tab_visible(page)
        _click_tab(page, "ranking")
        ladder_val = page.locator("#search-ranking").input_value()
        assert name in ladder_val, f"Ladder input expected '{name}', got '{ladder_val}'"
