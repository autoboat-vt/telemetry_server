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
- DiagnosticMessageIntensity: An enumeration representing the intensity levels of diagnostic messages.
"""

__all__ = [
    "AutopilotParametersType",
    "BoatStatusMappingType",
    "BoatStatusType",
    "DiagnosticMessageIntensity",
    "ResponseType",
    "WaypointSequenceType",
    "WaypointType",
]

from enum import IntEnum
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


class DiagnosticMessageIntensity(IntEnum):
    """
    Enumeration representing the intensity levels of diagnostic messages.

    Attributes
    ----------
    - ```INFO```: Represents informational messages that indicate normal operation or
        provide general information.

    - ```WARNING```: Represents warning messages that indicate a potential issue or a
        situation that may require attention but does not necessarily indicate an immediate problem.

    - ```ERROR```: Represents error messages that indicate a significant problem or
        failure that requires immediate attention and may impact the functionality of the system.

    Inherits
    -------
    ``IntEnum``
    """

    INFO = 1
    WARNING = 2
    ERROR = 3
