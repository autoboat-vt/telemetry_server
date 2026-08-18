"""Tests for the Alembic migration setup (multi-bind).

These tests verify that:
- The migrations directory is wired up and importable.
- The multi-bind env.py iterates over both binds (default + "hashes").
- The initial migration creates both `telemetry_table` (in instances.db)
  and `hash_table` (in hashes.db) when run against fresh DBs.
- The migration round-trips (upgrade then downgrade leaves a clean state).

The conftest bootstraps the /home discovery so the package imports on macOS;
these tests build a fresh app against a temp instance dir and invoke the
Flask-Migrate API directly (the same API the CLI uses).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from conftest import SRC_INSTANCE
from flask import Flask


def _tables_in(db_path: Path) -> list[str]:
    """Return the user table names in a SQLite file (excluding sqlite_*)."""

    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        ).fetchall()
        return [r[0] for r in rows]
    finally:
        conn.close()


@pytest.fixture
def migration_app(tmp_path: Path) -> Flask:
    """Build an app whose INSTANCE_DIR points at a fresh temp dir.

    The temp dir has empty instances.db / hashes.db files. We do NOT call
    db.create_all() (the conftest `app` fixture does, but that would hide
    migration bugs); we want the migration to be the only thing that creates
    tables.
    """

    import autoboat_telemetry_server as ats

    instance_dir = tmp_path / "instance"
    instance_dir.mkdir()
    (instance_dir / "config.py").write_text((SRC_INSTANCE / "config.py").read_text())

    original_instance_dir = ats.INSTANCE_DIR
    # copy the checked-in config.py into the temp instance dir; the app
    # factory resolves the SQLite paths relative to INSTANCE_DIR, so patching
    # INSTANCE_DIR to our temp dir makes the app use fresh DBs
    (instance_dir / "config.py").write_text((SRC_INSTANCE / "config.py").read_text())
    ats.INSTANCE_DIR = instance_dir

    app = ats.create_app()
    app.config.update(TESTING=True)

    yield app

    with app.app_context():
        from autoboat_telemetry_server.models import db

        db.session.remove()
        db.drop_all()

    ats.INSTANCE_DIR = original_instance_dir


class TestMigrationWiring:
    """The migrations directory and Alembic config are present and importable."""

    def test_migrations_directory_exists(self) -> None:
        from autoboat_telemetry_server import create_app

        app = create_app()
        migrate_dir = app.extensions["migrate"].directory
        assert Path(migrate_dir).is_dir(), f"migrations dir not found: {migrate_dir}"
        assert (Path(migrate_dir) / "env.py").is_file()
        assert (Path(migrate_dir) / "alembic.ini").is_file()

    def test_versions_directory_has_initial_migration(self) -> None:
        from autoboat_telemetry_server import create_app

        app = create_app()
        migrate_dir = Path(app.extensions["migrate"].directory)
        version_files = list((migrate_dir / "versions").glob("*.py"))
        assert len(version_files) >= 1, "no migration versions found"
        # the initial migration should define revision 0001_initial
        initial = next((p for p in version_files if "initial" in p.name), None)
        assert initial is not None, "initial migration file not found"


class TestMultiBindMigration:
    """The initial migration creates both tables in their respective DBs."""

    def test_upgrade_creates_both_tables(self, migration_app: Flask, tmp_path: Path) -> None:
        instances_db = migration_app.config["SQLALCHEMY_BINDS"][None]
        hashes_db = migration_app.config["SQLALCHEMY_BINDS"]["hashes"]
        # extract the file path from the sqlite URI
        instances_path = Path(instances_db.replace("sqlite:///", ""))
        hashes_path = Path(hashes_db.replace("sqlite:///", ""))

        with migration_app.app_context():
            from flask_migrate import upgrade

            upgrade()

        assert "telemetry_table" in _tables_in(instances_path)
        assert "alembic_version" in _tables_in(instances_path)
        assert "hash_table" in _tables_in(hashes_path)
        assert "alembic_version" in _tables_in(hashes_path)

    def test_downgrade_drops_both_tables(self, migration_app: Flask, tmp_path: Path) -> None:
        instances_db = migration_app.config["SQLALCHEMY_BINDS"][None]
        hashes_db = migration_app.config["SQLALCHEMY_BINDS"]["hashes"]
        instances_path = Path(instances_db.replace("sqlite:///", ""))
        hashes_path = Path(hashes_db.replace("sqlite:///", ""))

        with migration_app.app_context():
            from flask_migrate import downgrade, upgrade

            upgrade()
            downgrade()

        # alembic_version persists after downgrade to base, but the data
        # tables should be gone
        assert "telemetry_table" not in _tables_in(instances_path)
        assert "hash_table" not in _tables_in(hashes_path)

    def test_upgrade_is_idempotent_when_run_twice(self, migration_app: Flask, tmp_path: Path) -> None:
        """Running upgrade twice should not error (Alembic tracks state)."""

        with migration_app.app_context():
            from flask_migrate import upgrade

            upgrade()
            upgrade()  # no-op: already at head

        # both tables should still be present
        instances_db = migration_app.config["SQLALCHEMY_BINDS"][None]
        hashes_db = migration_app.config["SQLALCHEMY_BINDS"]["hashes"]
        instances_path = Path(instances_db.replace("sqlite:///", ""))
        hashes_path = Path(hashes_db.replace("sqlite:///", ""))
        assert "telemetry_table" in _tables_in(instances_path)
        assert "hash_table" in _tables_in(hashes_path)
