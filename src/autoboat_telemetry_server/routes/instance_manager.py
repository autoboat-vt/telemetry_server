from flask import Blueprint, Response, jsonify
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
        def create_instance() -> tuple[Response, int]:
            """
            Create a new telemetry instance with optional payload overrides.

            Method: GET

            Returns
            -------
            tuple[Response, int]
                A tuple containing a JSON response with the new instance ID and a status code of 201.
            """

            new_instance = TelemetryTable(autopilot_parameters={}, boat_status={}, waypoints=[])
            db.session.add(new_instance)
            db.session.commit()

            return jsonify({"id": new_instance.instance_id}), 201

        @self._blueprint.route("/delete/<int:instance_id>", methods=["DELETE"])
        def delete_instance(instance_id: int) -> tuple[Response, int]:
            """
            Delete a telemetry instance by its ID.

            Method: DELETE

            Returns
            -------
            tuple[Response, int]
                A tuple containing a JSON response with confirmation or error message and a status code.
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

        @self._blueprint.route("/set_name/<int:instance_id>/<instance_name>", methods=["POST"])
        def set_instance_name(instance_id: int, instance_name: str) -> tuple[Response, int]:
            """
            Set the name of a telemetry instance.

            Method: POST

            Parameters
            ----------
            instance_id
                The ID of the telemetry instance to set the name for.
            instance_name
                The new name for the telemetry instance.

            Returns
            -------
            tuple[Response, int]
                A tuple containing a JSON response confirming the name has been set and a status code of 200.
            """

            try:
                telemetry_instance: TelemetryTable | None = TelemetryTable.query.get(instance_id)
                if telemetry_instance is None:
                    raise ValueError("Instance not found.")

                for instance in TelemetryTable.query.all():
                    if instance.instance_identifier == instance_name and instance.instance_id != instance_id:
                        raise ValueError("Instance name already exists.")

                telemetry_instance.instance_identifier = instance_name
                db.session.commit()

                return jsonify({"message": f"Instance {instance_id} name set to {instance_name}."}), 200

            except ValueError as e:
                return jsonify({"error": str(e)}), 404

            except Exception as e:
                db.session.rollback()
                return jsonify({"error": str(e)}), 500

        @self._blueprint.route("/get_name/<int:instance_id>", methods=["GET"])
        def get_instance_name(instance_id: int) -> Response:
            """
            Get the name of a telemetry instance by its ID.

            Method: GET

            Parameters
            ----------
            instance_id
                The ID of the telemetry instance to retrieve the name for.

            Returns
            -------
            Response
                A JSON response containing the instance name or an error message if the instance is not found.
            """

            telemetry_instance: TelemetryTable | None = TelemetryTable.query.get(instance_id)
            if telemetry_instance is None:
                return jsonify({"error": "Instance not found."}), 404

            return jsonify({"instance_name": telemetry_instance.instance_identifier}), 200

        @self._blueprint.route("/get_id/<instance_name>", methods=["GET"])
        def get_instance_id(instance_name: str) -> Response:
            """
            Get the ID of a telemetry instance by its name.

            Method: GET

            Parameters
            ----------
            instance_name
                The name of the telemetry instance to retrieve the ID for.

            Returns
            -------
            Response
                A JSON response containing the instance ID or an error message if the instance is not found.
            """

            telemetry_instance: TelemetryTable | None = TelemetryTable.query.filter_by(instance_identifier=instance_name).first()
            if telemetry_instance is None:
                return jsonify({"error": "Instance not found."}), 404

            return jsonify({"instance_id": telemetry_instance.instance_id}), 200

        @self._blueprint.route("/get_ids", methods=["GET"])
        def get_ids() -> tuple[Response, int]:
            """
            Return all telemetry instance IDs.

            Method: GET

            Returns
            -------
            tuple[Response, int]
                A tuple containing a JSON response with a list of IDs and a 200 status.
            """

            return jsonify({"ids": TelemetryTable.get_all_ids()}), 200

        return f"instance_manager routes registered successfully: {self._blueprint.url_prefix}"
