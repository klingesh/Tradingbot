"""Only one bot may run at a time.

Caught in the wild by an impossible number: the published restart counter went
3, 4, 3, 4. Two processes had each loaded state.json at their own start time, so
each held its own safety state and overwrote the other's status.json on alternating
ticks. Both were trading the same account, each with its own drawdown baseline --
a kill switch split in half sees neither side of the loss.
"""

from __future__ import annotations

import os

import pytest

from src.live.lock import AlreadyRunning, SingleInstance


def test_the_first_instance_gets_the_lock(tmp_path):
    lock = SingleInstance(str(tmp_path / "bot.lock"))
    lock.acquire()
    try:
        assert os.path.exists(lock.path)
    finally:
        lock.release()


def test_the_second_instance_is_refused(tmp_path):
    """The bug: nothing used to stop this."""
    path = str(tmp_path / "bot.lock")
    first = SingleInstance(path).acquire()
    try:
        with pytest.raises(AlreadyRunning):
            SingleInstance(path).acquire()
    finally:
        first.release()


def test_the_refusal_says_what_to_do(tmp_path):
    path = str(tmp_path / "bot.lock")
    first = SingleInstance(path).acquire()
    try:
        try:
            SingleInstance(path).acquire()
            raise AssertionError("should have been refused")
        except AlreadyRunning as exc:
            message = str(exc)
        assert "already running" in message
        assert "Stop it before starting another" in message
        assert path in message, "say which file, so it can be cleared if stale"
    finally:
        first.release()


def test_the_pid_is_recorded(tmp_path):
    path = str(tmp_path / "bot.lock")
    lock = SingleInstance(path).acquire()
    try:
        assert open(path, encoding="utf-8").read().strip() == str(os.getpid())
    finally:
        lock.release()


def test_releasing_lets_the_next_one_in(tmp_path):
    """A restart must not be blocked by the instance it is replacing."""
    path = str(tmp_path / "bot.lock")
    SingleInstance(path).acquire().release()
    second = SingleInstance(path).acquire()
    try:
        assert second._handle is not None
    finally:
        second.release()


def test_a_leftover_lock_file_does_not_block_startup(tmp_path):
    """The reason this uses an OS lock and not a pid file.

    A pid file left behind by a crash has to be validated -- awkward on Windows,
    and wrong if the number has been reused. A kernel lock is dropped when the
    holder dies however it dies, so a stale *file* is harmless.
    """
    path = tmp_path / "bot.lock"
    path.write_text("999999", encoding="utf-8")

    lock = SingleInstance(str(path)).acquire()
    try:
        assert open(path, encoding="utf-8").read().strip() == str(os.getpid())
    finally:
        lock.release()


def test_an_existing_lock_file_is_not_truncated_before_we_win_it(tmp_path):
    """Otherwise a refused second start would erase the running instance's pid."""
    path = str(tmp_path / "bot.lock")
    first = SingleInstance(path).acquire()
    try:
        recorded = open(path, encoding="utf-8").read().strip()
        try:
            SingleInstance(path).acquire()
        except AlreadyRunning:
            pass
        assert open(path, encoding="utf-8").read().strip() == recorded
    finally:
        first.release()


def test_it_works_as_a_context_manager(tmp_path):
    path = str(tmp_path / "bot.lock")
    with SingleInstance(path):
        with pytest.raises(AlreadyRunning):
            SingleInstance(path).acquire()
    # released on exit
    SingleInstance(path).acquire().release()


def test_the_log_directory_is_created_if_missing(tmp_path):
    path = str(tmp_path / "nested" / "deeper" / "bot.lock")
    lock = SingleInstance(path).acquire()
    try:
        assert os.path.exists(path)
    finally:
        lock.release()


def test_release_is_safe_to_call_twice(tmp_path):
    lock = SingleInstance(str(tmp_path / "bot.lock")).acquire()
    lock.release()
    lock.release()          # must not raise
