"""merge_two_heads

Revision ID: 6a00cfb28a61
Revises: b0c1d2e3f4a5, dc7b5505f37c
Create Date: 2026-06-20 17:24:20.530986

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '6a00cfb28a61'
down_revision: Union[str, Sequence[str], None] = ('b0c1d2e3f4a5', 'dc7b5505f37c')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass