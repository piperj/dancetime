from datetime import datetime, timedelta, timezone

from schedule.calendar import parse_date


def is_comp_active(calendar: dict, now: datetime | None = None) -> tuple[bool, int | None]:
    override = calendar.get("active_cyi")
    if override is not None:
        return True, int(override)

    if now is None:
        now = datetime.now(timezone.utc)
    now_date = now.date()

    for comp in calendar.get("competitions", []):
        start = parse_date(comp.get("start_date", ""))
        end = parse_date(comp.get("end_date", ""))
        if start is None or end is None:
            continue
        if start <= now_date <= end + timedelta(days=1):
            return True, comp.get("cyi")

    return False, None
