"""
Tests for ``autoboat_telemetry_server.__init__`` (the app factory).

Covers:
- ``_parse_cors_origins`` (pure string parsing for the CORS_ORIGINS env var).
- ``DEFAULT_CORS_ORIGINS`` contents (the known website + telemetry origins).
- ``create_app()`` basic behavior (blueprints registered, DB initialized,
  index route responds, CORS configured).
- ``shared_lock_manager`` is a singleton instance.

The conftest bootstraps the ``/home`` discovery so the package imports on
macOS; these tests build on that by exercising ``create_app()`` against a
temp instance dir.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from conftest import FAKE_HOME
from flask.app import Flask
from flask.testing import FlaskClient


class TestParseCorsOrigins:
    """``_parse_cors_origins`` splits and trims a comma-separated env var."""

    def test_single_origin(self) -> None:
        from autoboat_telemetry_server import _parse_cors_origins

        assert _parse_cors_origins("https://example.com") == ["https://example.com"]

    def test_multiple_origins(self) -> None:
        from autoboat_telemetry_server import _parse_cors_origins

        result = _parse_cors_origins("https://a.com,https://b.com,https://c.com")
        assert result == ["https://a.com", "https://b.com", "https://c.com"]

    def test_whitespace_is_trimmed(self) -> None:
        from autoboat_telemetry_server import _parse_cors_origins

        result = _parse_cors_origins(" https://a.com , https://b.com , ")
        assert result == ["https://a.com", "https://b.com"]

    def test_empty_string_returns_empty_list(self) -> None:
        from autoboat_telemetry_server import _parse_cors_origins

        assert _parse_cors_origins("") == []

    def test_only_commas_returns_empty_list(self) -> None:
        from autoboat_telemetry_server import _parse_cors_origins

        assert _parse_cors_origins(",,,") == []

    def test_only_whitespace_returns_empty_list(self) -> None:
        from autoboat_telemetry_server import _parse_cors_origins

        assert _parse_cors_origins("   ") == []


class TestDefaultCorsOrigins:
    """``DEFAULT_CORS_ORIGINS`` is the fallback CORS allowlist."""

    def test_includes_production_website(self) -> None:
        from autoboat_telemetry_server import DEFAULT_CORS_ORIGINS

        assert "https://autoboat.aoe.vt.edu" in DEFAULT_CORS_ORIGINS

    def test_includes_production_telemetry_domain(self) -> None:
        from autoboat_telemetry_server import DEFAULT_CORS_ORIGINS

        assert "https://vt-autoboat-telemetry.uk" in DEFAULT_CORS_ORIGINS
        assert "https://www.vt-autoboat-telemetry.uk" in DEFAULT_CORS_ORIGINS

    def test_includes_test_telemetry_domain(self) -> None:
        from autoboat_telemetry_server import DEFAULT_CORS_ORIGINS

        assert "https://test.vt-autoboat-telemetry.uk" in DEFAULT_CORS_ORIGINS

    def test_includes_local_dev_origins(self) -> None:
        from autoboat_telemetry_server import DEFAULT_CORS_ORIGINS

        assert "http://localhost:5173" in DEFAULT_CORS_ORIGINS
        assert "http://127.0.0.1:5173" in DEFAULT_CORS_ORIGINS

    def test_is_a_list_of_strings(self) -> None:
        from autoboat_telemetry_server import DEFAULT_CORS_ORIGINS

        assert isinstance(DEFAULT_CORS_ORIGINS, list)
        assert all(isinstance(o, str) for o in DEFAULT_CORS_ORIGINS)

    def test_includes_www_website_mirror(self) -> None:
        """The www mirror of the website must be in the default allowlist.

        Regression guard: this entry once lived only in src/instance/config.py
        and was missing from the module-level DEFAULT_CORS_ORIGINS, so the
        two lists silently diverged. Keep them in sync.
        """

        from autoboat_telemetry_server import DEFAULT_CORS_ORIGINS

        assert "https://www.autoboat.aoe.vt.edu" in DEFAULT_CORS_ORIGINS


class TestCorsPrecedence:
    """The three CORS_ORIGIN sources resolve in a fixed precedence order.

    Precedence (highest first):
      1. ``CORS_ORIGINS`` env var (comma-separated).
      2. ``app.config["CORS_ORIGINS"]`` (from src/instance/config.py).
      3. ``DEFAULT_CORS_ORIGINS`` (module-level fallback in __init__.py).

    Regression guard: config.py once defined ``DEFAULT_CORS_ORIGINS`` instead
    of ``CORS_ORIGINS``, so Flask loaded it into
    ``app.config["DEFAULT_CORS_ORIGINS"]`` (a key nothing reads) and the
    level-2 override was silently dead. These tests pin the keys the app
    actually reads so that drift can't recur.
    """

    def test_instance_config_defines_cors_origins_key(self) -> None:
        """src/instance/config.py must define CORS_ORIGINS (not DEFAULT_CORS_ORIGINS).

        ``create_app()`` reads ``app.config["CORS_ORIGINS"]``; Flask's
        ``from_pyfile`` loads module-level names by their own name, so only
        ``CORS_ORIGINS`` in config.py reaches that key.
        """

        import importlib.util

        from autoboat_telemetry_server import INSTANCE_DIR

        spec = importlib.util.spec_from_file_location("_test_instance_config", INSTANCE_DIR / "config.py")
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        assert hasattr(module, "CORS_ORIGINS"), (
            "src/instance/config.py must define CORS_ORIGINS (the key "
            "create_app reads as app.config['CORS_ORIGINS']). Defining "
            "DEFAULT_CORS_ORIGINS here is dead — it lands in a key nothing reads."
        )
        assert not hasattr(module, "DEFAULT_CORS_ORIGINS"), (
            "src/instance/config.py should not define DEFAULT_CORS_ORIGINS — "
            "the module-level fallback lives in __init__.py. Defining it here "
            "shadows nothing and misleads readers."
        )

    def test_instance_config_overrides_default(self, tmp_instance_dir: Path) -> None:
        """app.config['CORS_ORIGINS'] from config.py beats DEFAULT_CORS_ORIGINS.

        We assert on the observable effect (the CORS response header) rather
        than app.config internals, because create_app passes the resolved
        list straight to flask-cors without writing it back to config.
        """

        import autoboat_telemetry_server as ats

        # write a config.py with a distinctive CORS_ORIGINS we can detect via
        # the response header; include both SQLAlchemy binds so db.create_all
        # doesn't blow up on the missing 'hashes' bind
        (tmp_instance_dir / "config.py").write_text(
            "SQLALCHEMY_BINDS = {None: 'sqlite:///:memory:', 'hashes': 'sqlite:///:memory:'}\n"
            "SQLALCHEMY_TRACK_MODIFICATIONS = False\n"
            "CORS_ORIGINS = ['https://override-marker.example.com']\n"
        )

        original = ats.INSTANCE_DIR
        ats.INSTANCE_DIR = tmp_instance_dir
        try:
            app = ats.create_app()
            client = app.test_client()
            response = client.get("/", headers={"Origin": "https://override-marker.example.com"})
            assert response.headers.get("Access-Control-Allow-Origin") == "https://override-marker.example.com"
            # and a non-listed origin does NOT get echoed back
            other = client.get("/", headers={"Origin": "https://not-allowed.example.com"})
            assert other.headers.get("Access-Control-Allow-Origin") != "https://not-allowed.example.com"
        finally:
            ats.INSTANCE_DIR = original

    def test_env_var_overrides_instance_config(self, tmp_instance_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """CORS_ORIGINS env var beats app.config['CORS_ORIGINS']."""

        import autoboat_telemetry_server as ats

        (tmp_instance_dir / "config.py").write_text(
            "SQLALCHEMY_BINDS = {None: 'sqlite:///:memory:', 'hashes': 'sqlite:///:memory:'}\n"
            "SQLALCHEMY_TRACK_MODIFICATIONS = False\n"
            "CORS_ORIGINS = ['https://from-config.example.com']\n"
        )

        monkeypatch.setenv("CORS_ORIGINS", "https://from-env.example.com")

        original = ats.INSTANCE_DIR
        ats.INSTANCE_DIR = tmp_instance_dir
        try:
            app = ats.create_app()
            client = app.test_client()
            # the env-var origin is echoed; the config-only origin is not
            response = client.get("/", headers={"Origin": "https://from-env.example.com"})
            assert response.headers.get("Access-Control-Allow-Origin") == "https://from-env.example.com"
            other = client.get("/", headers={"Origin": "https://from-config.example.com"})
            assert other.headers.get("Access-Control-Allow-Origin") != "https://from-config.example.com"
        finally:
            ats.INSTANCE_DIR = original


class TestSharedLockManager:
    """``shared_lock_manager`` is the module-level singleton used by routes."""

    def test_is_a_lock_manager(self) -> None:
        from autoboat_telemetry_server import shared_lock_manager
        from autoboat_telemetry_server.lock_manager import LockManager

        assert isinstance(shared_lock_manager, LockManager)

    def test_is_singleton(self) -> None:
        """Importing the symbol twice returns the same object."""

        from autoboat_telemetry_server import shared_lock_manager as a, shared_lock_manager as b

        assert a is b


class TestCreateApp:
    """``create_app()`` wires up blueprints, CORS, and the DB."""

    def test_returns_flask_app(self, app: Flask) -> None:
        from flask import Flask

        assert isinstance(app, Flask)

    def test_index_route_responds(self, client: FlaskClient) -> None:
        response = client.get("/")
        assert response.status_code == 200
        assert b"telemetry server" in response.data
        assert b"running" in response.data

    def test_registers_instance_manager_blueprint(self, app: Flask) -> None:
        rules = [r.rule for r in app.url_map.iter_rules()]
        assert any(r.startswith("/instance_manager") for r in rules)

    def test_registers_autopilot_parameters_blueprint(self, app: Flask) -> None:
        rules = [r.rule for r in app.url_map.iter_rules()]
        assert any(r.startswith("/autopilot_parameters") for r in rules)

    def test_registers_boat_status_blueprint(self, app: Flask) -> None:
        rules = [r.rule for r in app.url_map.iter_rules()]
        assert any(r.startswith("/boat_status") for r in rules)

    def test_registers_waypoints_blueprint(self, app: Flask) -> None:
        rules = [r.rule for r in app.url_map.iter_rules()]
        assert any(r.startswith("/waypoints") for r in rules)

    def test_test_routes_exist(self, client: FlaskClient) -> None:
        """Each blueprint exposes a ``/<domain>/test`` health-check route."""

        for prefix, expected in [
            ("/instance_manager/test", b"instance_manager route testing"),
            ("/autopilot_parameters/test", b"autopilot_parameters route testing"),
            ("/boat_status/test", b"boat_status route testing"),
            ("/waypoints/test", b"waypoints route testing"),
        ]:
            response = client.get(prefix)
            assert response.status_code == 200, f"{prefix} returned {response.status_code}"
            assert expected in response.data, f"{prefix} did not contain {expected!r}"

    def test_cors_header_present_on_response(self, client: FlaskClient) -> None:
        """CORS is configured globally; responses should carry the header."""

        response = client.get("/", headers={"Origin": "https://autoboat.aoe.vt.edu"})
        # the exact value depends on config, but the header should be present
        assert "Access-Control-Allow-Origin" in response.headers

    def test_app_is_in_testing_mode(self, app: Flask) -> None:
        assert app.config["TESTING"] is True


class TestInstanceDirDiscovery:
    """The conftest bootstraps the /home discovery; verify it worked."""

    def test_instance_dir_is_set(self) -> None:
        from autoboat_telemetry_server import INSTANCE_DIR

        assert INSTANCE_DIR is not None
        # the conftest patches /home to return the repo's parent dir, so
        # INSTANCE_DIR should point at .../telemetry_server/src/instance
        assert INSTANCE_DIR.name == "instance"

    def test_home_dir_is_fake_home(self) -> None:
        from autoboat_telemetry_server import HOME_DIR

        # the conftest patches /home to return the repo's parent dir so that
        # HOME_DIR / "telemetry_server" / "src" / "instance" resolves to the
        # repo's checked-in src/instance; in production this would be
        # /home/ubuntu
        # HOME_DIR == FAKE_HOME (the repo's parent) on every machine, regardless
        # of what that parent happens to be named locally
        assert HOME_DIR == FAKE_HOME
