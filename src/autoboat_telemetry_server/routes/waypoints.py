from flask import Blueprint, Response, jsonify, request
from typing import Literal
from autoboat_telemetry_server.models import TelemetryTable, db


class WaypointEndpoint:
    """Endpoint for handling waypoints."""

    def __init__(self) -> None:
        self._blueprint = Blueprint("waypoints_page", __name__, url_prefix="/waypoints")
        self._register_routes()

    @property
    def blueprint(self) -> Blueprint:
        """Returns the Flask blueprint for autopilot parameters."""
        return self._blueprint

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

            Returns
            -------
            Literal["waypoints route testing!"]
                Confirmation message for testing the waypoints route.
            """

            return "waypoints route testing!"

        @self._blueprint.route("/get/<int:instance_id>", methods=["GET"])
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
                telemetry_instance: TelemetryTable | None = TelemetryTable.query.get(instance_id)
                if telemetry_instance is None:
                    raise ValueError("Instance not found.")

                return jsonify(telemetry_instance.waypoints), 200

            except ValueError as e:
                return jsonify({"error": str(e)}), 404

            except Exception as e:
                return jsonify({"error": str(e)}), 500

        @self._blueprint.route("/get_new/<int:instance_id>", methods=["GET"])
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
                or an empty response if there are no new waypoints.
            """

            try:
                telemetry_instance: TelemetryTable | None = TelemetryTable.query.get(instance_id)
                if telemetry_instance is None:
                    raise ValueError("Instance not found.")

                if telemetry_instance.waypoints_new_flag is False:
                    return jsonify({}), 200

                telemetry_instance.waypoints_new_flag = False
                db.session.commit()

                return jsonify(telemetry_instance.waypoints), 200

            except ValueError as e:
                return jsonify({"error": str(e)}), 404

            except Exception as e:
                return jsonify({"error": str(e)}), 500

        @self._blueprint.route("/set/<int:instance_id>", methods=["POST"])
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
                telemetry_instance: TelemetryTable | None = TelemetryTable.query.get(instance_id)
                if telemetry_instance is None:
                    raise ValueError("Instance not found.")

                waypoints_data = request.json.get("waypoints", [])
                if not isinstance(waypoints_data, list):
                    raise TypeError("Invalid waypoints data format. Expected a list.")

                telemetry_instance.waypoints = waypoints_data
                telemetry_instance.waypoints_new_flag = True
                db.session.commit()

                return jsonify({"message": "Waypoints updated successfully."}), 200

            except ValueError as e:
                return jsonify({"error": str(e)}), 404

            except TypeError as e:
                return jsonify({"error": str(e)}), 400

            except Exception as e:
                db.session.rollback()
                return jsonify({"error": str(e)}), 500

        return f"waypoints paths registered successfully: {self._blueprint.url_prefix}"
