from typing import Literal

from flask import Blueprint, Response, jsonify, request

from autoboat_telemetry_server import HOME_DIR, shared_lock_manager
from autoboat_telemetry_server.autopilot_conf_manager import AutopilotConfigManager
from autoboat_telemetry_server.models import TelemetryTable, db


class AutopilotParametersEndpoint:
    """Endpoint for handling autopilot parameters."""

    def __init__(self) -> None:
        self._blueprint = Blueprint(name="autopilot_parameters_page", import_name=__name__, url_prefix="/autopilot_parameters")
        self._config_manager = AutopilotConfigManager(HOME_DIR / "default_autopilot_parameters_config_storage")
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
        """

        instance = TelemetryTable.query.get(instance_id)

        if not isinstance(instance, TelemetryTable):
            raise TypeError("Instance not found.")

        return instance

    def _register_routes(self) -> str:
        """
        Registers the routes for the autopilot parameters endpoint.

        Returns
        -------
        str
            Confirmation message indicating the routes have been registered successfully.
        """

        @self._blueprint.route("/test", methods=["GET"])
        def test_route() -> Literal["autopilot_parameters route testing!"]:
            """
            Test route for autopilot parameters.

            Method: GET

            Returns
            -------
            Literal["autopilot_parameters route testing!"]
                Confirmation message for testing the autopilot parameters route.
            """

            return "autopilot_parameters route testing!"

        @self._blueprint.route("/get/<int:instance_id>", methods=["GET"])
        @shared_lock_manager.require_read_lock
        def get_route(instance_id: int) -> tuple[Response, int]:
            """
            Get the current autopilot parameters.

            Method: GET

            Parameters
            ----------
            instance_id
                The ID of the telemetry instance to retrieve the autopilot parameters for.

            Returns
            -------
            tuple[Response, int]
                A tuple containing a JSON response with the autopilot parameters for the specified telemetry instance,
                or an error message if the instance is not found.
            """

            try:
                telemetry_instance = self._get_instance(instance_id)
                return jsonify(telemetry_instance.autopilot_parameters), 200

            except TypeError as e:
                return jsonify(str(e)), 404

            except Exception as e:
                return jsonify(str(e)), 500

        @self._blueprint.route("/get_new/<int:instance_id>", methods=["GET"])
        @shared_lock_manager.require_write_lock
        def get_new_route(instance_id: int) -> tuple[Response, int]:
            """
            Get the latest autopilot parameters if they haven't been seen yet.

            Method: GET

            Parameters
            ----------
            instance_id
                The ID of the telemetry instance to retrieve the new autopilot parameters for.

            Returns
            -------
            tuple[Response, int]
                A tuple containing a JSON response with the new autopilot parameters for the specified telemetry instance,
                or an empty dictionary if there are no new parameters, or an error message if the instance is not found.
            """

            try:
                telemetry_instance = self._get_instance(instance_id)

                if telemetry_instance.autopilot_parameters_new_flag is False:
                    return jsonify({}), 200

                telemetry_instance.autopilot_parameters_new_flag = False
                db.session.commit()

                return jsonify(telemetry_instance.autopilot_parameters), 200

            except TypeError as e:
                return jsonify(str(e)), 404

            except Exception as e:
                return jsonify(str(e)), 500

        @self._blueprint.route("/get_default/<int:instance_id>", methods=["GET"])
        @shared_lock_manager.require_read_lock
        def get_default_route(instance_id: int) -> tuple[Response, int]:
            """
            Get the default autopilot parameters.

            Method: GET

            Parameters
            ----------
            instance_id
                The ID of the telemetry instance to retrieve the default autopilot parameters for.

            Returns
            -------
            tuple[Response, int]
                A tuple containing a JSON response with the default autopilot parameters for the specified telemetry instance,
                or an error message if the instance is not found.
            """

            try:
                telemetry_instance = self._get_instance(instance_id)
                return jsonify(telemetry_instance.default_autopilot_parameters), 200

            except TypeError as e:
                return jsonify(str(e)), 404

            except Exception as e:
                return jsonify(str(e)), 500

        @self._blueprint.route("/get_hash/<int:instance_id>", methods=["GET"])
        @shared_lock_manager.require_read_lock
        def get_current_hash_route(instance_id: int) -> tuple[Response, int]:
            """
            Get the current autopilot configuration hash.

            Method: GET

            Parameters
            ----------
            instance_id
                The ID of the telemetry instance to retrieve the autopilot configuration hash for.

            Returns
            -------
            tuple[Response, int]
                A tuple containing a JSON response with the autopilot configuration hash for the specified telemetry instance,
                or an error message if the instance is not found.
            """

            try:
                telemetry_instance = self._get_instance(instance_id)
                return jsonify(telemetry_instance.current_config_hash), 200

            except TypeError as e:
                return jsonify(str(e)), 404

            except Exception as e:
                return jsonify(str(e)), 500

        @self._blueprint.route("/get_config/<config_hash>", methods=["GET"])
        @shared_lock_manager.require_read_lock
        def get_config_route(config_hash: str) -> tuple[Response, int]:
            """
            Get the autopilot configuration for a given hash.

            Method: GET

            Parameters
            ----------
            config_hash
                The hash of the autopilot configuration to retrieve.

            Returns
            -------
            tuple[Response, int]
                A tuple containing a JSON response with the autopilot configuration for the specified hash,
                or an error message if the configuration is not found.
            """

            try:
                config = self._config_manager.load(config_hash)
                return jsonify(config), 200

            except FileNotFoundError as e:
                return jsonify(str(e)), 404

            except ValueError as e:
                return jsonify(str(e)), 400

            except Exception as e:
                return jsonify(str(e)), 500

        @self._blueprint.route("/get_hash_description/<config_hash>", methods=["GET"])
        @shared_lock_manager.require_read_lock
        def get_hash_description_route(config_hash: str) -> tuple[Response, int]:
            """
            Get the description for a given autopilot configuration hash.

            Method: GET

            Parameters
            ----------
            config_hash
                The hash of the autopilot configuration to retrieve the description for.

            Returns
            -------
            tuple[Response, int]
                A tuple containing a JSON response with the description of the specified autopilot configuration hash,
                or an error message if an unexpected error occurs.
            """

            try:
                description = self._config_manager.get_description(config_hash)
                return Response(description, mimetype="text/plain"), 200

            except FileNotFoundError as e:
                return jsonify(str(e)), 404

            except OSError as e:
                return jsonify(str(e)), 500

            except Exception as e:
                return jsonify(str(e)), 500

        @self._blueprint.route("/get_all_hashes", methods=["GET"])
        @shared_lock_manager.require_read_lock
        def get_all_hashes_route() -> tuple[Response, int]:
            """
            Get all stored autopilot configuration hashes.

            Method: GET

            Returns
            -------
            tuple[Response, int]
                A tuple containing a JSON response with a list of all stored autopilot configuration hashes,
                or an error message if an unexpected error occurs.
            """

            try:
                return jsonify(self._config_manager.get_all_hashes()), 200

            except Exception as e:
                return jsonify(str(e)), 500

        @self._blueprint.route("/get_hash_exists/<config_hash>", methods=["GET"])
        @shared_lock_manager.require_read_lock
        def get_hash_exists_route(config_hash: str) -> tuple[Response, int]:
            """
            Check if a given autopilot configuration hash exists in storage.

            Method: GET

            Parameters
            ----------
            config_hash
                The hash of the autopilot configuration to check.

            Returns
            -------
            tuple[Response, int]
                A tuple containing a JSON response with a boolean indicating whether the configuration hash exists,
                or an error message if an unexpected error occurs.
            """

            try:
                return jsonify(self._config_manager.exists(config_hash)), 200

            except Exception as e:
                return jsonify(str(e)), 500

        @self._blueprint.route("/set/<int:instance_id>", methods=["POST"])
        @shared_lock_manager.require_write_lock
        def set_route(instance_id: int) -> tuple[Response, int]:
            """
            Set the autopilot parameters from the request data.

            Method: POST

            Parameters
            ----------
            instance_id
                The ID of the telemetry instance to set the autopilot parameters for.

            Returns
            -------
            tuple[Response, int]
                A tuple containing a JSON response confirming the autopilot parameters have been updated successfully,
                or an error message if the instance is not found or if the input format is invalid.
            """

            try:
                telemetry_instance = self._get_instance(instance_id)
                new_parameters = request.json
                if not isinstance(new_parameters, dict):
                    raise TypeError("Invalid autopilot parameters format. Expected a dictionary.")

                if telemetry_instance.default_autopilot_parameters:
                    new_parameters_keys = frozenset(new_parameters)
                    default_parameters_keys = frozenset(telemetry_instance.default_autopilot_parameters)

                    if new_parameters_keys != default_parameters_keys:
                        raise ValueError("Autopilot parameters keys do not match the default configuration keys.")

                telemetry_instance.autopilot_parameters_new_flag = telemetry_instance.autopilot_parameters != new_parameters
                telemetry_instance.autopilot_parameters = new_parameters
                db.session.commit()

                return jsonify("Autopilot parameters updated successfully."), 200

            except TypeError as e:
                return jsonify(str(e)), 400

            except ValueError as e:
                return jsonify(str(e)), 400

            except Exception as e:
                db.session.rollback()
                return jsonify(str(e)), 500

        @self._blueprint.route("/set_default/<int:instance_id>", methods=["POST"])
        @shared_lock_manager.require_write_lock
        def set_default_route(instance_id: int) -> tuple[Response, int]:
            """
            Set the default autopilot parameters from the request data.

            Method: POST

            Parameters
            ----------
            instance_id
                The ID of the telemetry instance to set the default autopilot parameters for.

            Returns
            -------
            tuple[Response, int]
                A tuple containing a JSON response confirming the default autopilot parameters have been updated successfully,
                or an error message if the instance is not found or if the input format is invalid.
            """

            def validate_function(config: object) -> bool:
                """Validate the structure of the autopilot parameters configuration."""

                return isinstance(config, dict) and all(isinstance(key, str) for key in config)

            try:
                telemetry_instance = self._get_instance(instance_id)
                new_parameters = request.json

                telemetry_instance.current_config_hash = self._config_manager.save(new_parameters, validate_function)
                telemetry_instance.default_autopilot_parameters = new_parameters

                if not telemetry_instance.autopilot_parameters:
                    telemetry_instance.autopilot_parameters = {key: value["default"] for key, value in new_parameters.items()}

                db.session.commit()

                return jsonify("Default autopilot parameters updated successfully."), 200

            except TypeError as e:
                return jsonify(str(e)), 400

            except ValueError as e:
                return jsonify(str(e)), 400

            except FileNotFoundError as e:
                return jsonify(str(e)), 404

            except Exception as e:
                db.session.rollback()
                return jsonify(str(e)), 500

        @self._blueprint.route("/set_default_from_hash/<int:instance_id>/<config_hash>", methods=["POST"])
        @shared_lock_manager.require_write_lock
        def set_default_from_hash_route(instance_id: int, config_hash: str) -> tuple[Response, int]:
            """
            Set the default autopilot parameters from a saved configuration hash.

            Method: POST

            Parameters
            ----------
            instance_id
                The ID of the telemetry instance to set the default autopilot parameters for.
            config_hash
                The hash of the saved autopilot parameters configuration to load.

            Returns
            -------
            tuple[Response, int]
                A tuple containing a JSON response confirming the default autopilot parameters have been updated successfully,
                or an error message if the instance is not found or if the configuration hash is invalid.
            """

            try:
                telemetry_instance = self._get_instance(instance_id)
                new_parameters = self._config_manager.load(config_hash)

                telemetry_instance.current_config_hash = config_hash
                telemetry_instance.default_autopilot_parameters = new_parameters

                if not telemetry_instance.autopilot_parameters:
                    telemetry_instance.autopilot_parameters = {key: value["default"] for key, value in new_parameters.items()}

                db.session.commit()

                return jsonify("Default autopilot parameters updated successfully from hash."), 200

            except ValueError as e:
                return jsonify(str(e)), 400

            except FileNotFoundError as e:
                return jsonify(str(e)), 404

            except Exception as e:
                db.session.rollback()
                return jsonify(str(e)), 500

        @self._blueprint.route("/set_hash_description/<config_hash>/<description>", methods=["POST"])
        @shared_lock_manager.require_write_lock
        def set_hash_description_route(config_hash: str, description: str) -> tuple[Response, int]:
            """
            Set a description for a given autopilot configuration hash.

            Method: POST

            Parameters
            ----------
            config_hash
                The hash of the autopilot configuration to describe.
            description
                The description to associate with the configuration hash.

            Returns
            -------
            tuple[Response, int]
                A tuple containing a JSON response confirming the description has been set successfully,
                or an error message if an unexpected error occurs.
            """

            try:
                self._config_manager.set_description(config_hash, description)
                return jsonify("Description set successfully."), 200

            except FileNotFoundError as e:
                return jsonify(str(e)), 404

            except ValueError as e:
                return jsonify(str(e)), 400

            except OSError as e:
                return jsonify(str(e)), 500

            except Exception as e:
                return jsonify(str(e)), 500

        return f"autopilot_parameters paths registered successfully: {self._blueprint.url_prefix}"
