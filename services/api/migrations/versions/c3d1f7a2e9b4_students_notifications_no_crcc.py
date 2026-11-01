"""student register numbers, notifications, last login; remove the CRCC role; admin sign-ups need no approval

Revision ID: c3d1f7a2e9b4
Revises: b7c2e91d4f10
Create Date: 2026-11-01 18:00:00.000000

"""
from collections import defaultdict
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c3d1f7a2e9b4"
down_revision: Union[str, Sequence[str], None] = "b7c2e91d4f10"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("child") as batch:
        batch.add_column(sa.Column("register_no", sa.String(length=20), nullable=True))
        batch.create_unique_constraint("uq_child_register_no", ["register_no"])
    with op.batch_alter_table("app_user") as batch:
        batch.add_column(sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True))
    op.create_table(
        "notification",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("recipient_id", sa.String(length=36), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("subject_user_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["recipient_id"], ["app_user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_notification_recipient_id", "notification", ["recipient_id"])
    op.create_index("ix_notification_subject_user_id", "notification", ["subject_user_id"])
    op.create_index("ix_notification_recipient_read", "notification", ["recipient_id", "read_at"])

    conn = op.get_bind()
    # Register numbers for existing students: STU-<year created>-<sequence within that year>, oldest first.
    rows = conn.execute(sa.text("SELECT id, created_at FROM child ORDER BY created_at, id")).all()
    seq: dict[str, int] = defaultdict(int)
    for cid, created in rows:
        year = str(created)[:4] if created else "2026"
        seq[year] += 1
        conn.execute(sa.text("UPDATE child SET register_no = :r WHERE id = :i"),
                     {"r": f"STU-{year}-{seq[year]:05d}", "i": cid})
    # The CRCC role is retired: remove those accounts and anything pointing at them.
    crcc = [r[0] for r in conn.execute(sa.text("SELECT id FROM app_user WHERE role = 'crcc'")).all()]
    for uid in crcc:
        conn.execute(sa.text("UPDATE app_user SET approver_id = NULL WHERE approver_id = :u"), {"u": uid})
        conn.execute(sa.text("DELETE FROM classroom_teacher WHERE user_id = :u"), {"u": uid})
        conn.execute(sa.text("DELETE FROM app_user WHERE id = :u"), {"u": uid})
    # Admin sign-ups no longer wait for approval: activate the ones still waiting.
    conn.execute(sa.text("UPDATE app_user SET pending = :f, active = :t, approver_id = NULL "
                         "WHERE role = 'admin' AND pending = :t"), {"f": False, "t": True})


def downgrade() -> None:
    op.drop_index("ix_notification_recipient_read", table_name="notification")
    op.drop_index("ix_notification_subject_user_id", table_name="notification")
    op.drop_index("ix_notification_recipient_id", table_name="notification")
    op.drop_table("notification")
    with op.batch_alter_table("app_user") as batch:
        batch.drop_column("last_login_at")
    with op.batch_alter_table("child") as batch:
        batch.drop_constraint("uq_child_register_no", type_="unique")
        batch.drop_column("register_no")
