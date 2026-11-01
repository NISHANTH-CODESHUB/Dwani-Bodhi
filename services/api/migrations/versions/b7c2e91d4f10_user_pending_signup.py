"""user pending (self sign-up awaiting admin approval)

Revision ID: b7c2e91d4f10
Revises: a451d68a8a69
Create Date: 2026-10-30 22:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b7c2e91d4f10'
down_revision: Union[str, Sequence[str], None] = 'a451d68a8a69'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # batch mode: SQLite cannot ALTER a table to add a foreign key (it rebuilds the table instead).
    with op.batch_alter_table("app_user") as batch:
        batch.add_column(sa.Column("pending", sa.Boolean(), server_default=sa.text("false"), nullable=False))
        batch.add_column(sa.Column("approver_id", sa.String(length=36), nullable=True))
        batch.create_foreign_key("fk_app_user_approver_id", "app_user", ["approver_id"], ["id"])


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("app_user") as batch:
        batch.drop_constraint("fk_app_user_approver_id", type_="foreignkey")
        batch.drop_column("approver_id")
        batch.drop_column("pending")
