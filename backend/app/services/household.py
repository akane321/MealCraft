from app.core.clock import today as local_today
from app.data.household_reference import daily_energy_kcal, sodium_limit
from app.models.household import HouseholdProfile, HouseholdProfileVersion
from app.planning.capability import require_composition_enabled
from app.repositories.household import HouseholdProfileRepository, HouseholdProfileVersionConflictError
from app.repositories.meal_plan import MealPlanRepository
from app.schemas.household import (
    HouseholdMemberInput,
    HouseholdMemberResponse,
    HouseholdProfilePlanRequest,
    HouseholdProfilePlanResponse,
    HouseholdProfileResponse,
    HouseholdProfileUpdate,
    HouseholdProfileVersionCollectionResponse,
    HouseholdProfileVersionResponse,
    HouseholdProfileWrite,
    ProfileConstraintChange,
)
from app.schemas.household_rules import HouseholdPlanning, NutritionLimit, PlanningMember
from app.schemas.meal_plan import WeeklyMealPlanRequest, default_plan_shape
from app.schemas.recommendation import NutritionTargets
from app.services.meal_plan import WeeklyMealPlanService


class HouseholdProfileNotFoundError(RuntimeError):
    pass


class HouseholdProfileAlreadyExistsError(RuntimeError):
    pass


class HouseholdProfilePlanError(RuntimeError):
    pass


def household_planning(version: HouseholdProfileVersion) -> HouseholdPlanning:
    """A saved version's members, rules and limits as the planner reads them (layer 08): each member's portions,
    own allergens, exclusions, diet and HPB energy target, and a sodium limit left to HPB resolved to the
    tightest limit of the members usually home.

    A member's `allergens` holds every allergen of theirs, the ones marked "only I avoid it" included: those are
    this member's own food rule. What the whole household avoids is the version's `allergens` column
    (ADR-0071 section 2), which `HouseholdProfileService._planning_constraints` passes as the request's own.
    """
    members = [HouseholdMemberInput.model_validate(member) for member in version.members]
    home = [member for member in members if member.default_present]
    limits = []
    for limit in version.nutrition_limits or []:
        limit = NutritionLimit.model_validate(limit)
        if limit.max_value is None:
            known = [value for value in (sodium_limit(member.age_band) for member in home) if value is not None]
            limit = limit.model_copy(update={"max_value": min(known) if known else None})
        limits.append(limit)
    return HouseholdPlanning(
        members=[
            PlanningMember(
                name=m.name,
                servings=m.resolved_servings()[0],
                default_present=m.default_present,
                allergens=m.allergens,
                excluded_ingredients=m.excluded_ingredients,
                dietary_preferences=list(m.dietary_preferences),
                daily_energy_kcal=daily_energy_kcal(m.age_band, m.sex, m.goal, m.activity),
            )
            for m in members
        ],
        presence_rules=version.presence_rules or [],
        cooking_time_rules=version.cooking_time_rules or [],
        missing_basics=version.missing_basics or [],
        nutrition_limits=[limit for limit in limits if limit.max_value is not None],
        protein_priority=any(member.goal == "muscle_gain" for member in members),
        missing_equipment=getattr(version, "missing_equipment", None) or [],
    )


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
        require_composition_enabled(payload.meal_composition)
        for roles in payload.plan_shape.meals.values() if payload.plan_shape else []:
            require_composition_enabled(roles)
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
        require_composition_enabled(write_payload.meal_composition)
        for roles in write_payload.plan_shape.meals.values() if write_payload.plan_shape else []:
            require_composition_enabled(roles)
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
        # Rebuilding a week still under way keeps its dates; a week that has ended is
        # replaced by one starting on the requested date, not replayed in the past.
        start = previous.start_date if previous.end_date >= local_today() else request.start_date
        replan_request = request.model_copy(update={"start_date": start})
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
            members=[HouseholdMemberResponse.of(member) for member in version.members],
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
            meal_composition=version.meal_composition,
            plan_shape=version.plan_shape,
            presence_rules=version.presence_rules or [],
            cooking_time_rules=version.cooking_time_rules or [],
            missing_basics=version.missing_basics or [],
            nutrition_limits=version.nutrition_limits or [],
            missing_equipment=version.missing_equipment or [],
            created_at=version.created_at,
        )

    @staticmethod
    def _planning_constraints(
        version: HouseholdProfileVersion,
        request: HouseholdProfilePlanRequest,
    ) -> WeeklyMealPlanRequest:
        values = {
            "start_date": request.start_date,
            "day_count": request.day_count,
            "household_size": version.planning_household_size,
            "max_cooking_time_minutes": version.max_cooking_time_minutes,
            "budget_per_meal_sgd": (
                float(version.budget_per_meal_sgd) if version.budget_per_meal_sgd is not None else None
            ),
            "weekly_budget_sgd": float(version.weekly_budget_sgd) if version.weekly_budget_sgd is not None else None,
            # The whole household's limits only. Each member's exclusions and diet travel with the member
            # (ADR-0071 sections 1 and 2), so one member's diet no longer narrows the week for everyone; the
            # union columns stay stored for compatibility and are not read here.
            "allergens": version.allergens,
            "excluded_ingredients": [],
            "dietary_preferences": [],
            "health_preferences": version.health_preferences,
            "nutrition_targets": NutritionTargets.model_validate(version.nutrition_targets),
            "max_sodium_mg_per_meal": (
                float(version.max_sodium_mg_per_meal) if version.max_sodium_mg_per_meal is not None else None
            ),
            "available_ingredients": version.available_ingredients,
            "pricing_mode": version.pricing_mode,
            "meal_composition": version.meal_composition if version.plan_shape is None else None,
            # A household that set neither plans the full default (ADR-0070); a saved shape is used as stored.
            "plan_shape": version.plan_shape
            or (default_plan_shape().model_dump(mode="json") if version.meal_composition is None else None),
            "household": household_planning(version),
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
            "meal_composition": "Dishes per meal",
            "plan_shape": "Meals and dishes",
            "household.members": "Members' portions",
            "household.presence_rules": "Who is home",
            "household.cooking_time_rules": "Cooking-time rules",
            "household.missing_basics": "Basics to buy",
            "household.nutrition_limits": "Nutrition limits",
            "household.missing_equipment": "Kitchen equipment",
            "day_count": "Days planned",
        }

        def value(constraints: dict, key: str):
            if not key.startswith("household."):
                return constraints.get(key)
            household = constraints.get("household") or {}
            return household.get(key.removeprefix("household.")) or None  # no rules and an empty list are one

        return [
            ProfileConstraintChange(field=labels[key], before=value(before, key), after=value(after, key))
            for key in labels
            if value(before, key) != value(after, key)
        ]
