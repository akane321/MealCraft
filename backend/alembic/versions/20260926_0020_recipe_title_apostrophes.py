"""Lower the letter after an apostrophe in release recipe titles ("Polly'S" -> "Polly's").

The release title-cased its names, capitalising the letter after every apostrophe (283
recipes). The importer now writes them correctly; this fixes the rows already imported.
Only the single letter after an apostrophe changes, so the downgrade is a no-op.

Revision ID: 20260926_0020
Revises: 20260925_0019
Create Date: 2026-09-26
"""

import re
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260926_0020"
down_revision: str | None = "20260925_0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APOSTROPHE_CAPITAL = re.compile(r"(?<=[A-Za-z])'([A-Z])\b")


def upgrade() -> None:
    connection = op.get_bind()
    rows = connection.execute(
        sa.text("SELECT id, title FROM recipes WHERE release_version IS NOT NULL AND title LIKE '%''%'")
    ).all()
    for recipe_id, title in rows:
        fixed = APOSTROPHE_CAPITAL.sub(lambda match: "'" + match.group(1).lower(), title)
        if fixed != title:
            connection.execute(
                sa.text("UPDATE recipes SET title = :title WHERE id = :id"), {"title": fixed, "id": recipe_id}
            )


def downgrade() -> None:
    pass
