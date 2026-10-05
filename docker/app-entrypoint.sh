#!/usr/bin/env bash
set -e

INSTANCE_DIR="/home/ubuntu/telemetry_server/src/instance"

if [ ! -f "$INSTANCE_DIR/config.py" ]; then
    echo "[entrypoint] Restoring default config.py to $INSTANCE_DIR"
    cp /opt/config.py "$INSTANCE_DIR/config.py"
fi

export PATH="/home/ubuntu/telemetry_server/venv/bin:$PATH"
export FLASK_APP="autoboat_telemetry_server:create_app()"

# run database migrations on container start if the DB exists,
# or if the DB is missing the alembic_version table (pre-Alembic volume).
echo "[entrypoint] Running database migrations"
_stamp_needed=0
if [ -f "$INSTANCE_DIR/instances.db" ]; then
    if command -v sqlite3 >/dev/null 2>&1; then
        if sqlite3 "$INSTANCE_DIR/instances.db" "SELECT name FROM sqlite_master WHERE type='table' AND name='telemetry_table'" 2>/dev/null | grep -q telemetry_table &&
            ! sqlite3 "$INSTANCE_DIR/instances.db" "SELECT name FROM sqlite_master WHERE type='table' AND name='alembic_version'" 2>/dev/null | grep -q alembic_version; then
            _stamp_needed=1
        fi
    else
        _stamp_needed=$(
            /home/ubuntu/telemetry_server/venv/bin/python - <<'PY' 2>/dev/null || echo 0
import sqlite3
c = sqlite3.connect("/home/ubuntu/telemetry_server/src/instance/instances.db")
tables = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
print(1 if "telemetry_table" in tables and "alembic_version" not in tables else 0)
PY
        )
    fi
fi
if [ "$_stamp_needed" = "1" ]; then
    echo "[entrypoint] Pre-Alembic volume detected (telemetry_table exists, alembic_version missing); stamping head"
    flask db stamp head
fi
flask db upgrade

exec "$@"
