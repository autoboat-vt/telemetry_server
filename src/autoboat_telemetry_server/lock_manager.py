"""Centralized lock manager with reader-writer locks for Flask endpoints."""

import threading
from collections.abc import Callable
from functools import wraps
from typing import ParamSpec, TypeVar

from flask import Response, jsonify

P = ParamSpec("P")
FlaskReturn = Response | tuple[Response, int]
R = TypeVar("R", bound=FlaskReturn)


class ReaderWriterLock:
    """A fair reader-writer lock."""

    def __init__(self) -> None:
        self._cond = threading.Condition(threading.Lock())
        self._readers = 0
        self._writer = False

    def acquire_read(self) -> None:
        with self._cond:
            while self._writer:
                self._cond.wait()
            self._readers += 1

    def release_read(self) -> None:
        with self._cond:
            self._readers -= 1
            if self._readers == 0:
                self._cond.notify_all()

    def acquire_write(self, *, blocking: bool = True) -> bool:
        acquired = self._cond.acquire(blocking)
        if not acquired:
            return False

        while self._writer or self._readers > 0:
            if not blocking:
                self._cond.release()
                return False
            self._cond.wait()

        self._writer = True
        return True

    def release_write(self) -> None:
        self._writer = False
        self._cond.notify_all()
        self._cond.release()


class LockManager:
    """Thread-safe lock manager for Flask endpoints."""

    def __init__(self) -> None:
        self._rw_lock = ReaderWriterLock()

    def require_read_lock(self, func: Callable[P, R]) -> Callable[P, R]:
        @wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            lock_manager = getattr(args[0], "_lock_manager", None) if args else None
            if lock_manager:
                lock_manager._rw_lock.acquire_read()
                try:
                    return func(*args, **kwargs)
                finally:
                    lock_manager._rw_lock.release_read()
            return func(*args, **kwargs)

        return wrapper

    def require_write_lock(self, func: Callable[P, R]) -> Callable[P, R]:
        @wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            lock_manager = getattr(args[0], "_lock_manager", None) if args else None
            if not lock_manager:
                return func(*args, **kwargs)

            if not lock_manager._rw_lock.acquire_write(blocking=False):
                return jsonify("Write operation in progress. Please try again later."), 429

            try:
                return func(*args, **kwargs)
            finally:
                lock_manager._rw_lock.release_write()

        return wrapper
