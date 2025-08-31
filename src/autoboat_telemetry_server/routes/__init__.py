"""
Module containing the routes for the Autoboat telemetry server.

Autopilot Routes:
- `/autopilot_parameters/test`: Test route for autopilot parameters.
- `/autopilot_parameters/get`: Get the current autopilot parameters.
- `/autopilot_parameters/get_new`: Get the latest autopilot parameters if they haven't been seen yet.
- `/autopilot_parameters/get_default`: Get the default autopilot parameters.
- `/autopilot_parameters/set`: Set the autopilot parameters from the request data.
- `/autopilot_parameters/set_default`: Set the default autopilot parameters from the request data.

Boat Status Routes:
- `/boat_status/test`: Test route for boat status.
- `/boat_status/get`: Get the current boat status.
- `/boat_status/get_new`: Get the latest boat status if it hasn't been seen yet.
- `/boat_status/set`: Set the boat status from the request data.

Waypoint Routes:
- `/waypoints/test`: Test route for waypoints.
- `/waypoints/get`: Get the current waypoints.
- `/waypoints/get_new`: Get the latest waypoints if they haven't been seen yet.
- `/waypoints/set`: Set the waypoints from the request data.
"""

__all__ = ["AutopilotParametersEndpoint", "BoatStatusEndpoint", "WaypointEndpoint"]

from .autopilot_parameters import AutopilotParametersEndpoint
from .boat_status import BoatStatusEndpoint
from .waypoints import WaypointEndpoint
