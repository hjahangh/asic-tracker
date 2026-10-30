"""Migration configuration depends only on models and the database URL, not auth."""
from __future__ import annotations

import os
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.models import Base

config = context.config
if config.config_file_name:
    fileConfig(config.config_file_name, disable_existing_loggers=False)
target_metadata = Base.metadata


def database_url() -> str:
    direct = os.environ.get("DATABASE_URL", "").strip()
    secret_file = os.environ.get("DATABASE_URL_FILE", "").strip()
    if direct and secret_file:
        raise RuntimeError("Set DATABASE_URL or DATABASE_URL_FILE, not both.")
    if secret_file:
        direct = Path(secret_file).read_text().strip()
    direct = direct or config.get_main_option("sqlalchemy.url", "").strip()
    if not direct:
        raise RuntimeError("Provide DATABASE_URL or DATABASE_URL_FILE before running migrations.")
    return direct


def run_migrations_offline() -> None:
    context.configure(url=database_url(), target_metadata=target_metadata,
                      literal_binds=True, dialect_opts={"paramstyle": "named"}, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    options = config.get_section(config.config_ini_section) or {}
    options["sqlalchemy.url"] = database_url()
    engine = engine_from_config(options, prefix="sqlalchemy.", poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
