__all__ = ["ImageManagerEndpoint"]

from typing import Literal

from flask import Blueprint, Response, jsonify, request

from autoboat_telemetry_server import shared_lock_manager
from autoboat_telemetry_server.models import ImageTable, db
from autoboat_telemetry_server.types import ResponseType


class ImageManagerEndpoint:
    """Endpoint for managing the image database."""

    def __init__(self) -> None:
        self._blueprint = Blueprint(name="image_manager_page", import_name=__name__, url_prefix="/image_manager")
        self._register_routes()

    @property
    def blueprint(self) -> Blueprint:
        """Returns the Flask blueprint for image management."""
        return self._blueprint

    @staticmethod
    def _get_image_or_none(image_uuid: str) -> ImageTable | None:
        """
        Return the image row for a UUID, or `None` if it doesn't exist.

        Parameters
        ----------
        image_uuid
            The content-addressed UUID of the image to retrieve.

        Returns
        -------
        :class:`ImageTable` or `None`
            The image row corresponding to the provided UUID, or `None` if not found.
        """

        return db.session.get(ImageTable, image_uuid)

    @staticmethod
    def _extract_image_data() -> bytes:
        """
        Extract raw image bytes from the request.

        Returns
        -------
        `bytes`
            The raw image bytes from the request.

        Raises
        ------
        :class:`TypeError`
            If the request does not contain any image data.
        """

        if request.files:
            file = next(iter(request.files.values()))
            return file.read()

        data = request.get_data(cache=False)
        if not data:
            raise TypeError("No image data in the request.")

        return data

    def _register_routes(self) -> str:
        """
        Registers the routes for the image manager endpoint.

        Returns
        -------
        `str`
            Confirmation message indicating the routes have been registered successfully.
        """

        @self._blueprint.route("/test", methods=["GET"])
        def test_route() -> Literal["image_manager route testing!"]:
            """
            Test route for image management.

            Method: GET

            Returns
            -------
            `Literal["image_manager route testing!"]`
                Confirmation message for testing the image manager route.
            """

            return "image_manager route testing!"

        @self._blueprint.route("/get/<image_uuid>", methods=["GET"])
        @shared_lock_manager.require_read_lock
        def get_route(image_uuid: str) -> ResponseType:
            """
            Get the raw image bytes for a UUID.

            Method: GET

            Parameters
            ----------
            image_uuid
                The content-addressed UUID of the image to retrieve.

            Returns
            -------
            :type:`ResponseType`
                A tuple containing the raw image bytes in the response, or an error message if the image is not found.
            """

            image = self._get_image_or_none(image_uuid)
            if image is None:
                return jsonify("Image not found."), 404

            return Response(image.data, mimetype="application/octet-stream"), 200

        @self._blueprint.route("/get_info/<image_uuid>", methods=["GET"])
        @shared_lock_manager.require_read_lock
        def get_info_route(image_uuid: str) -> ResponseType:
            """
            Get metadata for a UUID without the binary payload.

            Method: GET

            Parameters
            ----------
            image_uuid
                The content-addressed UUID of the image.

            Returns
            -------
            :type:`ResponseType`
                A tuple containing a JSON response with the image metadata,
                or an error message if the image is not found.
            """

            image = self._get_image_or_none(image_uuid)
            if image is None:
                return jsonify("Image not found."), 404

            return jsonify(image.to_dict()), 200

        @self._blueprint.route("/get_all", methods=["GET"])
        @shared_lock_manager.require_read_lock
        def get_all_route() -> ResponseType:
            """
            Get metadata for all stored images.

            Method: GET

            Returns
            -------
            :type:`ResponseType`
                A tuple containing a JSON response with a list of metadata for
                every stored image.
            """

            images = db.session.execute(db.select(ImageTable)).scalars().all()
            return jsonify([image.to_dict() for image in images]), 200

        @self._blueprint.route("/upload", methods=["POST"])
        @shared_lock_manager.require_write_lock
        def upload_route() -> ResponseType:
            """
            Store a new image and return its content-addressed UUID.

            Accepts a multipart/form-data file upload or a raw binary body.
            Because the UUID is derived from the image bytes, re-uploading an
            identical image returns the existing UUID without creating a
            duplicate row.

            Method: POST

            Returns
            -------
            :type:`ResponseType`
                A tuple containing a JSON response with the image UUID, or an
                error message if the request has no image data.
            """

            try:
                image_data = self._extract_image_data()
                image = ImageTable.get_or_create(image_data)
                db.session.commit()
                return jsonify(image.image_uuid), 200

            except TypeError as e:
                return jsonify(str(e)), 400

            except Exception as e:
                db.session.rollback()
                return jsonify(str(e)), 500

        @self._blueprint.route("/delete/<image_uuid>", methods=["DELETE"])
        @shared_lock_manager.require_write_lock
        def delete_route(image_uuid: str) -> ResponseType:
            """
            Delete a stored image by UUID.

            Method: DELETE

            Parameters
            ----------
            image_uuid
                The content-addressed UUID of the image to delete.

            Returns
            -------
            :type:`ResponseType`
                A tuple containing a JSON confirmation message, or an error
                message if the image is not found.
            """

            try:
                image = self._get_image_or_none(image_uuid)
                if image is None:
                    return jsonify("Image not found."), 404

                db.session.delete(image)
                db.session.commit()
                return jsonify(f"Image {image_uuid} deleted successfully."), 200

            except Exception as e:
                db.session.rollback()
                return jsonify(str(e)), 500

        @self._blueprint.route("/delete_all", methods=["DELETE"])
        @shared_lock_manager.require_write_lock
        def delete_all_route() -> ResponseType:
            """
            Delete all stored images.

            Method: DELETE

            Returns
            -------
            :type:`ResponseType`
                A tuple containing a JSON confirmation message with the number
                of deleted images.
            """

            try:
                count = db.session.query(ImageTable).delete()
                db.session.commit()
                return jsonify(f"{count} images deleted successfully."), 200

            except Exception as e:
                db.session.rollback()
                return jsonify(str(e)), 500

        return f"image_manager paths registered successfully: {self._blueprint.url_prefix}"
