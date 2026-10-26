"""Explicit mapping approval and append-only reviewer decisions."""
from alembic import op
import sqlalchemy as sa

revision = '0007_location_review'
down_revision = '0006_canonical_locations'
branch_labels = depends_on = None


def upgrade():
    with op.batch_alter_table('location_mapping_rules') as batch:
        batch.add_column(sa.Column('approval_status',sa.String(16),nullable=False,server_default='PENDING'))
        batch.add_column(sa.Column('reviewed_by',sa.String(128)))
        batch.add_column(sa.Column('reviewed_at',sa.DateTime(timezone=True)))
        batch.create_check_constraint('ck_location_rule_approval',"approval_status IN ('PENDING','APPROVED','REJECTED')")
        batch.create_check_constraint('ck_location_approved_target',"approval_status != 'APPROVED' OR location_id IS NOT NULL")
    # Preserve the old assignment/review distinction once during migration.
    # No human reviewer or date is invented for inherited approvals.
    op.execute(sa.text("""UPDATE location_mapping_rules SET approval_status='APPROVED'
        WHERE location_id IS NOT NULL
          AND lower(coalesce(review_note,'')) NOT LIKE '%conflict%'
          AND lower(coalesce(review_note,'')) NOT LIKE '%versus%'"""))
    op.create_index('ix_location_rule_review_queue','location_mapping_rules',['approval_status','source_system'])
    op.create_table('location_mapping_reviews',
        sa.Column('id',sa.Uuid(),primary_key=True),
        sa.Column('rule_id',sa.String(64),sa.ForeignKey('location_mapping_rules.id'),nullable=False),
        sa.Column('reviewed_by',sa.String(128),nullable=False),
        sa.Column('reviewed_at',sa.DateTime(timezone=True),nullable=False),
        sa.Column('comment',sa.String(512)),
        sa.Column('before_data',sa.JSON(),nullable=False),
        sa.Column('after_data',sa.JSON(),nullable=False))
    op.create_index('ix_location_review_rule_time','location_mapping_reviews',['rule_id','reviewed_at'])


def downgrade():
    op.drop_table('location_mapping_reviews')
    with op.batch_alter_table('location_mapping_rules') as batch:
        batch.drop_index('ix_location_rule_review_queue')
        batch.drop_constraint('ck_location_approved_target',type_='check')
        batch.drop_constraint('ck_location_rule_approval',type_='check')
        for column in ['reviewed_at','reviewed_by','approval_status']:
            batch.drop_column(column)
