from datetime import datetime, timezone
from pathlib import Path

from schedule.active import is_comp_active
from schedule.calendar import load_calendar, refresh_calendar
from schedule.runner import should_run
from scrape.client import NDCAClient


def run(args):
    data_dir = Path(args.data_dir)
    client = NDCAClient()
    calendar = refresh_calendar(data_dir, client)
    now = datetime.now(timezone.utc)
    active, cyi = is_comp_active(calendar, now)
    run_now = should_run(data_dir, now)
    print(f"schedule: active={active}, cyi={cyi}, should_run={run_now}")
