#!/usr/bin/env bash
set -e

INSTANCE_DIR="/home/ubuntu/telemetry_server/src/instance"

# A named volume is mounted over the instance directory to persist the SQLite
# databases across restarts. On first start the mounted directory is empty, so
# restore the default config.py baked into the image (no-clobber: never
# overwrite an existing user-configured config.py).
if [ ! -f "$INSTANCE_DIR/config.py" ]; then
    echo "[entrypoint] Restoring default config.py to $INSTANCE_DIR"
    cp /opt/config.py "$INSTANCE_DIR/config.py"
fi

# Put the venv on PATH so the CMD's gunicorn resolves.
export PATH="/home/ubuntu/telemetry_server/venv/bin:$PATH"

exec "$@"
