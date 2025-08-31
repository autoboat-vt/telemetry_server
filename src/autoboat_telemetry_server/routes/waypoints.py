from flask import Blueprint, Response, jsonify, request
from typing import Literal


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

            Method: GET

            Returns
            -------
            Literal["waypoints route testing!"]
                Confirmation message for testing the waypoints route.
            """

            return "waypoints route testing!"

        @self._blueprint.route("/get", methods=["GET"])
        def get_route() -> tuple[Response, int]:
            """
            Get the current waypoints.

            Method: GET

            Returns
            -------
            tuple[Response, int]
                A tuple containing the JSON response of the waypoints and the HTTP status code.
            """

            return jsonify(self.waypoints), 200

        @self._blueprint.route("/get_new", methods=["GET"])
        def get_new_route() -> tuple[Response, int]:
            """
            Get the latest waypoints if they haven't been seen yet.

            Method: GET

            Returns
            -------
            tuple[Response, int]
                A tuple containing the JSON response of the new waypoints (or empty if none) and the HTTP status code.
            """

            if self.new_flag:
                self.new_flag = False
                return jsonify(self.waypoints), 200

            else:
                return jsonify({}), 200

        @self._blueprint.route("/set", methods=["POST"])
        def set_route() -> tuple[Response, int]:
            """
            Set the waypoints from the request data.

            Method: POST

            Returns
            -------
            tuple[Response, int]
                A tuple containing a confirmation message and the HTTP status code.
            """

            try:
                new_waypoints = request.json
                if not isinstance(new_waypoints, list):
                    raise TypeError("Invalid waypoints format. Expected a list of lists of floats.")

                self.waypoints = new_waypoints
                self.new_flag = True

                return jsonify("Waypoints updated successfully."), 200

            except TypeError as e:
                return jsonify(str(e)), 400

            except Exception as e:
                return jsonify(str(e)), 500

        return f"waypoints paths registered successfully: {self._blueprint.url_prefix}"
