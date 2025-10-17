from logging.config import fileConfig
import os
import sys

from sqlalchemy import engine_from_config, pool
from alembic import context
# backend/app/migrations/env.py
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]  # .../backend
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

# Ensure "app" is importable when running alembic from project root
sys.path.append(os.path.abspath(os.path.join(os.getcwd(), "app")))

from app.models import Base
from app.db import DB_URL as DEFAULT_DB_URL, _normalize_db_url  # add _normalize_db_url
# Alembic config object
config = context.config

# Optionally load .env
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

# Configure DB URL for Alembic
db_url = _normalize_db_url(os.getenv("DATABASE_URL") or DEFAULT_DB_URL)
config.set_main_option("sqlalchemy.url", db_url)

# Setup logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# metadata for autogenerate support
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
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()