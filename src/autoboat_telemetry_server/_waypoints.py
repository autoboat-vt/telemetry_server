"""
Routes
------
- `/waypoints/test`: Test route for waypoints.
- `/waypoints/get`: Get the current waypoints.
- `/waypoints/get_new`: Get the latest waypoints if they haven't been seen yet.
- `/waypoints/set`: Set the waypoints from the request data.
"""

from flask import request, Blueprint
from typing import Literal

__all__ = ["WaypointEndpoint"]


class WaypointEndpoint:
    """Endpoint for handling waypoints."""

    def __init__(self) -> None:
        self._blueprint = Blueprint("waypoints_page", __name__, url_prefix="/waypoints")
        self.waypoints: list[list[float]] = []
        self.new_flag: bool = False
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

        @self._blueprint.route("/get", methods=["GET"])
        def get_route() -> list[list[float]]:
            """
            Get the current waypoints.

            Returns
            -------
            list[list[float]]
                The current waypoints stored in the endpoint.
            """

            return self.waypoints

        @self._blueprint.route("/get_new", methods=["GET"])
        def get_new_route() -> list[list[float]] | list:
            """
            Get the latest waypoints if they haven't been seen yet.

            Returns
            -------
            list[list[float]] | list
                The latest waypoints if they are new, otherwise an empty list.
            """

            if self.new_flag:
                self.new_flag = False
                return self.waypoints

            else:
                return []

        @self._blueprint.route("/set", methods=["POST"])
        def set_route() -> str:
            """
            Set the waypoints from the request data.

            Returns
            -------
            str
                Confirmation message indicating the waypoints were updated successfully.
            """

            try:
                data = request.get_json()
                new_waypoints = data.get("value")
                self.waypoints = new_waypoints
                self.new_flag = True

            except Exception as e:
                return f"waypoints not updated successfully: {e!s}"

            return f"waypoints updated successfully: {self.waypoints}"

        return f"waypoints paths registered successfully: {self._blueprint.url_prefix}"
