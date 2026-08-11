"""Publish the bot's status to a private GitHub repo.

The bot runs on a VPS; whatever watches it does not. There is no way to read
`logs/status.json` across that gap, so this pushes it somewhere both can reach.

GitHub is the transport for three practical reasons: nothing has to be opened on
the VPS firewall, no new service has to be run or paid for, and the result is
readable from a phone. It is not a clever choice, it is the one with the fewest
moving parts.

**This runs as its own process, never inside the trading loop.** A network call
that hangs would delay a tick, and monitoring must not be able to interfere with
the thing it monitors. Start it beside the bot with scripts/run_publisher.bat.

Publishing is time-based with an override: every `interval_seconds` normally, but
immediately when something worth knowing changes -- a halt, a new error, a
position opening or closing, a restart. Pushing every 60-second heartbeat would
mean 1,440 commits a day to say nothing at all.

Setup: copy config/publish.example.yaml to config/publish.yaml (gitignored) and
fill in a private repo and a token scoped to it.
"""

from __future__ import annotations

import argparse
import base64
import json
import logging
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from typing import Any, Dict, Optional, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

STATUS_PATH = "logs/status.json"
CONFIG_PATH = "config/publish.yaml"
LOG_PATH = "logs/publisher.log"
API = "https://api.github.com"
_UA = "tradingbot-status-publisher"

log = logging.getLogger("publisher")


# --- configuration ----------------------------------------------------------
def load_config(path: str = CONFIG_PATH) -> Dict[str, Any]:
    """Read publisher settings from YAML, with environment overrides.

    Environment variables win so the token need never be written to disk on a
    shared or snapshotted machine.
    """
    cfg: Dict[str, Any] = {
        "repo": "", "token": "", "branch": "main",
        "status_file": "status.json", "readme_file": "STATUS.md",
        "interval_seconds": 300,
    }
    try:
        import yaml

        with open(path, encoding="utf-8") as f:
            loaded = yaml.safe_load(f) or {}
        cfg.update({k: v for k, v in loaded.items() if v is not None})
    except FileNotFoundError:
        pass
    except Exception as exc:
        log.warning("could not read %s: %s", path, exc)

    cfg["repo"] = os.environ.get("STATUS_REPO", cfg["repo"]).strip()
    cfg["token"] = os.environ.get("STATUS_TOKEN", cfg["token"]).strip()
    cfg["interval_seconds"] = int(cfg.get("interval_seconds") or 300)
    return cfg


