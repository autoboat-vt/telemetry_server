"""Telemetry server for Autoboat at Virginia Tech."""

__all__ = ["HOME_DIR", "INSTANCE_DIR", "create_app", "shared_lock_manager"]

import os
from pathlib import Path

from flask import Flask as _flask
from flask_cors import CORS
from flask_migrate import Migrate

from .lock_manager import LockManager
from .models import db
from .observability import init_app as init_observability

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

# cors origins — lowest-precedence fallback; see
# python-source.instructions.md #"CORS precedence" and #"App factory"
DEFAULT_CORS_ORIGINS: list[str] = [
    "https://autoboat.aoe.vt.edu",
    "https://www.autoboat.aoe.vt.edu",
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

    # cors origins — see python-source.instructions.md #"CORS precedence"
    env_origins = os.environ.get("CORS_ORIGINS")
    if env_origins:
        origins: str | list[str] = _parse_cors_origins(env_origins)
    else:
        origins = app.config.get("CORS_ORIGINS", DEFAULT_CORS_ORIGINS)

    CORS(app, origins=origins)

    db.init_app(app)

    # migrations are the only path that creates tables in prod; see
    # python-source.instructions.md #"App factory" and AGENTS.md #6.2
    migrate = Migrate()
    migrate.init_app(app, db, directory=str(Path(__file__).resolve().parent.parent.parent / "migrations"))

    app.register_blueprint(InstanceManagerEndpoint().blueprint)
    app.register_blueprint(AutopilotParametersEndpoint().blueprint)
    app.register_blueprint(BoatStatusEndpoint().blueprint)
    app.register_blueprint(WaypointEndpoint().blueprint)

    # structured logging + /metrics endpoint; see observability.py and
    # python-source.instructions.md #"Observability"
    init_observability(app)

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
