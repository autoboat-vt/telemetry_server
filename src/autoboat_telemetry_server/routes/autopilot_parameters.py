from flask import Blueprint, Response, jsonify, request
from typing import Literal
from autoboat_telemetry_server.models import TelemetryTable, db


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

            Method: GET

            Returns
            -------
            Literal["autopilot_parameters route testing!"]
                Confirmation message for testing the autopilot parameters route.
            """

            return "autopilot_parameters route testing!"

        @self._blueprint.route("/get/<int:instance_id>", methods=["GET"])
        def get_route(instance_id: int) -> tuple[Response, int]:
            """
            Get the current autopilot parameters.

            Method: GET

            Parameters
            ----------
            instance_id
                The ID of the telemetry instance to retrieve the autopilot parameters for.

            Returns
            -------
            tuple[Response, int]
                A tuple containing a JSON response with the autopilot parameters for the specified telemetry instance,
                or an error message if the instance is not found.
            """

            try:
                telemetry_instance = TelemetryTable.query.get(instance_id)
                if not isinstance(telemetry_instance, TelemetryTable):
                    raise TypeError("Instance not found.")

                return jsonify(telemetry_instance.autopilot_parameters), 200

            except TypeError as e:
                return jsonify(str(e)), 404

            except Exception as e:
                return jsonify(str(e)), 500

        @self._blueprint.route("/get_new/<int:instance_id>", methods=["GET"])
        def get_new_route(instance_id: int) -> tuple[Response, int]:
            """
            Get the latest autopilot parameters if they haven't been seen yet.

            Method: GET

            Parameters
            ----------
            instance_id
                The ID of the telemetry instance to retrieve the new autopilot parameters for.

            Returns
            -------
            tuple[Response, int]
                A tuple containing a JSON response with the new autopilot parameters for the specified telemetry instance,
                or an empty dictionary if there are no new parameters, or an error message if the instance is not found.
            """

            try:
                telemetry_instance = TelemetryTable.query.get(instance_id)
                if not isinstance(telemetry_instance, TelemetryTable):
                    raise TypeError("Instance not found.")

                if telemetry_instance.autopilot_parameters_new_flag is False:
                    return jsonify({}), 200

                telemetry_instance.autopilot_parameters_new_flag = False
                db.session.commit()

                return jsonify(telemetry_instance.autopilot_parameters), 200

            except TypeError as e:
                return jsonify(str(e)), 404

            except Exception as e:
                return jsonify(str(e)), 500

        @self._blueprint.route("/get_default/<int:instance_id>", methods=["GET"])
        def get_default_route(instance_id: int) -> tuple[Response, int]:
            """
            Get the default autopilot parameters.

            Method: GET

            Parameters
            ----------
            instance_id
                The ID of the telemetry instance to retrieve the default autopilot parameters for.

            Returns
            -------
            tuple[Response, int]
                A tuple containing a JSON response with the default autopilot parameters for the specified telemetry instance,
                or an error message if the instance is not found.
            """

            try:
                telemetry_instance = TelemetryTable.query.get(instance_id)
                if not isinstance(telemetry_instance, TelemetryTable):
                    raise TypeError("Instance not found.")

                return jsonify(telemetry_instance.default_autopilot_parameters), 200

            except TypeError as e:
                return jsonify(str(e)), 404

            except Exception as e:
                return jsonify(str(e)), 500

        @self._blueprint.route("/set/<int:instance_id>", methods=["POST"])
        def set_route(instance_id: int) -> tuple[Response, int]:
            """
            Set the autopilot parameters from the request data.

            Method: POST

            Parameters
            ----------
            instance_id
                The ID of the telemetry instance to set the autopilot parameters for.

            Returns
            -------
            tuple[Response, int]
                A tuple containing a JSON response confirming the autopilot parameters have been updated successfully,
                or an error message if the instance is not found or if the input format is invalid.
            """

            try:
                telemetry_instance = TelemetryTable.query.get(instance_id)
                if not isinstance(telemetry_instance, TelemetryTable):
                    raise TypeError("Instance not found.")

                new_parameters = request.json
                if not isinstance(new_parameters, dict):
                    raise TypeError("Invalid autopilot parameters format. Expected a dictionary.")

                if telemetry_instance.default_autopilot_parameters != {}:
                    new_parameters_keys = list(new_parameters.keys())
                    if len(new_parameters_keys) == 1 and new_parameters_keys[0] in telemetry_instance.default_autopilot_parameters:
                        telemetry_instance.autopilot_parameters[new_parameters_keys[0]] = new_parameters[new_parameters_keys[0]]

                    elif new_parameters_keys == list(telemetry_instance.default_autopilot_parameters.keys()):
                        telemetry_instance.autopilot_parameters = new_parameters

                    else:
                        raise ValueError("Invalid keys in autopilot parameters.")

                else:
                    telemetry_instance.autopilot_parameters = new_parameters

                telemetry_instance.autopilot_parameters_new_flag = True
                db.session.commit()

                return jsonify("Autopilot parameters updated successfully."), 200

            except TypeError as e:
                return jsonify(str(e)), 400

            except ValueError as e:
                return jsonify(str(e)), 400

            except Exception as e:
                db.session.rollback()
                return jsonify(str(e)), 500

        @self._blueprint.route("/set_default/<int:instance_id>", methods=["POST"])
        def set_default_route(instance_id: int) -> tuple[Response, int]:
            """
            Set the default autopilot parameters from the request data.

            Method: POST

            Parameters
            ----------
            instance_id
                The ID of the telemetry instance to set the default autopilot parameters for.

            Returns
            -------
            tuple[Response, int]
                A tuple containing a JSON response confirming the default autopilot parameters have been updated successfully,
                or an error message if the instance is not found or if the input format is invalid.
            """

            try:
                telemetry_instance = TelemetryTable.query.get(instance_id)
                if not isinstance(telemetry_instance, TelemetryTable):
                    raise TypeError("Instance not found.")

                new_parameters = request.json
                if not isinstance(new_parameters, dict):
                    raise TypeError("Invalid default autopilot parameters format. Expected a dictionary.")

                # if default parameters are being updated, remove any existing keys that will no longer be valid
                if new_parameters != {}:
                    filtered_autopilot_parameters = {}
                    for key in new_parameters:
                        if key in telemetry_instance.default_autopilot_parameters:
                            filtered_autopilot_parameters[key] = new_parameters[key]

                    telemetry_instance.autopilot_parameters = filtered_autopilot_parameters

                telemetry_instance.default_autopilot_parameters = new_parameters
                db.session.commit()

                return jsonify("Default autopilot parameters updated successfully."), 200

            except TypeError as e:
                return jsonify(str(e)), 400

            except Exception as e:
                db.session.rollback()
                return jsonify(str(e)), 500

        return f"autopilot_parameters paths registered successfully: {self._blueprint.url_prefix}"
