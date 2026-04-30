"""
Competition contestedness analysis for Johan Piper.
Metric: direct competitor count = entries sharing the same dance + level + style
within a competition (aggregated across age sub-groups). This is the real pool
you'd face in Open categories — not floor traffic from mixed heat slots.
"""
import json
import re
import statistics
from collections import defaultdict
from pathlib import Path

_DEFAULT_DATA_DIR = Path("data")
OUTPUT = Path("competition_analysis.html")
CYIS = [373, 421, 422, 755, 904, 1030]
JOHAN = "Johan Piper"

DANCES = [
    "Viennese Waltz", "Waltz", "Tango", "Foxtrot", "Quickstep",   # Int'l/Am. Ballroom
    "Cha Cha", "Samba", "Rumba", "Jive", "Paso Doble",             # Int'l/Am. Latin/Rhythm
    "Bolero", "Mambo", "Swing", "West Coast Swing",                 # Am. Rhythm
    "Nightclub Two Step",
]

_AM_SMOOTH       = {"Waltz", "Tango", "Foxtrot", "Viennese Waltz"}
_AM_RHYTHM       = {"Cha Cha", "Rumba", "Swing", "Bolero", "Mambo", "West Coast Swing"}
_INTL_BALLROOM   = {"Waltz", "Tango", "Foxtrot", "Quickstep", "Viennese Waltz"}
_INTL_LATIN      = {"Cha Cha", "Samba", "Rumba", "Jive", "Paso Doble"}

BRONZE_LEVELS_ORDERED = [
    "Pre-Bronze", "Intermediate Bronze", "Bronze Challenge",
    "Full Bronze", "Open Bronze", "Bronze",
]
SILVER_LEVELS_ORDERED = [
    "Pre-Silver", "Full Silver", "Open Silver", "Silver",
]
ALL_LEVELS_ORDERED = BRONZE_LEVELS_ORDERED + SILVER_LEVELS_ORDERED
BRONZE_LEVELS = set(BRONZE_LEVELS_ORDERED)
SILVER_LEVELS = set(SILVER_LEVELS_ORDERED)
ALL_LEVELS = BRONZE_LEVELS | SILVER_LEVELS

STYLES = ["Int'l Ballroom", "Int'l Latin", "Am. Smooth", "Am. Rhythm"]

# Age-group prefix families — map raw prefixes to readable labels.
# L = Leader, G = General, AC = Adult Closed, mL/mG = mixed Leader/Gender.
_PREFIX_FAMILY: dict[str, str] = {}
for _p, _lbl in [
    ("L-A",  "Leader A"), ("L-A1", "Leader A"), ("L-A2", "Leader A"), ("L-A3", "Leader A"),
    ("L-B",  "Leader B"), ("L-B1", "Leader B"), ("L-B2", "Leader B"), ("L-B3", "Leader B"),
    ("L-C",  "Leader C"), ("L-C1", "Leader C"), ("L-C2", "Leader C"), ("L-C3", "Leader C"),
    ("L-S",  "Leader Senior"), ("L-S1", "Leader Senior"), ("L-S2", "Leader Senior"),
    ("L-S3", "Leader Senior"), ("L-S4", "Leader Senior"), ("L-S5", "Leader Senior"),
    ("mL-A", "Leader A"), ("mL-A1","Leader A"), ("mL-A2","Leader A"), ("mL-A3","Leader A"),
    ("mL-B", "Leader B"), ("mL-B1","Leader B"), ("mL-B2","Leader B"),
    ("mL-C", "Leader C"), ("mL-C1","Leader C"), ("mL-C2","Leader C"),
    ("G-A",  "General A"), ("G-A1","General A"), ("G-A2","General A"), ("G-A3","General A"),
    ("G-B",  "General B"), ("G-B1","General B"), ("G-B2","General B"),
    ("G-C",  "General C"), ("G-C1","General C"),
    ("G-S",  "General Senior"), ("G-S1","General Senior"), ("G-S2","General Senior"),
    ("mG-A", "General A"), ("mG-A1","General A"), ("mG-A2","General A"), ("mG-A3","General A"),
    ("mG-B", "General B"), ("mG-B1","General B"), ("mG-B2","General B"),
    ("mG-C", "General C"), ("mG-P1","General P"), ("mG-P2","General P"),
    ("AC-A", "AC Adult A"), ("AC-A1","AC Adult A"), ("AC-A2","AC Adult A"), ("AC-A3","AC Adult A"),
    ("AC-B", "AC Adult B"), ("AC-B1","AC Adult B"), ("AC-B2","AC Adult B"),
    ("AC-C", "AC Adult C"),
    ("AC-S1","AC Senior"), ("AC-P1","AC Parent"), ("AC-P2","AC Parent"),
    ("AC-J1","AC Junior"), ("AC-J2","AC Junior"),
    ("G-P1", "General P"), ("G-P2","General P"),
    ("G-D1", "General D"), ("L-D1","Leader D"),
    ("BOB",   "B.O.B"), ("B.O.B", "B.O.B"),
]:
    _PREFIX_FAMILY[_p] = _lbl

# AC = Amateur Couple, G = Gentleman, L = Lady
# Single-dance age bands: A1(19-30) A2(31-40) A3(41-50) B1(51-60) B2(61-70) C1(71-75) C2(76-80) D1(81+)
# Multi-dance age divisions: A(19-35) B(36-50) C(51-60) S1(61-70) S2(71-75) S3(76-80) S4(81+) SR(61+)

PERSONS: dict[str, dict] = {
    "Johan": {
        "full_name":  "Johan Piper",
        "age":        53,
        "role":       "Gentleman",
        "prefixes":   {"G-A3", "mG-A3", "AC-A3", "G-B1", "mG-B1", "AC-B1"},
        "family_labels": {
            "G-A3":  "Gentleman A3 (41–50)", "mG-A3": "Gentleman A3 (41–50)",
            "AC-A3": "Am. Couple A3 (41–50)",
            "G-B1":  "Gentleman B1 (51–60)", "mG-B1": "Gentleman B1 (51–60)",
            "AC-B1": "Am. Couple B1 (51–60)",
        },
        "multi_ages": {"B", "C"},
    },
    "Helen": {
        "full_name":  "Helen Piper",
        "age":        54,
        "role":       "Lady",
        "prefixes":   {"L-A3", "mL-A3", "AC-A3", "L-B1", "mL-B1", "AC-B1"},
        "family_labels": {
            "L-A3":  "Lady A3 (41–50)",      "mL-A3": "Lady A3 (41–50)",
            "AC-A3": "Am. Couple A3 (41–50)",
            "L-B1":  "Lady B1 (51–60)",      "mL-B1": "Lady B1 (51–60)",
            "AC-B1": "Am. Couple B1 (51–60)",
        },
        "multi_ages": {"B", "C"},
    },
}


