create a route for storing the images

create a way to tell the boat to pull from github and reset systemctl from the groundstation. Make a separate version control node that communicates with the telemetry node to do version control from the groundstation. This will help limit the amount of times we need to ssh especially if we get ros2 working over lte

Move relevant code outside of the \_\_init\_\_.py file

potentially have the telemetry server create a websocket connection to the groundstation and telemetry node for less latency and to send less data
