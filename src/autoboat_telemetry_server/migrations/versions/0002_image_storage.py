"""Add content-addressed image storage.

Revision ID: 0002_image_storage
Revises: 0001_initial
Create Date: 2026-09-04 00:00:00.000000

Adds:
  - ``camera_image_uuid`` column on ``telemetry_table`` (default bind).
  - ``image_table`` on the new "images" bind (-> images.db).

This migration runs once per bind (see migrations/env.py). Each function
checks which database it's connected to via the bind key stashed in
``config.attributes['bind_key']`` and routes operations accordingly.
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic
revision = "0002_image_storage"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def _bind_key() -> str | None:
    """Return the current bind key (None=default, "images"=images.db).

    Alembic loads migration files via ``load_python_file`` which bypasses the
    package import system, so read the bind key directly from the context.
    """

    from alembic import context

    return context.config.attributes.get("bind_key")


def _default_bind() -> bool:
    return _bind_key() is None


def _images_bind() -> bool:
    return _bind_key() == "images"


def upgrade() -> None:
    """Add the image column to the default bind and create image_table."""

    if _default_bind():
        with op.batch_alter_table("telemetry_table", schema=None) as batch_op:
            batch_op.add_column(sa.Column("camera_image_uuid", sa.String(), nullable=False, server_default=""))

    if _images_bind():
        op.create_table(
            "image_table",
            sa.Column("image_uuid", sa.String(length=36), nullable=False),
            sa.Column("data", sa.LargeBinary(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint("image_uuid"),
        )


def downgrade() -> None:
    """Drop image_table and remove the image column."""

    if _images_bind():
        op.drop_table("image_table")

    if _default_bind():
        with op.batch_alter_table("telemetry_table", schema=None) as batch_op:
            batch_op.drop_column("camera_image_uuid")
