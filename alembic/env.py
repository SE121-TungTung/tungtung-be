from logging.config import fileConfig
from sqlalchemy import engine_from_config
from sqlalchemy import pool
import os
from dotenv import load_dotenv
from alembic import context
from app.models.academic import  Room, Course
from app.models.user import User 

load_dotenv()
target_metadata = None

config = context.config

try:
    from app.models import base  # noqa: F401
    target_metadata = base.Base.metadata
except ImportError:
    print("WARNING: Could not import Base class for target_metadata.")
    target_metadata = None

implemented_tables = target_metadata.tables.keys() if target_metadata else []

database_url = os.getenv("DATABASE_URL")
if database_url:
    config.set_main_option("sqlalchemy.url", database_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
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
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    def include_only_implemented(object, name, type, reflected, compare_to):
        """Chỉ bao gồm các đối tượng có trong code (target_metadata)."""
        if type == 'table':
            # Chỉ bao gồm bảng nếu nó có trong danh sách đã implement
            return name in implemented_tables
        return True # Cho phép các đối tượng khác (index, schema) đi qua

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            # GỌI HÀM LỌC CHUẨN
            include_object=include_only_implemented,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
