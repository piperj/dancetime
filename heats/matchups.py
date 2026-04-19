from collections import defaultdict

from heats.parser import HeatInstance


def compute_top_matchups(
    heat_instances: list[HeatInstance], top_n: int = 5
) -> dict[str, list[dict]]:
    counts: dict[str, dict[str, dict]] = defaultdict(dict)

    for instance in heat_instances:
        entries = instance.entries
        for i, my_entry in enumerate(entries):
            me = my_entry.competitor1
            for j, their_entry in enumerate(entries):
                if i == j:
                    continue
                opponent = their_entry.couple
                if opponent not in counts[me]:
                    counts[me][opponent] = {
                        "opponent_couple": opponent,
                        "count": 0,
                        "my_bib": my_entry.bib,
                        "their_bib": their_entry.bib,
                    }
                counts[me][opponent]["count"] += 1

    result = {}
    for competitor, opponents in counts.items():
        sorted_opponents = sorted(opponents.values(), key=lambda x: x["count"], reverse=True)
        result[competitor] = sorted_opponents[:top_n]
    return result
