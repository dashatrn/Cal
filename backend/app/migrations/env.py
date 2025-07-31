from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool
from alembic import context

import os
import sys

# Make sure Alembic can find db.py
sys.path.append(os.path.abspath(os.path.join(os.getcwd(), "app")))
from app.models import Base          #  <-- imports your Event model

# Alembic config object
config = context.config

# Add DATABASE_URL from .env
from dotenv import load_dotenv
load_dotenv()

config.set_main_option("sqlalchemy.url", os.getenv("DATABASE_URL", ""))

# Setup logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Assign metadata for autogenerate support
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
