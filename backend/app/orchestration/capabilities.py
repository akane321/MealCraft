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
            name="get_recipe_detail",
            effect=ToolEffect.READ,
            description="Read a catalog recipe and its ingredients.",
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
        ToolSpec(
            name="read_saved_plan",
            effect=ToolEffect.READ,
            description="Read the authorized saved plan and its facts.",
        ),
        ToolSpec(name="route_planning_request", effect=ToolEffect.READ, description="Route a meal-planning request."),
        ToolSpec(name="route_food_question", effect=ToolEffect.READ, description="Route a food question."),
        ToolSpec(name="route_social_message", effect=ToolEffect.READ, description="Route a social message."),
        ToolSpec(
            name="route_partial_request",
            effect=ToolEffect.READ,
            description="Route meal and unrelated segments.",
        ),
        ToolSpec(name="route_out_of_scope", effect=ToolEffect.READ, description="Route an unsupported request."),
        ToolSpec(name="route_restricted_request", effect=ToolEffect.READ, description="Route a restricted request."),
        ToolSpec(name="route_ambiguous_request", effect=ToolEffect.READ, description="Route an unclear request."),
        ToolSpec(name="route_adversarial_request", effect=ToolEffect.READ, description="Route adversarial content."),
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
        CapabilitySpec(
            intent="answer_food_question",
            description="Answer supported questions from an authorized saved plan without changing it.",
            allowed_tools=["read_saved_plan", "get_recipe_detail"],
        ),
        CapabilitySpec(
            intent="classify_scope",
            description="Select one application routing tool without mutating data.",
            allowed_tools=[
                "route_planning_request",
                "route_food_question",
                "route_social_message",
                "route_partial_request",
                "route_out_of_scope",
                "route_restricted_request",
                "route_ambiguous_request",
                "route_adversarial_request",
            ],
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
