from flask import Blueprint, jsonify
from typing import Any, Literal
from autoboat_telemetry_server.models import TelemetryTable, db


class InstanceManagerEndpoint:
    """Endpoint for managing instances."""

    def __init__(self) -> None:
        self._blueprint = Blueprint("instance_manager_page", __name__, url_prefix="/instance_manager")
        self._register_routes()

    @property
    def blueprint(self) -> Blueprint:
        """Returns the Flask blueprint for instance management."""

        return self._blueprint

    def _register_routes(self) -> str:
        """
        Registers the routes for the instance management endpoint.

        Returns
        -------
        str
            Confirmation message indicating the routes have been registered successfully.
        """

        @self._blueprint.route("/create", methods=["GET"])
        def create_instance() -> tuple[dict[str, Any], Literal[201]]:
            """
            Create a new telemetry instance with optional payload overrides.

            Method: GET

            Returns
            -------
            tuple[dict[str, Any], Literal[201]]
                A tuple containing a JSON response with the new instance ID and a status code of 201
            """

            new_instance = TelemetryTable(autopilot_parameters={}, boat_status={}, waypoints=[])
            db.session.add(new_instance)
            db.session.commit()

            return jsonify(
                {"message": f"Successfully created instance {new_instance.instance_id}.", "id": new_instance.instance_id}
            ), 201

        @self._blueprint.route("/delete/<int:instance_id>", methods=["DELETE"])
        def delete_instance(instance_id: int) -> tuple[dict[str, Any], int]:
            """
            Delete a telemetry instance by its ID.

            Method: DELETE

            Parameters
            ----------
            instance_id
                The ID of the telemetry instance to delete.

            Returns
            -------
            tuple[dict[str, Any], int]
                A tuple containing an empty JSON response and a status code of 204 if successful,
                or an error message and a status code of 404 if the instance is not found.
            """

            try:
                instance = TelemetryTable.query.get(instance_id)
                if not instance:
                    raise ValueError("Instance not found.")

                db.session.delete(instance)
                db.session.commit()
                return jsonify({"message": f"Successfully deleted instance {instance_id}."}), 204

            except ValueError as e:
                return jsonify({"error": str(e)}), 404

            except Exception as e:
                db.session.rollback()
                return jsonify({"error": str(e)}), 500

        @self._blueprint.route("/get_ids", methods=["GET"])
        def get_ids() -> tuple[dict[str, list[int]], Literal[200]]:
            """
            Return all telemetry instance IDs.

            Method: GET

            Returns
            -------
            tuple[dict[str, list[int]], Literal[200]]
                A tuple containing a JSON response with a list of instance IDs and a status code of 200.
            """

            return jsonify({"ids": TelemetryTable.get_all_ids()}), 200

        return f"instance_manager routes registered successfully: {self._blueprint.url_prefix}"
