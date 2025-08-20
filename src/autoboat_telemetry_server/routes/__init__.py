"""
Module containing the routes for the Autoboat telemetry server.

Autopilot Routes:
- `/autopilot_parameters/test`: Test route for autopilot parameters.
- `/autopilot_parameters/get/<int:instance_id>`: Get the current autopilot parameters.
- `/autopilot_parameters/get_new/<int:instance_id>`: Get the latest autopilot parameters if they haven't been seen yet.
- `/autopilot_parameters/set/<int:instance_id>`: Set the autopilot parameters from the request data.

Boat Status Routes:
- `/boat_status/test`: Test route for boat status.
- `/boat_status/get/<int:instance_id>`: Get the current boat status.
- `/boat_status/get_new/<int:instance_id>`: Get the latest boat status if it hasn't been seen yet.
- `/boat_status/set/<int:instance_id>`: Set the boat status from the request data.

Waypoint Routes:
- `/waypoints/test`: Test route for waypoints.
- `/waypoints/get/<int:instance_id>`: Get the current waypoints.
- `/waypoints/get_new/<int:instance_id>`: Get the latest waypoints for
- `/waypoints/set/<int:instance_id>`: Set the waypoints from the request data.

Instance Manager Routes:
- `/instance_manager/create_instance`: Create a new telemetry instance.
- `/instance_manager/delete_instance/<int:instance_id>`: Delete a telemetry instance by ID.
- `/instance_manager/set_name/<int:instance_id>/<instance_name>`: Set the name of a telemetry instance.
- `/instance_manager/get_name/<int:instance_id>`: Get the name of a telemetry instance.
- `/instance_manager/get_id/<instance_name>`: Get the ID of a telemetry instance by name.
- `/instance_manager/get_instance_info/<int:instance_id>`: Get the telemetry instance information by ID.
- `/instance_manager/get_ids`: Get all telemetry instance IDs.
"""

__all__ = ["AutopilotParametersEndpoint", "BoatStatusEndpoint", "InstanceManagerEndpoint", "WaypointEndpoint"]

from .instance_manager import InstanceManagerEndpoint
from .autopilot_parameters import AutopilotParametersEndpoint
from .boat_status import BoatStatusEndpoint
from .waypoints import WaypointEndpoint
