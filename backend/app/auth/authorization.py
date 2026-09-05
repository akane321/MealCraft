from __future__ import annotations

from enum import StrEnum


class HouseholdRole(StrEnum):
    OWNER = "owner"
    EDITOR = "editor"
    MEMBER = "member"
    VIEWER = "viewer"


class HouseholdAction(StrEnum):
    VIEW = "view"
    EDIT_PROFILE = "edit_profile"
    CREATE_PLAN = "create_plan"
    CHECK_IN = "check_in"
    MANAGE_MEMBERS = "manage_members"
    DELETE_HOUSEHOLD = "delete_household"


class SystemRole(StrEnum):
    ORDINARY_USER = "ordinary_user"
    DATA_REVIEWER = "data_reviewer"
    OPERATOR = "operator"
    ADMIN = "admin"


class OperationsAction(StrEnum):
    VIEW_RUNS = "view_runs"
    REVIEW_DATA = "review_data"
    RETRY_RETRIEVAL = "retry_retrieval"
    RUN_EVALUATION = "run_evaluation"
    MANAGE_SYSTEM_ROLES = "manage_system_roles"


HOUSEHOLD_PERMISSIONS: dict[HouseholdRole, frozenset[HouseholdAction]] = {
    HouseholdRole.OWNER: frozenset(HouseholdAction),
    HouseholdRole.EDITOR: frozenset(
        {
            HouseholdAction.VIEW,
            HouseholdAction.EDIT_PROFILE,
            HouseholdAction.CREATE_PLAN,
            HouseholdAction.CHECK_IN,
        }
    ),
    HouseholdRole.MEMBER: frozenset(
        {
            HouseholdAction.VIEW,
            HouseholdAction.CREATE_PLAN,
            HouseholdAction.CHECK_IN,
        }
    ),
    HouseholdRole.VIEWER: frozenset({HouseholdAction.VIEW}),
}

OPERATIONS_PERMISSIONS: dict[SystemRole, frozenset[OperationsAction]] = {
    SystemRole.ORDINARY_USER: frozenset(),
    SystemRole.DATA_REVIEWER: frozenset({OperationsAction.VIEW_RUNS, OperationsAction.REVIEW_DATA}),
    SystemRole.OPERATOR: frozenset(
        {
            OperationsAction.VIEW_RUNS,
            OperationsAction.REVIEW_DATA,
            OperationsAction.RETRY_RETRIEVAL,
            OperationsAction.RUN_EVALUATION,
        }
    ),
    SystemRole.ADMIN: frozenset(OperationsAction),
}


def may_access_household(role: HouseholdRole | str, action: HouseholdAction) -> bool:
    return action in HOUSEHOLD_PERMISSIONS[HouseholdRole(role)]


def may_access_operations(role: SystemRole | str, action: OperationsAction) -> bool:
    return action in OPERATIONS_PERMISSIONS[SystemRole(role)]
