import type { PricingMode } from "~/types/recommendation";
import type { HealthResponse } from "~/types/system";

export interface ServiceStatus {
  name: string;
  state: "Working" | "Not available";
  healthy: boolean;
}

/** What a household can do right now, in its own words: the page it reads already works, so it is not listed. */
export function createServiceStatuses(health?: HealthResponse): ServiceStatus[] {
  const backendHealthy = health?.status === "ok";
  const databaseHealthy = backendHealthy && health?.database === "connected";
  const row = (name: string, healthy: boolean): ServiceStatus => ({ name, state: healthy ? "Working" : "Not available", healthy });

  return [
    row("Planning and the assistant", backendHealthy),
    row("Your weeks and household", databaseHealthy),
  ];
}

/** Which prices the household's shopping list uses (ADR-0026 section 4: sample prices never pass as today's). */
export function pricesLine(mode: PricingMode | null | undefined): string {
  if (mode === "live") return "The final shopping list checks FairPrice prices and may reuse saved prices. If a lookup fails, the selected saved or sample price is kept. Each item shows its price source and check time when available.";
  if (mode === "fixture") return "Sample prices. They stay the same and are not today's FairPrice prices.";
  return "Sample prices, unless your household chooses today's FairPrice prices.";
}
