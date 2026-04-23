"""
ELO progression plotter.

Usage:
    uv run python plot_elo.py "Kristina Kuvshynov"
    uv run python plot_elo.py "Alice Smith" "Bob Jones"
    uv run python plot_elo.py "Alice Smith & Bob Jones"        # couple filter
    uv run python plot_elo.py "Alice Smith" "Alice Smith & Bob Jones" --out /tmp/plot.png
"""

import argparse
import json
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.ticker as ticker


COLORS = ["steelblue", "tomato", "seagreen", "darkorange", "mediumpurple", "brown"]


def _load_history(history_path: str | Path = "data/elo_history.json") -> dict:
    return json.loads(Path(history_path).read_text()).get("history", {})


def _load_comp_names(data_dir: str | Path = "data/raw") -> dict[str, str]:
    names = {}
    for p in Path(data_dir).glob("comp_*.zip"):
        try:
            from scrape.zip_store import load_json
            cyi = p.stem.split("_")[1]
            info = load_json(p, "competition_info.json")
            names[cyi] = info.get("Comp_Year_Name") or info.get("Competition_Name") or cyi
        except Exception:
            pass
    return names


def _is_couple(name: str) -> tuple[str, str] | None:
    if " & " in name:
        parts = name.split(" & ", 1)
        return parts[0].strip(), parts[1].strip()
    return None


def _heat_key(cyi: str, entry: dict) -> tuple:
    return (cyi, entry["event_name"], entry["round_name"], entry["dance_name"])


def _extract_entries(history: dict, name: str) -> tuple[dict[tuple, float], float | None]:
    couple = _is_couple(name)
    result = {}
    initial: float | None = None
    for cyi, heats in history.items():
        if couple:
            a, b = couple
            matched = [
                e for e in heats
                if (e["competitor"] == a and e.get("partner") == b)
                or (e["competitor"] == b and e.get("partner") == a)
            ]
        else:
            matched = [e for e in heats if e["competitor"] == name]
        for e in matched:
            if initial is None:
                initial = e["elo_before"]
            result[_heat_key(cyi, e)] = e["elo_after"]
    return result, initial


def _build_global_timeline(history: dict, series_entries: list[dict[tuple, float]]) -> list[tuple]:
    """
    Return ordered list of unique heat keys for all heats in the history
    that at least one series participated in. Preserves insertion order.
    """
    participating_keys = set()
    for entries in series_entries:
        participating_keys.update(entries.keys())

    seen = set()
    timeline = []
    for cyi, heats in history.items():
        for e in heats:
            key = _heat_key(cyi, e)
            if key not in seen and key in participating_keys:
                seen.add(key)
                timeline.append(key)
    return timeline


def _align_to_timeline(
    timeline: list[tuple],
    entries: dict[tuple, float],
    start_elo: float,
) -> list[float]:
    """ELO value at each heat in timeline; carry-forward when not competing."""
    elo = start_elo
    result = [elo]
    for key in timeline:
        if key in entries:
            elo = entries[key]
        result.append(elo)
    return result


def plot_elo(
    names: list[str],
    history_path: str | Path = "data/elo_history.json",
    data_dir: str | Path = "data/raw",
    output_path: str | Path | None = None,
    show: bool = True,
) -> None:
    history = _load_history(history_path)
    comp_names = _load_comp_names(data_dir)

    extracted = [_extract_entries(history, name) for name in names]
    series_entries = [e for e, _ in extracted]
    series_initial = [s for _, s in extracted]
    timeline = _build_global_timeline(history, series_entries)

    if not timeline:
        print("No data found for any name.")
        return

    # competition boundary positions on the shared timeline
    boundaries: list[tuple[int, str]] = []
    prev_cyi = None
    for i, (cyi, *_) in enumerate(timeline):
        if cyi != prev_cyi:
            boundaries.append((i, cyi))
            prev_cyi = cyi

    fig, ax = plt.subplots(figsize=(16, 5))
    all_elos = []

    for i, name in enumerate(names):
        color = COLORS[i % len(COLORS)]
        start = series_initial[i]
        if start is None:
            print(f"  no data for: {name}")
            continue

        elo = _align_to_timeline(timeline, series_entries[i], start)
        all_elos.extend(elo)
        ax.step(range(len(elo)), elo, linewidth=1.2, color=color, where="post",
                label=f"{name} ({len(series_entries[i])} heats)")

    if not all_elos:
        print("No data found for any name.")
        plt.close()
        return

    pad = max(10, (max(all_elos) - min(all_elos)) * 0.05)
    ax.set_ylim(min(all_elos) - pad, max(all_elos) + pad * 3)

    band_colors = ["#efefef", "#ffffff"]
    for j, (heat_idx, cyi) in enumerate(boundaries):
        next_idx = boundaries[j + 1][0] if j + 1 < len(boundaries) else len(timeline)
        color = band_colors[j % len(band_colors)]
        ax.axvspan(heat_idx, next_idx, color=color, alpha=0.5, zorder=0)
        label = comp_names.get(cyi, cyi)
        mid = (heat_idx + next_idx) / 2
        ax.text(mid, ax.get_ylim()[0] + 1, label,
                fontsize=8, color="#555555", ha="center", va="bottom",
                fontweight="bold")

    ax.set_title("ELO progression — " + ", ".join(names), fontsize=13)
    ax.set_xlabel(f"Shared heat index ({len(timeline)} total heats)")
    ax.set_ylabel("ELO rating")
    ax.yaxis.set_minor_locator(ticker.AutoMinorLocator())
    ax.grid(True, which="major", alpha=0.3)
    ax.grid(True, which="minor", alpha=0.1)
    ax.legend(loc="upper left")
    fig.tight_layout()

    if output_path:
        fig.savefig(output_path, dpi=150)
        print(f"saved: {output_path}")
    if show:
        plt.show()
    else:
        plt.close()


def main():
    parser = argparse.ArgumentParser(description="Plot ELO progression for competitors or couples.")
    parser.add_argument("names", nargs="+", help="Competitor name(s) or 'A & B' for a couple")
    parser.add_argument("--history", default="data/elo_history.json")
    parser.add_argument("--data-dir", default="data/raw")
    parser.add_argument("--out", default=None, help="Save to file instead of showing")
    args = parser.parse_args()

    plot_elo(
        names=args.names,
        history_path=args.history,
        data_dir=args.data_dir,
        output_path=args.out,
        show=args.out is None,
    )


if __name__ == "__main__":
    main()
