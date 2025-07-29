support multiple boats connecting to the telemetry server at once

increase the efficiency of transmission and make it require as few bytes as possible

make the API more RESTful and have everything be stored in a database instead of being on RAM

create a route for storing the images

HIGH PRIORITY: add a default parameters route so that we can send the default parameters for a boat at the start of the transmission. Once the default parameters have been set up, then make it so that the autopilot_parameters/get gives you all of the parameters including the parameters that have not been changed yet. Currently, whenever you do autopilot_parameters/get, it gives you the parameters that have changed and not all of the parameters. This is not ideal

create a domain name that redirects to this server

create a way to tell the boat to pull from github and reset systemctl from the groundstation. Make a separate version control node that communicates with the telemetry node to do version control from the groundstation. This will help limit the amount of times we need to ssh especially if we get ros2 working over lte

Make the default parameters files in the autopilot package contain the parameters' descriptions, types, display names, etc and send that entire file through the default parameters route so that the groundstation doesn't have to separately store the same parameters and their descriptions/ default values.


Move relevant code outside of the \_\_init\_\_.py file