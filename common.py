import re

_SHORT_NAME_RE = re.compile(r'\b(?:dancesport|championships?|competition)\b', re.IGNORECASE)


def short_name(name: str) -> str:
    result = _SHORT_NAME_RE.sub('', name)
    return re.sub(r'\s{2,}', ' ', result).strip(' ,')


def comp_meta(info: dict) -> tuple[str, str, str]:
    name = info.get("Competition_Name") or info.get("Name", "")
    date_range = info.get("Date_Range", "")
    if not date_range:
        start = info.get("Start_Date") or info.get("StartDate", "")
        end = info.get("End_Date") or info.get("EndDate", "")
        date_range = f"{start} – {end}" if start and end else start or end
    return name, date_range, info.get("Location", "")
