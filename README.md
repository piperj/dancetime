# Dancetime

A data pipeline and interactive web app for competitive ballroom dance rankings. Fetches results from the NDCA API, computes ELO ratings across competitions, and publishes a single-page app for exploring heat schedules and leaderboards.

Live site: https://piperj.github.io/dancetime/

## Features

- **ELO ranking** — ratings accumulate across competitions; partner strength is blended in
- **Heat browser** — view heat cards by session, with placements and contested-couple badges
- **Competitor view** — select any dancer to see their full schedule and head-to-head stats
- **Leaderboard** — ranked clusters of competitors who have shared heats, with win percentages
- **Pipeline CLI** — scrape, process, and publish with four commands

## Installation

Requires Python 3.11+ and [uv](https://github.com/astral-sh/uv).

```bash
git clone https://github.com/piperj/dancetime.git
cd dancetime
uv sync
```

## Usage

Run the full pipeline for a competition using its NDCA Competition Year ID (CYI):

```bash
uv run python dancetime_cli.py scrape --cyi <CYI>
uv run python dancetime_cli.py heats --cyi <CYI>
uv run python dancetime_cli.py ranking --cyi <CYI>
uv run python dancetime_cli.py publish
```

`publish` writes `index.html` and `data/index.json` for GitHub Pages. Check the active competition schedule with:

```bash
uv run python dancetime_cli.py schedule
```

## Development and Testing

```bash
# Install dev dependencies
uv sync

# Run all tests with coverage
uv run pytest tests/ -v --cov --cov-report=term-missing

# Run a single test file
uv run pytest tests/test_ranking.py -v
```

Raw competition data is cached in `data/raw/comp_{cyi}.zip`. ELO state persists across competitions in `data/elo_ratings.json`.
