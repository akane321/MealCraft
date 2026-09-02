import { describe, expect, it } from "vitest";

import { resolveEvaluationUiState } from "../app/lib/evaluation-state";

describe("evaluation UI state precedence", () => {
  it.each([
    [{ isLoading: true, hasData: false }, "loading"],
    [{ isLoading: false, hasData: false }, "empty"],
    [{ isLoading: false, hasData: true }, "ready"],
    [{ isLoading: true, hasData: true }, "loading"],
    [{ isLoading: false, hasData: true, errorMessage: "Request failed" }, "error"],
    [{ isLoading: true, hasData: false, errorMessage: "Request failed" }, "error"],
  ] as const)("maps %o to %s", (input, expected) => {
    expect(resolveEvaluationUiState(input)).toBe(expected);
  });
});