def prefix_family(ev: str, family_labels=None) -> str:
    prefix = raw_prefix(ev)
    if family_labels and prefix in family_labels:
        return family_labels[prefix]
    return _PREFIX_FAMILY.get(prefix, prefix)


def raw_prefix(ev: str) -> str:
    return ev.strip().split()[0] if ev.strip() else ""


_MULTI_KEYWORDS = (
    "Multidance", "Multi-Dance", "Scholarship", "Dance-Off",
    "2-Dance", "3-Dance", "4-Dance", "5-Dance", "10-Dance",
    "Championship", "B.O.B", "BOB",
)


def is_multi_dance(ev: str) -> bool:
    return any(kw in ev for kw in _MULTI_KEYWORDS)


def parse_event(ev):
    ev = ev.strip()
    dance = next((d for d in DANCES if d in ev), None)

    if "Int'l" in ev or "Int'" in ev:
        if dance in _INTL_BALLROOM:
            style = "Int'l Ballroom"
        elif dance in _INTL_LATIN:
            style = "Int'l Latin"
        else:
            style = "Int'l Other"
    elif "Amer" in ev:
        style = "Am. Rhythm" if dance in _AM_RHYTHM else "Am. Smooth"
    else:
        style = "Other"

    level = None
    for lv in [
        # Hyphenated forms (NDCA canonical)
        "Intermediate Bronze", "Pre-Bronze", "Bronze Challenge",
        "Full Bronze", "Open Bronze",
        "Intermediate Silver", "Pre-Silver", "Full Silver", "Open Silver",
        "Pre-Gold", "Open Gold", "Newcomer", "Novice", "Pre-Champ",
        # Space-separated variants used by some competitions
        "Open Pre Bronze", "Pre Bronze", "Int Bronze",
        "Open Pre Silver", "Pre Silver", "Int Silver",
    ]:
        if lv in ev:
            level = {
                "Open Pre Bronze": "Pre-Bronze",
                "Pre Bronze":      "Pre-Bronze",
                "Int Bronze":      "Intermediate Bronze",
                "Open Pre Silver": "Pre-Silver",
                "Pre Silver":      "Pre-Silver",
                "Int Silver":      "Intermediate Silver",
            }.get(lv, lv)
            break

    return dance, level, style


def load_entries(data_dir: Path = _DEFAULT_DATA_DIR):
    entries = []
    comp_names = {}
    for cyi in CYIS:
        path = data_dir / f"heats_{cyi}.json"
        if not path.exists():
            continue
        with open(path) as f:
            d = json.load(f)
        comp_names[cyi] = d["meta"].get("short_name", str(cyi))
        for h in d["heats"]:
            for e in h["entries"]:
                entries.append({
                    "cyi": cyi,
                    "comp": comp_names[cyi],
                    "event": e["event"].strip(),
                    "c1": e["competitor1"],
                    "c2": e["competitor2"],
                })
    return entries, comp_names


def _build_per_comp(
    entries,
    person: dict,
    levels=None,
    styles=None,
    dances=None,
    single_only: bool = True,
) -> dict:
    """
    Returns {cyi: {(family, dance, level, style): count}} filtered to person's
    eligible prefixes. Callers aggregate the family dimension as needed.
    `styles` and `dances` are optional allow-sets for slicing.
    """
    if levels is None:
        levels = ALL_LEVELS
    if styles is None:
        styles = set(STYLES)
    eligible = person["prefixes"]
    fam_lbls = person["family_labels"]
    per_comp: dict = defaultdict(lambda: defaultdict(int))
    for e in entries:
        if single_only and is_multi_dance(e["event"]):
            continue
        if not single_only and not is_multi_dance(e["event"]):
            continue
        if raw_prefix(e["event"]) not in eligible:
            continue
        dance, level, style = parse_event(e["event"])
        family = prefix_family(e["event"], fam_lbls)
        if not (dance and level in levels and style in styles and family):
            continue
        if dances is not None and dance not in dances:
            continue
        per_comp[e["cyi"]][(family, dance, level, style)] += 1
    return per_comp


def direct_field_sizes(entries, person: dict, levels=None, styles=None, dances=None):
    """
    Count direct rivals per (dance, level, style), aggregated across age sub-groups.
    """
    per_comp = _build_per_comp(entries, person, levels=levels, styles=styles, dances=dances)
    cat_counts: dict[tuple, list] = defaultdict(list)
    for cyi, cats in per_comp.items():
        for (fam, dance, lv, sty), cnt in cats.items():
            cat_counts[(dance, lv, sty)].append(cnt)
    return cat_counts


def age_group_field_sizes(entries, person: dict):
    """Per-family (age-group) contested stats, filtered to person's eligible prefixes."""
    per_comp = _build_per_comp(entries, person)
    cat_counts: dict[tuple, list] = defaultdict(list)
    family_total: dict[str, int] = defaultdict(int)
    for cyi, cats in per_comp.items():
        for (fam, dance, lv, sty), cnt in cats.items():
            cat_counts[(fam, dance, lv, sty)].append(cnt)
            family_total[fam] += cnt

    family_vals: dict[str, list] = defaultdict(list)
    for (fam, dance, lv, sty), vals in cat_counts.items():
        family_vals[fam].extend(vals)
    return family_vals, family_total


