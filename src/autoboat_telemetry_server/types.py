"""
This module defines type aliases used throughout the Autoboat telemetry server.

Types:
- WaypointType: A list or tuple representing a waypoint with latitude and longitude.
- WaypointSequenceType: A list of waypoints, where each waypoint is a list of coordinates
    (latitude and longitude).
- BoatStatusType: A dictionary representing the boat's status information.
"""

from typing import Any

type CoordinateType = float | int
type WaypointType = tuple[CoordinateType, CoordinateType]
type WaypointSequenceType = list[WaypointType]

type BoatStatusType = dict[str, Any]

# example: {..., "tack_distance": {"default": 100.0, "description": ...}, ...}
type AutopilotParametersType = dict[str, dict[str, Any]]
