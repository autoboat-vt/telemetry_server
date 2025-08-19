"""
This module defines the TelemetryTable model for the autoboat telemetry server.
It includes the database schema and methods for interacting with telemetry data.
"""

from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import Integer, String, Boolean, JSON
from datetime import datetime
from typing import Any
from autoboat_telemetry_server.types import (
    AutopilotParametersType,
    BoatStatusType,
    WaypointsType,
)


db = SQLAlchemy()


class TelemetryTable(db.Model):
    """
    Database model for storing telemetry data.

    Inherits
    -------
    db.Model
        SQLAlchemy base model for database interaction.

    Attributes
    ----------
    instance_id : int
        Unique identifier for each telemetry instance.
    instance_identifier : str
        Optional identifier for the telemetry instance, can be used for custom naming.

    autopilot_parameters : AutopilotParametersType
        Autopilot parameters associated with the telemetry instance.
    autopilot_parameters_new_flag : bool
        Flag indicating if there are new autopilot parameters.

    boat_status : BoatStatusType
        Current status of the boat.
    boat_status_new_flag : bool
        Flag indicating if there is a new boat status.

    waypoints : WaypointsType
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

    autopilot_parameters: Mapped[AutopilotParametersType] = mapped_column(JSON, nullable=False)
    autopilot_parameters_new_flag: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    boat_status: Mapped[BoatStatusType] = mapped_column(JSON, nullable=False)
    boat_status_new_flag: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    waypoints: Mapped[WaypointsType] = mapped_column(JSON, nullable=False)
    waypoints_new_flag: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    created_at: Mapped[datetime] = mapped_column(db.DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

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
            "autopilot_parameters": self.autopilot_parameters,
            "boat_status": self.boat_status,
            "waypoints": self.waypoints,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }
