"""
Pytest configuration and shared fixtures.

The package's ``__init__.py`` discovers the instance directory at import time
by scanning ``/home`` for user directories (it expects exactly one entry in
``/home`` and uses it as ``HOME_DIR``, then derives
``INSTANCE_DIR = HOME_DIR / "telemetry_server" / "src" / "instance"``).

On macOS (and any non-Linux dev machine) ``/home`` is empty or missing, so the
import raises ``RuntimeError``. This conftest monkeypatches
``pathlib.Path.iterdir`` to return a fake ``/home`` listing pointing at the
repo's parent directory before the package is imported, so the tests can run
anywhere. The repo's parent directory contains ``telemetry_server/src/instance``
(the real, checked-in ``config.py``), which satisfies the discovery logic.

Per-test isolation is provided by the ``app`` fixture, which monkeypatches
``INSTANCE_DIR`` to a temp directory (with a copy of ``config.py``) so the
SQLite DBs are created in a tmp_path and dropped after each test.
"""

from __future__ import annotations

import importlib
import shutil
import sys
from collections.abc import Generator, Iterator
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from flask import Flask
from flask.testing import FlaskClient
from flask_sqlalchemy.session import Session
from sqlalchemy.orm import scoped_session

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_INSTANCE = REPO_ROOT / "src" / "instance"
# The package computes INSTANCE_DIR = HOME_DIR / "telemetry_server" / "src" / "instance".
# For that to resolve to the repo's src/instance, HOME_DIR must be the repo's parent.
FAKE_HOME = REPO_ROOT.parent


def _bootstrap_package_import() -> None:
    """Make ``autoboat_telemetry_server`` importable off macOS.

    Patches ``Path.iterdir`` so that ``Path("/home").iterdir()`` returns the
    repo's parent directory (a real, existing directory) as the sole ``/home``
    entry. ``is_dir()`` then returns True naturally, and the downstream
    ``INSTANCE_DIR = HOME_DIR / "telemetry_server" / "src" / "instance"``
    resolves to the repo's checked-in ``src/instance/config.py``.
    """

    if "autoboat_telemetry_server" in sys.modules:
        return

    original_iterdir = Path.iterdir

    def patched_iterdir(self: Path) -> Iterator[Path]:
        if self == Path("/home"):
            return iter([FAKE_HOME])
        return original_iterdir(self)

    with patch.object(Path, "iterdir", patched_iterdir):
        importlib.import_module("autoboat_telemetry_server")


_bootstrap_package_import()


@pytest.fixture
def tmp_instance_dir(tmp_path: Path) -> Iterator[Path]:
    """Provide a fresh temp instance dir with a config.py for each test.

    Yields the temp directory path. The caller should point the Flask app
    config at this directory. Tests that need a DB should use the ``app``
    fixture, which wires this up automatically.
    """

    instance_dir = tmp_path / "instance"
    instance_dir.mkdir()
    shutil.copy(SRC_INSTANCE / "config.py", instance_dir / "config.py")
    return instance_dir


@pytest.fixture
def app(tmp_instance_dir: Path) -> Generator[Flask, Any, None]:
    """Build a Flask app instance whose INSTANCE_DIR is the temp dir.

    The app factory reads ``INSTANCE_DIR`` at module import time, so we
    monkeypatch the module attribute and reload the config. SQLite DBs are
    created inside the temp dir and dropped after the test.
    """

    import autoboat_telemetry_server as ats
    from autoboat_telemetry_server.models import db

    original_instance_dir = ats.INSTANCE_DIR
    ats.INSTANCE_DIR = tmp_instance_dir

    flask_app = ats.create_app()
    flask_app.config.update(TESTING=True)

    with flask_app.app_context():
        db.create_all()
        yield flask_app
        db.session.remove()
        db.drop_all()

    ats.INSTANCE_DIR = original_instance_dir


@pytest.fixture
def client(app: Flask) -> FlaskClient:
    """A Flask test client backed by the ``app`` fixture."""

    return app.test_client()


@pytest.fixture
def db_session(app: Flask) -> scoped_session[Session]:
    """A SQLAlchemy session bound to the test app's app context."""

    from autoboat_telemetry_server.models import db

    return db.session
