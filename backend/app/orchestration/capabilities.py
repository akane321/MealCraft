from app.orchestration.contracts import (
    CapabilitySpec,
    ToolAuthorizationDecision,
    ToolEffect,
    ToolSpec,
)

TOOL_SPECS: dict[str, ToolSpec] = {
    item.name: item
    for item in (
        ToolSpec(
            name="get_household_profile", effect=ToolEffect.READ, description="Read the authorized household profile."
        ),
        ToolSpec(
            name="search_recipe_candidates", effect=ToolEffect.READ, description="Retrieve grounded recipe candidates."
        ),
        ToolSpec(
            name="lookup_fairprice_products",
            effect=ToolEffect.READ,
            description="Retrieve timestamped product evidence.",
        ),
        ToolSpec(name="generate_plan_preview", effect=ToolEffect.PREVIEW, description="Run the deterministic planner."),
        ToolSpec(name="validate_plan", effect=ToolEffect.READ, description="Independently validate a plan preview."),
        ToolSpec(name="save_plan_revision", effect=ToolEffect.COMMIT, description="Commit a confirmed plan revision."),
        ToolSpec(
            name="generate_replan_preview", effect=ToolEffect.PREVIEW, description="Prepare a bounded plan change."
        ),
        ToolSpec(name="confirm_replan", effect=ToolEffect.COMMIT, description="Commit a confirmed replanning event."),
        ToolSpec(name="find_top1_tutorial", effect=ToolEffect.READ, description="Return one ranked cooking tutorial."),
        ToolSpec(name="get_nutrition_dashboard", effect=ToolEffect.READ, description="Read plan-only dashboard facts."),
    )
}

CAPABILITIES: dict[str, CapabilitySpec] = {
    item.intent: item
    for item in (
        CapabilitySpec(
            intent="create_plan",
            description="Create a validated meal-plan preview and commit only after confirmation.",
            allowed_tools=[
                "get_household_profile",
                "search_recipe_candidates",
                "lookup_fairprice_products",
                "generate_plan_preview",
                "validate_plan",
                "save_plan_revision",
            ],
            confirmation_required=True,
        ),
        CapabilitySpec(
            intent="replan_meal",
            description="Preview and confirm a change to an existing plan revision.",
            allowed_tools=["generate_replan_preview", "validate_plan", "confirm_replan"],
            confirmation_required=True,
        ),
        CapabilitySpec(
            intent="find_tutorial",
            description="Find one grounded cooking tutorial for a selected recipe.",
            allowed_tools=["find_top1_tutorial"],
        ),
        CapabilitySpec(
            intent="show_dashboard",
            description="Read plan-only nutrition and execution facts.",
            allowed_tools=["get_nutrition_dashboard"],
        ),
    )
}


def allowed_tools_for(intent: str, *, confirmed: bool = False) -> set[str]:
    capability = CAPABILITIES.get(intent)
    if capability is None:
        return set()
    tools = set(capability.allowed_tools)
    if not confirmed:
        tools = {name for name in tools if TOOL_SPECS[name].effect is not ToolEffect.COMMIT}
    return tools


def authorize_tool_call(
    intent: str,
    tool_name: str,
    *,
    confirmed: bool = False,
) -> ToolAuthorizationDecision:
    """Return an auditable deny-by-default decision for a proposed tool call."""
    capability = CAPABILITIES.get(intent)
    if capability is None:
        return ToolAuthorizationDecision(
            intent=intent,
            tool_name=tool_name,
            allowed=False,
            confirmation_present=confirmed,
            reason_code="UNKNOWN_CAPABILITY",
        )
    if tool_name not in TOOL_SPECS or tool_name not in capability.allowed_tools:
        return ToolAuthorizationDecision(
            intent=intent,
            tool_name=tool_name,
            allowed=False,
            confirmation_present=confirmed,
            reason_code="TOOL_NOT_ALLOWED_FOR_CAPABILITY",
        )
    if TOOL_SPECS[tool_name].effect is ToolEffect.COMMIT and not confirmed:
        return ToolAuthorizationDecision(
            intent=intent,
            tool_name=tool_name,
            allowed=False,
            confirmation_present=False,
            reason_code="CONFIRMATION_REQUIRED",
        )
    return ToolAuthorizationDecision(
        intent=intent,
        tool_name=tool_name,
        allowed=True,
        confirmation_present=confirmed,
        reason_code="AUTHORIZED",
    )
