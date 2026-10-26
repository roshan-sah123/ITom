"""Stable groups and reviewed cross-source site correspondences."""
from alembic import op
import sqlalchemy as sa

revision = '0009_group_site_scores'
down_revision = '0008_solarwinds_groups'
branch_labels = depends_on = None


def upgrade():
    op.add_column('solarwinds_groups', sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()))
    op.create_table('solarwinds_group_locations',
        sa.Column('group_id', sa.Integer(), sa.ForeignKey('solarwinds_groups.group_id'), primary_key=True),
        sa.Column('location_id', sa.String(64), sa.ForeignKey('locations.id'), nullable=False),
        sa.Column('approval_status', sa.String(16), nullable=False),
        sa.Column('reviewed_by', sa.String(128), nullable=False),
        sa.Column('reviewed_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('evidence', sa.Text(), nullable=False),
        sa.Column('revision', sa.String(36), nullable=False),
        sa.CheckConstraint("approval_status IN ('APPROVED','REVIEW','REJECTED')", name='ck_sw_group_location_approval'))
    op.create_table('solarwinds_group_location_reviews',
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('group_id', sa.Integer(), sa.ForeignKey('solarwinds_groups.group_id'), nullable=False),
        sa.Column('actor', sa.String(128), nullable=False),
        sa.Column('recorded_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('evidence', sa.Text(), nullable=False),
        sa.Column('before_data', sa.JSON(), nullable=False),
        sa.Column('after_data', sa.JSON(), nullable=False))


def downgrade():
    op.drop_table('solarwinds_group_location_reviews')
    op.drop_table('solarwinds_group_locations')
    with op.batch_alter_table('solarwinds_groups') as batch:
        batch.drop_column('is_active')