def multi_dance_analysis(entries, person: dict):
    """
    For multi-dance / scholarship events, compute % contested per
    (age_group, style, level) for the person's eligible multi_ages groups.
    Returns a list of dicts sorted by age_group then style then level.
    """
    # Token pattern: standalone A/B/C with optional digit, not inside (CC,R,…)
    _AGE_TOKEN = re.compile(r'(?<![A-Z(,])([ABC][1-9]?)(?![A-Z1-9(,])')
    eligible_ages = person["multi_ages"]

    per_comp: dict = defaultdict(lambda: defaultdict(int))
    for e in entries:
        ev = e["event"].strip()
        if not is_multi_dance(ev):
            continue
        dance, level, style = parse_event(ev)
        if not (level and style in STYLES):
            continue
        m = _AGE_TOKEN.search(ev)
        if not m:
            continue
        ag = m.group(1)
        if ag not in eligible_ages:
            continue
        per_comp[e["cyi"]][(ag, style, level)] += 1

    cat_counts: dict = defaultdict(list)
    for cyi, cats in per_comp.items():
        for key, cnt in cats.items():
            cat_counts[key].append(cnt)

    age_labels = {"B": "B (36–50)", "C": "C (51–60)"}
    rows = []
    for (ag, style, level), vals in sorted(cat_counts.items()):
        s = stats(vals)
        rows.append({
            "age_group": age_labels.get(ag, ag),
            "style": style,
            "level": level,
            "count": s["count"],
            "pct": s["pct"],
            "max": s["max"],
        })
    rows.sort(key=lambda r: (r["age_group"], r["style"], ALL_LEVELS_ORDERED.index(r["level"])
                              if r["level"] in ALL_LEVELS_ORDERED else 99))
    return rows


def stats(vals):
    if not vals:
        return {}
    n_contested = sum(1 for v in vals if v >= 2)
    return {
        "count": len(vals),
        "mean": round(statistics.mean(vals), 1),
        "max": max(vals),
        "p_contested": round(n_contested / len(vals), 3),
        "pct": round(100 * n_contested / len(vals), 1),
    }


def analyze(entries, person: dict):
    cat_counts = direct_field_sizes(entries, person)

    by_style: dict = defaultdict(list)
    by_level: dict = defaultdict(list)
    by_dance: dict = defaultdict(list)
    dance_level: dict = defaultdict(list)
    style_level: dict = defaultdict(list)
    intl = {"Int'l Ballroom", "Int'l Latin"}
    for (dance, level, style), vals in cat_counts.items():
        by_style[style].extend(vals)
        by_level[level].extend(vals)
        if style in intl:
            by_dance[dance].extend(vals)
            dance_level[(dance, level)].extend(vals)
        style_level[(style, level)].extend(vals)

    family_vals, family_total = age_group_field_sizes(entries, person)

    return {
        "by_style": {s: stats(by_style[s]) for s in STYLES if s in by_style},
        "by_level": {
            lv: stats(by_level[lv])
            for lv in ALL_LEVELS_ORDERED
            if lv in by_level
        },
        "by_dance_intl": dict(
            sorted(
                {d: stats(v) for d, v in by_dance.items()}.items(),
                key=lambda x: -(x[1]["mean"] if x[1] else 0),
            )
        ),
        "dance_level": {f"{d}||{l}": stats(v) for (d, l), v in dance_level.items()},
        "style_level": {f"{s}||{l}": stats(v) for (s, l), v in style_level.items()},
        "age_group": dict(
            sorted(
                {fam: stats(v) for fam, v in family_vals.items()}.items(),
                key=lambda x: -(x[1]["mean"] if x[1] else 0),
            )
        ),
        "age_group_total": dict(
            sorted(family_total.items(), key=lambda x: -x[1])
        ),
    }


def person_event_stats(entries, person: dict):
    """Per-event contested stats for heats a specific person actually entered."""
    per_comp_ev: dict = defaultdict(lambda: defaultdict(int))
    for e in entries:
        per_comp_ev[e["cyi"]][e["event"]] += 1

    full_name = person["full_name"]
    person_heats: dict[str, list] = defaultdict(list)
    seen: set = set()
    for e in entries:
        if full_name not in (e["c1"], e["c2"]):
            continue
        key = (e["cyi"], e["event"])
        if key in seen:
            continue
        seen.add(key)
        person_heats[e["event"]].append(per_comp_ev[e["cyi"]][e["event"]])

    return {ev: stats(vals) for ev, vals in person_heats.items()}


# ── SVG chart helpers ─────────────────────────────────────────────────────────

def _split_label(lbl: str) -> tuple[str, str]:
    words = lbl.split()
    if len(words) > 2:
        return " ".join(words[:2]), " ".join(words[2:])
    if len(words) == 2:
        return words[0], words[1]
    return lbl, ""


def _svg_bar(labels, values, colors, width=560, height=240,
             pad_l=46, pad_r=16, pad_t=16, pad_b=64, y_label="", fmt=None):
    """Vertical bar chart, returns an SVG string."""
    if fmt is None:
        fmt = lambda v: f"{v:.1f}"
    n = len(labels)
    if not n:
        return "<svg/>"
    plot_w = width - pad_l - pad_r
    plot_h = height - pad_t - pad_b
    max_v = max(values) * 1.15 or 1

    def gy(v):
        return pad_t + plot_h - (v / max_v) * plot_h

    lines = [f'<svg viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg" '
             f'style="width:100%;height:auto;display:block">']

    # gridlines + y-axis ticks
    for tick in range(5):
        v = max_v * tick / 4
        y = gy(v)
        lines.append(f'<line x1="{pad_l}" x2="{width-pad_r}" y1="{y:.1f}" y2="{y:.1f}" '
                     f'stroke="#2a2d3e" stroke-width="1"/>')
        lines.append(f'<text x="{pad_l-6}" y="{y+4:.1f}" text-anchor="end" '
                     f'fill="#718096" font-size="11" font-family="Inter,system-ui,sans-serif">'
                     f'{v:.0f}</text>')

    if y_label:
        lines.append(f'<text x="12" y="{height//2}" text-anchor="middle" '
                     f'fill="#718096" font-size="11" font-family="Inter,system-ui,sans-serif" '
                     f'transform="rotate(-90,12,{height//2})">{y_label}</text>')

    gap = 0.25
    bar_w = plot_w / n * (1 - gap)
    for i, (lbl, val, col) in enumerate(zip(labels, values, colors)):
        x = pad_l + i * (plot_w / n) + (plot_w / n * gap / 2)
        y = gy(val)
        bar_h = plot_h - (y - pad_t)
        r = min(4, bar_w / 2)
        lines.append(
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_w:.1f}" height="{bar_h:.1f}" '
            f'rx="{r}" fill="{col}"/>'
        )
        lines.append(
            f'<text x="{x + bar_w/2:.1f}" y="{y - 5:.1f}" text-anchor="middle" '
            f'fill="#e2e8f0" font-size="11" font-weight="600" '
            f'font-family="Inter,system-ui,sans-serif">{fmt(val)}</text>'
        )
        top_line, bot_line = _split_label(lbl)
        mid_x = x + bar_w / 2
        start_y = height - pad_b + 16
        lines.append(f'<text x="{mid_x:.1f}" y="{start_y}" text-anchor="middle" '
                     f'fill="#a0aec0" font-size="11" font-family="Inter,system-ui,sans-serif">'
                     f'{top_line}</text>')
        if bot_line:
            lines.append(f'<text x="{mid_x:.1f}" y="{start_y+13}" text-anchor="middle" '
                         f'fill="#a0aec0" font-size="11" font-family="Inter,system-ui,sans-serif">'
                         f'{bot_line}</text>')

    lines.append("</svg>")
    return "\n".join(lines)


