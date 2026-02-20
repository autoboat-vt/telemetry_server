"""
This module defines type aliases used throughout the Autoboat telemetry server.

Types:
- ResponseType: A tuple containing a Flask Response object and an integer status code.
- WaypointType: A list or tuple representing a waypoint with latitude and longitude.
- WaypointSequenceType: A list of waypoints, where each waypoint is a list of coordinates
    (latitude and longitude).
- BoatStatusType: A dictionary representing the boat's status information.
- AutopilotParametersType: A dictionary representing the autopilot parameters configuration.
"""

__all__ = ["AutopilotParametersType", "BoatStatusType", "ResponseType", "WaypointSequenceType", "WaypointType"]

from typing import Any

from flask import Response

type ResponseType = tuple[Response, int]

type CoordinateType = float | int
type WaypointType = tuple[CoordinateType, CoordinateType]
type WaypointSequenceType = list[WaypointType]

type BoatStatusType = dict[str, Any]

# example: {..., "tack_distance": {"default": 100.0, "description": ...}, ...}
type AutopilotParametersType = dict[str, dict[str, Any]]
