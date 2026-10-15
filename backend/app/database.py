from sqlalchemy import Boolean, Column, Float, ForeignKey, Index, Integer, MetaData, String, Table, Text, create_engine, event
from sqlalchemy.engine import Engine


metadata = MetaData()

bins = Table('bins', metadata, Column('id', String(120), primary_key=True), Column('payload', Text, nullable=False))
vehicles = Table('vehicles', metadata, Column('id', String(120), primary_key=True), Column('payload', Text, nullable=False))
readings = Table(
    'readings', metadata,
    Column('id', Integer, primary_key=True, autoincrement=True),
    Column('bin_id', String(120), nullable=False), Column('fill', Float, nullable=False),
    Column('ts', String(64), nullable=False), Column('weight', Float),
)
Index('ix_readings_bin_ts', readings.c.bin_id, readings.c.ts)
routes = Table('routes', metadata, Column('id', String(120), primary_key=True), Column('payload', Text, nullable=False))
events = Table('events', metadata, Column('id', String(120), primary_key=True), Column('payload', Text, nullable=False))
collections = Table(
    'collections', metadata,
    Column('id', Integer, primary_key=True, autoincrement=True),
    Column('route_id', String(120), nullable=False), Column('bin_id', String(120), nullable=False),
    Column('waste_type', String(32), nullable=False), Column('volume_liters', Float, nullable=False),
    Column('collected_at', String(64), nullable=False),
)
Index('ix_collections_route_time', collections.c.route_id, collections.c.collected_at)
app_metadata = Table('metadata', metadata, Column('key', String(120), primary_key=True), Column('value', Text, nullable=False))
forecasts = Table(
    'forecasts', metadata,
    Column('id', Integer, primary_key=True, autoincrement=True),
    Column('bin_id', String(120), ForeignKey('bins.id'), nullable=False),
    Column('generated_at', String(64), nullable=False), Column('payload', Text, nullable=False),
)
Index('ix_forecasts_bin_time', forecasts.c.bin_id, forecasts.c.generated_at)
users = Table(
    'users', metadata,
    Column('id', Integer, primary_key=True, autoincrement=True),
    Column('username', String(254), nullable=False, unique=True),
    Column('password_hash', Text, nullable=False), Column('role', String(32), nullable=False),
    Column('active', Boolean, nullable=False, default=True), Column('created_at', String(64), nullable=False),
)
approval_history = Table(
    'approval_history', metadata,
    Column('id', Integer, primary_key=True, autoincrement=True),
    Column('route_id', String(120), ForeignKey('routes.id'), nullable=False),
    Column('operator_user_id', Integer, ForeignKey('users.id'), nullable=False),
    Column('decision', String(16), nullable=False), Column('comment', Text, nullable=False),
    Column('created_at', String(64), nullable=False),
)
audit_logs = Table(
    'audit_logs', metadata,
    Column('id', Integer, primary_key=True, autoincrement=True),
    Column('actor_user_id', Integer, ForeignKey('users.id')),
    Column('action', String(120), nullable=False), Column('entity_type', String(64), nullable=False),
    Column('entity_id', String(120), nullable=False), Column('details', Text, nullable=False),
    Column('created_at', String(64), nullable=False),
)


def create_database_engine(database_url: str) -> Engine:
    options = {'pool_pre_ping': True, 'pool_recycle': 1800}
    if database_url.startswith('sqlite:'):
        options['connect_args'] = {'check_same_thread': False, 'timeout': 30}
    elif database_url.startswith('postgresql+'):
        options['connect_args'] = {'connect_timeout': 10}
    else:
        raise RuntimeError('DATABASE_URL must use SQLite locally or PostgreSQL with psycopg in production.')

    engine = create_engine(database_url, **options)
    if database_url.startswith('sqlite:'):
        @event.listens_for(engine, 'connect')
        def enable_sqlite_foreign_keys(connection, _record):
            cursor = connection.cursor()
            cursor.execute('PRAGMA foreign_keys=ON')
            cursor.execute('PRAGMA busy_timeout=30000')
            cursor.close()
    return engine
