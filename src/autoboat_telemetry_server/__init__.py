"""Telemetry server for Autoboat at Virginia Tech."""

__all__ = ["HOME_DIR", "INSTANCE_DIR", "create_app", "shared_lock_manager"]

import os
from pathlib import Path

from flask import Flask as _flask
from flask_cors import CORS

from .lock_manager import LockManager
from .models import db

shared_lock_manager = LockManager()

home_directories: list[Path] = [d for d in Path("/home").iterdir() if d.is_dir()]
if len(home_directories) == 0:
    raise RuntimeError("No home directories found in /home. Expected at least one user directory.")

elif len(home_directories) == 1:
    HOME_DIR = home_directories[0]

else:
    HOME_DIR = Path.home()

INSTANCE_DIR = HOME_DIR / "telemetry_server" / "src" / "instance"

from autoboat_telemetry_server.routes import (  # noqa: E402
    AutopilotParametersEndpoint,
    BoatStatusEndpoint,
    InstanceManagerEndpoint,
    WaypointEndpoint,
)

# Origins allowed to make cross-origin requests to this API.
#
# The Autoboat website (https://autoboat.aoe.vt.edu) fetches boat positions
# from the telemetry API in the browser, so the server must send
# Access-Control-Allow-Origin headers for that origin. Local development of
# the website (vite dev server on localhost) is also allowed.
DEFAULT_CORS_ORIGINS: list[str] = [
    "https://autoboat.aoe.vt.edu",
    "https://vt-autoboat-telemetry.uk",
    "https://www.vt-autoboat-telemetry.uk",
    "https://test.vt-autoboat-telemetry.uk",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]


def _parse_cors_origins(raw: str) -> list[str]:
    """Split a comma-separated CORS_ORIGINS env var into a list of origins."""
    return [origin.strip() for origin in raw.split(",") if origin.strip()]


def create_app() -> _flask:
    """
    Create and configure the Flask application instance.

    Returns
    -------
    Flask
        Configured Flask application instance.
    """

    app = _flask(__name__)

    config_path = INSTANCE_DIR / "config.py"
    app.config.from_pyfile(config_path)

    # Determine the allowed CORS origins. Precedence (highest first):
    #   1. CORS_ORIGINS env var (comma-separated) — works on existing
    #      deployments without rebuilding, since src/instance/config.py is
    #      persisted in a named volume and not overwritten on image updates.
    #   2. app.config["CORS_ORIGINS"] (set in src/instance/config.py) —
    #      applies on fresh installs where config.py is seeded from the image.
    #   3. DEFAULT_CORS_ORIGINS — the known website + telemetry origins.
    env_origins = os.environ.get("CORS_ORIGINS")
    if env_origins:
        origins: str | list[str] = _parse_cors_origins(env_origins)
    else:
        origins = app.config.get("CORS_ORIGINS", DEFAULT_CORS_ORIGINS)

    CORS(app, origins=origins)

    db.init_app(app)

    with app.app_context():
        db.create_all()

    app.register_blueprint(InstanceManagerEndpoint().blueprint)
    app.register_blueprint(AutopilotParametersEndpoint().blueprint)
    app.register_blueprint(BoatStatusEndpoint().blueprint)
    app.register_blueprint(WaypointEndpoint().blueprint)

    @app.route("/")
    def index() -> str:
        """
        Root route for the telemetry server.

        Returns
        -------
        str
            Confirmation message indicating which server is running.
        """

        return "This is the telemetry server. It is running!"

    return app
