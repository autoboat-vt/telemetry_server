from flask import Blueprint, Response, jsonify
from typing import Literal
from datetime import datetime, timedelta, UTC

from autoboat_telemetry_server.models import TelemetryTable, db
from autoboat_telemetry_server import lock_manager


class InstanceManagerEndpoint:
    """Endpoint for managing instances."""

    def __init__(self) -> None:
        self._blueprint = Blueprint(name="instance_manager_page", import_name=__name__, url_prefix="/instance_manager")
        self._lock_manager = lock_manager
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

        @self._blueprint.route("/test", methods=["GET"])
        def test_route() -> Literal["instance_manager route testing!"]:
            """
            Test route for instance management.

            Method: GET

            Returns
            -------
            Literal["instance_manager route testing!"]
                Confirmation message for testing the instance management route.
            """

            return "instance_manager route testing!"

        @self._blueprint.route("/create", methods=["GET"])
        @lock_manager.require_write_lock
        def create_instance() -> tuple[Response, int]:
            """
            Create a new telemetry instance with optional payload overrides.

            Method: GET

            Returns
            -------
            tuple[Response, int]
                A tuple containing a JSON response with the new instance ID and a status code of 200.
            """

            try:
                new_instance = TelemetryTable(
                    default_autopilot_parameters={},
                    autopilot_parameters={},
                    boat_status={},
                    waypoints=[],
                )
                db.session.add(new_instance)
                db.session.commit()

                return jsonify(new_instance.instance_id), 200

            except Exception as e:
                db.session.rollback()
                return jsonify(str(e)), 500

        @self._blueprint.route("/delete/<int:instance_id>", methods=["DELETE"])
        @lock_manager.require_write_lock
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
                telemetry_instance = TelemetryTable.query.get(instance_id)
                if not isinstance(telemetry_instance, TelemetryTable):
                    raise TypeError("Instance not found.")

                db.session.delete(telemetry_instance)
                db.session.commit()
                return jsonify(f"Successfully deleted instance {instance_id}."), 200

            except TypeError as e:
                return jsonify(str(e)), 404

            except Exception as e:
                db.session.rollback()
                return jsonify(str(e)), 500

        @self._blueprint.route("/delete_all", methods=["DELETE"])
        @lock_manager.require_write_lock
        def delete_all_instances() -> tuple[Response, int]:
            """
            Delete all telemetry instances.

            Method: DELETE

            Returns
            -------
            tuple[Response, int]
                A tuple containing a JSON response with confirmation or error message and a status code.
            """

            try:
                num_deleted = db.session.query(TelemetryTable).delete()
                db.session.commit()
                return jsonify(f"Successfully deleted {num_deleted} instances."), 200

            except Exception as e:
                db.session.rollback()
                return jsonify(str(e)), 500

        @self._blueprint.route("/clean_instances", methods=["DELETE"])
        @lock_manager.require_write_lock
        def clean_instances() -> tuple[Response, int]:
            """
            Delete all inactive telemetry instances.

            Method: DELETE

            Returns
            -------
            tuple[Response, int]
                A tuple containing a JSON response with confirmation or error message and a status code.
            """

            try:
                timeout = 5.0  # minutes
                cutoff = datetime.now(UTC) - timedelta(minutes=timeout)
                num_deleted = (
                    db.session.query(TelemetryTable).filter(TelemetryTable.updated_at < cutoff).delete(synchronize_session=False)
                )
                db.session.commit()
                return jsonify(f"Successfully deleted {num_deleted} inactive instances."), 200

            except Exception as e:
                db.session.rollback()
                return jsonify(str(e)), 500

        @self._blueprint.route("/set_user/<int:instance_id>/<user_name>", methods=["POST"])
        @lock_manager.require_write_lock
        def set_instance_user(instance_id: int, user_name: str) -> tuple[Response, int]:
            """
            Set the user of a telemetry instance.

            Method: POST

            Parameters
            ----------
            instance_id
                The ID of the telemetry instance to set the user for.
            user_name
                The user name to assign to the telemetry instance.

            Returns
            -------
            tuple[Response, int]
                A tuple containing a JSON response confirming the user has been set and a status code of 200.
            """

            try:
                telemetry_instance = TelemetryTable.query.get(instance_id)
                if not isinstance(telemetry_instance, TelemetryTable):
                    raise TypeError("Instance not found.")

                telemetry_instance.user = user_name
                db.session.commit()

                return jsonify(f"Instance {instance_id} user set to {user_name}."), 200

            except TypeError as e:
                return jsonify(str(e)), 404

            except ValueError as e:
                return jsonify(str(e)), 400

            except Exception as e:
                db.session.rollback()
                return jsonify(str(e)), 500

        @self._blueprint.route("/get_user/<int:instance_id>", methods=["GET"])
        @lock_manager.require_read_lock
        def get_instance_user(instance_id: int) -> tuple[Response, int]:
            """
            Get the user of a telemetry instance by its ID.

            Method: GET

            Parameters
            ----------
            instance_id
                The ID of the telemetry instance to retrieve the user for.

            Returns
            -------
            tuple[Response, int]
                A tuple containing a JSON response with the instance user or an error message if the instance is not found.
            """

            try:
                telemetry_instance = TelemetryTable.query.get(instance_id)
                if not isinstance(telemetry_instance, TelemetryTable):
                    raise TypeError("Instance not found.")

                return jsonify(telemetry_instance.user), 200

            except TypeError as e:
                return jsonify(str(e)), 404

            except Exception as e:
                return jsonify(str(e)), 500

        @self._blueprint.route("/set_name/<int:instance_id>/<instance_name>", methods=["POST"])
        @lock_manager.require_write_lock
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
                telemetry_instance = TelemetryTable.query.get(instance_id)
                if not isinstance(telemetry_instance, TelemetryTable):
                    raise TypeError("Instance not found.")

                for instance in TelemetryTable.query.all():
                    if instance.instance_identifier == instance_name and instance.instance_id != instance_id:
                        raise ValueError("Instance name already exists.")

                telemetry_instance.instance_identifier = instance_name
                db.session.commit()

                return jsonify(f"Instance {instance_id} name set to {instance_name}."), 200

            except TypeError as e:
                return jsonify(str(e)), 404

            except ValueError as e:
                return jsonify(str(e)), 400

            except Exception as e:
                db.session.rollback()
                return jsonify(str(e)), 500

        @self._blueprint.route("/get_name/<int:instance_id>", methods=["GET"])
        @lock_manager.require_read_lock
        def get_instance_name(instance_id: int) -> tuple[Response, int]:
            """
            Get the name of a telemetry instance by its ID.

            Method: GET

            Parameters
            ----------
            instance_id
                The ID of the telemetry instance to retrieve the name for.

            Returns
            -------
            tuple[Response, int]
                A tuple containing a JSON response with the instance name or an error message if the instance is not found.
            """

            try:
                telemetry_instance = TelemetryTable.query.get(instance_id)
                if not isinstance(telemetry_instance, TelemetryTable):
                    raise TypeError("Instance not found.")

                return jsonify(telemetry_instance.instance_identifier), 200

            except TypeError as e:
                return jsonify(str(e)), 404

            except Exception as e:
                return jsonify(str(e)), 500

        @self._blueprint.route("/get_id/<instance_name>", methods=["GET"])
        @lock_manager.require_read_lock
        def get_instance_id(instance_name: str) -> tuple[Response, int]:
            """
            Get the ID of a telemetry instance by its name.

            Method: GET

            Parameters
            ----------
            instance_name
                The name of the telemetry instance to retrieve the ID for.

            Returns
            -------
            tuple[Response, int]
                A tuple containing a JSON response with the instance ID or an error message if the instance is not found.
            """

            try:
                telemetry_instance: TelemetryTable | None = TelemetryTable.query.filter_by(instance_identifier=instance_name).first()
                if not isinstance(telemetry_instance, TelemetryTable):
                    raise TypeError("Instance not found.")

                return jsonify(telemetry_instance.instance_id), 200

            except TypeError as e:
                return jsonify(str(e)), 404

            except Exception as e:
                return jsonify(str(e)), 500

        @self._blueprint.route("/get_instance_info/<int:instance_id>", methods=["GET"])
        @lock_manager.require_read_lock
        def get_instance_info(instance_id: int) -> tuple[Response, int]:
            """
            Get detailed information about a telemetry instance by its ID.

            Method: GET

            Parameters
            ----------
            instance_id
                The ID of the telemetry instance to retrieve information for.

            Returns
            -------
            tuple[Response, int]
                A tuple containing a JSON response with the instance details and a 200 status,
                or an error message if the instance is not found.
            """

            try:
                telemetry_instance = TelemetryTable.query.get(instance_id)
                if not isinstance(telemetry_instance, TelemetryTable):
                    raise TypeError("Instance not found.")

                return jsonify(telemetry_instance.to_dict()), 200

            except TypeError as e:
                return jsonify(str(e)), 404

            except Exception as e:
                return jsonify(str(e)), 500

        @self._blueprint.route("/get_all_instance_info", methods=["GET"])
        @lock_manager.require_read_lock
        def get_all_instance_info() -> tuple[Response, int]:
            """
            Get detailed information about all telemetry instances.

            Method: GET

            Returns
            -------
            tuple[Response, int]
                A tuple containing a JSON response with a list of all instance details and a 200 status.
            """

            try:
                telemetry_instances: list[TelemetryTable] = TelemetryTable.query.all()
                instances_info = [instance.to_dict() for instance in telemetry_instances]

                return jsonify(instances_info), 200

            except Exception as e:
                return jsonify(str(e)), 500

        @self._blueprint.route("/get_ids", methods=["GET"])
        @lock_manager.require_read_lock
        def get_ids() -> tuple[Response, int]:
            """
            Return all telemetry instance IDs.

            Method: GET

            Returns
            -------
            tuple[Response, int]
                A tuple containing a JSON response with a list of IDs and a 200 status.
            """

            try:
                return jsonify(TelemetryTable.get_all_ids()), 200

            except Exception as e:
                return jsonify(str(e)), 500

        return f"instance_manager routes registered successfully: {self._blueprint.url_prefix}"
