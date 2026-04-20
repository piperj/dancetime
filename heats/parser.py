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
    instances: dict[str, HeatInstance] = {}

    for competitor_data in heatlists:
        meta = competitor_data.get("_metadata", {})
        competitor_name = meta.get("competitor_name", "")
        studio = meta.get("studio", "")

        for entry in competitor_data.get("Entries", []):
            partner_parts = []
            for p in entry.get("Participants", []):
                name_parts = p.get("Name", [])
                partner_parts.append(" ".join(str(x) for x in name_parts))
            partner_name = " & ".join(partner_parts)
            couple = f"{competitor_name} & {partner_name}" if partner_name else competitor_name

            for event in entry.get("Events", []):
                event_name = event.get("Event_Name", "")
                bib = str(event.get("Bib", ""))
                heat_num = str(event.get("Heat", ""))

                for round_ in event.get("Rounds", []):
                    sid = str(round_.get("Session", "")).strip()
                    time_str = round_.get("Round_Time", "")
                    round_name = round_.get("Round_Name", "")

                    t = parse_round_time(time_str)
                    time_iso = t.isoformat() if t else time_str
                    time_key = time_str.replace("/", "").replace(":", "").replace(" ", "").replace(",", "")
                    key = f"{sid}_{heat_num}_{time_key[:12]}"

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

    return sorted(instances.values(), key=lambda h: (h.session, h.heat_number, h.time))


def _build_result_index(results: list[dict]) -> dict[str, str]:
    index = {}
    for comp_data in results:
        for event in comp_data.get("Events", []):
            event_name = event.get("Name", "")
            for round_ in event.get("Rounds", []):
                round_name = round_.get("Name", "")
                for dance in round_.get("Dances", []):
                    for comp in dance.get("Competitors", []):
                        placement = comp.get("Result")
                        if placement is None:
                            continue
                        for participant in comp.get("Participants", []):
                            name_parts = participant.get("Name", [])
                            name = " ".join(str(x) for x in name_parts)
                            index[_result_key(event_name, round_name, name)] = str(placement)
    return index


def _result_key(event: str, round_name: str, competitor: str) -> str:
    return f"{event}|{round_name}|{competitor}"


def _entry_exists(instance: HeatInstance, competitor_name: str, partner_name: str) -> bool:
    for e in instance.entries:
        if e.competitor1 == competitor_name:
            return True
        if partner_name and e.competitor1 == partner_name and e.competitor2 == competitor_name:
            return True
    return False
