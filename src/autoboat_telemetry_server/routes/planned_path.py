from typing import Literal

from flask import Blueprint, jsonify, request

from autoboat_telemetry_server import shared_lock_manager
from autoboat_telemetry_server.models import TelemetryTable, db
from autoboat_telemetry_server.types import ResponseType


class PlannedPathEndpoint:
    """Endpoint for handling the obstacle-avoiding planned path."""

    def __init__(self) -> None:
        self._blueprint = Blueprint(name="path_page", import_name=__name__, url_prefix="/path")
        self._register_routes()

    @property
    def blueprint(self) -> Blueprint:
        """Returns the Flask blueprint for the planned path."""

        return self._blueprint

    def _get_instance(self, instance_id: int) -> TelemetryTable:
        """
        Helper function to retrieve a telemetry instance by its ID.

        Parameters
        ----------
        instance_id
            The ID of the telemetry instance to retrieve.

        Returns
        -------
        :class:`TelemetryTable`
            The telemetry instance corresponding to the provided ID.

        Raises
        ------
        :class:`TypeError`
            If the instance with the given ID does not exist.
        """

        instance = db.session.get(TelemetryTable, instance_id)

        if not isinstance(instance, TelemetryTable):
            raise TypeError("Instance not found.")

        return instance

    def _register_routes(self) -> str:
        """
        Registers the routes for the planned path endpoint.

        Returns
        -------
        `str`
            Confirmation message indicating the routes have been registered successfully.
        """

        @self._blueprint.route("/test", methods=["GET"])
        def test_route() -> Literal["path route testing!"]:
            """
            Test route for the planned path.

            Method: GET

            Returns
            -------
            `Literal["path route testing!"]`
                Confirmation message for testing the planned path route.
            """

            return "path route testing!"

        @self._blueprint.route("/get/<int:instance_id>", methods=["GET"])
        @shared_lock_manager.require_read_lock
        def get_route(instance_id: int) -> ResponseType:
            """
            Get the stored planned path for a telemetry instance.

            Method: GET

            Parameters
            ----------
            instance_id
                The ID of the telemetry instance to retrieve the planned path for.

            Returns
            -------
            :type:`ResponseType`
                A tuple containing a JSON response with the planned path as a list of
                [latitude, longitude] points, or an error message if the instance is not found.
            """

            try:
                telemetry_instance = self._get_instance(instance_id)
                return jsonify(telemetry_instance.planned_path), 200

            except TypeError as e:
                return jsonify(str(e)), 404

            except Exception as e:
                return jsonify(str(e)), 500

        @self._blueprint.route("/get_new/<int:instance_id>", methods=["GET"])
        @shared_lock_manager.require_read_lock
        def get_new_route(instance_id: int) -> ResponseType:
            """
            Get the stored planned path for a telemetry instance.

            Method: GET

            Mirrors ``waypoints/get_new`` in shape (a list of points) but is a
            pure read: the planned path is display-only, so there is no "new"
            flag to clear. The ground station polls ``path/get`` directly; this
            route exists so the advertised ``get_new_planned_path`` key is valid.

            Parameters
            ----------
            instance_id
                The ID of the telemetry instance to retrieve the planned path for.

            Returns
            -------
            :type:`ResponseType`
                A tuple containing a JSON response with the planned path as a list of
                [latitude, longitude] points, or an error message if the instance is not found.
            """

            try:
                telemetry_instance = self._get_instance(instance_id)
                return jsonify(telemetry_instance.planned_path), 200

            except TypeError as e:
                return jsonify(str(e)), 404

            except Exception as e:
                return jsonify(str(e)), 500

        @self._blueprint.route("/set/<int:instance_id>", methods=["POST"])
        @shared_lock_manager.require_write_lock
        def set_route(instance_id: int) -> ResponseType:
            """
            Set the planned path for a telemetry instance.

            Method: POST

            The body is a raw JSON array of [latitude, longitude] points, the
            same encoding the waypoints routes use for list payloads.

            Parameters
            ----------
            instance_id
                The ID of the telemetry instance to set the planned path for.

            Returns
            -------
            :type:`ResponseType`
                A tuple containing a JSON response confirming the planned path has been
                updated successfully, or an error message if the instance is not found
                or the payload is invalid.
            """

            try:
                telemetry_instance = self._get_instance(instance_id)
                path_data = request.json

                if not isinstance(path_data, list):
                    raise TypeError("Invalid planned path data format. Expected a list of [latitude, longitude] points.")

                for point in path_data:
                    if not (isinstance(point, (list, tuple)) and len(point) == 2):
                        raise TypeError("Invalid path point format. Each point must be a list or tuple of two coordinates.")

                    if not all(isinstance(coord, (int, float)) for coord in point):
                        raise TypeError("Invalid coordinate type. Each coordinate must be an integer or float.")

                # MutableList rejects tuples — see python-source.instructions.md#MutableList rejects tuples
                telemetry_instance.planned_path = path_data
                db.session.commit()

                return jsonify("Planned path updated successfully."), 200

            except TypeError as e:
                return jsonify(str(e)), 400

            except Exception as e:
                db.session.rollback()
                return jsonify(str(e)), 500

        return f"path paths registered successfully: {self._blueprint.url_prefix}"
