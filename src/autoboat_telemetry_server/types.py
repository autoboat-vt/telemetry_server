"""
This module defines type aliases used throughout the autoboat telemetry server.

Types:
- BoatStatusType: A dictionary representing the status of the boat.
- WaypointsType: A list of waypoints, where each waypoint is a list of coordinates
    (latitude and longitude).
- AutopilotParametersType: A dictionary representing the autopilot parameters.
"""

from typing import Any

type BoatStatusType = dict[str, Any]
type WaypointsType = list[list[float | int]]
type AutopilotParametersType = dict[str, Any]
