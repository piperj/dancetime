from datetime import datetime, timedelta, timezone


def is_comp_active(calendar: dict, now: datetime | None = None) -> tuple[bool, int | None]:
    if now is None:
        now = datetime.now(timezone.utc)
    now_date = now.date()

    for comp in calendar.get("competitions", []):
        start = _parse_date(comp.get("start_date", ""))
        end = _parse_date(comp.get("end_date", ""))
        if start is None or end is None:
            continue
        active_until = end + timedelta(days=1)
        if start <= now_date <= active_until:
            return True, comp.get("cyi")

    return False, None


def _parse_date(date_str: str):
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(date_str, fmt).date()
        except (ValueError, TypeError):
            pass
    return None
