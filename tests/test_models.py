"""
Tests for ``autoboat_telemetry_server.models``.

Covers:
- ``HashTable.compute_hash`` (pure static method: deterministic SHA-256).
- ``HashTable.validate_config`` (pure static method: structural validation).
- ``HashTable.check_hash_exists`` (DB-backed classmethod).
- ``HashTable.to_dict`` (serialization).
- ``TelemetryTable.validate_user`` (the immutability invariant, §3.3).
- ``TelemetryTable.to_dict`` and ``get_all_ids``.
- The ``after_insert`` hook that auto-sets ``instance_identifier`` (§3.5).
"""

from __future__ import annotations

import hashlib
import json

import pytest
from flask import Flask

from autoboat_telemetry_server.models import HashTable, TelemetryTable, db

# --------------------------------------------------------------------------- #
# HashTable.compute_hash -- pure function, no app context needed
# --------------------------------------------------------------------------- #


class TestComputeHash:
    """``compute_hash`` must be deterministic and match the documented formula."""

    def test_returns_sha256_hexdigest(self) -> None:
        config = {"speed": {"default": 1.0, "description": "boat speed"}}
        expected = hashlib.sha256(json.dumps(config, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
        assert HashTable.compute_hash(config) == expected

    def test_is_64_chars_hex(self) -> None:
        h = HashTable.compute_hash({"a": {"default": 1, "description": "x"}})
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)

    def test_key_order_does_not_matter(self) -> None:
        """The hash is computed with sort_keys=True, so key order is irrelevant."""

        config_a = {"speed": {"default": 1.0, "description": "speed"}, "heading": {"default": 0.0, "description": "heading"}}
        config_b = {"heading": {"default": 0.0, "description": "heading"}, "speed": {"default": 1.0, "description": "speed"}}
        assert HashTable.compute_hash(config_a) == HashTable.compute_hash(config_b)

    def test_whitespace_in_values_does_matter(self) -> None:
        """Whitespace inside values changes the serialized JSON, so it changes the hash."""

        a = {"key": {"default": 1, "description": "boat"}}
        b = {"key": {"default": 1, "description": "boat "}}
        assert HashTable.compute_hash(a) != HashTable.compute_hash(b)

    def test_different_configs_different_hash(self) -> None:
        a = {"key": {"default": 1, "description": "x"}}
        b = {"key": {"default": 2, "description": "x"}}
        assert HashTable.compute_hash(a) != HashTable.compute_hash(b)

    def test_empty_dict_hash_is_stable(self) -> None:
        """The empty dict still hashes to a deterministic value."""

        h = HashTable.compute_hash({})
        assert h == hashlib.sha256(b"{}").hexdigest()


# --------------------------------------------------------------------------- #
# HashTable.validate_config -- pure function, no app context needed
# --------------------------------------------------------------------------- #


class TestValidateConfig:
    """``validate_config`` enforces the autopilot config contract."""

    def test_valid_config(self) -> None:
        config = {
            "speed": {"default": 1.0, "description": "boat speed"},
            "heading": {"default": 0.0, "description": "current heading"},
        }
        valid, msg = HashTable.validate_config(config)
        assert valid is True
        assert msg == "The configuration is valid."

    def test_single_key_valid(self) -> None:
        valid, _ = HashTable.validate_config({"x": {"default": 0, "description": "x"}})
        assert valid is True

    def test_non_dict_rejected(self) -> None:
        for bad in (None, 42, "string", [1, 2, 3], ("a", "b")):
            valid, msg = HashTable.validate_config(bad)
            assert valid is False
            assert "must be a dictionary" in msg

    def test_empty_dict_rejected(self) -> None:
        valid, msg = HashTable.validate_config({})
        assert valid is False
        assert "empty" in msg

    def test_inner_value_not_dict_rejected(self) -> None:
        config = {"speed": 1.0}
        valid, msg = HashTable.validate_config(config)
        assert valid is False
        assert "must be a dictionary" in msg

    def test_missing_default_key_rejected(self) -> None:
        config = {"speed": {"description": "speed"}}
        valid, msg = HashTable.validate_config(config)
        assert valid is False
        assert "default" in msg and "description" in msg

    def test_missing_description_key_rejected(self) -> None:
        config = {"speed": {"default": 1.0}}
        valid, msg = HashTable.validate_config(config)
        assert valid is False
        assert "default" in msg and "description" in msg

    def test_extra_keys_in_inner_dict_allowed(self) -> None:
        """Only ``default`` and ``description`` are required; extras are ignored."""

        config = {"speed": {"default": 1.0, "description": "s", "units": "knots"}}
        valid, _ = HashTable.validate_config(config)
        assert valid is True

    def test_non_string_top_level_key_rejected(self) -> None:
        # JSON keys are always strings, but validate_config is called on
        # Python objects too, so int keys should be rejected.
        config = {1: {"default": 1, "description": "x"}}
        valid, msg = HashTable.validate_config(config)
        assert valid is False
        assert "strings" in msg


# --------------------------------------------------------------------------- #
# TelemetryTable.validate_user -- the immutability invariant (§3.3)
# --------------------------------------------------------------------------- #


class TestValidateUser:
    """The ``user`` field can be set once, then is immutable.

    Note: the ``default='unknown'`` on the column is a SQLAlchemy *database*
    default, applied at INSERT/flush time, not at object construction. So a
    freshly constructed (un-flushed) ``TelemetryTable`` has ``user is None``
    until flushed. These tests flush the instance first to reach the
    post-insert state where ``user == 'unknown'``, then exercise the
    validator (which is the state the route handlers operate on).
    """

    @staticmethod
    def _make_instance() -> TelemetryTable:
        instance = TelemetryTable(
            default_autopilot_parameters={}, autopilot_parameters={}, boat_status={}, waypoints=[], boat_status_mapping=[]
        )
        db.session.add(instance)
        db.session.flush()  # apply the column default for `user`
        return instance

    def test_default_user_is_unknown(self, app: Flask) -> None:
        instance = self._make_instance()
        assert instance.user == "unknown"

    def test_setting_from_unknown_to_named_is_allowed(self, app: Flask) -> None:
        instance = self._make_instance()
        instance.user = "alice"
        assert instance.user == "alice"

    def test_changing_named_user_raises(self, app: Flask) -> None:
        instance = self._make_instance()
        instance.user = "alice"
        with pytest.raises(ValueError, match="can only be set once"):
            instance.user = "bob"

    def test_setting_same_named_user_is_allowed(self, app: Flask) -> None:
        """Idempotent sets (same value) don't raise."""

        instance = self._make_instance()
        instance.user = "alice"
        instance.user = "alice"
        assert instance.user == "alice"

    def test_setting_from_unknown_to_unknown_is_allowed(self, app: Flask) -> None:
        instance = self._make_instance()
        instance.user = "unknown"
        assert instance.user == "unknown"


# --------------------------------------------------------------------------- #
# DB-backed tests: after_insert hook, to_dict, get_all_ids, check_hash_exists
# --------------------------------------------------------------------------- #


class TestAfterInsertHook:
    """The ``after_insert`` event auto-sets ``instance_identifier`` (§3.5)."""

    def test_auto_sets_default_identifier(self, app: Flask) -> None:
        instance = TelemetryTable(
            default_autopilot_parameters={}, autopilot_parameters={}, boat_status={}, waypoints=[], boat_status_mapping=[]
        )
        db.session.add(instance)
        db.session.commit()
        assert instance.instance_identifier == f"Unnamed instance #{instance.instance_id}"

    def test_preserves_supplied_identifier(self, app: Flask) -> None:
        instance = TelemetryTable(
            default_autopilot_parameters={},
            autopilot_parameters={},
            boat_status={},
            waypoints=[],
            boat_status_mapping=[],
            instance_identifier="my-custom-name",
        )
        db.session.add(instance)
        db.session.commit()
        assert instance.instance_identifier == "my-custom-name"

    def test_empty_string_identifier_gets_default(self, app: Flask) -> None:
        """An empty string is falsy, so the hook should replace it."""

        instance = TelemetryTable(
            default_autopilot_parameters={},
            autopilot_parameters={},
            boat_status={},
            waypoints=[],
            boat_status_mapping=[],
            instance_identifier="",
        )
        db.session.add(instance)
        db.session.commit()
        assert instance.instance_identifier == f"Unnamed instance #{instance.instance_id}"


class TestTelemetryTableToDict:
    """``to_dict`` serializes a subset of columns for the info routes."""

    def test_to_dict_keys(self, app: Flask) -> None:
        instance = TelemetryTable(
            default_autopilot_parameters={}, autopilot_parameters={}, boat_status={}, waypoints=[], boat_status_mapping=[]
        )
        db.session.add(instance)
        db.session.commit()

        data = instance.to_dict()
        assert set(data.keys()) == {
            "instance_id",
            "instance_identifier",
            "user",
            "current_config_hash",
            "created_at",
            "updated_at",
        }
        assert data["instance_id"] == instance.instance_id
        assert data["user"] == "unknown"
        assert data["current_config_hash"] == ""

    def test_to_dict_timestamps_are_iso_strings(self, app) -> None:
        instance = TelemetryTable(
            default_autopilot_parameters={}, autopilot_parameters={}, boat_status={}, waypoints=[], boat_status_mapping=[]
        )
        db.session.add(instance)
        db.session.commit()

        data = instance.to_dict()
        assert isinstance(data["created_at"], str)
        assert isinstance(data["updated_at"], str)
        # ISO 8601 format includes a 'T' separator
        assert "T" in data["created_at"]


class TestGetAllIds:
    """``get_all_ids`` returns all instance IDs in the table."""

    def test_empty_table(self, app: Flask) -> None:
        assert TelemetryTable.get_all_ids() == []

    def test_returns_all_ids(self, app: Flask) -> None:
        instances = [
            TelemetryTable(
                default_autopilot_parameters={}, autopilot_parameters={}, boat_status={}, waypoints=[], boat_status_mapping=[]
            )
            for _ in range(3)
        ]
        for inst in instances:
            db.session.add(inst)
        db.session.commit()

        ids = TelemetryTable.get_all_ids()
        assert len(ids) == 3
        assert set(ids) == {inst.instance_id for inst in instances}


class TestHashTableDb:
    """DB-backed tests for ``HashTable`` classmethods and ``to_dict``."""

    def test_check_hash_exists_false_when_missing(self, app: Flask) -> None:
        assert HashTable.check_hash_exists("nonexistent") is False

    def test_check_hash_exists_true_after_insert(self, app: Flask) -> None:
        config = {"speed": {"default": 1.0, "description": "speed"}}
        h = HashTable.compute_hash(config)
        entry = HashTable(config_hash=h, data=config, description="test")
        db.session.add(entry)
        db.session.commit()

        assert HashTable.check_hash_exists(h) is True

    def test_to_dict_keys(self, app: Flask) -> None:
        config = {"speed": {"default": 1.0, "description": "speed"}}
        h = HashTable.compute_hash(config)
        entry = HashTable(config_hash=h, data=config, description="a description")
        db.session.add(entry)
        db.session.commit()

        data = entry.to_dict()
        assert set(data.keys()) == {"config_hash", "description", "created_at"}
        assert data["config_hash"] == h
        assert data["description"] == "a description"
        assert isinstance(data["created_at"], str)

    def test_default_description_is_empty_string(self, app: Flask) -> None:
        entry = HashTable(config_hash="abc123", data={"x": {"default": 1, "description": "x"}})
        db.session.add(entry)
        db.session.commit()
        assert entry.description == ""


# --------------------------------------------------------------------------- #
# SQLite connection pragmas (WAL, synchronous, etc.)
# --------------------------------------------------------------------------- #


class TestSqlitePragmas:
    """The engine-connect listener must apply performance pragmas to every bind."""

    def _pragma(self, app: Flask, name: str) -> object:
        from sqlalchemy import text

        with app.app_context():
            return db.session.execute(text(f"PRAGMA {name}")).scalar()

    def test_journal_mode_is_wal_on_default_bind(self, app: Flask) -> None:
        assert str(self._pragma(app, "journal_mode")).lower() == "wal"

    def test_journal_mode_is_wal_on_hashes_bind(self, app: Flask) -> None:
        from sqlalchemy import text

        with app.app_context():
            engine = db.engines["hashes"]
            with engine.connect() as conn:
                result = conn.execute(text("PRAGMA journal_mode")).scalar()
        assert str(result).lower() == "wal"

    def test_synchronous_is_normal(self, app: Flask) -> None:
        # synchronous=NORMAL is reported as the integer 1 under SQLite.
        assert self._pragma(app, "synchronous") == 1

    def test_busy_timeout_is_set(self, app: Flask) -> None:
        assert self._pragma(app, "busy_timeout") == 5000


# --------------------------------------------------------------------------- #
# Indexes on TelemetryTable (updated_at, instance_identifier)
# --------------------------------------------------------------------------- #


class TestTelemetryTableIndexes:
    """``db.create_all()`` must create indexes on fresh databases.

    See AGENTS.md §6.2: there is no migration framework, so existing
    deployments need a one-time ``CREATE INDEX`` on the volume. These tests
    only pin the fresh-DB behavior; they do not exercise the migration path.
    """

    def _index_names(self, app: Flask) -> set[str]:
        from sqlalchemy import inspect

        with app.app_context():
            inspector = inspect(db.engine)
            return {idx["name"] for idx in inspector.get_indexes("telemetry_table")}

    def test_updated_at_index_exists(self, app: Flask) -> None:
        assert "ix_telemetry_table_updated_at" in self._index_names(app)

    def test_instance_identifier_index_exists(self, app: Flask) -> None:
        assert "ix_telemetry_table_instance_identifier" in self._index_names(app)
