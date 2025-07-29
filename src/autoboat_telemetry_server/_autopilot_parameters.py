"""
Routes
------
- `/autopilot_parameters/test`: Test route for autopilot parameters.
- `/autopilot_parameters/get`: Get the current autopilot parameters.
- `/autopilot_parameters/get_new`: Get the latest autopilot parameters if they haven't been seen yet.
- `/autopilot_parameters/set`: Set the autopilot parameters from the request data
"""

from flask import request, Blueprint
from typing import Literal

__all__ = ["AutopilotParametersEndpoint"]


class AutopilotParametersEndpoint:
    """Endpoint for handling autopilot parameters."""

    def __init__(self) -> None:
        self._blueprint = Blueprint(
            "autopilot_parameters_page", __name__, url_prefix="/autopilot_parameters"
        )
        self.autopilot_parameters = {}
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

            Returns
            -------
            Literal["autopilot_parameters route testing!"]
                Confirmation message for testing the autopilot parameters route.
            """

            return "autopilot_parameters route testing!"

        @self._blueprint.route("/get", methods=["GET"])
        def get_route() -> dict:
            """
            Get the current autopilot parameters.

            Returns
            -------
            dict
                The current autopilot parameters stored in the endpoint.
            """

            return self.autopilot_parameters

        @self._blueprint.route("/get_new", methods=["GET"])
        def get_new_route() -> dict:
            """
            Get the latest autopilot parameters if they haven't been seen yet.

            Returns
            -------
            dict
                The latest autopilot parameters if they are new, otherwise an empty dictionary.
            """

            if self.new_flag:
                self.new_flag = False
                return self.autopilot_parameters
            else:
                return {}

        @self._blueprint.route("/set", methods=["POST"])
        def set_route() -> str:
            """
            Set the autopilot parameters from the request data.

            Returns
            -------
            str
                Confirmation message indicating the autopilot parameters were updated successfully.
            """

            try:
                data = request.get_json()
                new_autopilot_parameters = data.get("value")
                self.autopilot_parameters = new_autopilot_parameters
                self.new_flag = True

            except Exception as e:
                return f"autopilot_parameters not updated successfully: {e!s}"

            return f"autopilot_parameters updated successfully: {self.autopilot_parameters}"

        return f"autopilot_parameters paths registered successfully: {self._blueprint.url_prefix}"
