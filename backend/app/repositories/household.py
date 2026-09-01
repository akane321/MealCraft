from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.household import HouseholdProfile, HouseholdProfileVersion
from app.models.meal_plan import MealPlan
from app.schemas.household import HouseholdProfileWrite


class HouseholdProfileVersionConflictError(RuntimeError):
    pass


class HouseholdProfileRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(self, payload: HouseholdProfileWrite) -> HouseholdProfile:
        profile = HouseholdProfile(name=payload.name, current_version=1)
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

    def get(self, profile_id: int) -> HouseholdProfile | None:
        statement = (
            select(HouseholdProfile)
            .where(HouseholdProfile.id == profile_id)
            .options(selectinload(HouseholdProfile.versions))
        )
        return self.session.scalars(statement).unique().one_or_none()

    def get_current(self) -> HouseholdProfile | None:
        statement = (
            select(HouseholdProfile)
            .options(selectinload(HouseholdProfile.versions))
            .order_by(HouseholdProfile.updated_at.desc(), HouseholdProfile.id.desc())
            .limit(1)
        )
        return self.session.scalars(statement).unique().one_or_none()

    def get_version(self, profile_id: int, version: int) -> HouseholdProfileVersion | None:
        statement = select(HouseholdProfileVersion).where(
            HouseholdProfileVersion.profile_id == profile_id,
            HouseholdProfileVersion.version == version,
        )
        return self.session.scalars(statement).one_or_none()

    def latest_plan_id(self, profile_id: int) -> int | None:
        statement = (
            select(MealPlan.id)
            .where(MealPlan.household_profile_id == profile_id)
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
        allergens = sorted({item for member in payload.members for item in member.allergens})
        excluded = sorted({item for member in payload.members for item in member.excluded_ingredients})
        dietary = sorted({item for member in payload.members for item in member.dietary_preferences})
        return HouseholdProfileVersion(
            version=version,
            members=[member.model_dump(mode="json") for member in payload.members],
            planning_household_size=sum(member.servings_per_meal for member in payload.members),
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
        )
