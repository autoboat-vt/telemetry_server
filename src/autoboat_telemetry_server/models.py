from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()


class AutopilotParameters(db.Model):
    __tablename__ = "autopilot_parameters"

    id = db.Column(db.Integer, primary_key=True)
    data = db.Column(db.JSON, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    def to_dict(self) -> dict:
        """
        Convert the autopilot parameters data to a dictionary.

        Returns
        -------
        dict
            The autopilot parameters data as a dictionary.
        """

        return list(self.data.values())[0] if self.data else {}


class BoatStatus(db.Model):
    __tablename__ = "boat_status"

    id = db.Column(db.Integer, primary_key=True)
    data = db.Column(db.JSON, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    def to_dict(self) -> dict:
        """
        Convert the boat status data to a dictionary.

        Returns
        -------
        dict
            The boat status data as a dictionary.
        """

        return dict(self.data) if self.data else {}


class Waypoints(db.Model):
    __tablename__ = "waypoints"

    id = db.Column(db.Integer, primary_key=True)
    data = db.Column(db.JSON, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    def to_list(self) -> list[list[float]]:
        """
        Convert the waypoints data to a list of lists.

        Returns
        -------
        list[list[float]]
            The waypoints data as a list of lists.
        """

        return list(self.data.values())[0]
