"""Telemetry server for Autoboat at Virginia Tech."""

import os
from flask import Flask as _flask
from autoboat_telemetry_server.routes import AutopilotParametersEndpoint, BoatStatusEndpoint, WaypointEndpoint

__all__ = ["create_app"]


def create_app() -> _flask:
    """
    Create and configure the Flask application instance.

    Returns
    -------
    _flask
        Configured Flask application instance.
    """

    app = _flask(__name__)

    instance_dir = "/home/ubuntu/telemetry_server/src/instance"
    config_path = os.path.join(instance_dir, "config.py")

    app.config.from_pyfile(config_path)

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

        return "This is the production telemetry server. It is running!"

    return app
