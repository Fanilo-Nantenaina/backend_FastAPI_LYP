"""add_device_id_to_fridges

Revision ID: 1a0551aaf2b4
Revises: a93a28d58e74
Create Date: 2025-12-09 04:16:35.099384

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1a0551aaf2b4'
down_revision: Union[str, Sequence[str], None] = 'a93a28d58e74'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
