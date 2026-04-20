# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## TODOs

- **Push to GitHub**: Create remote repo, push `main`, configure GitHub Pages (Settings → Pages → Deploy from `main` root). Add any required secrets (e.g. competition CYI) to Actions.

- **Interactive YAML/calendar command**: Add a `calendar` subcommand to `dancetime_cli.py` — an interactive CLI tool to view and edit the competition schedule (add/remove competitions, mark as complete, set active CYI). Likely reads/writes `data/calendar.json`.

- **De-duplicate data**: In the ranking the couples appear twice, as {'a', 'b,} and {'b', 'a'} combine into a single couple, maybe by using set().

- **Fantasy match-up tab**: Add a third tab to the SPA. User picks two competitors and sees a head-to-head breakdown: shared heats, placement comparison heat-by-heat, win/loss/tie record, ELO trajectory. Data is already in `heats_{cyi}.json` (`top_matchups` + `competitor_heats`).

- **Improve UI**: General polish pass — mobile layout, loading states, better typography, heat card design, leaderboard colour coding by ELO band, session timeline view.

- **Smart scraping**: `scrape` should detect whether new results have been posted since last download (e.g. compare `total_competitors` or a checksum) before re-downloading the full dataset, even without `--force`. Saves API quota and speeds up the pipeline on stale days.

- **ELO weighting**: Use a non-linear weighting between the partners, for example c=1/(1/a+1/b), w_a=c/a, w_b=c/b, or the ELO equation itself

- **Real unit tests**: The ranking is fiddly. Write unit tests for specific heats and persons where we already know the results.

## Commands

All commands use `uv`. Install deps: `uv sync`

```bash
# Run the full pipeline for a competition
uv run python dancetime_cli.py scrape --cyi <CYI>
uv run python dancetime_cli.py heats --cyi <CYI>
uv run python dancetime_cli.py ranking --cyi <CYI>
uv run python dancetime_cli.py publish

# Tests
uv run pytest tests/ -v --cov --cov-report=term-missing

# Single test file
uv run pytest tests/test_ranking.py -v

# Check active competition schedule
uv run python dancetime_cli.py schedule
```

## Architecture

### Pipeline overview

`dancetime_cli.py` is the single entrypoint — it dispatches to five subcommand modules (`scrape`, `heats`, `ranking`, `publish`, `schedule`), each a Python package with a `run(args)` function.

```
NDCA API → scrape → data/raw/comp_{cyi}.zip
                  → data/calendar.json
         zip → heats   → data/heats_{cyi}.json
         zip → ranking → data/ranking_{cyi}.json
                       → data/elo_ratings.json   (persisted ELO state across comps)
heats + ranking → publish → data/index.json
                          → index.html  (copied from static/index.html)
```

### Data flow and key files

- **`data/raw/comp_{cyi}.zip`** — raw NDCA API responses; contains `competition_info.json`, `results.json`, `heatlists.json`. All downstream stages read from this zip via `scrape.zip_store.load_json`.
- **`data/elo_ratings.json`** — ELO ratings persisted across competitions. The `ranking` module loads prior ratings, runs ELO, then writes updated ratings back. This is what makes ELO accumulate over time.
- **`data/index.json`** — manifest of all competitions; the SPA loads this first to discover available `heats_*.json` / `ranking_*.json` files.
- **`static/index.html`** — the SPA source; `publish` copies it to repo root `index.html` for GitHub Pages.

### ELO ranking

`ranking/elo.py` — `EloCalculator` processes heats pairwise. Each competitor pair in a final produces a standard Elo update (K=32, default). Partner rating is blended in with `partner_weight=0.3`: effective rating = 0.7 × own + 0.3 × partner. Deltas are averaged across all pairs to avoid inflating results in large fields.

`ranking/clusters.py` — competitors are grouped into leaderboard "clusters" via a graph of who competed against whom (using networkx). Competitors who never shared a heat get separate leaderboards.

### Schedule / automation

`schedule/runner.py` — controls when the pipeline actually runs (rate-limiting; avoids redundant runs between competitions). GitHub Actions (`update.yml`) runs every 15 minutes, but `should_run()` gates actual execution. `schedule/active.py` + `schedule/calendar.py` determine the active CYI from the calendar.

### Testing

Fixtures in `tests/conftest.py` provide a `sample_zip` (in-memory zip with realistic NDCA-shaped JSON) and raw data dicts. Most unit tests import parsers/writers directly and pass fixture data; integration tests (`test_integration.py`) exercise the full CLI via `subprocess`.
