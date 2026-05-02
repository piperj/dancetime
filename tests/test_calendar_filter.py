"""
Spec for the calendar search filter (mirrors the JS in cal/static/calendar.html).

Rules:
  - query is exactly 2 uppercase ASCII letters (e.g. "CA", "NJ"):
      exact token match against name and location tokens (handles state codes)
  - otherwise: normal substring search on name and location
  - empty query matches everything
"""

import re


def _tokens(text: str) -> list[str]:
    return [t for t in re.split(r"[\s,]+", text.lower()) if t]


def comp_matches(name: str, location: str, query: str) -> bool:
    if not query.strip():
        return True
    if re.fullmatch(r"[A-Z]{2}", query):
        tokens = _tokens(name) + _tokens(location)
        return query.lower() in tokens
    q = query.lower()
    return q in name.lower() or q in (location or "").lower()


# ---------------------------------------------------------------------------
# State-code queries (exactly 2 uppercase letters) → exact token match
# ---------------------------------------------------------------------------

def test_ca_does_not_match_american():
    assert not comp_matches("American Star Ball Championships", "Atlantic City, NJ", "CA")

def test_ca_does_not_match_carte():
    assert not comp_matches("Dancing a la Carte", "Springfield, MA", "CA")

def test_ca_matches_irvine_ca():
    assert comp_matches("City Lights Open", "Irvine, CA", "CA")

def test_ma_matches_springfield_ma():
    assert comp_matches("Dancing a la Carte", "Springfield, MA", "MA")

def test_nj_matches_atlantic_city_nj():
    assert comp_matches("American Star Ball Championships", "Atlantic City, NJ", "NJ")

def test_tx_does_not_match_extra():
    assert not comp_matches("Texas Extra Championships", "Dallas, OK", "TX")

def test_tx_matches_dallas_tx():
    assert comp_matches("Some Open", "Dallas, TX", "TX")


# ---------------------------------------------------------------------------
# Lowercase / long queries → normal substring search
# ---------------------------------------------------------------------------

def test_lowercase_ca_matches_substring_in_name():
    # "ca" lowercase → normal search → matches "American" mid-word
    assert comp_matches("American Star Ball Championships", "Atlanta, GA", "ca")

def test_star_matches_name():
    assert comp_matches("American Star Ball Championships", "Atlanta, GA", "star")

def test_irvine_matches_location():
    assert comp_matches("City Lights Open", "Irvine, CA", "irvine")

def test_nash_matches_nashville():
    assert comp_matches("Some Open", "Nashville, TN", "nash")

def test_ameri_matches_name():
    assert comp_matches("American Star Ball Championships", "Atlanta, GA", "ameri")

def test_all_matches_ball_as_substring():
    # normal search → "all" is a substring of "ball"
    assert comp_matches("Ball Room Classic", "Denver, CO", "all")


# ---------------------------------------------------------------------------
# Mixed-case or non-2-letter queries are NOT treated as state codes
# ---------------------------------------------------------------------------

def test_mixed_case_ca_is_normal_search():
    # "Ca" is not 2 uppercase → normal substring → matches "Carte"
    assert comp_matches("Dancing a la Carte", "Springfield, MA", "Ca")

def test_single_letter_is_normal_search():
    assert comp_matches("California Open", "Los Angeles, CA", "C")


# ---------------------------------------------------------------------------
# Empty query matches everything
# ---------------------------------------------------------------------------

def test_empty_query_matches_anything():
    assert comp_matches("Whatever", "Somewhere, XX", "")
    assert comp_matches("Whatever", "Somewhere, XX", "  ")
