from typing import Literal

from flask import Blueprint, Response, jsonify, request

from autoboat_telemetry_server import lock_manager
from autoboat_telemetry_server.models import TelemetryTable, db


class WaypointEndpoint:
    """Endpoint for handling waypoints."""

    def __init__(self) -> None:
        self._blueprint = Blueprint(name="waypoints_page", import_name=__name__, url_prefix="/waypoints")
        self._register_routes()

    @property
    def blueprint(self) -> Blueprint:
        """Returns the Flask blueprint for autopilot parameters."""

        return self._blueprint

    def _get_instance(self, instance_id: int) -> TelemetryTable:
        """
        Helper function to retrieve a telemetry instance by its ID.

        Parameters
        ----------
        instance_id
            The ID of the telemetry instance to retrieve.

        Returns
        -------
        TelemetryTable
            The telemetry instance corresponding to the provided ID.
        """

        instance = TelemetryTable.query.get(instance_id)

        if not isinstance(instance, TelemetryTable):
            raise TypeError("Instance not found.")

        return instance

    def _register_routes(self) -> str:
        """
        Registers the routes for the waypoints endpoint.

        Returns
        -------
        str
            Confirmation message indicating the routes have been registered successfully.
        """

        @self._blueprint.route("/test", methods=["GET"])
        def test_route() -> Literal["waypoints route testing!"]:
            """
            Test route for waypoints.

            Method: GET

            Returns
            -------
            Literal["waypoints route testing!"]
                Confirmation message for testing the waypoints route.
            """

            return "waypoints route testing!"

        @self._blueprint.route("/get/<int:instance_id>", methods=["GET"])
        @lock_manager.require_read_lock
        def get_route(instance_id: int) -> tuple[Response, int]:
            """
            Get the current waypoints for a specific telemetry instance.

            Method: GET

            Parameters
            ----------
            instance_id
                The ID of the telemetry instance to retrieve the waypoints for.

            Returns
            -------
            tuple[Response, int]
                A tuple containing a JSON response with the waypoints for the specified telemetry instance,
                or an error message if the instance is not found.
            """

            try:
                telemetry_instance = self._get_instance(instance_id)
                return jsonify(telemetry_instance.waypoints), 200

            except TypeError as e:
                return jsonify(str(e)), 404

            except Exception as e:
                return jsonify(str(e)), 500

        @self._blueprint.route("/get_new/<int:instance_id>", methods=["GET"])
        @lock_manager.require_write_lock
        def get_new_route(instance_id: int) -> tuple[Response, int]:
            """
            Gets the waypoints for a specific telemetry instance if it hasn't already been
            requested since the last update.

            Method: GET

            Parameters
            ----------
            instance_id
                The ID of the telemetry instance to retrieve the waypoints for.

            Returns
            -------
            tuple[Response, int]
                A tuple containing a JSON response with the waypoints for the specified telemetry instance,
                or an empty dictionary if there are no new waypoints, or an error message if the instance is not found.
            """

            try:
                telemetry_instance = self._get_instance(instance_id)
                if telemetry_instance.waypoints_new_flag is False:
                    return jsonify({}), 200

                telemetry_instance.waypoints_new_flag = False
                db.session.commit()

                return jsonify(telemetry_instance.waypoints), 200

            except TypeError as e:
                return jsonify(str(e)), 404

            except Exception as e:
                return jsonify(str(e)), 500

        @self._blueprint.route("/set/<int:instance_id>", methods=["POST"])
        @lock_manager.require_write_lock
        def set_route(instance_id: int) -> tuple[Response, int]:
            """
            Set the waypoints from the request data.

            Method: POST

            Parameters
            ----------
            instance_id
                The ID of the telemetry instance to set the waypoints for.

            Returns
            -------
            tuple[Response, int]
                A tuple containing a JSON response confirming the waypoints have been updated successfully,
                or an error message if the instance is not found or if the input format is invalid.
            """

            try:
                telemetry_instance = self._get_instance(instance_id)
                waypoints_data = request.json
                if not isinstance(waypoints_data, list):
                    raise TypeError("Invalid waypoints data format. Expected a list of [x, y] coordinates.")

                for point in waypoints_data:
                    if not (isinstance(point, (list, tuple)) and len(point) == 2):
                        raise TypeError("Invalid waypoint format. Each waypoint must be a list or tuple of two coordinates.")

                    if not all(isinstance(coord, (int, float)) for coord in point):
                        raise TypeError("Invalid coordinate type. Each coordinate must be an integer or float.")

                telemetry_instance.waypoints = waypoints_data
                telemetry_instance.waypoints_new_flag = True
                db.session.commit()

                return jsonify("Waypoints updated successfully."), 200

            except TypeError as e:
                return jsonify(str(e)), 400

            except Exception as e:
                db.session.rollback()
                return jsonify(str(e)), 500

        return f"waypoints paths registered successfully: {self._blueprint.url_prefix}"
