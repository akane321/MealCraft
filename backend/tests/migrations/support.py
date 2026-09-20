from dataclasses import dataclass

import sqlalchemy as sa
from sqlalchemy.engine import Engine

from alembic import command
from alembic.config import Config

PRE_TENANCY_REVISION = "20260909_0013"
TENANCY_REVISION = "20260916_0014"
DATABASE_URL_ENV = "MEALCRAFT_MIGRATION_TEST_DATABASE_URL"

COUNTED_TABLES = (
    "users",
    "households",
    "household_memberships",
    "operation_runs",
    "audit_events",
    "household_profiles",
    "household_profile_versions",
    "meal_plans",
    "agent_sessions",
    "agent_messages",
    "agent_runs",
)


@dataclass(frozen=True)
class MigrationDatabase:
    engine: Engine
    alembic_config: Config
    counts_before_upgrade: dict[str, int]

    def upgrade(self, revision: str = "head") -> None:
        command.upgrade(self.alembic_config, revision)

    def downgrade(self, revision: str) -> None:
        command.downgrade(self.alembic_config, revision)

    def counts(self) -> dict[str, int]:
        with self.engine.connect() as connection:
            return {
                table: connection.execute(sa.text(f'SELECT count(*) FROM "{table}"')).scalar_one()
                for table in COUNTED_TABLES
            }
