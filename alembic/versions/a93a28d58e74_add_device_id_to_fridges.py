"""add_device_id_to_fridges

Revision ID: a93a28d58e74
Revises: 2c12f218dd84
Create Date: 2025-12-09 04:08:01.286755

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a93a28d58e74'
down_revision: Union[str, Sequence[str], None] = '2c12f218dd84'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
