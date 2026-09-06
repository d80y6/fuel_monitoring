"""Remove TCP columns from Tank model

Revision ID: c3d4e5f6a7b8
Revises: a1b2c3d4e5f6
Create Date: 2025-03-30 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c3d4e5f6a7b8'
down_revision = 'a1b2c3d4e5f6'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('tank', schema=None) as batch_op:
        batch_op.drop_column('host')
        batch_op.drop_column('tcp_port')


def downgrade():
    with op.batch_alter_table('tank', schema=None) as batch_op:
        batch_op.add_column(sa.Column('tcp_port', sa.Integer(), server_default='2000', nullable=True))
        batch_op.add_column(sa.Column('host', sa.String(length=100), nullable=False))
