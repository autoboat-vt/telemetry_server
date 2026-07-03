#!/bin/sh
# cron sidecar that replicates server_files/auto_clean.txt.
#
# Original crontab:
#   */5 * * * * curl -X DELETE "https://vt-autoboat-telemetry.uk/instance_manager/clean_instances"
#
# Here we call the production app container directly over the internal network
# instead of routing through the public HTTPS endpoint.
set -e

mkdir -p /etc/crontabs /var/log

cat >/etc/crontabs/root <<'EOF'
SHELL=/bin/sh
*/5 * * * * /usr/bin/curl -fsS -X DELETE "http://telemetry-prod:8000/instance_manager/clean_instances" >> /var/log/clean_instances.log 2>&1
EOF

echo "[cron] Starting crond (clean_instances every 5 minutes)"
# -f foreground, -l 8 info logging
crond -f -l 8