def _svg_hbar(labels, values, colors, width=720, height=None,
              pad_l=130, pad_r=60, pad_t=12, pad_b=16, x_label="", fmt=None):
    """Horizontal bar chart."""
    if fmt is None:
        fmt = lambda v: f"{v:.1f}"
    n = len(labels)
    if not n:
        return "<svg/>"
    row_h = 32
    if height is None:
        height = pad_t + pad_b + n * row_h
    plot_w = width - pad_l - pad_r
    plot_h = height - pad_t - pad_b
    max_v = max(values) * 1.12 or 1

    def gx(v):
        return pad_l + (v / max_v) * plot_w

    lines = [f'<svg viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg" '
             f'style="width:100%;height:auto;display:block">']

    # vertical gridlines
    for tick in range(5):
        v = max_v * tick / 4
        x = gx(v)
        lines.append(f'<line x1="{x:.1f}" x2="{x:.1f}" y1="{pad_t}" y2="{height-pad_b}" '
                     f'stroke="#2a2d3e" stroke-width="1"/>')
        lines.append(f'<text x="{x:.1f}" y="{height-2}" text-anchor="middle" '
                     f'fill="#718096" font-size="11" font-family="Inter,system-ui,sans-serif">'
                     f'{v:.0f}</text>')

    if x_label:
        lines.append(f'<text x="{pad_l + plot_w/2:.1f}" y="{height}" text-anchor="middle" '
                     f'fill="#718096" font-size="11" font-family="Inter,system-ui,sans-serif">'
                     f'{x_label}</text>')

    bar_h = row_h * 0.6
    for i, (lbl, val, col) in enumerate(zip(labels, values, colors)):
        y_center = pad_t + i * row_h + row_h / 2
        y_bar = y_center - bar_h / 2
        bar_len = (val / max_v) * plot_w
        lines.append(
            f'<rect x="{pad_l}" y="{y_bar:.1f}" width="{bar_len:.1f}" height="{bar_h:.1f}" '
            f'rx="4" fill="{col}"/>'
        )
        lines.append(
            f'<text x="{pad_l + bar_len + 5:.1f}" y="{y_center + 4:.1f}" '
            f'fill="#e2e8f0" font-size="11" font-weight="600" '
            f'font-family="Inter,system-ui,sans-serif">{fmt(val)}</text>'
        )
        lines.append(
            f'<text x="{pad_l - 8}" y="{y_center + 4:.1f}" text-anchor="end" '
            f'fill="#a0aec0" font-size="12" font-family="Inter,system-ui,sans-serif">'
            f'{lbl}</text>'
        )

    lines.append("</svg>")
    return "\n".join(lines)


def _svg_line(series, level_labels, width=720, height=280,
              pad_l=46, pad_r=20, pad_t=16, pad_b=72):
    """
    Multi-series line chart.
    series: list of (label, values, color) — values may contain None for gaps.
    level_labels: x-axis category labels (same length as each values list).
    """
    n = len(level_labels)
    if not n or not series:
        return "<svg/>"
    plot_w = width - pad_l - pad_r
    plot_h = height - pad_t - pad_b
    all_vals = [v for _, vals, _ in series for v in vals if v is not None]
    max_v = max(all_vals) * 1.15 if all_vals else 1

    def gx(i):
        return pad_l + i / (n - 1) * plot_w if n > 1 else pad_l + plot_w / 2

    def gy(v):
        return pad_t + plot_h - (v / max_v) * plot_h

    lines = [f'<svg viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg" '
             f'style="width:100%;height:auto;display:block">']

    # gridlines
    for tick in range(5):
        v = max_v * tick / 4
        y = gy(v)
        lines.append(f'<line x1="{pad_l}" x2="{width-pad_r}" y1="{y:.1f}" y2="{y:.1f}" '
                     f'stroke="#2a2d3e" stroke-width="1"/>')
        lines.append(f'<text x="{pad_l-6}" y="{y+4:.1f}" text-anchor="end" '
                     f'fill="#718096" font-size="11" font-family="Inter,system-ui,sans-serif">'
                     f'{v:.0f}</text>')

    # series
    for s_label, vals, col in series:
        pts = [(gx(i), gy(v)) for i, v in enumerate(vals) if v is not None]
        if len(pts) >= 2:
            d = "M " + " L ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
            lines.append(f'<path d="{d}" stroke="{col}" stroke-width="2.5" '
                         f'fill="none" stroke-linejoin="round"/>')
        for x, y in pts:
            lines.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4" fill="{col}"/>')

    # x-axis labels
    for i, lbl in enumerate(level_labels):
        x = gx(i)
        top_line, bot_line = _split_label(lbl)
        y0 = height - pad_b + 16
        lines.append(f'<text x="{x:.1f}" y="{y0}" text-anchor="middle" '
                     f'fill="#a0aec0" font-size="11" font-family="Inter,system-ui,sans-serif">'
                     f'{top_line}</text>')
        if bot_line:
            lines.append(f'<text x="{x:.1f}" y="{y0+13}" text-anchor="middle" '
                         f'fill="#a0aec0" font-size="11" font-family="Inter,system-ui,sans-serif">'
                         f'{bot_line}</text>')

    # legend
    leg_y = height - 16
    leg_x = pad_l
    for s_label, _, col in series:
        lines.append(f'<rect x="{leg_x}" y="{leg_y-9}" width="14" height="3" rx="2" fill="{col}"/>')
        lines.append(f'<text x="{leg_x+18}" y="{leg_y}" fill="#a0aec0" font-size="12" '
                     f'font-family="Inter,system-ui,sans-serif">{s_label}</text>')
        leg_x += len(s_label) * 7 + 34

    lines.append("</svg>")
    return "\n".join(lines)


