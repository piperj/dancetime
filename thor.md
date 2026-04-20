# Engineer's Notebook — dancetime

---

## 2026-04-20 — SPA UI overhaul: porting the competitor schedule view from dancetime.master

### What we set out to do

Replace the original SPA's simple heat-card list with the richer, competitor-centric schedule UI from `dancetime.master` — while keeping the SPA architecture (static files, `fetch`-based data loading, multi-competition support).

### Competition_ID ≠ Comp_Year_ID

The NDCA API has two separate IDs. The `Comp_Year_ID` (CYI, e.g. 373) identifies a specific running of a competition in a given year. The `Competition_ID` (e.g. 11) identifies the recurring competition itself across all years. The logo URL pattern is `https://ndca.org/images/comp_logos/{Competition_ID}.jpg` — using CYI gives a 404. The fix was to add `competition_id` to the `heats/{writer.py}` `meta` block and use it in the SPA.

### `display:none` + `onload` is a trap

The pattern `<img style="display:none" onload="this.style.display='block'">` sounds clean but breaks under Tailwind CDN and browser caching interactions — the `onload` fires at different times relative to DOM visibility depending on whether the image was cached. The fix: drop `style="display:none"` entirely. Let the browser render the `<img>` naturally and only use `onerror` to set `visibility:hidden` if the URL fails. Fewer moving parts, always works.

### Data shape adaptation (master template → SPA)

The master template is Flask server-rendered: all data is pre-aggregated into `scheduleData` (competitor_heats, heat_times, competitor_contested_stats, etc.). The SPA loads `heats_{cyi}.json` which has: `heats[]`, `competitor_heats{}` (competitor → heat key list), `competitor_studios{}`. No precomputed contested stats.

Key adaptations:
- Build `heatsByKey` lookup from `heats[]` at load time.
- Partner = the other `competitor1`/`competitor2` in the same entry.
- Contested = other entries in the same heat with the same `event`.
- `competitor_contested_stats` is derived client-side by iterating `competitor_heats` keys.
- Studio → competitor mapping: invert `competitor_studios` into `studioCompetitors` at load time.

### Removed the top bar in favour of a clickable comp name

The `<header>` with app title and `<select>` was removed. The competition name in the header now shows a `▾` chevron and expands an inline dropdown listing all competitions. Clicking outside closes it. The active competition is highlighted. Cleaner on mobile.

---

## 2026-04-19 — Full rebuild from scratch: lessons from the NDCA API and a true incremental ELO

### What we set out to do

Rebuild `dancetime` on a clean `main` branch — no code copied from `dancetime.master`. The goal: a GitHub Pages site that automatically updates competition data via GitHub Actions, shows heat schedules, and ranks ballroom couples by an all-time cumulative ELO that ticks forward with every completed heat.

### The NDCA API is weirder than it looks

The old implementation gave us a rough map, but hitting the endpoints live revealed a few surprises:

**`/feed/compyears/` uses `"Events"`, not `"Result"`**. Every other endpoint returns `{"Status":1,"Result":{...}}`. The competition-years endpoint uses `{"Status":1,"Events":[...]}`. If you blindly fall through to `data.get("Result")` you get `None` every time and never know why.

**Heatlists and results use different ID formats**. Results use letter-prefix IDs (`A155`). Heatlists use plain numeric IDs (`155`). They refer to the same competitor. The fetcher has to maintain two separate lists and track which format each endpoint expects.

**The heatlist structure is deeply nested, not flat**. We assumed `{"Entries":[{"SessionID":2,"HeatNumber":"42",...}]}`. The real shape is `Entries → Events → Rounds` where `Round.Session` is a zero-padded string (`"02"`) and `Round.Round_Time` is `"1/23/2026 12:10:42 PM"`. This required a complete rewrite of both `heats/session_names.py` and `heats/parser.py` once we saw real data.

**Lesson**: Before building any parser, probe the API and compare a real response against your assumptions. The fixture shape and the production shape must match. We fixed `tests/fixtures/comp_test.zip` to reflect the real structure so tests stay honest.

### True incremental ELO: order is everything

The design question was: should ELO be a batch end-of-comp calculation, or should it update with every completed heat? We chose the latter — a "true" incremental ELO. This means:

- `DanceResult` has a `sort_key = (session_id, heat_number, time)`.
- `parse_results()` returns results already sorted by `sort_key`.
- `EloCalculator.process_heat()` updates ratings in-place, one heat at a time.
- The leaderboard at any point in time is the exact ELO state after the last known result.

The practical consequence: early heats in a session set the ELO baseline; later heats nudge it. If you process out of order, the deltas cancel out wrong. The sort is the contract.

No Monte Carlo. No batching. Sequential, deterministic.

### All-time ELO across competitions

`data/elo_ratings.json` is the ledger. For a new competition, `get_initial_ratings()` seeds known competitors from their prior ELO and assigns skill/age offsets only to newcomers. After a competition is marked complete in `calendar.json`, `save_ratings()` merges the final ratings back into the ledger. The `elo_delta` shown in the UI is `final − prior` — the net change from this competition.

### Deployment pattern (same as tanzpalast)

GitHub Pages from `main` root. `data/*.json` files are committed — the Actions bot runs the pipeline and pushes back. `data/raw/` is git-ignored (scraper cache). The SPA at `index.html` uses relative `fetch("data/index.json")` which works identically in local dev and on Pages.

Adaptive polling: `*/15 * * * *` cron (GitHub's minimum), but the pipeline scripts call `schedule/runner.py:should_run()` first. That function returns `False` if no competition is active and last update was < 23h ago, so we don't burn API quota for nothing.

### What shipped

- 45 files, 95 tests, all passing.
- City Lights Open (cyi=373): 805 heats, 409 competitors, 15 ELO leaderboards committed.
- Static SPA with heats tab (search + session filter) and rankings tab (ELO, Δ, heats processed).
- Full pipeline: `scrape → heats → ranking → publish` each as a standalone subcommand.