# --- GitHub -----------------------------------------------------------------
def _request(url: str, token: str, method: str = "GET",
             payload: Optional[Dict[str, Any]] = None) -> Tuple[int, Any]:
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=body, method=method, headers={
        "User-Agent": _UA,
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28",
        "Content-Type": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read()
            return resp.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as exc:
        detail = None
        try:
            detail = json.loads(exc.read() or b"{}")
        except Exception:
            pass
        return exc.code, detail


def current_sha(repo: str, path: str, branch: str, token: str) -> Optional[str]:
    """The blob sha of the file as it stands, or None if it isn't there yet.

    Updating a file through the Contents API requires the sha it is replacing;
    creating one requires that the sha be absent. Getting this wrong is the usual
    cause of a 409.
    """
    status, body = _request(
        f"{API}/repos/{repo}/contents/{path}?ref={branch}", token)
    if status == 200 and isinstance(body, dict):
        return body.get("sha")
    return None


def put_file(repo: str, path: str, content: bytes, message: str, branch: str,
             token: str, sha: Optional[str]) -> Tuple[bool, str]:
    payload: Dict[str, Any] = {
        "message": message,
        "content": base64.b64encode(content).decode("ascii"),
        "branch": branch,
    }
    if sha:
        payload["sha"] = sha
    status, body = _request(f"{API}/repos/{repo}/contents/{path}", token,
                            method="PUT", payload=payload)
    if status in (200, 201):
        return True, "ok"
    reason = ""
    if isinstance(body, dict):
        reason = str(body.get("message") or "")
    return False, f"HTTP {status}{': ' + reason if reason else ''}"


# --- what counts as news ----------------------------------------------------
def significant(status: Dict[str, Any]) -> Tuple:
    """The fields whose change justifies an immediate push.

    Deliberately excludes the heartbeat and equity. Both move every cycle, so
    including them would make every poll 'significant' and produce 1,440 commits a
    day that say nothing. These are the things you would want to be told about
    within the minute.
    """
    return (
        bool(status.get("halted")),
        bool(status.get("day_halted")),
        bool(status.get("new_entries_blocked")),
        int(status.get("open_count") or 0),
        int(status.get("restarts") or 0),
        len(status.get("recent_errors") or []),
        bool(status.get("dry_run")),
    )


def render_markdown(status: Dict[str, Any]) -> str:
    """A human-readable status page, for reading on a phone.

    The JSON is what the monitor parses; this is what a person opens in the GitHub
    app when they want to know whether anything is wrong.
    """
    halted = status.get("halted")
    blocked = status.get("new_entries_blocked")
    if halted:
        headline = "HALTED - kill switch fired"
    elif blocked:
        headline = "TRADING PAUSED - no new entries"
    else:
        headline = "Running"

    dd = status.get("drawdown_percent", 0.0)
    limit = status.get("drawdown_limit_percent", 0.0)
    day_dd = status.get("day_drawdown_percent", 0.0)
    day_limit = status.get("day_loss_limit_percent", 0.0)
    currency = status.get("currency", "")

    lines = [
        f"# {headline}",
        "",
        f"_Heartbeat: {status.get('heartbeat', 'unknown')}_",
        "",
        "| | |",
        "| --- | --- |",
        f"| Equity | {status.get('equity', 0):,.2f} {currency} |",
        f"| Balance | {status.get('balance', 0):,.2f} {currency} |",
        f"| Peak equity | {status.get('peak_equity') or 0:,.2f} {currency} |",
        f"| Drawdown | {dd:.2f}% of {limit:.2f}% limit |",
        f"| Today | {day_dd:.2f}% of {day_limit:.2f}% limit |",
        f"| Open positions | {status.get('open_count', 0)} |",
        f"| Mode | {'DRY RUN' if status.get('dry_run') else 'live orders'} |",
        f"| Restarts | {status.get('restarts', 0)} |",
    ]

    if halted:
        lines += ["", f"**Halted at {status.get('halted_at', '')}** — "
                      f"{status.get('halt_reason', '')}",
                  "", "Delete `logs/state.json` on the VPS to clear it, but "
                      "understand why it fired first."]

    positions = status.get("open_positions") or []
    if positions:
        lines += ["", "## Open positions", "",
                  "| Symbol | Side | Lots | Profit |", "| --- | --- | --- | --- |"]
        for p in positions:
            lines.append(
                f"| {p.get('symbol','')} | {p.get('side','')} | "
                f"{p.get('lots',0)} | {p.get('profit',0):,.2f} |")

    errors = status.get("recent_errors") or []
    if errors:
        lines += ["", "## Recent problems", ""]
        for e in errors[-5:]:
            lines.append(f"- `{e.get('at','')}` **{e.get('where','')}** — "
                         f"{e.get('message','')}")

    lines += ["", "---", "",
              "Published automatically by `scripts/publish_status.py`. "
              "Read-only: nothing here can place, close or modify a trade."]
    return "\n".join(lines) + "\n"


# --- the loop ---------------------------------------------------------------
def read_status(path: str = STATUS_PATH) -> Optional[Dict[str, Any]]:
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        log.warning("%s not found -- is the bot running?", path)
    except Exception as exc:
        # A partially-written file is possible in principle; the bot writes
        # atomically, but a retry next cycle costs nothing.
        log.debug("could not read %s: %s", path, exc)
    return None


def publish_once(cfg: Dict[str, Any], status: Dict[str, Any]) -> bool:
    repo, token, branch = cfg["repo"], cfg["token"], cfg["branch"]
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")
    state = ("HALTED" if status.get("halted")
             else "paused" if status.get("new_entries_blocked") else "running")
    message = f"status {stamp} — {state}, equity {status.get('equity', 0):,.2f}"

    ok = True
    for path, content in (
        (cfg["status_file"], json.dumps(status, indent=2,
                                        sort_keys=True).encode("utf-8")),
        (cfg["readme_file"], render_markdown(status).encode("utf-8")),
    ):
        sha = current_sha(repo, path, branch, token)
        good, why = put_file(repo, path, content, message, branch, token, sha)
        if not good:
            log.error("publishing %s failed: %s", path, why)
            ok = False
    return ok


def _setup_logging() -> None:
    handlers: list[logging.Handler] = [logging.StreamHandler()]
    try:
        os.makedirs(os.path.dirname(LOG_PATH) or ".", exist_ok=True)
        handlers.append(RotatingFileHandler(LOG_PATH, maxBytes=1_000_000,
                                            backupCount=3, encoding="utf-8"))
    except Exception:
        pass
    logging.basicConfig(
        level=logging.INFO, force=True, handlers=handlers,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Publish bot status to GitHub.")
    parser.add_argument("--once", action="store_true",
                        help="publish a single snapshot and exit")
    parser.add_argument("--dry-run", action="store_true",
                        help="show what would be published, send nothing")
    args = parser.parse_args(argv)

    _setup_logging()
    cfg = load_config()

    if args.dry_run:
        status = read_status()
        if status is None:
            print("No status.json -- start the bot first.")
            return 1
        print(render_markdown(status))
        print(f"Would publish to: {cfg['repo'] or '(no repo configured)'}")
        return 0

    if not cfg["repo"] or not cfg["token"]:
        print("Not configured. Copy config/publish.example.yaml to "
              "config/publish.yaml and set repo and token,")
        print("or set STATUS_REPO and STATUS_TOKEN in the environment.")
        return 1

    log.info("Publishing %s to %s every %ss (immediately on a halt or error).",
             STATUS_PATH, cfg["repo"], cfg["interval_seconds"])

    last_pushed = 0.0
    last_significant: Optional[Tuple] = None
    backoff = 0

    while True:
        status = read_status()
        if status is not None:
            marks = significant(status)
            due = (time.time() - last_pushed) >= cfg["interval_seconds"]
            changed = last_significant is not None and marks != last_significant
            first = last_significant is None

            if due or changed or first:
                if changed:
                    log.info("Something changed -- publishing now.")
                if publish_once(cfg, status):
                    last_pushed = time.time()
                    last_significant = marks
                    backoff = 0
                else:
                    # Never spin on a failing API: back off, but keep the last
                    # known-good marks so a real change still forces a retry.
                    backoff = min(backoff * 2 or 60, 900)
                    log.warning("Retrying in %ss.", backoff)
                    time.sleep(backoff)
                    continue

        if args.once:
            return 0
        time.sleep(30)


if __name__ == "__main__":
    raise SystemExit(main())
