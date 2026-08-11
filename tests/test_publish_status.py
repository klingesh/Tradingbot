"""The publisher must be quiet when nothing happens and loud when it does."""

from __future__ import annotations

import json

from scripts.publish_status import (load_config, put_file, render_markdown,
                                    significant)

RUNNING = {
    "heartbeat": "2026-08-11T09:14:02+00:00",
    "equity": 9735.5, "balance": 9735.5, "peak_equity": 10000.0,
    "currency": "USD", "drawdown_percent": 2.65, "drawdown_limit_percent": 20.0,
    "day_drawdown_percent": 0.0, "day_loss_limit_percent": 6.0,
    "halted": False, "day_halted": False, "new_entries_blocked": False,
    "dry_run": False, "open_count": 0, "open_positions": [],
    "restarts": 0, "recent_errors": [],
}


def test_a_heartbeat_alone_is_not_worth_a_commit():
    """Otherwise this makes 1,440 commits a day to say nothing changed."""
    later = dict(RUNNING, heartbeat="2026-08-11T09:15:02+00:00", equity=9740.10)
    assert significant(later) == significant(RUNNING)


def test_a_halt_is_worth_publishing_immediately():
    halted = dict(RUNNING, halted=True, new_entries_blocked=True)
    assert significant(halted) != significant(RUNNING)


def test_so_is_a_position_opening_or_closing():
    opened = dict(RUNNING, open_count=1)
    assert significant(opened) != significant(RUNNING)


def test_so_is_a_new_error_or_a_restart():
    errored = dict(RUNNING, recent_errors=[{"at": "x", "message": "boom"}])
    assert significant(errored) != significant(RUNNING)
    restarted = dict(RUNNING, restarts=1)
    assert significant(restarted) != significant(RUNNING)


def test_so_is_switching_out_of_dry_run():
    """The difference between logging trades and placing them."""
    assert significant(dict(RUNNING, dry_run=True)) != significant(RUNNING)


def test_markdown_leads_with_the_state():
    assert render_markdown(RUNNING).startswith("# Running")
    assert render_markdown(dict(RUNNING, halted=True)).startswith(
        "# HALTED - kill switch fired")
    assert render_markdown(dict(RUNNING, new_entries_blocked=True)).startswith(
        "# TRADING PAUSED")


def test_markdown_shows_drawdown_against_its_limit():
    """A number without its limit doesn't say whether to worry."""
    out = render_markdown(RUNNING)
    assert "2.65% of 20.00% limit" in out
    assert "9,735.50 USD" in out
    assert "10,000.00 USD" in out


def test_markdown_explains_a_halt_and_how_to_clear_it():
    out = render_markdown(dict(
        RUNNING, halted=True, halt_reason="total drawdown 21.00% >= 20.00%",
        halted_at="2026-08-11T02:00:00+00:00"))
    assert "21.00%" in out
    assert "logs/state.json" in out
    assert "understand why it fired first" in out


def test_markdown_lists_open_positions():
    out = render_markdown(dict(RUNNING, open_count=2, open_positions=[
        {"symbol": "XAUUSD.ecn", "side": "buy", "lots": 0.12, "profit": 12.4},
        {"symbol": "AUDUSD.ecn", "side": "sell", "lots": 0.3, "profit": -4.05},
    ]))
    assert "XAUUSD.ecn" in out and "AUDUSD.ecn" in out
    assert "-4.05" in out


def test_markdown_states_it_cannot_trade():
    assert "cannot place, close or modify a trade" in render_markdown(RUNNING) \
        or "nothing here can place, close or modify a trade" in \
        render_markdown(RUNNING)


def test_missing_config_file_is_not_fatal(tmp_path):
    cfg = load_config(str(tmp_path / "absent.yaml"))
    assert cfg["repo"] == ""
    assert cfg["interval_seconds"] == 300
    assert cfg["branch"] == "main"
    assert cfg["status_path"] == "logs/status.json"


def test_the_status_path_is_configurable(tmp_path):
    """It was a default argument bound at import time, so it could not be moved."""
    path = tmp_path / "publish.yaml"
    path.write_text("status_path: D:/elsewhere/status.json\n", encoding="utf-8")
    assert load_config(str(path))["status_path"] == "D:/elsewhere/status.json"


def test_environment_overrides_the_file(tmp_path, monkeypatch):
    """So a token need never be written to disk on a snapshotted VPS."""
    path = tmp_path / "publish.yaml"
    path.write_text("repo: from/file\ntoken: file-token\n", encoding="utf-8")

    monkeypatch.setenv("STATUS_REPO", "from/env")
    monkeypatch.setenv("STATUS_TOKEN", "env-token")
    cfg = load_config(str(path))
    assert cfg["repo"] == "from/env"
    assert cfg["token"] == "env-token"


