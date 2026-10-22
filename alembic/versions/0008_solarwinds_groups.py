"""Source-native SolarWinds groups, memberships and snapshot audit counts."""
from alembic import op
import sqlalchemy as sa

revision = '0008_solarwinds_groups'
down_revision = '0007_location_review'
branch_labels = depends_on = None


def upgrade():
    op.add_column('sync_runs', sa.Column('groups_extracted', sa.Integer(), nullable=True))
    op.add_column('sync_runs', sa.Column('memberships_extracted', sa.Integer(), nullable=True))
    op.create_table('solarwinds_groups',
        sa.Column('group_id', sa.Integer(), primary_key=True),
        sa.Column('name', sa.Text(), nullable=False),
        sa.Column('status_code', sa.Integer(), nullable=False),
        sa.Column('status', sa.Text(), nullable=False))
    op.create_table('solarwinds_group_members',
        sa.Column('group_id', sa.Integer(), sa.ForeignKey('solarwinds_groups.group_id'), primary_key=True),
        sa.Column('member_entity_type', sa.String(32), primary_key=True),
        sa.Column('member_id', sa.BigInteger(), primary_key=True),
        sa.Column('child_group_id', sa.Integer(), sa.ForeignKey('solarwinds_groups.group_id')),
        sa.Column('ci_id', sa.Uuid(), sa.ForeignKey('configuration_items.id')),
        sa.CheckConstraint("(member_entity_type = 'Orion.Groups' AND child_group_id = member_id AND child_group_id IS NOT NULL AND ci_id IS NULL) OR "
                           "(member_entity_type = 'Orion.Nodes' AND ci_id IS NOT NULL AND child_group_id IS NULL)",
                           name='ck_sw_group_member_target'))
    op.create_index('ix_sw_group_member_child', 'solarwinds_group_members', ['child_group_id'])
    op.create_index('ix_sw_group_member_ci', 'solarwinds_group_members', ['ci_id'])


def downgrade():
    op.drop_table('solarwinds_group_members')
    op.drop_table('solarwinds_groups')
    with op.batch_alter_table('sync_runs') as batch:
        batch.drop_column('memberships_extracted')
        batch.drop_column('groups_extracted')
