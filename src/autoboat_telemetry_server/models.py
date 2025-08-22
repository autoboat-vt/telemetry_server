"""
This module defines the TelemetryTable model for the autoboat telemetry server.
It includes the database schema and methods for interacting with telemetry data.
"""

from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import Mapped, mapped_column, Mapper
from sqlalchemy import Integer, String, Boolean, JSON, event
from sqlalchemy.engine import Connection
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

    default_autopilot_parameters: Mapped[AutopilotParametersType] = mapped_column(JSON, nullable=False)
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
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }


@event.listens_for(TelemetryTable, "after_insert")
def set_instance_identifier(mapper: Mapper, connection: Connection, target: TelemetryTable) -> None:
    """
    Event listener to set the instance_identifier after a TelemetryTable row is inserted.

    Parameters
    ----------
    mapper
        SQLAlchemy mapper for the model.
    connection
        Database connection used for the update.
    target
        The instance of TelemetryTable that was inserted.

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
