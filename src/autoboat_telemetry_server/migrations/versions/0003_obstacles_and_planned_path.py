"""Add obstacles and planned-path storage.

Revision ID: 0003_obstacles_and_path
Revises: 0002_image_storage
Create Date: 2026-10-04 00:00:00.000000

Adds (default bind only, on ``telemetry_table``):
  - ``obstacles`` (JSON): the obstacle polygon GeoJSON document. nullable=False
    with a server default of ``{}`` so the ALTER works on rows that already
    exist (SQLite requires a default when adding a NOT NULL column).
  - ``obstacles_new_flag`` (Boolean): set when the obstacle set changes, so
    ``obstacles/get_new`` can mirror ``waypoints/get_new``.
  - ``planned_path`` (JSON): the obstacle-avoiding path the boat is following.

These feed the new ``obstacles/*`` and ``path/*`` route groups (see
docs/telemetry_server_obstacles_and_path_routes.md in autoboat_vt). The columns
live on the default bind (instances.db), unlike the "images" bind added in
0002, so this migration only touches the default bind.

This migration runs once per bind (see migrations/env.py). Each function
checks which database it's connected to via the bind key stashed in
``config.attributes['bind_key']`` and routes operations accordingly.
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic
revision = "0003_obstacles_and_path"
down_revision = "0002_image_storage"
branch_labels = None
depends_on = None


def _bind_key() -> str | None:
    """Return the current bind key (None=default, "hashes"/"images"=that db).

    Alembic loads migration files via ``load_python_file`` which bypasses the
    package import system, so read the bind key directly from the context.
    """

    from alembic import context

    return context.config.attributes.get("bind_key")


def _default_bind() -> bool:
    return _bind_key() is None


def upgrade() -> None:
    """Add the obstacles / planned_path columns to the default bind."""

    if not _default_bind():
        return

    with op.batch_alter_table("telemetry_table", schema=None) as batch_op:
        # server_default keeps the NOT NULL ALTER valid for pre-existing rows
        # (SQLite requires a default when adding a NOT NULL column); the ORM
        # model default only applies to newly inserted rows.
        batch_op.add_column(sa.Column("obstacles", sa.JSON(), nullable=False, server_default="{}"))
        batch_op.add_column(sa.Column("obstacles_new_flag", sa.Boolean(), nullable=False, server_default=sa.false()))
        batch_op.add_column(sa.Column("planned_path", sa.JSON(), nullable=False, server_default="[]"))


def downgrade() -> None:
    """Drop the obstacles / planned_path columns from the default bind."""

    if not _default_bind():
        return

    with op.batch_alter_table("telemetry_table", schema=None) as batch_op:
        batch_op.drop_column("planned_path")
        batch_op.drop_column("obstacles_new_flag")
        batch_op.drop_column("obstacles")
