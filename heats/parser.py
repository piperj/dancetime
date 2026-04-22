from dataclasses import dataclass, field

from heats.session_names import parse_round_time


@dataclass
class HeatEntry:
    couple: str
    competitor1: str
    competitor2: str
    bib: str
    studio: str
    event: str
    result: str


@dataclass
class HeatInstance:
    key: str
    heat_number: str
    session: str
    session_name: str
    time: str
    round_name: str
    entries: list[HeatEntry] = field(default_factory=list)


def parse_heatlists(
    heatlists: list[dict],
    results: list[dict],
    session_names: dict[str, str],
) -> list[HeatInstance]:
    result_index = _build_result_index(results)
    name_to_studio = _build_name_to_studio(heatlists)
    instances: dict[str, HeatInstance] = {}

    for competitor_data in heatlists:
        meta = competitor_data.get("_metadata", {})
        competitor_name = meta.get("competitor_name", "")
        studio = meta.get("studio", "")

        for entry in competitor_data.get("Entries") or []:
            partner_parts = []
            for p in entry.get("Participants") or []:
                name_parts = p.get("Name") or []
                partner_parts.append(" ".join(str(x) for x in name_parts))
            partner_name = " & ".join(partner_parts)
            couple = f"{competitor_name} & {partner_name}" if partner_name else competitor_name

            for event in entry.get("Events") or []:
                event_name = event.get("Event_Name", "")
                bib = str(event.get("Bib", ""))
                heat_num = str(event.get("Heat", ""))

                for round_ in event.get("Rounds") or []:
                    sid = str(round_.get("Session", "")).strip()
                    time_str = round_.get("Round_Time", "")
                    round_name = round_.get("Round_Name", "")

                    t = parse_round_time(time_str)
                    time_iso = t.isoformat() if t else time_str
                    key = _make_heat_key(sid, heat_num, time_str)

                    if key not in instances:
                        instances[key] = HeatInstance(
                            key=key,
                            heat_number=heat_num,
                            session=sid,
                            session_name=session_names.get(sid, f"Session {sid}"),
                            time=time_iso,
                            round_name=round_name,
                        )

                    result_val = result_index.get(
                        _result_key(event_name, round_name, competitor_name), ""
                    )
                    entry_obj = HeatEntry(
                        couple=couple,
                        competitor1=competitor_name,
                        competitor2=partner_name,
                        bib=bib,
                        studio=studio,
                        event=event_name,
                        result=result_val,
                    )

                    if not _entry_exists(instances[key], competitor_name, partner_name):
                        instances[key].entries.append(entry_obj)

    _synthesize_rounds_from_results(instances, results, session_names, name_to_studio, result_index)

    return sorted(instances.values(), key=lambda h: (h.session, h.heat_number, h.time))


def _build_result_index(results: list[dict]) -> dict[str, str]:
    index = {}
    for comp_data in results:
        for event in comp_data.get("Events") or []:
            event_name = event.get("Name", "")
            for round_ in event.get("Rounds") or []:
                round_name = round_.get("Name", "")

                for dance in round_.get("Dances") or []:
                    for comp in dance.get("Competitors") or []:
                        placement = comp.get("Result")
                        if placement is None:
                            continue
                        for participant in comp.get("Participants") or []:
                            name_parts = participant.get("Name") or []
                            name = " ".join(str(x) for x in name_parts)
                            index[_result_key(event_name, round_name, name)] = str(placement)

                # Fall back to Summary Circuit.Place (multi-dance rounds like semi-finals
                # leave individual Result=None and store the combined placement here).
                # Place=0 means the couple advanced and has no elimination placement.
                summary = round_.get("Summary") or {}
                for comp in summary.get("Competitors") or []:
                    circuit = comp.get("Circuit") or {}
                    place = circuit.get("Place")
                    if not place:
                        continue
                    for participant in comp.get("Participants") or []:
                        name_parts = participant.get("Name") or []
                        name = " ".join(str(x) for x in name_parts)
                        key = _result_key(event_name, round_name, name)
                        if key not in index:
                            index[key] = str(place)

    return index


def _make_heat_key(sid: str, heat_num: str, time_str: str) -> str:
    time_key = time_str.replace("/", "").replace(":", "").replace(" ", "").replace(",", "")
    return f"{sid}_{heat_num}_{time_key[:12]}"


def _result_key(event: str, round_name: str, competitor: str) -> str:
    return f"{event}|{round_name}|{competitor}"


def _entry_exists(instance: HeatInstance, competitor_name: str, partner_name: str) -> bool:
    for e in instance.entries:
        if e.competitor1 == competitor_name:
            return True
        if partner_name and e.competitor1 == partner_name and e.competitor2 == competitor_name:
            return True
    return False


def _build_name_to_studio(heatlists: list[dict]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for competitor_data in heatlists:
        meta = competitor_data.get("_metadata", {})
        name = meta.get("competitor_name", "")
        studio = meta.get("studio", "")
        if name and studio:
            mapping[name] = studio
    return mapping


def _synthesize_rounds_from_results(
    instances: dict[str, HeatInstance],
    results: list[dict],
    session_names: dict[str, str],
    name_to_studio: dict[str, str],
    result_index: dict[str, str],
) -> None:
    """Create HeatInstances for rounds present in results but absent from heatlists.

    This happens when the NDCA API omits a round (e.g. a Final) from competitor
    heatlists even though the results are present in results.json.
    """
    existing: set[tuple[str, str, str]] = {(h.session, h.heat_number, h.round_name) for h in instances.values()}

    for comp_data in results:
        for ev in comp_data.get("Events") or []:
            heat_num = str(ev.get("Heat", ""))
            event_name = ev.get("Name", "")
            if not heat_num:
                continue

            for round_ in ev.get("Rounds") or []:
                round_name = round_.get("Name", "")
                sid_int = round_.get("Session_ID")
                sid = f"{int(sid_int):02d}" if sid_int is not None else "00"
                pair = (sid, heat_num, round_name)
                if pair in existing:
                    continue

                time_str = round_.get("Date_Time", "")
                t = parse_round_time(time_str)
                time_iso = t.isoformat() if t else time_str
                key = _make_heat_key(sid, heat_num, time_str)

                instance = HeatInstance(
                    key=key,
                    heat_number=heat_num,
                    session=sid,
                    session_name=session_names.get(sid, f"Session {sid}"),
                    time=time_iso,
                    round_name=round_name,
                )

                summary = round_.get("Summary") or {}
                for comp in summary.get("Competitors") or []:
                    bib = str(comp.get("Bib", ""))
                    participants = comp.get("Participants") or []
                    names = [" ".join(str(x) for x in p.get("Name") or []) for p in participants]
                    if not names:
                        continue
                    competitor1 = names[0]
                    competitor2 = names[1] if len(names) > 1 else ""
                    couple = f"{competitor1} & {competitor2}" if competitor2 else competitor1
                    studio = name_to_studio.get(competitor1) or name_to_studio.get(competitor2, "")
                    result_val = result_index.get(_result_key(event_name, round_name, competitor1), "")

                    instance.entries.append(HeatEntry(
                        couple=couple,
                        competitor1=competitor1,
                        competitor2=competitor2,
                        bib=bib,
                        studio=studio,
                        event=event_name,
                        result=result_val,
                    ))

                if instance.entries:
                    instances[key] = instance
                    existing.add(pair)
