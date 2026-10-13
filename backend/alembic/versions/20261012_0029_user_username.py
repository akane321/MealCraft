"""A username to sign in with.

People sign in with a username by default, or with their email (2026-10-12, owner). Every existing account gets
one from its email's local part, with a number added where two would clash, so nobody has to choose one first.

Revision ID: 20261012_0029
Revises: 20261012_0028
Create Date: 2026-10-12
"""

import re
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261012_0029"
down_revision: str | None = "20261012_0028"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _from_email(email: str) -> str:
    # The same rule as app.schemas.platform.username_from_email, frozen here as migrations must be.
    local = re.sub(r"[^\w.-]", "-", email.split("@", 1)[0].casefold()).strip(".-_")[:28]
    return local if len(local) >= 2 else f"user-{local}".rstrip("-")


def upgrade() -> None:
    op.add_column("users", sa.Column("username", sa.String(length=32), nullable=True))
    connection = op.get_bind()
    users = sa.table("users", sa.column("id", sa.BigInteger), sa.column("normalized_email"), sa.column("username"))
    taken: set[str] = set()
    for user_id, email in connection.execute(sa.select(users.c.id, users.c.normalized_email).order_by(users.c.id)):
        base = _from_email(email)
        name, number = base, 2
        while name in taken:
            name, number = f"{base}-{number}", number + 1
        taken.add(name)
        connection.execute(sa.update(users).where(users.c.id == user_id).values(username=name))
    op.create_index("users_username_key", "users", ["username"], unique=True)


def downgrade() -> None:
    op.drop_index("users_username_key", table_name="users")
    op.drop_column("users", "username")
