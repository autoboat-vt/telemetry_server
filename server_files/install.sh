#!/usr/bin/env bash
set -e

sudo apt update && sudo apt upgrade -y

# install necessary packages
sudo apt install -y nginx supervisor certbot python3 python3-venv python3-certbot-nginx

# initial config for nginx to get ssl working
sudo cp ~/telemetry_server/server_files/nginx_autoboat_nossl.conf /etc/nginx/sites-available/
if [ ! -L /etc/nginx/sites-enabled/nginx_autoboat.conf ]; then
  sudo ln -s /etc/nginx/sites-available/nginx_autoboat_nossl.conf /etc/nginx/sites-enabled/nginx_autoboat.conf
fi
sudo nginx -t
sudo systemctl reload nginx

# generate SSL certificates using certbot
sudo certbot --nginx -d vt-autoboat-telemetry.uk -d www.vt-autoboat-telemetry.uk --non-interactive --agree-tos --email autoboat@vt.edu

# update nginx configuration for SSL
sudo cp ~/telemetry_server/server_files/nginx_autoboat_ssl.conf /etc/nginx/sites-available/
sudo ln -sf /etc/nginx/sites-available/nginx_autoboat_ssl.conf /etc/nginx/sites-enabled/nginx_autoboat.conf
sudo nginx -t
sudo systemctl reload nginx

# create a virtual environment for the Python application and install packages
(
  python3 -m venv ~/telemetry_server/venv
  source ~/telemetry_server/venv/bin/activate
  pip install --upgrade pip
  pip install ~/telemetry_server
  deactivate
)

# ensure supervisor is enabled and started
sudo systemctl enable supervisor
sudo systemctl start supervisor

# configure supervisor
sudo cp ~/telemetry_server/server_files/supervisor_autoboat.conf /etc/supervisor/conf.d/
sudo supervisorctl reread
sudo supervisorctl update
sudo supervisorctl start telemetry_server

echo "Installation complete. Please check the status of the services."
sudo systemctl status nginx
sudo supervisorctl status telemetry_server
