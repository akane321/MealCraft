type MealType = "breakfast" | "lunch" | "dinner" | "snack";
type Flavor = "fragrant" | "spicy" | "light" | "rich";

export interface PlanningPreferencesView {
  repeat_allowed_meals: MealType[];
  flavor_boosts: Array<{ flavor: Flavor; weekdays: string[]; meal_types: MealType[] }>;
  more_vegetables: boolean;
  lighter: boolean;
}

export function copyPlanningPreferences(value?: PlanningPreferencesView | null): PlanningPreferencesView {
  return value ? {
    repeat_allowed_meals: [...value.repeat_allowed_meals],
    flavor_boosts: value.flavor_boosts.map(boost => ({ ...boost, weekdays: [...boost.weekdays], meal_types: [...boost.meal_types] })),
    more_vegetables: value.more_vegetables,
    lighter: value.lighter,
  } : { repeat_allowed_meals: [], flavor_boosts: [], more_vegetables: false, lighter: false };
}

const mealLabels: Record<MealType, string> = {
  breakfast: "breakfast",
  lunch: "lunch",
  dinner: "dinner",
  snack: "snack",
};

const flavorLabels: Record<Flavor, string> = {
  fragrant: "Fragrant",
  spicy: "Spicy",
  light: "Light",
  rich: "Rich",
};

const dayLabels: Record<string, string> = {
  monday: "Mon",
  tuesday: "Tue",
  wednesday: "Wed",
  thursday: "Thu",
  friday: "Fri",
  saturday: "Sat",
  sunday: "Sun",
};

export function planningPreferenceLabels(preferences?: PlanningPreferencesView | null): string[] {
  if (!preferences) return [];
  const labels = preferences.repeat_allowed_meals.map(meal => `${mealLabels[meal]} can repeat`);
  for (const boost of preferences.flavor_boosts) {
    const scope = [
      boost.weekdays.map(day => dayLabels[day] ?? day).join(", "),
      boost.meal_types.map(meal => mealLabels[meal]).join(", "),
    ].filter(Boolean).join(" ");
    labels.push(`${flavorLabels[boost.flavor]}${scope ? ` · ${scope}` : ""}`);
  }
  if (preferences.more_vegetables) labels.push("More vegetables");
  if (preferences.lighter) labels.push("Lighter meals");
  return labels;
}
