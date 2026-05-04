from datetime import date, timedelta

SOON_DAYS = 10
UPCOMING_DAYS = 30
GRACE_DAYS = 1  # days after end_date still considered live

PHASE_INTERVALS: dict[str, timedelta | None] = {
    "live":     timedelta(minutes=15),
    "soon":     timedelta(hours=1),
    "upcoming": timedelta(hours=24),
    "recent":   timedelta(hours=24),
    "distant":  None,
    "none":     None,
}

PHASE_URGENCY = {"live": 0, "soon": 1, "upcoming": 2, "recent": 2, "distant": 3, "none": 4}


def comp_phase(start: date, end: date, now_date: date) -> str:
    if start <= now_date <= end + timedelta(days=GRACE_DAYS):
        return "live"
    if now_date < start:
        days = (start - now_date).days
        if days <= SOON_DAYS:
            return "soon"
        if days <= UPCOMING_DAYS:
            return "upcoming"
        return "distant"
    days = (now_date - end).days
    if days <= UPCOMING_DAYS:
        return "recent"
    return "distant"


def interval_label(phase: str) -> str | None:
    iv = PHASE_INTERVALS.get(phase)
    if iv is None:
        return None
    total = int(iv.total_seconds())
    if total < 3600:
        return f"every {total // 60} min"
    if total < 86400:
        return f"every {total // 3600}h"
    return f"every {total // 86400}d"
