import { describe, expect, it } from "vitest";

import { activeAgentPhase, formatPantryQuantity } from "../app/lib/agent-format";

describe("agent presentation helpers", () => {
  it("keeps unknown pantry quantities explicit as ranking-only preferences", () => {
    expect(formatPantryQuantity({ normalized_name: "chicken_breast", quantity: null, unit: null }))
      .toBe("Unknown · ranking only");
  });

  it("maps persistent session states to the three-step progress rail", () => {
    expect(activeAgentPhase(null)).toBe(1);
    expect(activeAgentPhase("collecting")).toBe(2);
    expect(activeAgentPhase("ready")).toBe(3);
    expect(activeAgentPhase("planned")).toBe(3);
  });
});
