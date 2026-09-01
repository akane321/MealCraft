import type { AgentSessionStatus } from "~/types/agent";
import type { AvailableIngredientInput } from "~/types/recommendation";

export function formatOptionalNumber(value: number | null, suffix = ""): string {
  return value === null ? "Not specified" : `${value}${suffix}`;
}

export function formatPantryQuantity(item: AvailableIngredientInput): string {
  if (item.quantity === null) return "Unknown · ranking only";
  return `${item.quantity} ${item.unit || ""}`.trim();
}

export function activeAgentPhase(status: AgentSessionStatus | null): number {
  if (status === "planned" || status === "ready") return 3;
  if (status === "collecting") return 2;
  return 1;
}
