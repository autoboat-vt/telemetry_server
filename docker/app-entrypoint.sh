#!/usr/bin/env bash
set -e

INSTANCE_DIR="/home/ubuntu/telemetry_server/src/instance"

# a named volume is mounted over the instance directory to persist the SQLite
# databases across restarts; on first start the mounted directory is empty, so
# restore the default config.py baked into the image (no-clobber: never
# overwrite an existing user-configured config.py)
if [ ! -f "$INSTANCE_DIR/config.py" ]; then
    echo "[entrypoint] Restoring default config.py to $INSTANCE_DIR"
    cp /opt/config.py "$INSTANCE_DIR/config.py"
fi

# put the venv on PATH so the CMD's gunicorn (and flask) resolve
export PATH="/home/ubuntu/telemetry_server/venv/bin:$PATH"

# tell Flask CLI where the app factory lives; the package is installed, so
# `autoboat_telemetry_server:create_app()` resolves to the factory in
# src/autoboat_telemetry_server/__init__.py
export FLASK_APP="autoboat_telemetry_server:create_app()"

# run database migrations before starting the app; this is the authoritative
# path for schema changes (AGENTS.md #6.2): create_app() deliberately does NOT
# call db.create_all() in production, so without this step a fresh volume
# would have no tables and the app would 500 on every request
#
# for existing volumes that predate Alembic (created back when create_all()
# ran in create_app), there is no alembic_version row, so `flask db upgrade`
# would try to re-create tables that already exist and fail. Detect that case
# and `stamp head` first so Alembic knows the DB is already at the baseline.
# This replaces the old manual operator step ("run flask db stamp head ONCE").
echo "[entrypoint] Running database migrations"
_stamp_needed=0
if [ -f "$INSTANCE_DIR/instances.db" ]; then
    # sqlite3 may not be installed in the slim image; fall back to python.
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
