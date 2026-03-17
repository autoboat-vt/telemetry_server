import ctypes
from typing import ClassVar, Literal

from flask import Blueprint, jsonify, request

from autoboat_telemetry_server import shared_lock_manager
from autoboat_telemetry_server.models import TelemetryTable, db
from autoboat_telemetry_server.types import BoatStatusMappingType, ResponseType


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

    def _normalize_mapping(self, mapping: list) -> BoatStatusMappingType:
        """
        Normalize mapping input into a tuple-of-tuples in the same order.

        Parameters
        ----------
        mapping``
            The input mapping to normalize, expected to be a list of ``[field_name, field_type]`` pairs.

        Returns
        -------
        BoatStatusMappingType
            Mapping normalized as ``list[list[str]]``.

        Raises
        ------
        TypeError
            If mapping structure or ctypes names are invalid.
        """

        if not isinstance(mapping, list):
            raise TypeError(f"Got: {mapping} of type {type(mapping)}. Expected list[list[str]]")

        normalized: BoatStatusMappingType = []
        for item in mapping:
            if not isinstance(item, list) or len(item) != 2:
                raise TypeError("Invalid mapping format. Expected sequence of [field_name, field_type] pairs.")

            field_name, field_type = item
            if not isinstance(field_name, str) or not isinstance(field_type, str):
                raise TypeError("Invalid mapping format. field_name and field_type must be strings.")

            if not hasattr(ctypes, field_type):
                raise TypeError(f"Invalid field type in mapping: {field_type}")

            normalized.append([field_name, field_type])

        return normalized

    def _decode_payload(self, update_data: bytes, mapping: BoatStatusMappingType) -> dict[str, int | float]:
        """
        Decode raw payload bytes into a dictionary using a tuple of tuples mapping.

        Parameters
        ----------
        update_data
            Raw bytes from request body.
        mapping
            Field mapping as a list of ``[field_name, field_type]`` pairs defining the structure of the payload.

        Returns
        -------
        dict[str, int | float]
            Decoded field values.

        Raises
        ------
        TypeError
            If payload length does not match the expected struct layout.
        """

        class AlignedPayload(ctypes.LittleEndianStructure):
            _fields_: ClassVar[tuple[tuple[str, ctypes._SimpleCData], ...]] = tuple(
                (field_name, getattr(ctypes, field_type)) for field_name, field_type in mapping
            )

        class PackedPayload(ctypes.LittleEndianStructure):
            _pack_ = 1
            _fields_: ClassVar[tuple[tuple[str, ctypes._SimpleCData], ...]] = tuple(
                (field_name, getattr(ctypes, field_type)) for field_name, field_type in mapping
            )

        aligned_size = ctypes.sizeof(AlignedPayload)
        packed_size = ctypes.sizeof(PackedPayload)
        payload_size = len(update_data)

        if payload_size == aligned_size:
            payload = AlignedPayload.from_buffer_copy(update_data)
            return {field_name: getattr(payload, field_name) for field_name, _ in AlignedPayload._fields_}

        if payload_size == packed_size:
            payload = PackedPayload.from_buffer_copy(update_data)
            return {field_name: getattr(payload, field_name) for field_name, _ in PackedPayload._fields_}

        raise TypeError(
            f"Payload length mismatch. Got {payload_size} bytes, expected aligned={aligned_size} or packed={packed_size} bytes."
        )

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

            try:
                telemetry_instance = self._get_instance(instance_id)
                if not telemetry_instance.boat_status_mapping:
                    raise TypeError("Set variable mapping for the instance before using the fast update route.")

                update_data: bytes = request.get_data(cache=False)
                updated_status = self._decode_payload(update_data, telemetry_instance.boat_status_mapping)

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

            try:
                telemetry_instance = self._get_instance(instance_id)
                new_mapping = request.json

                mapping = self._normalize_mapping(new_mapping)

                telemetry_instance.boat_status_mapping = mapping
                db.session.commit()

                return jsonify("Boat status mapping updated successfully."), 200

            except TypeError as e:
                return jsonify(str(e)), 404

            except Exception as e:
                db.session.rollback()
                return jsonify(str(e)), 500

        return f"boat_status paths registered successfully: {self._blueprint.url_prefix}"
