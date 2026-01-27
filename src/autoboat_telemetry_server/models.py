"""
Database models for the Autoboat Telemetry Server.

Includes:
- TelemetryTable: Model for storing telemetry data.
- HashTable: Model for storing configuration hashes.
"""

__all__ = ["HashTable", "TelemetryTable", "db"]

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import JSON, Boolean, Integer, String, event
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Mapped, Mapper, mapped_column, validates

from autoboat_telemetry_server.types import AutopilotParametersType, BoatStatusType, WaypointSequenceType

db = SQLAlchemy()


class TelemetryTable(db.Model):
    """
    Database model for storing telemetry data.

    Inherits
    -------
    ``db.Model``
        SQLAlchemy base model for database interaction.

    Attributes
    ----------
    instance_id : int
        Unique identifier for each telemetry instance.
    instance_identifier : str
        Optional identifier for the telemetry instance, can be used for custom naming.
    user : str
        User associated with the telemetry instance.
        Should be set by the telemetry node in the simulation.
        Can only be changed once when the instance is created.

    current_config_hash : str
        SHA-256 hash of the current autopilot parameters configuration.
    default_autopilot_parameters : AutopilotParametersType
        Default autopilot parameters for the telemetry instance.
    autopilot_parameters : AutopilotParametersType
        Autopilot parameters associated with the telemetry instance.
    autopilot_parameters_new_flag : bool
        Flag indicating if there are new autopilot parameters.

    boat_status : BoatStatusType
        Current status of the boat.
    boat_status_new_flag : bool
        Flag indicating if there is a new boat status.

    waypoints : WaypointSequenceType
        List of waypoints for the boat.
    waypoints_new_flag : bool
        Flag indicating if there are new waypoints.

    created_at : datetime
        Timestamp when the telemetry instance was created.
    updated_at : datetime
        Timestamp when the telemetry instance was last updated.
    """

    __tablename__ = "telemetry_table"

    instance_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    instance_identifier: Mapped[str] = mapped_column(String, default="", nullable=True)
    user: Mapped[str] = mapped_column(String, default="unknown", nullable=False)

    current_config_hash: Mapped[str] = mapped_column(String, default="", nullable=False)
    default_autopilot_parameters: Mapped[AutopilotParametersType] = mapped_column(JSON, nullable=False)
    autopilot_parameters: Mapped[AutopilotParametersType] = mapped_column(JSON, nullable=False)
    autopilot_parameters_new_flag: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    boat_status: Mapped[BoatStatusType] = mapped_column(JSON, nullable=False)
    boat_status_new_flag: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    waypoints: Mapped[WaypointSequenceType] = mapped_column(JSON, nullable=False)
    waypoints_new_flag: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    created_at: Mapped[datetime] = mapped_column(db.DateTime, default=lambda: datetime.now(UTC), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        db.DateTime, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC), nullable=False
    )

    @validates("user")
    def validate_user(self, _: str, value: str) -> str:
        """
        Validate the user field to ensure it can only be set once.

        Parameters
        ----------
        _
            The name of the field being validated. Not used in this method
            because we only validate the "user" field.
        value
            The value being assigned to the field.

        Returns
        -------
        str
            The validated value.

        Raises
        ------
        ValueError
            If there is an attempt to change the user after it has been set.
        """

        if getattr(self, "user", "unknown") != "unknown" and self.user != value:
            raise ValueError("The 'user' field can only be set once and cannot be changed.")

        return value

    def to_dict(self) -> dict[str, Any]:
        """
        Convert the telemetry instance to a dictionary.

        Returns
        -------
        dict[str, Any]
            A dictionary representation of the telemetry instance.
        """

        return {
            "instance_id": self.instance_id,
            "instance_identifier": self.instance_identifier,
            "user": self.user,
            "current_config_hash": self.current_config_hash,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

    @classmethod
    def get_all_ids(cls) -> list[int]:
        """
        Retrieve all instance IDs from the database.

        Returns
        -------
        list[int]
            A list of all instance IDs.
        """

        return db.session.execute(db.select(cls.instance_id)).scalars().all()


@event.listens_for(TelemetryTable, "after_insert")
def set_instance_identifier(mapper: Mapper, connection: Connection, target: TelemetryTable) -> None:
    """
    Event listener to set the ``instance_identifier`` after a ``TelemetryTable`` row is inserted.

    Parameters
    ----------
    mapper
        SQLAlchemy mapper for the model.
    connection
        Database connection used for the update.
    target
        The instance of ``TelemetryTable`` that was inserted.

    Returns
    -------
    None
    """

    new_identifier = f"Unnamed instance #{target.instance_id}"
    if not target.instance_identifier:
        connection.execute(
            TelemetryTable.__table__.update()
            .where(TelemetryTable.instance_id == target.instance_id)
            .values(instance_identifier=new_identifier)
        )
        target.instance_identifier = new_identifier


class HashTable(db.Model):
    """
    Database model for storing configuration hashes.

    Inherits
    -------
    ``db.Model``
        SQLAlchemy base model for database interaction.

    Attributes
    ----------
    config_hash : str
        Immutable SHA-256 hash of the configuration.
    data : AutopilotParametersType
        The actual configuration data associated with this hash.
    description : str
        Optional description of the configuration.
    created_at : datetime
        Timestamp when the hash was created.
    """

    __tablename__ = "hash_table"
    __bind_key__ = "hashes"

    config_hash: Mapped[str] = mapped_column(String, primary_key=True, nullable=False)
    data: Mapped[AutopilotParametersType] = mapped_column(JSON, nullable=False)
    description: Mapped[str] = mapped_column(String, default="", nullable=True)

    created_at: Mapped[datetime] = mapped_column(db.DateTime, default=lambda: datetime.now(UTC), nullable=False)

    def to_dict(self) -> dict[str, Any]:
        """
        Convert the hash instance to a dictionary.

        Returns
        -------
        dict[str, Any]
            A dictionary representation of the hash instance.
        """

        return {"config_hash": self.config_hash, "description": self.description, "created_at": self.created_at.isoformat()}

    @classmethod
    def check_hash_exists(cls, config_hash: str) -> bool:
        """
        Check if a configuration hash exists in the database.

        Parameters
        ----------
        config_hash
            The SHA-256 hash of the configuration to check.

        Returns
        -------
        bool
            ``True`` if the hash exists, ``False`` otherwise.
        """

        exists = db.session.execute(db.select(cls.config_hash).where(cls.config_hash == config_hash)).first()
        return exists is not None

    @staticmethod
    def compute_hash(config_data: dict) -> str:
        """
        Compute the SHA-256 hash of the given configuration data.

        Parameters
        ----------
        config_data
            The configuration data to hash.

        Returns
        -------
        str
            The SHA-256 hash of the configuration data.
        """

        config_json = json.dumps(config_data, sort_keys=True, separators=(",", ":"))
        hash_obj = hashlib.sha256(config_json.encode(encoding="utf-8"))
        return hash_obj.hexdigest()

    @staticmethod
    def validate_config(config: object) -> bool:
        """
        Validate the structure of the autopilot parameters configuration.

        Parameters
        ----------
        config
            The configuration to validate.

        Returns
        -------
        bool
            ``True`` if the configuration is valid, ``False`` otherwise.
        """

        if not isinstance(config, dict):
            return False

        if config == {}:
            return False

        for key, inner in config.items():
            if not isinstance(key, str):
                return False

            if not isinstance(inner, dict):
                return False

            if not all(isinstance(inner_key, str) for inner_key in inner):
                return False

            if not {"default", "description"}.issubset(inner):
                return False

        return True
