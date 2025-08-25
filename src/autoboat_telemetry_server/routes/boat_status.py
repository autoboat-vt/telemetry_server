from flask import Blueprint, Response, jsonify, request
from typing import Literal
from autoboat_telemetry_server.models import TelemetryTable, db


class BoatStatusEndpoint:
    """Endpoint for handling boat status."""

    def __init__(self) -> None:
        self._blueprint = Blueprint("boat_status_page", __name__, url_prefix="/boat_status")
        self._register_routes()

    @property
    def blueprint(self) -> Blueprint:
        """Returns the Flask blueprint for autopilot parameters."""
        return self._blueprint

    def _register_routes(self) -> str:
        """
        Registers the routes for the boat status endpoint.

        Returns
        -------
        str
            Confirmation message indicating the routes have been registered successfully.
        """

        @self._blueprint.route("/test", methods=["GET"])
        def test_route() -> Literal["boat_status route testing!"]:
            """
            Test route for boat status.

            Returns
            -------
            Literal["boat_status route testing!"]
                Confirmation message for testing the boat status route.
            """

            return "boat_status route testing!"

        @self._blueprint.route("/get/<int:instance_id>", methods=["GET"])
        def get_route(instance_id: int) -> tuple[Response, int]:
            """
            Get the boat status for a specific telemetry instance.

            Method: GET

            Parameters
            ----------
            instance_id
                The ID of the telemetry instance to retrieve the boat status for.

            Returns
            -------
            tuple[Response, int]
                A tuple containing a JSON response with the boat status for the specified telemetry instance,
                or an error message if the instance is not found.
            """

            try:
                telemetry_instance = TelemetryTable.query.get(instance_id)
                if not isinstance(telemetry_instance, TelemetryTable):
                    raise TypeError("Instance not found.")

                return jsonify(telemetry_instance.boat_status), 200

            except TypeError as e:
                return jsonify(str(e)), 404

            except Exception as e:
                return jsonify(str(e)), 500

        @self._blueprint.route("/get_new/<int:instance_id>", methods=["GET"])
        def get_new_route(instance_id: int) -> tuple[Response, int]:
            """
            Gets the boat status for a specific telemetry instance if it hasn't already been
            requested since the last update.

            Method: GET

            Parameters
            ----------
            instance_id
                The ID of the telemetry instance to retrieve the new boat status for.

            Returns
            -------
            tuple[Response, int]
                A tuple containing a JSON response with the boat status for the specified telemetry instance,
                or an empty dictionary if there is no new boat status, or an error message if the instance is not found.
            """

            try:
                telemetry_instance = TelemetryTable.query.get(instance_id)
                if not isinstance(telemetry_instance, TelemetryTable):
                    raise TypeError("Instance not found.")

                if telemetry_instance.boat_status_new_flag is False:
                    return jsonify({}), 200

                telemetry_instance.boat_status_new_flag = False
                db.session.commit()

                return jsonify(telemetry_instance.boat_status), 200

            except TypeError as e:
                return jsonify(str(e)), 404

            except Exception as e:
                return jsonify(str(e)), 500

        @self._blueprint.route("/set/<int:instance_id>", methods=["POST"])
        def set_route(instance_id: int) -> tuple[Response, int]:
            """
            Set the boat status for a specific telemetry instance.

            Method: POST

            Parameters
            ----------
            instance_id
                The ID of the telemetry instance to set the boat status for.

            Returns
            -------
            tuple[Response, int]
                A tuple containing a JSON response confirming the boat status has been updated successfully,
                or an error message if the instance is not found or if the input format is invalid.
            """

            try:
                telemetry_instance = TelemetryTable.query.get(instance_id)
                if not isinstance(telemetry_instance, TelemetryTable):
                    raise TypeError("Instance not found.")

                new_status = request.json
                if not isinstance(new_status, dict):
                    raise TypeError("Invalid boat status format. Expected a dictionary.")

                telemetry_instance.boat_status = new_status
                telemetry_instance.boat_status_new_flag = True
                db.session.commit()

                return jsonify({"message": "Boat status updated successfully."}), 200

            except TypeError as e:
                return jsonify(str(e)), 400

            except Exception as e:
                db.session.rollback()
                return jsonify(str(e)), 500

        return f"boat_status paths registered successfully: {self._blueprint.url_prefix}"
