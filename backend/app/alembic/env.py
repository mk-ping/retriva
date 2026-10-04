import os
import sys

# make the app folder importable (alembic runs this file from inside /app/alembic)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from alembic import context

from database import Base, engine
import database  # noqa: F401  (registers all models on Base.metadata)

target_metadata = Base.metadata


def run_migrations_online():
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


run_migrations_online()