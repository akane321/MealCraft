import type { MealPlanEventType, MealPlanGroceryDeltaLine } from "~/types/meal-plan";

export const replanEventOptions: { value: MealPlanEventType; label: string; description: string }[] = [
  {
    value: "REPLACE_MEAL",
    label: "Replace this meal",
    description: "Choose the best alternative while keeping the rest of the week stable.",
  },
  {
    value: "CANCEL_MEAL",
    label: "Cancel this meal",
    description: "Mark this meal as skipped and remove its demand from the shopping estimate.",
  },
  {
    value: "LOCK_MEAL",
    label: "Lock this meal",
    description: "Protect this meal from later replanning while still allowing check-in.",
  },
  {
    value: "ITEM_UNAVAILABLE",
    label: "Ingredient unavailable",
    description: "Find an alternative recipe that does not use the unavailable ingredient.",
  },
];

export function eventTypeLabel(type: MealPlanEventType): string {
  return replanEventOptions.find(option => option.value === type)?.label || type;
}

export function formatSigned(value: number, unit = ""): string {
  const rounded = Math.abs(value) < 0.005 ? 0 : value;
  const sign = rounded > 0 ? "+" : rounded < 0 ? "−" : "";
  return `${sign}${Math.abs(rounded).toFixed(rounded % 1 === 0 ? 0 : 1)}${unit}`;
}

export function groceryDeltaSummary(line: MealPlanGroceryDeltaLine): string {
  if (line.change === "added") return `${line.after_packages_required} package(s) added`;
  if (line.change === "removed") return `${line.before_packages_required} package(s) removed`;
  return `${line.before_packages_required} → ${line.after_packages_required} package(s)`;
}
