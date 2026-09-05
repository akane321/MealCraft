from app.orchestration.contracts import CapabilitySpec, ToolEffect, ToolSpec

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
