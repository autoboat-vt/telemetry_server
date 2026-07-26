"""Tests for ``autoboat_telemetry_server.__init__`` (the app factory).

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


class TestSharedLockManager:
    """``shared_lock_manager`` is the module-level singleton used by routes."""

    def test_is_a_lock_manager(self) -> None:
        from autoboat_telemetry_server import shared_lock_manager
        from autoboat_telemetry_server.lock_manager import LockManager

        assert isinstance(shared_lock_manager, LockManager)

    def test_is_singleton(self) -> None:
        """Importing the symbol twice returns the same object."""

        from autoboat_telemetry_server import shared_lock_manager as a
        from autoboat_telemetry_server import shared_lock_manager as b

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
        # The exact value depends on config, but the header should be present.
        assert "Access-Control-Allow-Origin" in response.headers

    def test_app_is_in_testing_mode(self, app: Flask) -> None:
        assert app.config["TESTING"] is True


class TestInstanceDirDiscovery:
    """The conftest bootstraps the /home discovery; verify it worked."""

    def test_instance_dir_is_set(self) -> None:
        from autoboat_telemetry_server import INSTANCE_DIR

        assert INSTANCE_DIR is not None
        # The conftest patches /home to return the repo's parent dir, so
        # INSTANCE_DIR should point at .../telemetry_server/src/instance.
        assert INSTANCE_DIR.name == "instance"

    def test_home_dir_is_fake_home(self) -> None:
        from autoboat_telemetry_server import HOME_DIR

        # The conftest patches /home to return the repo's parent dir so that
        # HOME_DIR / "telemetry_server" / "src" / "instance" resolves to the
        # repo's checked-in src/instance. In production this would be /home/ubuntu.
        assert HOME_DIR.name == "autoboat"
