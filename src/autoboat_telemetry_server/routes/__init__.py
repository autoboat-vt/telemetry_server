"""
Module containing the routes for the Autoboat telemetry server.

Autopilot Routes:
- `/autopilot_parameters/test`: Test route for autopilot parameters.
- `/autopilot_parameters/get/<int:instance_id>`: Get the current autopilot parameters.
- `/autopilot_parameters/get_new/<int:instance_id>`: Get the latest autopilot parameters if they haven't been seen yet.
- `/autopilot_parameters/get_default/<int:instance_id>`: Get the default autopilot parameters.
- `/autopilot_parameters/set/<int:instance_id>`: Set the autopilot parameters from the request data.
- `/autopilot_parameters/set_default/<int:instance_id>`: Set the default autopilot parameters from the request data.

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
- `/instance_manager/test`: Test route for instance management.
- `/instance_manager/create`: Create a new telemetry instance.
- `/instance_manager/delete/<int:instance_id>`: Delete a telemetry instance by its ID.
- `/instance_manager/delete_all`: Delete all telemetry instances.
- `/instance_manager/clean_instances`: Remove all telemetry instances which haven't been marked for keeping.
- `/instance_manager/set_user/<int:instance_id>/<user_name>`: Set the user of a telemetry instance.
- `/instance_manager/get_user/<int:instance_id>`: Get the user of a telemetry instance.
- `/instance_manager/set_name/<int:instance_id>/<instance_name>`: Set the name of a telemetry instance.
- `/instance_manager/get_name/<int:instance_id>`: Get the name of a telemetry instance.
- `/instance_manager/set_archive/<int:instance_id>/<int:archive_status>`: Set the archive status of a telemetry instance.
- `/instance_manager/get_archive/<int:instance_id>`: Get the archive status of a telemetry instance.
- `/instance_manager/get_id/<instance_name>`: Get the ID of a telemetry instance by its name.
- `/instance_manager/get_instance_info/<int:instance_id>`: Get detailed information about a telemetry instance.
- `/instance_manager/get_all_instance_info`: Get detailed information about all telemetry instances.
- `/instance_manager/get_ids`: Return all telemetry instance IDs.
"""

__all__ = ["AutopilotParametersEndpoint", "BoatStatusEndpoint", "InstanceManagerEndpoint", "WaypointEndpoint"]

from .autopilot_parameters import AutopilotParametersEndpoint
from .boat_status import BoatStatusEndpoint
from .instance_manager import InstanceManagerEndpoint
from .waypoints import WaypointEndpoint
