"""Initial schema for both binds.

Revision ID: 0001_initial
Revises:
Create Date: 2026-08-17 19:00:00.000000

Baseline schema for both binds (AGENTS.md #6.4):
  - default bind (None -> instances.db): telemetry_table
  - "hashes" bind (-> hashes.db):        hash_table

This migration runs once per bind (see migrations/env.py). Each function
checks which database it's connected to via the bind key stashed in
``config.attributes['bind_key']`` and routes operations accordingly.
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic
revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def _bind_key() -> str | None:
    """Return the current bind key (None=default, "hashes"=hashes.db).

    Alembic loads migration files via ``load_python_file`` which bypasses the
    package import system, so we can't ``from migrations._bind_helpers import``
    here. Instead, read the bind key directly from the alembic context.
    """

    from alembic import context

    return context.config.attributes.get("bind_key")


def _default_bind() -> bool:
    return _bind_key() is None


def _hashes_bind() -> bool:
    return _bind_key() == "hashes"


def upgrade() -> None:
    """Create the baseline tables on each bind."""

    if _default_bind():
        op.create_table(
            "telemetry_table",
            sa.Column("instance_id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("instance_identifier", sa.String(), nullable=True),
            sa.Column("user", sa.String(), nullable=False),
            sa.Column("diagnostic_message", sa.JSON(), nullable=True),
            sa.Column("current_config_hash", sa.String(), nullable=False),
            sa.Column("default_autopilot_parameters", sa.JSON(), nullable=False),
            sa.Column("autopilot_parameters", sa.JSON(), nullable=False),
            sa.Column("autopilot_parameters_new_flag", sa.Boolean(), nullable=False),
            sa.Column("boat_status", sa.JSON(), nullable=False),
            sa.Column("boat_status_mapping", sa.JSON(), nullable=True),
            sa.Column("boat_status_new_flag", sa.Boolean(), nullable=False),
            sa.Column("waypoints", sa.JSON(), nullable=False),
            sa.Column("waypoints_new_flag", sa.Boolean(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint("instance_id"),
        )
        with op.batch_alter_table("telemetry_table", schema=None) as batch_op:
            batch_op.create_index("ix_telemetry_table_instance_identifier", ["instance_identifier"], unique=False)
            batch_op.create_index("ix_telemetry_table_updated_at", ["updated_at"], unique=False)

    if _hashes_bind():
        op.create_table(
            "hash_table",
            sa.Column("config_hash", sa.String(length=64), nullable=False),
            sa.Column("data", sa.JSON(), nullable=False),
            sa.Column("description", sa.String(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint("config_hash"),
        )


def downgrade() -> None:
    """Drop the baseline tables on each bind."""

    if _hashes_bind():
        op.drop_table("hash_table")

    if _default_bind():
        with op.batch_alter_table("telemetry_table", schema=None) as batch_op:
            batch_op.drop_index("ix_telemetry_table_updated_at")
            batch_op.drop_index("ix_telemetry_table_instance_identifier")
        op.drop_table("telemetry_table")
