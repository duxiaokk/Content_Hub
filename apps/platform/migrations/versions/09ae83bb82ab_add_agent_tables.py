"""add agent tables

Revision ID: 09ae83bb82ab
Revises: 32c1f746183e
Create Date: 2026-04-27 14:29:04.443371

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '09ae83bb82ab'
down_revision: Union[str, Sequence[str], None] = '32c1f746183e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass