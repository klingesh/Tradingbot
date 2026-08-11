"""One bot at a time.

Nothing used to stop a second `live_trader.py` from starting, and on a machine
reached by RDP that is easy to do by accident: start the bot, lose the session,
reconnect, and start it again.

It was caught in the wild by an impossible number. The published status showed a
restart counter going 3, 4, 3, 4 -- and a counter cannot decrease. Two processes
had each loaded `state.json` at their own start time, so each held its own copy of
the safety state in memory and overwrote the other's `status.json` on alternating
ticks, thirty seconds apart on a sixty-second poll.

The reporting confusion is the least of it. Both instances evaluate the same
signals against the same account with the same magic number, and each carries its
own drawdown baseline -- so the kill switch is split in two, and neither half sees
the whole loss. A safety limit that two processes disagree about is not a limit.

The lock is taken from the operating system rather than from a PID file. A PID file
has to answer "is that process still alive", which is awkward on Windows and wrong
if the number has been reused; an OS lock is released by the kernel when the holder
dies, however it dies, so a crash cannot leave a stale lock that refuses to let the
bot start again.
"""

from __future__ import annotations

import os
import sys
from typing import Optional, TextIO

LOCK_PATH = "logs/bot.lock"


class AlreadyRunning(RuntimeError):
    """Another instance holds the lock."""


class SingleInstance:
    """Hold an exclusive lock for the life of the process.

    Used as a context manager, or by calling acquire() and simply never releasing
    -- the kernel does that when the process ends.
    """

    def __init__(self, path: str = LOCK_PATH):
        self.path = path
        self._handle: Optional[TextIO] = None

    def acquire(self) -> "SingleInstance":
        folder = os.path.dirname(self.path) or "."
        os.makedirs(folder, exist_ok=True)

        # Opened r+ where possible so an existing lock file is not truncated
        # before we know whether we are allowed to have it -- truncating first
        # would destroy the running instance's recorded pid.
        try:
            handle = open(self.path, "r+", encoding="utf-8")
        except FileNotFoundError:
            handle = open(self.path, "w", encoding="utf-8")

        try:
            _lock(handle)
        except OSError:
            existing = ""
            try:
                handle.seek(0)
                existing = handle.read().strip()
            except Exception:
                pass
            handle.close()
            raise AlreadyRunning(
                "another bot process is already running"
                + (f" (pid {existing})" if existing else "")
                + f". Stop it before starting another, or delete {self.path} only "
                  "if you are certain nothing is running.")

        try:
            handle.seek(0)
            handle.truncate()
            handle.write(str(os.getpid()))
            handle.flush()
        except Exception:
            pass          # the lock is what matters; the pid is a courtesy

        self._handle = handle
        return self

    def release(self) -> None:
        if self._handle is None:
            return
        try:
            _unlock(self._handle)
        except Exception:
            pass
        try:
            self._handle.close()
        except Exception:
            pass
        self._handle = None

    def __enter__(self) -> "SingleInstance":
        return self.acquire()

    def __exit__(self, *_exc) -> None:
        self.release()


# --- platform specifics -----------------------------------------------------
if sys.platform == "win32":                          # pragma: no cover
    import msvcrt

    def _lock(handle: TextIO) -> None:
        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)

    def _unlock(handle: TextIO) -> None:
        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
else:
    import fcntl

    def _lock(handle: TextIO) -> None:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)

    def _unlock(handle: TextIO) -> None:
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
