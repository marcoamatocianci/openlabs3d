from alembic import context
from sqlalchemy import engine_from_config, pool
from app.database import Base
from app import models, config

config_obj = context.config
config_obj.set_main_option('sqlalchemy.url', config.DATABASE_URL.replace('%', '%%'))
target_metadata = Base.metadata
if context.is_offline_mode():
    context.configure(url=config.DATABASE_URL, target_metadata=target_metadata, literal_binds=True, dialect_opts={'paramstyle':'named'})
    with context.begin_transaction(): context.run_migrations()
else:
    engine = engine_from_config(config_obj.get_section(config_obj.config_ini_section), prefix='sqlalchemy.', poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, render_as_batch=True)
        with context.begin_transaction(): context.run_migrations()
