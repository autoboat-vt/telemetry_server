import ctypes
from typing import ClassVar, Literal

from flask import Blueprint, jsonify, request

from autoboat_telemetry_server import shared_lock_manager
from autoboat_telemetry_server.models import TelemetryTable, db
from autoboat_telemetry_server.types import ResponseType


class BoatStatusEndpoint:
    """Endpoint for handling boat status."""

    def __init__(self) -> None:
        self._blueprint = Blueprint(name="boat_status_page", import_name=__name__, url_prefix="/boat_status")
        self._register_routes()

    @property
    def blueprint(self) -> Blueprint:
        """Returns the Flask blueprint for autopilot parameters."""
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
        TelemetryTable
            The telemetry instance corresponding to the provided ID.

        Raises
        ------
        TypeError
            If the instance with the given ID does not exist.
        """

        instance = TelemetryTable.query.get(instance_id)

        if not isinstance(instance, TelemetryTable):
            raise TypeError("Instance not found.")

        return instance

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

        @self._blueprint.route("/get/<int:instance_id>", methods=["GET"])
        @shared_lock_manager.require_read_lock
        def get_route(instance_id: int) -> ResponseType:
            """
            Get the boat status for a specific telemetry instance.

            Method: GET

            Parameters
            ----------
            instance_id
                The ID of the telemetry instance to retrieve the boat status for.

            Returns
            -------
            ResponseType
                A tuple containing a JSON response with the boat status for the specified telemetry instance,
                or an error message if the instance is not found.
            """

            try:
                telemetry_instance = self._get_instance(instance_id)
                return jsonify(telemetry_instance.boat_status), 200

            except TypeError as e:
                return jsonify(str(e)), 404

            except Exception as e:
                return jsonify(str(e)), 500

        @self._blueprint.route("/get_new/<int:instance_id>", methods=["GET"])
        @shared_lock_manager.require_write_lock
        def get_new_route(instance_id: int) -> ResponseType:
            """
            Gets the boat status for a specific telemetry instance if it hasn't already been
            requested since the last update.

            Method: GET

            Parameters
            ----------
            instance_id
                The ID of the telemetry instance to retrieve the new boat status for.

            Returns
            -------
            ResponseType
                A tuple containing a JSON response with the boat status for the specified telemetry instance,
                or an empty dictionary if there is no new boat status, or an error message if the instance is not found.
            """

            try:
                telemetry_instance = self._get_instance(instance_id)
                if telemetry_instance.boat_status_new_flag is False:
                    return jsonify({}), 200

                telemetry_instance.boat_status_new_flag = False
                db.session.commit()

                return jsonify(telemetry_instance.boat_status), 200

            except TypeError as e:
                return jsonify(str(e)), 404

            except Exception as e:
                db.session.rollback()
                return jsonify(str(e)), 500

        @self._blueprint.route("/set/<int:instance_id>", methods=["POST"])
        @shared_lock_manager.require_write_lock
        def set_route(instance_id: int) -> ResponseType:
            """
            Set the boat status for a specific telemetry instance.

            Method: POST

            Parameters
            ----------
            instance_id
                The ID of the telemetry instance to set the boat status for.

            Returns
            -------
            ResponseType
                A tuple containing a JSON response confirming the boat status has been updated successfully,
                or an error message if the instance is not found or if the input format is invalid.
            """

            try:
                telemetry_instance = self._get_instance(instance_id)
                new_status = request.json
                if not isinstance(new_status, dict):
                    raise TypeError("Invalid boat status format. Expected a dictionary.")

                telemetry_instance.boat_status = new_status
                telemetry_instance.boat_status_new_flag = True
                db.session.commit()

                return jsonify("Boat status updated successfully."), 200

            except TypeError as e:
                return jsonify(str(e)), 404

            except Exception as e:
                db.session.rollback()
                return jsonify(str(e)), 500

        @self._blueprint.route("/set_fast/<int:instance_id>", methods=["POST"])
        @shared_lock_manager.require_write_lock
        def set_fast_route(instance_id: int) -> ResponseType:
            """
            Set the boat status for a specific telemetry instance using a fast update method that allows
            updating specific fields without needing to send the entire boat status object.

            Method: POST

            Parameters
            ----------
            instance_id
                The ID of the telemetry instance to set the boat status for.

            Returns
            -------
            ResponseType
                A tuple containing a JSON response confirming the boat status has been updated successfully,
                or an error message if the instance is not found or if the input format is invalid.
            """

            def form_payload_class(mapping: list[list[str]]) -> type[ctypes.LittleEndianStructure]:
                """
                Dynamically forms a ``ctypes`` ``LittleEndianStructure`` class based on the provided mapping of field names and types.

                Parameters
                ----------
                mapping
                    A list of pairs of field names and their corresponding data types for the boat status.

                Returns
                -------
                type[ctypes.LittleEndianStructure]
                    A dynamically created ``ctypes`` ``LittleEndianStructure`` class with fields
                    defined according to the provided mapping.
                """

                class Payload(ctypes.LittleEndianStructure):
                    _pack_: ClassVar[int] = 1
                    _fields_: ClassVar[tuple[tuple[str, ctypes._SimpleCData], ...]] = tuple(
                        (field_name, getattr(ctypes, field_type)) for field_name, field_type in mapping
                    )

                return Payload

            try:
                telemetry_instance = self._get_instance(instance_id)
                if not telemetry_instance.boat_status_mapping:
                    raise TypeError("Set variable mapping for the instance before using the fast update route.")

                update_data: bytes = request.get_data(cache=False)
                try:
                    payload_class = form_payload_class(telemetry_instance.boat_status_mapping)
                    payload = payload_class.from_buffer_copy(update_data)
                    updated_status = {
                        field_name: getattr(payload, field_name) for field_name, _ in telemetry_instance.boat_status_mapping
                    }

                except Exception as e:
                    raise TypeError(f"Error creating temporary payload structure: {e}") from e

                telemetry_instance.boat_status = updated_status
                telemetry_instance.boat_status_new_flag = True
                db.session.commit()

                return jsonify("Boat status updated successfully using fast update method."), 200

            except TypeError as e:
                return jsonify(str(e)), 404

            except ValueError as e:
                return jsonify(str(e)), 400

            except Exception as e:
                db.session.rollback()
                return jsonify(str(e)), 500

        @self._blueprint.route("/set_mapping/<int:instance_id>", methods=["POST"])
        @shared_lock_manager.require_write_lock
        def set_mapping_route(instance_id: int) -> ResponseType:
            """
            Set the boat status mapping for a specific telemetry instance.

            Method: POST

            Parameters
            ----------
            instance_id
                The ID of the telemetry instance to set the boat status mapping for.

            Returns
            -------
            ResponseType
                A tuple containing a JSON response confirming the boat status mapping has been updated successfully,
                or an error message if the instance is not found or if the input format is invalid.
            """

            def is_valid_pair(item: list) -> bool:
                return isinstance(item, list) and len(item) == 2 and all(isinstance(subitem, str) for subitem in item)

            try:
                telemetry_instance = self._get_instance(instance_id)
                new_mapping = request.json
                if not isinstance(new_mapping, list):
                    raise TypeError(f"Got: {new_mapping} of type {type(new_mapping)}. Expected {list}")

                if not all(is_valid_pair(item) for item in new_mapping):
                    raise TypeError(f"Got {new_mapping}. Expected {list[list[str]]} with format [[field_name, field_type], ...]")

                if not all(hasattr(ctypes, field_type) for _, field_type in new_mapping):
                    raise TypeError("Invalid field type in mapping. Each field type must correspond to a valid ctypes type.")

                telemetry_instance.boat_status_mapping = new_mapping
                db.session.commit()

                return jsonify("Boat status mapping updated successfully."), 200

            except TypeError as e:
                return jsonify(str(e)), 404

            except Exception as e:
                db.session.rollback()
                return jsonify(str(e)), 500

        return f"boat_status paths registered successfully: {self._blueprint.url_prefix}"
