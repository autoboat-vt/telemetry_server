"""Telemetry server for Autoboat at Virginia Tech."""

from typing import Literal
from flask import Flask as _flask
# from flask_sqlalchemy import SQLAlchemy

from autoboat_telemetry_server._autopilot_parameters import (
    AutopilotParametersEndpoint,
)
from autoboat_telemetry_server._boat_status import BoatStatusEndpoint
from autoboat_telemetry_server._waypoints import WaypointEndpoint

__all__ = ["create_app"]


def create_app() -> _flask:
    """
    Create and configure the Flask application instance.

    Returns:
        Flask: Configured Flask application instance.
    """

    app = _flask(__name__, instance_relative_config=True)
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///project.db"
    # db = SQLAlchemy(app)

    app.register_blueprint(AutopilotParametersEndpoint().blueprint)
    app.register_blueprint(BoatStatusEndpoint().blueprint)
    app.register_blueprint(WaypointEndpoint().blueprint)

    @app.route("/")
    def index() -> Literal["Autoboat Telemetry Server is running."]:
        """
        Root route for the telemetry server.

        Returns
        -------
        Literal["Autoboat Telemetry Server is running."]
            Confirmation message indicating the server is running.
        """

        return "Autoboat Telemetry Server is running."

    return app
