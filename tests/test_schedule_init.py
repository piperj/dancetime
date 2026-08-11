from types import SimpleNamespace
from unittest.mock import patch

import schedule


def test_run_prints_status(tmp_path, capsys):
    args = SimpleNamespace(data_dir=str(tmp_path))
    with patch("schedule.NDCAClient"), \
         patch("schedule.refresh_calendar", return_value={"competitions": []}), \
         patch("schedule.is_comp_active", return_value=(True, 42)), \
         patch("schedule.should_run", return_value=True):
        schedule.run(args)
    out = capsys.readouterr().out
    assert "active=True" in out
    assert "cyi=42" in out
    assert "should_run=True" in out


def test_run_inactive_no_cyi(tmp_path, capsys):
    args = SimpleNamespace(data_dir=str(tmp_path))
    with patch("schedule.NDCAClient"), \
         patch("schedule.refresh_calendar", return_value={"competitions": []}), \
         patch("schedule.is_comp_active", return_value=(False, None)), \
         patch("schedule.should_run", return_value=False):
        schedule.run(args)
    out = capsys.readouterr().out
    assert "active=False" in out
    assert "cyi=None" in out
    assert "should_run=False" in out
