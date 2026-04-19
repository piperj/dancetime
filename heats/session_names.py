from datetime import datetime


# Round_Time format: "1/23/2026 12:10:42 PM"
_TIME_FORMATS = [
    "%m/%d/%Y %I:%M:%S %p",
    "%m/%d/%Y %I:%M %p",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%dT%H:%M",
]


def parse_round_time(time_str: str) -> datetime | None:
    for fmt in _TIME_FORMATS:
        try:
            return datetime.strptime(time_str.strip(), fmt)
        except (ValueError, AttributeError):
            pass
    return None


def infer_session_names(heatlists: list[dict]) -> dict[str, str]:
    earliest: dict[str, datetime] = {}

    for competitor_data in heatlists:
        for entry in competitor_data.get("Entries", []):
            for event in entry.get("Events", []):
                for round_ in event.get("Rounds", []):
                    sid = str(round_.get("Session", "")).strip()
                    raw_time = round_.get("Round_Time", "")
                    if not sid or not raw_time:
                        continue
                    t = parse_round_time(raw_time)
                    if t is None:
                        continue
                    if sid not in earliest or t < earliest[sid]:
                        earliest[sid] = t

    names = {}
    for sid, t in earliest.items():
        hour = t.hour
        if hour < 12:
            period = "Morning"
        elif hour < 17:
            period = "Afternoon"
        else:
            period = "Evening"
        day = t.strftime("%A")
        names[sid] = f"{day} {period}"
    return names
