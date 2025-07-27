"""
Routes
------
- `/boat_status/test`: Test route for boat status.
- `/boat_status/get`: Get the current boat status.
- `/boat_status/get_new`: Get the latest boat status if it hasn't been seen yet.
- `/boat_status/set`: Set the boat status from the request data.
"""

from flask import request, Blueprint
from typing import Literal

__all__ = ["BoatStatusEndpoint"]


class BoatStatusEndpoint:
    """Endpoint for handling boat status."""

    def __init__(self) -> None:
        self._blueprint = Blueprint(
            "boat_status_page", __name__, url_prefix="/boat_status"
        )
        self.boat_status = {}
        self.new_flag: bool = False
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

        @self._blueprint.route("/get", methods=["GET"])
        def get_route() -> dict:
            """
            Get the current boat status.

            Returns
            -------
            dict
                The current boat status stored in the endpoint.
            """

            return self.boat_status

        @self._blueprint.route("/get_new", methods=["GET"])
        def get_new_route() -> dict | None:
            """
            Get the latest boat status if it hasn't been seen yet.

            Returns
            -------
            dict | None
                The latest boat status if it is new, otherwise None.
            """

            if self.new_flag:
                self.new_flag = False
                return self.boat_status

            else:
                return None

        @self._blueprint.route("/set", methods=["POST"])
        def set_route() -> str:
            """
            Set the boat status from the request data.

            Returns
            -------
            str
                Confirmation message indicating the boat status has been set.
            """

            try:
                data = request.get_json()
                new_boat_status = data.get("value")
                self.boat_status = new_boat_status
                self.new_flag = True

            except Exception as e:
                return f"boat_status not updated successfully: {e!s}"

            return f"boat_status updated successfully: {self.boat_status}"

        return (
            f"boat_status paths registered successfully: {self._blueprint.url_prefix}"
        )
