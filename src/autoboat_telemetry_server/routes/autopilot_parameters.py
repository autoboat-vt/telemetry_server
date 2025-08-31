from flask import Blueprint, Response, jsonify, request
from typing import Literal, Any


class AutopilotParametersEndpoint:
    """Endpoint for handling autopilot parameters."""

    def __init__(self) -> None:
        self._blueprint = Blueprint("autopilot_parameters_page", __name__, url_prefix="/autopilot_parameters")
        self.autopilot_parameters: dict[str, Any] = {}
        self.default_autopilot_parameters: dict[str, Any] = {}
        self.new_flag: bool = False
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

        @self._blueprint.route("/get", methods=["GET"])
        def get_route() -> tuple[Response, int]:
            """
            Get the current autopilot parameters.

            Method: GET

            Returns
            -------
            tuple[Response, int]
                A tuple containing the JSON response of the autopilot parameters and the HTTP status code.
            """

            return jsonify(self.autopilot_parameters), 200

        @self._blueprint.route("/get_new", methods=["GET"])
        def get_new_route() -> tuple[Response, int]:
            """
            Get the latest autopilot parameters if they haven't been seen yet.

            Method: GET

            Returns
            -------
            tuple[Response, int]
                A tuple containing the JSON response of the autopilot parameters if new,
                otherwise an empty JSON object, along with the HTTP status code.
            """

            if self.new_flag:
                self.new_flag = False
                return jsonify(self.autopilot_parameters), 200

            else:
                return jsonify({}), 200

        @self._blueprint.route("/get_default", methods=["GET"])
        def get_default_route() -> tuple[Response, int]:
            """
            Get the default autopilot parameters.

            Method: GET

            Returns
            -------
            tuple[Response, int]
                A tuple containing the JSON response of the default autopilot parameters and the HTTP status code.
            """

            return jsonify(self.default_autopilot_parameters), 200

        @self._blueprint.route("/set", methods=["POST"])
        def set_route() -> tuple[Response, int]:
            """
            Set the autopilot parameters from the request data.

            Method: POST

            Returns
            -------
            tuple[Response, int]
                A tuple containing a success message or error message and the corresponding HTTP status code.
            """

            try:
                new_parameters = request.json
                if not isinstance(new_parameters, dict):
                    raise TypeError("Invalid autopilot parameters format. Expected a dictionary.")

                if self.default_autopilot_parameters != {}:
                    new_parameters_keys = list(new_parameters.keys())
                    if len(new_parameters_keys) == 1 and new_parameters_keys[0] in self.default_autopilot_parameters:
                        self.autopilot_parameters[new_parameters_keys[0]] = new_parameters[new_parameters_keys[0]]

                    elif new_parameters_keys == list(self.default_autopilot_parameters.keys()):
                        self.autopilot_parameters = new_parameters

                    else:
                        raise ValueError("Invalid keys in autopilot parameters.")

                else:
                    self.autopilot_parameters = new_parameters

                self.new_flag = True
                return jsonify("Autopilot parameters updated successfully."), 200

            except TypeError as e:
                return jsonify(str(e)), 400

            except ValueError as e:
                return jsonify(str(e)), 400

            except Exception as e:
                return jsonify(str(e)), 500

        @self._blueprint.route("/set_default", methods=["POST"])
        def set_default_route() -> tuple[Response, int]:
            """
            Set the default autopilot parameters from the request data.

            Method: POST

            Returns
            -------
            tuple[Response, int]
                A tuple containing a success message or error message and the corresponding HTTP status code.
            """

            try:
                new_default_parameters = request.json
                if not isinstance(new_default_parameters, dict):
                    raise TypeError("Invalid default autopilot parameters format. Expected a dictionary.")

                if new_default_parameters != {}:
                    filtered_autopilot_parameters = {}
                    for key in new_default_parameters:
                        if key in self.default_autopilot_parameters:
                            filtered_autopilot_parameters[key] = new_default_parameters[key]

                    self.autopilot_parameters = filtered_autopilot_parameters

                self.default_autopilot_parameters = new_default_parameters
                return jsonify("Default autopilot parameters updated successfully."), 200

            except TypeError as e:
                return jsonify(str(e)), 400

            except Exception as e:
                return jsonify(str(e)), 500

        return f"autopilot_parameters paths registered successfully: {self._blueprint.url_prefix}"