def test_create_omits_the_sha_and_update_includes_it(monkeypatch):
    """Getting this wrong is the usual cause of a 409 from the Contents API."""
    seen = {}

    def fake_request(url, token, method="GET", payload=None):
        seen["url"] = url
        seen["method"] = method
        seen["payload"] = payload
        return 200, {"content": {}}

    monkeypatch.setattr("scripts.publish_status._request", fake_request)

    put_file("me/status", "status.json", b"{}", "msg", "main", "tok", None)
    assert "sha" not in seen["payload"], "creating must not send a sha"
    assert seen["method"] == "PUT"

    put_file("me/status", "status.json", b"{}", "msg", "main", "tok", "abc123")
    assert seen["payload"]["sha"] == "abc123", "updating must send the sha"


def test_content_is_sent_base64_and_round_trips(monkeypatch):
    import base64

    captured = {}

    def fake_request(url, token, method="GET", payload=None):
        captured.update(payload or {})
        return 201, None

    monkeypatch.setattr("scripts.publish_status._request", fake_request)
    body = json.dumps(RUNNING).encode("utf-8")
    ok, why = put_file("me/status", "status.json", body, "msg", "main", "t", None)

    assert ok is True and why == "ok"
    assert base64.b64decode(captured["content"]) == body


def test_a_failure_reports_the_reason(monkeypatch):
    def fake_request(url, token, method="GET", payload=None):
        return 404, {"message": "Not Found"}

    monkeypatch.setattr("scripts.publish_status._request", fake_request)
    ok, why = put_file("me/nope", "status.json", b"{}", "m", "main", "t", None)
    assert ok is False
    assert "404" in why and "Not Found" in why



# --- how the command-line tool behaves -------------------------------------
# Found by running it: --once said nothing at all on success, retried forever on
# failure, and Ctrl+C printed a traceback over the operator's console.

def _configured(monkeypatch, tmp_path, status=RUNNING, published=True):
    """Point the publisher at a temp status file and stub out the network."""
    import scripts.publish_status as ps

    path = tmp_path / "status.json"
    if status is not None:
        path.write_text(json.dumps(status), encoding="utf-8")

    cfg = {
        "repo": "me/status", "token": "tok", "branch": "main",
        "status_path": str(path), "status_file": "status.json",
        "readme_file": "STATUS.md", "interval_seconds": 300,
    }
    monkeypatch.setattr("scripts.publish_status.load_config", lambda *a: cfg)
    monkeypatch.setattr("scripts.publish_status.LOG_PATH",
                        str(tmp_path / "publisher.log"))
    monkeypatch.setattr("scripts.publish_status.publish_once",
                        lambda c, s: published)
    return ps


def test_once_succeeds_and_stops(tmp_path, monkeypatch):
    ps = _configured(monkeypatch, tmp_path)
    assert ps.main(["--once"]) == 0


def test_once_reports_failure_instead_of_retrying_forever(tmp_path, monkeypatch):
    """It used to `continue` past the --once check and loop until killed."""
    ps = _configured(monkeypatch, tmp_path, published=False)
    assert ps.main(["--once"]) == 1


def test_once_with_no_status_file_is_a_failure(tmp_path, monkeypatch):
    """Exiting 0 would tell a caller it had published when it had not."""
    ps = _configured(monkeypatch, tmp_path, status=None)
    assert ps.main(["--once"]) == 1


def test_a_successful_publish_is_announced(tmp_path, monkeypatch, caplog=None):
    """Silence after publishing left no way to tell whether it had worked."""
    import logging

    ps = _configured(monkeypatch, tmp_path)
    records = []

    class Capture(logging.Handler):
        def emit(self, record):
            records.append(record.getMessage())

    handler = Capture()
    ps.log.addHandler(handler)
    try:
        assert ps.main(["--once"]) == 0
    finally:
        ps.log.removeHandler(handler)

    published = [r for r in records if "Published to me/status" in r]
    assert published, f"no publish confirmation in {records}"
    assert "9735.50" in published[0]
    assert "2.65%" in published[0]
    assert "running" in published[0]


def test_ctrl_c_exits_cleanly(tmp_path, monkeypatch):
    """Ctrl+C is how this is stopped; a traceback is not an acceptable goodbye."""
    ps = _configured(monkeypatch, tmp_path)

    import types as _types

    def interrupt(_seconds):
        raise KeyboardInterrupt

    monkeypatch.setattr("scripts.publish_status.time",
                        _types.SimpleNamespace(sleep=interrupt, time=lambda: 0.0))
    assert ps.main([]) == 0, "KeyboardInterrupt must not propagate"


def test_unconfigured_refuses_with_guidance(tmp_path, monkeypatch):
    import scripts.publish_status as ps

    monkeypatch.setenv("STATUS_REPO", "")
    monkeypatch.setenv("STATUS_TOKEN", "")
    monkeypatch.setattr("scripts.publish_status.CONFIG_PATH",
                        str(tmp_path / "absent.yaml"))
    assert ps.main([]) == 1