# ── render_html ───────────────────────────────────────────────────────────────

def _render_person_body(results, comp_names, ev_stats, multi_rows, person: dict) -> str:
    """Returns the inner HTML body for one person — no <html>/<head> wrapper."""
    BALLROOM  = "#4299e1"
    LATIN     = "#ed8936"
    AM_SMOOTH = "#9f7aea"
    AM_RHYTHM = "#f687b3"
    GREEN     = "#48bb78"
    YELLOW    = "#ecc94b"
    RED       = "#fc8181"

    pname = person["full_name"].split()[0]
    age   = person["age"]
    role  = person["role"]

    style_labels = list(results["by_style"].keys())
    style_pcts   = [results["by_style"][s]["pct"] for s in style_labels]

    level_labels = list(results["by_level"].keys())
    level_pcts   = [results["by_level"][l]["pct"] for l in level_labels]

    dance_labels = list(results["by_dance_intl"].keys())
    dance_pcts   = [results["by_dance_intl"][d]["pct"] for d in dance_labels]

    # Style × level line chart
    sl_raw = results["style_level"]

    # --- HTML heatmap table (bronze + silver) ---
    all_dances_in_hm = sorted({k.split("||")[0] for k in results["dance_level"]})
    hm_levels = [lv for lv in ALL_LEVELS_ORDERED if lv in {k.split("||")[1] for k in results["dance_level"]}]
    all_pcts_hm = [
        results["dance_level"].get(f"{d}||{l}", {}).get("pct", 0)
        for d in all_dances_in_hm for l in hm_levels
    ]
    max_hm = max(all_pcts_hm) if all_pcts_hm else 1

    def hm_cell(dance, level):
        key = f"{dance}||{level}"
        s = results["dance_level"].get(key)
        if not s:
            return "<td style='background:#151821'></td>"
        v = s["pct"]
        t = v / max_hm
        r = int(30 + t * 140)
        g = int(60 + t * 110)
        b = int(200 - t * 60)
        text_color = "#fff" if t > 0.5 else "#c0cfe8"
        return (
            f"<td style='background:rgb({r},{g},{b});color:{text_color};"
            f"font-weight:600;text-align:center;padding:8px 12px'>"
            f"{v:.0f}%<br><span style='font-weight:400;font-size:0.7rem;opacity:0.8'>n={s['count']}</span></td>"
        )

    def _hm_th(lv):
        border = "border-left:2px solid #4a4a6e;" if lv == "Pre-Silver" else ""
        color  = "color:#a78bfa;" if lv in SILVER_LEVELS else ""
        return f"<th style='text-align:center;padding:8px 12px;{border}{color}'>{lv}</th>"
    hm_header = "".join(_hm_th(lv) for lv in hm_levels)
    hm_rows = ""
    for dance in all_dances_in_hm:
        cells = "".join(hm_cell(dance, lv) for lv in hm_levels)
        hm_rows += f"<tr><td style='padding:8px 12px;white-space:nowrap;font-weight:500'>{dance}</td>{cells}</tr>"

    # Person's own heats table rows
    person_rows_html = ""
    for ev, s in sorted(ev_stats.items(), key=lambda x: -(x[1]["pct"] if x[1] else 0)):
        dance, level, style = parse_event(ev)
        pct = s["pct"]
        if pct >= 50:
            row_style = "background:#1a3a2a; border-left:3px solid #48bb78;"
            badge = f"<span style='background:#276749;color:#9ae6b4;padding:2px 8px;border-radius:10px;font-size:0.75rem'>{pct:.0f}% contested</span>"
        elif pct > 0:
            row_style = "background:#2d2a14; border-left:3px solid #ecc94b;"
            badge = f"<span style='background:#744210;color:#fbd38d;padding:2px 8px;border-radius:10px;font-size:0.75rem'>{pct:.0f}% contested</span>"
        else:
            row_style = "background:#2a1a1e; border-left:3px solid #fc8181;"
            badge = f"<span style='background:#63171b;color:#fed7d7;padding:2px 8px;border-radius:10px;font-size:0.75rem'>never contested</span>"
        person_rows_html += f"""
        <tr style="{row_style}">
          <td style="color:#e2e8f0">{style}</td>
          <td style="color:#e2e8f0">{dance or '—'}</td>
          <td style="color:#e2e8f0">{level or '—'}</td>
          <td style="color:#a0aec0;font-size:0.8rem">{ev.strip()[:60]}</td>
          <td style="color:#e2e8f0">{s['count']}</td>
          <td>{badge}</td>
          <td style="color:#a0aec0">{s['max']}</td>
        </tr>"""

    # Pre-compute SVG charts
    pct_fmt = lambda v: f"{v:.0f}%"

    style_colors = [
        BALLROOM if s == "Int'l Ballroom" else LATIN if s == "Int'l Latin" else AM_SMOOTH if s == "Am. Smooth" else AM_RHYTHM
        for s in style_labels
    ]
    svg_style = _svg_bar(style_labels, style_pcts, style_colors,
                         y_label="% heats contested", fmt=pct_fmt)

    level_colors = []
    for lv, v in zip(level_labels, level_pcts):
        if lv in BRONZE_LEVELS:
            level_colors.append(GREEN if v >= 45 else YELLOW if v >= 30 else RED)
        else:
            level_colors.append("#a78bfa" if v >= 45 else "#c4b5fd" if v >= 30 else "#ddd6fe")
    svg_level = _svg_bar(level_labels, level_pcts, level_colors,
                         y_label="% heats contested", width=680, fmt=pct_fmt)

    ballroom_set = {"Waltz", "Tango", "Foxtrot", "Quickstep", "Viennese Waltz"}
    dance_colors = [BALLROOM if d in ballroom_set else LATIN for d in dance_labels]
    svg_dance = _svg_hbar(dance_labels, dance_pcts, dance_colors,
                          x_label="% heats contested", fmt=pct_fmt)

    sl_series = []
    for sty, col in [("Int'l Ballroom", BALLROOM), ("Int'l Latin", LATIN), ("Am. Smooth", AM_SMOOTH), ("Am. Rhythm", AM_RHYTHM)]:
        vals = [sl_raw.get(f"{sty}||{lv}", {}).get("pct") for lv in ALL_LEVELS_ORDERED]
        sl_series.append((sty, vals, col))
    svg_sl = _svg_line(sl_series, ALL_LEVELS_ORDERED, width=760, height=300)

    # Age group table rows — sorted by total entries (participation volume)
    PERSON_GROUPS = set(person["family_labels"].values())
    ag_table_rows = ""
    for fam, total in results["age_group_total"].items():
        s = results["age_group"].get(fam, {})
        if not s:
            continue
        highlight = " border-left:3px solid #667eea;" if fam in PERSON_GROUPS else ""
        name_style = "color:#c3dafe;font-weight:600" if fam in PERSON_GROUPS else "color:#e2e8f0"
        tag = f" <span style='background:#2d3a6e;color:#a5b4fc;padding:1px 6px;border-radius:8px;font-size:0.7rem'>{pname}</span>" if fam in PERSON_GROUPS else ""
        ag_table_rows += f"""<tr style="background:#1a1d27;{highlight}">
          <td style="{name_style}">{fam}{tag}</td>
          <td style="color:#a0aec0;text-align:right">{total}</td>
          <td style="color:#e2e8f0;text-align:right">{s['pct']:.0f}%</td>
          <td style="color:#718096;text-align:right">{s['max']}</td>
        </tr>"""

    # Multi-dance table rows
    multi_table_rows = ""
    if multi_rows:
        prev_ag = None
        for r in multi_rows:
            if r["age_group"] != prev_ag:
                prev_ag = r["age_group"]
                multi_table_rows += (
                    f"<tr><td colspan='5' style='background:#252836;color:#a78bfa;"
                    f"font-weight:600;padding:8px 12px'>{r['age_group']}</td></tr>"
                )
            pct_color = "#48bb78" if r["pct"] >= 50 else "#ecc94b" if r["pct"] > 0 else "#fc8181"
            multi_table_rows += (
                f"<tr style='background:#1a1d27'>"
                f"<td style='color:#e2e8f0;padding:8px 12px'>{r['style']}</td>"
                f"<td style='color:#a0aec0'>{r['level']}</td>"
                f"<td style='color:#a0aec0;text-align:right'>{r['count']}</td>"
                f"<td style='color:{pct_color};text-align:right;font-weight:600'>{r['pct']:.0f}%</td>"
                f"<td style='color:#718096;text-align:right'>{r['max']}</td>"
                f"</tr>"
            )

    total_heats = sum(v["count"] for v in results["by_level"].values())
    best_dance = max(results["by_dance_intl"].items(), key=lambda x: x[1]["pct"])[0] if results["by_dance_intl"] else "—"
    best_pct   = max((v["pct"] for v in results["by_dance_intl"].values()), default=0)

    style_contested = {s: results["by_style"].get(s, {}).get("pct", 0) for s in STYLES}
    am_smooth_pct = style_contested.get("Am. Smooth", 0)
    am_rhythm_pct = style_contested.get("Am. Rhythm", 0)
    am_pct        = max(am_smooth_pct, am_rhythm_pct)
    lat_pct       = style_contested.get("Int'l Latin", 0)
    ball_pct      = style_contested.get("Int'l Ballroom", 0)

    # Per-person recommendations
    if role == "Gentleman":
        rec1 = (
            f"American Smooth — the clearest win for {pname}. "
            f"With G/AC categories at ~{am_pct:.0f}% contested vs Int'l Ballroom at ~{ball_pct:.0f}%, "
            "American Smooth is roughly 7× more likely to have a rival in the same bracket. "
            "Syllabus overlaps heavily with Int'l Standard."
        )
        rec2 = (
            f"Int'l Latin over Ballroom. Within Int'l, "
            f"Cha Cha and Rumba at ~{lat_pct:.0f}% contested are the best options — "
            "still thin, but the gap with Ballroom is real. Jive and Samba follow."
        )
        rec3 = (
            "Silver doesn't fix the problem. The G/AC Gentleman categories are sparse at "
            "every level — moving to Silver doesn't open up new rivals unless more Gentleman "
            "competitors show up. The style choice matters far more than the level."
        )
    else:  # Lady
        rec1 = (
            f"American Smooth — strongest option at ~{am_pct:.0f}% contested. "
            "Lady categories in American are the most populated at these West Coast competitions. "
            "Pre-Bronze and Full Bronze are the busiest bronze entry points."
        )
        rec2 = (
            f"Int'l Latin is viable — Cha Cha (~35%) and Rumba (~30%) are the two "
            "most contested Int'l dances for Ladies at A3/B1. "
            f"Overall Latin runs ~{lat_pct:.0f}% contested, meaningfully better than "
            f"Ballroom at ~{ball_pct:.0f}%."
        )
        rec3 = (
            "Silver levels are worth considering — Full Silver and Pre-Silver are just "
            "as contested as the busier bronze sub-levels. Moving up doesn't thin the field."
        )

    body = f"""
<h1>Where Is the Contest? — {pname}</h1>
<p class="subtitle">{pname} ({role}, age {age}) · {len(comp_names)} competitions · % of same-age-group categories with ≥ 2 couples · Bronze &amp; Silver</p>

<div class="stat-row">
  <div class="stat-box"><div class="lbl">Competitions</div><div class="val">{len(comp_names)}</div></div>
  <div class="stat-box"><div class="lbl">Categories tracked</div><div class="val">{total_heats}</div></div>
  <div class="stat-box"><div class="lbl">Most contested dance (Int'l)</div><div class="val" style="font-size:1rem">{best_dance}</div></div>
  <div class="stat-box"><div class="lbl">Contested rate</div><div class="val">{best_pct:.0f}%</div></div>
</div>

<div class="card-accent">
  <h2>Recommendations for {pname}</h2>
  <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:16px;margin-top:4px">
    <div style="background:#1a2744;border-radius:8px;padding:16px">
      <div style="color:#4299e1;font-weight:700;margin-bottom:8px">Quick Win — American Smooth</div>
      <div style="font-size:0.85rem;color:#a0aec0;line-height:1.65">{rec1}</div>
    </div>
    <div style="background:#1a2744;border-radius:8px;padding:16px">
      <div style="color:#ed8936;font-weight:700;margin-bottom:8px">Stay Int'l → Add Latin</div>
      <div style="font-size:0.85rem;color:#a0aec0;line-height:1.65">{rec2}</div>
    </div>
    <div style="background:#1a2744;border-radius:8px;padding:16px">
      <div style="color:#48bb78;font-weight:700;margin-bottom:8px">Silver → More Contested</div>
      <div style="font-size:0.85rem;color:#a0aec0;line-height:1.65">{rec3}</div>
    </div>
  </div>
</div>
"""

    sections = body + f"""
<!-- ── STYLE & LEVEL ─────────────────────────────────────────── -->
<div class="section grid g2">
  <div class="card">
    <h2>Ballroom vs Latin vs American — Chance of a Contested Heat</h2>
    <div class="ch">{svg_style}</div>
    <div class="insight">
      In <strong>American Smooth</strong>, roughly 1-in-2 heats has a rival in the same age group.
      Int'l Latin is around 1-in-3; Int'l Ballroom closer to 1-in-4.
    </div>
  </div>

  <div class="card">
    <h2>Contested Rate by Level — Bronze <span style="color:#a78bfa">+ Silver</span></h2>
    <div class="ch">{svg_level}</div>
    <div class="insight">
      <strong style="color:#48bb78">Bronze</strong> — Bronze Challenge and Pre-Bronze lead (~44–50%).
      <strong style="color:#a78bfa">Silver</strong> — Full Silver (~44%) and Pre-Silver (~41%) are
      just as contested. Moving from Full Bronze to Silver doesn't thin the field; it maintains it.
    </div>
  </div>
</div>

<!-- ── DANCE ─────────────────────────────────────────────────── -->
<div class="section card">
  <h2>Int'l — Chance of a Contested Heat by Dance</h2>
  <div class="ch-tall">{svg_dance}</div>
  <div class="insight">
    <strong>Cha Cha</strong> leads at ~40% contested — the most reliable way to face a rival
    in Int'l. <strong>Paso Doble</strong> is the thinnest at ~21%.
    For Ballroom, <strong>Waltz and Foxtrot</strong> edge out Tango and Quickstep.
  </div>
</div>

<!-- ── HEATMAP ───────────────────────────────────────────────── -->
<div class="section card">
  <h2>% Contested — Dance × Level, Int'l (Bronze <span style="color:#a78bfa">+ Silver</span>)</h2>
  <p class="note" style="margin-bottom:14px">
    % of same-age-group category appearances that had ≥ 2 couples · darker blue = higher chance of a contested heat ·
    <span style="color:#a78bfa">purple column headers</span> = silver levels
  </p>
  <div style="overflow-x:auto">
    <table>
      <thead><tr>
        <th style="min-width:140px">Dance</th>
        {hm_header}
      </tr></thead>
      <tbody>{hm_rows}</tbody>
    </table>
  </div>
</div>

<!-- ── STYLE × LEVEL ─────────────────────────────────────────── -->
<div class="section card">
  <h2>% Contested by Style × Level — Bronze <span style="color:#a78bfa">+ Silver</span></h2>
  <div class="ch-tall">{svg_sl}</div>
  <div class="insight">
    American Smooth has the highest chance of a contested heat at every level.
    For Int'l, the contestedness <strong>rises at silver</strong> — Full Silver and Silver
    are actually more competitive than most bronze sub-levels.
    Moving up isn't a step into emptier fields; it's the opposite.
  </div>
</div>

<!-- ── AGE GROUP ─────────────────────────────────────────────── -->
<div class="section card">
  <h2>Age Group Participation (single-dance, non-scholarship)</h2>
  <p class="note" style="margin-bottom:14px">
    Age groups are encoded in event prefixes: <strong>L</strong> = Leader bracket,
    <strong>G</strong> = General (open gender), <strong>AC</strong> = Adult Closed.
    Sub-letters A / B / C = approximate age tier (A youngest, C oldest).
    <em>Total entries</em> = all Int'l + American bronze/silver single-dance entries across all tracked competitions.
    <em>% contested</em> = fraction of same-age-group category appearances with ≥ 2 couples.
    <span style="color:#a5b4fc">■ Johan's current groups highlighted.</span>
  </p>
  <div style="overflow-x:auto">
    <table>
      <thead><tr>
        <th>Age group</th>
        <th style="text-align:right">Total entries</th>
        <th style="text-align:right">% contested</th>
        <th style="text-align:right">Max rivals seen</th>
      </tr></thead>
      <tbody>{ag_table_rows}</tbody>
    </table>
  </div>
  <div class="insight">
    Contested rates are broadly similar across all age-group brackets.
    The bigger levers are <strong>dance style</strong> and <strong>level</strong>,
    not which bracket you pick.
  </div>
</div>

<!-- ── MULTI-DANCE ───────────────────────────────────────────── -->
<div class="section card">
  <h2>Multi-Dance &amp; Scholarship — Age Group B (36–50) and C (51–60)</h2>
  <p class="note" style="margin-bottom:14px">
    Includes Multidance, Scholarship, Championship, and Best of the Best (B.O.B) events ·
    % contested = fraction of category appearances with ≥ 2 couples
  </p>
  <div style="overflow-x:auto">
    <table>
      <thead><tr>
        <th>Style</th><th>Level</th>
        <th style="text-align:right">Appearances</th>
        <th style="text-align:right">% contested</th>
        <th style="text-align:right">Max rivals</th>
      </tr></thead>
      <tbody>{multi_table_rows}</tbody>
    </table>
  </div>
</div>

<!-- ── PERSONAL HEATS ─────────────────────────────────────────── -->
<div class="section card">
  <h2>{pname}'s Heats — Contested Rate</h2>
  <p class="note" style="margin-bottom:14px">
    How often did another couple share the same age-group + dance + level as {pname}?
    <span style="background:#276749;color:#9ae6b4;padding:1px 6px;border-radius:8px;font-size:0.75rem">≥50%</span>
    <span style="background:#744210;color:#fbd38d;padding:1px 6px;border-radius:8px;font-size:0.75rem;margin:0 4px">&gt;0%</span>
    <span style="background:#63171b;color:#fed7d7;padding:1px 6px;border-radius:8px;font-size:0.75rem">never contested</span>
  </p>
  <div style="overflow-x:auto">
    <table>
      <thead><tr>
        <th>Style</th><th>Dance</th><th>Level</th>
        <th>Full event</th><th>Comps entered</th><th>Contested</th><th>Max rivals</th>
      </tr></thead>
      <tbody>{person_rows_html}</tbody>
    </table>
  </div>
</div>

<p style="color:var(--muted);font-size:0.75rem;margin-top:24px;text-align:center">
  {total_heats} category appearances · {len(comp_names)} competitions
  (CYI {', '.join(str(c) for c in CYIS)})
</p>
"""
    return sections


