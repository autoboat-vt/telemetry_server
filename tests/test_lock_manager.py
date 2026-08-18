"""
Tests for ``autoboat_telemetry_server.lock_manager``.

Covers:
- ``ReaderWriterLock`` concurrency semantics (read/read, read/write,
  write/write exclusion, non-blocking write acquisition).
- ``LockManager.require_read_lock`` (blocking reader decorator).
- ``LockManager.require_write_lock`` (non-blocking writer decorator,
  returns HTTP 429 on contention).

The reader-writer lock is the correctness backbone for SQLite + a single
Gunicorn worker (#3.6). Breaking its semantics would silently corrupt data
in production, so the exclusion properties are tested explicitly.
"""

from __future__ import annotations

import threading

import pytest
from flask import Flask

from autoboat_telemetry_server.lock_manager import LockManager, ReaderWriterLock

# --------------------------------------------------------------------------- #
# ReaderWriterLock -- low-level lock semantics
# --------------------------------------------------------------------------- #


class TestReaderWriterLock:
    """Direct tests of the ``ReaderWriterLock`` primitive."""

    def test_multiple_readers_can_hold_simultaneously(self) -> None:
        """Readers don't block each other (the whole point of a RW lock)."""

        lock = ReaderWriterLock()
        lock.acquire_read()
        lock.acquire_read()
        lock.acquire_read()
        # if we got here, three readers coexisted
        lock.release_read()
        lock.release_read()
        lock.release_read()

    def test_write_excludes_read(self) -> None:
        """A writer blocks readers until released."""

        lock = ReaderWriterLock()
        lock.acquire_write()

        acquired = []

        def try_read() -> None:
            lock.acquire_read()
            acquired.append(True)
            lock.release_read()

        t = threading.Thread(target=try_read)
        t.start()
        t.join(timeout=0.2)
        # the reader should still be waiting
        assert not acquired
        lock.release_write()
        t.join(timeout=1.0)
        assert acquired

    def test_read_excludes_write(self) -> None:
        """A reader blocks writers until released."""

        lock = ReaderWriterLock()
        lock.acquire_read()

        acquired = []

        def try_write() -> None:
            got = lock.acquire_write(blocking=True)
            if got:
                acquired.append(True)
                lock.release_write()

        t = threading.Thread(target=try_write)
        t.start()
        t.join(timeout=0.2)
        assert not acquired
        lock.release_read()
        t.join(timeout=1.0)
        assert acquired

    def test_write_excludes_write(self) -> None:
        """Only one writer at a time."""

        lock = ReaderWriterLock()
        lock.acquire_write()

        acquired = []

        def try_write() -> None:
            got = lock.acquire_write(blocking=True)
            if got:
                acquired.append(True)
                lock.release_write()

        t = threading.Thread(target=try_write)
        t.start()
        t.join(timeout=0.2)
        assert not acquired
        lock.release_write()
        t.join(timeout=1.0)
        assert acquired

    def test_non_blocking_write_returns_false_when_busy(self) -> None:
        """``acquire_write(blocking=False)`` returns False immediately if held."""

        lock = ReaderWriterLock()
        lock.acquire_write()
        assert lock.acquire_write(blocking=False) is False
        lock.release_write()

    def test_non_blocking_write_returns_false_when_reader_holds(self) -> None:
        lock = ReaderWriterLock()
        lock.acquire_read()
        assert lock.acquire_write(blocking=False) is False
        lock.release_read()

    def test_non_blocking_write_succeeds_when_free(self) -> None:
        lock = ReaderWriterLock()
        assert lock.acquire_write(blocking=False) is True
        lock.release_write()

    def test_release_write_unblocks_waiting_writer(self) -> None:
        """Releasing a writer wakes a blocked writer."""

        lock = ReaderWriterLock()
        lock.acquire_write()

        results: list[bool] = []

        def writer() -> None:
            results.append(lock.acquire_write(blocking=True))
            if results[-1]:
                lock.release_write()

        t = threading.Thread(target=writer)
        t.start()
        t.join(timeout=0.2)
        assert not results
        lock.release_write()
        t.join(timeout=1.0)
        assert results == [True]


# --------------------------------------------------------------------------- #
# LockManager decorators -- require_read_lock / require_write_lock
# --------------------------------------------------------------------------- #


