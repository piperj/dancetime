def process_participants(
    participants: list,
    placement,
    competitors: list,
    partners: dict,
    placements: dict,
) -> None:
    if len(participants) == 1:
        name = join_name(participants[0].get("Name", []))
        competitors.append(name)
        if placement is not None:
            placements[name] = int(placement)
    elif len(participants) == 2:
        n1 = join_name(participants[0].get("Name", []))
        n2 = join_name(participants[1].get("Name", []))
        for n in (n1, n2):
            if n not in competitors:
                competitors.append(n)
        partners[n1] = n2
        partners[n2] = n1
        if placement is not None:
            placements[n1] = int(placement)
            placements[n2] = int(placement)


def join_name(parts: list) -> str:
    if not parts or not isinstance(parts, list):
        return "Unknown"
    return " ".join(str(p) for p in parts if p)
