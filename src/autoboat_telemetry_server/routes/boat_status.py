from flask import Blueprint, Response, jsonify, request
from typing import Literal, Any


class BoatStatusEndpoint:
    """Endpoint for handling boat status."""

    def __init__(self) -> None:
        self._blueprint = Blueprint("boat_status_page", __name__, url_prefix="/boat_status")
        self.boat_status: dict[str, Any] = {}
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

            Method: GET

            Returns
            -------
            Literal["boat_status route testing!"]
                Confirmation message for testing the boat status route.
            """

            return "boat_status route testing!"

        @self._blueprint.route("/get", methods=["GET"])
        def get_route() -> tuple[Response, int]:
            """
            Get the current boat status.

            Method: GET

            Returns
            -------
            tuple[Response, int]
                A tuple containing the JSON response of the boat status and the HTTP status code.
            """

            return jsonify(self.boat_status)

        @self._blueprint.route("/get_new", methods=["GET"])
        def get_new_route() -> tuple[Response, int]:
            """
            Get the latest boat status if it hasn't been seen yet.

            Method: GET

            Returns
            -------
            tuple[Response, int]
                A tuple containing the JSON response of the new boat status (or empty if none) and the HTTP status code.
            """

            if self.new_flag:
                self.new_flag = False
                return jsonify(self.boat_status), 200

            else:
                return jsonify({}), 200

        @self._blueprint.route("/set", methods=["POST"])
        def set_route() -> tuple[Response, int]:
            """
            Set the boat status from the request data.

            Method: POST

            Returns
            -------
            tuple[Response, int]
                A tuple containing a confirmation message and the HTTP status code.
            """

            try:
                new_status = request.json
                if not isinstance(new_status, dict):
                    raise TypeError("Invalid boat status format. Expected a dictionary.")

                self.boat_status = new_status
                self.new_flag = True

                return jsonify("Boat status updated successfully."), 200

            except TypeError as e:
                return jsonify(str(e)), 400

            except Exception as e:
                return jsonify(str(e)), 500

        return f"boat_status paths registered successfully: {self._blueprint.url_prefix}"