class TestRequireReadLock:
    """``require_read_lock`` wraps a function and releases the lock on return."""

    def test_reader_decorator_runs_function(self, app: Flask) -> None:
        """The decorated function executes and returns its value.

        ``require_write_lock`` calls ``jsonify`` on the 429 path, so we need
        a Flask app context for both decorators even when testing reads.
        """

        lm = LockManager()

        @lm.require_read_lock
        def get_value() -> str:
            return "hello"

        assert get_value() == "hello"

    def test_reader_decorator_releases_lock(self, app: Flask) -> None:
        """After a read, a write must be immediately acquirable."""

        lm = LockManager()

        @lm.require_read_lock
        def reader() -> None:
            pass

        reader()
        # if the read lock wasn't released, this non-blocking write fails
        assert lm._rw_lock.acquire_write(blocking=False) is True
        lm._rw_lock.release_write()

    def test_reader_decorator_releases_lock_on_exception(self, app: Flask) -> None:
        lm = LockManager()

        @lm.require_read_lock
        def raising_reader() -> None:
            raise ValueError("boom")

        with pytest.raises(ValueError, match="boom"):
            raising_reader()

        # lock must be released even though the function raised
        assert lm._rw_lock.acquire_write(blocking=False) is True
        lm._rw_lock.release_write()

    def test_concurrent_readers_dont_block(self, app: Flask) -> None:
        """Multiple decorated readers run concurrently without deadlock."""

        lm = LockManager()
        barrier = threading.Barrier(3)
        results: list[str] = []

        @lm.require_read_lock
        def reader(idx: int) -> int:
            barrier.wait(timeout=2.0)
            results.append(f"reader-{idx}")
            return idx

        threads = [threading.Thread(target=reader, args=(i,)) for i in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=2.0)

        assert len(results) == 3


class TestRequireWriteLock:
    """``require_write_lock`` is non-blocking and returns 429 on contention."""

    def test_write_decorator_runs_function(self, app: Flask) -> None:
        lm = LockManager()

        @lm.require_write_lock
        def writer() -> str:
            return "ok"

        assert writer() == "ok"

    def test_write_decorator_releases_lock(self, app: Flask) -> None:
        lm = LockManager()

        @lm.require_write_lock
        def writer() -> None:
            pass

        writer()
        assert lm._rw_lock.acquire_write(blocking=False) is True
        lm._rw_lock.release_write()

    def test_write_decorator_releases_lock_on_exception(self, app: Flask) -> None:
        lm = LockManager()

        @lm.require_write_lock
        def raising_writer() -> None:
            raise RuntimeError("fail")

        with pytest.raises(RuntimeError, match="fail"):
            raising_writer()

        assert lm._rw_lock.acquire_write(blocking=False) is True
        lm._rw_lock.release_write()

    def test_returns_429_when_lock_held(self, app: Flask) -> None:
        """When the lock is held, the decorator returns the 429 response."""

        lm = LockManager()
        # hold the write lock manually so the decorator can't acquire it
        assert lm._rw_lock.acquire_write(blocking=False) is True

        @lm.require_write_lock
        def writer() -> str:
            return "should not run"

        response, status = writer()
        assert status == 429
        # the response is a Flask Response wrapping the retry-later message
        assert b"Write operation in progress" in response.data
        assert b"try again later" in response.data

        lm._rw_lock.release_write()

    def test_write_blocks_readers_temporarily(self, app: Flask) -> None:
        """While a writer holds the lock, a reader waits, then proceeds."""

        lm = LockManager()
        lm._rw_lock.acquire_write()

        reader_results: list[str] = []

        @lm.require_read_lock
        def reader() -> str:
            reader_results.append("done")
            return "done"

        t = threading.Thread(target=reader)
        t.start()
        t.join(timeout=0.2)
        assert not reader_results  # still waiting

        lm._rw_lock.release_write()
        t.join(timeout=2.0)
        assert reader_results == ["done"]


# --------------------------------------------------------------------------- #
# Fairness / integration-ish tests
# --------------------------------------------------------------------------- #


class TestLockFairness:
    """The lock is documented as "fair". We test the basic progress property:
    a waiting writer eventually acquires the lock once readers drain.
    """

    def test_writer_progresses_after_readers_release(self, app: Flask) -> None:
        lock = ReaderWriterLock()

        # two readers acquire the lock
        lock.acquire_read()
        lock.acquire_read()

        writer_acquired: list[bool] = []

        def writer() -> None:
            got = lock.acquire_write(blocking=True)
            writer_acquired.append(got)
            if got:
                lock.release_write()

        t = threading.Thread(target=writer)
        t.start()
        t.join(timeout=0.2)
        assert not writer_acquired

        lock.release_read()
        t.join(timeout=0.2)
        # still one reader holding
        assert not writer_acquired

        lock.release_read()
        t.join(timeout=2.0)
        assert writer_acquired == [True]
