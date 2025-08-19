"""Telemetry server for Autoboat at Virginia Tech."""

import os
from flask import Flask as _flask
from .models import db
from autoboat_telemetry_server.routes import AutopilotParametersEndpoint, BoatStatusEndpoint, WaypointEndpoint, InstanceManagerEndpoint

__all__ = ["create_app"]


def create_app() -> _flask:
    """
    Create and configure the Flask application instance.

    Returns:
        Flask: Configured Flask application instance.
    """

    app = _flask(__name__)

    instance_dir = "/home/ubuntu/telemetry_server/src/instance"
    # instance_dir = "/Users/bwise/important_files/projects/autoboat/telemetry_server/src/instance"
    config_path = os.path.join(instance_dir, "config.py")

    app.config.from_pyfile(config_path)

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
            A string showing information about the current state of the server.
        """

        return "Autoboat Telemetry Server is running!"

    return app