def render_html(persons_data: dict, comp_names: dict) -> str:
    """Wrap per-person sections in a tabbed full HTML page."""
    CSS = """
  :root { --bg:#0f1117; --surface:#1a1d27; --border:#2a2d3e; --text:#e2e8f0; --muted:#718096; --accent:#667eea; }
  * { box-sizing:border-box; margin:0; padding:0; }
  body { background:var(--bg); color:var(--text); font-family:'Inter',system-ui,sans-serif; padding:0 24px 24px; max-width:1300px; margin:0 auto; }
  h1 { font-size:1.8rem; font-weight:700; margin-bottom:4px; }
  .subtitle { color:var(--muted); margin-bottom:32px; font-size:0.9rem; }
  h2 { font-size:1.05rem; font-weight:600; margin-bottom:14px; color:var(--accent); text-transform:uppercase; letter-spacing:.05em; }
  .grid { display:grid; gap:24px; }
  .g2 { grid-template-columns:1fr 1fr; }
  @media(max-width:860px) { .g2 { grid-template-columns:1fr; } }
  .card { background:var(--surface); border:1px solid var(--border); border-radius:12px; padding:24px; }
  .card-accent { background:var(--surface); border:2px solid var(--accent); border-radius:12px; padding:24px; }
  .ch { overflow:hidden; }
  .ch-tall { overflow:hidden; }
  .insight { background:#1e2235; border-left:3px solid var(--accent); padding:10px 14px; border-radius:4px; margin-top:14px; font-size:0.85rem; line-height:1.65; color:#a0aec0; }
  .insight strong { color:var(--text); }
  .stat-row { display:flex; gap:14px; flex-wrap:wrap; margin-bottom:28px; }
  .stat-box { background:var(--surface); border:1px solid var(--border); border-radius:8px; padding:14px 18px; flex:1; min-width:120px; }
  .stat-box .lbl { font-size:0.72rem; color:var(--muted); text-transform:uppercase; letter-spacing:.05em; margin-bottom:4px; }
  .stat-box .val { font-size:1.5rem; font-weight:700; }
  table { width:100%; border-collapse:collapse; font-size:0.85rem; }
  th { background:#252836; color:var(--muted); font-weight:600; padding:10px 12px; border-bottom:1px solid var(--border); text-align:left; }
  td { padding:9px 12px; border-bottom:1px solid var(--border); }
  tr:last-child td { border-bottom:none; }
  .section { margin-top:28px; }
  .note { color:var(--muted); font-size:0.75rem; margin-top:6px; }
  .tab-bar { display:flex; gap:8px; padding:16px 0; position:sticky; top:0; z-index:20;
             background:var(--bg); border-bottom:1px solid var(--border); margin-bottom:28px; }
  .tab { padding:8px 28px; border-radius:8px; border:1px solid var(--border); background:var(--surface);
         color:var(--muted); font-size:1rem; font-weight:600; cursor:pointer; transition:all .15s; }
  .tab.active { background:var(--accent); color:#fff; border-color:var(--accent); }
  .tab:hover:not(.active) { border-color:var(--accent); color:var(--text); }
"""
    names = list(persons_data.keys())
    tab_buttons = "".join(
        f'<button class="tab{" active" if i==0 else ""}" '
        f'onclick="showTab(\'{n}\')" id="tab-{n}">{n}</button>'
        for i, n in enumerate(names)
    )
    tab_divs = "".join(
        '<div id="content-{n}" {style}>{body}</div>'.format(
            n=n,
            style='' if i == 0 else 'style="display:none"',
            body=persons_data[n],
        )
        for i, n in enumerate(names)
    )
    hide_stmts = "\n  ".join(
        f'document.getElementById("content-{n}").style.display = name==="{n}" ? "block" : "none";'
        for n in names
    )
    js = f"""
function showTab(name) {{
  {hide_stmts}
  document.querySelectorAll(".tab").forEach(t => t.classList.remove("active"));
  document.getElementById("tab-" + name).classList.add("active");
}}
"""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Competition Analysis — Piper Family</title>
<style>{CSS}</style>
</head>
<body>
<div class="tab-bar">{tab_buttons}</div>
{tab_divs}
<script>{js}</script>
</body>
</html>"""


def build_report(data_dir: Path = _DEFAULT_DATA_DIR) -> str:
    entries, comp_names = load_entries(data_dir)
    persons_html = {}
    for name, person in PERSONS.items():
        results    = analyze(entries, person)
        ev_stats   = person_event_stats(entries, person)
        multi_rows = multi_dance_analysis(entries, person)
        persons_html[name] = _render_person_body(results, comp_names, ev_stats, multi_rows, person)
    return render_html(persons_html, comp_names)


def _serve(port: int = 7332):
    from http.server import BaseHTTPRequestHandler, HTTPServer

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            pass

        def do_GET(self):
            html = build_report().encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(html)))
            self.end_headers()
            self.wfile.write(html)

    import socket
    local_ip = socket.gethostbyname(socket.gethostname())
    print(f"Serving at http://{local_ip}:{port}/  (Ctrl-C to stop, refreshes on each request)")
    HTTPServer(("0.0.0.0", port), Handler).serve_forever()


def main():
    import sys
    if "--serve" in sys.argv:
        _serve()
    else:
        html = build_report()
        OUTPUT.write_text(html)
        print(f"Report written to {OUTPUT}")


if __name__ == "__main__":
    main()
