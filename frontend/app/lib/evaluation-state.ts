export type EvaluationUiState = "loading" | "empty" | "ready" | "error";

export interface EvaluationUiStateInput {
  isLoading: boolean;
  hasData: boolean;
  errorMessage?: string | null;
}

export function resolveEvaluationUiState(input: EvaluationUiStateInput): EvaluationUiState {
  if (input.errorMessage) return "error";
  if (input.isLoading) return "loading";
  return input.hasData ? "ready" : "empty";
}
