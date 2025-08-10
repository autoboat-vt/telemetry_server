#!/usr/bin/env bash

sudo apt update && sudo apt upgrade -y

# install nginx and supervisor
sudo apt install -y nginx supervisor

# install python stuff
sudo apt install -y python3 python3-venv

# create a virtual environment for the Python application
python3 -m venv ~/telemetry_server/venv
source ~/telemetry_server/venv/bin/activate

# install required Python packages
pip install --upgrade pip
pip install ~/telemetry_server

# configure nginx
sudo cp ~/telemetry_server/nginx/telemetry_server.conf /etc/nginx/sites-available/
sudo ln -s /etc/nginx/sites-available/telemetry_server.conf /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl restart nginx

# configure supervisor
sudo cp ~/telemetry_server/supervisor/telemetry_server.conf /etc/supervisor/conf.d/
sudo supervisorctl reread
sudo supervisorctl update
sudo supervisorctl start telemetry_server

# cleanup
deactivate
echo "Installation complete. Please check the status of the services."
sudo systemctl status nginx
sudo supervisorctl status telemetry_server

