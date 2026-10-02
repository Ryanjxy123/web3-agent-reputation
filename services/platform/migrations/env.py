from alembic import context
from reputation_platform.infrastructure.db.connection import engine
from reputation_platform.infrastructure.db.tables import metadata

config = context.config
if context.is_offline_mode():
    raise RuntimeError("Use a real PostgreSQL connection for migration validation")
with engine().connect() as connection:
    context.configure(connection=connection, target_metadata=metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()
