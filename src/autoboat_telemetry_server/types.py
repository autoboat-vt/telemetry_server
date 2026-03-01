"""
This module defines type aliases used throughout the Autoboat telemetry server.

Types:
- ResponseType: A tuple containing a Flask Response object and an integer status code.
- WaypointType: A list or tuple representing a waypoint with latitude and longitude.
- WaypointSequenceType: A list of waypoints, where each waypoint is a list of coordinates
    (latitude and longitude).
- BoatStatusType: A dictionary representing the boat's status information.
- BoatStatusMappingType: A list of pairs of field names and their corresponding data types for the boat status.
- AutopilotParametersType: A dictionary representing the autopilot parameters configuration.
"""

__all__ = [
    "AutopilotParametersType",
    "BoatStatusMappingType",
    "BoatStatusType",
    "ResponseType",
    "WaypointSequenceType",
    "WaypointType",
]

from typing import Any

from flask import Response

type ResponseType = tuple[Response, int]

type CoordinateType = float | int
type WaypointType = tuple[CoordinateType, CoordinateType]
type WaypointSequenceType = list[WaypointType]

type BoatStatusType = dict[str, Any]

# list of [field_name, field_type] pairs defining the mapping of boat status fields to their corresponding data types
type BoatStatusMappingType = list[list[str]]

# example: {..., "tack_distance": {"default": 100.0, "description": ...}, ...}
type AutopilotParametersType = dict[str, dict[str, Any]]
