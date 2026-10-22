from pydantic import BaseModel

from app.orchestration.tool_scheduler import ExecutableTool, ModelToolScheduler


class Args(BaseModel):
    plan_id: int


class FakeBoundModel:
    def __init__(self):
        self.responses = [
            type(
                "Response",
                (),
                {
                    "tool_calls": [{"name": "read_saved_plan", "args": {"plan_id": 5}, "id": "call-1"}],
                    "content": "",
                },
            )(),
            type("Response", (), {"tool_calls": [], "content": "The saved plan has five dinners."})(),
        ]

    def invoke(self, messages):
        return self.responses.pop(0)


class FakeChatOpenAI:
    bound = None
    bound_tools = []

    def __init__(self, **kwargs):
        pass

    def bind_tools(self, tools, **kwargs):
        self.bound = FakeBoundModel()
        type(self).bound_tools = tools
        return self.bound


def test_scheduler_executes_only_capability_authorized_typed_tools(monkeypatch):
    import app.orchestration.tool_scheduler as scheduler_module

    monkeypatch.setattr(scheduler_module, "ChatOpenAI", FakeChatOpenAI)
    invoked = []
    scheduler = ModelToolScheduler(api_key="test", model="test")
    tools = {
        "read_saved_plan": ExecutableTool(
            name="read_saved_plan",
            description="Read the caller's saved plan.",
            arguments=Args,
            handler=lambda args: invoked.append(args.plan_id) or {"dinners": 5},
        ),
        "save_plan_revision": ExecutableTool(
            name="save_plan_revision",
            description="Commit a plan.",
            arguments=Args,
            handler=lambda args: invoked.append(-args.plan_id),
        ),
    }

    result = scheduler.run(intent="answer_food_question", prompt="How many dinners are planned?", tools=tools)

    assert result.answer == "The saved plan has five dinners."
    assert result.calls == 1 and result.denied_calls == 0
    assert invoked == [5]
    assert [tool["name"] for tool in FakeChatOpenAI.bound_tools] == ["read_saved_plan"]
