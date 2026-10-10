"""Canonical location assignments and observed score history."""
from alembic import op
import sqlalchemy as sa

revision = '0006_canonical_locations'
down_revision = '0005_rejected_source_count'
branch_labels = depends_on = None


def upgrade():
    op.create_table('locations', sa.Column('id',sa.String(64),primary_key=True),
                    sa.Column('name',sa.String(128),nullable=False,unique=True),
                    sa.Column('level',sa.String(32),nullable=False),
                    sa.Column('created_at',sa.DateTime(timezone=True),nullable=False),
                    sa.Column('updated_at',sa.DateTime(timezone=True),nullable=False))
    op.create_table('location_mapping_rules',sa.Column('id',sa.String(64),primary_key=True),
                    sa.Column('source_system',sa.String(32),nullable=False),
                    sa.Column('match_key',sa.String(255),nullable=False),
                    sa.Column('location_id',sa.String(64),sa.ForeignKey('locations.id')),
                    sa.Column('revision',sa.String(64),nullable=False),
                    sa.Column('enabled',sa.Boolean(),nullable=False),
                    sa.Column('review_note',sa.String(512)),
                    sa.UniqueConstraint('source_system','match_key',name='uq_location_source_key'))
    with op.batch_alter_table('configuration_items') as batch:
        batch.add_column(sa.Column('location_id',sa.String(64)))
        batch.add_column(sa.Column('location_rule_id',sa.String(64)))
        batch.add_column(sa.Column('location_resolution',sa.String(32),nullable=False,server_default='unassigned'))
        batch.add_column(sa.Column('location_revision',sa.String(64)))
        batch.create_foreign_key('fk_ci_location','locations',['location_id'],['id'])
        batch.create_foreign_key('fk_ci_location_rule','location_mapping_rules',['location_rule_id'],['id'])
        batch.create_index('ix_configuration_items_location_id',['location_id'])
    op.create_table('location_score_snapshots',sa.Column('id',sa.Uuid(),primary_key=True),
                    sa.Column('location_id',sa.String(64),sa.ForeignKey('locations.id'),nullable=False),
                    sa.Column('sync_run_id',sa.Uuid(),sa.ForeignKey('sync_runs.id'),nullable=False),
                    sa.Column('recorded_at',sa.DateTime(timezone=True),nullable=False),
                    sa.Column('policy_version',sa.String(32),nullable=False),
                    sa.Column('mapping_revision',sa.String(64),nullable=False),
                    sa.Column('data',sa.JSON(),nullable=False),
                    sa.UniqueConstraint('location_id','sync_run_id',name='uq_location_run_snapshot'))
    op.create_index('ix_location_snapshot_time','location_score_snapshots',['location_id','recorded_at'])


def downgrade():
    op.drop_table('location_score_snapshots')
    with op.batch_alter_table('configuration_items') as batch:
        batch.drop_index('ix_configuration_items_location_id')
        batch.drop_constraint('fk_ci_location_rule',type_='foreignkey')
        batch.drop_constraint('fk_ci_location',type_='foreignkey')
        for name in ['location_revision','location_resolution','location_rule_id','location_id']:batch.drop_column(name)
    op.drop_table('location_mapping_rules')
    op.drop_table('locations')
