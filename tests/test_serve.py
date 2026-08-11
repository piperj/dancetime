from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import serve


def _args(tmp_path, no_browser=True, port=7332):
    return SimpleNamespace(root=str(tmp_path), port=port, no_browser=no_browser)


def test_run_serves_and_stops_on_interrupt(tmp_path, capsys):
    mock_httpd = MagicMock()
    mock_httpd.serve_forever.side_effect = KeyboardInterrupt()
    with patch("serve.HTTPServer", return_value=mock_httpd) as mock_server, \
         patch("serve.webbrowser.open") as mock_open:
        serve.run(_args(tmp_path, no_browser=True))
    mock_server.assert_called_once()
    mock_httpd.serve_forever.assert_called_once()
    mock_open.assert_not_called()
    out = capsys.readouterr().out
    assert "serve: stopped" in out


def test_run_opens_browser_when_not_suppressed(tmp_path):
    mock_httpd = MagicMock()
    mock_httpd.serve_forever.side_effect = KeyboardInterrupt()
    with patch("serve.HTTPServer", return_value=mock_httpd), \
         patch("serve.threading.Timer") as mock_timer:
        serve.run(_args(tmp_path, no_browser=False))
    mock_timer.assert_called_once()
    assert mock_timer.call_args[0][0] == 0.3
