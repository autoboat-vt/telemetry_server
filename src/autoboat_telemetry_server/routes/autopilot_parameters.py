from flask import request, Blueprint, jsonify
from typing import Literal
from autoboat_telemetry_server.types import AutopilotParametersType
from autoboat_telemetry_server.models import db, TelemetryTable


class AutopilotParametersEndpoint:
    """Endpoint for handling autopilot parameters."""

    def __init__(self) -> None:
        self._blueprint = Blueprint("autopilot_parameters_page", __name__, url_prefix="/autopilot_parameters")
        self._register_routes()

    @property
    def blueprint(self) -> Blueprint:
        """Returns the Flask blueprint for autopilot parameters."""

        return self._blueprint

    def _register_routes(self) -> str:
        """
        Registers the routes for the autopilot parameters endpoint.

        Returns
        -------
        str
            Confirmation message indicating the routes have been registered successfully.
        """

        @self._blueprint.route("/test", methods=["GET"])
        def test_route() -> Literal["autopilot_parameters route testing!"]:
            """
            Test route for autopilot parameters.

            Returns
            -------
            Literal["autopilot_parameters route testing!"]
                Confirmation message for testing the autopilot parameters route.
            """

            return "autopilot_parameters route testing!"

        @self._blueprint.route("/get/<int:instance_id>", methods=["GET"])
        def get_route(instance_id: int) -> tuple[AutopilotParametersType, int]:
            """
            Get the current autopilot parameters.

            Method: GET

            Parameters
            ----------
            instance_id
                The ID of the telemetry instance to retrieve the autopilot parameters for.


            Returns
            -------
            tuple[AutopilotParametersType, int]
                A tuple containing the autopilot parameters and a status code of 200 if successful,
                or an error message and a status code of 404 if the instance is not found.
            """

            try:
                telemetry_instance: TelemetryTable | None = TelemetryTable.query.get(instance_id)
                if telemetry_instance is None:
                    raise ValueError("Instance not found.")

                return jsonify(telemetry_instance.autopilot_parameters), 200

            except ValueError as e:
                return jsonify({"error": str(e)}), 404

            except Exception as e:
                return jsonify({"error": str(e)}), 500

        @self._blueprint.route("/get_new/<int:instance_id>", methods=["GET"])
        def get_new_route(instance_id: int) -> tuple[AutopilotParametersType, int]:
            """
            Get the latest autopilot parameters if they haven't been seen yet.

            Method: GET

            Parameters
            ----------
            instance_id
                The ID of the telemetry instance to retrieve the new autopilot parameters for.

            Returns
            -------
            tuple[AutopilotParametersType, int]
                A tuple containing the new autopilot parameters and a status code of 200 if successful,
                or an error message and a status code of 404 if the instance is not found.
            """

            try:
                telemetry_instance: TelemetryTable | None = TelemetryTable.query.get(instance_id)
                if telemetry_instance is None:
                    raise ValueError("Instance not found.")

                if telemetry_instance.autopilot_parameters_new_flag is False:
                    return jsonify(telemetry_instance.autopilot_parameters), 200

                telemetry_instance.autopilot_parameters_new_flag = False
                db.session.commit()

                return jsonify(telemetry_instance.autopilot_parameters), 200

            except ValueError as e:
                return jsonify({"error": str(e)}), 404

            except Exception as e:
                return jsonify({"error": str(e)}), 500

        @self._blueprint.route("/set/<int:instance_id>", methods=["POST"])
        def set_route(instance_id: int) -> tuple[dict[str, str], int]:
            """
            Set the autopilot parameters from the request data.

            Method: POST

            Parameters
            ----------
            instance_id
                The ID of the telemetry instance to set the autopilot parameters for.

            Returns
            -------
            tuple[dict[str, str], int]
                A tuple containing a success message and a status code of 200 if successful,
                or an error message and a status code of 404 if the instance is not found.
            """

            try:
                telemetry_instance: TelemetryTable | None = TelemetryTable.query.get(instance_id)
                if telemetry_instance is None:
                    raise ValueError("Instance not found.")

                new_parameters = request.json.get("autopilot_parameters")
                if not isinstance(new_parameters, dict):
                    raise TypeError("Invalid autopilot parameters format. Expected a dictionary.")

                telemetry_instance.autopilot_parameters = new_parameters
                telemetry_instance.autopilot_parameters_new_flag = True
                db.session.commit()

                return jsonify({"message": "Autopilot parameters updated successfully."}), 200

            except ValueError as e:
                return jsonify({"error": str(e)}), 404

            except TypeError as e:
                return jsonify({"error": str(e)}), 400

            except Exception as e:
                db.session.rollback()
                return jsonify({"error": str(e)}), 500

        return f"autopilot_parameters paths registered successfully: {self._blueprint.url_prefix}"
