"""Persist geographic scores and their supporting inventory."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = '0010_geographic_reporting'
down_revision = '0009_group_site_scores'
branch_labels = depends_on = None


def upgrade():
    op.create_table('geographic_score_snapshots',
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('location_id', sa.String(64), sa.ForeignKey('locations.id'), nullable=False),
        sa.Column('sync_run_id', sa.Uuid(), sa.ForeignKey('sync_runs.id'), nullable=False),
        sa.Column('location_name', sa.String(128), nullable=False),
        sa.Column('match_level', sa.String(16), nullable=False),
        sa.Column('recorded_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('policy_version', sa.String(32), nullable=False),
        sa.Column('data', sa.JSON().with_variant(JSONB(), 'postgresql'), nullable=False),
        sa.UniqueConstraint('location_id', 'sync_run_id', name='uq_geographic_location_run'))
    op.create_index('ix_geographic_snapshot_time', 'geographic_score_snapshots', ['location_id', 'recorded_at'])
    op.create_table('geographic_score_inventory',
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('snapshot_id', sa.Uuid(), sa.ForeignKey('geographic_score_snapshots.id', ondelete='CASCADE'), nullable=False),
        sa.Column('ci_id', sa.Uuid(), sa.ForeignKey('configuration_items.id'), nullable=False),
        sa.Column('source_system', sa.String(32), nullable=False),
        sa.Column('source_id', sa.String(128), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('ci_type', sa.String(64), nullable=False),
        sa.Column('status', sa.String(32), nullable=False),
        sa.Column('source_location', sa.String(128)),
        sa.Column('checkin_at_source', sa.String(128)),
        sa.Column('last_sync_time', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('snapshot_id', 'ci_id', name='uq_geographic_snapshot_ci'))
    op.create_index('ix_geographic_inventory_snapshot', 'geographic_score_inventory', ['snapshot_id'])


def downgrade():
    op.drop_table('geographic_score_inventory')
    op.drop_table('geographic_score_snapshots')
