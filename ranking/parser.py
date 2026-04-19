from ranking.models import DanceResult


def parse_results(results_json: dict) -> list[DanceResult]:
    all_results: list[DanceResult] = []
    for competitor_data in results_json.get("results", []):
        all_results.extend(_parse_competitor_events(competitor_data))
    deduplicated = _deduplicate(all_results)
    return sorted(
        [r for r in deduplicated if r.is_contested()],
        key=lambda r: r.sort_key,
    )


def _parse_competitor_events(data: dict) -> list[DanceResult]:
    results = []
    for event in data.get("Events", []):
        event_id = event.get("ID", 0)
        event_name = event.get("Name", "")
        for round_ in event.get("Rounds", []):
            round_id = round_.get("ID", 0)
            round_name = round_.get("Name", "")
            session_id = round_.get("Session_ID", 0)
            dances = round_.get("Dances", [])

            if _has_individual_results(dances):
                results.extend(_parse_individual_dances(event_id, event_name, round_id, round_name, session_id, dances))
            else:
                combined = _parse_summary_fallback(event_id, event_name, round_id, round_name, session_id, round_)
                if combined:
                    results.append(combined)
    return results


def _has_individual_results(dances: list[dict]) -> bool:
    for dance in dances:
        for comp in dance.get("Competitors", []):
            if comp.get("Result") is not None or comp.get("Marks"):
                return True
    return False


def _parse_individual_dances(
    event_id, event_name, round_id, round_name, session_id, dances
) -> list[DanceResult]:
    results = []
    num_judges = 0
    if dances and dances[0].get("Competitors"):
        num_judges = len(dances[0]["Competitors"][0].get("Marks", []))

    for dance in dances:
        dance_id = dance.get("Dance_ID", 0)
        dance_name = dance.get("Dance_Name", "")
        competitors, partners, placements = [], {}, {}

        for comp in dance.get("Competitors", []):
            participants = comp.get("Participants", [])
            if not participants:
                continue
            placement = comp.get("Result")
            if placement is None and num_judges > 0:
                marks = comp.get("Marks", [])
                if marks:
                    placement = num_judges - sum(marks) + 1

            if len(participants) == 1:
                name = _join_name(participants[0].get("Name", []))
                competitors.append(name)
                if placement is not None:
                    placements[name] = int(placement)
            elif len(participants) == 2:
                n1 = _join_name(participants[0].get("Name", []))
                n2 = _join_name(participants[1].get("Name", []))
                for n in (n1, n2):
                    if n not in competitors:
                        competitors.append(n)
                partners[n1] = n2
                partners[n2] = n1
                if placement is not None:
                    placements[n1] = int(placement)
                    placements[n2] = int(placement)

        if competitors:
            results.append(DanceResult(
                event_id=event_id, event_name=event_name,
                round_id=round_id, round_name=round_name,
                dance_id=dance_id, dance_name=dance_name,
                session_id=session_id, heat_number=0, time="",
                competitors=competitors, partners=partners, placements=placements,
            ))
    return results


def _parse_summary_fallback(
    event_id, event_name, round_id, round_name, session_id, round_data
) -> DanceResult | None:
    summary = round_data.get("Summary", {})
    if not summary or not summary.get("Competitors"):
        return None
    dances = round_data.get("Dances", [])
    dance_id = dances[0].get("Dance_ID", round_id) if dances else round_id
    competitors, partners, placements = [], {}, {}

    for comp in summary["Competitors"]:
        participants = comp.get("Participants", [])
        if not participants:
            continue
        placement = _extract_placement(comp)

        if len(participants) == 1:
            name = _join_name(participants[0].get("Name", []))
            competitors.append(name)
            if placement is not None:
                placements[name] = placement
        elif len(participants) == 2:
            n1 = _join_name(participants[0].get("Name", []))
            n2 = _join_name(participants[1].get("Name", []))
            for n in (n1, n2):
                if n not in competitors:
                    competitors.append(n)
            partners[n1] = n2
            partners[n2] = n1
            if placement is not None:
                placements[n1] = placement
                placements[n2] = placement

    if not competitors:
        return None
    return DanceResult(
        event_id=event_id, event_name=event_name,
        round_id=round_id, round_name=round_name,
        dance_id=dance_id, dance_name=f"{round_name} (Combined)",
        session_id=session_id, heat_number=0, time="",
        competitors=competitors, partners=partners, placements=placements,
    )


def _deduplicate(results: list[DanceResult]) -> list[DanceResult]:
    index: dict[tuple, DanceResult] = {}
    for r in results:
        key = (r.event_id, r.round_id, r.dance_id)
        if key not in index:
            index[key] = r
        else:
            existing = index[key]
            for c in r.competitors:
                if c not in existing.competitors:
                    existing.competitors.append(c)
            existing.partners.update(r.partners)
            existing.placements.update(r.placements)
    return list(index.values())


def _extract_placement(comp: dict) -> int | None:
    result = comp.get("Result")
    if isinstance(result, list) and result and result[0]:
        try:
            return int(result[0])
        except (ValueError, TypeError):
            pass
    elif isinstance(result, (int, float)):
        return int(result)
    circuit = comp.get("Circuit", {})
    if isinstance(circuit, dict) and "Place" in circuit:
        try:
            return int(circuit["Place"])
        except (ValueError, TypeError):
            pass
    return None


def _join_name(parts: list) -> str:
    if not parts or not isinstance(parts, list):
        return "Unknown"
    return " ".join(str(p) for p in parts if p)
