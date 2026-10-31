from decimal import Decimal
from fractions import Fraction
from math import ceil

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.household import HouseholdProfile, HouseholdProfileVersion
from app.models.meal_plan import MealPlan
from app.schemas.household import HouseholdProfileWrite, household_allergens


class HouseholdProfileVersionConflictError(RuntimeError):
    pass


class HouseholdProfileRepository:
    def __init__(self, session: Session, *, household_id: int) -> None:
        self.session = session
        self.household_id = household_id

    def create(self, payload: HouseholdProfileWrite) -> HouseholdProfile:
        profile = HouseholdProfile(household_id=self.household_id, name=payload.name, current_version=1)
        profile.versions.append(self._build_version(payload=payload, version=1))
        self.session.add(profile)
        self.session.commit()
        return self.get(profile.id) or profile

    def update(
        self,
        profile: HouseholdProfile,
        *,
        payload: HouseholdProfileWrite,
        expected_version: int,
    ) -> HouseholdProfile:
        if profile.current_version != expected_version:
            raise HouseholdProfileVersionConflictError(
                f"Household profile is now at version {profile.current_version}; refresh before saving."
            )
        next_version = profile.current_version + 1
        profile.name = payload.name
        profile.current_version = next_version
        profile.versions.append(self._build_version(payload=payload, version=next_version))
        self.session.commit()
        return self.get(profile.id) or profile

    def keep_plan_shape(self, plan_shape: dict) -> HouseholdProfile | None:
        """A new profile version that differs only in its meals and dishes (ADR-0046: a change made in
        the conversation becomes the household's usual shape when they say so)."""
        return self._next_version({"plan_shape": plan_shape, "meal_composition": None})

    def keep_requires_halal(self) -> HouseholdProfile | None:
        """A new profile version that differs only in being halal (ADR-0104: a halal week asked for in the
        conversation becomes the household's usual one when they say so)."""
        return self._next_version({"requires_halal": True})

    def _next_version(self, changes: dict) -> HouseholdProfile | None:
        profile = self.get_current()
        if profile is None:
            return None
        current = self.current_version(profile)
        copied = {
            column.key: getattr(current, column.key)
            for column in HouseholdProfileVersion.__table__.columns
            if column.key not in {"id", "profile_id", "version", "created_at"}
        }
        profile.current_version += 1
        profile.versions.append(HouseholdProfileVersion(**{**copied, **changes}, version=profile.current_version))
        self.session.commit()
        return self.get(profile.id)

    def get(self, profile_id: int) -> HouseholdProfile | None:
        statement = (
            select(HouseholdProfile)
            .where(HouseholdProfile.id == profile_id, HouseholdProfile.household_id == self.household_id)
            .options(selectinload(HouseholdProfile.versions))
        )
        return self.session.scalars(statement).unique().one_or_none()

    def get_current(self) -> HouseholdProfile | None:
        statement = (
            select(HouseholdProfile)
            .where(HouseholdProfile.household_id == self.household_id)
            .options(selectinload(HouseholdProfile.versions))
            .order_by(HouseholdProfile.updated_at.desc(), HouseholdProfile.id.desc())
            .limit(1)
        )
        return self.session.scalars(statement).unique().one_or_none()

    def get_version(self, profile_id: int, version: int) -> HouseholdProfileVersion | None:
        statement = select(HouseholdProfileVersion).where(
            HouseholdProfileVersion.profile_id == profile_id,
            HouseholdProfileVersion.version == version,
            HouseholdProfileVersion.profile.has(HouseholdProfile.household_id == self.household_id),
        )
        return self.session.scalars(statement).one_or_none()

    def latest_plan_id(self, profile_id: int) -> int | None:
        statement = (
            select(MealPlan.id)
            .where(
                MealPlan.household_profile_id == profile_id,
                MealPlan.household_id == self.household_id,
            )
            .order_by(MealPlan.created_at.desc(), MealPlan.id.desc())
            .limit(1)
        )
        return self.session.scalars(statement).one_or_none()

    @staticmethod
    def current_version(profile: HouseholdProfile) -> HouseholdProfileVersion:
        version = next((item for item in profile.versions if item.version == profile.current_version), None)
        if version is None:
            raise LookupError("Current household profile version is missing")
        return version

    @staticmethod
    def _build_version(*, payload: HouseholdProfileWrite, version: int) -> HouseholdProfileVersion:
        # What the whole household avoids: every member's allergens, less the ones only their own member avoids
        # (ADR-0071 section 2). The exclusion and diet union columns stay written for compatibility
        # (docs/design/sprint2-schema-foundation.md); planning reads them per member, not from these.
        allergens = household_allergens(payload.members)
        excluded = sorted({item for member in payload.members for item in member.excluded_ingredients})
        dietary = sorted({item for member in payload.members for item in member.dietary_preferences})
        return HouseholdProfileVersion(
            version=version,
            members=[member.model_dump(mode="json") for member in payload.members],
            # The usually-home members' portions, rounded up: the union column stays written (the foundation
            # contract) and buys enough at the recommendation stage; each meal is planned for its exact sum.
            planning_household_size=min(
                12, ceil(sum(Fraction(str(m.resolved_servings()[0])) for m in payload.members if m.default_present))
            ),
            max_cooking_time_minutes=payload.max_cooking_time_minutes,
            budget_per_meal_sgd=(
                Decimal(str(payload.budget_per_meal_sgd)) if payload.budget_per_meal_sgd is not None else None
            ),
            weekly_budget_sgd=(
                Decimal(str(payload.weekly_budget_sgd)) if payload.weekly_budget_sgd is not None else None
            ),
            allergens=allergens,
            excluded_ingredients=excluded,
            dietary_preferences=dietary,
            health_preferences=list(payload.health_preferences),
            nutrition_targets=payload.nutrition_targets.model_dump(mode="json"),
            max_sodium_mg_per_meal=(
                Decimal(str(payload.max_sodium_mg_per_meal)) if payload.max_sodium_mg_per_meal is not None else None
            ),
            available_ingredients=[item.model_dump(mode="json") for item in payload.available_ingredients],
            pricing_mode=payload.pricing_mode,
            meal_composition=(
                [role.model_dump(mode="json") for role in payload.meal_composition]
                if payload.meal_composition is not None
                else None
            ),
            plan_shape=payload.plan_shape.model_dump(mode="json") if payload.plan_shape is not None else None,
            # An empty list is stored as NULL, which means the same (docs/design/sprint2-schema-foundation.md).
            presence_rules=[rule.model_dump(mode="json") for rule in payload.presence_rules] or None,
            cooking_time_rules=[rule.model_dump(mode="json") for rule in payload.cooking_time_rules] or None,
            missing_basics=list(payload.missing_basics) or None,
            nutrition_limits=[limit.model_dump(mode="json") for limit in payload.nutrition_limits] or None,
            missing_equipment=list(payload.missing_equipment) or None,
            requires_halal=payload.requires_halal,
        )
