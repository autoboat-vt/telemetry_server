"""Alembic environment for multi-bind Flask-SQLAlchemy.

This project uses two SQLite binds (AGENTS.md #6.4):
  - None (default) -> instances.db (TelemetryTable)
  - "hashes"        -> hashes.db    (HashTable)

The stock Flask-Migrate env.py only migrates the default bind, which would
silently skip the `hash_table` table. This version handles both:

  - **Autogenerate** (`flask db migrate`): diffs ONLY the default bind to
    produce a coherent single migration file. Operations for the `hashes`
    bind must be added manually (HashTable schema changes are rare).
  - **Runtime** (`flask db upgrade` / `downgrade`): iterates over every bind
    in `SQLALCHEMY_BINDS` and runs the migration once per bind. The
    migration's `upgrade()`/`downgrade()` branch on `op.get_bind()` (or on
    `config.attributes['bind_key']`) to route operations to the correct
    database.
"""

import logging
from logging.config import fileConfig

from alembic import context
from flask import current_app

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use
config = context.config

# interpret the config file for Python logging
fileConfig(config.config_file_name)
logger = logging.getLogger("alembic.env")


def get_engine(bind_key: str | None = None):
    # Flask-SQLAlchemy>=3 exposes per-bind engines in `db.engines` (a dict
    # keyed by bind key, with None for the default bind); the older
    # `db.get_engine(bind=...)` API is deprecated as of 3.1 and removed in 3.2
    # we fall back to it only for older Flask-SQLAlchemy / Alchemical
    db = current_app.extensions["migrate"].db
    try:
        return db.engines[bind_key]
    except (KeyError, AttributeError):
        return db.get_engine(bind=bind_key)


def get_engine_url(bind_key: str | None = None) -> str:
    try:
        return get_engine(bind_key).url.render_as_string(hide_password=False).replace("%", "%%")
    except AttributeError:
        return str(get_engine(bind_key).url).replace("%", "%%")


target_db = current_app.extensions["migrate"].db


def get_metadata(bind_key: str | None):
    """Return the MetaData for a given bind.

    Flask-SQLAlchemy>=3 stores per-bind MetaData in `db.metadatas` (a dict
    keyed by bind key, with None for the default bind). Older versions and
    single-bind setups expose a single `db.metadata`.
    """

    if hasattr(target_db, "metadatas"):
        return target_db.metadatas[bind_key]
    return target_db.metadata


def _bind_keys() -> list[str | None]:
    """Return [default, *extra_binds] from SQLALCHEMY_BINDS."""

    binds = current_app.config.get("SQLALCHEMY_BINDS", {}) or {}
    keys: list[str | None] = [None]
    for key in binds:
        if key is not None:
            keys.append(key)
    return keys


def _is_autogenerate() -> bool:
    """True when Alembic is generating a migration revision."""

    return bool(getattr(config.cmd_opts, "autogenerate", False))


def _process_revision_directives(context, revision, directives) -> None:
    """Prevent an empty auto-migration from being generated.

    Reference: https://alembic.zzzcomputing.com/en/latest/cookbook.html
    """

    if _is_autogenerate():
        script = directives[0]
        if script.upgrade_ops.is_empty():
            directives[:] = []
            logger.info("No changes in schema detected for this bind.")


# apply any extra configure_args from Flask-Migrate (e.g. compare_type)
conf_args = current_app.extensions["migrate"].configure_args
if conf_args.get("process_revision_directives") is None:
    conf_args["process_revision_directives"] = _process_revision_directives


def _stash_bind_key(bind_key: str | None) -> None:
    """Make the current bind key available to migration code.

    Migration `upgrade()`/`downgrade()` functions can read the current bind
    via `config.attributes['bind_key']` to route operations to the right DB.
    """

    config.attributes["bind_key"] = bind_key


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    For autogenerate, only the default bind is diffed (multi-bind autogenerate
    produces incoherent output). For runtime (upgrade/downgrade), iterate
    over every bind and emit SQL for each.
    """

    keys = [None] if _is_autogenerate() else _bind_keys()
    for bind_key in keys:
        logger.info("Running offline migrations for bind: %r", bind_key)
        _stash_bind_key(bind_key)
        context.configure(url=get_engine_url(bind_key), target_metadata=get_metadata(bind_key), literal_binds=True, **conf_args)

        with context.begin_transaction():
            context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    For autogenerate, only diff the default bind. For runtime, iterate over
    every bind so the migration runs once per database.
    """

    keys = [None] if _is_autogenerate() else _bind_keys()
    for bind_key in keys:
        logger.info("Running online migrations for bind: %r", bind_key)
        _stash_bind_key(bind_key)
        connectable = get_engine(bind_key)

        with connectable.connect() as connection:
            context.configure(connection=connection, target_metadata=get_metadata(bind_key), **conf_args)

            with context.begin_transaction():
                context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
