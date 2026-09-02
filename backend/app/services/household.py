from app.models.household import HouseholdProfile, HouseholdProfileVersion
from app.repositories.household import HouseholdProfileRepository, HouseholdProfileVersionConflictError
from app.repositories.meal_plan import MealPlanRepository
from app.schemas.household import (
    HouseholdProfilePlanRequest,
    HouseholdProfilePlanResponse,
    HouseholdProfileResponse,
    HouseholdProfileUpdate,
    HouseholdProfileVersionCollectionResponse,
    HouseholdProfileVersionResponse,
    HouseholdProfileWrite,
    ProfileConstraintChange,
)
from app.schemas.meal_plan import WeeklyMealPlanRequest
from app.schemas.recommendation import NutritionTargets
from app.services.meal_plan import WeeklyMealPlanService


class HouseholdProfileNotFoundError(RuntimeError):
    pass


class HouseholdProfileAlreadyExistsError(RuntimeError):
    pass


class HouseholdProfilePlanError(RuntimeError):
    pass


class HouseholdProfileService:
    def __init__(
        self,
        *,
        repository: HouseholdProfileRepository,
        meal_plan_repository: MealPlanRepository,
        meal_plan_service: WeeklyMealPlanService,
    ) -> None:
        self.repository = repository
        self.meal_plan_repository = meal_plan_repository
        self.meal_plan_service = meal_plan_service

    def create(self, payload: HouseholdProfileWrite) -> HouseholdProfileResponse:
        if self.repository.get_current() is not None:
            raise HouseholdProfileAlreadyExistsError(
                "The MVP supports one household profile; update the existing profile."
            )
        return self._profile_response(self.repository.create(payload))

    def get_current(self) -> HouseholdProfileResponse:
        profile = self.repository.get_current()
        if profile is None:
            raise HouseholdProfileNotFoundError("Household profile not found")
        return self._profile_response(profile)

    def get(self, profile_id: int) -> HouseholdProfileResponse:
        return self._profile_response(self._require_profile(profile_id))

    def update(self, profile_id: int, payload: HouseholdProfileUpdate) -> HouseholdProfileResponse:
        profile = self._require_profile(profile_id)
        write_payload = HouseholdProfileWrite.model_validate(payload.model_dump(exclude={"expected_version"}))
        try:
            updated = self.repository.update(
                profile,
                payload=write_payload,
                expected_version=payload.expected_version,
            )
        except HouseholdProfileVersionConflictError:
            raise
        return self._profile_response(updated)

    def list_versions(self, profile_id: int) -> HouseholdProfileVersionCollectionResponse:
        profile = self._require_profile(profile_id)
        return HouseholdProfileVersionCollectionResponse(
            items=[self._version_response(item) for item in sorted(profile.versions, key=lambda item: -item.version)]
        )

    def generate_plan(
        self,
        profile_id: int,
        request: HouseholdProfilePlanRequest,
    ) -> HouseholdProfilePlanResponse:
        profile = self._require_profile(profile_id)
        version = self._select_version(profile, request.profile_version)
        constraints = self._planning_constraints(version, request)
        plan = self.meal_plan_service.generate(
            constraints,
            household_profile_id=profile.id,
            household_profile_version=version.version,
        )
        return HouseholdProfilePlanResponse(
            profile_id=profile.id,
            profile_version=version.version,
            replaces_plan_id=None,
            constraint_changes=[],
            plan=plan,
        )

    def replan(
        self,
        profile_id: int,
        plan_id: int,
        request: HouseholdProfilePlanRequest,
    ) -> HouseholdProfilePlanResponse:
        profile = self._require_profile(profile_id)
        previous = self.meal_plan_repository.get(plan_id)
        if previous is None:
            raise HouseholdProfilePlanError("Meal plan not found")
        if previous.household_profile_id != profile_id:
            raise HouseholdProfilePlanError("Meal plan was not generated from this household profile")

        version = self._select_version(profile, request.profile_version)
        replan_request = request.model_copy(update={"start_date": previous.start_date})
        constraints = self._planning_constraints(version, replan_request)
        current_constraints = previous.constraints if isinstance(previous.constraints, dict) else {}
        next_constraints = constraints.model_dump(mode="json")
        changes = self._constraint_changes(current_constraints, next_constraints)
        plan = self.meal_plan_service.generate(
            constraints,
            household_profile_id=profile.id,
            household_profile_version=version.version,
            replaces_plan_id=previous.id,
        )
        return HouseholdProfilePlanResponse(
            profile_id=profile.id,
            profile_version=version.version,
            replaces_plan_id=previous.id,
            constraint_changes=changes,
            plan=plan,
        )

    def _require_profile(self, profile_id: int) -> HouseholdProfile:
        profile = self.repository.get(profile_id)
        if profile is None:
            raise HouseholdProfileNotFoundError("Household profile not found")
        return profile

    def _select_version(self, profile: HouseholdProfile, requested: int | None) -> HouseholdProfileVersion:
        version_number = requested or profile.current_version
        version = next((item for item in profile.versions if item.version == version_number), None)
        if version is None:
            raise HouseholdProfileNotFoundError(f"Household profile version {version_number} not found")
        return version

    def _profile_response(self, profile: HouseholdProfile) -> HouseholdProfileResponse:
        current = self.repository.current_version(profile)
        return HouseholdProfileResponse(
            id=profile.id,
            name=profile.name,
            current_version=profile.current_version,
            current=self._version_response(current),
            latest_plan_id=self.repository.latest_plan_id(profile.id),
            created_at=profile.created_at,
            updated_at=profile.updated_at,
        )

    @staticmethod
    def _version_response(version: HouseholdProfileVersion) -> HouseholdProfileVersionResponse:
        return HouseholdProfileVersionResponse(
            version=version.version,
            members=version.members,
            planning_household_size=version.planning_household_size,
            max_cooking_time_minutes=version.max_cooking_time_minutes,
            budget_per_meal_sgd=(
                float(version.budget_per_meal_sgd) if version.budget_per_meal_sgd is not None else None
            ),
            weekly_budget_sgd=(float(version.weekly_budget_sgd) if version.weekly_budget_sgd is not None else None),
            allergens=version.allergens,
            excluded_ingredients=version.excluded_ingredients,
            dietary_preferences=version.dietary_preferences,
            health_preferences=version.health_preferences,
            nutrition_targets=version.nutrition_targets,
            max_sodium_mg_per_meal=(
                float(version.max_sodium_mg_per_meal) if version.max_sodium_mg_per_meal is not None else None
            ),
            available_ingredients=version.available_ingredients,
            pricing_mode=version.pricing_mode,
            created_at=version.created_at,
        )

    @staticmethod
    def _planning_constraints(
        version: HouseholdProfileVersion,
        request: HouseholdProfilePlanRequest,
    ) -> WeeklyMealPlanRequest:
        values = {
            "start_date": request.start_date,
            "day_count": 7,
            "household_size": version.planning_household_size,
            "max_cooking_time_minutes": version.max_cooking_time_minutes,
            "budget_per_meal_sgd": (
                float(version.budget_per_meal_sgd) if version.budget_per_meal_sgd is not None else None
            ),
            "weekly_budget_sgd": float(version.weekly_budget_sgd) if version.weekly_budget_sgd is not None else None,
            "allergens": version.allergens,
            "excluded_ingredients": version.excluded_ingredients,
            "dietary_preferences": version.dietary_preferences,
            "health_preferences": version.health_preferences,
            "nutrition_targets": NutritionTargets.model_validate(version.nutrition_targets),
            "max_sodium_mg_per_meal": (
                float(version.max_sodium_mg_per_meal) if version.max_sodium_mg_per_meal is not None else None
            ),
            "available_ingredients": version.available_ingredients,
            "pricing_mode": version.pricing_mode,
        }
        for field in request.overrides.model_fields_set:
            override = getattr(request.overrides, field)
            values[field] = override
        return WeeklyMealPlanRequest.model_validate(values)

    @staticmethod
    def _constraint_changes(before: dict, after: dict) -> list[ProfileConstraintChange]:
        labels = {
            "household_size": "Household servings",
            "max_cooking_time_minutes": "Maximum cooking time",
            "budget_per_meal_sgd": "Per-meal budget",
            "weekly_budget_sgd": "Weekly budget",
            "allergens": "Allergens",
            "excluded_ingredients": "Excluded ingredients",
            "dietary_preferences": "Dietary requirements",
            "health_preferences": "Health preferences",
            "nutrition_targets": "Nutrition targets",
            "max_sodium_mg_per_meal": "Sodium target",
            "available_ingredients": "Available ingredients",
            "pricing_mode": "Pricing source",
        }
        return [
            ProfileConstraintChange(field=labels[key], before=before.get(key), after=after.get(key))
            for key in labels
            if before.get(key) != after.get(key)
        ]
