"""merge heads

Revision ID: a29f40c35240
Revises: a1b2c3d4e5f7, b7c8d9e0f1a2
Create Date: 2026-06-19 17:13:11.782102

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a29f40c35240'
down_revision: Union[str, Sequence[str], None] = ('a1b2c3d4e5f7', 'b7c8d9e0f1a2')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass