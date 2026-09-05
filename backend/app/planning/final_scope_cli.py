import json
from pathlib import Path

from app.planning.final_scope_reference import FinalScopeReferencePlanner
from app.schemas.planning_v2 import FinalPlanningProblem


def main() -> None:
    fixture = Path("data/fixtures/planning-v2/final-scope-multislot.json")
    problem = FinalPlanningProblem.model_validate_json(fixture.read_text(encoding="utf-8"))
    solution = FinalScopeReferencePlanner().solve(problem)
    print(json.dumps(solution.model_dump(mode="json"), indent=2))


if __name__ == "__main__":
    main()
