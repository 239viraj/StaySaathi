"""Initial migration

Revision ID: 41088368f6c9
Revises:
Create Date: 2026-11-07 16:47:58.752208

"""
from alembic import op
import sqlalchemy as sa


revision = '41088368f6c9'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('saved_pg', schema=None) as batch_op:
        batch_op.drop_constraint(
            batch_op.f('unique_student_pg'),
            type_='unique'
        )
        batch_op.create_unique_constraint(
            'unique_student_pg_saved',
            ['student_id', 'pg_id']
        )


def downgrade():
    with op.batch_alter_table('saved_pg', schema=None) as batch_op:
        batch_op.drop_constraint(
            'unique_student_pg_saved',
            type_='unique'
        )
        batch_op.create_unique_constraint(
            batch_op.f('unique_student_pg'),
            ['student_id', 'pg_id']
        )