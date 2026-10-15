from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = '20261015_0001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    existing = set(inspect(bind).get_table_names())
    if 'bins' not in existing:
        op.create_table('bins', sa.Column('id', sa.String(120), primary_key=True), sa.Column('payload', sa.Text(), nullable=False))
    if 'vehicles' not in existing:
        op.create_table('vehicles', sa.Column('id', sa.String(120), primary_key=True), sa.Column('payload', sa.Text(), nullable=False))
    if 'readings' not in existing:
        op.create_table(
            'readings', sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column('bin_id', sa.String(120), nullable=False), sa.Column('fill', sa.Float(), nullable=False),
            sa.Column('ts', sa.String(64), nullable=False), sa.Column('weight', sa.Float()),
        )
    if 'routes' not in existing:
        op.create_table('routes', sa.Column('id', sa.String(120), primary_key=True), sa.Column('payload', sa.Text(), nullable=False))
    if 'events' not in existing:
        op.create_table('events', sa.Column('id', sa.String(120), primary_key=True), sa.Column('payload', sa.Text(), nullable=False))
    if 'collections' not in existing:
        op.create_table(
            'collections', sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column('route_id', sa.String(120), nullable=False), sa.Column('bin_id', sa.String(120), nullable=False),
            sa.Column('waste_type', sa.String(32), nullable=False), sa.Column('volume_liters', sa.Float(), nullable=False),
            sa.Column('collected_at', sa.String(64), nullable=False),
        )
    if 'metadata' not in existing:
        op.create_table('metadata', sa.Column('key', sa.String(120), primary_key=True), sa.Column('value', sa.Text(), nullable=False))
    if 'forecasts' not in existing:
        op.create_table(
            'forecasts', sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column('bin_id', sa.String(120), sa.ForeignKey('bins.id'), nullable=False),
            sa.Column('generated_at', sa.String(64), nullable=False), sa.Column('payload', sa.Text(), nullable=False),
        )
    if 'users' not in existing:
        op.create_table(
            'users', sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column('username', sa.String(254), nullable=False, unique=True),
            sa.Column('password_hash', sa.Text(), nullable=False), sa.Column('role', sa.String(32), nullable=False),
            sa.Column('active', sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column('created_at', sa.String(64), nullable=False),
        )
    if 'approval_history' not in existing:
        op.create_table(
            'approval_history', sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column('route_id', sa.String(120), sa.ForeignKey('routes.id'), nullable=False),
            sa.Column('operator_user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
            sa.Column('decision', sa.String(16), nullable=False), sa.Column('comment', sa.Text(), nullable=False),
            sa.Column('created_at', sa.String(64), nullable=False),
        )
    if 'audit_logs' not in existing:
        op.create_table(
            'audit_logs', sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column('actor_user_id', sa.Integer(), sa.ForeignKey('users.id')),
            sa.Column('action', sa.String(120), nullable=False), sa.Column('entity_type', sa.String(64), nullable=False),
            sa.Column('entity_id', sa.String(120), nullable=False), sa.Column('details', sa.Text(), nullable=False),
            sa.Column('created_at', sa.String(64), nullable=False),
        )
    inspector = inspect(bind)
    for table_name, index_name, columns in (
        ('readings', 'ix_readings_bin_ts', ['bin_id', 'ts']),
        ('collections', 'ix_collections_route_time', ['route_id', 'collected_at']),
        ('forecasts', 'ix_forecasts_bin_time', ['bin_id', 'generated_at']),
    ):
        indexes = {index['name'] for index in inspector.get_indexes(table_name)}
        if index_name not in indexes:
            op.create_index(index_name, table_name, columns)


def downgrade():
    raise RuntimeError('Automatic destructive downgrades are disabled to protect operational records.')
