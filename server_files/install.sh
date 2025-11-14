#!/usr/bin/env bash
set -e

# ------------------------
# System update + packages
# ------------------------
sudo apt update && sudo apt upgrade -y
sudo apt install -y nginx supervisor certbot python3 python3-venv python3-certbot-nginx git

# ------------------------
# Nginx initial config
# ------------------------
sudo cp ~/telemetry_server/server_files/nginx_autoboat_nossl.conf /etc/nginx/sites-available/
if [ ! -L /etc/nginx/sites-enabled/nginx_autoboat.conf ]; then
  sudo ln -s /etc/nginx/sites-available/nginx_autoboat_nossl.conf /etc/nginx/sites-enabled/nginx_autoboat.conf
fi
sudo nginx -t
sudo systemctl reload nginx

# ------------------------
# SSL certificates
# ------------------------
sudo certbot --nginx -d vt-autoboat-telemetry.uk -d www.vt-autoboat-telemetry.uk --non-interactive --agree-tos --email autoboat@vt.edu

# ------------------------
# Update Nginx for SSL
# ------------------------
sudo cp ~/telemetry_server/server_files/nginx_autoboat_ssl.conf /etc/nginx/sites-available/
sudo ln -sf /etc/nginx/sites-available/nginx_autoboat_ssl.conf /etc/nginx/sites-enabled/nginx_autoboat.conf
sudo nginx -t
sudo systemctl reload nginx

# ------------------------
# Python virtual envs + install
# ------------------------
(
  python3 -m venv ~/telemetry_server/venv
  source ~/telemetry_server/venv/bin/activate
  pip install --upgrade pip
  pip install ~/telemetry_server
  deactivate
)

# ------------------------
# Testing branch setup
# ------------------------
if [ ! -d ~/telemetry_server_testing ]; then
  git clone https://github.com/autoboat-vt/telemetry_server ~/telemetry_server_testing
  cd ~/telemetry_server_testing
  git checkout testing
  (
    python3 -m venv ~/telemetry_server_testing/venv
    source ~/telemetry_server_testing/venv/bin/activate
    pip install --upgrade pip
    pip install ~/telemetry_server_testing
    deactivate
  )
fi

# ------------------------
# Permissions
# ------------------------
sudo chown -R ubuntu:ubuntu /home/ubuntu/telemetry_server/src/instance
sudo chmod 755 /home/ubuntu/telemetry_server/src/instance
sudo chown -R ubuntu:ubuntu /home/ubuntu/telemetry_server_testing/src/instance
sudo chmod 755 /home/ubuntu/telemetry_server_testing/src/instance

# ------------------------
# Supervisor setup
# ------------------------
sudo systemctl enable supervisor
sudo systemctl start supervisor

# stop any running instances
sudo supervisorctl stop telemetry_server || true
sudo supervisorctl stop telemetry_server_testing || true

sudo cp ~/telemetry_server/server_files/supervisor_autoboat.conf /etc/supervisor/conf.d/
sudo supervisorctl reread
sudo supervisorctl update
sudo supervisorctl start telemetry_server
sudo supervisorctl start telemetry_server_testing

# ------------------------
# Telemetry server status
# ------------------------
echo "Telemetry server status:"
sudo systemctl status nginx
sudo supervisorctl status telemetry_server
sudo supervisorctl status telemetry_server_testing

# ------------------------
# Crontab setup for auto removal of instances
# ------------------------
crontab ~/telemetry_server/server_files/auto_clean.txt
echo "Installation complete!"
