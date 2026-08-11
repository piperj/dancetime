from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import cal


def _args(tmp_path, no_browser=True):
    return SimpleNamespace(data_dir=str(tmp_path), port=7331, no_browser=no_browser)


def test_run_refreshes_calendar_and_serves(tmp_path):
    mock_httpd = MagicMock()
    mock_httpd.serve_forever.side_effect = KeyboardInterrupt()
    with patch("cal.refresh_calendar") as mock_refresh, \
         patch("cal.NDCAClient"), \
         patch("cal.make_handler", return_value=object()), \
         patch("cal.ThreadingHTTPServer", return_value=mock_httpd), \
         patch("cal.webbrowser.open") as mock_open:
        cal.run(_args(tmp_path, no_browser=True))
    mock_refresh.assert_called_once()
    mock_httpd.serve_forever.assert_called_once()
    mock_open.assert_not_called()


def test_run_opens_browser_when_not_suppressed(tmp_path):
    mock_httpd = MagicMock()
    mock_httpd.serve_forever.side_effect = KeyboardInterrupt()
    with patch("cal.refresh_calendar"), \
         patch("cal.NDCAClient"), \
         patch("cal.make_handler", return_value=object()), \
         patch("cal.ThreadingHTTPServer", return_value=mock_httpd), \
         patch("cal.threading.Timer") as mock_timer:
        cal.run(_args(tmp_path, no_browser=False))
    mock_timer.assert_called_once()
    assert mock_timer.call_args[0][0] == 0.3


def test_run_handles_refresh_calendar_failure(tmp_path, capsys):
    mock_httpd = MagicMock()
    mock_httpd.serve_forever.side_effect = KeyboardInterrupt()
    with patch("cal.refresh_calendar", side_effect=RuntimeError("boom")), \
         patch("cal.NDCAClient"), \
         patch("cal.make_handler", return_value=object()), \
         patch("cal.ThreadingHTTPServer", return_value=mock_httpd), \
         patch("cal.webbrowser.open"):
        cal.run(_args(tmp_path, no_browser=True))
    out = capsys.readouterr().out
    assert "could not refresh calendar" in out
    assert "boom" in out


def test_run_keyboard_interrupt_prints_stopped(tmp_path, capsys):
    mock_httpd = MagicMock()
    mock_httpd.serve_forever.side_effect = KeyboardInterrupt()
    with patch("cal.refresh_calendar"), \
         patch("cal.NDCAClient"), \
         patch("cal.make_handler", return_value=object()), \
         patch("cal.ThreadingHTTPServer", return_value=mock_httpd), \
         patch("cal.webbrowser.open"):
        cal.run(_args(tmp_path, no_browser=True))
    out = capsys.readouterr().out
    assert "calendar: stopped" in out
