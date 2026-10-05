import json
from typing import Literal

from flask import Blueprint, jsonify, request

from autoboat_telemetry_server import shared_lock_manager
from autoboat_telemetry_server.models import TelemetryTable, db
from autoboat_telemetry_server.types import ResponseType

# GeoJSON document types the server accepts for the obstacle set - see
# autoboat_vt docs/telemetry_server_obstacles_and_path_routes.md
_GEOJSON_TYPES = ("FeatureCollection", "Feature")


class ObstaclesEndpoint:
    """Endpoint for handling the obstacle polygon GeoJSON documents."""

    def __init__(self) -> None:
        self._blueprint = Blueprint(name="obstacles_page", import_name=__name__, url_prefix="/obstacles")
        self._register_routes()

    @property
    def blueprint(self) -> Blueprint:
        """Returns the Flask blueprint for obstacles."""

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
        Registers the routes for the obstacles endpoint.

        Returns
        -------
        `str`
            Confirmation message indicating the routes have been registered successfully.
        """

        @self._blueprint.route("/test", methods=["GET"])
        def test_route() -> Literal["obstacles route testing!"]:
            """
            Test route for obstacles.

            Method: GET

            Returns
            -------
            `Literal["obstacles route testing!"]`
                Confirmation message for testing the obstacles route.
            """

            return "obstacles route testing!"

        @self._blueprint.route("/get/<int:instance_id>", methods=["GET"])
        @shared_lock_manager.require_read_lock
        def get_route(instance_id: int) -> ResponseType:
            """
            Get the stored obstacle GeoJSON document for a telemetry instance.

            Method: GET

            Parameters
            ----------
            instance_id
                The ID of the telemetry instance to retrieve the obstacles for.

            Returns
            -------
            :type:`ResponseType`
                A tuple containing a JSON response with the obstacle GeoJSON document,
                or an error message if the instance is not found.
            """

            try:
                telemetry_instance = self._get_instance(instance_id)
                return jsonify(telemetry_instance.obstacles), 200

            except TypeError as e:
                return jsonify(str(e)), 404

            except Exception as e:
                return jsonify(str(e)), 500

        @self._blueprint.route("/get_new/<int:instance_id>", methods=["GET"])
        @shared_lock_manager.require_read_lock
        def get_new_route(instance_id: int) -> ResponseType:
            """
            Get the obstacle GeoJSON document for a telemetry instance.

            Method: GET

            Unlike ``waypoints/get_new`` this is a pure read - there is no flag
            to clear - so it uses ``require_read_lock``, not the write lock (see
            python-source.instructions.md#Lock decorators and AGENTS.md #3.6).
            The telemetry node de-duplicates client side by comparing the
            returned document against the previous response, and returning the
            current value on every call is permitted by the contract (see
            autoboat_vt docs/telemetry_server_obstacles_and_path_routes.md).

            Parameters
            ----------
            instance_id
                The ID of the telemetry instance to retrieve the obstacles for.

            Returns
            -------
            :type:`ResponseType`
                A tuple containing a JSON response with the obstacle GeoJSON document,
                or an error message if the instance is not found.
            """

            try:
                telemetry_instance = self._get_instance(instance_id)
                return jsonify(telemetry_instance.obstacles), 200

            except TypeError as e:
                return jsonify(str(e)), 404

            except Exception as e:
                return jsonify(str(e)), 500

        @self._blueprint.route("/set/<int:instance_id>", methods=["POST"])
        @shared_lock_manager.require_write_lock
        def set_route(instance_id: int) -> ResponseType:
            """
            Set the obstacle polygons for a telemetry instance.

            Method: POST

            The body is a JSON-encoded string whose value is a GeoJSON document
            (double-encoded, the convention for ``dict`` payloads - see
            autoboat_vt docs/telemetry_server_obstacles_and_path_routes.md).

            Parameters
            ----------
            instance_id
                The ID of the telemetry instance to set the obstacles for.

            Returns
            -------
            :type:`ResponseType`
                A tuple containing a JSON response confirming the obstacles have been
                updated successfully, or an error message if the instance is not found
                or the payload is invalid.
            """

            try:
                telemetry_instance = self._get_instance(instance_id)

                # double-encoded dict payload: request.json is a JSON *string*
                # that must be decoded once to get the GeoJSON object.
                try:
                    obstacles_data = json.loads(request.json)
                except (TypeError, ValueError) as e:
                    raise TypeError("Invalid obstacles data format. Expected a JSON-encoded GeoJSON document.") from e

                if not isinstance(obstacles_data, dict):
                    raise TypeError("Invalid obstacles data format. Expected a GeoJSON object.")

                if obstacles_data.get("type") not in _GEOJSON_TYPES:
                    raise TypeError(f"Invalid GeoJSON type. Expected one of {_GEOJSON_TYPES}.")

                # track the flag explicitly rather than relying on MutableDict's
                # top-level change detection - see
                # python-source.instructions.md#JSON column mutation tracking
                telemetry_instance.obstacles_new_flag = telemetry_instance.obstacles != obstacles_data
                telemetry_instance.obstacles = obstacles_data
                db.session.commit()

                return jsonify("Obstacles updated successfully."), 200

            except TypeError as e:
                return jsonify(str(e)), 400

            except Exception as e:
                db.session.rollback()
                return jsonify(str(e)), 500

        return f"obstacles paths registered successfully: {self._blueprint.url_prefix}"
