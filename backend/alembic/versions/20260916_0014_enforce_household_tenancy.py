"""Enforce household ownership for private product roots.

Revision ID: 20260916_0014
Revises: 20260909_0013
Create Date: 2026-09-16
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260916_0014"
down_revision: str | None = "20260909_0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

LEGACY_EMAIL = "legacy-import@mealcraft.invalid"


def _legacy_household_id() -> int:
    bind = op.get_bind()
    users = sa.table(
        "users",
        sa.column("id", sa.BigInteger()),
        sa.column("normalized_email", sa.String()),
        sa.column("display_name", sa.String()),
        sa.column("status", sa.String()),
        sa.column("system_role", sa.String()),
    )
    households = sa.table(
        "households",
        sa.column("id", sa.BigInteger()),
        sa.column("name", sa.String()),
        sa.column("created_by_user_id", sa.BigInteger()),
    )
    memberships = sa.table(
        "household_memberships",
        sa.column("household_id", sa.BigInteger()),
        sa.column("user_id", sa.BigInteger()),
        sa.column("role", sa.String()),
        sa.column("status", sa.String()),
    )

    user_id = bind.execute(sa.select(users.c.id).where(users.c.normalized_email == LEGACY_EMAIL)).scalar_one_or_none()
    if user_id is None:
        user_id = bind.execute(
            users.insert()
            .values(
                normalized_email=LEGACY_EMAIL,
                display_name="Legacy import owner",
                status="suspended",
                system_role="ordinary_user",
            )
            .returning(users.c.id)
        ).scalar_one()

    household_id = bind.execute(
        sa.select(memberships.c.household_id).where(memberships.c.user_id == user_id)
    ).scalar_one_or_none()
    if household_id is None:
        household_id = bind.execute(
            households.insert()
            .values(name="Legacy imported household", created_by_user_id=user_id)
            .returning(households.c.id)
        ).scalar_one()
        bind.execute(
            memberships.insert().values(
                household_id=household_id,
                user_id=user_id,
                role="owner",
                status="active",
            )
        )
    return household_id


def upgrade() -> None:
    op.add_column("household_profiles", sa.Column("household_id", sa.BigInteger(), nullable=True))
    op.add_column("meal_plans", sa.Column("household_id", sa.BigInteger(), nullable=True))
    op.add_column("agent_sessions", sa.Column("household_id", sa.BigInteger(), nullable=True))

    legacy_household_id = _legacy_household_id()
    bind = op.get_bind()
    bind.execute(
        sa.text("UPDATE household_profiles SET household_id = :id WHERE household_id IS NULL"),
        {"id": legacy_household_id},
    )
    bind.execute(
        sa.text("UPDATE meal_plans SET household_id = :id WHERE household_id IS NULL"),
        {"id": legacy_household_id},
    )
    bind.execute(
        sa.text("UPDATE agent_sessions SET household_id = :id WHERE household_id IS NULL"),
        {"id": legacy_household_id},
    )
    bind.execute(
        sa.text(
            "UPDATE agent_runs AS runs SET household_id = sessions.household_id "
            "FROM agent_sessions AS sessions "
            "WHERE runs.agent_session_id = sessions.id AND runs.household_id IS NULL"
        )
    )

    op.create_foreign_key(
        "household_profiles_household_id_fkey",
        "household_profiles",
        "households",
        ["household_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_unique_constraint("household_profiles_household_key", "household_profiles", ["household_id"])
    op.create_foreign_key(
        "meal_plans_household_id_fkey",
        "meal_plans",
        "households",
        ["household_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index("meal_plans_household_created_idx", "meal_plans", ["household_id", "created_at", "id"])
    op.create_foreign_key(
        "agent_sessions_household_id_fkey",
        "agent_sessions",
        "households",
        ["household_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index(
        "agent_sessions_household_updated_idx",
        "agent_sessions",
        ["household_id", "updated_at", "id"],
    )

    op.alter_column("household_profiles", "household_id", nullable=False)
    op.alter_column("meal_plans", "household_id", nullable=False)
    op.alter_column("agent_sessions", "household_id", nullable=False)


def downgrade() -> None:
    op.drop_index("agent_sessions_household_updated_idx", table_name="agent_sessions")
    op.drop_constraint("agent_sessions_household_id_fkey", "agent_sessions", type_="foreignkey")
    op.drop_index("meal_plans_household_created_idx", table_name="meal_plans")
    op.drop_constraint("meal_plans_household_id_fkey", "meal_plans", type_="foreignkey")
    op.drop_constraint("household_profiles_household_key", "household_profiles", type_="unique")
    op.drop_constraint("household_profiles_household_id_fkey", "household_profiles", type_="foreignkey")
    op.drop_column("agent_sessions", "household_id")
    op.drop_column("meal_plans", "household_id")
    op.drop_column("household_profiles", "household_id")
