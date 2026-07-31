import re

from ranking.models import DanceResult
from ranking.parse_helpers import process_participants

_HEAT_NUMBER_RE = re.compile(r"(\d+)")


def parse_session_results(session_items: list[dict], session_id: int) -> list[DanceResult]:
    """Parse one session's `/feed/program/?type=2` response into DanceResults.

    Unlike parse_results() (which reads per-competitor results.json fragments
    and must _deduplicate them back together), a session response already
    contains one full-roster record per heat/round — no merge step needed.
    Only round-combined placements are available here (no per-dance judge
    marks), matching parse_results()'s _parse_summary_fallback path.
    """
    results = []
    for item in session_items:
        if item.get("Type") != "Heat":
            continue
        heat_number = _extract_heat_number(item.get("Title", ""))
        time_str = item.get("Date_Time", "")
        for floor in item.get("Floors") or []:
            for round_ in floor.get("Rounds") or []:
                result = _parse_round(round_, session_id, heat_number, time_str)
                if result is not None:
                    results.append(result)
    return sorted(
        [r for r in results if r.is_contested()],
        key=lambda r: r.sort_key,
    )


def _parse_round(round_: dict, session_id: int, heat_number: int, time_str: str) -> DanceResult | None:
    round_id = round_.get("ID", 0)
    event_id = round_.get("Event_ID", 0)
    event_name = round_.get("Name", "")
    round_name = round_.get("Round", "")
    competitors, partners, placements = [], {}, {}

    for entry in round_.get("Entries") or []:
        participants = (entry.get("Competitors") or {}).get("Participants", [])
        if not participants:
            continue
        placement = _parse_placement(entry.get("Placement"))
        process_participants(participants, placement, competitors, partners, placements)

    if not competitors:
        return None
    return DanceResult(
        event_id=event_id, event_name=event_name,
        round_id=round_id, round_name=round_name,
        dance_id=round_id, dance_name=f"{round_name} (Combined)",
        session_id=session_id, heat_number=heat_number, time=time_str,
        competitors=competitors, partners=partners, placements=placements,
    )


def _parse_placement(value) -> int | None:
    # Digit-string placements only — "X" (Semi-Final recall) and "" (cut) are
    # not a placement and must not become a phantom int.
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None


def _extract_heat_number(title: str) -> int:
    m = _HEAT_NUMBER_RE.search(title or "")
    return int(m.group(1)) if m else 0
