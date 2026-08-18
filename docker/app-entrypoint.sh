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
# ran in create_app), the operator must run `flask db stamp head` ONCE before
# deploying this image -- otherwise Alembic thinks the DB is at base and tries
# to re-create tables that already exist; see deployment-docs.instructions.md
echo "[entrypoint] Running database migrations"
flask db upgrade

exec "$@"
