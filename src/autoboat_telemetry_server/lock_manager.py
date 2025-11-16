"""Centralized lock manager for thread-safe database operations across all endpoints."""

import threading
from typing import Any
from collections.abc import Callable
from functools import wraps
from flask import Response, jsonify
from typing import Literal


class LockManager:
    """
    Manages read-write locks for thread-safe database operations.

    Uses a combination of RLock (allowing recursive locking for reads) and
    a separate write lock to ensure:
    - Multiple concurrent reads are allowed
    - Writes get exclusive access (no reads or other writes)
    - Cleanup operations block all other operations
    """

    def __init__(self) -> None:
        self._rw_lock = threading.RLock()
        self._write_lock = threading.Lock()

    @staticmethod
    def require_read_lock(func: Callable[..., Any]) -> Callable[..., Any]:
        """
        Decorator for read operations. Allows concurrent reads.

        Parameters
        ----------
        func
            The function to decorate.

        Returns
        -------
        Callable
            The wrapped function with read lock protection.
        """

        @wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            if args and hasattr(args[0], "_lock_manager"):
                lock_manager = args[0]._lock_manager
                with lock_manager._rw_lock:
                    return func(*args, **kwargs)
            return func(*args, **kwargs)

        return wrapper

    @staticmethod
    def require_write_lock(func: Callable[..., Any]) -> Callable[..., Any]:
        """
        Decorator for write operations. Gets exclusive access.

        Parameters
        ----------
        func
            The function to decorate.

        Returns
        -------
        Callable
            The wrapped function with write lock protection.
        """

        @wraps(func)
        def wrapper(*args, **kwargs) -> tuple[Response, Literal[429]] | Any:
            if args and hasattr(args[0], "_lock_manager"):
                lock_manager = args[0]._lock_manager

                if not lock_manager._write_lock.acquire(blocking=False):
                    return jsonify("Write operation in progress. Please try again later."), 429

                try:
                    with lock_manager._rw_lock:
                        return func(*args, **kwargs)
                finally:
                    lock_manager._write_lock.release()

            return func(*args, **kwargs)

        return wrapper
